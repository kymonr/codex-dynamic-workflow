"""Versioned Workflow IR v3 foundations.

The v3 IR is intentionally declarative.  It can represent future dynamic
control-flow nodes without executing arbitrary model-authored Python or
JavaScript.  The current compiler executes only the static ``agent`` subset and
reports every dynamic node kind explicitly.
"""

from __future__ import annotations

import re
from typing import Any

IR_VERSION = 3
IR_MODES = {"direct", "delegate", "workflow"}
NODE_KINDS = {
    "agent",
    "map",
    "verify",
    "loop",
    "reduce",
    "conditional",
    "human_gate",
}
AGENT_PROFILES = {"spark", "luna", "sol"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
NODE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TOP_KEYS = {
    "version",
    "name",
    "mode",
    "objective",
    "workdir",
    "budgets",
    "nodes",
}
NODE_KEYS = {"id", "kind", "depends_on", "config"}
BUDGET_DEFAULTS = {
    "max_agents": 12,
    "max_concurrency": 4,
    "max_iterations": 3,
    "max_tokens": 200_000,
    "soft_timeout_seconds": 900,
    "hard_timeout_seconds": 3600,
}
BUDGET_RANGES = {
    "max_agents": (1, 64),
    "max_concurrency": (1, 16),
    "max_iterations": (1, 20),
    "max_tokens": (1, 20_000_000),
    "soft_timeout_seconds": (30, 7200),
    "hard_timeout_seconds": (60, 86400),
}


class WorkflowIRValidationError(ValueError):
    pass


def _integer(value: Any, where: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkflowIRValidationError(f"{where} must be an integer")
    if not minimum <= value <= maximum:
        raise WorkflowIRValidationError(
            f"{where} must be between {minimum} and {maximum}"
        )
    return value


def _validate_budgets(raw: Any) -> dict[str, int]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise WorkflowIRValidationError("budgets must be an object")
    unknown = sorted(set(raw) - set(BUDGET_DEFAULTS))
    if unknown:
        raise WorkflowIRValidationError(f"unknown budget keys: {unknown}")
    budgets: dict[str, int] = {}
    for key, default in BUDGET_DEFAULTS.items():
        minimum, maximum = BUDGET_RANGES[key]
        budgets[key] = _integer(raw.get(key, default), f"budgets.{key}", minimum, maximum)
    if budgets["hard_timeout_seconds"] < budgets["soft_timeout_seconds"] * 2:
        raise WorkflowIRValidationError(
            "hard_timeout_seconds must be at least twice soft_timeout_seconds"
        )
    if budgets["max_concurrency"] > budgets["max_agents"]:
        raise WorkflowIRValidationError(
            "max_concurrency cannot exceed max_agents"
        )
    return budgets


def _validate_agent_config(config: dict[str, Any], where: str) -> dict[str, Any]:
    allowed = {"profile", "prompt", "route_reason", "output_schema", "access"}
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise WorkflowIRValidationError(f"{where} has unknown keys: {unknown}")
    profile = config.get("profile", "luna")
    if profile not in AGENT_PROFILES:
        raise WorkflowIRValidationError(
            f"{where}.profile must be spark, luna, or sol"
        )
    prompt = config.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise WorkflowIRValidationError(f"{where}.prompt must be non-empty")
    access = config.get("access", "read_only")
    if access not in {"read_only", "scoped_writer"}:
        raise WorkflowIRValidationError(
            f"{where}.access must be read_only or scoped_writer"
        )
    if access == "scoped_writer":
        raise WorkflowIRValidationError(
            "Workflow IR v3 execution foundation is read-only; scoped_writer is reserved"
        )
    output_schema = config.get("output_schema")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise WorkflowIRValidationError(
            f"{where}.output_schema must be an object"
        )
    return {
        "profile": profile,
        "prompt": prompt,
        "route_reason": config.get(
            "route_reason", "Workflow IR v3 static agent node"
        ),
        "output_schema": output_schema,
        "access": access,
    }


def _validate_dynamic_config(kind: str, config: dict[str, Any], where: str) -> dict[str, Any]:
    if kind == "map":
        if not isinstance(config.get("over"), str) or not config["over"].strip():
            raise WorkflowIRValidationError(f"{where}.over must be non-empty")
        if not isinstance(config.get("template"), dict):
            raise WorkflowIRValidationError(f"{where}.template must be an object")
    elif kind == "verify":
        if not isinstance(config.get("target"), str) or not config["target"].strip():
            raise WorkflowIRValidationError(f"{where}.target must be non-empty")
    elif kind == "loop":
        iterations = config.get("max_iterations")
        if iterations is not None:
            _integer(iterations, f"{where}.max_iterations", 1, 20)
        if not isinstance(config.get("body"), list) or not config["body"]:
            raise WorkflowIRValidationError(f"{where}.body must be a non-empty list")
    elif kind == "reduce":
        if not isinstance(config.get("over"), str) or not config["over"].strip():
            raise WorkflowIRValidationError(f"{where}.over must be non-empty")
    elif kind == "conditional":
        if not isinstance(config.get("condition"), str) or not config["condition"].strip():
            raise WorkflowIRValidationError(f"{where}.condition must be non-empty")
    elif kind == "human_gate":
        if not isinstance(config.get("prompt"), str) or not config["prompt"].strip():
            raise WorkflowIRValidationError(f"{where}.prompt must be non-empty")
    return dict(config)


def _validate_dag(nodes: list[dict[str, Any]]) -> None:
    ids = {node["id"] for node in nodes}
    indegree = {node["id"]: len(node["depends_on"]) for node in nodes}
    children = {node_id: [] for node_id in ids}
    for node in nodes:
        for dependency in node["depends_on"]:
            if dependency not in ids:
                raise WorkflowIRValidationError(
                    f"node {node['id']} depends on unknown node {dependency}"
                )
            if dependency == node["id"]:
                raise WorkflowIRValidationError(
                    f"node {node['id']} cannot depend on itself"
                )
            children[dependency].append(node["id"])
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited != len(nodes):
        cycle = sorted(node_id for node_id, degree in indegree.items() if degree)
        raise WorkflowIRValidationError(f"Workflow IR contains a cycle: {cycle}")


def validate_workflow_ir(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise WorkflowIRValidationError("Workflow IR must be an object")
    unknown = sorted(set(raw) - TOP_KEYS)
    if unknown:
        raise WorkflowIRValidationError(f"unknown Workflow IR keys: {unknown}")
    if raw.get("version") != IR_VERSION or isinstance(raw.get("version"), bool):
        raise WorkflowIRValidationError(f"Workflow IR version must be {IR_VERSION}")
    name = raw.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise WorkflowIRValidationError(
            "name must be 1-50 lowercase letters, digits, or hyphens"
        )
    mode = raw.get("mode", "workflow")
    if mode not in IR_MODES:
        raise WorkflowIRValidationError(f"mode must be one of {sorted(IR_MODES)}")
    objective = raw.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise WorkflowIRValidationError("objective must be non-empty")
    workdir = raw.get("workdir")
    if not isinstance(workdir, str) or not workdir.strip():
        raise WorkflowIRValidationError("workdir must be non-empty")
    budgets = _validate_budgets(raw.get("budgets"))

    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise WorkflowIRValidationError("nodes must be a non-empty list")
    if len(raw_nodes) > budgets["max_agents"]:
        raise WorkflowIRValidationError(
            "node count exceeds budgets.max_agents"
        )

    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_node in enumerate(raw_nodes):
        where = f"nodes[{index}]"
        if not isinstance(raw_node, dict):
            raise WorkflowIRValidationError(f"{where} must be an object")
        unknown_node = sorted(set(raw_node) - NODE_KEYS)
        if unknown_node:
            raise WorkflowIRValidationError(
                f"{where} has unknown keys: {unknown_node}"
            )
        node_id = raw_node.get("id")
        if not isinstance(node_id, str) or not NODE_ID_RE.fullmatch(node_id):
            raise WorkflowIRValidationError(f"{where}.id is invalid")
        if node_id.casefold() in seen:
            raise WorkflowIRValidationError(
                f"duplicate node id under case-insensitive semantics: {node_id}"
            )
        seen.add(node_id.casefold())
        kind = raw_node.get("kind")
        if kind not in NODE_KINDS:
            raise WorkflowIRValidationError(
                f"{where}.kind must be one of {sorted(NODE_KINDS)}"
            )
        depends_on = raw_node.get("depends_on", [])
        if not isinstance(depends_on, list) or any(
            not isinstance(item, str) for item in depends_on
        ):
            raise WorkflowIRValidationError(
                f"{where}.depends_on must be a string list"
            )
        if len(depends_on) != len(set(depends_on)):
            raise WorkflowIRValidationError(
                f"{where}.depends_on contains duplicates"
            )
        config = raw_node.get("config", {})
        if not isinstance(config, dict):
            raise WorkflowIRValidationError(f"{where}.config must be an object")
        normalized_config = (
            _validate_agent_config(config, f"{where}.config")
            if kind == "agent"
            else _validate_dynamic_config(kind, config, f"{where}.config")
        )
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "depends_on": list(depends_on),
                "config": normalized_config,
            }
        )

    _validate_dag(nodes)
    return {
        "version": IR_VERSION,
        "name": name,
        "mode": mode,
        "objective": objective.strip(),
        "workdir": workdir,
        "budgets": budgets,
        "nodes": nodes,
        "execution": analyze_execution_support(nodes),
    }


def analyze_execution_support(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    dynamic = sorted({node["kind"] for node in nodes if node["kind"] != "agent"})
    return {
        "static_v2_compilable": not dynamic,
        "dynamic_node_kinds": dynamic,
        "runtime_version_required": 3 if dynamic else 2,
    }


def compile_static_ir_to_v2(ir: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_workflow_ir(ir) if ir.get("execution") is None else ir
    dynamic = normalized["execution"]["dynamic_node_kinds"]
    if dynamic:
        raise WorkflowIRValidationError(
            "dynamic Workflow IR nodes are validated but not executable yet: "
            + ", ".join(dynamic)
        )
    budgets = normalized["budgets"]
    tasks = []
    for node in normalized["nodes"]:
        config = node["config"]
        tasks.append(
            {
                "id": node["id"],
                "prompt": config["prompt"],
                "role": config["profile"],
                "route_reason": config["route_reason"],
                "depends_on": node["depends_on"],
                "output_schema": config["output_schema"],
                "allow_escalation": False,
            }
        )
    return {
        "version": 2,
        "name": normalized["name"],
        "workdir": normalized["workdir"],
        "max_concurrency": budgets["max_concurrency"],
        "soft_timeout_seconds": budgets["soft_timeout_seconds"],
        "hard_timeout_seconds": budgets["hard_timeout_seconds"],
        "tasks": tasks,
    }
