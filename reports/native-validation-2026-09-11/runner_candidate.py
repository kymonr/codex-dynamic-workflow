"""Task-local native acceptance runner candidate with zero-model integration support.

The module contains no Codex command, model name, network client, or Runtime ledger
write. A caller must inject the subprocess command and explicit start parameters.
Zero-model tests use a synthetic JSON-RPC host process; those tests are not native
model acceptance evidence.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Callable, Iterable

from collector_candidate import Collector


class RpcProtocolError(RuntimeError):
    pass


class EvidenceJournal:
    """Append-only task evidence; existing output directories are never reused."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.timeline = (self.root / 'timeline.jsonl').open('x', encoding='utf-8')
        self.finalized = False

    def append(self, kind: str, payload: dict) -> None:
        self.timeline.write(json.dumps({'kind': kind, 'payload': payload},
                                       ensure_ascii=False) + '\n')
        self.timeline.flush()

    def finalize(self, summary: dict) -> Path:
        if self.finalized:
            raise RuntimeError('evidence journal is already finalized')
        path = self.root / 'summary.json'
        with path.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        self.finalized = True
        return path

    def close(self) -> None:
        if not self.timeline.closed:
            self.timeline.close()


class SubprocessJsonRpcHost:
    """Line-delimited JSON-RPC transport around an explicitly supplied process."""

    def __init__(self, command: list[str], *, cwd=None, env=None):
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError('command must be a nonempty list of nonempty strings')
        self.command = tuple(command)
        self.process = subprocess.Popen(
            command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', bufsize=1,
        )
        self.inbox = queue.Queue()
        self.events: list[tuple[float, dict]] = []
        self.pending: dict[int, dict] = {}
        self.stderr_lines: list[str] = []
        self.sequence = 0
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.reader.start(); self.stderr_reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                self.inbox.put(json.loads(line))
            except ValueError:
                self.inbox.put({'client_error': 'non-JSON host output', 'raw': line.rstrip('\n')})
        self.inbox.put({'client_eof': True})

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr_lines.append(line.rstrip('\n'))
            if len(self.stderr_lines) > 100:
                del self.stderr_lines[:-100]

    def send(self, message: dict) -> None:
        if self.process.stdin is None or self.process.stdin.closed:
            raise RuntimeError('host stdin is closed')
        self.process.stdin.write(json.dumps(message, ensure_ascii=True) + '\n')
        self.process.stdin.flush()

    def poll(self) -> int:
        count = 0
        while True:
            try:
                message = self.inbox.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, dict) and 'id' in message and ('result' in message or 'error' in message):
                self.pending[message['id']] = message
            else:
                self.events.append((time.time(), message))
            count += 1
        return count

    def call(self, method: str, params: dict, *, timeout: float) -> dict:
        if timeout <= 0:
            raise TimeoutError('host request deadline already expired: ' + method)
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.poll()
            if request_id in self.pending:
                return self.pending.pop(request_id)
            if self.process.poll() is not None:
                raise RuntimeError('host process exited: ' + str(self.process.returncode))
            time.sleep(0.005)
        raise TimeoutError('host request timed out: ' + method)

    def close(self, *, timeout: float = 2.0):
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            result = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return 'UNKNOWN'
        self.reader.join(timeout=0.2); self.stderr_reader.join(timeout=0.2)
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        return result


