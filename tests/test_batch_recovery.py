import unittest
from scripts.test_batch_recovery import run_case


class BatchRecoveryTests(unittest.TestCase):
    def test_kill_before_dispatch(self):
        run_case("queued")

    def test_kill_after_permit_before_write(self):
        run_case("before_write")

    def test_kill_during_open_transaction(self):
        run_case("mid_transaction")

    def test_kill_racing_commit(self):
        run_case("commit_race")

    def test_kill_after_commit_before_receipt(self):
        run_case("after_commit")

    def test_kill_after_receipt(self):
        run_case("after_receipt")
