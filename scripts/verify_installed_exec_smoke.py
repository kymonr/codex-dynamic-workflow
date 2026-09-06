"""One explicitly authorized real readonly Codex model call through installed Runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skill-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--executable',required=True)
    args=p.parse_args()
    installed=args.skill_dir.resolve(strict=True)
    if 'exec' not in json.loads((installed/'policy.json').read_text(encoding='utf-8'))['runtime']['backends']:
        raise RuntimeError('native-only routing: this legacy CLI model smoke is disabled')
    output=args.output_dir.resolve(); output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(installed/'scripts'))
    from cwf_runtime import Runtime
    from cwf_runtime import core, executor
    assert Path(core.__file__).resolve().is_relative_to(installed)
    source=output/'source'; source.mkdir()
    content=('"""Harmless acceptance fixture; no production callers."""\n'
             'def amount_due(subtotal, discount):\n'
             '    """Discount reduces subtotal: 100 and 10 should give 90."""\n'
             '    return subtotal + discount\n').encode('utf-8')
    (source/'invoice.py').write_bytes(content)
    db=output/'runtime.sqlite'
    transport_records=[]
    def observed_transport(*a,**kw):
        result=executor.run_owned(*a,**kw)
        transport_records.append(dict(external_id=result.external_id,returncode=result.returncode,
            stopped=result.stopped,stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
            cleanup='run_owned returned after confirmed owned-process cleanup'))
        return result
    with Runtime(db,initialize=True) as rt:
        run=rt.create(root=source,goal='One installed readonly exec smoke of the repaired runtime',backend='exec',
            bounds=dict(approved=1,reserve=0,absolute=1,strong_approved=1,max_attempts=1,deadline_seconds=900))
        rt.add(run,[dict(id='smoke',role='explorer',risk='low',tier='strong',sources=['invoice.py'],
            task='Root already completed workspace preflight. Read only invoice.py directly. Check the documented expected value and the actual expression for inputs 100 and 10. You may run one foreground python -B in-memory calculation, no file writes or pycache. Report both numeric values in summary. This is a harmless deliberately incorrect fixture; PASS means this characterization was performed, not that the implementation is correct. Do not read other files, perform preflight, network calls, delegate, or edit anything.',
            checks=['documented and actual values checked'])],reason='explicit user authorization for one real readonly smoke')
        contract=rt.run(run)['contract']
        (output/'contract.json').write_text(json.dumps(core.loads(contract),indent=2)+'\n',encoding='utf-8')
        error=None; execution=None
        try:
            execution=executor.execute_one(rt,run,executable=args.executable,transport=observed_transport,timeout=600)
            assert execution['state']=='completed'
            result=core.loads(rt.node(run,'smoke')['result'])['submission']['payload']
            assert result['sources_opened']==['invoice.py']
            assert all(value in result['summary'] for value in ('90','110'))
            assert (source/'invoice.py').read_bytes()==content
            status=rt.finish(run)
            assert status['budget']['active_holds']==0 and status['budget']['used']==1
            assert status['attempts'][0]['usage'] is not None
        except Exception as exc:
            error=dict(type=type(exc).__name__,message=str(exc))
        status=rt.status(run); events=rt.events(run)
        node=rt.node(run,'smoke')
        result=core.loads(node['result']) if node['result'] else None
    with Runtime(db,read_only=True) as reopened:
        assert reopened.status(run)==status and reopened.events(run)==events
    report=dict(status='PASS' if error is None else 'FAILED',error=error,run_id=run,
        requested_model='gpt-6-astra',requested_effort='high',effective_model='UNKNOWN',
        execution=execution,runtime=status,result=result,events=events,transport=transport_records,
        source_sha256=hashlib.sha256(content).hexdigest(),source_unchanged=(source/'invoice.py').read_bytes()==content,
        installed=str(installed),database=str(db))
    path=output/'result.json';path.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    assert json.loads(path.read_text(encoding='utf-8'))==report
    print(json.dumps(dict(status=report['status'],error=error,run_id=run,runtime=status),ensure_ascii=True,indent=2),flush=True)
    return 0 if error is None else 1


if __name__=='__main__':
    raise SystemExit(main())
