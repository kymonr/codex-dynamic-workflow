"""Zero-model regressions for the native-acceptance collector review candidate."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/native-validation-2026-09-11'
SPEC = importlib.util.spec_from_file_location('cwf_acceptance_collector_candidate', REPORT / 'collector_candidate.py')
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
Collector = MODULE.Collector


def turn(tid, status='completed', method='turn/completed', turn_id=None):
    return {'method': method, 'params': {'threadId': tid,
            'turn': {'id': turn_id or 'turn-' + tid, 'status': status}}}


def started(tid, parent='parent'):
    return {'method': 'thread/started', 'params': {'thread': {'id': tid, 'parentThreadId': parent}}}


def item(tid, method='item/started', kind='futureTool', status=None):
    raw = {'id': 'item-1', 'type': kind}
    if status is not None:
        raw['status'] = status
    return {'method': method, 'params': {'threadId': tid, 'turnId': 'turn-' + tid, 'item': raw}}


def ready(*children):
    collector = Collector('parent')
    collector.observe(turn('parent'), 1.0)
    for child in children:
        collector.observe(started(child), 1.1)
        collector.observe(turn(child), 2.0)
    return collector


def historical(events, failed_read=None):
    """Extract functions, NEVER import/execute the historical native runner."""
    tree = ast.parse((REPORT / 'collector-fixed.py.txt').read_text(encoding='utf-8'))
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ('drain', 'snapshot', 'actors_settled')]
    calls = []
    def rpc(method, params):
        calls.append((method, deepcopy(params)))
        if method == 'thread/list':
            return {'data': [], 'nextCursor': None}
        if params['threadId'] == failed_read:
            raise RuntimeError('synthetic unavailable metadata')
        return {'thread': {'id': params['threadId']}}
    scope = dict(parent='parent', known=set(), record={'agents': {}}, ended=False,
                 seen_turns=set(), json=json, event_file=io.StringIO(),
                 host=SimpleNamespace(poll=lambda: None, events=[(1.0, e) for e in events]),
                 publish=lambda: None, rpc=rpc, capture_context=lambda *_: None)
    exec(compile(ast.Module(body=funcs, type_ignores=[]), 'historical-functions-only', 'exec'), scope)
    with redirect_stdout(io.StringIO()):
        scope['drain']()
    return scope, calls


class HistoricalCounterexamples(unittest.TestCase):
    def test_metadata_error_skips_later_threads(self):
        scope, calls = historical([turn('parent'), turn('child-a'), turn('child-b')], 'child-a')
        with self.assertRaises(RuntimeError):
            scope['snapshot']()
        self.assertEqual([p['threadId'] for m, p in calls if m == 'thread/read'], ['parent', 'child-a'])

    def test_nested_started_event_is_missed(self):
        scope, _ = historical([turn('parent'), started('child')])
        self.assertEqual(scope['known'], set())
        self.assertTrue(scope['actors_settled']())

    def test_unrelated_turn_enters_mutation_allowlist(self):
        scope, _ = historical([turn('parent'), turn('unrelated')])
        self.assertIn('unrelated', scope['known'])


class CollectorCandidateTests(unittest.TestCase):
    def test_captured_six_turns_require_separate_lineage_evidence(self):
        capture = json.loads((REPORT / 'lifecycle-events.json').read_text(encoding='utf-8'))
        c = Collector(capture['parent_thread_id'])
        for event in capture['events']:
            c.observe({'method': event['method'], 'params': event['params']}, event['observed_at'])
        self.assertEqual(sum(len(a.turns) for a in c.actors.values()), 6)
        self.assertEqual(len(c.events), 12)
        self.assertFalse(c.all_executions_complete())
        # Explicitly synthetic lineage, not recovered historical host evidence.
        for tid in c.actors:
            if tid != c.parent:
                c.record_metadata(tid, {'id': tid, 'parentThreadId': c.parent, 'source': 'TEST_STUB'})
        self.assertTrue(c.all_executions_complete())
        self.assertTrue(all(c.resource_observation(tid) == 'UNKNOWN' for tid in c.actors))

    def test_started_child_without_turn_blocks_settlement(self):
        c = ready()
        c.observe(started('child'), 2.0)
        self.assertIn('child', c.owned_ids())
        self.assertFalse(c.all_executions_complete())

    def test_unrelated_event_is_preserved_but_not_controlled(self):
        c = ready()
        c.observe(turn('unrelated'), 2.0)
        self.assertIn('unrelated', c.actors)
        self.assertNotIn('unrelated', c.owned_ids())
        self.assertFalse(c.all_executions_complete())
        calls = []
        c.unsubscribe_settled(lambda m, p, **kw: calls.append(p['threadId']) or {'status': 'unsubscribed'}, deadline=1, clock=lambda: 0)
        self.assertEqual(calls, ['parent'])

    def test_unknown_running_and_missing_turns_are_not_terminal(self):
        for status in ('inProgress', 'UNKNOWN', None):
            with self.subTest(status=status):
                c = ready('child')
                c.observe(turn('child', status), 3.0)
                self.assertFalse(c.execution_complete('child'))
        self.assertFalse(Collector('parent').execution_complete('parent'))

    def test_all_terminal_statuses_mean_execution_only(self):
        for status in ('completed', 'failed', 'interrupted'):
            c = Collector('parent')
            c.observe(turn('parent', status), 1.0)
            self.assertTrue(c.execution_complete('parent'))
            self.assertEqual(c.resource_observation('parent'), 'UNKNOWN')

    def test_unknown_item_type_is_still_tracked(self):
        c = ready('child')
        c.observe(item('child'), 3.0)
        self.assertFalse(c.execution_complete('child'))
        c.observe(item('child', 'item/completed'), 4.0)
        self.assertTrue(c.execution_complete('child'))

    def test_malformed_item_cannot_authorize_cleanup(self):
        c = ready('child')
        event = item('child')
        del event['params']['turnId']
        c.observe(event, 3.0)
        self.assertTrue(c.stop_required)
        self.assertFalse(c.execution_complete('child'))

    def test_completed_item_with_running_status_stays_unsettled(self):
        c = ready('child')
        c.observe(item('child', 'item/completed', 'commandExecution', 'inProgress'), 3.0)
        self.assertFalse(c.execution_complete('child'))

    def test_active_host_status_overrides_old_completed_turn(self):
        c = ready('child')
        c.observe({'method': 'thread/status/changed', 'params': {'threadId': 'child', 'status': {'type': 'active'}}}, 3.0)
        self.assertFalse(c.execution_complete('child'))

    def test_new_turn_reopens_execution_and_invalidates_old_unsubscribe(self):
        c = ready('child')
        c.unsubscribe_settled(lambda *a, **kw: {'status': 'unsubscribed'}, deadline=1, clock=lambda: 0)
        c.observe(turn('child', 'inProgress', 'turn/started', 'second-turn'), 3.0)
        self.assertFalse(c.execution_complete('child'))
        self.assertEqual(c.resource_observation('child'), 'UNKNOWN')

    def test_duplicate_turn_events_do_not_consume_extra_budget(self):
        c = ready()
        for _ in range(9):
            c.observe(turn('parent'), 2.0)
        self.assertEqual(len(c.actors['parent'].turns), 1)
        self.assertFalse(c.stop_required)

    def test_lineage_conflict_revokes_descendants(self):
        c = ready('child')
        c.observe(started('grandchild', 'child'), 3.0)
        self.assertIn('grandchild', c.owned_ids())
        c.record_metadata('child', {'id': 'child', 'parentThreadId': 'other-root'})
        self.assertNotIn('child', c.owned_ids())
        self.assertNotIn('grandchild', c.owned_ids())
        self.assertTrue(c.stop_required)

    def test_bad_metadata_identity_is_not_accepted(self):
        c = ready('child')
        with self.assertRaises(ValueError):
            c.record_metadata('child', {'id': 'other'})
        self.assertEqual(c.actors['child'].metadata, [])

    def test_metadata_failures_do_not_starve_other_threads(self):
        c = ready('child-a', 'child-b')
        reads = []
        def rpc(method, params, **kwargs):
            reads.append(params['threadId'])
            if params['threadId'] == 'child-a':
                raise TimeoutError('synthetic timeout')
            return {'thread': {'id': params['threadId']}}
        for _ in range(3):
            c.metadata_step(rpc, deadline=1, clock=lambda: 0)
        self.assertEqual(reads, ['parent', 'child-a', 'child-b'])
        self.assertEqual(len(c.errors), 1)
        self.assertEqual(len(c.actors['child-b'].metadata), 1)
        self.assertTrue(c.execution_complete('child-a'))

    def test_metadata_step_is_one_bounded_read(self):
        c = ready('child')
        calls = []
        c.metadata_step(lambda m, p, **kw: calls.append(kw['timeout']) or {'thread': {'id': p['threadId']}}, deadline=0.1, clock=lambda: 0)
        self.assertEqual(calls, [0.1])

    def test_expired_deadline_makes_no_metadata_call(self):
        c = ready()
        calls = []
        self.assertIsNone(c.metadata_step(lambda *a, **kw: calls.append(a), deadline=1, clock=lambda: 2))
        self.assertEqual(calls, [])

    def test_cleanup_error_does_not_skip_remaining_owned_threads(self):
        c = ready('child-a', 'child-b')
        calls = []
        def rpc(method, params, **kwargs):
            calls.append((method, params['threadId']))
            if params['threadId'] == 'child-a':
                raise RuntimeError('synthetic unavailable child')
            return {'status': 'unsubscribed'}
        c.unsubscribe_settled(rpc, deadline=1, clock=lambda: 0)
        self.assertEqual(calls, [('thread/unsubscribe', 'child-a'), ('thread/unsubscribe', 'child-b'), ('thread/unsubscribe', 'parent')])
        self.assertEqual(c.resource_observation('child-a'), 'UNKNOWN')
        self.assertEqual(c.resource_observation('child-b'), 'UNSUBSCRIBED_ONLY')

    def test_unsubscribe_and_closed_are_distinct_observations(self):
        c = ready('child')
        c.unsubscribe_settled(lambda *a, **kw: {'status': 'unsubscribed'}, deadline=1, clock=lambda: 0)
        self.assertEqual(c.resource_observation('child'), 'UNSUBSCRIBED_ONLY')
        c.observe({'method': 'thread/closed', 'params': {'threadId': 'child'}}, 3.0)
        self.assertEqual(c.resource_observation('child'), 'THREAD_CLOSED_OBSERVED')

    def test_cleanup_deadline_preserves_missing_receipts(self):
        c = ready('child')
        calls = []
        c.unsubscribe_settled(lambda *a, **kw: calls.append(a) or {'status': 'unsubscribed'}, deadline=1, clock=lambda: 2)
        self.assertEqual(calls, [])
        self.assertEqual(len(c.errors), 2)
        self.assertEqual(c.resource_observation('child'), 'UNKNOWN')

    def test_unknown_unsubscribe_status_stays_unknown(self):
        c = ready()
        c.unsubscribe_settled(lambda *a, **kw: {'status': 'UNKNOWN'}, deadline=1, clock=lambda: 0)
        self.assertEqual(c.resource_observation('parent'), 'UNKNOWN')
        self.assertEqual(len(c.errors), 1)

    def test_pending_host_request_is_retained_and_never_approved(self):
        c = ready()
        c.observe({'id': 1, 'method': 'approval', 'params': {}}, 2.0)
        c.observe(turn('child'), 3.0)
        self.assertTrue(c.stop_required)
        self.assertEqual(len(c.events), 3)
        self.assertIn('child', c.actors)

    def test_parent_settings_do_not_become_child_identity(self):
        c = ready('child')
        c.observe({'method': 'thread/settings/updated', 'params': {'threadId': 'parent', 'model': 'test-model', 'sandbox': 'readOnly'}}, 3.0)
        self.assertEqual(c.actors['child'].settings, [])
        self.assertEqual(c.actors['child'].metadata, [])

    def test_limits_detect_overruns_without_dropping_evidence(self):
        c = Collector('parent', max_children=0, max_turns=1)
        c.observe(started('child'), 1.0)
        c.observe(turn('child'), 2.0)
        c.observe(turn('parent'), 3.0)
        self.assertTrue(c.stop_required)
        self.assertEqual(len(c.events), 3)
        self.assertEqual(len(c.actors), 2)

    def test_observations_are_copied(self):
        c = Collector('parent')
        event = turn('parent')
        c.observe(event, 1.0)
        event['params']['turn']['status'] = 'UNKNOWN'
        self.assertTrue(c.execution_complete('parent'))
        self.assertEqual(c.events[0]['message']['params']['turn']['status'], 'completed')

    def test_activity_during_unsubscribe_cannot_rebind_old_receipt(self):
        c = ready()
        def rpc(*args, **kwargs):
            c.observe(turn('parent', 'inProgress', 'turn/started', 'new-turn'), 3.0)
            return {'status': 'unsubscribed'}
        c.unsubscribe_settled(rpc, deadline=1, clock=lambda: 0)
        self.assertEqual(c.resource_observation('parent'), 'UNKNOWN')
        self.assertEqual(len(c.actors['parent'].unsubscribe), 1)

    def test_active_status_invalidates_old_closed_observation(self):
        c = ready()
        c.observe({'method': 'thread/closed', 'params': {'threadId': 'parent'}}, 3.0)
        c.observe({'method': 'thread/status/changed', 'params': {'threadId': 'parent', 'status': {'type': 'active'}}}, 4.0)
        self.assertEqual(c.resource_observation('parent'), 'UNKNOWN')

    def test_structured_unknown_unsubscribe_status_is_not_a_crash(self):
        c = ready()
        c.unsubscribe_settled(lambda *a, **kw: {'status': {'unknown': True}}, deadline=1, clock=lambda: 0)
        self.assertEqual(c.resource_observation('parent'), 'UNKNOWN')
        self.assertEqual(len(c.errors), 1)

    def test_metadata_active_status_is_negative_execution_evidence(self):
        c = ready()
        c.record_metadata('parent', {'id': 'parent', 'status': {'type': 'active'}})
        self.assertFalse(c.execution_complete('parent'))

    def test_cleanup_budget_is_shared_across_the_pass(self):
        c = ready('child-a', 'child-b')
        now, calls = [0.0], []
        def rpc(method, params, **kwargs):
            calls.append(params['threadId'])
            now[0] += kwargs['timeout']
            return {'status': 'unsubscribed'}
        c.unsubscribe_settled(rpc, deadline=0.5, clock=lambda: now[0])
        self.assertEqual(calls, ['child-a', 'child-b'])
        self.assertEqual(c.resource_observation('parent'), 'UNKNOWN')

    def test_invalid_bounds_rejected(self):
        for kwargs in ({'max_children': -1}, {'max_children': True}, {'max_turns': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Collector('parent', **kwargs)
        with self.assertRaises(ValueError):
            ready().metadata_step(lambda *a, **kw: None, deadline=float('inf'))


if __name__ == '__main__':
    unittest.main()
