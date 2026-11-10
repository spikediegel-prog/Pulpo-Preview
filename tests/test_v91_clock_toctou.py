"""v9.1 slice 2: clock TOCTOU fix and state integrity in SQLiteKernelState.

Report references: austin-v91-review-verification-2026-11-09.md section 4 (the
TOCTOU bug: the kernel samples the clock before the state call, so the expiry
checks inside the transaction run on a pre-lock timestamp) and section 6b(b)
(port custody's ``_custody_now`` regression check into ``SQLiteKernelState``;
sample time inside the transaction, after the lock).

What is proven here:
(a) a clock that regresses between the pre-lock sample and the post-lock
    sample fails closed (the regression check compares adjacent samples from
    the same clock -- see _sample_post_lock_timestamp for why the audit tip
    is not the comparison point);
(b) a permit that expires between the pre-lock sample and lock acquisition is
    refused, and the sample is proven to happen while the write lock is held;
(c) normal issue/consume still works, including the NULL-``expires_at_ns``
    ("no expiry") case, whose semantics are unchanged;
(d) the recovery-pin operator step works as documented (see
    tests/test_guarded_recovery.py and docs/RECOVERY_PIN_OPERATOR_STEP.md).
"""
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pulpo import (
    GovernanceKernel,
    Intent,
    Policy,
    InMemoryKernelState,
    SQLiteKernelState,
    StateClockError,
)


T0 = 1_700_000_000_000_000_000
SECOND_NS = 1_000_000_000


def _policy():
    return Policy(frozenset({"read"}), 100, frozenset())


def _intent():
    return Intent("agent:fixture", "read", "local:fixture", 0, "clock-test")


def _kernel(state, clock=None):
    return GovernanceKernel(
        _policy(), secret=b"v91-clock-toctou-test-secret", clock=clock, state=state
    )


class _ScriptedClock:
    """Return the scripted values in order; fail loudly when exhausted."""

    def __init__(self, values):
        self._values = list(values)
        self.calls = 0

    def __call__(self):
        value = self._values[self.calls]
        self.calls += 1
        return value


class _LockProbingClock(_ScriptedClock):
    """A scripted clock that also proves *when* each sample was taken.

    On odd calls (the kernel's pre-lock samples) the database write lock must
    be free; on even calls (the state's post-lock re-samples) it must be held.
    A probe connection with a zero busy timeout either takes BEGIN IMMEDIATE
    at once or fails at once, so the assertion is deterministic, not timing.
    If the sampling regressed to before the lock, an even call would find the
    lock free and this clock would fail the test.
    """

    def __init__(self, path, values):
        super().__init__(values)
        self._path = str(path)

    def _write_lock_held(self):
        connection = sqlite3.connect(self._path, timeout=0)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ROLLBACK")
            return False
        except sqlite3.OperationalError:
            return True
        finally:
            connection.close()

    def __call__(self):
        self.calls += 1
        locked = self._write_lock_held()
        if self.calls % 2 == 1:
            assert not locked, "pre-lock sample taken while a write lock was held"
        else:
            assert locked, "post-lock sample taken without the write lock held"
        return self._values[self.calls - 1]


