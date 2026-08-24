"""Versioned, declarative Workflow IR v3.

The IR is data, never authorization or executable source code. The trusted
runtime supports read-only ``agent``, ``map``, ``verify``, ``reduce``,
``conditional`` and ``human_gate`` nodes, plus loop declarations that satisfy
the complete Bounded Loop v1 contract. Legacy loop declarations remain
validated-only and are never silently migrated.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

try:
    from .condition import ConditionValidationError, validate_condition
except ImportError:  # Standalone policy-contract import.
    from condition import ConditionValidationError, validate_condition

IR_VERSION = 3
IR_MODES = {"direct", "delegate", "workflow"}
NODE_KIND_ORDER = (
    "agent",
    "map",
    "verify",
    "loop",
    "reduce",
    "conditional",
    "human_gate",
)
NODE_KINDS = set(NODE_KIND_ORDER)
EXECUTABLE_NODE_KIND_ORDER = NODE_KIND_ORDER
EXECUTABLE_NODE_KINDS = set(EXECUTABLE_NODE_KIND_ORDER)
DEPENDENCY_POLICIES = {"all_succeeded", "join"}
DEFAULT_DEPENDENCY_POLICY = "all_succeeded"
JOIN_DEPENDENCY_POLICY = "join"
TOKEN_BUDGET_MODE = "advisory"
TIMEOUT_SCOPE = "per_agent"
BOUNDED_LOOP_CONTRACT: dict[str, Any] = {
    "contract_version": 1,
    "body_kind": "agent_templates",
    "body_min": 2,
    "body_max": 8,
    "stop_when": "verification_accept",
    "no_progress": "canonical_sha256",
    "no_progress_default": 1,
    "no_progress_min": 1,
    "no_progress_max": 5,
    "resume_reuses_succeeded_steps": True,
    "deadline_mode": "absolute_epoch",
    "workflow_timeout_min_seconds": 60,
    "workflow_timeout_max_seconds": 172_800,
    "pause_counts_against_deadline": True,
    "arbitrary_expression": False,
}
AGENT_PROFILES = {"spark", "luna", "sol"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
NODE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
GATE_OPTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
TOP_KEYS = {
    "version",
    "name",
    "mode",
    "objective",
    "workdir",
    "budgets",
    "limits",
    "nodes",
}
NODE_KEYS = {"id", "kind", "depends_on", "dependency_policy", "config"}
LIMIT_KEYS = {
    "max_result_bytes",
    "max_log_bytes",
    "max_run_artifact_bytes",
    "max_upstream_inline_bytes",
    "max_event_bytes",
}
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
OPTIONAL_BUDGET_RANGES = {
    "workflow_timeout_seconds": (
        BOUNDED_LOOP_CONTRACT["workflow_timeout_min_seconds"],
        BOUNDED_LOOP_CONTRACT["workflow_timeout_max_seconds"],
    ),
}

VERIFICATION_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["accept", "reject", "unknown"],
        },
        "summary": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["verdict", "summary", "evidence"],
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


def _non_empty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowIRValidationError(f"{where} must be non-empty")
    return value.strip()


def _validate_budgets(raw: Any) -> dict[str, int]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise WorkflowIRValidationError("budgets must be an object")
    unknown = sorted(
        set(raw) - set(BUDGET_DEFAULTS) - set(OPTIONAL_BUDGET_RANGES)
    )
    if unknown:
        raise WorkflowIRValidationError(f"unknown budget keys: {unknown}")
    budgets: dict[str, int] = {}
    for key, default in BUDGET_DEFAULTS.items():
        minimum, maximum = BUDGET_RANGES[key]
        budgets[key] = _integer(
            raw.get(key, default), f"budgets.{key}", minimum, maximum
        )
    for key, (minimum, maximum) in OPTIONAL_BUDGET_RANGES.items():
        if key in raw:
            budgets[key] = _integer(
                raw[key], f"budgets.{key}", minimum, maximum
            )
    if budgets["hard_timeout_seconds"] < budgets["soft_timeout_seconds"] * 2:
        raise WorkflowIRValidationError(
            "hard_timeout_seconds must be at least twice soft_timeout_seconds"
        )
    if budgets["max_concurrency"] > budgets["max_agents"]:
        raise WorkflowIRValidationError(
            "max_concurrency cannot exceed max_agents"
        )
    return budgets


def _validate_limits(raw: Any) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise WorkflowIRValidationError("limits must be an object")
    unknown = sorted(set(raw) - LIMIT_KEYS)
    if unknown:
        raise WorkflowIRValidationError(f"unknown runtime limit keys: {unknown}")
    normalized: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise WorkflowIRValidationError(
                f"limits.{key} must be a positive integer"
            )
        normalized[key] = value
    return normalized


def _validate_route_reason(value: Any, where: str, default: str) -> str:
    if value is None:
        return default
    text = _non_empty_string(value, where)
    if len(text) > 1000:
        raise WorkflowIRValidationError(f"{where} exceeds 1000 characters")
    return text


def _validate_agent_config(
    config: dict[str, Any],
    where: str,
    *,
    require_placeholder: str | None = None,
    allowed_extra: set[str] | None = None,
) -> dict[str, Any]:
    allowed = {
        "profile",
        "prompt",
        "route_reason",
        "output_schema",
        "access",
    } | (allowed_extra or set())
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise WorkflowIRValidationError(f"{where} has unknown keys: {unknown}")
    profile = config.get("profile", "luna")
    if profile not in AGENT_PROFILES:
        raise WorkflowIRValidationError(
            f"{where}.profile must be spark, luna, or sol"
        )
    prompt = _non_empty_string(config.get("prompt"), f"{where}.prompt")
    if require_placeholder and "{{" + require_placeholder + "}}" not in prompt:
        raise WorkflowIRValidationError(
            f"{where}.prompt must contain {{{{{require_placeholder}}}}}"
        )
    access = config.get("access", "read_only")
    if access != "read_only":
        raise WorkflowIRValidationError(
            f"{where}.access must remain read_only in Workflow IR v3"
        )
    output_schema = config.get("output_schema")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise WorkflowIRValidationError(
            f"{where}.output_schema must be an object"
        )
    return {
        "profile": profile,
        "prompt": prompt,
        "route_reason": _validate_route_reason(
            config.get("route_reason"),
            f"{where}.route_reason",
            "Workflow IR v3 trusted agent node",
        ),
        "output_schema": output_schema,
        "access": "read_only",
    }


def _validate_map_config(
    config: dict[str, Any], where: str, budgets: dict[str, int]
) -> dict[str, Any]:
    allowed = {"over", "template", "item_limit"}
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise WorkflowIRValidationError(f"{where} has unknown keys: {unknown}")
    over = _non_empty_string(config.get("over"), f"{where}.over")
    template = config.get("template")
    if not isinstance(template, dict):
        raise WorkflowIRValidationError(f"{where}.template must be an object")
    normalized_template = _validate_agent_config(
        template,
        f"{where}.template",
        require_placeholder="item",
    )
    item_limit = _integer(
        config.get("item_limit", budgets["max_agents"]),
        f"{where}.item_limit",
        1,
        64,
    )
    return {
        "over": over,
        "template": normalized_template,
        "item_limit": item_limit,
    }


def _validate_verify_config(config: dict[str, Any], where: str) -> dict[str, Any]:
    allowed = {
        "target",
        "profile",
        "prompt",
        "route_reason",
        "access",
        "require_all",
        "output_schema",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise WorkflowIRValidationError(f"{where} has unknown keys: {unknown}")
    supplied_schema = config.get("output_schema")
    if supplied_schema is not None and supplied_schema != VERIFICATION_RESULT_SCHEMA:
        raise WorkflowIRValidationError(
            f"{where}.output_schema is fixed by the verifier runtime"
        )
    target = _non_empty_string(config.get("target"), f"{where}.target")
    agent = _validate_agent_config(
        {key: value for key, value in config.items() if key != "target" and key != "require_all"},
        where,
        require_placeholder="candidate",
    )
    require_all = config.get("require_all", True)
    if not isinstance(require_all, bool):
        raise WorkflowIRValidationError(f"{where}.require_all must be boolean")
    return {
        "target": target,
        "profile": agent["profile"],
        "prompt": agent["prompt"],
        "route_reason": agent["route_reason"],
        "access": "read_only",
        "require_all": require_all,
        "output_schema": VERIFICATION_RESULT_SCHEMA,
    }


def _validate_reduce_config(config: dict[str, Any], where: str) -> dict[str, Any]:
    allowed = {
        "over",
        "profile",
        "prompt",
        "route_reason",
        "output_schema",
        "access",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise WorkflowIRValidationError(f"{where} has unknown keys: {unknown}")
    over = _non_empty_string(config.get("over"), f"{where}.over")
    agent = _validate_agent_config(
        {key: value for key, value in config.items() if key != "over"},
        where,
    )
    if "{{source}}" not in agent["prompt"] and "{{manifest}}" not in agent["prompt"]:
        raise WorkflowIRValidationError(
            f"{where}.prompt must contain {{{{source}}}} or {{{{manifest}}}}"
        )
    return {"over": over, **agent}


def _validate_reserved_config(
    kind: str, config: dict[str, Any], where: str
) -> dict[str, Any]:
    if kind == "loop":
        allowed = {
            "max_iterations",
            "no_progress_limit",
            "body",
            "stop_when",
        }
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise WorkflowIRValidationError(
                f"{where} has unknown keys: {unknown}"
            )
        iterations = _integer(
            config.get("max_iterations", BUDGET_DEFAULTS["max_iterations"]),
            f"{where}.max_iterations",
            1,
            20,
        )
        body = config.get("body")
        if not isinstance(body, list) or not body or any(
            not isinstance(item, str) or not item for item in body
        ):
            raise WorkflowIRValidationError(
                f"{where}.body must be a non-empty string list"
            )
        stop_when = _non_empty_string(
            config.get("stop_when", "iteration_limit"),
            f"{where}.stop_when",
        )
        normalized = {
            "max_iterations": iterations,
            "body": list(body),
            "stop_when": stop_when,
        }
        if "no_progress_limit" in config:
            normalized["no_progress_limit"] = _integer(
                config["no_progress_limit"],
                f"{where}.no_progress_limit",
                BOUNDED_LOOP_CONTRACT["no_progress_min"],
                BOUNDED_LOOP_CONTRACT["no_progress_max"],
            )
        return normalized
    if kind == "conditional":
        allowed = {"condition", "then", "else"}
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise WorkflowIRValidationError(
                f"{where} has unknown keys: {unknown}"
            )
        try:
            condition = validate_condition(
                config.get("condition"), f"{where}.condition"
            )
        except ConditionValidationError as exc:
            raise WorkflowIRValidationError(str(exc)) from exc
        branches: dict[str, list[str]] = {}
        for branch_name in ("then", "else"):
            value = config.get(branch_name, [])
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not NODE_ID_RE.fullmatch(item)
                for item in value
            ):
                raise WorkflowIRValidationError(
                    f"{where}.{branch_name} must be a node-id list"
                )
            folded = [item.casefold() for item in value]
            if len(folded) != len(set(folded)):
                raise WorkflowIRValidationError(
                    f"{where}.{branch_name} contains duplicates"
                )
            branches[branch_name] = list(value)
        if not branches["then"] and not branches["else"]:
            raise WorkflowIRValidationError(
                f"{where} must select at least one branch target"
            )
        return {"condition": condition, **branches}
    if kind == "human_gate":
        allowed = {"prompt", "options"}
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise WorkflowIRValidationError(
                f"{where} has unknown keys: {unknown}"
            )
        prompt = _non_empty_string(
            config.get("prompt"), f"{where}.prompt"
        )
        if len(prompt) > 4000:
            raise WorkflowIRValidationError(
                f"{where}.prompt exceeds 4000 characters"
            )
        options = config.get("options", ["approve", "reject"])
        if not isinstance(options, list) or not 2 <= len(options) <= 8:
            raise WorkflowIRValidationError(
                f"{where}.options must contain 2..8 strings"
            )
        if any(
            not isinstance(option, str)
            or not GATE_OPTION_RE.fullmatch(option)
            for option in options
        ):
            raise WorkflowIRValidationError(
                f"{where}.options contains an invalid option"
            )
        folded = [option.casefold() for option in options]
        if len(folded) != len(set(folded)):
            raise WorkflowIRValidationError(
                f"{where}.options must be case-insensitively unique"
            )
        return {"prompt": prompt, "options": list(options)}
    raise WorkflowIRValidationError(f"unsupported node kind: {kind}")


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


def _validate_control_flow_references(nodes: list[dict[str, Any]]) -> None:
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        kind = node["kind"]
        if kind == "map":
            source = node["config"]["over"]
            field = "over"
            allowed_source_kinds = {"agent", "reduce"}
        elif kind == "verify":
            source = node["config"]["target"]
            field = "target"
            allowed_source_kinds = {"map"}
        elif kind == "reduce":
            source = node["config"]["over"]
            field = "over"
            allowed_source_kinds = {"map", "verify"}
        else:
            continue
        if source not in by_id:
            raise WorkflowIRValidationError(
                f"node {node['id']} config.{field} references unknown node {source}"
            )
        if source not in node["depends_on"]:
            raise WorkflowIRValidationError(
                f"node {node['id']} must list config.{field}={source} in depends_on"
            )
        source_kind = by_id[source]["kind"]
        if source_kind not in allowed_source_kinds:
            raise WorkflowIRValidationError(
                f"node {node['id']} cannot consume {source_kind} node {source}"
            )

    branch_owners: dict[str, str] = {}
    for node in nodes:
        if node["kind"] != "conditional":
            continue
        config = node["config"]
        source = config["condition"]["source"]
        if source not in by_id:
            raise WorkflowIRValidationError(
                f"node {node['id']} condition.source references unknown node {source}"
            )
        if source not in node["depends_on"]:
            raise WorkflowIRValidationError(
                f"node {node['id']} must list condition.source={source} in depends_on"
            )
        then_targets = config["then"]
        else_targets = config["else"]
        overlap = sorted(set(then_targets) & set(else_targets))
        if overlap:
            raise WorkflowIRValidationError(
                f"conditional branches must be disjoint: {overlap}"
            )
        for target in then_targets + else_targets:
            if target not in by_id:
                raise WorkflowIRValidationError(
                    f"conditional branch target is unknown: {target}"
                )
            if target == node["id"]:
                raise WorkflowIRValidationError(
                    "conditional cannot select itself"
                )
            if node["id"] not in by_id[target]["depends_on"]:
                raise WorkflowIRValidationError(
                    f"conditional branch target {target} must directly depend on {node['id']}"
                )
            if by_id[target]["dependency_policy"] == JOIN_DEPENDENCY_POLICY:
                raise WorkflowIRValidationError(
                    f"conditional branch target {target} cannot use dependency_policy=join"
                )
            owner = branch_owners.get(target)
            if owner is not None and owner != node["id"]:
                raise WorkflowIRValidationError(
                    f"conditional branch target {target} is already owned by {owner}"
                )
            branch_owners[target] = node["id"]


def bounded_loop_child_id(
    loop_node_id: str,
    iteration: int,
    step_index: int,
    template_node_id: str,
) -> str:
    """Derive one stable, Windows-safe Bounded Loop child identity."""

    payload = json.dumps(
        [loop_node_id, iteration, step_index, template_node_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    domain = b"dynamic-workflow/bounded-loop-child/v1\0"
    return hashlib.sha256(domain + payload).hexdigest()[:40]


def bounded_loop_state_id(
    loop_node_id: str,
    iteration: int,
    step_index: int,
    template_node_id: str,
) -> str:
    """Derive a state-input identity in a domain distinct from child IDs."""

    payload = json.dumps(
        [loop_node_id, iteration, step_index, template_node_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    domain = b"dynamic-workflow/bounded-loop-state/v1\0"
    return hashlib.sha256(domain + payload).hexdigest()[:40]


def _bounded_loop_contract_errors(
    nodes: list[dict[str, Any]],
    budgets: Mapping[str, int],
) -> dict[str, list[str]]:
    """Return per-loop contract failures without persisting analysis metadata."""

    by_id = {node["id"]: node for node in nodes}
    loop_nodes = [node for node in nodes if node["kind"] == "loop"]
    owners: dict[str, list[str]] = {}
    for loop in loop_nodes:
        for template_id in loop["config"]["body"]:
            owners.setdefault(template_id.casefold(), []).append(loop["id"])

    conditional_targets = {
        target.casefold()
        for node in nodes
        if node["kind"] == "conditional"
        for target in node["config"]["then"] + node["config"]["else"]
    }
    source_ids = {
        source.casefold()
        for node in nodes
        for source in (
            [node["config"]["over"]]
            if node["kind"] in {"map", "reduce"}
            else [node["config"]["target"]]
            if node["kind"] == "verify"
            else []
        )
    }
    dependents: dict[str, list[str]] = {}
    for node in nodes:
        for dependency in node["depends_on"]:
            dependents.setdefault(dependency.casefold(), []).append(node["id"])

    errors: dict[str, list[str]] = {}
    reserved_ids = {node["id"].casefold() for node in nodes}
    generated_ids: set[str] = set()
    for loop in loop_nodes:
        loop_id = loop["id"]
        config = loop["config"]
        current: list[str] = []
        required_stop = BOUNDED_LOOP_CONTRACT["stop_when"]
        if config["stop_when"] != required_stop:
            current.append(f"stop_when must equal {required_stop}")
        if len(loop["depends_on"]) != 1:
            current.append("depends_on must contain exactly one initial result")
        body = config["body"]
        folded_body = [template_id.casefold() for template_id in body]
        body_min = BOUNDED_LOOP_CONTRACT["body_min"]
        body_max = BOUNDED_LOOP_CONTRACT["body_max"]
        if not body_min <= len(body) <= body_max:
            current.append(
                f"body must contain {body_min}..{body_max} template node ids"
            )
        if len(folded_body) != len(set(folded_body)):
            current.append("body template ids must be case-insensitively unique")
        if config["max_iterations"] > budgets["max_iterations"]:
            current.append("max_iterations exceeds budgets.max_iterations")

        for template_id in body:
            template = by_id.get(template_id)
            if template is None:
                current.append(f"body template does not exist: {template_id}")
                continue
            if template["kind"] != "agent":
                current.append(f"body template must be agent: {template_id}")
                continue
            if template["depends_on"] != [loop_id]:
                current.append(
                    f"body template {template_id} must depend exactly on {loop_id}"
                )
            prompt = template["config"]["prompt"]
            if "{{loop_state}}" not in prompt:
                current.append(
                    f"body template {template_id} prompt must contain {{{{loop_state}}}}"
                )
            declared_tokens = set(re.findall(r"\{\{[^{}]*\}\}", prompt))
            unexpected_placeholders = sorted(
                declared_tokens - {"{{loop_state}}", "{{iteration}}"}
            )
            if unexpected_placeholders:
                current.append(
                    f"body template {template_id} has unsupported placeholders: "
                    f"{unexpected_placeholders}"
                )
            if len(set(owners.get(template_id.casefold(), []))) != 1:
                current.append(
                    f"body template {template_id} must be owned by exactly one loop"
                )
            if template_id.casefold() in conditional_targets:
                current.append(
                    f"body template {template_id} cannot be a conditional target"
                )
            if template_id.casefold() in source_ids:
                current.append(
                    f"body template {template_id} cannot be a map/verify/reduce source"
                )
            external = [
                node_id
                for node_id in dependents.get(template_id.casefold(), [])
                if node_id.casefold() != loop_id.casefold()
            ]
            if external:
                current.append(
                    f"body template {template_id} has external dependents: {sorted(external)}"
                )

        if body:
            verifier = by_id.get(body[-1])
            if (
                verifier is None
                or verifier["kind"] != "agent"
                or verifier["config"].get("output_schema")
                != VERIFICATION_RESULT_SCHEMA
            ):
                current.append("final body template must use the fixed verifier schema")

        if not current:
            local_ids: set[str] = set()
            for iteration in range(1, config["max_iterations"] + 1):
                for step_index, template_id in enumerate(body):
                    child_id = bounded_loop_child_id(
                        loop_id, iteration, step_index, template_id
                    )
                    state_id = bounded_loop_state_id(
                        loop_id, iteration, step_index, template_id
                    )
                    for identity, label in (
                        (child_id, "child"),
                        (state_id, "state input"),
                    ):
                        folded = identity.casefold()
                        if (
                            folded in reserved_ids
                            or folded in generated_ids
                            or folded in local_ids
                        ):
                            current.append(
                                f"deterministic {label} id collides under case-insensitive semantics"
                            )
                        local_ids.add(folded)
            generated_ids.update(local_ids)
        errors[loop_id] = current
    return errors


def executable_bounded_loops(
    nodes: list[dict[str, Any]], budgets: Mapping[str, int]
) -> dict[str, tuple[str, ...]]:
    """Return executable loop/template ownership as ephemeral runtime data."""

    failures = _bounded_loop_contract_errors(nodes, budgets)
    return {
        node["id"]: tuple(node["config"]["body"])
        for node in nodes
        if node["kind"] == "loop" and not failures[node["id"]]
    }


def project_agent_claims(ir: Mapping[str, Any]) -> dict[str, int | bool]:
    """Compute the shared conservative agent-claim projection."""

    nodes = list(ir["nodes"])
    budgets = ir["budgets"]
    by_id = {node["id"]: node for node in nodes}
    loops = executable_bounded_loops(nodes, budgets)
    template_ids = {
        template_id.casefold()
        for body in loops.values()
        for template_id in body
    }
    static = sum(
        node["kind"] in {"agent", "reduce"}
        and node["id"].casefold() not in template_ids
        for node in nodes
    )
    mapped = sum(
        node["config"]["item_limit"]
        for node in nodes
        if node["kind"] == "map"
    )
    verified = sum(
        by_id[node["config"]["target"]]["config"]["item_limit"]
        for node in nodes
        if node["kind"] == "verify"
    )
    loop_children = sum(
        by_id[loop_id]["config"]["max_iterations"] * len(body)
        for loop_id, body in loops.items()
    )
    total = static + mapped + verified + loop_children
    maximum = budgets["max_agents"]
    projection: dict[str, int | bool] = {
        "static_agent_claims": static,
        "map_child_upper_bound": mapped,
        "verify_child_upper_bound": verified,
    }
    if loops:
        projection["loop_child_upper_bound"] = loop_children
    projection.update(
        {
            "total_upper_bound": total,
            "max_agents": maximum,
            "upper_bound_within_budget": total <= maximum,
        }
    )
    return projection


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
    objective = _non_empty_string(raw.get("objective"), "objective")
    workdir = _non_empty_string(raw.get("workdir"), "workdir")
    budgets = _validate_budgets(raw.get("budgets"))
    limits = _validate_limits(raw.get("limits"))

    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise WorkflowIRValidationError("nodes must be a non-empty list")
    if len(raw_nodes) > 128:
        raise WorkflowIRValidationError("nodes exceeds the hard plan limit 128")

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
        folded = node_id.casefold()
        if folded in seen:
            raise WorkflowIRValidationError(
                f"duplicate node id under case-insensitive semantics: {node_id}"
            )
        seen.add(folded)
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
        dependency_policy = raw_node.get(
            "dependency_policy", DEFAULT_DEPENDENCY_POLICY
        )
        if dependency_policy not in DEPENDENCY_POLICIES:
            raise WorkflowIRValidationError(
                f"{where}.dependency_policy must be one of "
                f"{sorted(DEPENDENCY_POLICIES)}"
            )
        if dependency_policy == JOIN_DEPENDENCY_POLICY and len(depends_on) < 2:
            raise WorkflowIRValidationError(
                f"{where}.dependency_policy=join requires at least two dependencies"
            )
        config = raw_node.get("config", {})
        if not isinstance(config, dict):
            raise WorkflowIRValidationError(f"{where}.config must be an object")
        if kind == "agent":
            normalized_config = _validate_agent_config(
                config, f"{where}.config"
            )
        elif kind == "map":
            normalized_config = _validate_map_config(
                config, f"{where}.config", budgets
            )
        elif kind == "verify":
            normalized_config = _validate_verify_config(
                config, f"{where}.config"
            )
        elif kind == "reduce":
            normalized_config = _validate_reduce_config(
                config, f"{where}.config"
            )
        else:
            normalized_config = _validate_reserved_config(
                kind, config, f"{where}.config"
            )
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "depends_on": list(depends_on),
                "dependency_policy": dependency_policy,
                "config": normalized_config,
            }
        )

    _validate_dag(nodes)
    _validate_control_flow_references(nodes)
    bounded_loops = executable_bounded_loops(nodes, budgets)
    bounded_templates = {
        template_id.casefold()
        for body in bounded_loops.values()
        for template_id in body
    }
    for node in nodes:
        if node["kind"] == "loop" and node["id"] in bounded_loops:
            node["config"].setdefault(
                "no_progress_limit",
                BOUNDED_LOOP_CONTRACT["no_progress_default"],
            )
    direct_agents = sum(
        node["kind"] in {"agent", "reduce"}
        and node["id"].casefold() not in bounded_templates
        for node in nodes
    )
    if direct_agents > budgets["max_agents"]:
        raise WorkflowIRValidationError(
            "direct agent/reduce nodes exceed budgets.max_agents before dynamic expansion"
        )
    return {
        "version": IR_VERSION,
        "name": name,
        "mode": mode,
        "objective": objective,
        "workdir": workdir,
        "budgets": budgets,
        "limits": limits,
        "nodes": nodes,
        "execution": analyze_execution_support(nodes, budgets),
    }


def analyze_execution_support(
    nodes: list[dict[str, Any]],
    budgets: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    dynamic = sorted({node["kind"] for node in nodes if node["kind"] != "agent"})
    unsupported_kinds = {
        node["kind"] for node in nodes if node["kind"] not in EXECUTABLE_NODE_KINDS
    }
    if any(node["kind"] == "loop" for node in nodes):
        if budgets is None or any(
            _bounded_loop_contract_errors(nodes, budgets).values()
        ):
            unsupported_kinds.add("loop")
    unsupported = sorted(unsupported_kinds)
    return {
        "static_v2_compilable": not dynamic,
        "trusted_runtime_executable": not unsupported,
        "dynamic_node_kinds": dynamic,
        "unsupported_node_kinds": unsupported,
        "runtime_version_required": 3 if dynamic else 2,
    }


def compile_static_ir_to_v2(ir: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_workflow_ir(ir) if ir.get("execution") is None else ir
    dynamic = normalized["execution"]["dynamic_node_kinds"]
    if dynamic:
        raise WorkflowIRValidationError(
            "only all-agent Workflow IR can compile to the legacy v2 DAG: "
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
    compiled = {
        "version": 2,
        "name": normalized["name"],
        "workdir": normalized["workdir"],
        "max_concurrency": budgets["max_concurrency"],
        "soft_timeout_seconds": budgets["soft_timeout_seconds"],
        "hard_timeout_seconds": budgets["hard_timeout_seconds"],
        "tasks": tasks,
    }
    if normalized.get("limits"):
        compiled["limits"] = normalized["limits"]
    return compiled
