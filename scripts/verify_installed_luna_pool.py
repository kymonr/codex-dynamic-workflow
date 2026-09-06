"""Explicit acceptance: two readonly Luna calls with overlapping owned transports."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import threading
import time


def main():
    if sys.flags.optimize:
        raise RuntimeError('Acceptance requires assertions enabled; do not use -O or PYTHONOPTIMIZE')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--executable', required=True)
    args = parser.parse_args()
    installed = args.skill_dir.resolve(strict=True)
    if 'exec' not in json.loads((installed/'policy.json').read_text(encoding='utf-8'))['runtime']['backends']:
        raise RuntimeError('native-only routing: this legacy CLI model smoke is disabled')
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(installed/'scripts'))
    from cwf_runtime import Runtime, core, executor, luna_pool
    assert Path(luna_pool.__file__).resolve().is_relative_to(installed)
    source = output/'source'; source.mkdir()
    fixtures = {
        'invoice.py': ('def amount_due(subtotal, discount):\n'
                       '    """Discount reduces subtotal: 100 and 10 should give 90."""\n'
                       '    return subtotal + discount\n'),
        'stock.py': ('def remaining_stock(stock, ordered):\n'
                     '    """Remaining stock is never negative; 3 stock and 5 ordered should give 0."""\n'
                     '    return stock - ordered\n')}
    for name, value in fixtures.items(): (source/name).write_text(value, encoding='utf-8')
    expected = {'invoice':'expected=90; actual=110', 'stock':'expected=0; actual=-2'}
    records = []; lock = threading.Lock()
    runtime_files = ['core.py','executor.py','luna_pool.py','cli.py']
    def hashes():
        return {name:hashlib.sha256((installed/'scripts/cwf_runtime'/name).read_bytes()).hexdigest() for name in runtime_files}
    before = hashes()

    def observed_transport(argv, cwd, prompt, **kwargs):
        packet = json.loads(prompt.split('Packet:\n', 1)[1])
        original_started = kwargs['on_started']
        item = {'node':packet['node_id'], 'attempt':packet['attempt'], 'argv':argv,
                'effective_model':'UNKNOWN', 'cleanup':'UNKNOWN'}
        def started(pid):
            original_started(pid)
            with lock:
                item.update(external_id=pid, start=time.monotonic(),
                            started_at=datetime.now(timezone.utc).isoformat())
                records.append(item)
        kwargs['on_started'] = started
        try:
            result = executor.run_owned(argv, cwd, prompt, **kwargs)
        except BaseException as exc:
            with lock: item['error'] = {'type':type(exc).__name__, 'message':str(exc)}
            raise
        with lock:
            item.update(end=time.monotonic(), ended_at=datetime.now(timezone.utc).isoformat(),
                        returncode=result.returncode, stopped=result.stopped,
                        cleanup='owned process tree release confirmed',
                        stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest())
        return result

    db = output/'runtime.sqlite'; error = None; execution = None; accepted = {}
    with Runtime(db, initialize=True) as rt:
        run = rt.create(root=source, goal='Two real bounded readonly Luna verification calls in one independent process pool',
                        backend='exec', execution_pool='luna', capacity_scope='backend',
                        bounds=dict(approved=2,reserve=0,absolute=2,strong_approved=0,capacity=2,
                                    max_attempts=1,max_nodes=2,deadline_seconds=900))
        nodes = []
        for filename in fixtures:
            name = Path(filename).stem
            nodes.append(dict(id=name, role='explorer', risk='low', ordinary_qualified=True,
                              sources=[filename], checks=['documented and actual values characterized'],
                              task='Root completed preflight. Open only '+filename+' directly. This is a harmless deliberately incorrect fixture. '
                                   'Characterize the documented numeric example and actual expression. Include literal markers '
                                   'expected=<documented number>; actual=<implementation number> in summary. '
                                   'PASS means characterization completed, not function correctness. No other sources, preflight, network, '
                                   'agents, file writes, config changes or production actions. One foreground python -B in-memory calculation is allowed.'))
        rt.add(run, nodes, reason='user selected independent Luna execution; two bounded real acceptance calls')
        (output/'contract.json').write_text(json.dumps(core.loads(rt.run(run)['contract']),indent=2)+'\n',encoding='utf-8')
        try:
            execution = luna_pool.execute_pool(rt,run,workers=2,executable=args.executable,
                                               transport=observed_transport,timeout=600)
            assert execution['state'] == 'drained', 'pool did not drain successfully'
            for name, marker in expected.items():
                payload = core.loads(rt.node(run,name)['result'])['submission']['payload']
                assert payload['sources_opened'] == [name+'.py']
                assert marker in payload['summary'], (name, 'numeric characterization differs')
                accepted[name] = payload
            assert len(records) == 2 and len({r['external_id'] for r in records}) == 2
            assert max(r['start'] for r in records) < min(r['end'] for r in records), 'owned transport observation intervals did not overlap'
            status = rt.finish(run)
            assert status['budget']['used'] == 2 and status['budget']['strong_used'] == 0
            assert status['host_resources_released'] and not status['budget']['execution_holds']
            assert all(a['usage'] is not None for a in status['attempts'])
            assert all((source/name).read_text(encoding='utf-8') == value for name,value in fixtures.items())
            assert hashes() == before
        except Exception as exc:
            error = {'type':type(exc).__name__, 'message':str(exc)}
        status = rt.status(run); events = rt.events(run)
    with Runtime(db, read_only=True) as reopened:
        assert reopened.status(run) == status and reopened.events(run) == events
    report = dict(status='PASS' if error is None else 'FAILED', error=error, run_id=run,
                  requested_model='gpt-5.6-luna', requested_effort='max', effective_model='UNKNOWN',
                  execution=execution, runtime=status, accepted=accepted, events=events, transport=records,
                  runtime_hashes=before, runtime_unchanged=hashes()==before,
                  source_unchanged=all((source/name).read_text(encoding='utf-8')==value for name,value in fixtures.items()),
                  installed=str(installed), database=str(db),
                  native_scope='No native agent is created by this harness; Root observes any concurrent Astra separately.')
    path = output/'result.json'; path.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    assert json.loads(path.read_text(encoding='utf-8')) == report
    print(json.dumps(dict(status=report['status'],error=error,run_id=run,runtime=status,
                         transport=records),ensure_ascii=True,indent=2),flush=True)
    return 0 if error is None else 1


if __name__ == '__main__': raise SystemExit(main())
