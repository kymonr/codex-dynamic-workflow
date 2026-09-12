"""Whole-review regressions; native identities and host observations are fixtures."""
import json
import unittest
from unittest.mock import patch
import test_v41_followup as previous
from test_v4_supplemental import node, reply
from cwf_runtime import WorkflowError
from cwf_runtime import core


class Review412Tests(unittest.TestCase):
    setUp = previous.FollowupTests.setUp
    tearDown = previous.FollowupTests.tearDown
    add = previous.FollowupTests.add
    probe = previous.FollowupTests.probe
    acquire = previous.FollowupTests.acquire
    start = previous.FollowupTests.start
    done = previous.FollowupTests.done

    def checked_pair(self, same_author=False, omit_source=False):
        sources = ['a.py', 'b.py'] if omit_source else ['a.py']
        self.add(node('main', sources=sources), node('check', role='reviewer',
                 verifies='main', depends=['main'], sources=['a.py']))
        p, e = self.start(identity='fixture-author')
        self.done(p, e, reply(sources_opened=sources))
        p, e = self.start(identity='fixture-author' if same_author else 'fixture-reviewer')
        self.done(p, e)

    def test_explicit_astra_verifier_cannot_self_verify_low_risk(self):
        self.checked_pair(same_author=True)
        with self.assertRaisesRegex(WorkflowError, 'independent'):
            self.rt.finish(self.run)

    def test_explicit_astra_verifier_must_cover_low_risk_target(self):
        self.checked_pair(omit_source=True)
        with self.assertRaisesRegex(WorkflowError, 'independent'):
            self.rt.finish(self.run)

    def test_valid_low_risk_independent_verification_passes(self):
        self.checked_pair()
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])

    def test_saved_v411_keeps_original_verification_semantics(self):
        c = core.loads(self.rt.run(self.run)['contract']); c['version'] = '4.1.1'
        self.rt.conn.execute('UPDATE runs SET contract=?,contract_hash=? WHERE id=?',
                             (core.dump(c), core.sha(c), self.run))
        before = self.rt.run(self.run)['contract']
        self.checked_pair(same_author=True)
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
        self.assertEqual(self.rt.run(self.run)['contract'], before)

    def test_unbound_reservation_is_added_to_observed_host_threads(self):
        self.add(node('main'), self.probe())
        self.assertTrue(self.acquire(host_capacity=5, host_active=3)['admitted'])
        # Three external threads plus one unbound reservation leave only the Astra slot.
        before = self.rt.status(self.run)['budget']
        denied = self.acquire(host_capacity=5, host_active=3)
        self.assertFalse(denied['admitted'], denied)
        self.assertIn('mainline-capacity-reserved', str(denied))
        self.assertEqual(self.rt.status(self.run)['budget'], before)

    def test_bound_thread_already_in_host_count_is_not_double_counted(self):
        self.add(node('main'), self.probe()); self.start()
        self.assertTrue(self.acquire(host_capacity=5, host_active=3)['admitted'])

    def test_real_one_mib_envelope_boundary_preserves_attempt(self):
        self.add(node('main')); p, e = self.start()
        claim = dict(proposition='p'*8000, impact='i'*8040, evidence=['a.py'],
                     existence='supported', applicability='unknown')
        payload = reply(summary='s', claims=[claim]*64)
        available = core.MAX_JSON_BYTES - len(core.dump(payload).encode('utf-8'))
        self.assertTrue(1 < available < 16000)
        payload['summary'] = 's'*available
        self.assertLess(len(core.dump(payload).encode('utf-8')), core.MAX_JSON_BYTES)
        with self.assertRaisesRegex(WorkflowError, 'JSON.*large'):
            self.rt.complete(p['attempt'], payload, external_id=e, backend='native')
        self.assertEqual(self.rt.attempt(p['attempt'])['state'], 'running')
        self.assertEqual(self.rt.conn.execute('SELECT COUNT(*) FROM claims').fetchone()[0], 0)
        self.done(p, e)
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])

    def test_oversized_saved_envelope_is_rejected_atomically(self):
        self.add(node('main')); p, e = self.start()
        payload = reply(summary='s' * 1600)
        limit = len(core.dump(payload).encode('utf-8')) + 50
        before = self.rt.events(self.run)
        with patch.object(core, 'MAX_JSON_BYTES', limit):
            with self.assertRaisesRegex(WorkflowError, 'JSON.*large'):
                self.rt.complete(p['attempt'], payload, external_id=e, backend='native')
        self.assertEqual(self.rt.attempt(p['attempt'])['state'], 'running')
        self.assertEqual(self.rt.events(self.run), before)
        self.assertEqual(self.rt.status(self.run)['budget']['used'], 1)
        self.done(p, e)
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])


import test_native_comparison_evaluator as comparison
from scripts.evaluate_native_comparison import evaluate, EvidenceError


class ComparisonReviewTests(unittest.TestCase):
    setUp = comparison.ComparisonTests.setUp
    tearDown = comparison.ComparisonTests.tearDown

    def test_mismatched_reference_defect_sets_are_rejected(self):
        self.data['pairs'][0]['astra_luna']['verified_findings'].append('bug2')
        with self.assertRaisesRegex(EvidenceError, 'reference'):
            evaluate(self.data, self.root)

    def test_additional_finding_requires_baseline_miss_in_same_reference_set(self):
        pair = self.data['pairs'][0]
        pair['astra']['missed_findings'].append('bug2')
        pair['astra_luna']['verified_findings'].append('bug2')
        result = evaluate(self.data, self.root)
        self.assertEqual(result['trials'][0]['incremental_verified_findings'], ['bug2'])

    def test_failed_arm_is_not_reported_as_a_faster_delivery(self):
        arm = self.data['pairs'][0]['astra_luna']
        arm.update(acceptance_passed=False, accepted_at=None, finished_at=11)
        report = evaluate(self.data, self.root)
        self.assertIsNone(report['median_elapsed_delta_seconds'])
        self.assertIsNone(report['trials'][0]['elapsed_delta_seconds'])
        self.assertEqual(report['acceptance_pass_delta'], -1)


if __name__ == '__main__':
    unittest.main()
