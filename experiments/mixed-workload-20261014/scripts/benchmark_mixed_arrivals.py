"""Finite scheduled arrivals; disposable SQL and 30ms API-style fake only."""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import closing, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--pairs', type=int, default=30)
parser.add_argument('--repeats', type=int, default=3)
parser.add_argument('--intervals-ms', nargs='+', type=float, default=[200, 100, 90, 80, 75])
parser.add_argument('--modes', nargs='+', choices=['fifo', 'ptc', 'ptc_poll'],
                    default=['fifo', 'ptc', 'ptc_poll'])
parser.add_argument('--expected-sha', default='d935987f016cfc1038b624a7b4cb6a03ad9f8baa')
args = parser.parse_args()
args.repo = args.repo.resolve()
args.output = args.output.resolve()
if not 1 <= args.pairs <= 100 or not 1 <= args.repeats <= 10:
    parser.error('pairs must be 1..100 and repeats 1..10')
if any(not 1 <= value <= 1000 for value in args.intervals_ms):
    parser.error('intervals must be finite values in 1..1000 ms')
if len(set(args.modes)) != len(args.modes) or len(set(args.intervals_ms)) != len(args.intervals_ms):
    parser.error('modes and intervals must be unique')
if args.output == args.repo or args.repo in args.output.parents:
    parser.error('output must be outside the source checkout')
if args.output.exists() and any(args.output.iterdir()):
    parser.error('output directory must be empty; preserve previous runs')
def git(*arguments):
    return subprocess.check_output(['git', '-C', str(args.repo), *arguments], text=True).strip()
source_sha = git('rev-parse', 'HEAD')
expected = git('rev-parse', '--verify', args.expected_sha + '^{commit}')
if source_sha != expected or git('status', '--porcelain'):
    parser.error('checkout must be clean and match expected-sha')
args.output.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(args.repo))
from pulpo import GovernanceKernel, Intent, Policy, SQLiteKernelState
from pulpo.orchestrator import PulpoOrchestrator
from pulpo.traffic import Path as Route, TrafficControl, Backpressure