class StateClockRegressionTests(unittest.TestCase):
    def _backends(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "state.sqlite3"
        sqlite_state = SQLiteKernelState(path)
        self.addCleanup(sqlite_state.close)
        return (("in-memory", InMemoryKernelState()), ("sqlite", sqlite_state))

    def test_out_of_order_append_preserved_for_legacy(self):
        # Deliberate scope: the generic append path stays permissive. Legacy
        # adoption preserves non-monotonic histories (the migration seed is
        # 100, 10, 10, -1 by design) and evidence fixtures append out-of-order
        # times, so a tip comparison cannot live on the append path. The
        # regression check applies only where a clock is supplied (issue /
        # consume), comparing adjacent samples from that one clock.
        for name, state in self._backends():
            with self.subTest(backend=name):
                for i, timestamp in enumerate((100, 10, 10, -1, 0)):
                    state.append("fixture", {"i": i}, timestamp)
                self.assertEqual(len(state.audit), 5)
                self.assertEqual(
                    [record["timestamp_ns"] for record in state.audit],
                    [100, 10, 10, -1, 0],
                )

    def test_clock_regressing_between_samples_fails_closed(self):
        # The post-lock sample predates the pre-lock sample: the clock went
        # backwards across the lock boundary. Fail closed, and (for consume)
        # without burning the permit.
        for name, state in self._backends():
            with self.subTest(backend=name):
                digest = "ab" * 32
                with self.assertRaises(StateClockError):
                    state.issue_permit(
                        "permit-2", digest, "ok", T0 + 100 * SECOND_NS,
                        clock=_ScriptedClock([T0 - 100 * SECOND_NS]),
                    )
                # Nothing was issued: the refused permit does not exist.
                self.assertFalse(state.consume_permit("permit-2", digest, T0 + 200 * SECOND_NS))
                self.assertIsNone(
                    state.issue_permit(
                        "permit-1", digest, "ok", T0,
                        expires_at_ns=T0 + 200 * SECOND_NS,
                        clock=_ScriptedClock([T0]),
                    )
                )
                with self.assertRaises(StateClockError):
                    state.consume_permit(
                        "permit-1", digest, T0 + 100 * SECOND_NS,
                        clock=_ScriptedClock([T0 - 100 * SECOND_NS]),
                    )
                self.assertTrue(state.consume_permit("permit-1", digest, T0 + SECOND_NS))
                self.assertFalse(state.consume_permit("permit-1", digest, T0 + 2 * SECOND_NS))


class ClockToctouTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"

    def _spent(self, permit):
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT spent FROM permits WHERE permit = ?", (permit,)
            ).fetchone()
        return row[0] if row else None

    def test_expired_between_sample_and_lock_is_refused(self):
        # The permit TTL is 300s. Issue anchors at T0 (calls 1-2). The consume
        # pre-lock sample (call 3) is T0+200s, still valid; the post-lock
        # re-sample (call 4) is T0+400s, past expiry. Old code would have
        # consumed on the pre-lock sample; the fix refuses on the post-lock one.
        state = SQLiteKernelState(self.path)
        self.addCleanup(state.close)
        clock = _LockProbingClock(
            self.path, [T0, T0, T0 + 200 * SECOND_NS, T0 + 400 * SECOND_NS]
        )
        kernel = _kernel(state, clock=clock)
        decision = kernel.evaluate(_intent())
        self.assertEqual(decision.outcome, "allow")
        self.assertFalse(kernel.consume(decision.permit, _intent()))
        self.assertEqual(clock.calls, 4)
        self.assertEqual(self._spent(decision.permit), 0)
        rejected = state.audit[-1]
        self.assertEqual(rejected["event"], "permit_rejected")
        # The rejection is stamped with the post-lock sample, not the pre-lock one.
        self.assertEqual(rejected["timestamp_ns"], T0 + 400 * SECOND_NS)

    def test_pre_lock_timestamp_alone_would_have_consumed(self):
        # Control for the test above: the same pre-lock timestamp, used on its
        # own without a post-lock re-sample, consumes the permit. This is the
        # old behaviour the fix closes.
        state = SQLiteKernelState(self.path)
        self.addCleanup(state.close)
        kernel = _kernel(state, clock=lambda: T0)
        decision = kernel.evaluate(_intent())
        digest = kernel.intent_hash(_intent())
        self.assertTrue(state.consume_permit(decision.permit, digest, T0 + 200 * SECOND_NS))
        self.assertEqual(self._spent(decision.permit), 1)

    def test_regressed_consume_refuses_without_burning_permit(self):
        state = SQLiteKernelState(self.path)
        self.addCleanup(state.close)
        clock = _ScriptedClock([T0, T0, T0 + 100 * SECOND_NS, T0 - 100 * SECOND_NS])
        kernel = _kernel(state, clock=clock)
        decision = kernel.evaluate(_intent())
        # The post-lock sample regressed below the audit tip: fail closed.
        self.assertFalse(kernel.consume(decision.permit, _intent()))
        self.assertEqual(self._spent(decision.permit), 0)
        # With the clock monotonic again, the same permit still consumes.
        good_clock = _ScriptedClock([T0 + 100 * SECOND_NS, T0 + 100 * SECOND_NS])
        retry = _kernel(state, clock=good_clock)
        self.assertTrue(retry.consume(decision.permit, _intent()))
        self.assertEqual(self._spent(decision.permit), 1)

    def test_clock_failing_midflight_fails_closed(self):
        state = SQLiteKernelState(self.path)
        self.addCleanup(state.close)

        def flaky():
            if flaky.calls == 0:
                flaky.calls += 1
                return T0
            raise RuntimeError("clock broke")

        flaky.calls = 0
        kernel = _kernel(state, clock=flaky)
        # The pre-lock sample succeeds; the post-lock re-sample raises.
        with self.assertRaisesRegex(RuntimeError, "permit_clock_invalid"):
            kernel.evaluate(_intent())
        self.assertEqual(state.audit, [])

        issued = _kernel(state, clock=lambda: T0).evaluate(_intent())
        self.assertEqual(issued.outcome, "allow")
        flaky.calls = 0
        failing = _kernel(state, clock=flaky)
        self.assertFalse(failing.consume(issued.permit, _intent()))
        self.assertEqual(self._spent(issued.permit), 0)
        self.assertEqual(state.audit[-1]["event"], "permit_rejected")
        self.assertEqual(state.audit[-1]["timestamp_ns"], 0)


