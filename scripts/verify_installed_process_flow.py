"""Bounded installed-Runtime acceptance with real harmless processes, no model calls.

The injected transport runs the installed run_owned implementation against a local
JSONL emitter instead of Codex. Fault injection never changes Windows ACLs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch


EMITTER = r'''
import json, subprocess, sys, time
case = sys.argv[1]
if case == 'timeout':
    time.sleep(60)
    raise SystemExit(0)
if case == 'normal-tree':
    child = subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(60)'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             creationflags=0x08000000 if sys.platform == 'win32' else 0)
    print('fixture_descendant_pid='+str(child.pid), file=sys.stderr, flush=True)
if case == 'malformed':
    sys.stdout.buffer.write(b'not-json\n')
    raise SystemExit(0)
summary = 'local process fixture response'
if case == 'unicode': summary += ''.join(map(chr,(0x85,0x2028,0x2029)))
payload = dict(outcome='completed', summary=summary, sources_opened=['sample.txt'],
               checks=[dict(name='fixture protocol checked', status='PASS')], changed_files=[], claims=[])
message = json.dumps(payload, ensure_ascii=False)
if case == 'bigint': message = message[:-1]+',"untrusted_integer":'+'9'*5000+'}'
events = [dict(type='turn.started'),
          dict(type='item.completed',item=dict(type='agent_message',text=message)),
          dict(type='turn.completed',usage=dict(input_tokens=10,output_tokens=2))]
sys.stdout.buffer.write(('\n'.join(json.dumps(e,ensure_ascii=False) for e in events)+'\n').encode('utf-8'))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    installed = args.skill_dir.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(installed/'scripts'))
    from cwf_runtime import Runtime, WorkflowError
    from cwf_runtime import core, executor
    assert Path(core.__file__).resolve().is_relative_to(installed)
    assert Path(executor.__file__).resolve().is_relative_to(installed)
    source = output/'fixture'; source.mkdir()
    original = b'bounded harmless source\n'
    (source/'sample.txt').write_bytes(original)
    emitter = output/'emitter.py'; emitter.write_text(EMITTER, encoding='utf-8')
    db = output/'acceptance.sqlite'
    records = []
    cases = ('normal-tree','unicode','malformed','bigint','source-denied','timeout','lost-return')
    with Runtime(db, initialize=True) as rt:
        for case in cases:
            run = rt.create(root=source,goal='installed real-process acceptance: '+case,backend='exec',
                            bounds=dict(approved=1,reserve=0,absolute=1,strong_approved=1,max_attempts=1))
            rt.add(run,[dict(id='check',role='explorer',task='Consume the deterministic fixture result.',
                            sources=['sample.txt'],checks=['fixture protocol checked'],risk='low')],reason='explicit local acceptance')
            transport_results = []; active_counts = []; source_denied = [False]
            original_fingerprint = core.fingerprint
            def fingerprint(*a, **kw):
                if source_denied[0]: raise PermissionError('injected post-transport source denial; no ACL change')
                return original_fingerprint(*a, **kw)
            def transport(argv, cwd, prompt, **kw):
                result = executor.run_owned([sys.executable,'-B',str(emitter),case],cwd,prompt,**kw)
                transport_results.append(result)
                source_denied[0] = case == 'source-denied'
                if case == 'lost-return': raise OSError('injected loss of confirmed transport response')
                return result
            original_active = executor.WindowsJob.active_count
            def active(job):
                count = original_active(job); active_counts.append(count); return count
            observed_error = None; returned = None
            with patch.object(core,'fingerprint',side_effect=fingerprint), patch.object(executor.WindowsJob,'active_count',active):
                try:
                    returned = executor.execute_one(rt,run,executable=sys.executable,transport=transport,
                                                    timeout=1 if case=='timeout' else 15)
                except (ValueError,OSError) as exc:
                    observed_error = dict(type=type(exc).__name__,message=str(exc),notes=getattr(exc,'__notes__',[]))
            assert len(transport_results)==1
            result = transport_results[0]
            if os.name=='nt': assert active_counts and active_counts[-1]==0
            status = rt.status(run)
            assert status['budget']['used']==1
            reconciliation = None
            if case=='lost-return':
                assert observed_error['type']=='OSError' and status['budget']['active_holds']==1
                assert status['attempts'][0]['state']=='running'
                reconciliation = status
                rt.release(status['attempts'][0]['attempt'],external_id=result.external_id,confirmed=True,
                           reason='acceptance controller observed returned run_owned cleanup and zero job processes')
            else:
                assert status['budget']['active_holds']==0
            if case in {'normal-tree','unicode'}:
                assert observed_error is None and returned['state']=='completed'
                status = rt.finish(run)
                assert status['attempts'][0]['usage']==dict(input_tokens=10,output_tokens=2)
                if case=='unicode':
                    saved = core.loads(rt.node(run,'check')['result'])['submission']['payload']['summary']
                    assert all(char in saved for char in ('\u0085','\u2028','\u2029'))
            elif case=='source-denied':
                assert observed_error['type']=='PermissionError'
                assert status['attempts'][0]['state']=='interrupted'
                assert status['attempts'][0]['usage']==dict(input_tokens=10,output_tokens=2)
            elif case=='timeout':
                assert observed_error is None and result.stopped and status['attempts'][0]['state']=='interrupted'
            elif case in {'malformed','bigint'}:
                assert observed_error is not None and status['attempts'][0]['state']=='failed'
            if case not in {'normal-tree','unicode'}:
                rt.cancel(run,reason='intentional negative acceptance case complete; retain failure history')
            status = rt.status(run)
            assert status['budget']['execution_holds']==0 and status['budget']['host_resource_holds']==0
            record = dict(case=case,run_id=run,worker_pid=result.external_id,
                          descendant_pids=re.findall(r'fixture_descendant_pid=(\d+)',result.stderr),
                          transport_returncode=result.returncode,stopped=result.stopped,
                          observed_job_active_counts=active_counts,error=observed_error,
                          pre_reconciliation=reconciliation,status=status,events=rt.events(run))
            if case=='normal-tree': assert len(record['descendant_pids'])==1
            records.append(record)
            print(json.dumps(dict(case=case,acceptance='PASS',state=status['attempts'][0]['state'],
                                  active_holds=status['budget']['active_holds']),ensure_ascii=True),flush=True)
    with Runtime(db,read_only=True) as reopened:
        for record in records:
            assert reopened.status(record['run_id'])==record['status']
            assert reopened.events(record['run_id'])==record['events']
    assert (source/'sample.txt').read_bytes()==original
    report = dict(status='PASS',kind='installed Runtime with real local processes and injected deterministic responses',
                  model_calls=0,os=os.name,installed=str(installed),database=str(db),
                  source_sha256=hashlib.sha256(original).hexdigest(),cases=records,
                  installed_code_hashes={p:hashlib.sha256((installed/'scripts/cwf_runtime'/p).read_bytes()).hexdigest()
                                         for p in ('core.py','executor.py','worker.py')})
    target = output/'result.json'
    target.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    assert json.loads(target.read_text(encoding='utf-8'))==report
    print('ALL_CASES_PASS; database reopened; source unchanged; no model calls',flush=True)


if __name__=='__main__':
    main()
