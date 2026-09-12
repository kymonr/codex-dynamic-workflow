"""Independent capacity and finite pool lifecycle with real SQLite and owned processes."""
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

import test_runtime as initial
from test_runtime import spec, reply
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime.core import DEFAULT_ROUTES, loads
from cwf_runtime.executor import ProcessResult, execute_one, run_owned
from cwf_runtime.luna_pool import execute_pool


def stream(payload=None):
    return '\n'.join(json.dumps(v) for v in (
        {'type':'turn.started'},
        {'type':'item.completed', 'item':{'type':'agent_message', 'text':json.dumps(payload or reply())}},
        {'type':'turn.completed', 'usage':{'input_tokens':12, 'output_tokens':3}}))


class LunaPoolTests(unittest.TestCase):
    setUp = initial.RuntimeTests.setUp
    tearDown = initial.RuntimeTests.tearDown

    def make_run(self, backend='exec', scope='backend', capacity=6, pool=False, **extra):
        fields = dict(root=self.root, goal='independent bounded inspection', backend=backend,
                      bounds={'capacity':capacity, 'strong_approved':0 if pool else 8})
        if scope is not None: fields['capacity_scope'] = scope
        if pool: fields['execution_pool'] = 'luna'
        fields.update(extra)
        return self.rt.create(workflow='legacy', **fields)

    def nodes(self, run, *values):
        self.rt.add(run, list(values), reason='bounded test batch')

    def release(self, packet):
        self.rt.release(packet['attempt'], external_id=None, confirmed=True, reason='test reservation never launched')

    def transport(self, argv, cwd, prompt, **kwargs):
        packet = json.loads(prompt.split('Packet:\n', 1)[1])
        pid = 'fixture-' + packet['attempt']
        kwargs['on_started'](pid)
        return ProcessResult(pid, 0, stream(), '')

    def test_missing_scope_preserves_database_capacity_and_contract_bytes(self):
        native = self.make_run('native', None, 1)
        old = self.rt.run(native)
        self.assertNotIn('capacity_scope', loads(old['contract']))
        other = self.make_run(pool=True)
        self.nodes(other, spec(ordinary_qualified=True))
        held = self.rt.acquire(other, backend='exec')
        self.nodes(native, spec())
        self.assertFalse(self.rt.acquire(native, backend='native')['admitted'])
        with Runtime(self.db) as reopened:
            current = reopened.run(native)
            self.assertEqual((old['contract'], old['contract_hash']), (current['contract'], current['contract_hash']))
        self.release(held)
        self.assertTrue(self.rt.acquire(native, backend='native')['admitted'])

    def test_explicit_database_scope_still_counts_other_backend(self):
        native = self.make_run('native', 'database', 1)
        other = self.make_run(pool=True)
        self.nodes(other, spec(ordinary_qualified=True)); self.nodes(native, spec())
        self.rt.acquire(other, backend='exec')
        self.assertEqual(self.rt.acquire(native, backend='native')['reasons'][0]['reason'], 'live-capacity')

    def test_backend_scope_separates_native_and_counts_other_exec_runs(self):
        native = self.make_run('native', capacity=1)
        first = self.make_run(capacity=1, pool=True)
        second = self.make_run(capacity=1, pool=True)
        for run in (native, first, second): self.nodes(run, spec(ordinary_qualified=run != native))
        native_hold = self.rt.acquire(native, backend='native')
        exec_hold = self.rt.acquire(first, backend='exec')
        self.assertTrue(native_hold['admitted']); self.assertTrue(exec_hold['admitted'])
        self.rt.cancel(first, reason='test retained ownership after cancellation')
        self.assertEqual(self.rt.acquire(second, backend='exec')['reasons'][0]['reason'], 'live-capacity')
        self.release(exec_hold)
        self.assertTrue(self.rt.acquire(second, backend='exec')['admitted'])
        self.assertEqual(self.rt.status(native)['budget']['used'], 1)

    def test_backend_capacity_includes_legacy_completed_unreleased_attempt(self):
        legacy = self.make_run('exec', None, 1)
        new = self.make_run(capacity=1, pool=True)
        self.nodes(legacy, spec()); self.nodes(new, spec(ordinary_qualified=True))
        p = self.rt.acquire(legacy, backend='exec')
        self.rt.bind(p['attempt'], 'old-worker', backend='exec')
        self.rt.complete(p['attempt'], reply(), external_id='old-worker', backend='exec')
        self.assertFalse(self.rt.acquire(new, backend='exec')['admitted'])
        self.rt.release(p['attempt'], external_id='old-worker', confirmed=True, reason='test old transport ended')
        self.assertTrue(self.rt.acquire(new, backend='exec')['admitted'])

    def test_mixed_scope_retains_legacy_asymmetry(self):
        legacy = self.make_run('native', None, 1)
        pool = self.make_run(capacity=1, pool=True)
        self.nodes(legacy, spec('a'), spec('b')); self.nodes(pool, spec(ordinary_qualified=True))
        first = self.rt.acquire(legacy, backend='native')
        self.assertTrue(self.rt.acquire(pool, backend='exec')['admitted'])
        self.release(first)
        self.assertFalse(self.rt.acquire(legacy, backend='native')['admitted'])

    def test_backend_capacity_keeps_cross_backend_source_writer_locks(self):
        writer = self.make_run('native', implement=True)
        pool = self.make_run(pool=True)
        self.nodes(writer, spec('writer', role='writer', writes=['a.py']),
                   spec('review', role='reviewer', depends=['writer'], verifies='writer'))
        self.nodes(pool, spec('a', ordinary_qualified=True), spec('b', ordinary_qualified=True))
        held = self.rt.acquire(pool, backend='exec')
        self.assertEqual(self.rt.acquire(writer, backend='native')['reasons'][0]['reason'], 'source-writer-lock')
        self.release(held)
        self.assertTrue(self.rt.acquire(writer, backend='native')['admitted'])
        self.assertEqual(self.rt.acquire(pool, backend='exec')['reasons'][0]['reason'], 'source-writer-lock')

    def test_concurrent_backend_admission_cannot_exceed_capacity(self):
        run = self.make_run(capacity=2, pool=True)
        self.nodes(run, *(spec(str(i), ordinary_qualified=True) for i in range(8)))
        def acquire(_):
            with Runtime(self.db) as rt: return rt.acquire(run, backend='exec')['admitted']
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(acquire, range(8))), 2)
        self.assertEqual(self.rt.status(run)['budget']['used'], 2)

    def test_invalid_pool_contracts_and_strong_nodes_are_rejected(self):
        bad = (dict(backend='native'), dict(scope='database'), dict(implement=True),
               dict(bounds={'strong_approved':1}), dict(execution_pool='astra'), dict(capacity_scope='run'))
        for change in bad:
            with self.subTest(change=change), self.assertRaises(WorkflowError): self.make_run(pool=True, **change)
        for tier, key, value in (('ordinary','model','gpt-6-astra'), ('ordinary','effort','high'), ('economy','model','other')):
            routes = json.loads(json.dumps(DEFAULT_ROUTES)); routes[tier][key] = value
            with self.assertRaises(WorkflowError): self.make_run(pool=True, routes=routes)
        run = self.make_run(pool=True)
        for values in (dict(), dict(ordinary_qualified=True, risk='high'),
                       dict(ordinary_qualified=True, role='writer', writes=['a.py']),
                       dict(ordinary_qualified=True, tier='strong')):
            with self.subTest(values=values), self.assertRaises(WorkflowError): self.nodes(run, spec(**values))
        self.assertEqual(self.rt.status(run)['nodes'], [])

    def test_pool_requires_explicit_selection_and_checks_executable_before_admission(self):
        run = self.make_run()
        with self.assertRaises(WorkflowError): execute_pool(self.rt, run, workers=2, executable=sys.executable)
        run = self.make_run(pool=True); self.nodes(run, spec(ordinary_qualified=True))
        with self.assertRaises(WorkflowError): execute_pool(self.rt, run, workers=2, executable=str(self.base/'absent'))
        self.assertEqual(self.rt.status(run)['budget']['used'], 0)

    def test_six_parallel_workers_refill_dependencies_preserve_native_and_usage(self):
        native = self.make_run('native', capacity=1); self.nodes(native, spec())
        self.rt.acquire(native, backend='native')
        run = self.make_run(pool=True)
        self.nodes(run, *(spec(str(i), ordinary_qualified=True) for i in range(6)),
                   spec('after', ordinary_qualified=True, depends=['0','1']),
                   spec('check', role='verifier', ordinary_qualified=True, depends=['after'], verifies='after'))
        barrier = threading.Barrier(6); guard = threading.Lock(); counters = {'active':0, 'max':0}
        def concurrent_transport(argv, cwd, prompt, **kwargs):
            packet = json.loads(prompt.split('Packet:\n', 1)[1])
            self.assertEqual(argv[argv.index('-m')+1], 'gpt-5.6-luna')
            self.assertIn('model_reasoning_effort="max"', argv)
            self.assertIn('--ephemeral', argv); self.assertEqual(argv.count('--disable'), 2)
            self.assertIn('multi_agent', argv); self.assertIn('multi_agent_v2', argv)
            self.assertEqual(argv[argv.index('--sandbox')+1], 'read-only')
            with guard:
                counters['active'] += 1; counters['max'] = max(counters['max'], counters['active'])
            try:
                if packet['node_id'].isdigit(): barrier.wait(timeout=15)
                return self.transport(argv, cwd, prompt, **kwargs)
            finally:
                with guard: counters['active'] -= 1
        result = execute_pool(self.rt, run, workers=6, executable=sys.executable, transport=concurrent_transport)
        self.assertEqual(result['state'], 'drained'); self.assertEqual(counters['max'], 6)
        self.assertEqual(self.rt.finish(run)['status'], 'completed')
        with Runtime(self.db, read_only=True) as rt:
            status = rt.status(run); budget = status['budget']
            self.assertEqual((budget['used'], budget['strong_used'], budget['reserve_used'], budget['execution_holds']), (8,0,0,0))
            self.assertTrue(status['host_resources_released'])
            self.assertEqual(sum(a['usage']['input_tokens'] for a in status['attempts']), 96)
            self.assertEqual(rt.status(native)['budget']['host_resource_holds'], 1)

    def test_exec_one_cannot_bypass_pool_nested_agent_flags(self):
        run = self.make_run(pool=True); self.nodes(run, spec(ordinary_qualified=True))
        def check(argv, *args, **kwargs):
            self.assertIn('--ephemeral', argv); self.assertEqual(argv.count('--disable'), 2)
            return self.transport(argv, *args, **kwargs)
        self.assertEqual(execute_one(self.rt, run, executable=sys.executable, transport=check)['state'], 'completed')

    def test_malformed_result_is_released_without_retry_and_finish_fails(self):
        run = self.make_run(pool=True)
        self.nodes(run, spec('bad', ordinary_qualified=True, required=False), spec('good', ordinary_qualified=True))
        def one_bad(argv, cwd, prompt, **kwargs):
            result = self.transport(argv, cwd, prompt, **kwargs)
            if '"id":"bad"' in prompt: result.stdout = 'malformed'
            return result
        result = execute_pool(self.rt, run, workers=2, executable=sys.executable, transport=one_bad)
        self.assertEqual(result['state'], 'incomplete')
        self.assertEqual(result['status']['budget']['used'], 2)
        self.assertTrue(result['status']['host_resources_released'])
        self.assertEqual([n['state'] for n in result['status']['nodes']], ['failed','completed'])
        with self.assertRaises(WorkflowError): self.rt.finish(run)

    def test_transport_uncertainty_remains_held_across_reopen(self):
        run = self.make_run(pool=True); self.nodes(run, spec(ordinary_qualified=True))
        def lost(argv, cwd, prompt, **kwargs):
            kwargs['on_started']('lost-worker'); raise OSError('injected lost transport')
        result = execute_pool(self.rt, run, workers=2, executable=sys.executable, transport=lost)
        self.assertEqual(result['state'], 'incomplete')
        with Runtime(self.db, read_only=True) as rt:
            budget = rt.status(run)['budget']
            self.assertEqual((budget['used'], budget['execution_holds']), (1,1))
            self.assertEqual(rt.status(run)['attempts'][0]['external_id'], 'lost-worker')

    def test_cancel_stops_dispatch_and_reconciles_only_owned_transports(self):
        run = self.make_run(pool=True)
        self.nodes(run, *(spec(str(i), ordinary_qualified=True) for i in range(5)))
        barrier = threading.Barrier(3)
        def cancelled(argv, cwd, prompt, **kwargs):
            packet = json.loads(prompt.split('Packet:\n', 1)[1]); pid = 'cancel-'+packet['attempt']
            kwargs['on_started'](pid)
            if barrier.wait(timeout=15) == 0:
                with Runtime(self.db) as rt: rt.cancel(run, reason='test external cancellation')
            until = time.monotonic()+10
            while not kwargs['cancelled']():
                if time.monotonic() > until: raise AssertionError('cancellation not observed')
                time.sleep(.01)
            return ProcessResult(pid, 130, '', '', True)
        result = execute_pool(self.rt, run, workers=3, executable=sys.executable, transport=cancelled)
        self.assertEqual(result['state'], 'incomplete'); self.assertEqual(result['status']['status'], 'cancelled')
        self.assertEqual(result['status']['budget']['used'], 3)
        self.assertEqual(result['status']['budget']['execution_holds'], 0)
        self.assertEqual([n['state'] for n in result['status']['nodes']], ['interrupted']*3+['cancelled']*2)

    def test_submit_failure_after_enqueue_never_launches_or_claims_success(self):
        run = self.make_run(pool=True); self.nodes(run, spec(ordinary_qualified=True))
        class FailAfterEnqueue(concurrent.futures.ThreadPoolExecutor):
            def submit(self, *args, **kwargs):
                super().submit(*args, **kwargs)
                raise RuntimeError('injected failure after enqueue')
        with patch('cwf_runtime.luna_pool.ThreadPoolExecutor', FailAfterEnqueue), patch('cwf_runtime.luna_pool._execute_admitted') as launch:
            with self.assertRaisesRegex(RuntimeError, 'after enqueue'):
                execute_pool(self.rt, run, workers=2, executable=sys.executable)
            launch.assert_not_called()
        status = self.rt.status(run)
        self.assertEqual(status['status'], 'cancelled'); self.assertTrue(status['host_resources_released'])
        self.assertEqual(status['budget']['used'], 1); self.assertFalse(status['scope_complete'])

    def test_controller_interrupt_cancels_and_waits_for_worker_cleanup(self):
        run = self.make_run(pool=True); self.nodes(run, spec(ordinary_qualified=True))
        started = threading.Event()
        def transport(argv, cwd, prompt, **kwargs):
            kwargs['on_started']('interrupted-worker'); started.set()
            until = time.monotonic()+10
            while not kwargs['cancelled']():
                if time.monotonic() > until: raise AssertionError('worker did not see controller cancellation')
                time.sleep(.01)
            return ProcessResult('interrupted-worker', 130, '', '', True)
        def interrupt(*args, **kwargs):
            self.assertTrue(started.wait(15)); raise KeyboardInterrupt()
        with patch('cwf_runtime.luna_pool.wait', interrupt), self.assertRaises(KeyboardInterrupt):
            execute_pool(self.rt, run, workers=1, executable=sys.executable, transport=transport)
        self.assertEqual(self.rt.status(run)['budget']['execution_holds'], 0)
        self.assertEqual(self.rt.status(run)['status'], 'cancelled')

    def test_six_real_owned_processes_overlap_and_reconcile(self):
        run = self.make_run(pool=True)
        self.nodes(run, *(spec(str(i), ordinary_qualified=True) for i in range(6)))
        markers = self.base/'markers'; markers.mkdir()
        emitter = self.base/'emitter.py'
        emitter.write_text('import os,sys,time\nfrom pathlib import Path\n'
                           'root=Path(sys.argv[1]); (root/str(os.getpid())).write_text("started")\n'
                           'end=time.monotonic()+15\n'
                           'while len(list(root.iterdir()))<6:\n'
                           '    if time.monotonic()>end: raise RuntimeError("six processes did not overlap")\n'
                           '    time.sleep(.02)\n'
                           'print('+repr(stream())+')\n', encoding='utf-8')
        def real(argv, cwd, prompt, **kwargs):
            return run_owned([sys.executable,'-B',str(emitter),str(markers)], cwd, '', **kwargs)
        result = execute_pool(self.rt, run, workers=6, executable=sys.executable, transport=real, timeout=25)
        self.assertEqual(result['state'], 'drained')
        self.assertEqual(len(list(markers.iterdir())), 6)
        self.assertEqual(len({a['external_id'] for a in result['status']['attempts']}), 6)
        self.assertTrue(result['status']['host_resources_released'])
        self.assertEqual(self.rt.finish(run)['status'], 'completed')


if __name__ == '__main__': unittest.main()
