"""Offline-review candidate for the task-local native acceptance collector.

No process creation, model calls, file access, or Runtime writes. The caller must
supply host notifications and an RPC function returning decoded result objects.
This is not a replacement live runner or evidence of native acceptance.
"""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
import math
import time
from typing import Callable


@dataclass
class Actor:
    parent_id: str | None = None
    lineage_conflict: bool = False
    turns: dict = field(default_factory=dict)
    items: dict = field(default_factory=dict)
    metadata: list = field(default_factory=list)
    settings: list = field(default_factory=list)
    unsubscribe: list = field(default_factory=list)
    closed: bool = False
    status: dict | None = None
    generation: int = 0
    awaiting_turn: bool = True


class Collector:
    """Keep observed IDs separate from host-evidenced owned descendants.

    Limits detect overruns; they do not authorize or prevent native dispatch.
    Unknown observations block global settlement but never authorize a mutation.
    """

    def __init__(self, parent: str, *, max_children: int = 5, max_turns: int = 6):
        if not isinstance(parent, str) or not parent:
            raise ValueError('parent must be an actual nonempty thread ID')
        if type(max_children) is not int or max_children < 0:
            raise ValueError('max_children must be a nonnegative integer')
        if type(max_turns) is not int or max_turns < 1:
            raise ValueError('max_turns must be a positive integer')
        self.parent = parent
        self.max_children = max_children
        self.max_turns = max_turns
        self.actors = {parent: Actor()}
        self.events = []
        self.errors = []
        self.faults = []
        self._metadata_queue = deque([parent])

    def _actor(self, tid: str) -> Actor:
        if not isinstance(tid, str) or not tid:
            raise ValueError('missing or invalid thread ID')
        if tid not in self.actors:
            self.actors[tid] = Actor()
            self._metadata_queue.append(tid)
        return self.actors[tid]

    def _lineage(self, tid: str, meta: dict) -> None:
        actor = self._actor(tid)
        parent = meta.get('parentThreadId')
        if parent is None:
            return  # Missing evidence never becomes the expected parent.
        if not isinstance(parent, str) or not parent or parent == tid:
            actor.lineage_conflict = True
        elif actor.parent_id is not None and actor.parent_id != parent:
            actor.lineage_conflict = True
        else:
            actor.parent_id = parent

    def _status(self, actor: Actor, status: dict) -> None:
        if not isinstance(status, dict):
            self.faults.append("invalid host thread status")
            return
        actor.status = deepcopy(status)
        if status.get("type") == "active":
            actor.closed = False
            actor.generation += 1

    def owned_ids(self) -> set[str]:
        owned = {self.parent} if not self.actors[self.parent].lineage_conflict else set()
        while True:
            additional = {tid for tid, actor in self.actors.items()
                          if not actor.lineage_conflict and actor.parent_id in owned}
            if additional <= owned:
                return owned
            owned.update(additional)

    @property
    def stop_required(self) -> bool:
        turns = sum(len(actor.turns) for actor in self.actors.values())
        return bool(self.faults or any(a.lineage_conflict for a in self.actors.values())
                    or len(self.owned_ids() - {self.parent}) > self.max_children
                    or turns > self.max_turns)

    def observe(self, message: dict, observed_at: float) -> None:
        """Journal before interpretation; retain subsequent events after errors."""
        self.events.append({'observed_at': observed_at, 'message': deepcopy(message)})
        try:
            if not isinstance(message, dict):
                raise ValueError('host message is not an object')
            method = message.get('method', '')
            if 'id' in message and method:
                raise ValueError('host user handling required; never auto-approve')
            params = message.get('params', {})
            if not isinstance(params, dict):
                raise ValueError('event params are not an object')
            meta = params.get('thread', {}) if method == 'thread/started' else {}
            tid = meta.get('id') if method == 'thread/started' else params.get('threadId')
            if tid is None:
                if method.startswith(('thread/', 'turn/', 'item/')):
                    raise ValueError('lifecycle event lacks a thread ID')
                return
            actor = self._actor(tid)
            if method == 'thread/started':
                self._lineage(tid, meta)
                actor.closed = False
                actor.generation += 1
                actor.awaiting_turn = True
            elif method in ('turn/started', 'turn/completed'):
                turn = params['turn']
                turn_id = turn.get('id')
                if not isinstance(turn_id, str) or not turn_id:
                    raise ValueError('turn event lacks a turn ID')
                if turn_id not in actor.turns:
                    actor.generation += 1
                    actor.closed = False
                actor.awaiting_turn = False
                actor.turns[turn_id] = {
                    'raw': deepcopy(turn), 'event': method, 'observed_at': observed_at,
                    'terminal': method == 'turn/completed' and turn.get('status') in
                    ('completed', 'failed', 'interrupted')}
                if method == 'turn/started':
                    actor.closed = False
            elif method in ('item/started', 'item/completed'):
                item = params['item']
                turn_id, item_id = params.get('turnId'), item.get('id')
                if not all(isinstance(v, str) and v for v in (turn_id, item_id)):
                    raise ValueError('item event lacks exact turn/item identity')
                actor.items[(turn_id, item_id)] = {
                    'raw': deepcopy(item), 'event': method, 'observed_at': observed_at}
            elif method == 'thread/settings/updated':
                actor.settings.append(deepcopy(params))
            elif method == 'thread/status/changed':
                self._status(actor, params.get('status'))
            elif method == 'thread/closed':
                actor.closed = True
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            self.faults.append(str(error))

    def record_metadata(self, tid: str, meta: dict) -> None:
        if not isinstance(meta, dict) or meta.get('id') != tid:
            raise ValueError('metadata identity does not match requested thread')
        actor = self._actor(tid)
        actor.metadata.append(deepcopy(meta))
        self._lineage(tid, meta)
        if 'status' in meta:
            self._status(actor, meta['status'])

    def execution_complete(self, tid: str) -> bool:
        """Lifecycle only, NOT quality acceptance, identity, or resource release."""
        actor = self.actors.get(tid)
        if self.faults or actor is None or actor.lineage_conflict or not actor.turns or actor.awaiting_turn:
            return False
        if actor.status is not None and actor.status.get('type') not in ('idle', 'notLoaded'):
            return False
        if not all(turn['terminal'] for turn in actor.turns.values()):
            return False
        return all(item['event'] == 'item/completed' and turn_id in actor.turns
                   and ('status' not in item['raw'] or item['raw']['status'] in
                        ('completed', 'failed', 'interrupted', 'declined', 'cancelled', 'canceled'))
                   for (turn_id, _), item in actor.items.items())

    def all_executions_complete(self) -> bool:
        return (not self.stop_required and self.owned_ids() == set(self.actors)
                and all(self.execution_complete(tid) for tid in self.actors))

    @staticmethod
    def _timeout(deadline: float, per_rpc_timeout: float, clock: Callable) -> float:
        if not math.isfinite(deadline) or not math.isfinite(per_rpc_timeout) or per_rpc_timeout <= 0:
            raise ValueError('finite deadline and positive finite RPC timeout required')
        return min(per_rpc_timeout, max(0.0, deadline - clock()))

    def metadata_step(self, rpc: Callable, *, deadline: float,
                      per_rpc_timeout: float = 0.25, clock: Callable = time.monotonic) -> str | None:
        """At most ONE bounded read per tick, after urgent Runtime owner work.

        rpc must honor timeout and return the decoded result, or raise. This
        helper cannot preempt a blocking/misbehaving transport implementation.
        """
        timeout = self._timeout(deadline, per_rpc_timeout, clock)
        if timeout <= 0:
            return None
        tid = self._metadata_queue.popleft()
        self._metadata_queue.append(tid)
        try:
            result = rpc('thread/read', {'threadId': tid, 'includeTurns': False}, timeout=timeout)
            self.record_metadata(tid, result['thread'])
        except Exception as error:
            self.errors.append({'operation': 'thread/read', 'thread_id': tid, 'error': str(error)})
        return tid

    def unsubscribe_settled(self, rpc: Callable, *, deadline: float,
                            per_rpc_timeout: float = 0.25, clock: Callable = time.monotonic) -> None:
        """One best-effort pass; no interrupts, archives, deletes or ledger writes.

        Failed reads are not a precondition for this pass. Missing identity stays
        missing; a successful unsubscribe is NOT proof of host slot recycling.
        """
        for tid in sorted(self.owned_ids() - {self.parent}) + [self.parent]:
            if tid not in self.owned_ids() or not self.execution_complete(tid):
                continue
            timeout = self._timeout(deadline, per_rpc_timeout, clock)
            if timeout <= 0:
                self.errors.append({'operation': 'thread/unsubscribe', 'thread_id': tid,
                                    'error': 'cleanup deadline reached; no receipt'})
                continue
            try:
                generation = self.actors[tid].generation
                result = rpc('thread/unsubscribe', {'threadId': tid}, timeout=timeout)
                if not isinstance(result, dict):
                    raise ValueError('unsubscribe result is not an object')
                self.actors[tid].unsubscribe.append({
                    'generation': generation, 'result': deepcopy(result)})
                if result.get('status') not in ('unsubscribed', 'notSubscribed', 'notLoaded'):
                    raise ValueError('unsubscribe status is unknown')
            except Exception as error:
                self.errors.append({'operation': 'thread/unsubscribe', 'thread_id': tid,
                                    'error': str(error)})

    def resource_observation(self, tid: str) -> str:
        actor = self.actors.get(tid)
        if actor is None:
            return 'UNKNOWN'
        if actor.closed:
            return 'THREAD_CLOSED_OBSERVED'
        receipt = actor.unsubscribe[-1] if actor.unsubscribe else {}
        status = (receipt.get('result', {}).get('status')
                  if receipt.get('generation') == actor.generation else None)
        if not isinstance(status, str):
            return 'UNKNOWN'
        return {'unsubscribed': 'UNSUBSCRIBED_ONLY', 'notSubscribed': 'NOT_SUBSCRIBED_ONLY',
                'notLoaded': 'NOT_LOADED_REPORTED'}.get(status, 'UNKNOWN')
