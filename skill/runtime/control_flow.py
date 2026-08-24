"""Trusted Workflow IR v3 control-flow scheduler.

This module executes declarative, read-only ``agent``, ``map``, ``verify``,
``reduce``, ``conditional`` and ``human_gate`` nodes. It never evaluates
model-authored Python, JavaScript, shell, path expressions, or arbitrary
selectors. Dynamic expansion and decisions are finite, deterministic,
budgeted, artifact-backed, and checkpointed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Awaitable, Callable

from .artifacts import (
    ArtifactStore,
    canonical_json_bytes,
    choose_public_output,
    is_artifact_reference,
)
from .condition import evaluate_condition
from .deadline import DeadlineClock, SystemDeadlineClock, checked_epoch_ms
from .human_gate import (
    HumanGateError,
    HumanGateStore,
    compute_gate_input_identity,
)
from .limits import (
    ArtifactLimitError,
    RuntimeLimits,
    enforce_projected_write,
    enforce_run_limit,
)
from .path_safety import (
    UnsafeRunPathError,
    assert_safe_descendant,
    assert_safe_run_tree,
)
from .run_lease import RunLease, RunLeaseError
from .state_store import RunStateStore, now_iso
from .workflow_ir import (
    DEFAULT_DEPENDENCY_POLICY,
    EXECUTABLE_NODE_KINDS,
    JOIN_DEPENDENCY_POLICY,
    TIMEOUT_SCOPE,
    TOKEN_BUDGET_MODE,
    VERIFICATION_RESULT_SCHEMA,
    bounded_loop_child_id,
    bounded_loop_state_id,
    executable_bounded_loops,
    project_agent_claims,
    validate_workflow_ir,
)

AgentExecutor = Callable[
    [dict[str, Any], dict[str, Any], dict[str, Any] | None],
    Awaitable[dict[str, Any]],
]

SUCCESS = "succeeded"
SKIPPED = "skipped"
WAITING = "waiting"
TERMINAL_STATES = {
    SUCCESS,
    SKIPPED,
    "failed",
    "blocked",
    "cancelled",
    "needs_escalation",
}
DEPENDENCY_FAILURE_STATES = {
    "failed",
    "blocked",
    "cancelled",
    "needs_escalation",
}
SIMPLE_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_-]*)\}\}")
RESERVED_PLACEHOLDERS = {
    "item",
    "index",
    "source",
    "candidate",
    "manifest",
}
LOOP_TEMPLATE_SKIP_REASON = "executed_as_bounded_loop_template"


class ControlFlowError(RuntimeError):
    """The trusted control-flow runtime cannot safely continue."""


class AgentBudgetError(ControlFlowError):
    """Dynamic expansion exceeded the workflow's explicit agent budget."""


