from dataclasses import replace
import unittest

from pulpo import GovernanceKernel, Intent, Policy
from pulpo.orchestrator import PulpoOrchestrator, OrchestrationError
from pulpo.traffic import Lane, Path, TrafficControl, Backpressure


class IdleRoutingTests(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.intent = Intent('fixture', 'write', 'fixture:exact')
        self.kernel = GovernanceKernel(Policy(frozenset({'write'}), 0), secret=b'fixture')
        self.owner = PulpoOrchestrator(self.kernel)

    def traffic(self, ttl=None, limit=4, reserve=1):
        return TrafficControl((Lane('sql','sql',1,limit,foreground_reserve=reserve),
                              Lane('api','api',2,limit,foreground_reserve=reserve)),
                              (Path('fg','sql',self.intent), Path('bg','sql',self.intent,True),
                               Path('fg-api','api',self.intent), Path('bg-api','api',self.intent,True)),
                              clock=lambda:self.now[0],queue_ttl_seconds=ttl)

    def enqueue(self, traffic, path, decision=None):
        decision = decision or self.kernel.evaluate(self.intent)
        traffic.enqueue(self.intent, decision, (path,))
        return decision

    def test_foreground_overtakes_background_but_each_class_stays_fifo(self):
        traffic = self.traffic()
        decisions = [self.enqueue(traffic,p) for p in ('bg','fg','bg','fg')]
        before = list(self.kernel.audit)
        observed = []
        for _ in range(4):
            token,dispatch = traffic.acquire()
            observed.append(dispatch.work.permit)
            traffic.release(token)
        self.assertEqual(observed,[decisions[i].permit for i in (1,3,0,2)])
        self.assertEqual(before,list(self.kernel.audit))

    def test_active_foreground_blocks_background_timer_until_release(self):
        traffic = self.traffic()
        self.enqueue(traffic,'fg')
        token,_ = traffic.acquire()
        self.enqueue(traffic,'bg-api')
        self.assertIsNone(traffic.acquire())
        self.assertIsNone(traffic.ready_delay())
        traffic.release(token)
        self.assertEqual(0,traffic.ready_delay())
        background,_ = traffic.acquire()
        traffic.release(background)

    def test_paused_foreground_does_not_allow_background_to_jump_priority(self):
        traffic = self.traffic()
        self.enqueue(traffic,'fg')
        self.enqueue(traffic,'bg-api')
        traffic.pause('sql',10)
        self.assertIsNone(traffic.acquire())
        self.assertEqual(10,traffic.ready_delay())

    def test_background_is_not_preempted_and_new_foreground_uses_independent_slot(self):
        traffic = self.traffic()
        self.enqueue(traffic,'bg')
        token,_ = traffic.acquire()
        self.enqueue(traffic,'fg-api')
        fg,_ = traffic.acquire()
        self.assertEqual(1,traffic.snapshot()['sql']['active'])
        traffic.release(fg)
        traffic.release(token)

    def test_reordered_background_expiry_remains_timely_without_canonical_mutation(self):
        traffic = self.traffic(ttl=1)
        self.enqueue(traffic,'bg')
        self.now[0] = .5
        fg = self.enqueue(traffic,'fg')
        # Pause dispatch to expose the older background deadline behind foreground.
        traffic.pause('sql',10)
        self.assertEqual(.5,traffic.ready_delay())
        before = list(self.kernel.audit)
        self.now[0] = 1
        self.assertEqual({'queued':1,'active':0,'dropped':1},traffic.snapshot()['sql'])
        self.assertEqual(before,list(self.kernel.audit))
        self.assertEqual(fg.permit,traffic._head(traffic._queues['sql']).permit)

    def test_classification_is_strict_and_mixed_equivalent_paths_are_rejected(self):
        for value in (1,'background',None):
            with self.assertRaises(ValueError):
                Path('bad','sql',self.intent,value)
        traffic = self.traffic()
        with self.assertRaisesRegex(ValueError,'same background'):
            traffic.enqueue(self.intent,self.kernel.evaluate(self.intent),('fg','bg'))

    def test_background_still_requires_canonical_consumption_and_never_retries(self):
        traffic = self.traffic()
        forged = replace(self.kernel.evaluate(self.intent),permit='forged')
        self.enqueue(traffic,'bg',forged)
        with self.assertRaises(OrchestrationError):
            with self.owner.traffic_dispatch(traffic):
                self.fail('forged work reached execution')
        self.assertEqual(0,traffic.snapshot()['sql']['active'])
        self.assertIsNone(traffic.acquire())
        decision = self.enqueue(traffic,'bg')
        with self.assertRaises(RuntimeError):
            with self.owner.traffic_dispatch(traffic):
                raise RuntimeError('uncertain effect')
        self.assertFalse(self.kernel.consume(decision.permit,self.intent))
        self.assertIsNone(traffic.acquire())

    def test_background_and_foreground_share_capacity(self):
        traffic = self.traffic(limit=1,reserve=0)
        self.enqueue(traffic,'bg')
        with self.assertRaises(Backpressure):
            self.enqueue(traffic,'fg')
        self.assertEqual(1,traffic.snapshot()['sql']['queued'])

    def test_background_cannot_take_reserved_foreground_space(self):
        traffic = self.traffic(limit=3,reserve=2)
        self.enqueue(traffic,'bg')
        rejected = self.kernel.evaluate(self.intent)
        before = list(self.kernel.audit)
        with self.assertRaises(Backpressure):
            self.enqueue(traffic,'bg',rejected)
        self.assertEqual(before,list(self.kernel.audit))
        self.assertTrue(self.kernel.consume(rejected.permit,self.intent))
        self.enqueue(traffic,'fg')
        self.enqueue(traffic,'fg')
        with self.assertRaises(Backpressure):
            self.enqueue(traffic,'fg')
        self.assertEqual(3,traffic.snapshot()['sql']['queued'])

    def test_foreground_can_use_all_slots_and_occupied_reserve_is_not_wasted(self):
        traffic = self.traffic(limit=3)
        self.enqueue(traffic,'fg')
        self.enqueue(traffic,'bg')
        self.enqueue(traffic,'bg')
        self.assertEqual(3,traffic.snapshot()['sql']['queued'])
        other = self.traffic(limit=3)
        for _ in range(3):
            self.enqueue(other,'fg')
        self.assertEqual(3,other.snapshot()['sql']['queued'])

    def test_background_uses_equivalent_lane_with_unreserved_capacity(self):
        traffic = self.traffic(limit=2)
        self.enqueue(traffic,'bg')
        traffic.enqueue(self.intent,self.kernel.evaluate(self.intent),('bg','bg-api'))
        self.assertEqual(1,traffic.snapshot()['api']['queued'])
        self.enqueue(traffic,'fg')
        self.enqueue(traffic,'fg-api')
        self.assertEqual(2,traffic.snapshot()['sql']['queued'])
        self.assertEqual(2,traffic.snapshot()['api']['queued'])

    def test_expiry_reclaims_background_capacity_with_reserve(self):
        traffic = self.traffic(ttl=1,limit=2)
        self.enqueue(traffic,'bg')
        self.now[0] = 1
        self.enqueue(traffic,'bg')
        self.enqueue(traffic,'fg')
        self.assertEqual({'queued':2,'active':0,'dropped':1},traffic.snapshot()['sql'])

    def test_reserve_validation_and_default_single_slot_protection(self):
        for value in (True,1.5,-1,3,None):
            with self.assertRaises(ValueError):
                Lane('sql','sql',queue_limit=2,foreground_reserve=value)
        traffic = self.traffic(limit=1)
        with self.assertRaises(Backpressure):
            self.enqueue(traffic,'bg')
        self.enqueue(traffic,'fg')

    def test_background_only_lane_keeps_its_full_capacity(self):
        traffic = TrafficControl((Lane('sql','sql',queue_limit=1),),
                                 (Path('bg','sql',self.intent,True),))
        self.enqueue(traffic,'bg')
        self.assertEqual(1,traffic.snapshot()['sql']['queued'])

    def test_sql_api_profile_forwards_per_lane_reserves(self):
        traffic = TrafficControl.for_sql_api(
            (Path('fg','sql',self.intent),Path('bg','sql',self.intent,True),
             Path('fg-api','api',self.intent),Path('bg-api','api',self.intent,True)),
            sql_queue_limit=2,api_queue_limit=2,
            sql_foreground_reserve=2,api_foreground_reserve=0)
        with self.assertRaises(Backpressure):
            self.enqueue(traffic,'bg')
        self.enqueue(traffic,'bg-api')
        self.enqueue(traffic,'bg-api')
        self.enqueue(traffic,'fg')
        self.assertEqual(2,traffic.snapshot()['api']['queued'])

    def test_concurrent_background_admission_preserves_foreground_slot(self):
        from concurrent.futures import ThreadPoolExecutor
        traffic = self.traffic(limit=4)
        decision = self.kernel.evaluate(self.intent)
        def admit(_):
            try:
                traffic.enqueue(self.intent,decision,('bg',))
                return True
            except Backpressure:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(3,sum(pool.map(admit,range(20))))
        self.enqueue(traffic,'fg')
        self.assertEqual(4,traffic.snapshot()['sql']['queued'])

    def test_failed_disposable_batch_rolls_back_without_receipt_or_retry(self):
        import sqlite3
        from contextlib import closing

        traffic = self.traffic()
        decision = self.enqueue(traffic,'bg')
        receipts = []
        with closing(sqlite3.connect(':memory:')) as db:
            db.executescript("CREATE TABLE derived(value INTEGER); CREATE TRIGGER reject_second "
                             "BEFORE INSERT ON derived WHEN NEW.value=2 "
                             "BEGIN SELECT RAISE(ABORT,'injected failure'); END;")
            with self.assertRaises(sqlite3.IntegrityError):
                with self.owner.traffic_dispatch(traffic):
                    with db:
                        db.executemany('INSERT INTO derived VALUES (?)',[(1,),(2,)])
                    receipts.append('committed')
            self.assertEqual(0,db.execute('SELECT COUNT(*) FROM derived').fetchone()[0])
        self.assertEqual([],receipts)
        self.assertFalse(self.kernel.consume(decision.permit,self.intent))
        self.assertIsNone(traffic.acquire())
        self.assertEqual(0,traffic.snapshot()['sql']['active'])
        self.assertTrue(self.kernel.verify_audit())


if __name__ == '__main__':
    unittest.main()
