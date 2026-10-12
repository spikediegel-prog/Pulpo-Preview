from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pulpo import AuditVerificationEngine, ResourceScope, SQLiteKernelState
from pulpo.custody import SQLiteGovernanceCustody
from pulpo.performance_tuning import AdaptiveAuditVerificationEngine


class ResourceLifecycleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "fixture.sqlite"

    def test_state_scope_rolls_back_pending_work_and_close_is_repeatable(self):
        with SQLiteKernelState(self.path) as state:
            state._connection.execute("CREATE TABLE disposable(value INTEGER)")
            state._connection.execute("INSERT INTO disposable VALUES (1)")
        state.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            state.__enter__()
        with SQLiteKernelState(self.path) as restarted:
            self.assertEqual(0, restarted._connection.execute(
                "SELECT COUNT(*) FROM disposable").fetchone()[0])

    def test_operation_error_closes_state_without_suppressing_error(self):
        with self.assertRaisesRegex(RuntimeError, "operation failed"):
            with SQLiteKernelState(self.path) as state:
                raise RuntimeError("operation failed")
        with self.assertRaises(sqlite3.ProgrammingError):
            state._connection.execute("SELECT 1")

    def test_reverse_order_attempts_all_cleanup_and_propagates_failure(self):
        events = []
        class Resource:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail
            def close(self):
                events.append(self.name)
                if self.fail:
                    raise RuntimeError("close failed")
        scope = ResourceScope()
        with self.assertRaisesRegex(RuntimeError, "close failed"):
            with scope:
                first = scope.own(Resource("state"))
                scope.own(first)
                scope.own(Resource("worker", fail=True))
        self.assertEqual(["worker", "state"], events)
        scope.close()
        self.assertEqual(["worker", "state"], events)
        with self.assertRaises(RuntimeError):
            scope.own(first)

    def test_scope_shuts_down_workers_and_closes_database_after_error(self):
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with ResourceScope() as resources:
                state = resources.own(SQLiteKernelState(self.path))
                workers = resources.own(ThreadPoolResource())
                self.assertEqual(42, workers.pool.submit(lambda: 42).result())
                raise RuntimeError("stop")
        with self.assertRaises(RuntimeError):
            workers.pool.submit(lambda: 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            state._connection.execute("SELECT 1")

    def test_partial_state_and_custody_setup_close_the_new_connection(self):
        original = sqlite3.connect
        captured = []
        class FailingConnection(sqlite3.Connection):
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("setup failed")
        def connect(*args, **kwargs):
            connection = original(*args, **kwargs, factory=FailingConnection)
            captured.append(connection)
            return connection
        with patch("sqlite3.connect", connect):
            with self.assertRaisesRegex(sqlite3.OperationalError, "setup failed"):
                SQLiteKernelState(self.path)
            with self.assertRaisesRegex(sqlite3.OperationalError, "setup failed"):
                SQLiteGovernanceCustody(self.path, signing_secret=b"fixture")
        self.assertEqual(2, len(captured))
        for connection in captured:
            with self.assertRaises(sqlite3.ProgrammingError):
                sqlite3.Connection.execute(connection, "SELECT 1")

    def test_later_initialization_failure_closes_already_owned_state(self):
        with self.assertRaisesRegex(ValueError, "new resource failed"):
            with ResourceScope() as resources:
                state = resources.own(SQLiteKernelState(self.path))
                raise ValueError("new resource failed")
        with self.assertRaises(sqlite3.ProgrammingError):
            state._connection.execute("SELECT 1")

    def test_interrupt_closes_owned_state_without_suppressing_interrupt(self):
        with self.assertRaises(KeyboardInterrupt):
            with ResourceScope() as resources:
                state = resources.own(SQLiteKernelState(self.path))
                raise KeyboardInterrupt()
        with self.assertRaises(sqlite3.ProgrammingError):
            state._connection.execute("SELECT 1")

    def test_adaptive_engine_attempts_other_closes_after_failure(self):
        events = []
        class Engine:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail
            def close(self):
                events.append(self.name)
                if self.fail:
                    raise RuntimeError("shutdown failed")
        adaptive = AdaptiveAuditVerificationEngine(None)
        adaptive._engines = {"first": Engine("first"), "last": Engine("last", True)}
        with self.assertRaisesRegex(RuntimeError, "shutdown failed"):
            adaptive.close()
        self.assertEqual(["last", "first"], events)
        self.assertEqual({}, adaptive._engines)
        adaptive.close()

    def test_verification_cache_clears_even_when_worker_shutdown_fails(self):
        class FailingPool:
            def shutdown(self, **kwargs):
                raise RuntimeError("pool shutdown failed")
        engine = AuditVerificationEngine()
        engine.cache.put(("event", "{}", "0" * 64, 1), "a" * 64)
        engine._executor = FailingPool()
        with self.assertRaisesRegex(RuntimeError, "pool shutdown failed"):
            engine.close()
        self.assertEqual(0, len(engine.cache))

    def test_scope_retains_resources_even_when_close_is_not_a_bound_method(self):
        import gc
        import weakref
        events = []
        class Resource:
            close = staticmethod(lambda: events.append("closed"))
        scope = ResourceScope()
        resource = Resource()
        reference = weakref.ref(resource)
        scope.own(resource)
        del resource
        gc.collect()
        self.assertIsNotNone(reference())
        scope.close()
        gc.collect()
        self.assertIsNone(reference())
        self.assertEqual(["closed"], events)


class ThreadPoolResource:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=2)
    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