class NativeAcceptanceRunner:
    """Bounded observer runner; metadata work is always lower priority than controls."""

    def __init__(self, host: SubprocessJsonRpcHost, *, max_children: int = 5,
                 max_turns: int = 6, clock: Callable = time.monotonic,
                 journal: EvidenceJournal | None = None):
        self.host = host
        self.journal = journal
        self.max_children = max_children
        self.max_turns = max_turns
        self.clock = clock
        self.parent: str | None = None
        self.parent_turn_id: str | None = None
        self.start_receipt: dict | None = None
        self.collector: Collector | None = None
        self.status = 'NEW'
        self.stop_requested = False
        self.control_failed = False
        self.host_faults: list[str] = []
        self.rpc_log: list[dict] = []
        self.control_log: list[dict] = []
        self.event_log: list[dict] = []

    @staticmethod
    def _bounded_timeout(deadline: float, cap: float, clock: Callable) -> float:
        return min(cap, max(0.0, deadline - clock()))

    def rpc(self, method: str, params: dict, *, timeout: float) -> dict:
        started = self.clock()
        try:
            response = self.host.call(method, params, timeout=timeout)
        except Exception as error:
            entry = {'method': method, 'params': deepcopy(params),
                     'elapsed': self.clock() - started, 'error': None,
                     'transport_error': f'{type(error).__name__}: {error}'}
            self.rpc_log.append(entry)
            if self.journal is not None:
                self.journal.append('rpc', deepcopy(entry))
            raise
        entry = {'method': method, 'params': deepcopy(params),
                 'elapsed': self.clock() - started, 'error': response.get('error'),
                 'transport_error': None}
        self.rpc_log.append(entry)
        if self.journal is not None:
            self.journal.append('rpc', deepcopy(entry))
        if 'error' in response:
            raise RpcProtocolError(f'{method}: {response["error"]}')
        result = response.get('result', {})
        if not isinstance(result, dict):
            raise RpcProtocolError(method + ': result is not an object')
        return result

    def start(self, *, thread_params: dict, turn_input: str,
              rpc_timeout: float = 2.0, require_read_only: bool = True) -> dict:
        if self.status != 'NEW':
            raise RuntimeError('runner start is single-use')
        self.status = 'STARTING'
        try:
            self.rpc('initialize', {'clientInfo': {'name': 'cwf_zero_model_runner_candidate', 'version': '1'},
                                    'capabilities': {'experimentalApi': True}}, timeout=rpc_timeout)
            self.host.send({'method': 'initialized'})
            started = self.rpc('thread/start', deepcopy(thread_params), timeout=rpc_timeout)
            thread = started.get('thread', {})
            parent = thread.get('id')
            if not isinstance(parent, str) or not parent:
                raise RpcProtocolError('thread/start did not return a thread id')
            if require_read_only and started.get('sandbox', {}).get('type') != 'readOnly':
                raise RpcProtocolError('requested read-only permission did not take effect')
            self.parent = parent
            self.collector = Collector(parent, max_children=self.max_children, max_turns=self.max_turns)
            turn = self.rpc('turn/start', {'threadId': parent,
                                           'input': [{'type': 'text', 'text': turn_input}]}, timeout=rpc_timeout)
            turn_data = turn.get('turn', {})
            turn_id = turn_data.get('id')
            if not isinstance(turn_id, str) or not turn_id:
                raise RpcProtocolError('turn/start did not return a turn id')
            self.parent_turn_id = turn_id
            self.status = 'RUNNING'
            self.start_receipt = {
                'thread': deepcopy(thread), 'turn': deepcopy(turn_data),
                'effective_start': {k: deepcopy(started.get(k)) for k in
                                    ('model', 'reasoningEffort', 'approvalPolicy',
                                     'sandbox', 'activePermissionProfile')},
            }
            return deepcopy(self.start_receipt)
        except Exception:
            self.status = 'FAILED_START'
            raise

    def drain(self) -> int:
        if self.collector is None:
            raise RuntimeError('runner is not started')
        self.host.poll()
        pending, self.host.events = self.host.events, []
        for observed_at, message in pending:
            event = {'observed_at': observed_at, 'message': deepcopy(message)}
            self.event_log.append(event)
            if self.journal is not None:
                self.journal.append('event', deepcopy(event))
            if isinstance(message, dict) and message.get('client_error'):
                self.host_faults.append(str(message['client_error']))
                continue
            if isinstance(message, dict) and message.get('client_eof'):
                self.host_faults.append('host stdout closed unexpectedly')
                continue
            self.collector.observe(message, observed_at)
        return len(pending)

    def apply_controls(self, controls: Iterable[dict], *, deadline: float) -> None:
        if self.parent is None or self.parent_turn_id is None:
            raise RuntimeError('runner is not started')
        for command in controls:
            reply = {'command': deepcopy(command)}
            try:
                if not isinstance(command, dict):
                    raise ValueError('control must be an object')
                op = command.get('op')
                if op == 'steer':
                    text = command.get('text')
                    if not isinstance(text, str) or not text:
                        raise ValueError('steer control requires nonempty text')
                    timeout = self._bounded_timeout(deadline, 0.5, self.clock)
                    if timeout <= 0:
                        raise TimeoutError('control deadline reached before steer')
                    reply['result'] = self.rpc(
                        'turn/steer',
                        {'threadId': self.parent, 'expectedTurnId': self.parent_turn_id,
                         'input': [{'type': 'text', 'text': text}]}, timeout=timeout)
                elif op == 'stop':
                    self.stop_requested = True
                    reply['result'] = {'stopping': True}
                elif op == 'metadata':
                    reply['result'] = {'scheduled': True}
                else:
                    raise ValueError('unsupported control operation')
            except Exception as error:
                reply['error'] = f'{type(error).__name__}: {error}'
                self.control_failed = True
            self.control_log.append(reply)
            if self.journal is not None:
                self.journal.append('control', deepcopy(reply))
            if self.control_failed or self.stop_requested:
                break

    def metadata_captured(self) -> bool:
        if self.collector is None:
            return False
        owned = self.collector.owned_ids()
        return (owned == set(self.collector.actors)
                and all(self.collector.actors[tid].metadata for tid in owned))

    def tick(self, controls: Iterable[dict], *, deadline: float,
             metadata_rpc_timeout: float = 0.25) -> None:
        if self.collector is None:
            raise RuntimeError('runner is not started')
        self.drain()
        self.apply_controls(controls, deadline=deadline)
        self.drain()  # Host events caused by urgent controls are visible before metadata.
        if (not self.stop_requested and not self.control_failed and not self.host_faults
                and self.clock() < deadline):
            self.collector.metadata_step(self.rpc, deadline=deadline,
                                         per_rpc_timeout=metadata_rpc_timeout,
                                         clock=self.clock)
        self.drain()

    def run(self, control_provider: Callable[['NativeAcceptanceRunner'], Iterable[dict]],
            *, deadline: float, poll_interval: float = 0.01,
            metadata_rpc_timeout: float = 0.25) -> str:
        if self.collector is None:
            raise RuntimeError('runner is not started')
        while self.clock() < deadline:
            # Drain first so required controls can react to newly completed mainline work
            # before any optional metadata RPC is allowed to consume the next slot.
            self.drain()
            if self.host_faults:
                self.status = 'BLOCKED_BY_HOST'
                return self.status
            if self.collector.stop_required:
                self.status = 'BLOCKED_BY_OBSERVATION'
                return self.status
            controls = list(control_provider(self))
            self.tick(controls, deadline=deadline, metadata_rpc_timeout=metadata_rpc_timeout)
            if self.host_faults:
                self.status = 'BLOCKED_BY_HOST'
                return self.status
            if self.control_failed:
                self.status = 'BLOCKED_BY_CONTROL'
                return self.status
            if self.collector.stop_required:
                self.status = 'BLOCKED_BY_OBSERVATION'
                return self.status
            if self.stop_requested:
                self.status = 'STOPPED_AT_BOUNDARY'
                return self.status
            if self.collector.all_executions_complete() and self.metadata_captured():
                self.status = 'OBSERVED'
                return self.status
            time.sleep(poll_interval)
        self.status = 'TIMEOUT'
        return self.status

    def cleanup(self, *, deadline: float, per_rpc_timeout: float = 0.25) -> None:
        if self.collector is None:
            raise RuntimeError('runner is not started')
        self.drain()
        self.collector.unsubscribe_settled(self.rpc, deadline=deadline,
                                           per_rpc_timeout=per_rpc_timeout,
                                           clock=self.clock)
        idle_polls = 0
        while self.clock() < deadline and idle_polls < 2:
            if self.drain():
                idle_polls = 0
            else:
                idle_polls += 1
                time.sleep(0.01)

    def finalize_evidence(self) -> dict:
        summary = self.summary()
        if self.journal is not None:
            self.journal.finalize(deepcopy(summary))
        return summary

    def summary(self) -> dict:
        if self.collector is None:
            raise RuntimeError('runner is not started')
        actors = {}
        for tid, actor in self.collector.actors.items():
            actors[tid] = {
                'parent_id': actor.parent_id,
                'lineage_conflict': actor.lineage_conflict,
                'turn_ids': sorted(actor.turns),
                'item_ids': sorted(f'{turn_id}:{item_id}' for turn_id, item_id in actor.items),
                'metadata_count': len(actor.metadata),
                'metadata': deepcopy(actor.metadata),
                'settings_count': len(actor.settings),
                'settings': deepcopy(actor.settings),
                'unsubscribe': deepcopy(actor.unsubscribe),
                'closed': actor.closed,
                'status': deepcopy(actor.status),
                'resource_observation': self.collector.resource_observation(tid),
            }
        return {
            'status': self.status,
            'parent': self.parent,
            'parent_turn_id': self.parent_turn_id,
            'start_receipt': deepcopy(self.start_receipt),
            'owned_ids': sorted(self.collector.owned_ids()),
            'observed_ids': sorted(self.collector.actors),
            'metadata_captured': self.metadata_captured(),
            'identity_validation': 'NOT_PERFORMED',
            'acceptance': 'NOT_EVALUATED',
            'host_resource_recycling': 'NOT_PROVEN',
            'executions_complete': self.collector.all_executions_complete(),
            'collector_faults': list(self.collector.faults),
            'collector_errors': deepcopy(self.collector.errors),
            'host_faults': list(self.host_faults),
            'control_failed': self.control_failed,
            'rpc': deepcopy(self.rpc_log),
            'controls': deepcopy(self.control_log),
            'event_count': len(self.event_log),
            'actors': actors,
            'host_stderr': list(self.host.stderr_lines),
        }