PAIRS = args.pairs
REPEATS = args.repeats
PERIODS_MS = tuple(args.intervals_ms)
MODES = tuple(args.modes)

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def p95(values):
    return sorted(values)[max(0, (95 * len(values) + 99) // 100 - 1)]

def run(mode, interval_ms):
    with tempfile.TemporaryDirectory(prefix='pulpo-arrivals-') as scratch:
        root = Path(scratch)
        effect_db = root / 'effects.sqlite'
        with closing(sqlite3.connect(effect_db)) as db, db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE effects (resource TEXT PRIMARY KEY)')
        state = SQLiteKernelState(root / 'governance.sqlite')
        try:
            kernel = GovernanceKernel(Policy(frozenset({'fixture_write'}), 0),
                secret=b'finite-arrival-fixture-only', state=state)
            owner = PulpoOrchestrator(kernel)
            responsive = mode == 'ptc_poll'
            sqlite_settings = dict(journal_mode=state._connection.execute(
                'PRAGMA journal_mode').fetchone()[0], synchronous=state._connection.execute(
                'PRAGMA synchronous').fetchone()[0])
            require(sqlite_settings['synchronous'] == 2, 'FULL durability required')
            jobs = [dict(lane=lane, intent=Intent('fixture', 'fixture_write',
                    f'fixture:{lane}:{index}'), pair=index, decision=None)
                    for index in range(PAIRS) for lane in ('sql', 'api')]
            router = None
            if mode in ('ptc', 'ptc_poll'):
                router = TrafficControl.for_sql_api(
                    tuple(Route(j['intent'].resource, j['lane'], j['intent']) for j in jobs),
                    sql_queue_limit=8, api_queue_limit=8)
            queues = {lane: deque() for lane in ('sql', 'api')}
            fifo = deque()
            pending = deque()
            active = {}
            occupied = dict(sql=0, api=0)
            limits = dict(sql=1, api=2)
            peaks = dict(sql=0, api=0)
            claims, completed = [], []
            cursor, blocked, backlog_peak = 0, 0, 0
            epoch = time.perf_counter() + 0.020
            for j in jobs:
                j['arrival'] = epoch + j['pair'] * interval_ms / 1000
            by_resource = {j['intent'].resource: j for j in jobs}
            stop_at = epoch + (PAIRS - 1) * interval_ms / 1000 + 30

            @contextmanager
            def direct(intent, permit):
                require(kernel.consume(permit, intent), 'FIFO permit rejected')
                yield

            def effect(lane, intent):
                worker_started = time.perf_counter()
                if lane == 'sql':
                    with closing(sqlite3.connect(effect_db)) as db, db:
                        db.execute('PRAGMA synchronous=FULL')
                        db.execute('INSERT INTO effects VALUES (?)', (intent.resource,))
                    time.sleep(0.002)
                else:
                    time.sleep(0.030)
                worker_finished = time.perf_counter()
                return dict(resource=intent.resource, finished=worker_finished,
                    effect_ms=(worker_finished - worker_started) * 1000)

            def collect_ready():
                # The same completion path is used by all three owner modes.
                # Candidate only calls it more often; authority gates are unchanged.
                for future in tuple(active):
                    if not future.done():
                        continue
                    j, context = active.pop(future)
                    try:
                        result = future.result()
                        require(result['resource'] == j['intent'].resource,
                                'effect target mismatch')
                    finally:
                        occupied[j['lane']] -= 1
                        context.__exit__(None, None, None)
                    observed = time.perf_counter()
                    completed.append(dict(lane=j['lane'], resource=j['intent'].resource,
                        admission_ms=j['admission_ms'],
                        authorization_wait_ms=j['authorization_wait_ms'],
                        authorization_ms=j['authorization_ms'],
                        authorization_cpu_ms=j['authorization_cpu_ms'],
                        consume_dispatch_ms=j['consume_dispatch_ms'],
                        consume_dispatch_cpu_ms=j['consume_dispatch_cpu_ms'],
                        effect_ms=result['effect_ms'],
                        observation_delay_ms=(observed - result['finished']) * 1000,
                        worker_completion_latency_ms=(result['finished'] - j['arrival']) * 1000,
                        latency_ms=(observed - j['arrival']) * 1000))

            with ThreadPoolExecutor(max_workers=3) as workers:
                while len(completed) < len(jobs):
                    if responsive:
                        collect_ready()
                    now = time.perf_counter()
                    require(now < stop_at, 'bounded workload timed out')
                    while cursor < len(jobs) and jobs[cursor]['arrival'] <= now:
                        pending.append(jobs[cursor])
                        cursor += 1
                    backlog_peak = max(backlog_peak, len(pending))
                    # Finite caller backlog; original unused claims survive backpressure.
                    for _ in range(len(pending)):
                        if responsive:
                            collect_ready()
                        j = pending.popleft()
                        if j['decision'] is None:
                            auth_started = time.perf_counter()
                            auth_cpu = time.process_time()
                            decision = kernel.evaluate(j['intent'])
                            j['authorization_ms'] = (time.perf_counter() - auth_started) * 1000
                            j['authorization_cpu_ms'] = (time.process_time() - auth_cpu) * 1000
                            j['authorization_wait_ms'] = (auth_started - j['arrival']) * 1000
                            require(decision.outcome == 'allow' and decision.permit,
                                    'fixture authorization denied')
                            j['decision'] = decision
                            claims.append((j['intent'], decision.permit))
                        if router is not None:
                            try:
                                router.enqueue(j['intent'], j['decision'],
                                               (j['intent'].resource,))
                            except Backpressure:
                                pending.append(j)
                                blocked += 1
                                continue
                        else:
                            if len(queues[j['lane']]) == 8:
                                pending.append(j)
                                blocked += 1
                                continue
                            queues[j['lane']].append(j)
                            fifo.append(j)
                        j['admission_ms'] = (time.perf_counter() - j['arrival']) * 1000
                    if router is not None:
                        for lane, value in router.snapshot().items():
                            require(value['queued'] <= 8, 'queue bound exceeded')
                            peaks[lane] = max(peaks[lane], value['queued'])
                    else:
                        for lane, queue in queues.items():
                            peaks[lane] = max(peaks[lane], len(queue))
                    while True:
                        if responsive:
                            collect_ready()
                        dispatch_started = time.perf_counter()
                        dispatch_cpu = time.process_time()
                        if router is not None:
                            context = owner.traffic_dispatch(router)
                            dispatch = context.__enter__()
                            if dispatch is None:
                                context.__exit__(None, None, None)
                                break
                            j = by_resource[dispatch.work.intent.resource]
                        else:
                            if not fifo or occupied[fifo[0]['lane']] >= limits[fifo[0]['lane']]:
                                break
                            j = fifo.popleft()
                            require(queues[j['lane']].popleft() is j, 'FIFO order mismatch')
                            context = direct(j['intent'], j['decision'].permit)
                            context.__enter__()
                        j['consume_dispatch_ms'] = (time.perf_counter() - dispatch_started) * 1000
                        j['consume_dispatch_cpu_ms'] = (time.process_time() - dispatch_cpu) * 1000
                        lane = j['lane']
                        occupied[lane] += 1
                        require(occupied[lane] <= limits[lane], 'slot limit exceeded')
                        try:
                            future = workers.submit(effect, lane, j['intent'])
                        except BaseException:
                            occupied[lane] -= 1
                            context.__exit__(*sys.exc_info())
                            raise
                        active[future] = (j, context)
                    if len(completed) == len(jobs):
                        break
                    now = time.perf_counter()
                    next_arrival = jobs[cursor]['arrival'] if cursor < len(jobs) else stop_at
                    delay = max(0, min(next_arrival, stop_at) - now)
                    if not active:
                        require(not pending and not fifo, 'idle fixture with retained work')
                        time.sleep(delay)
                        continue
                    wait(active, timeout=delay, return_when=FIRST_COMPLETED)
                    collect_ready()
            require(not pending and not fifo and not active and not any(occupied.values()),
                    'retained work after completion')
            if router is not None:
                require(all(not v['queued'] and not v['active'] for v in router.snapshot().values()),
                        'router failed to drain')
            expected = sorted(j['intent'].resource for j in jobs)
            require(sorted(j['resource'] for j in completed) == expected, 'completion mismatch')
            with closing(sqlite3.connect(effect_db)) as db:
                require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'database corrupt')
                require(sorted(r[0] for r in db.execute('SELECT resource FROM effects')) ==
                        sorted(j['intent'].resource for j in jobs if j['lane'] == 'sql'), 'rows mismatch')
            require(sum(r['event'] == 'permit_consumed' for r in kernel.audit) == len(jobs),
                    'permit count mismatch')
            require(kernel.verify_audit(), 'invalid audit')
            require(all(not kernel.consume(permit, intent) for intent, permit in claims),
                    'permit replay accepted')
            require(kernel.verify_audit(), 'invalid audit after replay checks')
            class_p95 = {lane: p95([j['latency_ms'] for j in completed if j['lane'] == lane])
                         for lane in ('sql', 'api')}
            return dict(mode=mode, interval_ms=interval_ms, class_p95_ms=class_p95,
                worst_ms=max(j['latency_ms'] for j in completed),
                misses_100ms=sum(j['latency_ms'] >= 100 for j in completed),
                queue_peaks=peaks, caller_backlog_peak=backlog_peak,
                backpressure_attempts=blocked, jobs=completed, correctness_passed=True,
                both_classes_p95_under_100ms=max(class_p95.values()) < 100,
                sqlite_settings=sqlite_settings)
        finally:
            state.close()

samples = []
for round_number in range(REPEATS):
    periods = PERIODS_MS if round_number % 2 == 0 else tuple(reversed(PERIODS_MS))
    for interval in periods:
        base_modes = MODES
        shift = round_number % len(base_modes)
        modes = base_modes[shift:] + base_modes[:shift]
        for mode in modes:
            row = run(mode, interval)
            row['round'] = round_number + 1
            samples.append(row)
            print(f"round {round_number + 1} {mode} every {interval}ms: "
                  f"SQL P95 {row['class_p95_ms']['sql']:.1f}ms; "
                  f"API P95 {row['class_p95_ms']['api']:.1f}ms; "
                  f"misses {row['misses_100ms']}/{PAIRS * 2}", flush=True)
            (args.output / 'partial.json').write_text(json.dumps(samples, indent=2) + '\n')
summary = []
for interval in PERIODS_MS:
    for mode in MODES:
        rows = [r for r in samples if r['interval_ms'] == interval and r['mode'] == mode]
        jobs = [j for r in rows for j in r['jobs']]
        class_p95 = {lane: p95([j['latency_ms'] for j in jobs if j['lane'] == lane])
                     for lane in ('sql', 'api')}
        row = dict(mode=mode, interval_ms=interval, offered_pairs_per_second=1000 / interval,
            offered_jobs_per_second=2000 / interval, pooled_class_p95_ms=class_p95,
            rounds_passing=sum(r['both_classes_p95_under_100ms'] for r in rows),
            rounds=REPEATS, misses_100ms=sum(r['misses_100ms'] for r in rows),
            total_jobs=len(jobs), worst_ms=max(r['worst_ms'] for r in rows),
            max_caller_backlog=max(r['caller_backlog_peak'] for r in rows),
            max_sql_queue=max(r['queue_peaks']['sql'] for r in rows),
            max_api_queue=max(r['queue_peaks']['api'] for r in rows))
        metrics = ('authorization_wait_ms', 'authorization_ms', 'authorization_cpu_ms',
                   'consume_dispatch_ms', 'consume_dispatch_cpu_ms',
                   'effect_ms', 'observation_delay_ms')
        row['stage_p95_ms'] = {metric: p95([j[metric] for j in jobs]) for metric in metrics}
        row['worker_completion_class_p95_ms'] = {lane: p95([
            j['worker_completion_latency_ms'] for j in jobs if j['lane'] == lane])
            for lane in ('sql', 'api')}
        summary.append(row)
        print(json.dumps(row), flush=True)
require(git('rev-parse', 'HEAD') == source_sha and not git('status', '--porcelain'),
        'source changed during the benchmark')
report = dict(schema='pulpo.mixed-arrival-fixture.v1', source_sha=source_sha,
    source_clean_after=True, intervals_ms=list(PERIODS_MS), modes=list(MODES),
    python=platform.python_version(), sqlite=sqlite3.sqlite_version,
    platform=platform.platform(), script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
    pairs_per_round=PAIRS, repeats=REPEATS, queue_limit_per_lane=8,
    scope='Finite predeclared scheduled arrivals, no provider calls. Latency starts at '
          'scheduled arrival and ends after observed effect completion and slot release; '
          'includes caller backlog, authorization and admission. Initialization and final '
          'verification excluded. No warm-up samples excluded. Not a sustained capacity guarantee.',
    source_sha256={name: sha256((args.repo / name).read_bytes()).hexdigest() for name in
        ('pulpo/kernel.py', 'pulpo/state.py', 'pulpo/traffic.py', 'pulpo/orchestrator.py')},
    candidate='ptc_poll observes finished workers before each authorization and dispatch; '
              'changes fixture owner scheduling only; no Pulpo source or runtime config changed',
    timing_cpu_scope='CPU timings are whole-process increments; overlapping worker CPU can contribute',
    samples=samples, summary=summary)
(args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print('Report:', args.output / 'report.json')
