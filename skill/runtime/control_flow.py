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
    choose_public_output,
    is_artifact_reference,
)
from .condition import evaluate_condition
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
from .state_store import RunStateStore, now_iso
from .workflow_ir import (
    DEFAULT_DEPENDENCY_POLICY,
    EXECUTABLE_NODE_KINDS,
    JOIN_DEPENDENCY_POLICY,
    TIMEOUT_SCOPE,
    TOKEN_BUDGET_MODE,
    VERIFICATION_RESULT_SCHEMA,
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


class ControlFlowError(RuntimeError):
    """The trusted control-flow runtime cannot safely continue."""


class AgentBudgetError(ControlFlowError):
    """Dynamic expansion exceeded the workflow's explicit agent budget."""


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
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    enforce_projected_write(
        run_dir,
        path,
        len(payload),
        limits.max_run_artifact_bytes,
        label,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
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
        store.resolve_reference(reference)
    else:
        reference = store.put_json(agent_id, normalized.get("output"))
        normalized["output_artifact"] = reference

    value = store.load_json(reference)
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

        self.run_dir = run_dir.resolve()
        self.execute_agent = execute_agent
        self.limits = limits
        self.node_by_id = {node["id"]: node for node in self.ir["nodes"]}
        self.node_order = [node["id"] for node in self.ir["nodes"]]
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
        record = self.results.get(node_id)
        if not isinstance(record, dict):
            raise ControlFlowError(f"node {node_id} has no accepted result")
        reference = record.get("artifact")
        if reference is not None:
            return self.store.load_json(reference)
        output = record.get("output")
        if is_artifact_reference(output):
            return self.store.load_json(output)
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
        return {
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
                "timeouts": TIMEOUT_SCOPE,
            },
            "limits": self.limits.to_dict(),
            "nodes": ordered,
        }

    def _snapshot_locked(self) -> None:
        summary = self._summary()
        _bounded_json_write(
            self.run_dir / "summary.json",
            summary,
            run_dir=self.run_dir,
            limits=self.limits,
            label="Workflow IR summary write",
        )
        self.state_store.write_checkpoint(
            {
                "runtime": "workflow-ir-v3",
                "ir_digest": self.ir_digest,
                "started": self.started,
                "finished": self.finished,
                "states": self.states,
                "entries": self.entries,
                "claimed_agents": sorted(self.claimed_agents),
            }
        )

    async def _snapshot(self) -> None:
        async with self.state_lock:
            self._snapshot_locked()

    async def _call_agent(
        self,
        task: dict[str, Any],
        results: dict[str, Any],
        prior_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        agent_id = task["id"]
        self._claim_agent(agent_id)
        if prior_entry and prior_entry.get("status") == SUCCESS:
            return _normalize_agent_entry(
                agent_id,
                prior_entry,
                store=self.store,
                limits=self.limits,
            )
        async with self.semaphore:
            raw = await self.execute_agent(task, results, prior_entry)
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
        agent_entry = await self._call_agent(task, dict(self.results), prior)
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
            agent_entry = await self._call_agent(task, results, prior)
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
            agent_entry = await self._call_agent(task, results, prior)
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
        agent_entry = await self._call_agent(task, dict(self.results), prior)
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
                self.store.resolve_reference(reference)
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
            entry["finished"] = now_iso()
            await self._event(
                "workflow.node.completed",
                {
                    "node_id": node_id,
                    "kind": node["kind"],
                    "status": entry["status"],
                    "error": entry.get("error"),
                },
            )
        return entry

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
        self.entries = entries
        self.states = states
        self.claimed_agents = set(claimed)
        if len(self.claimed_agents) > self.max_agents:
            raise AgentBudgetError("checkpoint exceeds the current agent budget")
        self.started = checkpoint.get("started") or now_iso()
        self.finished = None
        for node_id, state in list(self.states.items()):
            if state in {"running", WAITING}:
                self.states[node_id] = "pending"
                self.entries[node_id]["status"] = "pending"
                self.entries[node_id]["resume_count"] = int(
                    self.entries[node_id].get("resume_count", 0)
                ) + 1
                for child in self.entries[node_id].get("children", {}).values():
                    if child.get("status") == "running":
                        child["status"] = "pending"
                        child["error"] = "requeued by explicit resume"
        self.results = {
            node_id: _entry_record(self.entries[node_id])
            for node_id, state in self.states.items()
            if state == SUCCESS
        }

    async def run(self, *, resume: bool = False) -> dict[str, Any]:
        if resume:
            if not self.run_dir.is_dir():
                raise ControlFlowError(
                    f"resume directory does not exist: {self.run_dir}"
                )
            if self.cancel_path.exists():
                raise ControlFlowError(
                    "CANCEL marker is present; remove it only after reviewing the run"
                )
            self._restore()
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
        else:
            try:
                self.run_dir.mkdir(parents=True, exist_ok=False)
                (self.run_dir / "tasks").mkdir()
            except FileExistsError as exc:
                raise ControlFlowError(
                    f"run directory already exists: {self.run_dir}"
                ) from exc
            self.started = now_iso()
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
            self.state_store.append_event(
                "workflow.created",
                {"name": self.ir["name"], "ir_digest": self.ir_digest},
            )
        await self._snapshot()

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
