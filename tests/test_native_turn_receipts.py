"""Separate native readonly execution completion from host-resource closure."""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import unittest

import test_runtime as initial
from test_runtime import spec, reply
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime.cli import parser


class NativeTurnReceiptTests(unittest.TestCase):
    setUp=initial.RuntimeTests.setUp
    tearDown=initial.RuntimeTests.tearDown
    add=initial.RuntimeTests.add
    acquire=initial.RuntimeTests.acquire
    done=initial.RuntimeTests.done

    def receipt(self, packet, external, **extra):
        if not hasattr(self,'observation_times'):self.observation_times={}
        observed=self.observation_times.setdefault(packet['attempt'],datetime.now(timezone.utc).isoformat())
        data=dict(attempt=packet['attempt'],external_id=external,status='completed',
                  observed_via='collaboration.list_agents',observed_at=observed,tools_settled=True)
        data.update(extra)
        return data

    def reconcile(self, packet, external, receipt=None):
        return self.rt.release(packet['attempt'],external_id=external,confirmed=True,
            reason='synthetic host observation in deterministic test',kind='readonly-turn-completed',
            receipt=self.receipt(packet,external) if receipt is None else receipt)

    def test_readonly_finish_preserves_unknown_host_resources_and_reopens(self):
        self.add(spec());p,e,_=self.done(release=False)
        with self.assertRaisesRegex(WorkflowError,'unreconciled'):self.rt.finish(self.run)
        self.reconcile(p,e);status=self.rt.finish(self.run)
        self.assertEqual(status['status'],'completed')
        self.assertEqual(status['budget']['execution_holds'],0)
        self.assertEqual(status['budget']['host_resource_holds'],1)
        self.assertEqual(status['budget']['active_holds'],1)
        self.assertFalse(status['attempts'][0]['released'])
        self.assertEqual(status['host_resource_state'],'UNKNOWN')
        with Runtime(self.db,read_only=True) as rt:
            self.assertEqual(rt.status(self.run),status)

    def test_completion_text_is_not_a_host_observation(self):
        self.add(spec());p,e,_=self.done(result=reply(summary='Agent says completed and closed.'),release=False)
        with self.assertRaises(WorkflowError):self.reconcile(p,e,self.receipt(p,e,observed_via='agent-result'))
        self.assertEqual(self.rt.status(self.run)['budget']['execution_holds'],1)

    def test_host_times_compare_at_receipt_microsecond_precision(self):
        self.add(spec());p,e,_=self.done(release=False)
        # Same Windows clock tick: datetime truncates fractions that time.time retains.
        ended = 1788681600.1234567
        self.rt.conn.execute('UPDATE attempts SET ended=? WHERE token=?',(ended,p['attempt']))
        with patch('cwf_runtime.core.time.time',return_value=ended):
            for stamp in ('2026-09-06T08:00:00.123455Z','2026-09-06T08:00:00.123457Z'):
                with self.subTest(stamp=stamp), self.assertRaisesRegex(WorkflowError,'host observation'):
                    self.reconcile(p,e,self.receipt(p,e,observed_at=stamp))
            result=self.reconcile(p,e,self.receipt(p,e,observed_at='2026-09-06T08:00:00.123456Z'))
        self.assertTrue(result['execution_reconciled'])
        self.assertFalse(result['host_resources_released'])

    def test_float_rounding_across_microsecond_boundary_is_not_stale(self):
        cases = [
            (1788683572.478112,'2026-09-06T08:32:52.478111Z','2026-09-06T08:32:52.478110Z','2026-09-06T08:32:52.478113Z'),
            (1788681600.000001,'2026-09-06T08:00:00.000000Z','2026-09-06T07:59:59.999999Z','2026-09-06T08:00:00.000002Z'),
        ]
        for ended,stamp,stale,future in cases:
            with self.subTest(ended=ended):
                self.run=self.rt.create(root=self.root,goal='clock boundary',backend='native')
                self.add(spec());p,e,_=self.done(release=False)
                self.rt.conn.execute('UPDATE attempts SET ended=? WHERE token=?',(ended,p['attempt']))
                with patch('cwf_runtime.core.time.time',return_value=ended):
                    for bad in (stale,future):
                        with self.assertRaisesRegex(WorkflowError,'host observation'):
                            self.reconcile(p,e,self.receipt(p,e,observed_at=bad))
                    result=self.reconcile(p,e,self.receipt(p,e,observed_at=stamp))
                self.assertTrue(result['execution_reconciled'])
                self.assertFalse(result['host_resources_released'])

    def test_unbound_or_running_attempt_cannot_reconcile(self):
        self.add(spec());p=self.acquire()
        with self.assertRaises(WorkflowError):self.reconcile(p,None)
        self.rt.bind(p['attempt'],'running-child',backend='native')
        with self.assertRaises(WorkflowError):self.reconcile(p,'running-child')
        self.assertFalse(self.rt.attempt(p['attempt'])['released'])

    def test_failed_partial_interrupted_results_cannot_reconcile(self):
        for state in ('failed','partial','interrupted'):
            with self.subTest(state=state):
                self.run=self.rt.create(root=self.root,goal=state,backend='native')
                self.add(spec())
                if state=='interrupted':
                    p=self.acquire();e='stopped-child';self.rt.bind(p['attempt'],e,backend='native')
                    self.rt.release(p['attempt'],external_id=e,confirmed=True,reason='actual stop test path')
                else:
                    p,e,_=self.done(result=reply(outcome=state,checks=[]),release=False)
                with self.assertRaises(WorkflowError):self.reconcile(p,e)
                self.assertEqual(self.rt.status(self.run)['budget']['execution_holds'],0 if state=='interrupted' else 1)

    def test_writer_cannot_use_readonly_receipt(self):
        self.run=self.rt.create(root=self.root,goal='writer guard',backend='native',implement=True)
        self.add(spec('w',role='writer',writes=['a.py']),spec('v',role='reviewer',verifies='w',depends=['w']))
        p,e,_=self.done(release=False)
        with self.assertRaises(WorkflowError):self.reconcile(p,e)
        self.assertEqual(self.rt.status(self.run)['budget']['execution_holds'],1)

    def test_exec_cannot_use_native_turn_receipt(self):
        self.run=self.rt.create(root=self.root,goal='exec guard',backend='exec')
        self.add(spec());p=self.rt.acquire(self.run,backend='exec');e='process-1'
        self.rt.bind(p['attempt'],e,backend='exec')
        self.rt.complete(p['attempt'],reply(),external_id=e,backend='exec')
        with self.assertRaises(WorkflowError):self.reconcile(p,e)

    def test_malformed_or_mismatched_receipt_has_no_effect(self):
        self.add(spec());p,e,_=self.done(release=False)
        for bad in (None,{},[],self.receipt(p,e,attempt='old-token'),self.receipt(p,e,external_id='other'),
                    self.receipt(p,e,status='running'),self.receipt(p,e,tools_settled=False),self.receipt(p,e,tools_settled=1)):
            with self.subTest(bad=bad),self.assertRaises(WorkflowError):
                self.rt.release(p['attempt'],external_id=e,confirmed=True,reason='test',kind='readonly-turn-completed',receipt=bad)
        self.assertEqual(self.rt.status(self.run)['budget']['execution_holds'],1)

    def test_drift_before_receipt_blocks_execution_release(self):
        self.add(spec());p,e,_=self.done(release=False);(self.root/'a.py').write_text('changed\n')
        with self.assertRaisesRegex(WorkflowError,'candidate drift'):self.reconcile(p,e)

    def test_receipt_is_idempotent_but_conflicts_are_rejected(self):
        self.add(spec());p,e,_=self.done(release=False)
        self.assertFalse(self.reconcile(p,e)['idempotent']);before=len(self.rt.events(self.run))
        self.assertTrue(self.reconcile(p,e)['idempotent']);self.assertEqual(len(self.rt.events(self.run)),before)
        with self.assertRaisesRegex(WorkflowError,'conflicting'):
            self.reconcile(p,e,self.receipt(p,e,observed_at=datetime.now(timezone.utc).isoformat()))
        self.rt.release(p['attempt'],external_id=e,confirmed=True,reason='later real resource closure')
        status=self.rt.status(self.run)
        self.assertEqual(status['budget']['host_resource_holds'],0)
        self.assertEqual(status['host_resource_state'],'RELEASE_CONFIRMED')
        self.assertEqual(status['budget']['used'],1)

    def test_explicit_resource_capacity_still_blocks_retained_session(self):
        self.run=self.rt.create(root=self.root,goal='capacity',backend='native',bounds={'capacity':1})
        self.add(spec('a'),spec('b'));p,e,_=self.done(release=False);self.reconcile(p,e)
        self.assertFalse(self.acquire()['admitted'])
        self.rt.release(p['attempt'],external_id=e,confirmed=True,reason='real host closure')
        self.assertTrue(self.acquire()['admitted'])

    def test_settled_readonly_does_not_block_subsequent_writer(self):
        self.run=self.rt.create(root=self.root,goal='read then write',backend='native',implement=True)
        self.add(spec('read'),spec('write',role='writer',writes=['a.py'],depends=['read']),
                 spec('verify',role='reviewer',verifies='write',depends=['write']))
        p,e,_=self.done(release=False)
        self.assertFalse(self.acquire()['admitted'])
        self.reconcile(p,e);self.assertEqual(self.acquire()['node_id'],'write')

    def test_same_child_cannot_supply_independent_verification(self):
        self.add(spec('target',risk='high'),spec('check',role='verifier',verifies='target',depends=['target']))
        for _ in range(2):
            p=self.acquire();e='same-child';self.rt.bind(p['attempt'],e,backend='native')
            self.rt.complete(p['attempt'],reply(),external_id=e,backend='native');self.reconcile(p,e)
        with self.assertRaisesRegex(WorkflowError,'independent'):self.rt.finish(self.run)

    def test_event_failure_does_not_release_execution(self):
        self.add(spec());p,e,_=self.done(release=False)
        with patch.object(self.rt,'event',side_effect=RuntimeError('event write failure')):
            with self.assertRaises(RuntimeError):self.reconcile(p,e)
        self.assertEqual(self.rt.status(self.run)['budget']['execution_holds'],1)

    def test_cli_keeps_resource_release_default(self):
        args=['--db',str(self.db),'release','--attempt','x','--confirmed','--reason','test']
        self.assertEqual(parser().parse_args(args).kind,'host-resource')
        parsed=parser().parse_args(args+['--kind','readonly-turn-completed','--receipt','observation.json'])
        self.assertEqual(parsed.receipt,'observation.json')

    def test_invalid_stale_or_future_host_time_is_rejected(self):
        self.add(spec());p,e,_=self.done(release=False)
        for observed in ('not-a-time','2000-01-01T00:00:00Z','2999-01-01T00:00:00Z','2026-09-06T08:00:00'):
            with self.subTest(observed=observed),self.assertRaises(WorkflowError):
                self.reconcile(p,e,self.receipt(p,e,observed_at=observed))
        self.assertEqual(self.rt.status(self.run)['budget']['execution_holds'],1)


if __name__=='__main__':unittest.main()
