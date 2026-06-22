# -*- coding: utf-8 -*-
"""Helpers for the codex-team-router MVP.

This module is intentionally local and deterministic. It does not call Codex
thread tools; callers pass thread/tool observations in as plain data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import uuid
from typing import Any, Mapping


class ProtocolError(ValueError):
    """Raised when a TEAM_ROUTER_* marker block is missing or invalid."""


class StateStoreError(ValueError):
    """Raised when registry or task ledger JSON cannot be read safely."""


@dataclass(frozen=True)
class ProtocolMessage:
    marker: str
    task_id: str
    fields: dict[str, str]
    raw: str


MARKER_RE = re.compile(r"^(TEAM_ROUTER_[A-Z_]+)\s+taskId=([^\s]+)\s*$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*)$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
MAX_OBSERVATION_CONTENT_CHARS = 8192
REGISTRY_VERSION = 1
TASK_LEDGER_VERSION = 1
ROLE_NAMES = frozenset({"manager", "executor", "verifier"})
THREAD_PERMISSIONS = frozenset({"read-only", "design-only"})
_FORBIDDEN_STATE_ROOT_PARTS = {".codex-tmp"}

TERMINAL_STATUSES = frozenset({
    "blocked",
    "malformed_callback",
    "tool_error",
    "missing_role",
    "abandoned",
})
RECOVERABLE_STATUSES = {
    "plan_unreachable": "planned",
    "callback_unreachable": "verifying",
}

_ALLOWED_BY_MARKER = {
    "TEAM_ROUTER_PLAN": {
        "status": {"planned", "blocked"},
        "acknowledgedPermission": {"read-only", "design-only", "escalation-required"},
    },
    "TEAM_ROUTER_CALLBACK": {
        "status": {"done", "blocked"},
        "final": {"true"},
    },
    "TEAM_ROUTER_VERDICT": {
        "result": {"pass", "needs_rework", "blocked"},
    },
}

_REQUIRED_BY_MARKER = {
    "TEAM_ROUTER_PLAN": (
        "status",
        "acknowledgedPermission",
        "scope",
        "stopWhen",
        "riskBoundary",
        "executorPrompt",
        "notes",
    ),
    "TEAM_ROUTER_CALLBACK": (
        "status",
        "final",
        "summary",
        "evidence",
        "risks",
        "next",
    ),
    "TEAM_ROUTER_VERDICT": (
        "result",
        "summary",
        "requiredChanges",
        "evidenceChecked",
        "risks",
    ),
}


def _validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
        raise ProtocolError("invalid taskId: %r" % (task_id,))


def _resolve_persistent_state_root(root: str | Path) -> Path:
    resolved = Path(root).resolve()
    parts = {part.lower() for part in resolved.parts}
    if parts.intersection(_FORBIDDEN_STATE_ROOT_PARTS):
        raise StateStoreError("stateRoot must not be under .codex-tmp: %s" % resolved)
    return resolved


def _iter_marker_blocks(text: str) -> list[ProtocolMessage]:
    if not isinstance(text, str):
        raise ProtocolError("message text must be a string")
    lines = text.splitlines()
    out: list[ProtocolMessage] = []
    current_marker: str | None = None
    current_task_id: str | None = None
    current_fields: dict[str, str] = {}
    current_field: str | None = None
    raw_lines: list[str] = []

    def flush() -> None:
        nonlocal current_marker, current_task_id, current_fields, current_field, raw_lines
        if current_marker is None or current_task_id is None:
            return
        out.append(ProtocolMessage(
            marker=current_marker,
            task_id=current_task_id,
            fields=dict(current_fields),
            raw="\n".join(raw_lines).strip(),
        ))
        current_marker = None
        current_task_id = None
        current_fields = {}
        current_field = None
        raw_lines = []

    for line in lines:
        stripped = line.strip()
        marker_match = MARKER_RE.match(stripped)
        if marker_match:
            flush()
            current_marker = marker_match.group(1)
            current_task_id = marker_match.group(2)
            _validate_task_id(current_task_id)
            raw_lines = [line]
            current_fields = {}
            current_field = None
            continue
        if stripped.startswith("TEAM_ROUTER_"):
            raise ProtocolError("malformed marker line: %s" % stripped)
        if current_marker is None:
            continue
        raw_lines.append(line)
        field_match = FIELD_RE.match(line)
        if field_match:
            current_field = field_match.group(1)
            current_fields[current_field] = field_match.group(2).strip()
            continue
        if current_field is not None and stripped:
            current_fields[current_field] = (
                current_fields[current_field] + "\n" + stripped
            ).strip()
    flush()
    return out


def parse_message(text: str, marker: str, task_id: str) -> ProtocolMessage:
    """Return the last valid marker block for marker/task_id.

    Marker lines must be exactly `TEAM_ROUTER_* taskId=<id>`. Ordinary fields use
    `key: value`. This intentionally rejects `taskId: <id>` marker lines.
    """
    _validate_task_id(task_id)
    candidates = [m for m in _iter_marker_blocks(text)
                  if m.marker == marker and m.task_id == task_id]
    if not candidates:
        raise ProtocolError("missing %s taskId=%s" % (marker, task_id))
    msg = candidates[-1]
    required = _REQUIRED_BY_MARKER.get(marker, ())
    missing = [field for field in required if field not in msg.fields]
    if missing:
        raise ProtocolError("%s missing fields: %s" % (marker, ", ".join(missing)))
    blank = [field for field in required if not msg.fields[field]]
    if blank:
        raise ProtocolError("%s blank fields: %s" % (marker, ", ".join(blank)))
    for field, allowed in _ALLOWED_BY_MARKER.get(marker, {}).items():
        value = msg.fields.get(field)
        if value not in allowed:
            raise ProtocolError(
                "%s.%s must be one of %s, got %r"
                % (marker, field, sorted(allowed), value)
            )
    return msg


def parse_plan(text: str, task_id: str) -> ProtocolMessage:
    return parse_message(text, "TEAM_ROUTER_PLAN", task_id)


def parse_callback(text: str, task_id: str) -> ProtocolMessage:
    return parse_message(text, "TEAM_ROUTER_CALLBACK", task_id)


def parse_verdict(text: str, task_id: str) -> ProtocolMessage:
    return parse_message(text, "TEAM_ROUTER_VERDICT", task_id)


def manual_recovery_target(status: str) -> str:
    try:
        return RECOVERABLE_STATUSES[status]
    except KeyError as exc:
        raise ValueError("status is not manually recoverable: %s" % status) from exc


def next_rework_dispatch(rework_count: int, max_rework: int) -> tuple[str, int]:
    if not isinstance(rework_count, int) or not isinstance(max_rework, int):
        raise ValueError("rework counters must be integers")
    if rework_count < 0 or max_rework < 0:
        raise ValueError("rework counters must be non-negative")
    if rework_count >= max_rework:
        return "blocked", rework_count
    return "dispatched", rework_count + 1


def resolve_state_root(current_root: str | Path,
                       *,
                       canonical_root: str | Path | None = None,
                       explicit_state_root: str | Path | None = None) -> Path:
    if explicit_state_root is not None:
        return _resolve_persistent_state_root(explicit_state_root)
    root = Path(canonical_root if canonical_root is not None else current_root)
    return _resolve_persistent_state_root(root / ".codex-team-router")


def registry_path(state_root: str | Path, project_id: str) -> Path:
    _validate_task_id(project_id)
    return (
        _resolve_persistent_state_root(state_root)
        / "projects" / project_id / "registry.json"
    )


def task_path(state_root: str | Path, project_id: str, task_id: str) -> Path:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    return (
        _resolve_persistent_state_root(state_root)
        / "projects" / project_id / "tasks" / (task_id + ".json")
    )


def _as_mapping(value: Any, field: str, *, default_empty: bool = True) -> dict[str, Any]:
    if value is None and default_empty:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise StateStoreError("%s must be a JSON object" % field)


def _as_list(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    raise StateStoreError("%s must be a JSON array" % field)


def _as_int(value: Any, default: int, field: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateStoreError("%s must be an integer" % field)
    return value


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise StateStoreError("missing JSON file: %s" % path) from exc
    except PermissionError as exc:
        raise StateStoreError("cannot read JSON file: %s: %s" % (path, exc)) from exc
    except json.JSONDecodeError as exc:
        raise StateStoreError("invalid JSON in %s: %s" % (path, exc.msg)) from exc
    return _as_mapping(data, str(path), default_empty=False)


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name("%s.%s.tmp" % (path.name, uuid.uuid4().hex))
    try:
        with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _normalize_registry(data: Mapping[str, Any], state_root: str | Path,
                        project_id: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    root = str(_resolve_persistent_state_root(state_root))
    registry = dict(data)
    projects = _as_mapping(registry.get("projects"), "registry.projects")
    project = _as_mapping(
        projects.get(project_id),
        "registry.projects.%s" % project_id,
    )
    roles = _as_mapping(project.get("roles"), "registry.projects.%s.roles" % project_id)

    registry["version"] = REGISTRY_VERSION
    registry["stateRoot"] = root
    project.setdefault("projectName", "")
    project.setdefault("canonicalRoot", "")
    project.setdefault("localPathHash", "")
    project.setdefault("target", {})
    project.setdefault("targetFingerprint", "")
    project.setdefault("hostId", "")
    project["projectId"] = project_id
    project["roles"] = roles
    projects[project_id] = project
    registry["projects"] = projects
    return registry


def load_registry(state_root: str | Path, project_id: str) -> dict[str, Any]:
    path = registry_path(state_root, project_id)
    if path.exists():
        data = _read_json_object(path)
    else:
        data = {}
    return _normalize_registry(data, state_root, project_id)


def save_registry(state_root: str | Path, project_id: str,
                  registry: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_registry(registry, state_root, project_id)
    _atomic_write_json(registry_path(state_root, project_id), normalized)
    return normalized


def _normalize_task_ledger(data: Mapping[str, Any], state_root: str | Path,
                           project_id: str, task_id: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    ledger = dict(data)
    ledger["version"] = TASK_LEDGER_VERSION
    ledger["taskId"] = task_id
    ledger["projectId"] = project_id
    ledger["stateRoot"] = str(_resolve_persistent_state_root(state_root))
    ledger["projectLocalPath"] = str(ledger.get("projectLocalPath") or "")
    ledger["objective"] = str(ledger.get("objective") or "")
    ledger["status"] = str(ledger.get("status") or "created")
    ledger["reworkCount"] = _as_int(ledger.get("reworkCount"), 0, "ledger.reworkCount")
    ledger["maxRework"] = _as_int(ledger.get("maxRework"), 3, "ledger.maxRework")
    ledger["dispatches"] = _as_list(ledger.get("dispatches"), "ledger.dispatches")
    ledger["observations"] = _as_list(ledger.get("observations"), "ledger.observations")
    plan_request = ledger.get("planRequest")
    ledger["planRequest"] = None if plan_request is None else _as_mapping(plan_request, "ledger.planRequest", default_empty=False)
    plan = ledger.get("plan")
    ledger["plan"] = None if plan is None else _as_mapping(plan, "ledger.plan", default_empty=False)
    verification = ledger.get("verification")
    ledger["verification"] = None if verification is None else _as_mapping(verification, "ledger.verification", default_empty=False)
    ledger.setdefault("closeout", None)
    return ledger


def new_task_ledger(state_root: str | Path,
                    project_id: str,
                    task_id: str,
                    *,
                    objective: str,
                    project_local_path: str | Path,
                    max_rework: int = 3) -> dict[str, Any]:
    if not isinstance(objective, str) or not objective:
        raise StateStoreError("objective must be a non-empty string")
    if not isinstance(max_rework, int) or isinstance(max_rework, bool) or max_rework < 0:
        raise StateStoreError("maxRework must be a non-negative integer")
    return _normalize_task_ledger({
        "projectLocalPath": str(Path(project_local_path).resolve()),
        "objective": objective,
        "status": "created",
        "reworkCount": 0,
        "maxRework": max_rework,
        "dispatches": [],
        "observations": [],
        "verification": None,
        "closeout": None,
    }, state_root, project_id, task_id)


def load_task_ledger(state_root: str | Path, project_id: str,
                     task_id: str) -> dict[str, Any]:
    data = _read_json_object(task_path(state_root, project_id, task_id))
    return _normalize_task_ledger(data, state_root, project_id, task_id)


def save_task_ledger(state_root: str | Path,
                     project_id: str,
                     task_id: str,
                     ledger: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_task_ledger(ledger, state_root, project_id, task_id)
    _atomic_write_json(task_path(state_root, project_id, task_id), normalized)
    return normalized




def create_task_id(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    return "ctr-%s-%s" % (now.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])


def _validate_role(role: str) -> None:
    if role not in ROLE_NAMES:
        raise StateStoreError("invalid role: %s" % role)


def _validate_permission(permission: str) -> None:
    if permission not in THREAD_PERMISSIONS:
        raise StateStoreError("invalid Team Router permission: %s" % permission)


def _required_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise StateStoreError("%s must be a non-empty string" % field)
    return value


def _search_anchor(message_id: str | None, sent_at: str) -> dict[str, Any]:
    return {"messageId": message_id, "sentAt": sent_at}


def _normalize_role_record(role: str, data: Mapping[str, Any],
                           observed_at: str) -> dict[str, Any]:
    _validate_role(role)
    record = dict(_as_mapping(data, "roles.%s" % role, default_empty=False))
    record["threadId"] = _required_str(record.get("threadId"), "roles.%s.threadId" % role)
    record["title"] = str(record.get("title") or "TeamRouter %s" % role)
    record["status"] = str(record.get("status") or "active")
    record.setdefault("createdAt", observed_at)
    record["lastObservedAt"] = observed_at
    return record


def update_registry_roles(state_root: str | Path,
                          project_id: str,
                          roles: Mapping[str, Mapping[str, Any]],
                          observed_at: str) -> dict[str, Any]:
    registry = load_registry(state_root, project_id)
    project = registry["projects"][project_id]
    project_roles = _as_mapping(project.get("roles"), "registry.project.roles")
    for role, data in roles.items():
        project_roles[role] = _normalize_role_record(role, data, observed_at)
    project["roles"] = project_roles
    registry["projects"][project_id] = project
    return save_registry(state_root, project_id, registry)


def create_team_task(state_root: str | Path,
                     project_id: str,
                     task_id: str,
                     *,
                     objective: str,
                     project_local_path: str | Path,
                     roles: Mapping[str, Mapping[str, Any]],
                     observed_at: str,
                     max_rework: int = 3) -> dict[str, Any]:
    missing = sorted(ROLE_NAMES.difference(roles.keys()))
    if missing:
        raise StateStoreError("missing role bindings: %s" % ", ".join(missing))
    update_registry_roles(state_root, project_id, roles, observed_at)
    ledger = new_task_ledger(
        state_root,
        project_id,
        task_id,
        objective=objective,
        project_local_path=project_local_path,
        max_rework=max_rework,
    )
    ledger["status"] = "roles_ready"
    return save_task_ledger(state_root, project_id, task_id, ledger)


def make_plan_request_message(task_id: str, objective: str, permission: str) -> str:
    _validate_task_id(task_id)
    _required_str(objective, "objective")
    _validate_permission(permission)
    return "\n".join((
        "TEAM_ROUTER_PLAN_REQUEST taskId=%s" % task_id,
        "objective: %s" % objective,
        "permission: %s" % permission,
        "",
        "Please reply in this thread with:",
        "TEAM_ROUTER_PLAN taskId=%s" % task_id,
        "status: planned | blocked",
        "acknowledgedPermission: read-only | design-only | escalation-required",
        "scope: <clear scope>",
        "stopWhen: <done or blocked condition>",
        "riskBoundary: <permission/data/external-system boundary>",
        "executorPrompt: <prompt for executor>",
        "notes: <none or notes>",
    ))


def record_plan_request_sent(state_root: str | Path,
                             project_id: str,
                             task_id: str,
                             *,
                             manager_thread_id: str,
                             sent_at: str,
                             message_id: str | None = None) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    ledger["planRequest"] = {
        "role": "manager",
        "threadId": _required_str(manager_thread_id, "managerThreadId"),
        "messageId": message_id,
        "sentAt": _required_str(sent_at, "sentAt"),
        "searchAnchor": _search_anchor(message_id, sent_at),
        "expectedCallback": "TEAM_ROUTER_PLAN taskId=%s" % task_id,
    }
    ledger["status"] = "awaiting_plan"
    return save_task_ledger(state_root, project_id, task_id, ledger)


def make_executor_dispatch_message(task_id: str,
                                   plan_fields: Mapping[str, Any],
                                   permission: str,
                                   search_anchor: Mapping[str, Any]) -> str:
    _validate_task_id(task_id)
    _validate_permission(permission)
    scope = _required_str(plan_fields.get("scope"), "plan.scope")
    stop_when = _required_str(plan_fields.get("stopWhen"), "plan.stopWhen")
    executor_prompt = _required_str(plan_fields.get("executorPrompt"), "plan.executorPrompt")
    return "\n".join((
        "TEAM_ROUTER_DISPATCH taskId=%s" % task_id,
        "role: executor",
        "callbackMode: self-thread-marker",
        "callbackMarker: TEAM_ROUTER_CALLBACK taskId=%s" % task_id,
        "permission: %s" % permission,
        "scope: %s" % scope,
        "stopWhen: %s" % stop_when,
        "searchAnchor: %s" % dict(search_anchor),
        "",
        "Goal:",
        executor_prompt,
        "",
        "Delivery format:",
        "TEAM_ROUTER_CALLBACK taskId=%s" % task_id,
        "status: done | blocked",
        "final: true",
        "summary: <3-7 lines>",
        "evidence: <paths, command summaries, or thread observations>",
        "risks: <none or risks>",
        "next: <none or next step>",
    ))


def record_executor_dispatch_sent(state_root: str | Path,
                                  project_id: str,
                                  task_id: str,
                                  *,
                                  executor_thread_id: str,
                                  sent_at: str,
                                  message_id: str | None = None) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    if ledger["status"] == "needs_rework":
        status, rework_count = next_rework_dispatch(ledger["reworkCount"], ledger["maxRework"])
        if status == "blocked":
            ledger["status"] = "blocked"
            ledger["closeout"] = {
                "status": "blocked",
                "capturedAt": sent_at,
                "summary": "maximum rework attempts reached",
                "requiredChanges": "none",
                "evidenceChecked": "reworkCount",
                "risks": "none",
                "nextAction": "none",
            }
            return save_task_ledger(state_root, project_id, task_id, ledger)
        ledger["reworkCount"] = rework_count
    attempt = len(ledger["dispatches"]) + 1
    ledger["dispatches"].append({
        "role": "executor",
        "threadId": _required_str(executor_thread_id, "executorThreadId"),
        "messageId": message_id,
        "sentAt": _required_str(sent_at, "sentAt"),
        "searchAnchor": _search_anchor(message_id, sent_at),
        "expectedCallback": "TEAM_ROUTER_CALLBACK taskId=%s" % task_id,
        "attempt": attempt,
    })
    ledger["status"] = "awaiting_callback"
    return save_task_ledger(state_root, project_id, task_id, ledger)


def _message_text(message: Mapping[str, Any]) -> str:
    for key in ("text", "content", "summary"):
        value = message.get(key)
        if isinstance(value, str):
            return value
    return ""


def _messages_after_anchor(messages: list[Mapping[str, Any]],
                           anchor: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not anchor:
        return list(messages)
    message_id = anchor.get("messageId")
    if message_id:
        for index, message in enumerate(messages):
            if message.get("messageId") == message_id:
                return list(messages[index + 1:])
    sent_at = anchor.get("sentAt")
    anchor_time = _parse_thread_timestamp(sent_at)
    if anchor_time is None:
        return list(messages)
    filtered = []
    for message in messages:
        ts = _parse_thread_timestamp(
            message.get("sentAt") or message.get("createdAt") or message.get("timestamp")
        )
        if ts is not None and ts > anchor_time:
            filtered.append(message)
    return filtered


def _messages_text(messages: list[Mapping[str, Any]]) -> str:
    return "\n\n".join(_message_text(message) for message in messages if _message_text(message))


def _project_roles_from_registry(registry: Mapping[str, Any], project_id: str) -> dict[str, Any]:
    projects = _as_mapping(registry.get("projects"), "registry.projects")
    project = _as_mapping(projects.get(project_id), "registry.project", default_empty=False)
    return _as_mapping(project.get("roles"), "registry.project.roles")


def recovery_read_request(ledger: Mapping[str, Any],
                          registry: Mapping[str, Any],
                          role: str) -> dict[str, Any]:
    _validate_role(role)
    project_id = _required_str(ledger.get("projectId"), "ledger.projectId")
    source: Mapping[str, Any] | None
    if role == "manager":
        source = ledger.get("planRequest") if isinstance(ledger.get("planRequest"), Mapping) else None
    elif role == "executor":
        dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
        source = dispatches[-1] if dispatches else None
    else:
        verification = ledger.get("verification") if isinstance(ledger.get("verification"), Mapping) else None
        request = verification.get("request") if isinstance(verification, Mapping) else None
        source = request if isinstance(request, Mapping) else None
    if source is None:
        raise StateStoreError("no read request anchor for role: %s" % role)
    roles = _project_roles_from_registry(registry, project_id)
    role_record = _as_mapping(roles.get(role), "registry.roles.%s" % role, default_empty=False)
    thread_id = source.get("threadId") or role_record.get("threadId")
    return {
        "role": role,
        "threadId": _required_str(thread_id, "%s.threadId" % role),
        "searchAnchor": _as_mapping(source.get("searchAnchor"), "%s.searchAnchor" % role, default_empty=False),
        "expectedCallback": source.get("expectedCallback"),
    }


def capture_manager_plan_from_read(state_root: str | Path,
                                   project_id: str,
                                   task_id: str,
                                   messages: list[Mapping[str, Any]],
                                   *,
                                   captured_at: str) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    request = ledger.get("planRequest") if isinstance(ledger.get("planRequest"), Mapping) else None
    anchor = request.get("searchAnchor") if isinstance(request, Mapping) else None
    if anchor is None:
        raise StateStoreError("missing plan request searchAnchor for task: %s" % task_id)
    if not read_window_covers_anchor(messages, anchor):
        ledger["status"] = "plan_unreachable"
        return save_task_ledger(state_root, project_id, task_id, ledger)
    text = _messages_text(_messages_after_anchor(messages, anchor))
    try:
        msg = parse_plan(text, task_id)
    except ProtocolError as exc:
        if str(exc).startswith("missing "):
            ledger["status"] = "awaiting_plan"
        else:
            ledger["status"] = "malformed_callback"
        return save_task_ledger(state_root, project_id, task_id, ledger)
    ledger["plan"] = {
        "threadId": request.get("threadId") if isinstance(request, Mapping) else None,
        "capturedAt": captured_at,
        "raw": msg.raw,
        "fields": dict(msg.fields),
    }
    if msg.fields["status"] == "planned" and msg.fields["acknowledgedPermission"] != "escalation-required":
        ledger["status"] = "planned"
    else:
        ledger["status"] = "blocked"
    return save_task_ledger(state_root, project_id, task_id, ledger)


def capture_executor_callback_from_read(state_root: str | Path,
                                        project_id: str,
                                        task_id: str,
                                        messages: list[Mapping[str, Any]],
                                        *,
                                        captured_at: str) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    dispatch = ledger["dispatches"][-1] if ledger["dispatches"] else None
    if dispatch is None:
        raise StateStoreError("no executor dispatch recorded for task: %s" % task_id)
    anchor = dispatch.get("searchAnchor")
    if not read_window_covers_anchor(messages, anchor):
        ledger["status"] = "callback_unreachable"
        return save_task_ledger(state_root, project_id, task_id, ledger)
    text = _messages_text(_messages_after_anchor(messages, anchor))
    try:
        msg = parse_callback(text, task_id)
    except ProtocolError as exc:
        if str(exc).startswith("missing "):
            ledger["status"] = "awaiting_callback"
        else:
            ledger["status"] = "malformed_callback"
        return save_task_ledger(state_root, project_id, task_id, ledger)
    ledger["observations"].append(make_observation(
        "callback_raw",
        "executor",
        dispatch["threadId"],
        captured_at,
        msg.raw,
        msg.fields,
    ))
    ledger["status"] = "verifying"
    return save_task_ledger(state_root, project_id, task_id, ledger)


def make_verifier_request_message(task_id: str,
                                  callback_block: str,
                                  permission: str,
                                  scope: str) -> str:
    _validate_task_id(task_id)
    _validate_permission(permission)
    _required_str(callback_block, "callbackBlock")
    _required_str(scope, "scope")
    return "\n".join((
        "TEAM_ROUTER_VERIFY taskId=%s" % task_id,
        "callbackMarker: TEAM_ROUTER_VERDICT taskId=%s" % task_id,
        "permission: %s" % permission,
        "scope: %s" % scope,
        "",
        "Executor callback follows verbatim:",
        callback_block,
        "",
        "Please reply in this thread with:",
        "TEAM_ROUTER_VERDICT taskId=%s" % task_id,
        "result: pass | needs_rework | blocked",
        "summary: <verdict summary>",
        "requiredChanges: <none or changes>",
        "evidenceChecked: <checked evidence>",
        "risks: <none or risks>",
    ))


def record_verifier_request_sent(state_root: str | Path,
                                 project_id: str,
                                 task_id: str,
                                 *,
                                 verifier_thread_id: str,
                                 sent_at: str,
                                 message_id: str | None = None) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    verification = dict(ledger.get("verification") or {})
    verification["request"] = {
        "role": "verifier",
        "threadId": _required_str(verifier_thread_id, "verifierThreadId"),
        "messageId": message_id,
        "sentAt": _required_str(sent_at, "sentAt"),
        "searchAnchor": _search_anchor(message_id, sent_at),
        "expectedCallback": "TEAM_ROUTER_VERDICT taskId=%s" % task_id,
    }
    ledger["verification"] = verification
    ledger["status"] = "verifying"
    return save_task_ledger(state_root, project_id, task_id, ledger)


def _make_closeout(ledger: Mapping[str, Any],
                   verdict_fields: Mapping[str, Any],
                   captured_at: str) -> dict[str, Any]:
    return {
        "status": ledger.get("status"),
        "capturedAt": captured_at,
        "summary": verdict_fields.get("summary", ""),
        "requiredChanges": verdict_fields.get("requiredChanges", ""),
        "evidenceChecked": verdict_fields.get("evidenceChecked", ""),
        "risks": verdict_fields.get("risks", ""),
        "nextAction": "none" if ledger.get("status") == "done" else verdict_fields.get("requiredChanges", ""),
    }


def capture_verifier_verdict_from_read(state_root: str | Path,
                                       project_id: str,
                                       task_id: str,
                                       messages: list[Mapping[str, Any]],
                                       *,
                                       captured_at: str) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    verification = dict(ledger.get("verification") or {})
    request = verification.get("request") if isinstance(verification.get("request"), Mapping) else None
    anchor = request.get("searchAnchor") if isinstance(request, Mapping) else None
    if anchor is None:
        raise StateStoreError("missing verifier request searchAnchor for task: %s" % task_id)
    if not read_window_covers_anchor(messages, anchor):
        ledger["status"] = "callback_unreachable"
        return save_task_ledger(state_root, project_id, task_id, ledger)
    text = _messages_text(_messages_after_anchor(messages, anchor))
    try:
        msg = parse_verdict(text, task_id)
    except ProtocolError as exc:
        if str(exc).startswith("missing "):
            ledger["status"] = "verifying"
        else:
            ledger["status"] = "malformed_callback"
        return save_task_ledger(state_root, project_id, task_id, ledger)
    thread_id = request.get("threadId") if isinstance(request, Mapping) else ""
    if thread_id:
        ledger["observations"].append(make_observation(
            "verdict_raw",
            "verifier",
            thread_id,
            captured_at,
            msg.raw,
            msg.fields,
        ))
    verification["verdict"] = {
        "threadId": thread_id,
        "capturedAt": captured_at,
        "raw": msg.raw,
        "fields": dict(msg.fields),
    }
    ledger["verification"] = verification
    result = msg.fields["result"]
    if result == "pass":
        ledger["status"] = "done"
    elif result == "needs_rework":
        if ledger["reworkCount"] >= ledger["maxRework"]:
            ledger["status"] = "blocked"
        else:
            ledger["status"] = "needs_rework"
    else:
        ledger["status"] = "blocked"
    ledger["closeout"] = _make_closeout(ledger, msg.fields, captured_at)
    return save_task_ledger(state_root, project_id, task_id, ledger)


def _parse_thread_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def read_window_covers_anchor(messages: list[Mapping[str, Any]],
                              anchor: Mapping[str, Any]) -> bool:
    """Whether read_thread output proves it covers the anchor point.

    Returns False when messages have no stable message id or timestamp. That maps
    to plan_unreachable/callback_unreachable in the workflow.
    """
    if not messages:
        return False
    message_id = anchor.get("messageId")
    sent_at = anchor.get("sentAt")
    if message_id:
        return any(msg.get("messageId") == message_id for msg in messages)
    if not sent_at:
        return False
    anchor_time = _parse_thread_timestamp(sent_at)
    if anchor_time is None:
        return False
    timestamps = [
        _parse_thread_timestamp(
            msg.get("sentAt") or msg.get("createdAt") or msg.get("timestamp")
        )
        for msg in messages
    ]
    timestamps = [ts for ts in timestamps if ts is not None]
    if not timestamps:
        return False
    return min(timestamps) <= anchor_time


def make_observation(obs_type: str,
                     role: str,
                     thread_id: str,
                     captured_at: str,
                     content: str,
                     parsed_fields: Mapping[str, Any]) -> dict[str, Any]:
    if obs_type not in {"callback_raw", "verdict_raw", "plan_raw", "read_result", "system_event"}:
        raise ValueError("invalid observation type: %s" % obs_type)
    if role not in {"manager", "executor", "verifier", "system"}:
        raise ValueError("invalid observation role: %s" % role)
    for name, value in {
        "threadId": thread_id,
        "capturedAt": captured_at,
        "content": content,
    }.items():
        if not isinstance(value, str) or not value:
            raise ValueError("%s must be a non-empty string" % name)
    if len(content) > MAX_OBSERVATION_CONTENT_CHARS:
        raise ProtocolError(
            "content exceeds %d characters" % MAX_OBSERVATION_CONTENT_CHARS
        )
    if not isinstance(parsed_fields, Mapping):
        raise ValueError("parsedFields must be a mapping")
    return {
        "type": obs_type,
        "role": role,
        "threadId": thread_id,
        "capturedAt": captured_at,
        "content": content,
        "parsedFields": dict(parsed_fields),
    }