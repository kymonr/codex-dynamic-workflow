"""Zero-model subprocess integration tests for the acceptance runner candidate."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/native-validation-2026-09-11'
COLLECTOR_SPEC = importlib.util.spec_from_file_location('collector_candidate', REPORT / 'collector_candidate.py')
COLLECTOR_MODULE = importlib.util.module_from_spec(COLLECTOR_SPEC)
sys.modules[COLLECTOR_SPEC.name] = COLLECTOR_MODULE
COLLECTOR_SPEC.loader.exec_module(COLLECTOR_MODULE)
RUNNER_SPEC = importlib.util.spec_from_file_location('runner_candidate', REPORT / 'runner_candidate.py')
RUNNER_MODULE = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = RUNNER_MODULE
RUNNER_SPEC.loader.exec_module(RUNNER_MODULE)
NativeAcceptanceRunner = RUNNER_MODULE.NativeAcceptanceRunner
SubprocessJsonRpcHost = RUNNER_MODULE.SubprocessJsonRpcHost
EvidenceJournal = RUNNER_MODULE.EvidenceJournal


FAKE_HOST_SOURCE = r'''
import json, os, sys
from pathlib import Path
audit_path = Path(os.environ["ZERO_MODEL_AUDIT"])
audit_path.write_text(json.dumps({"kind":"zero-model-protocol-fixture","model_calls":0,"network_calls":0})+"\n", encoding="utf-8")
reads = {}; status = {"parent":"active"}
children = ("child-main","child-luna-1","child-luna-2","child-luna-3")
'''
FAKE_HOST_SOURCE += r'''
def audit(row):
    with audit_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=True)+"\n")
def emit(row):
    sys.stdout.write(json.dumps(row, ensure_ascii=True)+"\n"); sys.stdout.flush()
def reply(request_id, result=None, error=None):
    row={"id":request_id}
    if error is None: row["result"] = {} if result is None else result
    else: row["error"] = error
    emit(row)
def meta(tid):
    return {"id":tid,
            "parentThreadId": None if tid=="parent" else "parent",
            "model":"SYNTHETIC_ZERO_MODEL", "reasoningEffort":"none",
            "status":{"type":"idle" if status.get(tid)=="idle" else "active"},
            "source":"ZERO_MODEL_FIXTURE"}
def start_child(tid):
    status[tid]="active"
    emit({"method":"thread/started","params":{"thread":{"id":tid,"parentThreadId":"parent"}}})
    emit({"method":"thread/settings/updated","params":{"threadId":tid,
          "model":"SYNTHETIC_ZERO_MODEL","reasoningEffort":"none","sandbox":{"type":"readOnly"}}})
    turn_id="turn-"+tid
    emit({"method":"turn/started","params":{"threadId":tid,"turn":{"id":turn_id,"status":"inProgress"}}})
    emit({"method":"item/started","params":{"threadId":tid,"turnId":turn_id,
          "item":{"id":"item-"+tid,"type":"syntheticCheck","status":"inProgress"}}})
def finish_child(tid):
    status[tid]="idle"; turn_id="turn-"+tid
    emit({"method":"item/completed","params":{"threadId":tid,"turnId":turn_id,
          "item":{"id":"item-"+tid,"type":"syntheticCheck","status":"completed"}}})
    emit({"method":"turn/completed","params":{"threadId":tid,"turn":{"id":turn_id,"status":"completed"}}})
    emit({"method":"thread/status/changed","params":{"threadId":tid,"status":{"type":"idle"}}})
def complete_child(tid):
    start_child(tid); finish_child(tid)
'''
FAKE_HOST_SOURCE += r'''
for raw in sys.stdin:
    message=json.loads(raw); method=message.get("method"); params=message.get("params",{})
    audit({"method":method,"params":params})
    if "id" not in message:
        continue
    request_id=message["id"]
    if method=="initialize":
        reply(request_id,{"fixture":True})
    elif method=="thread/start":
        reply(request_id,{"thread":{"id":"parent","parentThreadId":None},
              "model":"SYNTHETIC_ZERO_MODEL","reasoningEffort":"none",
              "sandbox":{"type":"readOnly"},"activePermissionProfile":"zero-model"})
        emit({"method":"thread/started","params":{"thread":{"id":"parent","parentThreadId":None}}})
        emit({"method":"thread/settings/updated","params":{"threadId":"parent",
              "model":"SYNTHETIC_ZERO_MODEL","reasoningEffort":"none","sandbox":{"type":"readOnly"}}})
    elif method=="turn/start":
        reply(request_id,{"turn":{"id":"turn-parent","status":"inProgress"}})
        emit({"method":"turn/started","params":{"threadId":"parent",
              "turn":{"id":"turn-parent","status":"inProgress"}}})
        complete_child(children[0])
        for child in children[1:]: start_child(child)
    elif method=="turn/steer":
        audit({"kind":"steer-received","running_luna":[
            tid for tid in children[1:] if status.get(tid)=="active"]})
        reply(request_id,{"steered":True})
        complete_child("child-verify")
        for child in children[1:]: finish_child(child)
        status["parent"]="idle"
        emit({"method":"turn/completed","params":{"threadId":"parent",
              "turn":{"id":"turn-parent","status":"completed"}}})
        emit({"method":"thread/status/changed","params":{"threadId":"parent","status":{"type":"idle"}}})
    elif method=="thread/read":
        tid=params["threadId"]; reads[tid]=reads.get(tid,0)+1
        if tid=="child-main" and reads[tid]==1:
            reply(request_id,error={"code":-32000,"message":"synthetic first-read failure"})
        else:
            reply(request_id,{"thread":meta(tid)})
    elif method=="thread/unsubscribe":
        tid=params["threadId"]; reply(request_id,{"status":"unsubscribed"})
        emit({"method":"thread/closed","params":{"threadId":tid}})
    else:
        reply(request_id,error={"code":-32601,"message":"unsupported synthetic method"})
audit({"kind":"eof","model_calls":0,"network_calls":0})
'''


class NativeAcceptanceRunnerIntegrationTests(unittest.TestCase):
    def test_subprocess_runner_zero_model_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = Path(tmp) / 'audit.jsonl'
            env = os.environ.copy(); env['ZERO_MODEL_AUDIT'] = str(audit)
            host = SubprocessJsonRpcHost(
                [sys.executable, '-u', '-c', FAKE_HOST_SOURCE], cwd=ROOT, env=env)
            journal = EvidenceJournal(Path(tmp) / 'evidence')
            runner = NativeAcceptanceRunner(host, max_children=5, max_turns=6,
                                            journal=journal)
            started = runner.start(
                thread_params={'cwd': str(ROOT), 'permissions': ':read-only',
                               'ephemeral': True, 'model': 'SYNTHETIC_ZERO_MODEL'},
                turn_input='synthetic zero-model observer input', rpc_timeout=2.0)
            self.assertEqual(started['effective_start']['sandbox']['type'], 'readOnly')
            sent = [False]
            def controls(_runner):
                if sent[0] or not _runner.collector.execution_complete('child-main'):
                    return []
                sent[0] = True
                return [{'op': 'steer', 'text': 'synthetic required verifier now'}]
            state = runner.run(controls, deadline=time.monotonic()+5,
                               poll_interval=0.005, metadata_rpc_timeout=0.2)
            self.assertEqual(state, 'OBSERVED')
            runner.cleanup(deadline=time.monotonic()+2, per_rpc_timeout=0.2)
            summary = runner.finalize_evidence()
            journal.close()
            self.assertEqual(host.close(timeout=2), 0)
            stored = json.loads((Path(tmp)/'evidence/summary.json').read_text(encoding='utf-8'))
            self.assertEqual(stored, summary)
            timeline = [json.loads(line) for line in
                        (Path(tmp)/'evidence/timeline.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(any(row['kind']=='event' for row in timeline))
            self.assertTrue(any(row['kind']=='rpc' for row in timeline))
            self.assertTrue(any(row['kind']=='control' for row in timeline))

            expected = {'parent', 'child-main', 'child-luna-1', 'child-luna-2',
                        'child-luna-3', 'child-verify'}
            self.assertEqual(set(summary['owned_ids']), expected)
            self.assertEqual(set(summary['observed_ids']), expected)
            self.assertTrue(summary['metadata_captured'])
            self.assertTrue(summary['executions_complete'])
            self.assertEqual(summary['collector_faults'], [])
            self.assertEqual(summary['identity_validation'], 'NOT_PERFORMED')
            self.assertEqual(summary['acceptance'], 'NOT_EVALUATED')
            self.assertEqual(summary['host_resource_recycling'], 'NOT_PROVEN')
            self.assertTrue(any(e['thread_id']=='child-main'
                                and 'synthetic first-read failure' in e['error']
                                for e in summary['collector_errors']))
            self.assertTrue(all(a['metadata_count'] >= 1 for a in summary['actors'].values()))
            self.assertTrue(all(a['metadata'][-1]['model']=='SYNTHETIC_ZERO_MODEL'
                                for a in summary['actors'].values()))
            self.assertTrue(all(a['settings'][-1]['sandbox']['type']=='readOnly'
                                for a in summary['actors'].values()))
            self.assertTrue(all(a['unsubscribe'][-1]['result']['status']=='unsubscribed'
                                for a in summary['actors'].values()))
            self.assertEqual(summary['start_receipt']['effective_start']['sandbox']['type'], 'readOnly')
            self.assertEqual(sum(len(a['turn_ids']) for a in summary['actors'].values()), 6)
            self.assertTrue(all(a['resource_observation']=='THREAD_CLOSED_OBSERVED'
                                for a in summary['actors'].values()))

            methods = [entry['method'] for entry in summary['rpc']]
            self.assertLess(methods.index('turn/steer'), methods.index('thread/read'))
            self.assertNotIn('turn/interrupt', methods)
            self.assertNotIn('thread/archive', methods)
            self.assertEqual(methods.count('turn/start'), 1)
            self.assertEqual(methods.count('turn/steer'), 1)

            rows = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(rows[0]['model_calls'], 0)
            self.assertEqual(rows[0]['network_calls'], 0)
            self.assertEqual(rows[-1]['model_calls'], 0)
            self.assertEqual(rows[-1]['network_calls'], 0)
            steer_audit = next(row for row in rows if row.get('kind') == 'steer-received')
            self.assertEqual(set(steer_audit['running_luna']),
                             {'child-luna-1', 'child-luna-2', 'child-luna-3'})
            received = [row.get('method') for row in rows if 'method' in row]
            self.assertLess(received.index('turn/steer'), received.index('thread/read'))
            self.assertNotIn('turn/interrupt', received)
            self.assertNotIn('thread/archive', received)

    def test_transport_refuses_empty_command(self):
        with self.assertRaises(ValueError):
            SubprocessJsonRpcHost([])


class StubHost:
    def __init__(self, fail_method=None):
        self.fail_method = fail_method
        self.events = []
        self.stderr_lines = []
        self.calls = []
    def send(self, message):
        self.calls.append(('notification', message.get('method')))
    def poll(self):
        return 0
    def call(self, method, params, *, timeout):
        self.calls.append((method, timeout))
        if method == self.fail_method:
            raise TimeoutError('synthetic '+method+' timeout')
        if method == 'initialize':
            return {'result': {}}
        if method == 'thread/start':
            return {'result': {'thread': {'id': 'parent'}, 'sandbox': {'type': 'readOnly'}}}
        if method == 'turn/start':
            return {'result': {'turn': {'id': 'turn-parent', 'status': 'inProgress'}}}
        if method == 'thread/read':
            raise AssertionError('metadata must not run after failed required control')
        return {'result': {}}


class NativeAcceptanceRunnerFailureTests(unittest.TestCase):
    def test_partial_start_failure_is_single_use_and_audited(self):
        host = StubHost(fail_method='turn/start')
        runner = NativeAcceptanceRunner(host)
        with self.assertRaisesRegex(TimeoutError, 'synthetic turn/start timeout'):
            runner.start(thread_params={}, turn_input='zero-model')
        self.assertEqual(runner.status, 'FAILED_START')
        self.assertIn('synthetic turn/start timeout', runner.rpc_log[-1]['transport_error'])
        self.assertEqual(sum(call[0]=='thread/start' for call in host.calls), 1)
        with self.assertRaisesRegex(RuntimeError, 'single-use'):
            runner.start(thread_params={}, turn_input='zero-model')

    def test_failed_required_control_blocks_before_metadata(self):
        host = StubHost()
        runner = NativeAcceptanceRunner(host)
        runner.start(thread_params={}, turn_input='zero-model')
        state = runner.run(lambda _runner: [
            {'op': 'unsupported'}, {'op': 'steer', 'text': 'must not run'}],
            deadline=time.monotonic()+1)
        self.assertEqual(state, 'BLOCKED_BY_CONTROL')
        self.assertTrue(runner.control_failed)
        self.assertFalse(any(call[0]=='thread/read' for call in host.calls))
        self.assertFalse(any(call[0]=='turn/steer' for call in host.calls))


    def test_host_protocol_fault_blocks_before_metadata(self):
        host = StubHost()
        runner = NativeAcceptanceRunner(host)
        runner.start(thread_params={}, turn_input='zero-model')
        host.events.append((time.time(), {'client_error': 'synthetic non-json output'}))
        state = runner.run(lambda _runner: [], deadline=time.monotonic()+1)
        self.assertEqual(state, 'BLOCKED_BY_HOST')
        self.assertEqual(runner.host_faults, ['synthetic non-json output'])
        self.assertFalse(any(call[0]=='thread/read' for call in host.calls))

    def test_evidence_summary_is_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = EvidenceJournal(Path(tmp)/'evidence')
            (Path(tmp)/'evidence/summary.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                journal.finalize({'status': 'synthetic'})
            journal.close()


if __name__ == '__main__':
    unittest.main()
