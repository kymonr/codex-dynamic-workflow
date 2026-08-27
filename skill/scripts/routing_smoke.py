#!/usr/bin/env python3
"""Evidence-oriented Dynamic Workflow routing smoke.

The default command self-tests this evaluator with synthetic structured events.
It makes no model or network call. --transcript verifies an existing JSONL
event stream. --live is deliberately separate: it performs exactly one
ephemeral, read-only codex exec process invocation in a generated temporary
fixture; internal provider/model call count remains UNKNOWN.

Offline PASS proves only that the evaluator handles its evidence contract. A
live or captured transcript without terminal and structured dispatch provenance
is UNKNOWN, never a routing PASS inferred from prose.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from platform_paths import configure_utf8_stdio


_MARKER = re.compile(
    r"Workflow: (simple-swarm|managed-workflow|writer-workflow)"
)
_VALID_MODES = {None, "simple-swarm"}
_TOOL_CALL_TYPES = {
    "collaboration_tool_call",
    "function_call",
    "mcp_tool_call",
    "tool_call",
}


@dataclass(frozen=True)
class SmokeCase:
    name: str
    prompt: str
    workflow: bool
    routes: tuple[str, ...]
    mode: str | None
    reviewer_min: int = 0
    reviewer_max: int = 0


@dataclass(frozen=True)
class Dispatch:
    task_name: str
    route: str
    requested_route: str | None
    effective_route: str | None
    agent_type: str | None
    requested_model: str | None
    requested_effort: str | None
    requested_tier: str | None
    model: str | None
    effort: str | None
    tier: str | None
    fork: str | None
    source: str
    source_conflict: bool


@dataclass
class Observation:
    terminal: bool = False
    runtime_failed: bool = False
    invalid_lines: list[int] = field(default_factory=list)
    thread_started_count: int = 0
    turn_started_count: int = 0
    terminal_count: int = 0
    thread_ids: set[str] = field(default_factory=set)
    turn_ids: set[str] = field(default_factory=set)
    sequence_errors: list[str] = field(default_factory=list)
    structured_selection_count: int = 0
    structured_selection_modes: list[str] = field(default_factory=list)
    invalid_selection_mode_count: int = 0
    commentary_selection_count: int = 0
    commentary_marker_modes: list[str] = field(default_factory=list)
    visible_marker_count: int = 0
    untrusted_marker_count: int = 0
    untrusted_marker_modes: list[str] = field(default_factory=list)
    late_selection_count: int = 0
    dispatch_conflict_tasks: list[str] = field(default_factory=list)
    runtime_conflict_tasks: list[str] = field(default_factory=list)
    orphan_runtime_tasks: list[str] = field(default_factory=list)
    dispatches: list[Dispatch] = field(default_factory=list)
    reviewers: list[Dispatch] = field(default_factory=list)


CASES: dict[str, SmokeCase] = {
    "root-plus-luna": SmokeCase(
        name="root-plus-luna",
        prompt=(
            "只读检查 AGENTS.md 中的一条工作线规则，给出一个直接结论；"
            "不要修改，也没有第二条独立支线。"
        ),
        workflow=False,
        routes=(),
        mode=None,
    ),
    "implicit-luna": SmokeCase(
        name="implicit-luna",
        prompt=(
            "分别只读分析 login.log 的登录失败和 inventory.log 的库存同步变慢，"
            "各自给出证据，最后统一告诉我结论。"
        ),
        workflow=True,
        routes=("Luna", "Luna"),
        mode="simple-swarm",
    ),
    "simple-negative": SmokeCase(
        name="simple-negative",
        prompt="读取 package.json 和 tsconfig.json 的 version 字段并直接告诉我。",
        workflow=False,
        routes=(),
        mode=None,
    ),
    "serial-negative": SmokeCase(
        name="serial-negative",
        prompt=(
            "先读取 config.txt 的唯一值，再根据该值从 options.txt 选择对应标签并报告；"
            "后一步完全依赖前一步。"
        ),
        workflow=False,
        routes=(),
        mode=None,
    ),
    "bounded-explorer": SmokeCase(
        name="bounded-explorer",
        prompt=(
            "使用 $dynamic-workflow，只读定位 sample.py 中 target 的一个直接调用者，"
            "并给出本地证据。"
        ),
        workflow=True,
        routes=("Explorer",),
        mode="simple-swarm",
    ),
    "complex-sol": SmokeCase(
        name="complex-sol",
        prompt=(
            "使用 $dynamic-workflow，审核 sample.py 的架构和安全风险，"
            "并给出最终是否接受的判断。"
        ),
        workflow=True,
        routes=("Sol",),
        mode="simple-swarm",
        reviewer_min=0,
        reviewer_max=0,
    ),
    "explicit-luna": SmokeCase(
        name="explicit-luna",
        prompt=(
            "使用 $dynamic-workflow，并显式指定 Luna，只读定位 sample.py 中 target "
            "的一个直接调用者并给出本地证据。"
        ),
        workflow=True,
        routes=("Luna",),
        mode="simple-swarm",
    ),
}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _tier(value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).casefold()
    if normalized in {"priority", "fast"}:
        return "fast"
    return str(value)


def _canonical_route(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return {
        "custom": "Custom",
        "explorer": "Explorer",
        "inherited": "inherited",
        "luna": "Luna",
        "reviewer": "Reviewer",
        "sol": "Sol",
        "spark": "Spark",
    }.get(value.casefold(), value)


def _route_from_identity(agent_type: str | None, model: str | None) -> str:
    normalized_agent = (agent_type or "").casefold()
    normalized_model = (model or "").casefold()
    if normalized_agent == "dynamic_workflow_sol_reviewer":
        return "Reviewer"
    if normalized_agent == "luna":
        return "Luna"
    if normalized_agent == "explorer":
        return "Explorer"
    if normalized_agent == "spark":
        return "Spark"
    if normalized_agent == "sol":
        return "Sol"
    if normalized_agent == "default" and normalized_model == "gpt-5.6-sol":
        return "Sol"
    if normalized_agent == "default":
        return "Custom"
    return "UNKNOWN"


def _identity_alias_conflict(fields: dict[str, Any]) -> bool:
    alias_groups = (
        (("task_name", "task"), lambda value: str(value).casefold()),
        (("reasoning_effort", "effort"), lambda value: str(value).casefold()),
        (("service_tier", "tier", "priority"), _tier),
    )
    for keys, normalize in alias_groups:
        values = {
            normalized
            for key in keys
            if fields.get(key) not in (None, "")
            if (normalized := normalize(fields[key])) is not None
        }
        if len(values) > 1:
            return True
    if str(fields.get("agent_type") or "").casefold() == (
        "dynamic_workflow_sol_reviewer"
    ):
        explicit_routes = {
            route
            for key in ("route", "effective_route")
            if (route := _canonical_route(fields.get(key))) is not None
        }
        if any(route != "Reviewer" for route in explicit_routes):
            return True
    return False


def _route_from_fields(fields: dict[str, Any]) -> str:
    effective = _canonical_route(fields.get("effective_route"))
    requested = _canonical_route(fields.get("route"))
    agent_type = str(fields["agent_type"]) if fields.get("agent_type") else None
    model = str(fields["model"]) if fields.get("model") else None
    return effective or requested or _route_from_identity(agent_type, model)


def _dispatch(fields: dict[str, Any], source: str) -> Dispatch:
    effort = fields.get("reasoning_effort") or fields.get("effort")
    return Dispatch(
        task_name=str(fields.get("task_name") or fields.get("task") or "UNKNOWN"),
        route=_route_from_fields(fields),
        requested_route=_canonical_route(fields.get("route")),
        effective_route=_canonical_route(fields.get("effective_route")),
        agent_type=(str(fields["agent_type"]) if fields.get("agent_type") else None),
        requested_model=(
            str(fields["model"]) if fields.get("model") else None
        ),
        requested_effort=(str(effort) if effort else None),
        requested_tier=_tier(
            fields.get("service_tier")
            or fields.get("tier")
            or fields.get("priority")
        ),
        model=None,
        effort=None,
        tier=None,
        fork=(
            str(fields.get("fork_turns"))
            if fields.get("fork_turns") is not None
            else None
        ),
        source=source,
        source_conflict=_identity_alias_conflict(fields),
    )


def _tool_dispatch(item: dict[str, Any]) -> Dispatch | None:
    item_type = str(item.get("type") or "").casefold()
    if item_type not in _TOOL_CALL_TYPES:
        return None
    raw_names = [
        str(item[key]).casefold()
        for key in ("name", "tool_name", "tool")
        if item.get(key) not in (None, "")
    ]
    identifiers = [name.split(".") for name in raw_names]
    tool_bases = {parts[-1] for parts in identifiers}
    embedded_namespaces = {
        ".".join(parts[:-1]) for parts in identifiers if len(parts) > 1
    }
    servers = {
        str(item[key]).casefold()
        for key in ("server", "server_name")
        if item.get(key) not in (None, "")
    }
    namespaces = embedded_namespaces | servers
    name = str(
        item.get("name") or item.get("tool_name") or item.get("tool") or ""
    )
    server = str(item.get("server") or item.get("server_name") or "")
    selected_parts = name.casefold().split(".")
    selected_base = selected_parts[-1]
    selected_namespace = (
        ".".join(selected_parts[:-1])
        if len(selected_parts) > 1
        else (server.casefold() if server else None)
    )
    if selected_base != "spawn_agent":
        return None
    if selected_namespace not in (None, "collaboration"):
        return None
    payloads = [
        _json_object(item[key])
        for key in ("arguments", "input", "params")
        if item.get(key) not in (None, "")
    ]
    fields = payloads[0] if payloads else {}
    payload_shapes = {
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for payload in payloads
    }
    candidate = _dispatch(fields, "structured-tool-event")
    return replace(
        candidate,
        source_conflict=(
            candidate.source_conflict
            or len(tool_bases) > 1
            or len(namespaces) > 1
            or any(namespace != "collaboration" for namespace in namespaces)
            or len(payload_shapes) > 1
        ),
    )


def _marker_modes(text: str) -> list[str]:
    modes: list[str] = []
    for line in text.splitlines():
        match = _MARKER.fullmatch(line.strip())
        if match:
            modes.append(match.group(1))
    return modes


def observe_jsonl(transcript: str) -> Observation:
    """Extract only typed event evidence; never scan prompts or arbitrary JSON."""

    observation = Observation()
    runtimes: dict[str, list[dict[str, Any]]] = {}
    dispatch_seen = False
    dispatched_task_names: set[str] = set()
    phase = "before-thread"

    def remember_identifier(
        event: dict[str, Any], key: str, target: set[str]
    ) -> None:
        value = event.get(key)
        if value not in (None, "") and not isinstance(value, (dict, list)):
            target.add(str(value))

    def require_active(event_type: str, line_number: int) -> bool:
        if phase == "active":
            return True
        observation.sequence_errors.append(
            f"line {line_number}: {event_type} occurred while {phase}"
        )
        return False

    def remember_context(
        event: dict[str, Any], item: dict[str, Any] | None = None
    ) -> None:
        remember_identifier(event, "thread_id", observation.thread_ids)
        remember_identifier(event, "turn_id", observation.turn_ids)
        if item is not None:
            remember_identifier(item, "thread_id", observation.thread_ids)
            remember_identifier(item, "turn_id", observation.turn_ids)

    for line_number, line in enumerate(transcript.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            observation.invalid_lines.append(line_number)
            continue
        if not isinstance(event, dict):
            observation.invalid_lines.append(line_number)
            continue

        event_type = str(event.get("type") or "")
        if event_type == "thread.started":
            observation.thread_started_count += 1
            remember_identifier(event, "thread_id", observation.thread_ids)
            if phase != "before-thread":
                observation.sequence_errors.append(
                    f"line {line_number}: repeated or misplaced thread.started"
                )
            else:
                phase = "before-turn"
            continue
        if event_type == "turn.started":
            observation.turn_started_count += 1
            remember_identifier(event, "turn_id", observation.turn_ids)
            if phase != "before-turn":
                observation.sequence_errors.append(
                    f"line {line_number}: repeated or misplaced turn.started"
                )
            else:
                phase = "active"
            continue
        if event_type == "turn.completed":
            observation.terminal_count += 1
            remember_identifier(event, "turn_id", observation.turn_ids)
            if phase != "active":
                observation.sequence_errors.append(
                    f"line {line_number}: repeated or misplaced turn.completed"
                )
            else:
                observation.terminal = True
                phase = "terminal"
            continue
        if event_type in {"turn.failed", "error"}:
            observation.runtime_failed = True
            if event_type == "turn.failed":
                remember_identifier(event, "turn_id", observation.turn_ids)
            if phase != "active":
                observation.sequence_errors.append(
                    f"line {line_number}: {event_type} occurred while {phase}"
                )
            phase = "terminal"
            continue

        if event_type == "workflow.selected":
            if event.get("skill") == "dynamic-workflow":
                remember_context(event)
                if not require_active(event_type, line_number):
                    continue
                if dispatch_seen:
                    observation.late_selection_count += 1
                else:
                    observation.structured_selection_count += 1
                    mode = event.get("mode")
                    if mode in (None, "", "simple-swarm"):
                        observation.structured_selection_modes.append("simple-swarm")
                    elif isinstance(mode, str) and mode in {"local", "parallel", "audit", "full"}:
                        observation.invalid_selection_mode_count += 1
                    else:
                        observation.invalid_selection_mode_count += 1
            continue
        if event_type == "subagent.dispatched":
            remember_context(event)
            if not require_active(event_type, line_number):
                continue
            dispatch_seen = True
            candidate = _dispatch(event, "native-dispatch-event")
            target = (
                observation.reviewers
                if candidate.route == "Reviewer"
                else observation.dispatches
            )
            target.append(candidate)
            if candidate.task_name == "UNKNOWN":
                observation.sequence_errors.append(
                    f"line {line_number}: dispatch lacks task identity"
                )
            dispatched_task_names.add(candidate.task_name)
            continue
        if event_type == "subagent.runtime":
            remember_context(event)
            if not require_active(event_type, line_number):
                continue
            task_name = str(
                event.get("task_name") or event.get("task") or ""
            )
            if task_name:
                if (
                    _identity_alias_conflict(event)
                    and task_name not in observation.runtime_conflict_tasks
                ):
                    observation.runtime_conflict_tasks.append(task_name)
                if task_name not in dispatched_task_names:
                    observation.sequence_errors.append(
                        f"line {line_number}: runtime precedes matching dispatch"
                    )
                runtimes.setdefault(task_name, []).append(event)
            else:
                observation.sequence_errors.append(
                    f"line {line_number}: subagent.runtime lacks task identity"
                )
            continue
        if event_type == "item.completed":
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if (
                item.get("type") == "agent_message"
                and isinstance(item.get("text"), str)
            ):
                modes = _marker_modes(item["text"])
                if modes:
                    remember_context(event, item)
                    channels = {
                        str(value).casefold()
                        for value in (
                            item.get("channel"),
                            event.get("channel"),
                        )
                        if value not in (None, "")
                    }
                    channel = str(
                        item.get("channel")
                        or event.get("channel")
                        or ""
                    ).casefold()
                    if not require_active(event_type, line_number):
                        observation.untrusted_marker_modes.extend(modes)
                        observation.untrusted_marker_count += len(modes)
                    elif (
                        len(channels) == 1
                        and channel == "commentary"
                        and not dispatch_seen
                    ):
                        observation.commentary_marker_modes.extend(modes)
                        observation.commentary_selection_count += len(modes)
                        observation.visible_marker_count += len(modes)
                    else:
                        observation.untrusted_marker_modes.extend(modes)
                        observation.untrusted_marker_count += len(modes)
            candidate = _tool_dispatch(item)
            if candidate is not None:
                remember_context(event, item)
                if not require_active("spawn_agent tool call", line_number):
                    continue
                dispatch_seen = True
                target = (
                    observation.reviewers
                    if candidate.route == "Reviewer"
                    else observation.dispatches
                )
                target.append(candidate)
                if candidate.task_name == "UNKNOWN":
                    observation.sequence_errors.append(
                        f"line {line_number}: dispatch lacks task identity"
                    )
                dispatched_task_names.add(candidate.task_name)

    def merge_dispatches(items: list[Dispatch]) -> list[Dispatch]:
        groups: dict[str, list[Dispatch]] = {}
        for item in items:
            groups.setdefault(item.task_name, []).append(item)

        merged: list[Dispatch] = []
        for task_name, group in groups.items():
            conflict = False

            def select(
                attribute: str, *, ignore: set[str] | None = None
            ) -> str | None:
                nonlocal conflict
                values: list[str] = []
                for item in group:
                    value = getattr(item, attribute)
                    if value is None or (ignore and value in ignore):
                        continue
                    if not any(value.casefold() == seen.casefold() for seen in values):
                        values.append(value)
                if len(values) > 1:
                    conflict = True
                return values[0] if values else None

            requested_route = select("requested_route")
            effective_route = select("effective_route")
            agent_type = select("agent_type")
            requested_model = select("requested_model")
            route = (
                effective_route
                or requested_route
                or _route_from_identity(agent_type, requested_model)
            )
            merged.append(
                Dispatch(
                    task_name=task_name,
                    route=route,
                    requested_route=requested_route,
                    effective_route=effective_route,
                    agent_type=agent_type,
                    requested_model=requested_model,
                    requested_effort=select("requested_effort"),
                    requested_tier=select("requested_tier"),
                    model=select("model"),
                    effort=select("effort"),
                    tier=select("tier"),
                    fork=select("fork"),
                    source="+".join(
                        sorted({item.source for item in group})
                    ),
                    source_conflict=any(
                        item.source_conflict for item in group
                    ),
                )
            )
            if conflict or any(item.source_conflict for item in group):
                observation.dispatch_conflict_tasks.append(task_name)
        return merged

    logical_dispatches = merge_dispatches(
        observation.dispatches + observation.reviewers
    )
    observation.dispatches = [
        item for item in logical_dispatches if item.route != "Reviewer"
    ]
    observation.reviewers = [
        item for item in logical_dispatches if item.route == "Reviewer"
    ]

    def apply_runtime(candidate: Dispatch) -> Dispatch:
        runtime_events = runtimes.get(candidate.task_name, [])
        if not runtime_events:
            return candidate

        models = {
            str(event["model"])
            for event in runtime_events
            if event.get("model") not in (None, "")
        }
        efforts = {
            str(event.get("effort") or event.get("reasoning_effort"))
            for event in runtime_events
            if event.get("effort") or event.get("reasoning_effort")
        }
        tiers = {
            value
            for event in runtime_events
            if (
                value := _tier(
                    event.get("tier")
                    or event.get("service_tier")
                    or event.get("priority")
                )
            )
            is not None
        }
        if len(models) > 1 or len(efforts) > 1 or len(tiers) > 1:
            if candidate.task_name not in observation.runtime_conflict_tasks:
                observation.runtime_conflict_tasks.append(candidate.task_name)
            return candidate

        model = next(iter(models), None)
        effort = next(iter(efforts), None)
        tier = next(iter(tiers), None)
        return replace(
            candidate,
            model=model,
            effort=effort,
            tier=tier,
            source=f"{candidate.source}+native-runtime",
        )

    observation.dispatches = [
        apply_runtime(item) for item in observation.dispatches
    ]
    observation.reviewers = [
        apply_runtime(item) for item in observation.reviewers
    ]

    dispatched_tasks = {
        item.task_name
        for item in observation.dispatches + observation.reviewers
    }
    observation.orphan_runtime_tasks = sorted(
        task_name for task_name in runtimes if task_name not in dispatched_tasks
    )
    observation.dispatch_conflict_tasks.sort()
    observation.runtime_conflict_tasks.sort()
    return observation


def _identity_state(dispatch: Dispatch) -> str:
    requested_pairs = (
        (dispatch.requested_model, dispatch.model),
        (dispatch.requested_effort, dispatch.effort),
    )
    for requested, observed in requested_pairs:
        if requested is None:
            continue
        if observed is None:
            return "UNKNOWN"
        if requested.casefold() != observed.casefold():
            return "MISMATCH"

    def controlled_fork_state() -> str:
        if dispatch.fork is None:
            return "UNKNOWN"
        if dispatch.fork == "none":
            return "observed"
        try:
            return "observed" if int(dispatch.fork) > 0 else "MISMATCH"
        except ValueError:
            return "MISMATCH"

    if dispatch.route == "Luna":
        if dispatch.agent_type is None:
            return "UNKNOWN"
        if dispatch.agent_type.casefold() != "luna":
            return "MISMATCH"
        fork_state = controlled_fork_state()
        if fork_state != "observed":
            return fork_state
        if dispatch.model is None or dispatch.effort is None:
            return "UNKNOWN"
        if dispatch.model != "gpt-5.6-luna" or dispatch.effort != "max":
            return "MISMATCH"
        return "observed"
    if dispatch.route == "Sol":
        if dispatch.agent_type is None:
            return "UNKNOWN"
        if dispatch.agent_type.casefold() != "sol":
            return "MISMATCH"
        fork_state = controlled_fork_state()
        if fork_state != "observed":
            return fork_state
        if dispatch.model is None or dispatch.effort is None:
            return "UNKNOWN"
        if dispatch.model == "gpt-5.6-sol" and dispatch.effort == "xhigh":
            return "observed"
        return "MISMATCH"
    if dispatch.route == "Explorer":
        if dispatch.agent_type != "explorer":
            return "MISMATCH"
        if dispatch.fork is None:
            return "UNKNOWN"
        if dispatch.fork != "none":
            return "MISMATCH"
        if dispatch.model is None or dispatch.effort is None:
            return "UNKNOWN"
        return "observed"
    if dispatch.route == "Reviewer":
        if dispatch.agent_type != "dynamic_workflow_sol_reviewer":
            return "MISMATCH"
        if dispatch.fork is None:
            return "UNKNOWN"
        if dispatch.fork != "none":
            return "MISMATCH"
        if dispatch.model is None or dispatch.effort is None:
            return "UNKNOWN"
        if dispatch.model == "gpt-5.6-sol" and dispatch.effort == "xhigh":
            return "observed"
        return "MISMATCH"
    return "UNKNOWN"


def _service_tier_state(dispatch: Dispatch) -> str:
    expected = dispatch.requested_tier
    if expected is None and dispatch.route == "Luna":
        expected = "fast"
    if dispatch.tier is None:
        return "UNKNOWN"
    if expected is not None and expected.casefold() != dispatch.tier.casefold():
        return "MISMATCH"
    return "observed"


def evaluate_transcript(
    case: SmokeCase, transcript: str
) -> dict[str, Any]:
    observation = observe_jsonl(transcript)
    observed_routes = [item.route for item in observation.dispatches]
    identity = [_identity_state(item) for item in observation.dispatches]
    reviewer_identity = [
        _identity_state(item) for item in observation.reviewers
    ]
    service_tier = [
        _service_tier_state(item) for item in observation.dispatches
    ]
    reviewer_service_tier = [
        _service_tier_state(item) for item in observation.reviewers
    ]
    limitations: list[str] = []
    selection_count = (
        observation.structured_selection_count
        if observation.structured_selection_count
        else observation.commentary_selection_count
    )
    marker_count = (
        observation.visible_marker_count
        + observation.untrusted_marker_count
    )
    lifecycle_missing = (
        observation.thread_started_count == 0
        or observation.turn_started_count == 0
        or observation.terminal_count == 0
        or not observation.terminal
    )
    lifecycle_conflict = (
        observation.thread_started_count != 1
        or observation.turn_started_count != 1
        or observation.terminal_count != 1
        or len(observation.thread_ids) > 1
        or len(observation.turn_ids) > 1
        or bool(observation.sequence_errors)
    )
    terminal_contradiction = (
        observation.runtime_failed and observation.terminal_count > 0
    )
    mode_conflict = (
        len(observation.structured_selection_modes) == 1
        and len(observation.commentary_marker_modes) == 1
        and observation.structured_selection_modes[0]
        != observation.commentary_marker_modes[0]
    )
    observed_mode = (
        observation.structured_selection_modes[0]
        if len(observation.structured_selection_modes) == 1
        else (
            observation.commentary_marker_modes[0]
            if len(observation.commentary_marker_modes) == 1
            else None
        )
    )

    if observation.invalid_lines:
        status = "unknown"
        reason = "transcript contains invalid or non-object JSONL events"
    elif terminal_contradiction:
        status = "fail"
        reason = "successful and failed terminal evidence conflict"
    elif observation.runtime_failed:
        status = "unknown"
        reason = "terminal successful turn evidence is missing"
    elif lifecycle_missing:
        status = "unknown"
        reason = "one complete thread and turn lifecycle is missing"
    elif lifecycle_conflict:
        status = "fail"
        reason = "events do not belong to one ordered thread and turn"
    elif observation.dispatch_conflict_tasks:
        status = "fail"
        reason = "conflicting dispatch evidence was reported for one task"
    elif observation.runtime_conflict_tasks:
        status = "fail"
        reason = "conflicting runtime identities were reported for one task"
    elif observation.orphan_runtime_tasks:
        status = "fail"
        reason = "runtime identity was reported without a matching dispatch"
    elif case.workflow:
        if not observation.dispatches:
            status = "unknown"
            reason = "structured native dispatch provenance is missing"
        elif observation.late_selection_count:
            status = "fail"
            reason = "workflow selection evidence appeared after dispatch"
        elif observation.invalid_selection_mode_count:
            status = "fail"
            reason = "structured workflow selection used a retired outer mode"
        elif selection_count == 0:
            status = "unknown"
            reason = "structured or typed pre-dispatch selection provenance is missing"
        elif selection_count != 1:
            status = "fail"
            reason = "one logical workflow selection is required"
        elif observation.visible_marker_count != 1:
            status = "fail"
            reason = "one pre-dispatch commentary workflow marker is required"
        elif observation.untrusted_marker_count:
            status = "fail"
            reason = "final or untyped prose must not supply or repeat the marker"
        elif mode_conflict:
            status = "fail"
            reason = "structured selection and commentary marker modes conflict"
        elif observed_mode != case.mode:
            status = "fail"
            reason = "observed outer mode does not match the case contract"
        elif "UNKNOWN" in observed_routes:
            status = "unknown"
            reason = "a structured dispatch lacks a resolvable route"
        elif Counter(observed_routes) != Counter(case.routes):
            status = "fail"
            reason = "structured dispatch routes do not match the case contract"
        elif "MISMATCH" in identity:
            status = "fail"
            reason = "structured runtime identity conflicts with the route contract"
        elif "UNKNOWN" in identity:
            status = "unknown"
            reason = "structured runtime identity is incomplete"
        elif not case.reviewer_min <= len(observation.reviewers) <= case.reviewer_max:
            status = "fail"
            reason = "reviewer dispatch count does not match the case contract"
        elif "MISMATCH" in reviewer_identity:
            status = "fail"
            reason = "reviewer runtime identity conflicts with the reviewer contract"
        elif "UNKNOWN" in reviewer_identity:
            status = "unknown"
            reason = "reviewer runtime identity is incomplete"
        else:
            status = "pass"
            reason = "marker and structured dispatch routes match"
    elif (
        selection_count
        or marker_count
        or observation.late_selection_count
        or observation.dispatches
        or observation.reviewers
    ):
        status = "fail"
        reason = (
            "negative case unexpectedly selected or dispatched Dynamic Workflow"
        )
    else:
        status = "pass"
        reason = (
            "complete event stream contains no Dynamic Workflow selection "
            "or dispatch"
        )

    if any(state == "UNKNOWN" for state in identity):
        limitations.append(
            "runtime model identity remains UNKNOWN for one or more routes"
        )
    if any(state == "MISMATCH" for state in identity):
        limitations.append("runtime model identity mismatch was observed")
    if any(state == "UNKNOWN" for state in reviewer_identity):
        limitations.append("reviewer runtime identity remains UNKNOWN")
    if any(state == "MISMATCH" for state in reviewer_identity):
        limitations.append("reviewer runtime identity mismatch was observed")
    if any(state == "UNKNOWN" for state in service_tier):
        limitations.append(
            "service tier telemetry remains UNKNOWN; route identity is unaffected"
        )
    if any(state == "MISMATCH" for state in service_tier):
        limitations.append(
            "service tier telemetry differs from the request; route identity is unaffected"
        )
    if any(state == "UNKNOWN" for state in reviewer_service_tier):
        limitations.append(
            "reviewer service tier telemetry remains UNKNOWN; reviewer identity is unaffected"
        )
    if any(state == "MISMATCH" for state in reviewer_service_tier):
        limitations.append(
            "reviewer service tier telemetry differs from the request; reviewer identity is unaffected"
        )
    if not observation.thread_ids or not observation.turn_ids:
        limitations.append(
            "one or more lifecycle identifiers were absent; available IDs "
            "were checked for consistency without inventing missing fields"
        )
    limitations.append(
        "route PASS does not authorize effects and is not reviewer "
        "or production acceptance"
    )

    return {
        "case": case.name,
        "status": status,
        "passed": status == "pass",
        "reason": reason,
        "expected": {
            "workflow": case.workflow,
            "routes": list(case.routes),
            "mode": case.mode or "simple-swarm",
            "reviewer_min": case.reviewer_min,
            "reviewer_max": case.reviewer_max,
        },
        "observed": {
            "terminal": observation.terminal,
            "runtime_failed": observation.runtime_failed,
            "invalid_lines": observation.invalid_lines,
            "thread_started_count": observation.thread_started_count,
            "turn_started_count": observation.turn_started_count,
            "terminal_count": observation.terminal_count,
            "thread_ids": sorted(observation.thread_ids),
            "turn_ids": sorted(observation.turn_ids),
            "sequence_errors": observation.sequence_errors,
            "selection_count": selection_count,
            "mode": observed_mode,
            "structured_selection_count": (
                observation.structured_selection_count
            ),
            "commentary_selection_count": (
                observation.commentary_selection_count
            ),
            "structured_selection_modes": (
                observation.structured_selection_modes
            ),
            "commentary_marker_modes": (
                observation.commentary_marker_modes
            ),
            "invalid_selection_mode_count": (
                observation.invalid_selection_mode_count
            ),
            "visible_marker_count": observation.visible_marker_count,
            "untrusted_marker_count": (
                observation.untrusted_marker_count
            ),
            "untrusted_marker_modes": observation.untrusted_marker_modes,
            "late_selection_count": observation.late_selection_count,
            "dispatch_conflict_tasks": (
                observation.dispatch_conflict_tasks
            ),
            "runtime_conflict_tasks": (
                observation.runtime_conflict_tasks
            ),
            "orphan_runtime_tasks": observation.orphan_runtime_tasks,
            "routes": observed_routes,
            "dispatches": [
                asdict(item) for item in observation.dispatches
            ],
            "reviewer_dispatches": [
                asdict(item) for item in observation.reviewers
            ],
            "identity": identity,
            "reviewer_identity": reviewer_identity,
            "service_tier": service_tier,
            "reviewer_service_tier": reviewer_service_tier,
        },
        "limitations": limitations,
    }


def _synthetic_transcript(case: SmokeCase) -> str:
    events: list[dict[str, Any]] = [
        {"type": "thread.started", "thread_id": "offline-fixture"},
        {"type": "turn.started", "turn_id": "offline-turn"},
    ]
    if case.workflow:
        events.append(
            {
                "type": "workflow.selected",
                "skill": "dynamic-workflow",
                "mode": case.mode or "simple-swarm",
            }
        )
        events.append(
            {
                "type": "item.completed",
                "item": {
                    "id": "marker",
                    "type": "agent_message",
                    "channel": "commentary",
                    "text": "Workflow: simple-swarm",
                },
            }
        )
    for index, route in enumerate(case.routes, start=1):
        task_name = f"fixture-{index}"
        if route == "Luna":
            arguments = {
                "agent_type": "luna",
                "task_name": task_name,
                "fork_turns": "none",
            }
            runtime = {
                "model": "gpt-5.6-luna",
                "effort": "max",
                "tier": "fast",
            }
        elif route == "Sol":
            arguments = {
                "agent_type": "sol",
                "task_name": task_name,
                "fork_turns": "none",
            }
            runtime = {"model": "gpt-5.6-sol", "effort": "xhigh"}
        elif route == "Explorer":
            arguments = {
                "agent_type": "explorer",
                "task_name": task_name,
                "fork_turns": "none",
            }
            runtime = {
                "model": "gpt-5.6-luna",
                "effort": "max",
            }
        else:
            raise ValueError(f"unsupported synthetic route: {route}")
        events.append(
            {
                "type": "item.completed",
                "item": {
                    "id": f"spawn-{index}",
                    "type": "tool_call",
                    "name": "collaboration.spawn_agent",
                    "arguments": arguments,
                },
            }
        )
        events.append(
            {"type": "subagent.runtime", "task_name": task_name, **runtime}
        )
    for index in range(case.reviewer_min):
        task_name = f"fixture-reviewer-{index + 1}"
        events.append(
            {
                "type": "item.completed",
                "item": {
                    "id": f"reviewer-{index + 1}",
                    "type": "tool_call",
                    "name": "collaboration.spawn_agent",
                    "arguments": {
                        "agent_type": "dynamic_workflow_sol_reviewer",
                        "task_name": task_name,
                        "fork_turns": "none",
                    },
                },
            }
        )
        events.append(
            {
                "type": "subagent.runtime",
                "task_name": task_name,
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
            }
        )
    events.append(
        {
            "type": "turn.completed",
            "turn_id": "offline-turn",
            "usage": {},
        }
    )
    return "\n".join(
        json.dumps(event, ensure_ascii=False) for event in events
    )


def run_self_test() -> dict[str, Any]:
    results = [
        evaluate_transcript(case, _synthetic_transcript(case))
        for case in CASES.values()
    ]
    adversarial = "\n".join(
        json.dumps(event, ensure_ascii=False)
        for event in (
            {
                "type": "turn.started",
                "prompt": (
                    "Workflow: simple-swarm Luna Sol Explorer"
                ),
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": "Workflow: simple-swarm",
                },
            },
            {"type": "turn.completed"},
        )
    )
    echo_result = evaluate_transcript(
        CASES["implicit-luna"], adversarial
    )
    incomplete_result = evaluate_transcript(
        CASES["implicit-luna"], '{"type":"turn.started"}'
    )
    passed = (
        all(item["status"] == "pass" for item in results)
        and echo_result["status"] == "unknown"
        and incomplete_result["status"] == "unknown"
    )
    return {
        "mode": "offline-evaluator-self-test",
        "codex_exec_calls": 0,
        "model_calls": 0,
        "network_calls": 0,
        "status": "pass" if passed else "fail",
        "passed": passed,
        "cases": results,
        "adversarial_prompt_echo": echo_result["status"],
        "incomplete_transcript": incomplete_result["status"],
        "limitation": (
            "synthetic PASS validates the evaluator, "
            "not live Dynamic Workflow routing"
        ),
    }


def build_live_command(codex: str, workdir: Path) -> list[str]:
    return [
        codex,
        "exec",
        "--ephemeral",
        "--json",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--color",
        "never",
        "-C",
        str(workdir),
        "-",
    ]


def _write_live_fixture(workdir: Path) -> None:
    fixtures = {
        "login.log": (
            "ERROR invalid session signature after token rotation\n"
        ),
        "inventory.log": "WARN sync batch waited 45s for lock\n",
        "package.json": '{"version":"1.0.0"}\n',
        "tsconfig.json": (
            '{"compilerOptions":{},"version":"5.0"}\n'
        ),
        "config.txt": "blue\n",
        "options.txt": "blue=stable\ngreen=experimental\n",
        "sample.py": (
            "def target():\n"
            "    return 1\n\n"
            "def caller():\n"
            "    return target()\n"
        ),
    }
    for name, content in fixtures.items():
        (workdir / name).write_text(content, encoding="utf-8")


_STDERR_SUMMARY_LIMIT = 512
_SENSITIVE_STDERR_HEADER = re.compile(
    r"(?im)\b(authorization|cookie|set-cookie)\s*[:=]\s*[^\r\n]*"
)
_SENSITIVE_STDERR_VALUE = re.compile(
    r"(?i)(?<![a-z0-9_-])"
    r"([a-z0-9_-]*(?:api[-_]?key|password|secret|token)[a-z0-9_-]*|api key)"
    r"(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s]+)"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[^\s,;]+")


def _decode_utf8(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _public_stderr_summary(stderr: str | bytes | None) -> str:
    text = _decode_utf8(stderr)
    text = _SENSITIVE_STDERR_HEADER.sub(
        lambda match: f"{match.group(1)}: [REDACTED]",
        text,
    )
    text = _BEARER_VALUE.sub("Bearer [REDACTED]", text)
    text = _SENSITIVE_STDERR_VALUE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    text = " ".join(text.split())
    if len(text) > _STDERR_SUMMARY_LIMIT:
        return text[: _STDERR_SUMMARY_LIMIT - 3] + "..."
    return text


def run_live(
    case: SmokeCase, timeout_seconds: int
) -> dict[str, Any]:
    codex = shutil.which("codex.exe") or shutil.which("codex")
    if codex is None:
        return {
            "mode": "live",
            "case": case.name,
            "status": "unknown",
            "passed": False,
            "codex_exec_calls": 0,
            "model_calls": 0,
            "reason": "codex executable was not found",
        }
    with tempfile.TemporaryDirectory(
        prefix="dynamic-workflow-routing-smoke-"
    ) as temp:
        workdir = Path(temp)
        _write_live_fixture(workdir)
        command = build_live_command(codex, workdir)
        try:
            completed = subprocess.run(
                command,
                input=case.prompt.encode("utf-8"),
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "mode": "live",
                "case": case.name,
                "status": "unknown",
                "passed": False,
                "codex_exec_calls": 1,
                "model_calls": "UNKNOWN",
                "reason": (
                    "the single live run timed out; it was not replayed"
                ),
            }

    result = evaluate_transcript(case, _decode_utf8(completed.stdout))
    result.update(
        {
            "mode": "live-single-run",
            "codex_exec_calls": 1,
            "model_calls": "UNKNOWN",
            "network_calls": "not confined by read-only sandbox",
            "process_returncode": completed.returncode,
            "stderr_summary": (
                _public_stderr_summary(completed.stderr)
                if completed.returncode != 0
                else ""
            ),
        }
    )
    if completed.returncode != 0:
        result["status"] = "unknown"
        result["passed"] = False
        result["reason"] = (
            "codex exec returned nonzero; the run was not replayed"
        )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Self-test or verify Dynamic Workflow structured routing evidence. "
            "Default and --transcript modes make no model call; "
            "--live makes one codex exec invocation; internal model calls "
            "remain UNKNOWN."
        )
    )
    parser.add_argument(
        "--json", action="store_true", help="emit one JSON object"
    )
    parser.add_argument(
        "--case",
        choices=tuple(CASES),
        help="case for transcript or live mode",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--transcript",
        type=Path,
        help="verify an existing JSONL transcript offline",
    )
    modes.add_argument(
        "--live",
        action="store_true",
        help=(
            "explicitly perform one real ephemeral read-only codex exec "
            "invocation; internal model calls remain UNKNOWN"
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="live run timeout (1-1800)",
    )
    return parser


def _emit(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    print(
        f"routing smoke: {result.get('status', 'unknown').upper()} "
        f"({result.get('mode', 'unknown')})"
    )
    print(result.get("reason") or result.get("limitation") or "")


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = _parser()
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 1800:
        parser.error("--timeout-seconds must be between 1 and 1800")

    if args.live or args.transcript is not None:
        if args.case is None:
            parser.error("--case is required with --live or --transcript")
        case = CASES[args.case]
        if args.live:
            result = run_live(case, args.timeout_seconds)
        else:
            try:
                transcript = args.transcript.read_text(encoding="utf-8")
            except OSError as exc:
                parser.error(str(exc))
            result = evaluate_transcript(case, transcript)
            result.update(
                {
                    "mode": "offline-transcript",
                    "codex_exec_calls": 0,
                    "model_calls": 0,
                    "network_calls": 0,
                }
            )
    else:
        result = run_self_test()

    _emit(result, args.json)
    return {"pass": 0, "fail": 1, "unknown": 2}.get(
        result.get("status"), 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
