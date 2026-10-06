# Reconciliation audit scan allocation reduction

Status: **Proposed** for Pulpo-Preview review. Inspected base: `main` at
`ee88a8ea5aa5496c06afaa82ec31db30c2e4e1fc`.

## Invariant and authority boundary

`SQLiteKernelState.append_unique()` now iterates its SELECT cursor instead of
materializing every raw matching-event row with `fetchall()`. It still reads
and decodes every matching-event row before deciding whether an identity exists.
A later duplicate remains ambiguous, and malformed later JSON still raises.

Authority effect: **none**. Canonical state mutations introduced or exposed:
**none**. New identities use the existing governed canonical append; repeated
identities return the original payload without writing new evidence. Existing
`BEGIN IMMEDIATE`, commit/rollback boundaries, `synchronous=FULL`, audit event
order, JSON representation, hashes, prefix authentication, replay guards,
permit spending, and reconciliation decisions are unchanged.

No router, ledger, cache, signing material, authority service, or runtime writer
interface is added. The crash harness mutates only disposable synthetic fixtures.

## Evidence and classifications

**Verified:** Windows focused baseline and candidate runs each passed 115 tests
with `-W error`; the 14 new indexed/unindexed storage tests passed on both
backends. Compilation and whitespace checks passed. Test profile resolution was
isolated to a workspace-local directory rather than the installed user profile.

**Recorded:** Extended Windows reconciliation selections encountered the same
eight file-lifetime errors in baseline and candidate. These were four affected
cases: two SQLite cleanup cases produced three errors each, and two cases could
not reopen a Windows `NamedTemporaryFile`. These selections are not classified
as passing Windows validation.

**Verified:** WSL Ubuntu, Python 3.12.14, SQLite 3.53.1: baseline 501 core tests
and the initial optimized candidate 515 core tests passed. Baseline and candidate
authority-service suites completed 65 tests with four optional integrations
skipped (61 passed); custody-service suites each passed 26 tests. All runs used
`-W error`. Initial core setup errors were repaired by fetching exact freeze
fixture `0eb1266fecf586c79457e0fcaf412bc6345545a2` from Pulpo-Preview; no fixture
or product behavior was modified. Final PR preparation reran the complete core
suites: baseline 501 and candidate 520 tests passed, including the five additional
crash-harness oracle tests. The existing temporal regression is not a
historical-transfer proof for this optimization.

**Verified:** The final local crash-harness validation passed three rounds on
each backend: 126 forced process interruptions, 18 SQLite failure cases, six
tamper controls, and 36 oracle/reconciliation unit tests. Five oracle controls
deliberately reject partial issuance, missing consumption evidence, and loss
of an acknowledged commit. Restart proofs run in fresh processes. Before/after
commit and scan checkpoints plus randomized interruptions cover issuance,
consumption, unique append, and replay. Public test-fixture secrets and disposable
databases are used; there are no live provider effects or human credentials.

Storage failures are actual SQLite audit-trigger aborts, lock-induced commit
failures, and `SQLITE_FULL` induced with a connection-local page limit. They do
not inject a physical disk-flush failure or fill the host disk. The harness
preserves complete recovered state, replay rejection, and prior unknown
consequence evidence. Separate domain tests cover real reconciliation logic
with synthetic observations.

Raw benchmark samples and test evidence are in `docs/evidence/evidence-io/`.
The manifest records source hashes and exact run summaries. Final PR validation
results, including the five added harness-oracle tests, are recorded there
separately from the earlier 515-test run.

| WSL same-event history | Baseline lookup median | Streaming lookup median | Baseline Python allocation peak | Streaming peak |
| --- | ---: | ---: | ---: | ---: |
| 1,000 rows | 2.203 ms | 2.250 ms | 1,100,765 bytes | 6,319 bytes |
| 10,000 rows | 26.312 ms | 26.121 ms | 11,353,133 bytes | 6,320 bytes |

**Recorded:** Five alternating samples per variant, ten lookups per sample,
1,024-byte payload detail. Each fixture independently passes full chain proof.
Allocation tracing is an untimed pass measuring Python allocations, not SQLite
native memory or RSS. Measured replays change zero rows. OS caches are not flushed.
The 10,000-row allocation reduction is 99.944%. Windows also measured 99.944%
lower Python allocation peak (41.682 to 39.896 ms lookup median).

**Inferred:** This reduces avoidable row materialization for large reconciliation
histories. Timing differences are small; general throughput improvement is not
established. No physical write reduction, flush reduction, or faster restart is
claimed. The scan and writer-lock holding remain O(n); matching decoded payloads
are still collected to preserve duplicate rejection behavior.

## Continued native Windows validation — pending

**Proposed:** Continue testing on a **native Windows installation of the app**
using the intended install package, actual configuration/profile locations,
real state directories, filesystem, and storage hardware. WSL and isolated
test checkouts do not complete this requirement.

Use dedicated test state and synthetic authority fixtures. Record Windows,
Python/packaged-runtime, SQLite, installer/build, filesystem, drive, and source
versions. An isolated harness pass must not be promoted to an installed-app pass.