def _strict_resume_count(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ControlFlowError(f"{where} resume_count must be a non-negative integer")
    return value


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _child_agent_id(parent: str, phase: str, index: int) -> str:
    """Return a deterministic v2-compatible task id of at most 40 characters."""

    safe_parent = re.sub(r"[^A-Za-z0-9_-]", "_", parent)[:16]
    digest = hashlib.sha256(
        f"{parent}:{phase}:{index}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{safe_parent}_{phase}_{index:04d}_{digest}"[:40]


def _input_id(parent: str, phase: str, index: int) -> str:
    return _child_agent_id(parent, f"{phase}in", index)


def _entry_record(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "output": entry.get("output"),
        "artifact": entry.get("output_artifact"),
    }


def _render_prompt(template: str, replacements: dict[str, str]) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    leftovers = {
        match.group(1)
        for match in SIMPLE_PLACEHOLDER_RE.finditer(rendered)
    }
    if leftovers:
        raise ControlFlowError(
            "unresolved trusted placeholders: " + ", ".join(sorted(leftovers))
        )
    return rendered


def _bounded_json_write(
    path: Path,
    value: Any,
    *,
    run_dir: Path,
    limits: RuntimeLimits,
    label: str,
) -> None:
    assert_safe_descendant(run_dir, path, label=label)
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    enforce_projected_write(
        run_dir,
        path,
        len(payload),
        limits.max_run_artifact_bytes,
        label,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_descendant(run_dir, path, label=label)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    assert_safe_descendant(run_dir, temporary, label=f"{label} temporary")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    enforce_run_limit(run_dir, limits.max_run_artifact_bytes)


def _base_node_entry(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node["id"],
        "kind": node["kind"],
        "status": "pending",
        "depends_on": list(node["depends_on"]),
        "dependency_policy": node.get(
            "dependency_policy", DEFAULT_DEPENDENCY_POLICY
        ),
        "started": None,
        "finished": None,
        "output": None,
        "output_artifact": None,
        "error": None,
        "children": {},
        "condition_outcome": None,
        "gate": None,
        "resume_count": 0,
    }


def _normalize_agent_entry(
    agent_id: str,
    entry: dict[str, Any],
    *,
    store: ArtifactStore,
    limits: RuntimeLimits,
) -> dict[str, Any]:
    normalized = json.loads(json.dumps(entry, ensure_ascii=False))
    normalized.setdefault("id", agent_id)
    if normalized.get("id") != agent_id:
        raise ControlFlowError(
            f"agent entry identity mismatch: expected={agent_id!r} "
            f"actual={normalized.get('id')!r}"
        )
    if "resume_count" in normalized:
        _strict_resume_count(normalized["resume_count"], f"agent {agent_id}")
    normalized.setdefault("status", "failed")
    normalized.setdefault("error", None)
    normalized.setdefault("output", None)
    normalized.setdefault("output_artifact", None)
    if normalized["status"] != SUCCESS:
        return normalized

    reference = normalized.get("output_artifact")
    if reference is not None:
        if not is_artifact_reference(reference):
            raise ControlFlowError(
                f"agent {agent_id} returned an invalid artifact reference"
            )
        store.resolve_reference(reference, expected_task_id=agent_id)
    else:
        reference = store.put_json(agent_id, normalized.get("output"))
        normalized["output_artifact"] = reference

    value = store.load_json(reference, expected_task_id=agent_id)
    normalized["output"] = choose_public_output(
        value,
        reference,
        inline_limit=limits.max_upstream_inline_bytes,
    )
    return normalized


class TrustedControlFlowScheduler:
    """Execute the bounded Workflow IR v3 control-flow subset.

    ``execute_agent`` is the sole model/process boundary. The scheduler owns
    expansion, IDs, budgets, dependency state, manifests, events, checkpoints,
    and final acceptance of node execution state.
    """

    def __init__(
        self,
        ir: dict[str, Any],
        run_dir: Path,
        *,
        execute_agent: AgentExecutor,
        limits: RuntimeLimits,
        clock: DeadlineClock | None = None,
    ) -> None:
        candidate = dict(ir)
        candidate.pop("execution", None)
        self.ir = validate_workflow_ir(candidate)
        unsupported = self.ir["execution"]["unsupported_node_kinds"]
        if unsupported:
            raise ControlFlowError(
                "Workflow IR contains validated but non-executable node kinds: "
                + ", ".join(unsupported)
            )
        if any(
            node["kind"] not in EXECUTABLE_NODE_KINDS
            for node in self.ir["nodes"]
        ):
            raise ControlFlowError("Workflow IR contains an untrusted node kind")

        self.claim_projection = project_agent_claims(self.ir)
        projected_loops = executable_bounded_loops(
            self.ir["nodes"], self.ir["budgets"]
        )
        if projected_loops and not self.claim_projection["upper_bound_within_budget"]:
            raise AgentBudgetError(
                "projected agent claims exceed budgets.max_agents: "
                f"{self.claim_projection['total_upper_bound']} > "
                f"{self.claim_projection['max_agents']}"
            )

        self.run_dir = Path(os.path.abspath(os.fspath(run_dir)))
        self.execute_agent = execute_agent
        self.limits = limits
        self.node_by_id = {node["id"]: node for node in self.ir["nodes"]}
        self.node_order = [node["id"] for node in self.ir["nodes"]]
        self.bounded_loops = projected_loops
        self.loop_template_ids = {
            template_id.casefold()
            for body in self.bounded_loops.values()
            for template_id in body
        }
        self.max_agents = self.ir["budgets"]["max_agents"]
        self.max_concurrency = self.ir["budgets"]["max_concurrency"]
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        self.state_lock = asyncio.Lock()
        self.cancel_path = self.run_dir / "CANCEL"
        self.store = ArtifactStore(self.run_dir, limits)
        self.state_store = RunStateStore(
            self.run_dir,
            max_event_bytes=limits.max_event_bytes,
            max_run_artifact_bytes=limits.max_run_artifact_bytes,
        )
        self.gate_store = HumanGateStore(self.run_dir, limits)
        self.entries: dict[str, dict[str, Any]] = {}
        self.states: dict[str, str] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.claimed_agents: set[str] = set()
        self.started: str | None = None
        self.finished: str | None = None
        self.clock = clock or SystemDeadlineClock()
        self.workflow_started_epoch_ms: int | None = None
        self.workflow_deadline_epoch_ms: int | None = None
        self.workflow_last_observed_epoch_ms: int | None = None
        self.deadline_exceeded_recorded = False
        self.completed_node_events: set[str] = set()
        self.pending_node_completion_reconciliation: list[str] = []
        self.pending_deadline_event_reconciliation: str | None = None

    @property
    def ir_digest(self) -> str:
        payload = {
            key: self.ir[key]
            for key in (
                "version",
                "name",
                "mode",
                "objective",
                "workdir",
                "budgets",
                "limits",
                "nodes",
            )
            if key in self.ir
        }
        return _canonical_digest(payload)

    def _claim_agent(self, agent_id: str) -> None:
        if agent_id in self.claimed_agents:
            return
        if len(self.claimed_agents) >= self.max_agents:
            raise AgentBudgetError(
                f"agent budget exceeded: max_agents={self.max_agents}; "
                f"next={agent_id}"
            )
        self.claimed_agents.add(agent_id)

    def _load_result_value(self, node_id: str) -> Any:
        if node_id not in self.node_by_id:
            raise ControlFlowError(f"unknown Workflow IR result node: {node_id}")
        record = self.results.get(node_id)
        if not isinstance(record, dict):
            raise ControlFlowError(f"node {node_id} has no accepted result")
        reference = record.get("artifact")
        if reference is not None:
            return self.store.load_json(reference, expected_task_id=node_id)
        output = record.get("output")
        if is_artifact_reference(output):
            return self.store.load_json(output, expected_task_id=node_id)
        return output

    def _set_node_output(self, entry: dict[str, Any], value: Any) -> None:
        reference = self.store.put_json(entry["id"], value)
        entry["output_artifact"] = reference
        entry["output"] = choose_public_output(
            value,
            reference,
            inline_limit=self.limits.max_upstream_inline_bytes,
        )
        self.results[entry["id"]] = _entry_record(entry)

    async def _event(self, event_type: str, payload: dict[str, Any]) -> None:
        async with self.state_lock:
            self.state_store.append_event(event_type, payload)
            self._snapshot_locked()

    async def _record_node_completed(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> None:
        node_id = node["id"]
        async with self.state_lock:
            if node_id in self.completed_node_events:
                return
            self.state_store.append_event(
                "workflow.node.completed",
                {
                    "node_id": node_id,
                    "kind": node["kind"],
                    "status": entry["status"],
                    "error": entry.get("error"),
                },
            )
            # Keep the in-memory exactly-once guard after a successful append even
            # when the following snapshot fails. Resume reconstructs the same guard
            # from the durable journal.
            self.completed_node_events.add(node_id)
            # Publish the terminal entry and state as one snapshot.  A crash after
            # the durable event must never leave checkpoint.states at ``running``
            # while checkpoint.entries already contains a terminal result.
            self.entries[node_id] = entry
            self.states[node_id] = entry["status"]
            try:
                self._snapshot_locked()
            except Exception:
                # The journal append is the durable completion decision.  Let the
                # scheduler's next snapshot retry persist the same terminal entry;
                # propagating here would replace it with a generic failed entry.
                return

    def _summary(self) -> dict[str, Any]:
        ordered = [self.entries[node_id] for node_id in self.node_order]
        counts = {
            state: sum(entry["status"] == state for entry in ordered)
            for state in (
                "pending",
                "running",
                "succeeded",
                "failed",
                "blocked",
                "cancelled",
                "needs_escalation",
                "skipped",
                "waiting",
            )
        }
        summary = {
            "runtime": "workflow-ir-v3",
            "version": 3,
            "name": self.ir["name"],
            "objective": self.ir["objective"],
            "run_dir": str(self.run_dir),
            "workdir": self.ir["workdir"],
            "ir_digest": self.ir_digest,
            "started": self.started,
            "finished": self.finished,
            "total": len(ordered),
            "succeeded_count": counts["succeeded"],
            "failed_count": counts["failed"],
            "blocked_count": counts["blocked"],
            "cancelled_count": counts["cancelled"],
            "needs_escalation_count": counts["needs_escalation"],
            "skipped_count": counts["skipped"],
            "waiting_count": counts["waiting"],
            "paused": counts["waiting"] > 0,
            "all_succeeded": (
                counts["succeeded"] + counts["skipped"] == len(ordered)
            ),
            "claimed_agent_count": len(self.claimed_agents),
            "max_agents": self.max_agents,
            "max_concurrency": self.max_concurrency,
            "budget_semantics": {
                "max_tokens": TOKEN_BUDGET_MODE,
                "timeouts": (
                    "per_agent_capped_by_absolute_workflow_deadline"
                    if self.workflow_deadline_epoch_ms is not None
                    else TIMEOUT_SCOPE
                ),
            },
            "limits": self.limits.to_dict(),
            "nodes": ordered,
        }
        if self.workflow_deadline_epoch_ms is not None:
            summary["workflow_deadline"] = {
                "started_epoch_ms": self.workflow_started_epoch_ms,
                "deadline_epoch_ms": self.workflow_deadline_epoch_ms,
                "last_observed_epoch_ms": self.workflow_last_observed_epoch_ms,
                "timeout_seconds": self.ir["budgets"][
                    "workflow_timeout_seconds"
                ],
                "exceeded": self.deadline_exceeded_recorded,
            }
        return summary

    def _snapshot_locked(self) -> None:
        summary = self._summary()
        _bounded_json_write(
            self.run_dir / "summary.json",
            summary,
            run_dir=self.run_dir,
            limits=self.limits,
            label="Workflow IR summary write",
        )
        checkpoint = {
            "runtime": "workflow-ir-v3",
            "ir_digest": self.ir_digest,
            "started": self.started,
            "finished": self.finished,
            "states": self.states,
            "entries": self.entries,
            "claimed_agents": sorted(self.claimed_agents),
        }
        if self.workflow_deadline_epoch_ms is not None:
            checkpoint.update(
                {
                    "workflow_started_epoch_ms": self.workflow_started_epoch_ms,
                    "workflow_deadline_epoch_ms": self.workflow_deadline_epoch_ms,
                    "workflow_last_observed_epoch_ms": self.workflow_last_observed_epoch_ms,
                    "deadline_exceeded_recorded": self.deadline_exceeded_recorded,
                }
            )
        self.state_store.write_checkpoint(checkpoint)

    async def _snapshot(self) -> None:
        async with self.state_lock:
            self._snapshot_locked()

    async def _record_deadline_exceeded(self, agent_id: str) -> None:
        self._workflow_now()
        async with self.state_lock:
            if self.deadline_exceeded_recorded:
                return
            self.deadline_exceeded_recorded = True
            try:
                self.state_store.append_event(
                    "workflow.deadline.exceeded",
                    {
                        "agent_id": agent_id,
                        "workflow_deadline_epoch_ms": self.workflow_deadline_epoch_ms,
                    },
                )
            except BaseException:
                self.deadline_exceeded_recorded = False
                raise
            try:
                self._snapshot_locked()
            except Exception:
                # The exactly-once flag follows the durable append.  Callers have
                # already updated the referenced context, and their next snapshot
                # retries without appending a second deadline event.
                return

    async def _expire_nonterminal_for_deadline(self, context_id: str) -> None:
        """Fail closed at the scheduler boundary without creating agent claims."""

        for loop_id in self.bounded_loops:
            if self.states[loop_id] not in {"pending", "running", WAITING}:
                continue
            node = self.node_by_id[loop_id]
            entry = self.entries[loop_id]
            await self._mark_loop_templates_skipped(node)
            entry.setdefault("current_iteration", 1)
            entry.setdefault("completed_iterations", 0)
            entry.setdefault("progress_digests", [])
            entry.setdefault("stop_reason", None)
            entry.setdefault("iteration_records", [])
            entry.setdefault("children", {})
            await self._stop_loop(
                node,
                entry,
                status="needs_escalation",
                reason="workflow_deadline",
                error="absolute workflow deadline exceeded before dispatch",
                record_node_completion=entry.get("started") is not None,
            )

        for node_id in self.node_order:
            if self.states[node_id] not in {"pending", "running", WAITING}:
                continue
            if node_id.casefold() in self.loop_template_ids:
                continue
            entry = self.entries[node_id]
            self.states[node_id] = "needs_escalation"
            entry["status"] = "needs_escalation"
            entry["error"] = "absolute workflow deadline exceeded before dispatch"
            entry["finished"] = now_iso()
        await self._snapshot()
        if self.states.get(context_id) != "needs_escalation":
            context_id = next(
                node_id
                for node_id in self.node_order
                if self.states[node_id] == "needs_escalation"
            )
        await self._record_deadline_exceeded(context_id)

    def _deadline_agent_entry(
        self,
        agent_id: str,
        prior_entry: dict[str, Any] | None,
        *,
        cancellation_cleanup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = (
            json.loads(json.dumps(prior_entry, ensure_ascii=False))
            if isinstance(prior_entry, dict)
            else {}
        )
        entry.update(
            {
                "id": agent_id,
                "status": "needs_escalation",
                "error": "absolute workflow deadline exceeded",
                "output": None,
                "output_artifact": None,
            }
        )
        if cancellation_cleanup is not None:
            entry["cancellation_cleanup"] = cancellation_cleanup
        entry.setdefault("attempts", [])
        return entry

    def _bind_deadline_agent_entry(
        self,
        context_entry: dict[str, Any],
        agent_entry: dict[str, Any],
    ) -> None:
        """Bind deadline evidence to its real node/child before journaling it."""

        context_entry["agent_entry"] = agent_entry
        context_entry["status"] = agent_entry["status"]
        context_entry["error"] = agent_entry.get("error")
        context_entry["output"] = agent_entry.get("output")
        context_entry["output_artifact"] = agent_entry.get("output_artifact")
        context_id = context_entry.get("id")
        if (
            isinstance(context_id, str)
            and self.entries.get(context_id) is context_entry
        ):
            self.states[context_id] = agent_entry["status"]

    def _workflow_now(self) -> int:
        now = checked_epoch_ms(self.clock)
        previous = self.workflow_last_observed_epoch_ms
        if previous is not None and now < previous:
            raise ControlFlowError(
                "deadline clock moved backwards; refusing to expand remaining time"
            )
        self.workflow_last_observed_epoch_ms = now
        return now

    def _agent_runtime_metadata(self) -> dict[str, int] | None:
        if self.workflow_deadline_epoch_ms is None:
            return None
        now = self._workflow_now()
        remaining_ms = self.workflow_deadline_epoch_ms - now
        if remaining_ms <= 0:
            return None
        remaining_seconds = max(1, (remaining_ms + 999) // 1000)
        return {
            "soft_timeout_seconds": min(
                self.ir["budgets"]["soft_timeout_seconds"],
                remaining_seconds,
            ),
            "hard_timeout_seconds": min(
                self.ir["budgets"]["hard_timeout_seconds"],
                remaining_seconds,
            ),
        }

    async def _call_agent(
        self,
        task: dict[str, Any],
        results: dict[str, Any],
        prior_entry: dict[str, Any] | None,
        *,
        context_entry: dict[str, Any],
    ) -> dict[str, Any]:
        agent_id = task["id"]
        if prior_entry and prior_entry.get("status") == SUCCESS:
            self._claim_agent(agent_id)
            return _normalize_agent_entry(
                agent_id,
                prior_entry,
                store=self.store,
                limits=self.limits,
            )
        async with self.semaphore:
            runtime_metadata = self._agent_runtime_metadata()
            if (
                self.workflow_deadline_epoch_ms is not None
                and runtime_metadata is None
            ):
                deadline_entry = self._deadline_agent_entry(
                    agent_id, prior_entry
                )
                self._bind_deadline_agent_entry(
                    context_entry, deadline_entry
                )
                await self._record_deadline_exceeded(agent_id)
                return deadline_entry
            self._claim_agent(agent_id)
            dispatch_task = dict(task)
            if runtime_metadata is not None:
                dispatch_task["_runtime"] = runtime_metadata
            if self.workflow_deadline_epoch_ms is None:
                raw = await self.execute_agent(
                    dispatch_task, results, prior_entry
                )
            else:
                execution = asyncio.create_task(
                    self.execute_agent(dispatch_task, results, prior_entry)
                )
                deadline_waiter = asyncio.create_task(
                    self.clock.wait_until(self.workflow_deadline_epoch_ms)
                )
                try:
                    done, _ = await asyncio.wait(
                        {execution, deadline_waiter},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                except asyncio.CancelledError:
                    execution.cancel()
                    deadline_waiter.cancel()
                    await asyncio.gather(
                        execution, deadline_waiter, return_exceptions=True
                    )
                    raise
                if deadline_waiter in done:
                    if not execution.done():
                        execution.cancel()
                    cleanup_result = (
                        await asyncio.gather(execution, return_exceptions=True)
                    )[0]
                    if isinstance(cleanup_result, asyncio.CancelledError):
                        cleanup = {"status": "cancelled"}
                    elif isinstance(cleanup_result, BaseException):
                        cleanup = {
                            "status": "failed",
                            "error": (
                                f"{type(cleanup_result).__name__}: {cleanup_result}"
                            ),
                        }
                    else:
                        cleanup = {
                            "status": "returned_after_deadline",
                            "result_status": (
                                cleanup_result.get("status")
                                if isinstance(cleanup_result, dict)
                                else None
                            ),
                        }
                    deadline_entry = self._deadline_agent_entry(
                        agent_id,
                        prior_entry,
                        cancellation_cleanup=cleanup,
                    )
                    self._bind_deadline_agent_entry(
                        context_entry, deadline_entry
                    )
                    await self._record_deadline_exceeded(agent_id)
                    return deadline_entry
                deadline_waiter.cancel()
                await asyncio.gather(deadline_waiter, return_exceptions=True)
                raw = execution.result()
        return _normalize_agent_entry(
            agent_id,
            raw,
            store=self.store,
            limits=self.limits,
        )

    def _agent_task(
        self,
        agent_id: str,
        config: dict[str, Any],
        *,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": agent_id,
            "prompt": config["prompt"] if prompt is None else prompt,
            "role": config["profile"],
            "route_reason": config["route_reason"],
            "depends_on": [],
            "output_schema": config.get("output_schema"),
            "allow_escalation": False,
        }

    async def _run_agent_node(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        task = self._agent_task(node["id"], node["config"])
        prior = entry.get("agent_entry")
        agent_entry = await self._call_agent(
            task,
            dict(self.results),
            prior,
            context_entry=entry,
        )
        entry["agent_entry"] = agent_entry
        entry["status"] = agent_entry["status"]
        entry["error"] = agent_entry.get("error")
        entry["output"] = agent_entry.get("output")
        entry["output_artifact"] = agent_entry.get("output_artifact")
        if entry["status"] == SUCCESS:
            self.results[node["id"]] = _entry_record(entry)
        return entry

    async def _run_map_child(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        index: int,
        item: Any,
    ) -> dict[str, Any]:
        config = node["config"]
        agent_id = _child_agent_id(node["id"], "map", index)
        input_id = _input_id(node["id"], "map", index)
        item_reference = self.store.put_json(input_id, item)
        item_record = {
            "output": choose_public_output(
                item,
                item_reference,
                inline_limit=self.limits.max_upstream_inline_bytes,
            ),
            "artifact": item_reference,
        }
        prompt = _render_prompt(
            config["template"]["prompt"],
            {
                "item": "{{result:" + input_id + "}}",
                "index": str(index),
                "source": "{{result:" + config["over"] + "}}",
            },
        )
        task = self._agent_task(
            agent_id,
            config["template"],
            prompt=prompt,
        )
        child = entry["children"].get(agent_id) or {
            "id": agent_id,
            "index": index,
            "status": "pending",
            "input_artifact": item_reference,
            "output": None,
            "output_artifact": None,
            "error": None,
        }
        child["status"] = "running"
        entry["children"][agent_id] = child
        await self._event(
            "map.child.started",
            {"node_id": node["id"], "child_id": agent_id, "index": index},
        )
        results = dict(self.results)
        results[input_id] = item_record
        prior = child.get("agent_entry")
        try:
            agent_entry = await self._call_agent(
                task,
                results,
                prior,
                context_entry=child,
            )
        except Exception as exc:
            child["status"] = "failed"
            child["error"] = f"{type(exc).__name__}: {exc}"
        else:
            child["agent_entry"] = agent_entry
            child["status"] = agent_entry["status"]
            child["error"] = agent_entry.get("error")
            child["output"] = agent_entry.get("output")
            child["output_artifact"] = agent_entry.get("output_artifact")
        await self._event(
            "map.child.completed",
            {
                "node_id": node["id"],
                "child_id": agent_id,
                "index": index,
                "status": child["status"],
                "error": child.get("error"),
            },
        )
        return child

    async def _run_map_node(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        config = node["config"]
        source = self._load_result_value(config["over"])
        if not isinstance(source, list):
            raise ControlFlowError(
                f"map node {node['id']} source {config['over']} must be a JSON array"
            )
        item_limit = min(config["item_limit"], self.max_agents)
        if len(source) > item_limit:
            raise AgentBudgetError(
                f"map node {node['id']} has {len(source)} items; item_limit={item_limit}"
            )
        entry.setdefault("children", {})
        coroutines = []
        for index, item in enumerate(source):
            agent_id = _child_agent_id(node["id"], "map", index)
            prior = entry["children"].get(agent_id)
            if prior and prior.get("status") == SUCCESS:
                self._claim_agent(agent_id)
                continue
            coroutines.append(self._run_map_child(node, entry, index, item))
        if coroutines:
            await asyncio.gather(*coroutines)

        children = sorted(
            entry["children"].values(), key=lambda child: child["index"]
        )
        manifest = {
            "manifest_version": 1,
            "kind": "map",
            "node_id": node["id"],
            "source_node": config["over"],
            "item_count": len(source),
            "items": [
                {
                    "index": child["index"],
                    "child_id": child["id"],
                    "status": child["status"],
                    "input_artifact": child.get("input_artifact"),
                    "output": child.get("output"),
                    "output_artifact": child.get("output_artifact"),
                    "error": child.get("error"),
                }
                for child in children
            ],
        }
        self._set_node_output(entry, manifest)
        failures = [child for child in children if child["status"] != SUCCESS]
        if failures:
            entry["status"] = "failed"
            entry["error"] = (
                f"map node has {len(failures)} non-success child result(s)"
            )
        else:
            entry["status"] = SUCCESS
            entry["error"] = None
        return entry

    async def _run_verify_child(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        item: dict[str, Any],
    ) -> dict[str, Any]:
        config = node["config"]
        index = item["index"]
        agent_id = _child_agent_id(node["id"], "verify", index)
        input_id = _input_id(node["id"], "verify", index)
        candidate = {
            "index": index,
            "source_child_id": item["child_id"],
            "candidate_output": item.get("output"),
            "candidate_artifact": item.get("output_artifact"),
        }
        reference = self.store.put_json(input_id, candidate)
        record = {
            "output": choose_public_output(
                candidate,
                reference,
                inline_limit=self.limits.max_upstream_inline_bytes,
            ),
            "artifact": reference,
        }
        prompt = _render_prompt(
            config["prompt"],
            {
                "candidate": "{{result:" + input_id + "}}",
                "index": str(index),
                "source": "{{result:" + config["target"] + "}}",
                "manifest": "{{result:" + config["target"] + "}}",
            },
        )
        task_config = {
            "profile": config["profile"],
            "prompt": prompt,
            "route_reason": config["route_reason"],
            "output_schema": VERIFICATION_RESULT_SCHEMA,
            "access": "read_only",
        }
        task = self._agent_task(agent_id, task_config, prompt=prompt)
        child = entry["children"].get(agent_id) or {
            "id": agent_id,
            "index": index,
            "source_child_id": item["child_id"],
            "status": "pending",
            "input_artifact": reference,
            "output": None,
            "output_artifact": None,
            "error": None,
        }
        child["status"] = "running"
        entry["children"][agent_id] = child
        await self._event(
            "verify.child.started",
            {"node_id": node["id"], "child_id": agent_id, "index": index},
        )
        results = dict(self.results)
        results[input_id] = record
        prior = child.get("agent_entry")
        try:
            agent_entry = await self._call_agent(
                task,
                results,
                prior,
                context_entry=child,
            )
        except Exception as exc:
            child["status"] = "failed"
            child["error"] = f"{type(exc).__name__}: {exc}"
        else:
            child["agent_entry"] = agent_entry
            child["status"] = agent_entry["status"]
            child["error"] = agent_entry.get("error")
            child["output"] = agent_entry.get("output")
            child["output_artifact"] = agent_entry.get("output_artifact")
        await self._event(
            "verify.child.completed",
            {
                "node_id": node["id"],
                "child_id": agent_id,
                "index": index,
                "status": child["status"],
                "error": child.get("error"),
            },
        )
        return child

    async def _run_verify_node(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        config = node["config"]
        target = self._load_result_value(config["target"])
        if not isinstance(target, dict) or target.get("kind") != "map":
            raise ControlFlowError(
                f"verify node {node['id']} target must be a map manifest"
            )
        items = target.get("items")
        if not isinstance(items, list):
            raise ControlFlowError("map manifest items are malformed")
        entry.setdefault("children", {})
        coroutines = []
        for item in items:
            if not isinstance(item, dict) or item.get("status") != SUCCESS:
                raise ControlFlowError(
                    "verify target contains a non-success or malformed map item"
                )
            index = item.get("index")
            if not isinstance(index, int) or isinstance(index, bool):
                raise ControlFlowError("map manifest item index is invalid")
            agent_id = _child_agent_id(node["id"], "verify", index)
            prior = entry["children"].get(agent_id)
            if prior and prior.get("status") == SUCCESS:
                self._claim_agent(agent_id)
                continue
            coroutines.append(self._run_verify_child(node, entry, item))
        if coroutines:
            await asyncio.gather(*coroutines)

        children = sorted(
            entry["children"].values(), key=lambda child: child["index"]
        )
        execution_failures = [
            child for child in children if child["status"] != SUCCESS
        ]
        verdicts = {"accept": 0, "reject": 0, "unknown": 0}
        for child in children:
            if child["status"] != SUCCESS:
                continue
            value = child.get("output")
            if is_artifact_reference(value):
                value = self.store.load_json(value)
            if not isinstance(value, dict) or value.get("verdict") not in verdicts:
                raise ControlFlowError(
                    f"verifier child {child['id']} returned an invalid verdict"
                )
            verdicts[value["verdict"]] += 1

        verification_passed = verdicts["reject"] == 0 and (
            verdicts["unknown"] == 0 if config["require_all"] else True
        )
        manifest = {
            "manifest_version": 1,
            "kind": "verify",
            "node_id": node["id"],
            "target_node": config["target"],
            "item_count": len(children),
            "verdict_counts": verdicts,
            "require_all": config["require_all"],
            "verification_passed": verification_passed,
            "items": [
                {
                    "index": child["index"],
                    "child_id": child["id"],
                    "source_child_id": child["source_child_id"],
                    "status": child["status"],
                    "output": child.get("output"),
                    "output_artifact": child.get("output_artifact"),
                    "error": child.get("error"),
                }
                for child in children
            ],
        }
        self._set_node_output(entry, manifest)
        if execution_failures:
            entry["status"] = "failed"
            entry["error"] = (
                f"verify node has {len(execution_failures)} execution failure(s)"
            )
        else:
            entry["status"] = SUCCESS
            entry["error"] = None
        return entry

    async def _mark_loop_templates_skipped(
        self, node: dict[str, Any]
    ) -> None:
        for template_id in self.bounded_loops[node["id"]]:
            state = self.states[template_id]
            template_entry = self.entries[template_id]
            if state == SKIPPED:
                if template_entry.get("reason") != LOOP_TEMPLATE_SKIP_REASON:
                    raise ControlFlowError(
                        f"loop template {template_id} has an invalid skip reason"
                    )
                continue
            if state != "pending":
                raise ControlFlowError(
                    f"loop template {template_id} is not pending"
                )
            self.states[template_id] = SKIPPED
            template_entry["status"] = SKIPPED
            template_entry["reason"] = LOOP_TEMPLATE_SKIP_REASON
            template_entry["error"] = None
            template_entry["finished"] = now_iso()
            await self._event(
                "workflow.node.skipped",
                {
                    "node_id": template_id,
                    "loop_node": node["id"],
                    "reason": LOOP_TEMPLATE_SKIP_REASON,
                },
            )

    def _loop_state_value(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        iteration_record: dict[str, Any],
        step_index: int,
    ) -> dict[str, Any]:
        initial_id = node["depends_on"][0]
        initial_record = self.results[initial_id]
        initial = initial_record.get("output")

        previous_candidate = None
        previous_feedback = None
        if entry["iteration_records"]:
            completed = [
                record
                for record in entry["iteration_records"]
                if record.get("status") == "completed"
                and record.get("iteration", 0) < iteration_record["iteration"]
            ]
            if completed:
                previous = completed[-1]
                previous_candidate = entry["children"][
                    previous["child_ids"][-2]
                ].get("output")
                previous_feedback = entry["children"][
                    previous["child_ids"][-1]
                ].get("output")

        current_steps = []
        for child_id in iteration_record["child_ids"][:step_index]:
            child = entry["children"][child_id]
            current_steps.append(
                {
                    "child_id": child_id,
                    "template_node_id": child["template_node_id"],
                    "status": child["status"],
                    "output": child.get("output"),
                    "output_artifact": child.get("output_artifact"),
                }
            )
        history = [
            {
                "iteration": record["iteration"],
                "progress_digest": record.get("progress_digest"),
                "verdict": record.get("verdict"),
                "verifier_summary": record.get("verifier_summary"),
                "candidate_artifact": record.get("candidate_artifact"),
                "verifier_artifact": record.get("verifier_artifact"),
            }
            for record in entry["iteration_records"]
            if record.get("status") == "completed"
            and record.get("iteration", 0) < iteration_record["iteration"]
        ]
        return {
            "loop_version": 1,
            "loop_node_id": node["id"],
            "iteration": iteration_record["iteration"],
            "max_iterations": node["config"]["max_iterations"],
            "initial": initial,
            "previous_candidate": previous_candidate,
            "previous_feedback": previous_feedback,
            "current_steps": current_steps,
            "history": history,
        }

    def _loop_host_result_inputs(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        iteration_record: dict[str, Any],
        step_index: int,
        *,
        state_id: str,
        state_value: dict[str, Any],
        state_reference: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Expose only host-selected current loop inputs to substitution."""

        results: dict[str, Any] = {
            state_id: {
                "output": choose_public_output(
                    state_value,
                    state_reference,
                    inline_limit=self.limits.max_upstream_inline_bytes,
                ),
                "artifact": state_reference,
            }
        }
        placeholders: list[tuple[str, str]] = []

        initial_id = node["depends_on"][0]
        results[initial_id] = dict(self.results[initial_id])
        placeholders.append(("initial", initial_id))

        completed = [
            record
            for record in entry["iteration_records"]
            if record.get("status") == "completed"
            and record.get("iteration", 0) < iteration_record["iteration"]
        ]
        if completed:
            previous = completed[-1]
            for label, child_id in (
                ("previous_candidate", previous["child_ids"][-2]),
                ("previous_feedback", previous["child_ids"][-1]),
            ):
                results[child_id] = _entry_record(entry["children"][child_id])
                placeholders.append((label, child_id))

        for index, child_id in enumerate(
            iteration_record["child_ids"][:step_index]
        ):
            results[child_id] = _entry_record(entry["children"][child_id])
            placeholders.append((f"current_step_{index}", child_id))

        lines = ["<BOUNDED_LOOP_HOST_RESULTS_V1>"]
        lines.extend(
            f"{label}={{{{result:{result_id}}}}}"
            for label, result_id in placeholders
        )
        lines.append("</BOUNDED_LOOP_HOST_RESULTS_V1>")
        return "\n".join(lines), results

    def _new_loop_iteration(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        child_ids = []
        for step_index, template_id in enumerate(node["config"]["body"]):
            child_id = bounded_loop_child_id(
                node["id"], iteration, step_index, template_id
            )
            state_id = bounded_loop_state_id(
                node["id"], iteration, step_index, template_id
            )
            if child_id in entry["children"]:
                raise ControlFlowError(f"duplicate bounded loop child id: {child_id}")
            entry["children"][child_id] = {
                "id": child_id,
                "task_id": child_id,
                "loop_node_id": node["id"],
                "iteration": iteration,
                "step_index": step_index,
                "template_node_id": template_id,
                "state_input_id": state_id,
                "status": "pending",
                "input_artifact": None,
                "output": None,
                "output_artifact": None,
                "error": None,
                "resume_count": 0,
            }
            child_ids.append(child_id)
        record = {
            "iteration": iteration,
            "status": "running",
            "child_ids": child_ids,
            "progress_digest": None,
            "candidate_artifact": None,
            "verifier_artifact": None,
            "verdict": None,
            "verifier_summary": None,
            "decision_applied": False,
        }
        entry["iteration_records"].append(record)
        return record

    def _loop_manifest(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        records = entry["iteration_records"]
        completed = [record for record in records if record["status"] == "completed"]
        last = completed[-1] if completed else None
        initial_entry = self.entries[node["depends_on"][0]]
        children = sorted(
            entry["children"].values(),
            key=lambda child: (child["iteration"], child["step_index"]),
        )
        final_candidate = None
        final_feedback = None
        if last:
            final_candidate = entry["children"][last["child_ids"][-2]].get(
                "output"
            )
            final_feedback = entry["children"][last["child_ids"][-1]].get(
                "output"
            )
        return {
            "manifest_version": 1,
            "loop_version": 1,
            "kind": "loop",
            "node_id": node["id"],
            "source_node": node["depends_on"][0],
            "initial_artifact": initial_entry.get("output_artifact"),
            "max_iterations": node["config"]["max_iterations"],
            "no_progress_limit": node["config"]["no_progress_limit"],
            "stop_when": node["config"]["stop_when"],
            "status": entry["status"],
            "stop_reason": entry.get("stop_reason"),
            "converged": (
                entry["status"] == SUCCESS
                and entry.get("stop_reason") == "verification_accept"
            ),
            "current_iteration": entry["current_iteration"],
            "completed_iterations": entry["completed_iterations"],
            "progress_digests": list(entry["progress_digests"]),
            "final_candidate_artifact": (
                last.get("candidate_artifact") if last else None
            ),
            "final_verifier_artifact": (
                last.get("verifier_artifact") if last else None
            ),
            "final_candidate": final_candidate,
            "final_feedback": final_feedback,
            "iteration_records": json.loads(
                json.dumps(records, ensure_ascii=False)
            ),
            "children": [
                {
                    "id": child["id"],
                    "task_id": child["task_id"],
                    "loop_node_id": child["loop_node_id"],
                    "iteration": child["iteration"],
                    "step_index": child["step_index"],
                    "template_node_id": child["template_node_id"],
                    "state_input_id": child["state_input_id"],
                    "status": child["status"],
                    "input_artifact": child.get("input_artifact"),
                    "output_artifact": child.get("output_artifact"),
                    "error": child.get("error"),
                }
                for child in children
            ],
        }

    async def _stop_loop(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        *,
        status: str,
        reason: str,
        error: str | None,
        record_node_completion: bool = True,
    ) -> dict[str, Any]:
        if (
            entry.get("status") == status
            and entry.get("stop_reason") == reason
            and entry.get("output_artifact") is not None
        ):
            return entry
        entry["status"] = status
        entry["stop_reason"] = reason
        entry["error"] = error
        entry["finished"] = entry.get("finished") or now_iso()
        self.states[node["id"]] = status
        self._set_node_output(entry, self._loop_manifest(node, entry))
        await self._event(
            "workflow.loop.stopped",
            {
                "node_id": node["id"],
                "status": status,
                "stop_reason": reason,
                "completed_iterations": entry["completed_iterations"],
                "output_artifact": entry["output_artifact"],
            },
        )
        if record_node_completion:
            await self._record_node_completed(node, entry)
        return entry

    async def _apply_loop_decision(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        record: dict[str, Any],
    ) -> dict[str, Any] | None:
        verdict = record["verdict"]
        digest = record["progress_digest"]
        record["decision_applied"] = True
        if verdict == "accept":
            return await self._stop_loop(
                node,
                entry,
                status=SUCCESS,
                reason="verification_accept",
                error=None,
            )
        if verdict == "unknown":
            return await self._stop_loop(
                node,
                entry,
                status="needs_escalation",
                reason="verification_unknown",
                error="bounded loop verifier returned unknown",
            )

        repetitions = 0
        for previous in reversed(entry["progress_digests"][:-1]):
            if previous != digest:
                break
            repetitions += 1
        if repetitions >= node["config"]["no_progress_limit"]:
            return await self._stop_loop(
                node,
                entry,
                status="needs_escalation",
                reason="no_progress",
                error="bounded loop candidate digest made no progress",
            )
        if record["iteration"] >= node["config"]["max_iterations"]:
            return await self._stop_loop(
                node,
                entry,
                status="needs_escalation",
                reason="iteration_limit",
                error="bounded loop reached max_iterations without acceptance",
            )
        entry["current_iteration"] = record["iteration"] + 1
        return None

    async def _run_loop_node(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        await self._mark_loop_templates_skipped(node)
        entry.setdefault("current_iteration", 1)
        entry.setdefault("completed_iterations", 0)
        entry.setdefault("progress_digests", [])
        entry.setdefault("stop_reason", None)
        entry.setdefault("iteration_records", [])
        entry.setdefault("children", {})

        while entry["current_iteration"] <= node["config"]["max_iterations"]:
            iteration = entry["current_iteration"]
            existing = [
                record
                for record in entry["iteration_records"]
                if record.get("iteration") == iteration
            ]
            if len(existing) > 1:
                raise ControlFlowError("duplicate bounded loop iteration record")
            if existing:
                record = existing[0]
            else:
                record = self._new_loop_iteration(node, entry, iteration)
                await self._event(
                    "workflow.loop.iteration.started",
                    {
                        "node_id": node["id"],
                        "iteration": iteration,
                        "child_ids": list(record["child_ids"]),
                    },
                )

            if record.get("status") == "completed":
                terminal = await self._apply_loop_decision(node, entry, record)
                if terminal is not None:
                    return terminal
                continue

            for step_index, template_id in enumerate(node["config"]["body"]):
                child_id = record["child_ids"][step_index]
                child = entry["children"][child_id]
                if child["status"] == SUCCESS:
                    self.store.load_json(
                        child["output_artifact"], expected_task_id=child_id
                    )
                    continue
                if child["status"] in {
                    "failed",
                    "cancelled",
                    "needs_escalation",
                }:
                    propagated = child["status"]
                    return await self._stop_loop(
                        node,
                        entry,
                        status=propagated,
                        reason=f"step_{propagated}",
                        error=child.get("error")
                        or f"bounded loop step {child_id} did not succeed",
                    )
                if child["status"] != "pending":
                    raise ControlFlowError(
                        f"bounded loop child {child_id} cannot dispatch from {child['status']}"
                    )

                if (
                    self.workflow_deadline_epoch_ms is not None
                    and self._agent_runtime_metadata() is None
                ):
                    terminal = await self._stop_loop(
                        node,
                        entry,
                        status="needs_escalation",
                        reason="workflow_deadline",
                        error="absolute workflow deadline exceeded",
                    )
                    await self._record_deadline_exceeded(node["id"])
                    return terminal
                self._claim_agent(child_id)
                template = self.node_by_id[template_id]
                state_value = self._loop_state_value(
                    node, entry, record, step_index
                )
                state_id = child["state_input_id"]
                state_reference = self.store.put_json(state_id, state_value)
                if (
                    child.get("input_artifact") is not None
                    and child["input_artifact"] != state_reference
                ):
                    raise ControlFlowError(
                        f"bounded loop state identity changed for {child_id}"
                    )
                child["input_artifact"] = state_reference
                prompt = _render_prompt(
                    template["config"]["prompt"],
                    {
                        "loop_state": "{{result:" + state_id + "}}",
                        "iteration": str(iteration),
                    },
                )
                if "{{loop_state}}" in prompt or "{{iteration}}" in prompt:
                    raise ControlFlowError("bounded loop prompt substitution failed")
                host_inputs, results = self._loop_host_result_inputs(
                    node,
                    entry,
                    record,
                    step_index,
                    state_id=state_id,
                    state_value=state_value,
                    state_reference=state_reference,
                )
                prompt = prompt + "\n\n" + host_inputs
                task = self._agent_task(
                    child_id, template["config"], prompt=prompt
                )
                child["status"] = "running"
                await self._event(
                    "workflow.loop.step.started",
                    {
                        "node_id": node["id"],
                        "iteration": iteration,
                        "step_index": step_index,
                        "template_node_id": template_id,
                        "child_id": child_id,
                        "state_input_id": state_id,
                        "input_artifact": state_reference,
                    },
                )
                try:
                    agent_entry = await self._call_agent(
                        task,
                        results,
                        child.get("agent_entry"),
                        context_entry=child,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    child["status"] = "failed"
                    child["error"] = f"{type(exc).__name__}: {exc}"
                else:
                    child["agent_entry"] = agent_entry
                    child["status"] = agent_entry["status"]
                    child["error"] = agent_entry.get("error")
                    child["output"] = agent_entry.get("output")
                    child["output_artifact"] = agent_entry.get(
                        "output_artifact"
                    )
                await self._event(
                    "workflow.loop.step.completed",
                    {
                        "node_id": node["id"],
                        "iteration": iteration,
                        "step_index": step_index,
                        "template_node_id": template_id,
                        "child_id": child_id,
                        "status": child["status"],
                        "state_input_id": state_id,
                        "input_artifact": child.get("input_artifact"),
                        "output_artifact": child.get("output_artifact"),
                        "error": child.get("error"),
                    },
                )
                if child["status"] != SUCCESS:
                    propagated = child["status"]
                    if propagated not in {
                        "failed",
                        "cancelled",
                        "needs_escalation",
                    }:
                        propagated = "failed"
                    return await self._stop_loop(
                        node,
                        entry,
                        status=propagated,
                        reason=f"step_{propagated}",
                        error=child.get("error")
                        or f"bounded loop step {child_id} did not succeed",
                    )

            candidate_id = record["child_ids"][-2]
            verifier_id = record["child_ids"][-1]
            candidate = self.store.load_json(
                entry["children"][candidate_id]["output_artifact"],
                expected_task_id=candidate_id,
            )
            verifier = self.store.load_json(
                entry["children"][verifier_id]["output_artifact"],
                expected_task_id=verifier_id,
            )
            if (
                not isinstance(verifier, dict)
                or set(verifier) != {"verdict", "summary", "evidence"}
                or verifier.get("verdict") not in {"accept", "reject", "unknown"}
                or not isinstance(verifier.get("summary"), str)
                or not isinstance(verifier.get("evidence"), list)
                or any(not isinstance(item, str) for item in verifier["evidence"])
            ):
                return await self._stop_loop(
                    node,
                    entry,
                    status="failed",
                    reason="invalid_verifier_output",
                    error=(
                        f"bounded loop verifier {verifier_id} returned an invalid result"
                    ),
                )
            digest = hashlib.sha256(canonical_json_bytes(candidate)).hexdigest()
            record.update(
                {
                    "status": "completed",
                    "progress_digest": digest,
                    "candidate_artifact": entry["children"][candidate_id][
                        "output_artifact"
                    ],
                    "verifier_artifact": entry["children"][verifier_id][
                        "output_artifact"
                    ],
                    "verdict": verifier["verdict"],
                    "verifier_summary": verifier["summary"][:1000],
                    "decision_applied": False,
                }
            )
            entry["progress_digests"].append(digest)
            entry["completed_iterations"] += 1
            await self._event(
                "workflow.loop.iteration.completed",
                {
                    "node_id": node["id"],
                    "iteration": iteration,
                    "progress_digest": digest,
                    "verdict": verifier["verdict"],
                    "candidate_child_id": candidate_id,
                    "verifier_child_id": verifier_id,
                    "candidate_artifact": record["candidate_artifact"],
                    "verifier_artifact": record["verifier_artifact"],
                },
            )
            terminal = await self._apply_loop_decision(node, entry, record)
            if terminal is not None:
                return terminal

        raise ControlFlowError("bounded loop exhausted without a terminal state")

    async def _run_reduce_node(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        config = node["config"]
        # Resolve before dispatch so a stale or corrupted manifest fails closed.
        self._load_result_value(config["over"])
        prompt = _render_prompt(
            config["prompt"],
            {
                "source": "{{result:" + config["over"] + "}}",
                "manifest": "{{result:" + config["over"] + "}}",
            },
        )
        task = self._agent_task(node["id"], config, prompt=prompt)
        prior = entry.get("agent_entry")
        agent_entry = await self._call_agent(
            task,
            dict(self.results),
            prior,
            context_entry=entry,
        )
        entry["agent_entry"] = agent_entry
        entry["status"] = agent_entry["status"]
        entry["error"] = agent_entry.get("error")
        entry["output"] = agent_entry.get("output")
        entry["output_artifact"] = agent_entry.get("output_artifact")
        if entry["status"] == SUCCESS:
            self.results[node["id"]] = _entry_record(entry)
        return entry

    def _gate_dependency_payload(
        self, node: dict[str, Any]
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for dependency in node["depends_on"]:
            entry = self.entries[dependency]
            reference = entry.get("output_artifact")
            artifact_sha256 = None
            output_digest = None
            if reference is not None:
                if not is_artifact_reference(reference):
                    raise ControlFlowError(
                        f"gate dependency {dependency} has an invalid artifact"
                    )
                self.store.resolve_reference(
                    reference, expected_task_id=dependency
                )
                artifact_sha256 = reference["$artifact"]["sha256"]
            elif entry["status"] == SUCCESS:
                output_digest = _canonical_digest(entry.get("output"))
            payload.append(
                {
                    "node_id": dependency,
                    "status": entry["status"],
                    "artifact_sha256": artifact_sha256,
                    "output_digest": output_digest,
                }
            )
        return payload

    async def _run_conditional_node(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        config = node["config"]
        source_id = config["condition"]["source"]
        sources: dict[str, Any] = {}
        if self.states[source_id] == SUCCESS:
            sources[source_id] = self._load_result_value(source_id)
        outcome = evaluate_condition(config["condition"], sources)
        entry["condition_outcome"] = outcome
        if outcome["state"] == "unknown":
            selected: list[str] = []
            skipped: list[str] = []
        elif outcome["state"] == "true":
            selected = list(config["then"])
            skipped = list(config["else"])
        else:
            selected = list(config["else"])
            skipped = list(config["then"])
        manifest = {
            "condition_version": 1,
            "kind": "conditional",
            "node_id": node["id"],
            "condition": config["condition"],
            "outcome": outcome,
            "selected_targets": selected,
            "skipped_targets": skipped,
        }
        self._set_node_output(entry, manifest)
        self.state_store.append_event(
            "workflow.conditional.evaluated",
            {
                "node_id": node["id"],
                "state": outcome["state"],
                "selected_targets": selected,
                "skipped_targets": skipped,
            },
        )
        if outcome["state"] == "unknown":
            entry["status"] = "needs_escalation"
            entry["error"] = "conditional outcome is unknown: " + outcome["reason"]
            return entry
        for target in skipped:
            if self.states[target] != "pending":
                raise ControlFlowError(
                    f"conditional target {target} is not pending"
                )
            self.states[target] = SKIPPED
            target_entry = self.entries[target]
            target_entry["status"] = SKIPPED
            target_entry["error"] = (
                f"not selected by conditional node {node['id']}"
            )
            target_entry["finished"] = now_iso()
            self.state_store.append_event(
                "workflow.node.skipped",
                {
                    "node_id": target,
                    "conditional_node": node["id"],
                    "outcome": outcome["state"],
                },
            )
        entry["status"] = SUCCESS
        entry["error"] = None
        return entry

    async def _run_human_gate_node(
        self, node: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        config = node["config"]
        dependencies = self._gate_dependency_payload(node)
        input_identity = compute_gate_input_identity(
            node["id"],
            config["prompt"],
            config["options"],
            dependencies,
        )
        try:
            record = self.gate_store.open_gate(
                node["id"],
                prompt=config["prompt"],
                options=config["options"],
                input_identity=input_identity,
            )
        except HumanGateError as exc:
            entry["status"] = "needs_escalation"
            entry["error"] = f"human gate record rejected: {exc}"
            return entry
        entry["gate"] = record
        if record["status"] == "waiting":
            entry["status"] = WAITING
            entry["error"] = "explicit human decision required"
            return entry
        manifest = {
            "gate_version": record["gate_version"],
            "kind": "human_gate",
            "node_id": node["id"],
            "input_identity": record["input_identity"],
            "decision": record["decision"],
            "actor": record["actor"],
            "source": record["source"],
            "note": record["note"],
        }
        self._set_node_output(entry, manifest)
        entry["status"] = SUCCESS
        entry["error"] = None
        return entry

    async def _execute_node(self, node_id: str) -> dict[str, Any]:
        node = self.node_by_id[node_id]
        entry = self.entries[node_id]
        entry["status"] = "running"
        entry["started"] = entry.get("started") or now_iso()
        entry["error"] = None
        await self._event(
            "workflow.node.started",
            {"node_id": node_id, "kind": node["kind"]},
        )
        try:
            if node["kind"] == "agent":
                entry = await self._run_agent_node(node, entry)
            elif node["kind"] == "map":
                entry = await self._run_map_node(node, entry)
            elif node["kind"] == "verify":
                entry = await self._run_verify_node(node, entry)
            elif node["kind"] == "loop":
                entry = await self._run_loop_node(node, entry)
            elif node["kind"] == "reduce":
                entry = await self._run_reduce_node(node, entry)
            elif node["kind"] == "conditional":
                entry = await self._run_conditional_node(node, entry)
            elif node["kind"] == "human_gate":
                entry = await self._run_human_gate_node(node, entry)
            else:  # guarded by __init__; retained as a fail-closed assertion.
                raise ControlFlowError(
                    f"node kind is not executable: {node['kind']}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        if entry["status"] == WAITING:
            entry["finished"] = None
            await self._event(
                "workflow.node.waiting",
                {
                    "node_id": node_id,
                    "kind": node["kind"],
                    "input_identity": (
                        entry.get("gate") or {}
                    ).get("input_identity"),
                },
            )
        else:
            entry["finished"] = entry.get("finished") or now_iso()
            await self._record_node_completed(node, entry)
        return entry

    def _validate_successful_top_entry(
        self, node_id: str, entry: dict[str, Any]
    ) -> None:
        reference = entry.get("output_artifact")
        try:
            value = self.store.load_json(reference, expected_task_id=node_id)
        except ArtifactLimitError as exc:
            raise ControlFlowError(
                f"successful node {node_id} artifact is invalid: {exc}"
            ) from exc
        expected_output = choose_public_output(
            value,
            reference,
            inline_limit=self.limits.max_upstream_inline_bytes,
        )
        if entry.get("output") != expected_output:
            raise ControlFlowError(
                f"successful node {node_id} public output disagrees with artifact"
            )
        if self.node_by_id[node_id]["kind"] == "human_gate":
            try:
                record = self.gate_store.load(node_id)
            except HumanGateError as exc:
                raise ControlFlowError(
                    f"successful human gate {node_id} record is invalid: {exc}"
                ) from exc
            if record["status"] != "decided":
                raise ControlFlowError(
                    f"successful human gate {node_id} has no terminal decision"
                )
            node = self.node_by_id[node_id]
            expected_identity = compute_gate_input_identity(
                node_id,
                node["config"]["prompt"],
                node["config"]["options"],
                self._gate_dependency_payload(node),
            )
            if (
                record["prompt"] != node["config"]["prompt"]
                or record["options"] != node["config"]["options"]
                or record["input_identity"] != expected_identity
            ):
                raise ControlFlowError(
                    f"successful human gate {node_id} contract identity is invalid"
                )
            manifest = {
                "gate_version": record["gate_version"],
                "kind": "human_gate",
                "node_id": node_id,
                "input_identity": record["input_identity"],
                "decision": record["decision"],
                "actor": record["actor"],
                "source": record["source"],
                "note": record["note"],
            }
            if value != manifest or entry.get("gate") != record:
                raise ControlFlowError(
                    f"successful human gate {node_id} decision evidence disagrees "
                    "with its artifact or checkpoint"
                )
        agent_entry = entry.get("agent_entry")
        if self.node_by_id[node_id]["kind"] in {"agent", "reduce"}:
            if not isinstance(agent_entry, dict):
                raise ControlFlowError(
                    f"successful agent-backed node {node_id} is missing agent_entry"
                )
        if isinstance(agent_entry, dict):
            _strict_resume_count(
                agent_entry.get("resume_count", 0), f"agent entry {node_id}"
            )
            if (
                agent_entry.get("id") != node_id
                or agent_entry.get("status") != SUCCESS
                or agent_entry.get("output_artifact") != reference
                or agent_entry.get("output") != expected_output
            ):
                raise ControlFlowError(
                    f"successful node {node_id} agent_entry identity is invalid"
                )

    def _validate_loop_events(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        state: str,
        events: list[dict[str, Any]],
    ) -> None:
        loop_id = node["id"]

        for template_id in self.bounded_loops[loop_id]:
            expected_skip = []
            if self.states[template_id] == SKIPPED:
                expected_skip.append(
                    {
                        "node_id": template_id,
                        "loop_node": loop_id,
                        "reason": LOOP_TEMPLATE_SKIP_REASON,
                    }
                )
            actual_skip = [
                event["payload"]
                for event in events
                if event["type"] == "workflow.node.skipped"
                and event["payload"].get("node_id") == template_id
                and event["payload"].get("loop_node") == loop_id
            ]
            if actual_skip != expected_skip:
                raise ControlFlowError(
                    f"bounded loop template event evidence is invalid: {template_id}"
                )

        def payloads(event_type: str) -> list[dict[str, Any]]:
            return [
                event["payload"]
                for event in events
                if event["type"] == event_type
                and event["payload"].get("node_id") == loop_id
            ]

        expected_iterations = [
            {
                "node_id": loop_id,
                "iteration": record["iteration"],
                "child_ids": list(record["child_ids"]),
            }
            for record in entry.get("iteration_records", [])
        ]
        if payloads("workflow.loop.iteration.started") != expected_iterations:
            raise ControlFlowError(
                f"bounded loop iteration event evidence is invalid: {loop_id}"
            )

        expected_started: list[dict[str, Any]] = []
        expected_completed: list[dict[str, Any]] = []
        for record in entry.get("iteration_records", []):
            for child_id in record["child_ids"]:
                child = entry["children"][child_id]
                if child.get("input_artifact") is not None:
                    base = {
                        "node_id": loop_id,
                        "iteration": child["iteration"],
                        "step_index": child["step_index"],
                        "template_node_id": child["template_node_id"],
                        "child_id": child_id,
                        "state_input_id": child["state_input_id"],
                        "input_artifact": child["input_artifact"],
                    }
                    expected_started.extend(
                        [base] * (child.get("resume_count", 0) + 1)
                    )
                    if child["status"] not in {"pending", "running"}:
                        expected_completed.append(
                            {
                                **base,
                                "status": child["status"],
                                "output_artifact": child.get("output_artifact"),
                                "error": child.get("error"),
                            }
                        )
        if payloads("workflow.loop.step.started") != expected_started:
            raise ControlFlowError(
                f"bounded loop step-start event evidence is invalid: {loop_id}"
            )
        if payloads("workflow.loop.step.completed") != expected_completed:
            raise ControlFlowError(
                f"bounded loop step-complete event evidence is invalid: {loop_id}"
            )

        expected_completed_iterations = []
        for record in entry.get("iteration_records", []):
            if record.get("status") != "completed":
                continue
            expected_completed_iterations.append(
                {
                    "node_id": loop_id,
                    "iteration": record["iteration"],
                    "progress_digest": record["progress_digest"],
                    "verdict": record["verdict"],
                    "candidate_child_id": record["child_ids"][-2],
                    "verifier_child_id": record["child_ids"][-1],
                    "candidate_artifact": record["candidate_artifact"],
                    "verifier_artifact": record["verifier_artifact"],
                }
            )
        if (
            payloads("workflow.loop.iteration.completed")
            != expected_completed_iterations
        ):
            raise ControlFlowError(
                f"bounded loop completion event evidence is invalid: {loop_id}"
            )

        stopped = payloads("workflow.loop.stopped")
        expected_stopped = []
        if state in {SUCCESS, "failed", "cancelled", "needs_escalation"} and entry.get(
            "output_artifact"
        ) is not None:
            expected_stopped.append(
                {
                    "node_id": loop_id,
                    "status": state,
                    "stop_reason": entry.get("stop_reason"),
                    "completed_iterations": entry.get("completed_iterations"),
                    "output_artifact": entry["output_artifact"],
                }
            )
        if stopped != expected_stopped:
            raise ControlFlowError(
                f"bounded loop stop event evidence is invalid: {loop_id}"
            )

    def _validate_loop_resume_entry(
        self,
        node: dict[str, Any],
        entry: dict[str, Any],
        state: str,
        claimed_folded: set[str],
    ) -> None:
        loop_id = node["id"]
        templates = self.bounded_loops[loop_id]
        unstarted = not entry.get("iteration_records") and not entry.get("children")
        if state == "pending" or unstarted:
            if entry.get("iteration_records") or entry.get("children"):
                raise ControlFlowError(
                    f"pending bounded loop {loop_id} contains execution state"
                )
            for template_id in templates:
                template_state = self.states[template_id]
                template_entry = self.entries[template_id]
                if template_state == SKIPPED:
                    if template_entry.get("reason") != LOOP_TEMPLATE_SKIP_REASON:
                        raise ControlFlowError(
                            f"unstarted bounded loop template skip is invalid: {template_id}"
                        )
                elif template_state != "pending":
                    raise ControlFlowError(
                        f"unstarted bounded loop template state is invalid: {template_id}"
                    )
                if (
                    template_entry.get("output") is not None
                    or template_entry.get("output_artifact") is not None
                    or template_entry.get("agent_entry") is not None
                    or template_entry.get("children")
                ):
                    raise ControlFlowError(
                        f"unstarted bounded loop template has execution state: {template_id}"
                    )
            if (
                state == "needs_escalation"
                and entry.get("stop_reason") == "workflow_deadline"
            ):
                if any(
                    self.states[template_id] != SKIPPED
                    for template_id in templates
                ):
                    raise ControlFlowError(
                        f"deadline-stopped bounded loop templates are invalid: {loop_id}"
                    )
                if (
                    entry.get("current_iteration") != 1
                    or entry.get("completed_iterations") != 0
                    or entry.get("progress_digests") != []
                    or entry.get("iteration_records") != []
                    or entry.get("children") != {}
                ):
                    raise ControlFlowError(
                        f"deadline-stopped bounded loop state is invalid: {loop_id}"
                    )
                manifest = self.store.load_json(
                    entry.get("output_artifact"), expected_task_id=loop_id
                )
                if (
                    manifest != self._loop_manifest(node, entry)
                    or entry.get("output")
                    != choose_public_output(
                        manifest,
                        entry["output_artifact"],
                        inline_limit=self.limits.max_upstream_inline_bytes,
                    )
                ):
                    raise ControlFlowError(
                        f"deadline-stopped bounded loop manifest is invalid: {loop_id}"
                    )
                return
            if state != "pending" and (
                state not in {"running", "blocked", SKIPPED, "cancelled"}
                or entry.get("started") is not None
                and state != "running"
                or entry.get("output") is not None
                or entry.get("output_artifact") is not None
            ):
                raise ControlFlowError(
                    f"bounded loop {loop_id} has an invalid unstarted terminal state"
                )
            return
        if state not in {"running"} | TERMINAL_STATES:
            raise ControlFlowError(
                f"bounded loop {loop_id} has execution state while not running or terminal"
            )

        for template_id in templates:
            template_entry = self.entries[template_id]
            if (
                self.states[template_id] != SKIPPED
                or template_entry.get("status") != SKIPPED
                or template_entry.get("reason") != LOOP_TEMPLATE_SKIP_REASON
                or template_entry.get("output") is not None
                or template_entry.get("output_artifact") is not None
                or template_entry.get("agent_entry") is not None
                or template_entry.get("children")
            ):
                raise ControlFlowError(
                    f"bounded loop template state is invalid: {template_id}"
                )
            if (self.run_dir / "tasks" / template_id).exists():
                raise ControlFlowError(
                    f"bounded loop template created a top-level task directory: {template_id}"
                )

        current = entry.get("current_iteration")
        completed_count = entry.get("completed_iterations")
        progress = entry.get("progress_digests")
        records = entry.get("iteration_records")
        children = entry.get("children")
        maximum = node["config"]["max_iterations"]
        initial_entry = self.entries[node["depends_on"][0]]
        if initial_entry.get("status") != SUCCESS:
            raise ControlFlowError(
                f"started bounded loop source is not successful: {loop_id}"
            )
        self.store.load_json(
            initial_entry.get("output_artifact"),
            expected_task_id=node["depends_on"][0],
        )
        if (
            isinstance(current, bool)
            or not isinstance(current, int)
            or not 1 <= current <= maximum
            or isinstance(completed_count, bool)
            or not isinstance(completed_count, int)
            or not 0 <= completed_count <= maximum
            or not isinstance(progress, list)
            or len(progress) != completed_count
            or any(
                not isinstance(item, str)
                or len(item) != 64
                or any(character not in "0123456789abcdef" for character in item)
                for item in progress
            )
            or not isinstance(records, list)
            or not isinstance(children, dict)
        ):
            raise ControlFlowError(
                f"bounded loop checkpoint fields are malformed: {loop_id}"
            )
        if len(records) not in {completed_count, completed_count + 1}:
            raise ControlFlowError(
                f"bounded loop iteration prefix is invalid: {loop_id}"
            )
        expected_children: set[str] = set()
        computed_progress: list[str] = []
        for record_index, record in enumerate(records, start=1):
            if not isinstance(record, dict) or record.get("iteration") != record_index:
                raise ControlFlowError(
                    f"bounded loop iteration identity is invalid: {loop_id}"
                )
            expected_ids = [
                bounded_loop_child_id(loop_id, record_index, index, template_id)
                for index, template_id in enumerate(templates)
            ]
            if record.get("child_ids") != expected_ids:
                raise ControlFlowError(
                    f"bounded loop child tuple/id mismatch: {loop_id} iteration {record_index}"
                )
            expected_children.update(expected_ids)
            statuses: list[str] = []
            for step_index, (child_id, template_id) in enumerate(
                zip(expected_ids, templates)
            ):
                child = children.get(child_id)
                state_id = bounded_loop_state_id(
                    loop_id, record_index, step_index, template_id
                )
                if (
                    not isinstance(child, dict)
                    or child.get("id") != child_id
                    or child.get("task_id") != child_id
                    or child.get("loop_node_id") != loop_id
                    or child.get("iteration") != record_index
                    or child.get("step_index") != step_index
                    or child.get("template_node_id") != template_id
                    or child.get("state_input_id") != state_id
                ):
                    raise ControlFlowError(
                        f"bounded loop child identity is invalid: {child_id}"
                    )
                child_status = child.get("status")
                if child_status not in {
                    "pending",
                    "running",
                    SUCCESS,
                    "failed",
                    "cancelled",
                    "needs_escalation",
                }:
                    raise ControlFlowError(
                        f"bounded loop child status is invalid: {child_id}"
                    )
                statuses.append(child_status)
                _strict_resume_count(
                    child.get("resume_count", 0), f"loop child {child_id}"
                )
                agent_entry = child.get("agent_entry")
                if isinstance(agent_entry, dict):
                    _strict_resume_count(
                        agent_entry.get("resume_count", 0),
                        f"loop child agent entry {child_id}",
                    )
                    if agent_entry.get("id") != child_id:
                        raise ControlFlowError(
                            f"bounded loop child agent identity is invalid: {child_id}"
                        )
                input_reference = child.get("input_artifact")
                if child_status != "pending" or input_reference is not None:
                    input_value = self.store.load_json(
                        input_reference, expected_task_id=state_id
                    )
                    expected_state = self._loop_state_value(
                        node, entry, record, step_index
                    )
                    if canonical_json_bytes(input_value) != canonical_json_bytes(
                        expected_state
                    ):
                        raise ControlFlowError(
                            f"bounded loop state input content is invalid: {child_id}"
                        )
                    if child_id.casefold() not in claimed_folded:
                        raise ControlFlowError(
                            f"bounded loop started child is not claimed: {child_id}"
                        )
                if child_status == SUCCESS:
                    output_value = self.store.load_json(
                        child.get("output_artifact"), expected_task_id=child_id
                    )
                    agent_entry = child.get("agent_entry")
                    if (
                        not isinstance(agent_entry, dict)
                        or agent_entry.get("id") != child_id
                        or agent_entry.get("status") != SUCCESS
                        or agent_entry.get("output_artifact")
                        != child.get("output_artifact")
                        or child.get("output")
                        != choose_public_output(
                            output_value,
                            child["output_artifact"],
                            inline_limit=self.limits.max_upstream_inline_bytes,
                        )
                        or agent_entry.get("output") != child.get("output")
                    ):
                        raise ControlFlowError(
                            f"bounded loop successful child entry is invalid: {child_id}"
                        )

            first_non_success = next(
                (index for index, value in enumerate(statuses) if value != SUCCESS),
                len(statuses),
            )
            tail = statuses[first_non_success:]
            if tail:
                if tail[0] not in {
                    "pending",
                    "running",
                    "failed",
                    "cancelled",
                    "needs_escalation",
                } or any(value != "pending" for value in tail[1:]):
                    raise ControlFlowError(
                        f"bounded loop child status prefix is invalid: {loop_id} iteration {record_index}"
                    )
            if statuses.count("running") > 1:
                raise ControlFlowError(
                    f"bounded loop iteration has multiple running children: {loop_id}"
                )

            if record_index <= completed_count:
                if record.get("status") != "completed" or any(
                    value != SUCCESS for value in statuses
                ):
                    raise ControlFlowError(
                        f"completed bounded loop iteration is inconsistent: {loop_id}"
                    )
                candidate_id = expected_ids[-2]
                verifier_id = expected_ids[-1]
                candidate_ref = children[candidate_id]["output_artifact"]
                verifier_ref = children[verifier_id]["output_artifact"]
                candidate = self.store.load_json(
                    candidate_ref, expected_task_id=candidate_id
                )
                verifier = self.store.load_json(
                    verifier_ref, expected_task_id=verifier_id
                )
                digest = hashlib.sha256(
                    canonical_json_bytes(candidate)
                ).hexdigest()
                if (
                    record.get("progress_digest") != digest
                    or record.get("candidate_artifact") != candidate_ref
                    or record.get("verifier_artifact") != verifier_ref
                    or not isinstance(verifier, dict)
                    or record.get("verdict") != verifier.get("verdict")
                    or record.get("verifier_summary")
                    != verifier.get("summary", "")[:1000]
                    or not isinstance(record.get("decision_applied"), bool)
                ):
                    raise ControlFlowError(
                        f"bounded loop completed iteration artifact identity is invalid: {loop_id}"
                    )
                computed_progress.append(digest)
            elif record.get("status") != "running":
                raise ControlFlowError(
                    f"partial bounded loop iteration must be running: {loop_id}"
                )
        if set(children) != expected_children or computed_progress != progress:
            raise ControlFlowError(
                f"bounded loop children or progress digest mismatch: {loop_id}"
            )
        if current != max(1, len(records)):
            raise ControlFlowError(
                f"bounded loop current_iteration is inconsistent: {loop_id}"
            )
        if state in TERMINAL_STATES:
            if entry.get("output_artifact") is None:
                raise ControlFlowError(
                    f"bounded loop terminal manifest is missing: {loop_id}"
                )
            manifest = self.store.load_json(
                entry["output_artifact"], expected_task_id=loop_id
            )
            if (
                manifest != self._loop_manifest(node, entry)
                or entry.get("output")
                != choose_public_output(
                    manifest,
                    entry["output_artifact"],
                    inline_limit=self.limits.max_upstream_inline_bytes,
                )
            ):
                raise ControlFlowError(
                    f"bounded loop terminal manifest is inconsistent: {loop_id}"
                )

    def _restore(self) -> None:
        try:
            checkpoint = self.state_store.load_checkpoint()
        except ValueError as exc:
            raise ControlFlowError(str(exc)) from exc
        if checkpoint.get("runtime") != "workflow-ir-v3":
            raise ControlFlowError("checkpoint belongs to a different runtime")
        if checkpoint.get("ir_digest") != self.ir_digest:
            raise ControlFlowError(
                "Workflow IR digest mismatch; refusing to resume a different plan"
            )
        try:
            persisted_ir = json.loads(
                (self.run_dir / "workflow-ir.resolved.json").read_text(
                    encoding="utf-8"
                )
            )
            summary = json.loads(
                (self.run_dir / "summary.json").read_text(encoding="utf-8")
            )
            events = self.state_store.validate_journal(
                expected_sequence=checkpoint["event_sequence"]
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ControlFlowError(f"cannot validate resume evidence: {exc}") from exc
        if _canonical_digest(persisted_ir) != _canonical_digest(self.ir):
            raise ControlFlowError("resolved Workflow IR differs from scheduler IR")
        entries = checkpoint.get("entries")
        states = checkpoint.get("states")
        claimed = checkpoint.get("claimed_agents", [])
        if not isinstance(entries, dict) or not isinstance(states, dict):
            raise ControlFlowError("checkpoint entries or states are malformed")
        if set(entries) != set(self.node_by_id) or set(states) != set(self.node_by_id):
            raise ControlFlowError("checkpoint node set differs from Workflow IR")
        if not isinstance(claimed, list) or any(
            not isinstance(item, str) for item in claimed
        ):
            raise ControlFlowError("checkpoint claimed_agents is malformed")
        claimed_folded = [item.casefold() for item in claimed]
        if len(claimed_folded) != len(set(claimed_folded)):
            raise ControlFlowError(
                "checkpoint claimed_agents contains a case-insensitive duplicate"
            )
        self.entries = entries
        self.states = states
        self.claimed_agents = set(claimed)
        if len(self.claimed_agents) > self.max_agents:
            raise AgentBudgetError("checkpoint exceeds the current agent budget")
        for node_id, node in self.node_by_id.items():
            entry = self.entries[node_id]
            state = self.states[node_id]
            if (
                not isinstance(entry, dict)
                or entry.get("id") != node_id
                or entry.get("kind") != node["kind"]
                or entry.get("status") != state
                or state not in TERMINAL_STATES | {"pending", "running", WAITING}
            ):
                raise ControlFlowError(
                    f"checkpoint state/entry identity is invalid for {node_id}"
                )
            _strict_resume_count(entry.get("resume_count", 0), f"node {node_id}")
            agent_entry = entry.get("agent_entry")
            if isinstance(agent_entry, dict):
                _strict_resume_count(
                    agent_entry.get("resume_count", 0),
                    f"node agent entry {node_id}",
                )

        started_sequences: dict[str, list[int]] = {
            node_id: [] for node_id in self.node_by_id
        }
        resumed_sequences = [
            event["sequence"]
            for event in events
            if event["type"] == "workflow.resumed"
        ]
        for event in events:
            if event["type"] != "workflow.node.started":
                continue
            payload = event.get("payload")
            if (
                not isinstance(payload, dict)
                or set(payload) != {"node_id", "kind"}
                or payload.get("node_id") not in self.node_by_id
                or payload.get("kind")
                != self.node_by_id[payload["node_id"]]["kind"]
            ):
                raise ControlFlowError(
                    "workflow node started event evidence is invalid"
                )
            started_sequences[payload["node_id"]].append(event["sequence"])
        for node_id, sequences in started_sequences.items():
            entry_started = self.entries[node_id].get("started")
            if entry_started is not None and (
                not isinstance(entry_started, str) or not entry_started
            ):
                raise ControlFlowError(
                    f"workflow node started timestamp is malformed: {node_id}"
                )
            if bool(sequences) != (entry_started is not None):
                raise ControlFlowError(
                    f"workflow node started event disagrees with checkpoint: {node_id}"
                )
            for previous, current in zip(sequences, sequences[1:]):
                if not any(
                    previous < resumed < current
                    for resumed in resumed_sequences
                ):
                    raise ControlFlowError(
                        f"workflow node started event multiplicity is invalid: {node_id}"
                    )
        self.started = checkpoint.get("started")
        if not isinstance(self.started, str) or not self.started:
            raise ControlFlowError("checkpoint started timestamp is malformed")
        checkpoint_finished = checkpoint.get("finished")
        if checkpoint_finished is not None and (
            not isinstance(checkpoint_finished, str) or not checkpoint_finished
        ):
            raise ControlFlowError("checkpoint finished timestamp is malformed")
        self.finished = checkpoint_finished

        timeout = self.ir["budgets"].get("workflow_timeout_seconds")
        resumed_now_epoch: int | None = None
        deadline_keys = {
            "workflow_started_epoch_ms",
            "workflow_deadline_epoch_ms",
            "workflow_last_observed_epoch_ms",
            "deadline_exceeded_recorded",
        }
        if timeout is None:
            if any(key in checkpoint for key in deadline_keys):
                raise ControlFlowError(
                    "checkpoint contains an undeclared workflow deadline"
                )
        else:
            started_epoch = checkpoint.get("workflow_started_epoch_ms")
            deadline_epoch = checkpoint.get("workflow_deadline_epoch_ms")
            last_observed_epoch = checkpoint.get(
                "workflow_last_observed_epoch_ms"
            )
            recorded = checkpoint.get("deadline_exceeded_recorded")
            if (
                isinstance(started_epoch, bool)
                or not isinstance(started_epoch, int)
                or isinstance(deadline_epoch, bool)
                or not isinstance(deadline_epoch, int)
                or isinstance(last_observed_epoch, bool)
                or not isinstance(last_observed_epoch, int)
                or last_observed_epoch < started_epoch
                or deadline_epoch - started_epoch != timeout * 1000
                or not isinstance(recorded, bool)
            ):
                raise ControlFlowError("checkpoint workflow deadline is malformed")
            now_epoch = checked_epoch_ms(self.clock)
            if now_epoch < last_observed_epoch:
                raise ControlFlowError(
                    "deadline clock moved backwards since the persisted observation"
                )
            created = [event for event in events if event["type"] == "workflow.created"]
            deadline_events = [
                event
                for event in events
                if event["type"] == "workflow.deadline.exceeded"
            ]
            deadline_context_statuses = {
                node_id: entry.get("status")
                for node_id, entry in self.entries.items()
            }
            for entry in self.entries.values():
                children = entry.get("children")
                if not isinstance(children, dict):
                    continue
                deadline_context_statuses.update(
                    {
                        child_id: child.get("status")
                        for child_id, child in children.items()
                        if isinstance(child_id, str) and isinstance(child, dict)
                    }
                )
            expected_created_payload = {
                "name": self.ir["name"],
                "ir_digest": self.ir_digest,
                "workflow_started_epoch_ms": started_epoch,
                "workflow_deadline_epoch_ms": deadline_epoch,
            }
            if (
                len(created) != 1
                or created[0]["payload"] != expected_created_payload
                or len(deadline_events) != int(recorded)
            ):
                raise ControlFlowError(
                    "workflow deadline evidence does not match checkpoint"
                )
            if deadline_events:
                deadline_payload = deadline_events[0].get("payload")
                if (
                    not isinstance(deadline_payload, dict)
                    or set(deadline_payload)
                    != {"agent_id", "workflow_deadline_epoch_ms"}
                    or deadline_payload.get("workflow_deadline_epoch_ms")
                    != deadline_epoch
                    or isinstance(deadline_payload.get("agent_id"), bool)
                    or not isinstance(deadline_payload.get("agent_id"), str)
                    or not deadline_payload["agent_id"]
                    or deadline_context_statuses.get(
                        deadline_payload["agent_id"]
                    )
                    != "needs_escalation"
                ):
                    raise ControlFlowError(
                        "workflow deadline event payload does not match checkpoint"
                    )
            self.workflow_started_epoch_ms = started_epoch
            self.workflow_deadline_epoch_ms = deadline_epoch
            self.workflow_last_observed_epoch_ms = last_observed_epoch
            self.deadline_exceeded_recorded = recorded
            resumed_now_epoch = now_epoch

        if (
            not isinstance(summary, dict)
            or canonical_json_bytes(summary)
            != canonical_json_bytes(self._summary())
        ):
            raise ControlFlowError("summary does not match checkpoint state")
        if resumed_now_epoch is not None:
            self.workflow_last_observed_epoch_ms = resumed_now_epoch

        for node_id, state in self.states.items():
            if state == SUCCESS:
                self._validate_successful_top_entry(
                    node_id, self.entries[node_id]
                )
        self.results = {
            node_id: _entry_record(self.entries[node_id])
            for node_id, state in self.states.items()
            if state == SUCCESS
        }
        for loop_id in self.bounded_loops:
            try:
                self._validate_loop_resume_entry(
                    self.node_by_id[loop_id],
                    self.entries[loop_id],
                    self.states[loop_id],
                    set(claimed_folded),
                )
            except ArtifactLimitError as exc:
                raise ControlFlowError(
                    f"bounded loop artifact evidence is invalid: {exc}"
                ) from exc
            self._validate_loop_events(
                self.node_by_id[loop_id],
                self.entries[loop_id],
                self.states[loop_id],
                events,
            )

        completed_payloads: dict[str, dict[str, Any]] = {}
        for event in events:
            if event["type"] != "workflow.node.completed":
                continue
            payload = event.get("payload")
            node_id = payload.get("node_id") if isinstance(payload, dict) else None
            if node_id not in self.node_by_id or node_id in completed_payloads:
                raise ControlFlowError(
                    "workflow node completion event evidence is invalid"
                )
            expected_payload = {
                "node_id": node_id,
                "kind": self.node_by_id[node_id]["kind"],
                "status": self.entries[node_id]["status"],
                "error": self.entries[node_id].get("error"),
            }
            if canonical_json_bytes(payload) != canonical_json_bytes(
                expected_payload
            ):
                raise ControlFlowError(
                    f"workflow node completion event disagrees with checkpoint: {node_id}"
                )
            if (
                not started_sequences[node_id]
                or event["sequence"] <= started_sequences[node_id][-1]
            ):
                raise ControlFlowError(
                    f"workflow node completion lifecycle is invalid: {node_id}"
                )
            completed_payloads[node_id] = payload
        self.completed_node_events = set(completed_payloads)
        self.pending_node_completion_reconciliation = []
        for loop_id in self.bounded_loops:
            entry = self.entries[loop_id]
            state = self.states[loop_id]
            if (
                state not in {SUCCESS, "failed", "cancelled", "needs_escalation"}
                or entry.get("output_artifact") is None
            ):
                continue
            finished = entry.get("finished")
            if finished is not None and (
                not isinstance(finished, str) or not finished
            ):
                raise ControlFlowError(
                    f"bounded loop terminal timestamp is malformed: {loop_id}"
                )
            if loop_id in self.completed_node_events:
                if finished is None:
                    raise ControlFlowError(
                        f"bounded loop completed event lacks terminal timestamp: {loop_id}"
                    )
            elif entry.get("started") is not None:
                # Scheduler-boundary expiry may stop a loop before it ever starts;
                # workflow.loop.stopped is its terminal evidence in that case.
                self.pending_node_completion_reconciliation.append(loop_id)

        self.pending_deadline_event_reconciliation = None
        if (
            self.workflow_deadline_epoch_ms is not None
            and not self.deadline_exceeded_recorded
        ):
            deadline_candidates = [
                node_id
                for node_id in self.node_order
                if self.entries[node_id].get("status") == "needs_escalation"
                and (
                    self.entries[node_id].get("stop_reason")
                    == "workflow_deadline"
                    or self.entries[node_id].get("error")
                    in {
                        "absolute workflow deadline exceeded",
                        "absolute workflow deadline exceeded before dispatch",
                    }
                )
            ]
            if deadline_candidates:
                if (
                    resumed_now_epoch is None
                    or resumed_now_epoch < self.workflow_deadline_epoch_ms
                ):
                    raise ControlFlowError(
                        "terminal workflow deadline evidence precedes the deadline"
                    )
                self.pending_deadline_event_reconciliation = (
                    deadline_candidates[0]
                )

        known_claims = {
            node_id.casefold()
            for node_id, node in self.node_by_id.items()
            if node["kind"] in {"agent", "reduce"}
            and node_id.casefold() not in self.loop_template_ids
        }
        known_claims.update(
            child_id.casefold()
            for entry in self.entries.values()
            for child_id in entry.get("children", {})
        )
        if not set(claimed_folded) <= known_claims:
            raise ControlFlowError("checkpoint contains an unknown agent claim")

        for node_id, state in list(self.states.items()):
            if state in {"running", WAITING}:
                self.states[node_id] = "pending"
                self.entries[node_id]["status"] = "pending"
                if state == "running":
                    self.entries[node_id]["resume_count"] = (
                        _strict_resume_count(
                            self.entries[node_id].get("resume_count", 0),
                            f"node {node_id}",
                        )
                        + 1
                    )
                    agent_entry = self.entries[node_id].get("agent_entry")
                    if (
                        isinstance(agent_entry, dict)
                        and agent_entry.get("status") == "running"
                    ):
                        agent_entry["resume_count"] = (
                            _strict_resume_count(
                                agent_entry.get("resume_count", 0),
                                f"node agent entry {node_id}",
                            )
                            + 1
                        )
                for child in self.entries[node_id].get("children", {}).values():
                    if child.get("status") == "running":
                        child["status"] = "pending"
                        child["error"] = "requeued by explicit resume"
                        child["resume_count"] = (
                            _strict_resume_count(
                                child.get("resume_count", 0),
                                f"loop child {child.get('id')}",
                            )
                            + 1
                        )
                        agent_entry = child.get("agent_entry")
                        if (
                            isinstance(agent_entry, dict)
                            and agent_entry.get("status") == "running"
                        ):
                            agent_entry["resume_count"] = (
                                _strict_resume_count(
                                    agent_entry.get("resume_count", 0),
                                    f"loop child agent entry {child.get('id')}",
                                )
                                + 1
                            )
        self.results = {
            node_id: _entry_record(self.entries[node_id])
            for node_id, state in self.states.items()
            if state == SUCCESS
        }

    async def run(self, *, resume: bool = False) -> dict[str, Any]:
        try:
            with RunLease(self.run_dir):
                # Construction is intentionally read-only and may precede another
                # process releasing the lease. Refresh journal sequence only after
                # exclusivity is established.
                self.state_store = RunStateStore(
                    self.run_dir,
                    max_event_bytes=self.limits.max_event_bytes,
                    max_run_artifact_bytes=self.limits.max_run_artifact_bytes,
                )
                return await self._run_under_lease(resume=resume)
        except (RunLeaseError, UnsafeRunPathError) as exc:
            raise ControlFlowError(str(exc)) from exc

    async def _run_under_lease(self, *, resume: bool = False) -> dict[str, Any]:
        if resume:
            if not self.run_dir.is_dir():
                raise ControlFlowError(
                    f"resume directory does not exist: {self.run_dir}"
                )
            if self.cancel_path.exists():
                raise ControlFlowError(
                    "CANCEL marker is present; remove it only after reviewing the run"
                )
            assert_safe_run_tree(self.run_dir)
            self._restore()
            if self.pending_deadline_event_reconciliation is not None:
                await self._record_deadline_exceeded(
                    self.pending_deadline_event_reconciliation
                )
                self.pending_deadline_event_reconciliation = None
            self.state_store.append_event(
                "workflow.resumed",
                {
                    "ir_digest": self.ir_digest,
                    "pending_nodes": [
                        node_id
                        for node_id, state in self.states.items()
                        if state == "pending"
                    ],
                },
            )
            for node_id in self.pending_node_completion_reconciliation:
                entry = self.entries[node_id]
                entry["finished"] = entry.get("finished") or now_iso()
                await self._record_node_completed(self.node_by_id[node_id], entry)
            self.pending_node_completion_reconciliation = []
        else:
            try:
                self.run_dir.mkdir(parents=True, exist_ok=False)
                (self.run_dir / "tasks").mkdir()
            except FileExistsError as exc:
                raise ControlFlowError(
                    f"run directory already exists: {self.run_dir}"
                ) from exc
            assert_safe_run_tree(self.run_dir)
            self.started = now_iso()
            workflow_timeout = self.ir["budgets"].get(
                "workflow_timeout_seconds"
            )
            if workflow_timeout is not None:
                self.workflow_started_epoch_ms = checked_epoch_ms(self.clock)
                self.workflow_last_observed_epoch_ms = (
                    self.workflow_started_epoch_ms
                )
                self.workflow_deadline_epoch_ms = (
                    self.workflow_started_epoch_ms + workflow_timeout * 1000
                )
            self.entries = {
                node["id"]: _base_node_entry(node) for node in self.ir["nodes"]
            }
            self.states = {node_id: "pending" for node_id in self.node_by_id}
            _bounded_json_write(
                self.run_dir / "workflow-ir.resolved.json",
                self.ir,
                run_dir=self.run_dir,
                limits=self.limits,
                label="resolved Workflow IR write",
            )
            created_payload = {
                "name": self.ir["name"],
                "ir_digest": self.ir_digest,
            }
            if self.workflow_deadline_epoch_ms is not None:
                created_payload.update(
                    {
                        "workflow_started_epoch_ms": self.workflow_started_epoch_ms,
                        "workflow_deadline_epoch_ms": self.workflow_deadline_epoch_ms,
                    }
                )
            self.state_store.append_event("workflow.created", created_payload)
        await self._snapshot()
        if resume and self.finished is not None and not any(
            state in {"pending", "running", WAITING}
            for state in self.states.values()
        ):
            return self._summary()

        running: dict[str, asyncio.Task[dict[str, Any]]] = {}
        try:
            while any(
                state in {"pending", "running"} for state in self.states.values()
            ):
                changed = False
                if self.cancel_path.exists():
                    for task in running.values():
                        task.cancel()
                    if running:
                        await asyncio.gather(*running.values(), return_exceptions=True)
                    for node_id, state in list(self.states.items()):
                        if state in {"pending", "running"}:
                            self.states[node_id] = "cancelled"
                            self.entries[node_id]["status"] = "cancelled"
                            self.entries[node_id]["error"] = (
                                "CANCEL marker during Workflow IR execution"
                            )
                            self.entries[node_id]["finished"] = now_iso()
                    running.clear()
                    await self._event(
                        "workflow.cancelled", {"states": dict(self.states)}
                    )
                    break

                propagated = True
                while propagated:
                    propagated = False
                    for node_id, state in list(self.states.items()):
                        if state != "pending":
                            continue
                        node = self.node_by_id[node_id]
                        dependencies = node["depends_on"]
                        failed = [
                            dependency
                            for dependency in dependencies
                            if self.states[dependency] in DEPENDENCY_FAILURE_STATES
                        ]
                        if failed:
                            self.states[node_id] = "blocked"
                            entry = self.entries[node_id]
                            entry["status"] = "blocked"
                            entry["error"] = (
                                "upstream non-success: " + ", ".join(failed)
                            )
                            entry["finished"] = now_iso()
                            self.state_store.append_event(
                                "workflow.node.blocked",
                                {"node_id": node_id, "dependencies": failed},
                            )
                            propagated = True
                            changed = True
                            continue

                        skipped = [
                            dependency
                            for dependency in dependencies
                            if self.states[dependency] == SKIPPED
                        ]
                        if not skipped:
                            continue
                        policy = node.get(
                            "dependency_policy", DEFAULT_DEPENDENCY_POLICY
                        )
                        dependency_states = [
                            self.states[dependency] for dependency in dependencies
                        ]
                        all_resolved = all(
                            dependency_state in {SUCCESS, SKIPPED}
                            for dependency_state in dependency_states
                        )
                        join_has_success = any(
                            dependency_state == SUCCESS
                            for dependency_state in dependency_states
                        )
                        if policy == JOIN_DEPENDENCY_POLICY and (
                            not all_resolved or join_has_success
                        ):
                            continue
                        self.states[node_id] = SKIPPED
                        entry = self.entries[node_id]
                        entry["status"] = SKIPPED
                        entry["error"] = (
                            "upstream branch was skipped: " + ", ".join(skipped)
                        )
                        entry["finished"] = now_iso()
                        self.state_store.append_event(
                            "workflow.node.skipped",
                            {
                                "node_id": node_id,
                                "dependencies": skipped,
                                "reason": "upstream_skipped",
                            },
                        )
                        propagated = True
                        changed = True

                ready = []
                for node_id in self.node_order:
                    if self.states[node_id] != "pending":
                        continue
                    node = self.node_by_id[node_id]
                    dependencies = node["depends_on"]
                    dependency_states = [
                        self.states[dependency] for dependency in dependencies
                    ]
                    policy = node.get(
                        "dependency_policy", DEFAULT_DEPENDENCY_POLICY
                    )
                    if policy == JOIN_DEPENDENCY_POLICY:
                        is_ready = (
                            all(
                                dependency_state in {SUCCESS, SKIPPED}
                                for dependency_state in dependency_states
                            )
                            and any(
                                dependency_state == SUCCESS
                                for dependency_state in dependency_states
                            )
                        )
                    else:
                        is_ready = all(
                            dependency_state == SUCCESS
                            for dependency_state in dependency_states
                        )
                    if is_ready:
                        ready.append(node_id)
                while ready and len(running) < self.max_concurrency:
                    if (
                        self.workflow_deadline_epoch_ms is not None
                        and self._agent_runtime_metadata() is None
                    ):
                        await self._expire_nonterminal_for_deadline(ready[0])
                        ready.clear()
                        changed = True
                        break
                    node_id = ready.pop(0)
                    self.states[node_id] = "running"
                    self.entries[node_id]["status"] = "running"
                    running[node_id] = asyncio.create_task(
                        self._execute_node(node_id)
                    )
                    changed = True

                if changed:
                    await self._snapshot()
                if running:
                    done, _ = await asyncio.wait(
                        set(running.values()),
                        timeout=1.0,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for completed in done:
                        node_id = next(
                            key for key, value in running.items() if value is completed
                        )
                        del running[node_id]
                        try:
                            entry = completed.result()
                        except Exception as exc:
                            entry = _base_node_entry(self.node_by_id[node_id])
                            entry["status"] = "failed"
                            entry["error"] = (
                                f"runtime internal error: {type(exc).__name__}: {exc}"
                            )
                            entry["started"] = now_iso()
                            entry["finished"] = now_iso()
                        self.entries[node_id] = entry
                        self.states[node_id] = entry["status"]
                        await self._snapshot()
                elif any(state == WAITING for state in self.states.values()):
                    break
                elif any(state == "pending" for state in self.states.values()):
                    raise ControlFlowError(
                        "scheduler has pending nodes but no ready or running node"
                    )
        except BaseException:
            for task in running.values():
                task.cancel()
            if running:
                await asyncio.gather(*running.values(), return_exceptions=True)
            with contextlib.suppress(Exception):
                self.state_store.append_event(
                    "workflow.interrupted", {"states": dict(self.states)}
                )
            with contextlib.suppress(Exception):
                await self._snapshot()
            raise

        waiting_nodes = [
            node_id for node_id, state in self.states.items() if state == WAITING
        ]
        if waiting_nodes:
            self.finished = None
            self.state_store.append_event(
                "workflow.paused",
                {"waiting_nodes": waiting_nodes, "states": dict(self.states)},
            )
            await self._snapshot()
            return self._summary()

        self.finished = now_iso()
        self.state_store.append_event(
            "workflow.completed", {"states": dict(self.states)}
        )
        await self._snapshot()
        return self._summary()



# Imported late to keep the main implementation's dependency list explicit.
import contextlib  # noqa: E402
