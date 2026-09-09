"""Evaluator tests use synthetic files even when testing its attestation-shaped inputs."""
import copy
import hashlib
import tempfile
from pathlib import Path
import unittest
from scripts.evaluate_native_comparison import evaluate,EvidenceError


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name).resolve()
        capture=self.root/'capture.jsonl';capture.write_text('synthetic unit-test capture; NOT actual model evidence\n')
        cap=dict(path=capture.name,sha256=hashlib.sha256(capture.read_bytes()).hexdigest())
        def agent(name,role='mainline',direction=None):
            e=dict(model='gpt-6-astra' if role=='mainline' else 'gpt-5.6-luna',effort='high' if role=='mainline' else 'max',
                   profile='cwf_reader' if role=='mainline' else 'cwf_general',sandbox='read-only')
            return dict(id=name,role=role,effective=e,requested=dict(e),direction=direction,status='completed')
        def arm(agents):
            return dict(provenance='native-host',synthetic=False,capture=cap,agents=agents,started_at=10,finished_at=20,accepted_at=20,
                        acceptance_passed=True,task_sha256='a'*64,candidate_sha256='b'*64,acceptance_sha256='c'*64,
                        verified_findings=['bug1'],false_findings=[],missed_findings=[],triage_seconds=None,rework_seconds=None,
                        total_tokens=None,host_resources_released=None)
        self.data=dict(status='OBSERVED',pairs=[dict(trial_id='fixture',astra=arm([agent('baseline')]),
            astra_luna=arm([agent('mixed')]+[agent('probe'+str(i),'supplemental',str(i)) for i in range(3)]))])
    def tearDown(self):self.t.cleanup()
    def test_missing_live_trials_are_not_a_pass(self):
        with self.assertRaises(EvidenceError):evaluate(dict(status='NOT_RUN',pairs=[]),self.root)
    def test_attestation_shape_validates_but_never_claims_model_execution(self):
        report=evaluate(self.data,self.root)
        self.assertEqual(report['status'],'ATTESTATIONS_VALIDATED');self.assertEqual(report['model_calls_by_evaluator'],0)
        self.assertIsNone(report['trials'][0]['astra']['total_tokens'])
    def test_unknown_effective_identity_rejected(self):
        self.data['pairs'][0]['astra_luna']['agents'][1]['effective']=None
        with self.assertRaisesRegex(EvidenceError,'UNKNOWN'):evaluate(self.data,self.root)
    def test_synthetic_marker_is_not_live_evidence(self):
        self.data['pairs'][0]['astra']['synthetic']=True
        with self.assertRaisesRegex(EvidenceError,'synthetic'):evaluate(self.data,self.root)
    def test_request_is_not_proof_of_effective_model(self):
        self.data['pairs'][0]['astra_luna']['agents'][1]['effective']['model']='gpt-6-astra'
        with self.assertRaisesRegex(EvidenceError,'mismatched'):evaluate(self.data,self.root)
    def test_different_candidates_and_acceptance_are_not_comparable(self):
        for field in ('candidate_sha256','acceptance_sha256','task_sha256'):
            data=copy.deepcopy(self.data);data['pairs'][0]['astra_luna'][field]='d'*64
            with self.subTest(field=field),self.assertRaisesRegex(EvidenceError,'identical'):evaluate(data,self.root)
    def test_reported_effective_write_access_rejected_for_supplemental(self):
        self.data['pairs'][0]['astra_luna']['agents'][1]['effective']['sandbox']='danger-full-access'
        with self.assertRaisesRegex(EvidenceError,'readonly'):evaluate(self.data,self.root)
    def test_changed_raw_capture_is_rejected(self):
        (self.root/'capture.jsonl').write_text('changed')
        with self.assertRaisesRegex(EvidenceError,'changed'):evaluate(self.data,self.root)
    def test_duplicate_probe_directions_do_not_count_as_three(self):
        for a in self.data['pairs'][0]['astra_luna']['agents'][1:]:a['direction']='same'
        with self.assertRaisesRegex(EvidenceError,'three distinct'):evaluate(self.data,self.root)
    def test_unknown_and_negative_measurements_are_not_zero(self):
        self.data['pairs'][0]['astra']['total_tokens']=-1
        with self.assertRaisesRegex(EvidenceError,'measured'):evaluate(self.data,self.root)
    def test_capture_cannot_escape_trial_directory(self):
        self.data['pairs'][0]['astra']['capture']={'path':'../outside','sha256':'a'*64}
        with self.assertRaisesRegex(EvidenceError,'directory'):evaluate(self.data,self.root)

    def test_failed_arm_is_retained_instead_of_cherry_picking_successes(self):
        arm=self.data['pairs'][0]['astra'];arm['acceptance_passed']=False;arm['accepted_at']=None
        report=evaluate(self.data,self.root)
        self.assertEqual(report['acceptance_pass_delta'],1)
        self.assertFalse(report['trials'][0]['astra']['acceptance_passed'])
