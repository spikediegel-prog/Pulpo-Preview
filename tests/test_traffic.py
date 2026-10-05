from dataclasses import replace
from pathlib import Path as FilePath
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from pulpo import GovernanceKernel, Intent, Policy
from pulpo.directives import DirectiveAuthorityController, GovernedDirectiveProjection
from pulpo.orchestrator import OrchestrationError, PulpoOrchestrator
from pulpo.state import InMemoryKernelState, SQLiteKernelState
from pulpo.traffic import Backpressure, Lane, Path, TrafficControl
from tests.authority_support import HmacTestVerifier, signed_envelope, trust_for
from tests.test_directives import directive


class TrafficTests(unittest.TestCase):
    def setUp(self):
        self.now = [2_000_000]
        self.intent = Intent("agent:builder", "write", "repo:sql", 1)
        self.api = replace(self.intent, resource="repo:api:provider-a")
        self.kernel = GovernanceKernel(Policy(frozenset({"write"}), 10),
                                       clock=lambda: self.now[0], secret=b"fixture")
        self.owner = PulpoOrchestrator(self.kernel)
        self.traffic = self.make_traffic()

    def make_traffic(self, limit=2):
        return TrafficControl.for_sql_api(
            (Path("sql-a", "sql", self.intent), Path("sql-b", "api", self.intent),
             Path("provider-a", "api", self.api)), sql_queue_limit=limit,
            api_queue_limit=limit, clock=lambda: self.now[0] / 1e9)

    def enqueue(self, intent=None, paths=("sql-a",), decision=None):
        intent = intent or self.intent
        decision = decision or self.kernel.evaluate(intent)
        self.traffic.enqueue(intent, decision, paths)
        return decision

    def test_unauthorized_and_forged_work_never_reaches_effect(self):
        denied = self.kernel.evaluate(replace(self.intent, action="delete"))
        with self.assertRaises(ValueError):
            self.enqueue(decision=denied)
        forged = replace(self.kernel.evaluate(self.intent), permit="invented")
        self.enqueue(decision=forged)
        calls = []
        with self.assertRaisesRegex(OrchestrationError, "permit_rejected"):
            with self.owner.traffic_dispatch(self.traffic):
                calls.append("effect")
        self.assertEqual([], calls)
        self.assertEqual(0, self.traffic.snapshot()["sql"]["active"])

    def test_forged_intent_hash_cannot_substitute_target(self):
        allowed = self.kernel.evaluate(self.intent)
        substituted = replace(allowed, intent_hash=self.kernel.intent_hash(self.api))
        self.enqueue(self.api, ("provider-a",), substituted)
        with self.assertRaises(OrchestrationError):
            with self.owner.traffic_dispatch(self.traffic):
                self.fail("substituted target executed")

    def test_admission_and_congestion_do_not_substitute_targets(self):
        with self.assertRaisesRegex(ValueError, "target mismatch"):
            self.enqueue(paths=("provider-a",))
        self.enqueue()
        with self.owner.traffic_dispatch(self.traffic):
            self.enqueue()
            with self.owner.traffic_dispatch(self.traffic) as blocked:
                self.assertIsNone(blocked)
            self.assertEqual(1, self.traffic.snapshot()["sql"]["queued"])
            self.assertEqual(0, self.traffic.snapshot()["api"]["active"])

    def test_routing_only_among_exact_equivalent_registered_paths(self):
        self.enqueue()
        with self.owner.traffic_dispatch(self.traffic):
            decision = self.enqueue(paths=("sql-a", "sql-b"))
            with self.owner.traffic_dispatch(self.traffic) as routed:
                self.assertEqual("sql-b", routed.path.name)
                self.assertEqual(self.intent, routed.path.intent)
                self.assertEqual(decision.permit, routed.work.permit)

    def test_one_use_across_paths_and_no_retry_after_effect_failure(self):
        decision = self.enqueue(paths=("sql-a", "sql-b"))
        with self.assertRaisesRegex(RuntimeError, "lost response"):
            with self.owner.traffic_dispatch(self.traffic):
                raise RuntimeError("lost response")
        self.enqueue(paths=("sql-b",), decision=decision)
        with self.assertRaises(OrchestrationError):
            with self.owner.traffic_dispatch(self.traffic):
                self.fail("replayed effect")
        self.assertEqual(0, sum(v["active"] for v in self.traffic.snapshot().values()))

    def test_backpressure_does_not_spend_rejected_permit(self):
        self.traffic = self.make_traffic(limit=1)
        self.enqueue()
        rejected = self.kernel.evaluate(self.intent)
        audit_before = list(self.kernel.audit)
        with self.assertRaises(Backpressure):
            self.enqueue(decision=rejected)
        self.assertEqual(audit_before, self.kernel.audit)
        self.assertTrue(self.kernel.consume(rejected.permit, self.intent))

    def test_api_concurrency_is_bounded_and_sql_is_independent(self):
        for _ in range(2):
            self.enqueue(self.api, ("provider-a",))
        with self.owner.traffic_dispatch(self.traffic):
            with self.owner.traffic_dispatch(self.traffic):
                self.enqueue(self.api, ("provider-a",))
                with self.owner.traffic_dispatch(self.traffic) as blocked:
                    self.assertIsNone(blocked)
                self.enqueue()
                with self.owner.traffic_dispatch(self.traffic) as sql:
                    self.assertEqual("sql", sql.path.lane)
                    self.assertEqual(2, self.traffic.snapshot()["api"]["active"])

    def test_lane_rotation_prevents_starvation(self):
        self.enqueue()
        self.enqueue(self.api, ("provider-a",))
        with self.owner.traffic_dispatch(self.traffic) as first:
            self.assertEqual("sql", first.path.lane)
        self.enqueue()
        with self.owner.traffic_dispatch(self.traffic) as second:
            self.assertEqual("api", second.path.lane)

    def test_cooldown_delays_without_consuming_or_renewing(self):
        decision = self.enqueue()
        self.traffic.pause("sql", 1)
        audit_before = list(self.kernel.audit)
        with self.owner.traffic_dispatch(self.traffic) as blocked:
            self.assertIsNone(blocked)
        self.assertEqual(audit_before, self.kernel.audit)
        self.now[0] += 1_000_000_000
        with self.owner.traffic_dispatch(self.traffic) as work:
            self.assertEqual(decision.permit, work.work.permit)

    def test_invalid_configuration_and_release_fail_closed(self):
        for value in (0, -1, True, 1025, 1.5):
            with self.assertRaises(ValueError):
                Lane("sql", "sql", value)
        with self.assertRaises(ValueError):
            self.traffic.release(999)
        with self.assertRaises(ValueError):
            self.traffic.pause("sql", float("nan"))
        with self.assertRaises(ValueError):
            self.enqueue(paths=("unknown",))

    def governed(self, state):
        verifier = HmacTestVerifier()
        kernel = GovernanceKernel(Policy(
            frozenset({"write", "activate_directive", "revoke_directive"}), 100,
            frozenset({"activate_directive", "revoke_directive"}),
            authority_trust=trust_for(verifier)), secret=b"fixture",
            approval_verifier=verifier, clock=lambda: self.now[0], state=state)
        return kernel, verifier

    def activate(self, state):
        kernel, verifier = self.governed(state)
        controller = DirectiveAuthorityController(kernel)
        d = directive()
        operation = controller.authority_intent(controller.ACTIVATE, d,
                                                operator_principal="operator:owner")
        approval = signed_envelope(kernel, operation, verifier, now_ns=self.now[0])
        self.assertEqual("allow", controller.activate(
            d, approval, operator_principal="operator:owner").outcome)
        return kernel, verifier, controller, d

    def test_queued_expiry_and_revocation_checked_by_canonical_state(self):
        for persistent in (False, True):
            for mode in ("expiry", "revocation"):
                with self.subTest(persistent=persistent, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    self.now[0] = 2_000_000
                    state = SQLiteKernelState(FilePath(tmp) / "state.db") if persistent else InMemoryKernelState()
                    try:
                        kernel, verifier, controller, d = self.activate(state)
                        traffic = self.make_traffic()
                        decision = GovernedDirectiveProjection(kernel).evaluate(self.intent, d)
                        traffic.enqueue(self.intent, decision, ("sql-a", "sql-b"))
                        traffic.pause("sql", 0.0001)
                        traffic.pause("api", 0.0001)
                        if mode == "expiry":
                            self.now[0] = d.expires_at_ns
                        else:
                            operation = controller.authority_intent(controller.REVOKE, d,
                                                                    operator_principal="operator:owner")
                            approval = signed_envelope(kernel, operation, verifier,
                                now_ns=self.now[0], approval_id="revoke", nonce="revoke")
                            self.assertEqual("allow", controller.revoke(
                                d, approval, operator_principal="operator:owner").outcome)
                        self.now[0] += 100_000
                        if mode == "revocation":
                            self.assertLess(self.now[0], d.expires_at_ns)
                        if persistent:
                            state.close()
                            state = SQLiteKernelState(FilePath(tmp) / "state.db")
                            kernel, _ = self.governed(state)
                        with self.assertRaises(OrchestrationError):
                            with PulpoOrchestrator(kernel).traffic_dispatch(traffic):
                                self.fail("expired/revoked work executed")
                        rejected = [r for r in kernel.audit if r["event"] == "permit_rejected"][-1]
                        self.assertEqual("directive_inactive" if mode == "expiry" else "directive_revoked",
                                         rejected["payload"]["directive_status"])
                        self.assertTrue(kernel.verify_audit())
                        self.assertEqual(0, sum(v["active"] for v in traffic.snapshot().values()))
                    finally:
                        if persistent:
                            state.close()

    def test_persistent_replay_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = SQLiteKernelState(FilePath(tmp) / "state.db")
            kernel = GovernanceKernel(self.kernel.policy, secret=b"fixture", state=state)
            decision = kernel.evaluate(self.intent)
            self.traffic.enqueue(self.intent, decision, ("sql-a",))
            with PulpoOrchestrator(kernel).traffic_dispatch(self.traffic):
                pass
            state.close()
            state = SQLiteKernelState(FilePath(tmp) / "state.db")
            try:
                kernel = GovernanceKernel(self.kernel.policy, secret=b"fixture", state=state)
                self.traffic.enqueue(self.intent, decision, ("sql-b",))
                with self.assertRaises(OrchestrationError):
                    with PulpoOrchestrator(kernel).traffic_dispatch(self.traffic):
                        self.fail("restart replay executed")
            finally:
                state.close()

    def test_simultaneous_admission_respects_queue_bound(self):
        self.traffic = self.make_traffic(limit=2)
        decision = self.kernel.evaluate(self.intent)
        def submit(_):
            try:
                self.traffic.enqueue(self.intent, decision, ("sql-a",))
                return True
            except Backpressure:
                return False
        with ThreadPoolExecutor(max_workers=8) as workers:
            accepted = list(workers.map(submit, range(64)))
        self.assertEqual(2, sum(accepted))
        self.assertEqual(2, self.traffic.snapshot()["sql"]["queued"])

    def test_sql_pacing_does_not_block_api_or_spend_waiting_permit(self):
        traffic = TrafficControl((Lane("sql", "sql", 1, 2, 0.1), Lane("api", "api", 2, 2)),
            (Path("sql", "sql", self.intent), Path("api", "api", self.api)),
            clock=lambda: self.now[0] / 1e9)
        for _ in range(2):
            traffic.enqueue(self.intent, self.kernel.evaluate(self.intent), ("sql",))
        with self.owner.traffic_dispatch(traffic):
            self.assertIsNone(traffic.ready_delay())
        before = list(self.kernel.audit)
        with self.owner.traffic_dispatch(traffic) as waiting:
            self.assertIsNone(waiting)
        self.assertEqual(before, self.kernel.audit)
        self.assertAlmostEqual(0.1, traffic.ready_delay())
        traffic.enqueue(self.api, self.kernel.evaluate(self.api), ("api",))
        with self.owner.traffic_dispatch(traffic) as api:
            self.assertEqual("api", api.path.lane)
        self.now[0] += 101_000_000
        with self.owner.traffic_dispatch(traffic) as sql:
            self.assertEqual("sql", sql.path.lane)
        self.assertIsNone(traffic.ready_delay())

    def test_pacing_expiry_still_rejects_at_canonical_gate(self):
        kernel, _, _, d = self.activate(InMemoryKernelState())
        traffic = TrafficControl((Lane("sql", "sql", 1, 2, 0.1),),
            (Path("sql", "sql", self.intent),), clock=lambda: self.now[0] / 1e9)
        for _ in range(2):
            decision = GovernedDirectiveProjection(kernel).evaluate(self.intent, d)
            traffic.enqueue(self.intent, decision, ("sql",))
        owner = PulpoOrchestrator(kernel)
        with owner.traffic_dispatch(traffic):
            pass
        with owner.traffic_dispatch(traffic) as blocked:
            self.assertIsNone(blocked)
        self.now[0] += 101_000_000
        self.assertGreater(self.now[0], d.expires_at_ns)
        with self.assertRaises(OrchestrationError):
            with owner.traffic_dispatch(traffic):
                self.fail("pacing extended authority")

    def test_pacing_settings_reject_invalid_or_unbounded_intervals(self):
        for interval in (-1, 1.01, True, float("nan"), float("inf"), "0.1"):
            with self.assertRaises(ValueError):
                Lane("sql", "sql", min_dispatch_interval=interval)

    def test_simultaneous_sqlite_replay_executes_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = SQLiteKernelState(FilePath(tmp) / "state.db")
            try:
                kernel = GovernanceKernel(self.kernel.policy, secret=b"fixture", state=state)
                traffic = TrafficControl((Lane("sql", "sql", 8, 16),),
                                         (Path("sql", "sql", self.intent),))
                decision = kernel.evaluate(self.intent)
                for _ in range(16):
                    traffic.enqueue(self.intent, decision, ("sql",))
                def dispatch(_):
                    # SQLite's canonical connection is thread-affine. Each
                    # owner uses its own connection to the same canonical DB.
                    local_state = SQLiteKernelState(FilePath(tmp) / "state.db")
                    try:
                        local_kernel = GovernanceKernel(self.kernel.policy,
                            secret=b"fixture", state=local_state)
                        with PulpoOrchestrator(local_kernel).traffic_dispatch(traffic) as work:
                            return work is not None
                    except OrchestrationError:
                        return False
                    finally:
                        local_state.close()
                with ThreadPoolExecutor(max_workers=8) as workers:
                    results = list(workers.map(dispatch, range(16)))
                self.assertEqual(1, sum(results))
                self.assertTrue(kernel.verify_audit())
                self.assertEqual(0, traffic.snapshot()["sql"]["active"])
            finally:
                state.close()