class PermitExpiryAnchoringTests(unittest.TestCase):
    def test_expiry_reanchored_preserving_duration(self):
        # Kernel computes expires = pre-lock sample + TTL; the state anchors
        # the same lifetime at the post-lock sample instead.
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "state.sqlite3"
        state = SQLiteKernelState(path)
        self.addCleanup(state.close)
        clock = _ScriptedClock([T0 + 500 * SECOND_NS])
        digest = "cd" * 32
        self.assertIsNone(
            state.issue_permit(
                "permit-1", digest, "ok", T0, expires_at_ns=T0 + 300 * SECOND_NS, clock=clock
            )
        )
        with closing(sqlite3.connect(path)) as connection:
            row = connection.execute(
                "SELECT issued_at_ns, expires_at_ns FROM permits WHERE permit = 'permit-1'"
            ).fetchone()
        self.assertEqual(row, (T0 + 500 * SECOND_NS, T0 + 800 * SECOND_NS))

    def test_null_expiry_means_no_expiry_with_and_without_clock(self):
        # NULL expires_at_ns is load-bearing fork semantics ("no expiry") and
        # is unchanged by this slice: a permit issued with no expiry consumes
        # at any later time, including through the post-lock sampling path.
        for name, state in self._sqlite_and_memory():
            with self.subTest(backend=name):
                digest = "ef" * 32
                clock = _ScriptedClock([T0 + SECOND_NS])
                self.assertIsNone(
                    state.issue_permit(
                        "permit-1", digest, "ok", T0, expires_at_ns=None, clock=clock
                    )
                )
                far_future = T0 + 10**12
                self.assertTrue(
                    state.consume_permit("permit-1", digest, far_future, clock=lambda: far_future)
                )

    def _sqlite_and_memory(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "state.sqlite3"
        sqlite_state = SQLiteKernelState(path)
        self.addCleanup(sqlite_state.close)
        return (("in-memory", InMemoryKernelState()), ("sqlite", sqlite_state))


class NormalIssueConsumeTests(unittest.TestCase):
    def test_normal_issue_consume_still_works(self):
        for name, state in self._backends():
            with self.subTest(backend=name):
                kernel = _kernel(state, clock=lambda: T0)
                decision = kernel.evaluate(_intent())
                self.assertEqual(decision.outcome, "allow")
                self.assertTrue(kernel.consume(decision.permit, _intent()))
                self.assertFalse(kernel.consume(decision.permit, _intent()))
                self.assertTrue(kernel.verify_audit())

    def _backends(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "state.sqlite3"
        sqlite_state = SQLiteKernelState(path)
        self.addCleanup(sqlite_state.close)
        return (("in-memory", InMemoryKernelState()), ("sqlite", sqlite_state))


if __name__ == "__main__":
    unittest.main()
