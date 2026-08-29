#!/usr/bin/env python3
"""Read-only Workflow IR plan preview and run-status commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

try:  # Package import from repository root.
    from skill.platform_paths import configure_utf8_stdio
    from skill import runner as legacy
    from skill.runtime.human_gate import HumanGateError, HumanGateStore
    from skill.runtime.limits import ArtifactLimitError, RuntimeLimits
    from skill.runtime.workflow_ir import (
        WorkflowIRValidationError,
        executable_bounded_loops,
        project_agent_claims,
        validate_workflow_ir,
    )
except ModuleNotFoundError:  # Installed skill directory.
    from platform_paths import configure_utf8_stdio
    import runner as legacy
    from runtime.human_gate import HumanGateError, HumanGateStore
    from runtime.limits import ArtifactLimitError, RuntimeLimits
    from runtime.workflow_ir import (
        WorkflowIRValidationError,
        executable_bounded_loops,
        project_agent_claims,
        validate_workflow_ir,
    )

MAX_INPUT_BYTES = 2 * 1024 * 1024
PROMPT_PREVIEW_CHARS = 160
KNOWN_STATES = (
    "pending",
    "running",
    "waiting",
    "succeeded",
    "skipped",
    "failed",
    "blocked",
    "cancelled",
    "needs_escalation",
)
ATTENTION_STATES = {"failed", "blocked", "cancelled", "needs_escalation"}
ACTIVE_STATES = {"pending", "running"}


class OpsCommandError(RuntimeError):
    """A read-only operational command cannot safely continue."""


def _workflow_ir_digest(ir: Mapping[str, Any]) -> str:
    payload = {
        key: ir[key]
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
        if key in ir
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(
    path: str | Path,
    *,
    label: str,
    required: bool = True,
) -> Any:
    source = Path(path)
    if not source.exists():
        if required:
            raise OpsCommandError(f"{label} does not exist: {source}")
        return None
    try:
        if source.is_symlink() or legacy._is_reparse(source):
            raise OpsCommandError(f"{label} cannot be a symlink or reparse point")
        if not source.is_file():
            raise OpsCommandError(f"{label} is not a regular file: {source}")
        size = source.stat().st_size
        if size > MAX_INPUT_BYTES:
            raise OpsCommandError(
                f"{label} exceeds {MAX_INPUT_BYTES} bytes: {source}"
            )
        return json.loads(source.read_text(encoding="utf-8"))
    except OpsCommandError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise OpsCommandError(f"cannot read {label} {source}: {exc}") from exc


def _topological_order(nodes: list[dict[str, Any]]) -> list[str]:
    position = {node["id"]: index for index, node in enumerate(nodes)}
    indegree = {node["id"]: len(node["depends_on"]) for node in nodes}
    children = {node["id"]: [] for node in nodes}
    for node in nodes:
        for dependency in node["depends_on"]:
            children[dependency].append(node["id"])
    ready = sorted(
        [node_id for node_id, degree in indegree.items() if degree == 0],
        key=position.__getitem__,
    )
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current], key=position.__getitem__):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=position.__getitem__)
    if len(ordered) != len(nodes):  # validate_workflow_ir already guards this.
        raise OpsCommandError("validated Workflow IR unexpectedly contains a cycle")
    return ordered


def _prompt_metadata(config: Mapping[str, Any]) -> dict[str, Any]:
    prompt = config.get("prompt")
    if not isinstance(prompt, str):
        return {
            "prompt_chars": 0,
            "prompt_sha256": None,
            "prompt_preview": None,
        }
    compact = " ".join(prompt.split())
    preview = compact[:PROMPT_PREVIEW_CHARS]
    if len(compact) > PROMPT_PREVIEW_CHARS:
        preview += "…"
    return {
        "prompt_chars": len(prompt),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_preview": preview,
    }


def _node_preview(
    node: dict[str, Any],
    *,
    executable_loop_ids: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    config = node["config"]
    preview: dict[str, Any] = {
        "id": node["id"],
        "kind": node["kind"],
        "depends_on": list(node["depends_on"]),
        "dependency_policy": node["dependency_policy"],
    }
    kind = node["kind"]
    if kind == "agent":
        preview.update(
            {
                "profile": config["profile"],
                "route_reason": config["route_reason"],
                "output_schema": config.get("output_schema") is not None,
                **_prompt_metadata(config),
            }
        )
    elif kind == "map":
        preview.update(
            {
                "source_node": config["over"],
                "item_limit": config["item_limit"],
                "template_profile": config["template"]["profile"],
                "output_schema": config["template"].get("output_schema") is not None,
                **_prompt_metadata(config["template"]),
            }
        )
    elif kind == "verify":
        preview.update(
            {
                "target_node": config["target"],
                "profile": config["profile"],
                "require_all": config["require_all"],
                **_prompt_metadata(config),
            }
        )
    elif kind == "reduce":
        preview.update(
            {
                "source_node": config["over"],
                "profile": config["profile"],
                "output_schema": config.get("output_schema") is not None,
                **_prompt_metadata(config),
            }
        )
    elif kind == "fleet_aggregate":
        preview.update(
            {
                "mode": config["mode"],
                "subject_id": config["subject_id"],
                "risk_level": config["risk_level"],
                "sol_policy": config["sol_policy"],
                "fleet_members": len(config["members"]),
                "discovery_members": sum(
                    member["stage"] == "discovery" for member in config["members"]
                ),
                "challenge_members": sum(
                    member["stage"] == "challenge" for member in config["members"]
                ),
            }
        )
    elif kind == "conditional":
        preview.update(
            {
                "condition": config["condition"],
                "then": list(config["then"]),
                "else": list(config["else"]),
            }
        )
    elif kind == "human_gate":
        preview.update(
            {
                "options": list(config["options"]),
                **_prompt_metadata(config),
            }
        )
    elif kind == "loop":
        is_executable = node["id"] in executable_loop_ids
        preview.update(
            {
                "executable_contract": (
                    "bounded-loop-v1" if is_executable else None
                ),
                "initial_source": (
                    node["depends_on"][0]
                    if is_executable and len(node["depends_on"]) == 1
                    else None
                ),
                "loop_claim_upper_bound": (
                    config["max_iterations"] * len(config["body"])
                    if is_executable
                    else 0
                ),
                "max_iterations": config["max_iterations"],
                "no_progress_limit": config.get("no_progress_limit"),
                "body": list(config["body"]),
                "stop_when": config["stop_when"],
            }
        )
    return preview


def _agent_claim_projection(ir: dict[str, Any]) -> dict[str, Any]:
    return dict(project_agent_claims(ir))


def _plan_preview(raw: Any) -> dict[str, Any]:
    ir = validate_workflow_ir(raw)
    try:
        resolved_limits = RuntimeLimits.from_mapping(ir.get("limits")).to_dict()
    except ValueError as exc:
        raise OpsCommandError(f"invalid Workflow IR limits: {exc}") from exc

    projection = _agent_claim_projection(ir)
    executable_loop_ids = set(
        executable_bounded_loops(ir["nodes"], ir["budgets"])
    )
    unsupported = list(ir["execution"]["unsupported_node_kinds"])
    warnings = [
        "budgets.max_tokens is advisory; missing CLI usage cannot enforce a hard stop",
        "plan-ir does not run allowed-root, sensitive-path, Codex identity, or external-model export preflight",
    ]
    if "workflow_timeout_seconds" in ir["budgets"]:
        warnings.append(
            "workflow_timeout_seconds is an absolute whole-workflow deadline; per-agent soft/hard timeouts are capped by its remaining time"
        )
    else:
        warnings.append(
            "soft_timeout_seconds and hard_timeout_seconds are per-agent, not whole-workflow wall-clock limits"
        )
    if unsupported:
        warnings.append(
            "validated-only node kinds prevent execution: " + ", ".join(unsupported)
        )
    if not projection["upper_bound_within_budget"]:
        warnings.append(
            "agent claim projection exceeds max_agents; run-ir rejects the current plan before any dispatch"
        )

    return {
        "operation": "plan-ir",
        "model_calls": 0,
        "writes": [],
        "version": ir["version"],
        "name": ir["name"],
        "mode": ir["mode"],
        "objective": ir["objective"],
        "workdir": ir["workdir"],
        "workdir_preflight": {
            "performed": False,
            "required_before_run": True,
        },
        "execution_supported": (
            not unsupported and projection["upper_bound_within_budget"]
        ),
        "execution_blockers": (
            []
            if projection["upper_bound_within_budget"]
            else ["agent_claim_projection_exceeds_max_agents"]
        ),
        "execution": ir["execution"],
        "budgets": ir["budgets"],
        "declared_limits": ir["limits"],
        "resolved_limits": resolved_limits,
        "agent_claim_projection": projection,
        "topological_order": _topological_order(ir["nodes"]),
        "nodes": [
            _node_preview(
                node,
                executable_loop_ids=executable_loop_ids,
            )
            for node in ir["nodes"]
        ],
        "warnings": warnings,
    }


def _safe_run_dir(raw: str | Path) -> Path:
    lexical = Path(raw).expanduser()
    try:
        legacy._assert_no_reparse_components(lexical, "run-status run-dir")
    except legacy.WorkflowError as exc:
        raise OpsCommandError(str(exc)) from exc
    candidate = lexical.resolve()
    runs_root = legacy._runs_root().resolve()
    if candidate == runs_root or not candidate.is_relative_to(runs_root):
        raise OpsCommandError(f"run directory must be a child of {runs_root}")
    if not candidate.is_dir():
        raise OpsCommandError(f"run directory does not exist: {candidate}")
    return candidate


def _validate_checkpoint(
    checkpoint: Any,
    *,
    expected_node_ids: set[str],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    if not isinstance(checkpoint, dict):
        raise OpsCommandError("checkpoint.json must contain an object")
    if checkpoint.get("runtime") != "workflow-ir-v3":
        raise OpsCommandError("checkpoint does not belong to Workflow IR v3")
    states = checkpoint.get("states")
    entries = checkpoint.get("entries")
    if not isinstance(states, dict) or not isinstance(entries, dict):
        raise OpsCommandError("checkpoint states or entries are malformed")
    if set(states) != expected_node_ids or set(entries) != expected_node_ids:
        raise OpsCommandError("checkpoint node set differs from resolved Workflow IR")
    normalized_states: dict[str, str] = {}
    normalized_entries: dict[str, dict[str, Any]] = {}
    for node_id in expected_node_ids:
        state = states[node_id]
        entry = entries[node_id]
        if not isinstance(state, str):
            raise OpsCommandError(f"checkpoint state is invalid for {node_id}")
        if not isinstance(entry, dict):
            raise OpsCommandError(f"checkpoint entry is invalid for {node_id}")
        if entry.get("id") != node_id:
            raise OpsCommandError(
                f"checkpoint entry id does not match its key: {node_id}"
            )
        if entry.get("status") != state:
            raise OpsCommandError(
                f"checkpoint entry status disagrees with states for {node_id}"
            )
        normalized_states[node_id] = state
        normalized_entries[node_id] = entry
    return normalized_states, normalized_entries


def _workflow_state(counts: Counter[str], total: int, finished: Any) -> str:
    if counts["waiting"]:
        return "paused"
    if any(counts[state] for state in ACTIVE_STATES):
        return "running"
    if any(counts[state] for state in ATTENTION_STATES):
        return "attention_required"
    if counts["succeeded"] + counts["skipped"] == total and finished:
        return "succeeded"
    return "unknown"


def _summary_consistency(
    summary: Any,
    checkpoint_states: Mapping[str, str],
) -> str:
    if summary is None:
        return "unavailable"
    if not isinstance(summary, dict) or not isinstance(summary.get("nodes"), list):
        return "malformed"
    observed: dict[str, str] = {}
    for node in summary["nodes"]:
        if not isinstance(node, dict):
            return "malformed"
        node_id = node.get("id")
        status = node.get("status")
        if not isinstance(node_id, str) or not isinstance(status, str):
            return "malformed"
        if node_id in observed:
            return "malformed"
        observed[node_id] = status
    return "match" if observed == dict(checkpoint_states) else "mismatch"


def _gate_status(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "node_id": record.get("node_id"),
        "status": record.get("status"),
        "options": record.get("options"),
        "decision": record.get("decision"),
        "input_identity": record.get("input_identity"),
        "actor": record.get("actor"),
        "source": record.get("source"),
        "opened_at": record.get("opened_at"),
        "updated_at": record.get("updated_at"),
    }


def _run_status(run_dir: str | Path, *, node_id: str | None = None) -> dict[str, Any]:
    candidate = _safe_run_dir(run_dir)
    raw_ir = _load_json(
        candidate / "workflow-ir.resolved.json",
        label="resolved Workflow IR",
    )
    if not isinstance(raw_ir, dict):
        raise OpsCommandError("resolved Workflow IR must contain an object")
    validation_input = dict(raw_ir)
    validation_input.pop("execution", None)
    ir = validate_workflow_ir(validation_input)
    try:
        limits = RuntimeLimits.from_mapping(raw_ir.get("limits"))
    except ValueError as exc:
        raise OpsCommandError(f"invalid resolved runtime limits: {exc}") from exc

    checkpoint = _load_json(candidate / "checkpoint.json", label="checkpoint")
    summary = _load_json(
        candidate / "summary.json",
        label="summary",
        required=False,
    )
    expected_node_ids = {node["id"] for node in ir["nodes"]}
    states, entries = _validate_checkpoint(
        checkpoint,
        expected_node_ids=expected_node_ids,
    )
    if node_id is not None and node_id not in expected_node_ids:
        raise OpsCommandError(f"unknown node id: {node_id}")

    selected_nodes: list[dict[str, Any]] = []
    for node in ir["nodes"]:
        current_id = node["id"]
        if node_id is not None and current_id != node_id:
            continue
        entry = entries[current_id]
        selected_nodes.append(
            {
                "id": current_id,
                "kind": node["kind"],
                "depends_on": list(node["depends_on"]),
                "dependency_policy": node["dependency_policy"],
                "status": states[current_id],
                "started": entry.get("started"),
                "finished": entry.get("finished"),
                "resume_count": entry.get("resume_count", 0),
                "error": entry.get("error"),
                "condition_state": (
                    entry.get("condition_outcome") or {}
                ).get("state"),
                "gate_status": (entry.get("gate") or {}).get("status"),
            }
        )

    counts = Counter(states.values())
    total = len(states)
    finished = checkpoint.get("finished")
    gate_store = HumanGateStore(candidate, limits)
    gates = [_gate_status(record) for record in gate_store.list_records()]
    summary_ir_digest = summary.get("ir_digest") if isinstance(summary, dict) else None
    checkpoint_ir_digest = checkpoint.get("ir_digest")
    if not isinstance(checkpoint_ir_digest, str) or not checkpoint_ir_digest:
        raise OpsCommandError("checkpoint ir_digest must be a non-empty string")
    resolved_ir_digest = _workflow_ir_digest(ir)

    return {
        "operation": "run-status",
        "model_calls": 0,
        "writes": [],
        "source_of_truth": "checkpoint.json",
        "run_dir": str(candidate),
        "name": ir["name"],
        "objective": ir["objective"],
        "workflow_state": _workflow_state(counts, total, finished),
        "started": checkpoint.get("started"),
        "finished": finished,
        "paused": counts["waiting"] > 0,
        "counts": {
            state: counts[state]
            for state in KNOWN_STATES
            if counts[state]
        },
        "unknown_state_count": sum(
            count for state, count in counts.items() if state not in KNOWN_STATES
        ),
        "resolved_ir_digest": resolved_ir_digest,
        "checkpoint_ir_digest": checkpoint_ir_digest,
        "summary_ir_digest": summary_ir_digest,
        "resolved_ir_digest_consistency": (
            "match"
            if resolved_ir_digest == checkpoint_ir_digest
            else "mismatch"
        ),
        "ir_digest_consistency": (
            "unavailable"
            if summary_ir_digest is None
            else "match"
            if summary_ir_digest == checkpoint_ir_digest
            else "mismatch"
        ),
        "summary_state_consistency": _summary_consistency(summary, states),
        "nodes": selected_nodes,
        "gates": gates,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="read-only Workflow IR plan preview and run status"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser(
        "plan-ir",
        help="validate and preview Workflow IR without model calls or writes",
    )
    plan.add_argument("--spec", required=True, help="Workflow IR v3 JSON file")

    status = subparsers.add_parser(
        "run-status",
        help="read checkpoint, summary, and gate metadata without advancing a run",
    )
    status.add_argument("--run-dir", required=True)
    status.add_argument("--node-id", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan-ir":
            result = _plan_preview(
                _load_json(args.spec, label="Workflow IR specification")
            )
        else:
            result = _run_status(args.run_dir, node_id=args.node_id)
    except (
        OpsCommandError,
        WorkflowIRValidationError,
        HumanGateError,
        ArtifactLimitError,
        legacy.WorkflowError,
        ValueError,
    ) as exc:
        print(f"workflow operation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