- **Install and profile:** install/upgrade the app normally, verify the real
  profile loads, and exercise installed entry points with normal Windows user
  permissions. Check profile/state path access, locks, and file lifetime.
- **Durable lifecycle:** record synthetic approvals, permits, and reconciliation
  evidence; close/reopen the app and restart Windows normally. Acknowledged
  records must survive, consumed permits/approvals must remain rejected on replay,
  and unresolved consequences must remain unresolved until legitimate evidence
  settles them.
- **Windows interruption and contention:** terminate only the installed test
  process at documented boundaries, exercise concurrent instances/readers, and
  confirm atomic recovery and audit verification with the actual deployment
  layout. Record any interactions with Windows file locking and normal endpoint
  security software. Reproduce the prior file-lifetime cases using supported
  Windows fixtures; do not hide them with skips or treat Linux passes as repairs.
- **Representative load:** compare baseline and optimized installed builds on
  identical test data. Measure actual process memory, slow-request latency,
  throughput, and contention for realistic histories and payload sizes.
- **Storage failures:** validate deployment-appropriate failure handling on
  disposable storage. The Linux page-limit and lock tests alone do not establish
  native Windows device/flush behavior.

Success requires complete acknowledged evidence, atomic interrupted transitions,
unchanged replay/tamper rejection and reconciliation semantics, and no material
installed-app latency or contention regression. Record each outcome as Verified,
Recorded, Inferred, Proposed, or Unknown with its exact build and environment.

## Practical power-loss validation — pending

**Unknown:** Physical power-loss durability requires a practical test on a
dedicated machine using the intended OS, filesystem, drive/controller, and
storage configuration. Record acknowledged commits on a separate observer,
cut power during synthetic activity, then verify after restart that acknowledged
commits survived, interrupted transactions recovered atomically, the full audit
chain verifies, and replay guards remain correct. Unacknowledged operations may
have committed; reconciliation must preserve that uncertainty.

This PR does not automate machine shutdown or physical power cuts. WSL, process
`SIGKILL`, normal reboot, and a disposable VM crash do not validate the entire
physical storage stack. Actual flush failure, whole-valid-database rollback or
replacement resistance, production benefit, and skipped optional integrations
remain Unknown. Existing atomic rollback tests do not establish a monotonic
storage guarantee.

## Reproduce Linux tests

Run from a Linux/WSL checkout of this PR using Python 3.11 or newer:

```sh
python3 -W error -m unittest tests.test_crash_recovery_harness tests.test_unique_audit_scan -v
python3 -W error scripts/test_crash_recovery.py --rounds 20 --json /tmp/pulpo-crash-results.json
python3 scripts/benchmark_unique_audit_scan.py --compare-ref ee88a8ea5aa5496c06afaa82ec31db30c2e4e1fc --json /tmp/pulpo-unique-results.json
```

The crash CLI requires Linux process signals. The oracle/unit tests and existing
persistence tests are separate; no native Windows crash-harness pass is claimed.
Database fixtures use native Linux temporary storage. For
`benchmark_sqlite_state.py`, put the output JSON on native Linux storage too:
that harness puts its database fixtures beside the output file. An initial
Windows-mounted SQLite benchmark was interrupted; only the completed native
Linux comparison is included as final benchmark evidence.

## Adversarial transformation review

Purpose: reduce unnecessary reconciliation-row allocation while preserving
canonical storage, authority, evidence, and durability boundaries.

- **Flip:** hostile repeats cannot hide a late duplicate or malformed payload;
  the complete event scan remains mandatory. Negative oracle controls reject
  partial state even when its remaining audit chain is internally valid.
- **Reverse:** issuance/consumption/append still share their existing transaction
  with evidence; failed insert/commit and interrupted-process cases must recover
  whole transitions, not partial replay guards or spent permits.
- **Invert:** a smaller allocation peak is not success if rejection semantics
  change. An unacknowledged commit is permissible uncertainty; acknowledged loss
  is an explicit failure. Timing alone is not classified as a speed gain.
- **Inside-Out:** the same canonical backend and verifier retain control. Test
  orchestration adds no policy, runtime authority, provider interface, or truth cache.
- **Darken:** later duplicates, malformed JSON, historical hash/payload edits,
  full-page limits, commit locks, and audit aborts must reject or recover safely.
- **Lighten:** benign replay returns original evidence without a new write;
  unknown provider consequence is not silently converted into success/failure.
- **Amplify:** indexed/unindexed storage concurrency, hostile memory concurrency,
  repeated checkpoints, and randomized process interruptions are tested. Scan
  duration and contention remain history-dependent.
- **Negate:** remove `fetchall()` rather than weaken durability, delay flushing,
  batch across governed calls, add a key/cache, or expose another writer.

Decision: submit this bounded change for review; continued native Windows and
practical power-loss validation remain explicit follow-up requirements.

Legacy source: existing canonical SQLite state backend and current-head full
verifier. No historical router, executor, ledger, or authority path was imported.
Exact backend comparison is not whole-system temporal replay. No general reusable
historical-transfer lesson is asserted; historical checkpoints inspected for
context were not validated as transfer targets for this optimization.
