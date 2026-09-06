"""Finite readonly Luna execution pool; native agents use their own host capacity."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Event

from .core import Runtime, WorkflowError, integer
from .executor import _execute_admitted, codex_prefix, run_owned


def execute_pool(runtime, run, *, workers, executable=None, transport=run_owned, timeout=600):
    _, contract = runtime.open_run(run)
    if contract.get('execution_pool') != 'luna':
        raise WorkflowError('luna-pool requires an explicit immutable execution_pool=luna run')
    integer(workers, 'workers', 1, contract['bounds']['max_nodes'])
    integer(timeout, 'timeout', 1, 86400)
    prefix = codex_prefix(executable)  # Fail before any admission or allowance charge.
    results = []; inflight = {}; deferred = []

    def execute(packet, gate):
        gate['ready'].wait()
        if not gate['launch']:
            return {'admitted':True, 'attempt':packet['attempt'], 'state':'interrupted'}
        # SQLite connections are thread-affine; admissions stay with the controller.
        with Runtime(runtime.path) as worker:
            return _execute_admitted(worker, packet, prefix=prefix, transport=transport, timeout=timeout)

    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='cwf-luna')
    try:
        while True:
            while len(inflight) < workers and runtime.run(run)['status'] == 'open':
                packet = runtime.acquire(run, backend='exec')
                if not packet['admitted']:
                    deferred = packet['reasons']
                    break
                gate = {'ready':Event(), 'launch':False}
                try:
                    future = pool.submit(execute, packet, gate)
                    inflight[future] = packet['attempt']
                    gate['launch'] = True
                except BaseException:
                    # submit may enqueue before thread creation fails. Its callable
                    # must pass this gate before it can open a DB or launch a process.
                    gate['launch'] = False
                    runtime.release(packet['attempt'], external_id=None, confirmed=True,
                                    reason='pool submission failed before a worker was launched')
                    raise
                finally:
                    gate['ready'].set()
            if not inflight:
                break  # Quiescent, not automatic retry/resume or a background daemon.
            completed = set()
            while not completed:
                completed, _ = wait(inflight, timeout=0.25, return_when=FIRST_COMPLETED)
            for future in completed:
                token = inflight.pop(future)
                try:
                    results.append(future.result())
                except Exception as exc:
                    # Unknown transport ownership remains held by the existing adapter.
                    results.append({'admitted':True, 'attempt':token, 'state':'error', 'error':str(exc)})
    except BaseException:
        if runtime.run(run)['status'] == 'open':
            runtime.cancel(run, reason='Luna pool controller interrupted or failed')
        raise
    finally:
        # Running owned transports observe cancellation and reconcile their own trees.
        pool.shutdown(wait=True)
    status = runtime.status(run)
    drained = (status['scope_complete'] and status['current_evidence_valid']
               and not status['budget']['execution_holds']
               and all(r.get('state') == 'completed' for r in results))
    return {'state':'drained' if drained else 'incomplete', 'results':results,
            'deferred':deferred, 'status':status}
