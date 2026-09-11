"""Offline collector regression using captured lifecycle events; starts no models."""
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
capture = json.loads((ROOT / 'lifecycle-events.json').read_text(encoding='utf-8'))
parent = capture['parent_thread_id']
events = capture['events']
expected = {e['params']['threadId'] for e in events} - {parent}

def replay(filename):
    source = ROOT / filename
    tree = ast.parse(source.read_text(encoding='utf-8'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('drain', 'snapshot', 'actors_settled')]
    reads = []
    def rpc(method, params):
        if method == 'thread/list':
            return {'data': [], 'nextCursor': None}
        if method == 'thread/read':
            reads.append(params['threadId'])
            return {'thread': {'id': params['threadId'], 'status': {'type': 'notLoaded'}, 'source': 'REPLAY_STUB'}}
        raise AssertionError(method)
    scope = dict(parent=parent, known=set(), record={'agents': {}}, ended=False,
                 seen_turns=set(), json=json, event_file=io.StringIO(),
                 host=SimpleNamespace(poll=lambda: None, events=[
                     (e['observed_at'], {'method': e['method'], 'params': e['params']}) for e in events]),
                 publish=lambda: None, rpc=rpc, capture_context=lambda *_: None)
    # Extract only the collector functions. Never import or execute a runner module.
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), scope)
    with redirect_stdout(io.StringIO()):
        scope['drain']()
        scope['snapshot']()
    if 'actors_settled' in scope:
        assert scope['actors_settled']()
        actor = scope['record']['agents'][next(iter(expected))]
        turn = next(iter(actor['turns'].values()))
        original = turn['status']
        for status in ('inProgress', 'UNKNOWN'):
            turn['status'] = status
            assert not scope['actors_settled']()
        turn['status'] = original
        actor['tools']['pending'] = {'stage': 'item/started'}
        assert not scope['actors_settled']()
        del actor['tools']['pending']
        assert scope['actors_settled']()
    return {'known_children': sorted(scope['known']), 'metadata_read_ids': reads,
            'turn_count': len(scope['seen_turns']), 'observer_terminal': scope['ended']}

before = replay('collector-executed.py.txt')
after = replay('collector-fixed.py.txt')
assert len(events) == 12 and len(expected) == 5
assert before['known_children'] == [] and before['metadata_read_ids'] == [parent]
assert set(after['known_children']) == expected
assert set(after['metadata_read_ids']) == expected | {parent}
assert len(after['metadata_read_ids']) == 6
assert before['turn_count'] == after['turn_count'] == 6
assert before['observer_terminal'] and after['observer_terminal']
print(json.dumps({'status': 'PASS', 'model_calls': 0,
                  'mode': 'captured-events-with-stub-metadata', 'before': before, 'after': after,
                  'live_host_retest': 'NOT_RUN', 'historical_metadata_recovered': False}, indent=2))
