"""Synthetic comparison/serialization cases, not observed native experiments."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch
import test_native_comparison_evaluator as fixtures
from scripts.evaluate_native_comparison import evaluate, EvidenceError, main
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skill/codex-dynamic-workflow/scripts'))
from cwf_runtime import core


class EvidenceReviewTests(unittest.TestCase):
    setUp = fixtures.ComparisonTests.setUp
    tearDown = fixtures.ComparisonTests.tearDown

    def test_agent_failure_does_not_mean_failed_mixed_arm(self):
        arm = self.data['pairs'][0]['astra_luna']
        arm['agents'][1]['status'] = arm['attempts'][1]['status'] = 'failed'
        report = evaluate(self.data, self.root)
        self.assertTrue(report['trials'][0]['astra_luna']['acceptance_passed'])
        self.assertEqual(report['trials'][0]['astra_luna']['attempt_status_counts']['supplemental']['failed'], 1)

    def test_recovered_turn_on_same_agent_is_retained(self):
        arm = self.data['pairs'][0]['astra']
        arm['attempts'].insert(0, dict(id='baseline-turn0', agent_id='baseline', status='failed'))
        report = evaluate(self.data, self.root)
        self.assertTrue(report['trials'][0]['astra']['acceptance_passed'])
        self.assertEqual(report['trials'][0]['astra']['attempt_status_counts']['mainline'], {'failed': 1, 'completed': 1})

    def test_missing_or_incomplete_attempt_history_is_not_qualified(self):
        arm = self.data['pairs'][0]['astra']
        for change in ({'attempts': []}, {'attempts_complete': False}):
            before = dict(arm); arm.update(change)
            with self.assertRaisesRegex(EvidenceError, 'history'): evaluate(self.data, self.root)
            arm.clear(); arm.update(before)

    def test_old_input_schema_is_not_silently_upgraded(self):
        self.data.pop('schema_version')
        with self.assertRaisesRegex(EvidenceError, 'schema_version'): evaluate(self.data, self.root)

    def test_reused_turn_id_is_rejected(self):
        self.data['pairs'][0]['astra_luna']['attempts'][0]['id'] = 'baseline-turn1'
        with self.assertRaisesRegex(EvidenceError, 'turn IDs'): evaluate(self.data, self.root)

    def test_latest_agent_snapshot_must_match_recorded_turn(self):
        self.data['pairs'][0]['astra_luna']['attempts'][1]['status'] = 'failed'
        with self.assertRaisesRegex(EvidenceError, 'last captured'): evaluate(self.data, self.root)

    def test_live_supplemental_turn_does_not_invalidate_arm_acceptance(self):
        arm = self.data['pairs'][0]['astra_luna']
        arm['agents'][1]['status'] = arm['attempts'][1]['status'] = 'running'
        self.assertTrue(evaluate(self.data, self.root)['trials'][0]['astra_luna']['acceptance_passed'])
        arm['host_resources_released'] = True
        with self.assertRaisesRegex(EvidenceError, 'cleanup'): evaluate(self.data, self.root)

    def test_malformed_agent_and_status_fail_cleanly(self):
        arm = self.data['pairs'][0]['astra_luna']; original = arm['agents'][1]
        arm['agents'][1] = None
        with self.assertRaisesRegex(EvidenceError, 'object'): evaluate(self.data, self.root)
        arm['agents'][1] = original; arm['attempts'][1]['status'] = []
        with self.assertRaisesRegex(EvidenceError, 'status'): evaluate(self.data, self.root)

    def test_conflicting_json_keys_fail_before_grading(self):
        path = self.root/'duplicate.json'; path.write_text('{"status":"NOT_RUN","status":"OBSERVED"}')
        output = io.StringIO()
        with contextlib.redirect_stdout(output): code = main([str(path)])
        self.assertEqual(code, 1)
        self.assertIn('duplicate JSON key', json.loads(output.getvalue())['reason'])

    def test_large_hash_preimage_is_not_a_stored_json_envelope(self):
        value = {'records': ['x' * 40] * 10}
        with patch.object(core, 'MAX_JSON_BYTES', 100):
            self.assertEqual(len(core.sha(value)), 64)
            with self.assertRaisesRegex(core.WorkflowError, 'JSON.*large'): core.dump(value)

    def test_implausibly_large_numeric_measurement_is_rejected(self):
        self.data['pairs'][0]['astra']['total_tokens'] = 10**1000
        with self.assertRaisesRegex(EvidenceError, 'measured'): evaluate(self.data, self.root)

    def test_nonterminal_history_cannot_be_hidden_by_later_completion(self):
        arm = self.data['pairs'][0]['astra']
        arm['attempts'].insert(0, dict(id='still-running', agent_id='baseline', status='running'))
        with self.assertRaisesRegex(EvidenceError, 'nonterminal'): evaluate(self.data, self.root)


if __name__ == '__main__':
    unittest.main()
