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
    "done",
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


def _raise_if_terminal(ledger: Mapping[str, Any], action: str) -> None:
    status = ledger.get("status")
    if status in TERMINAL_STATUSES:
        raise StateStoreError(
            "cannot %s terminal task status: %s" % (action, status)
        )


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


def _adapter_call(thread_adapter: Any, method_name: str, **kwargs: Any) -> Any:
    if isinstance(thread_adapter, Mapping):
        method = thread_adapter.get(method_name)
    else:
        method = getattr(thread_adapter, method_name, None)
    if not callable(method):
        raise StateStoreError("thread adapter missing callable: %s" % method_name)
    return method(**kwargs)


def _optional_nonempty_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _first_str(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _optional_nonempty_str(mapping.get(key))
        if value is not None:
            return value
    return None


def _optional_timestamp_value(value: Any) -> str | int | float | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _first_timestamp(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str | int | float | None:
    for key in keys:
        value = _optional_timestamp_value(mapping.get(key))
        if value is not None:
            return value
    return None


def _candidate_mappings(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, Mapping):
        return []
    candidates: list[Mapping[str, Any]] = [result]
    for key in ("message", "data", "result", "thread"):
        nested = result.get(key)
        if isinstance(nested, Mapping):
            candidates.append(nested)
    return candidates


def thread_send_anchor(send_result: Any, *, fallback_sent_at: str) -> dict[str, Any]:
    sent_at_fallback = _required_str(fallback_sent_at, "fallbackSentAt")
    message_id: str | None = None
    sent_at: str | None = None
    for candidate in _candidate_mappings(send_result):
        if message_id is None:
            message_id = _first_str(candidate, ("messageId", "message_id", "id"))
        if sent_at is None:
            sent_at = _first_str(candidate, (
                "sentAt", "sent_at", "createdAt", "created_at", "timestamp",
            ))
    return {"messageId": message_id, "sentAt": sent_at or sent_at_fallback}


def _content_blocks_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    if isinstance(value, Mapping):
        text = value.get("text") or value.get("content")
        if isinstance(text, str):
            return text
    return ""


def _normalize_thread_message(message: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(message)
    message_id = _first_str(message, ("messageId", "message_id", "id", "turnId"))
    sent_at = _first_timestamp(message, (
        "sentAt", "sent_at", "createdAt", "created_at", "timestamp",
    ))
    text = _first_str(message, ("text",)) or ""
    if not text:
        for key in ("content", "output", "response"):
            text = _content_blocks_text(message.get(key))
            if text:
                break
    if not text:
        text = _first_str(message, ("summary",)) or ""
    normalized["messageId"] = message_id
    if sent_at is not None:
        normalized["sentAt"] = sent_at
    normalized["text"] = text
    return normalized


def _read_messages_from_mapping(read_result: Mapping[str, Any]) -> Any:
    for key in ("messages", "turns", "items"):
        value = read_result.get(key)
        if value is not None:
            return value
    for key in ("thread", "data", "result"):
        nested = read_result.get(key)
        if isinstance(nested, Mapping):
            value = _read_messages_from_mapping(nested)
            if value is not None:
                return value
    return None


def _turn_item_messages(turns: list[Any]) -> list[dict[str, Any]] | None:
    out: list[dict[str, Any]] = []
    saw_turn_items = False
    for turn_index, turn in enumerate(turns):
        if not isinstance(turn, Mapping):
            return None
        items = turn.get("items")
        if not isinstance(items, list):
            continue
        saw_turn_items = True
        turn_time = _first_timestamp(turn, (
            "sentAt", "sent_at", "createdAt", "created_at",
            "startedAt", "started_at", "timestamp",
        ))
        for item_index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise StateStoreError(
                    "read_thread turn %d item %d must be a JSON object"
                    % (turn_index, item_index)
                )
            message = dict(item)
            if turn_time is not None and _first_timestamp(message, (
                "sentAt", "sent_at", "createdAt", "created_at", "timestamp",
            )) is None:
                message["sentAt"] = turn_time
            out.append(message)
    return out if saw_turn_items else None


def normalize_thread_read_messages(read_result: Any) -> list[dict[str, Any]]:
    if isinstance(read_result, list):
        raw_messages = _turn_item_messages(read_result) or read_result
    elif isinstance(read_result, Mapping):
        raw_messages = _read_messages_from_mapping(read_result)
        if isinstance(raw_messages, list):
            raw_messages = _turn_item_messages(raw_messages) or raw_messages
    else:
        raise StateStoreError("read_thread result must be a JSON object or array")
    if not isinstance(raw_messages, list):
        raise StateStoreError("read_thread result does not contain a messages array")
    out: list[dict[str, Any]] = []
    for index, message in enumerate(raw_messages):
        if not isinstance(message, Mapping):
            raise StateStoreError("read_thread message %d must be a JSON object" % index)
        out.append(_normalize_thread_message(message))
    return out


def _thread_id_from_create_result(create_result: Any, role: str) -> str:
    for candidate in _candidate_mappings(create_result):
        thread_id = _first_str(candidate, ("threadId", "thread_id", "id"))
        if thread_id is not None:
            return thread_id
    raise StateStoreError("create_thread result missing thread id for role: %s" % role)


def _role_thread_id(state_root: str | Path, project_id: str, role: str) -> str:
    registry = load_registry(state_root, project_id)
    roles = _project_roles_from_registry(registry, project_id)
    role_record = _as_mapping(roles.get(role), "registry.roles.%s" % role, default_empty=False)
    return _required_str(role_record.get("threadId"), "registry.roles.%s.threadId" % role)


def make_role_thread_prompt(project_id: str, role: str, objective: str) -> str:
    _validate_task_id(project_id)
    _validate_role(role)
    _required_str(objective, "objective")
    return "\n".join((
        "Codex Team Router role thread",
        "projectId: %s" % project_id,
        "role: %s" % role,
        "objective: %s" % objective,
        "Wait for TEAM_ROUTER_* protocol messages before acting.",
    ))


def create_role_threads_with_adapter(thread_adapter: Any,
                                     *,
                                     project_id: str,
                                     objective: str,
                                     target: Mapping[str, Any],
                                     observed_at: str) -> dict[str, dict[str, Any]]:
    roles: dict[str, dict[str, Any]] = {}
    for role in sorted(ROLE_NAMES):
        prompt = make_role_thread_prompt(project_id, role, objective)
        result = _adapter_call(
            thread_adapter,
            "create_thread",
            prompt=prompt,
            target=dict(target),
        )
        thread_id = _thread_id_from_create_result(result, role)
        title = "TeamRouter %s - %s" % (role, project_id)
        for candidate in _candidate_mappings(result):
            found_title = _optional_nonempty_str(candidate.get("title"))
            if found_title:
                title = found_title
                break
        roles[role] = {
            "threadId": thread_id,
            "title": title,
            "createdAt": observed_at,
            "lastObservedAt": observed_at,
        }
    return roles


def start_team_task_with_adapter(state_root: str | Path,
                                 project_id: str,
                                 task_id: str,
                                 *,
                                 objective: str,
                                 project_local_path: str | Path,
                                 thread_adapter: Any,
                                 target: Mapping[str, Any],
                                 observed_at: str,
                                 max_rework: int = 3) -> dict[str, Any]:
    roles = create_role_threads_with_adapter(
        thread_adapter,
        project_id=project_id,
        objective=objective,
        target=target,
        observed_at=observed_at,
    )
    return create_team_task(
        state_root,
        project_id,
        task_id,
        objective=objective,
        project_local_path=project_local_path,
        roles=roles,
        observed_at=observed_at,
        max_rework=max_rework,
    )

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
    _raise_if_terminal(ledger, "record plan request for")
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
        "searchAnchor: %s" % json.dumps(dict(search_anchor), sort_keys=True),
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
    _raise_if_terminal(ledger, "dispatch")
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
        ledger["closeout"] = None
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


def _message_first_line(message: Mapping[str, Any]) -> str:
    text = _message_text(message).lstrip()
    return text.splitlines()[0].strip() if text else ""


def _message_kind(message: Mapping[str, Any]) -> str:
    value = _first_str(message, ("type", "role", "senderRole", "authorRole"))
    return (value or "").replace("_", "").replace("-", "").lower()


def _is_anchor_request_message(message: Mapping[str, Any]) -> bool:
    kind = _message_kind(message)
    if kind in {"user", "human", "usermessage"}:
        return True
    return _message_first_line(message).startswith((
        "TEAM_ROUTER_PLAN_REQUEST",
        "TEAM_ROUTER_DISPATCH",
        "TEAM_ROUTER_VERIFY",
    ))


def _is_same_timestamp_response_message(message: Mapping[str, Any]) -> bool:
    kind = _message_kind(message)
    if kind in {"agent", "assistant", "model", "agentmessage", "assistantmessage"}:
        return True
    return _message_first_line(message).startswith((
        "TEAM_ROUTER_PLAN taskId=",
        "TEAM_ROUTER_CALLBACK taskId=",
        "TEAM_ROUTER_VERDICT taskId=",
    ))


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
        if ts is None:
            continue
        if ts > anchor_time:
            filtered.append(message)
        elif (
            ts == anchor_time
            and _is_same_timestamp_response_message(message)
            and not _is_anchor_request_message(message)
        ):
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
    _raise_if_terminal(ledger, "capture manager plan for")
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
    _raise_if_terminal(ledger, "capture executor callback for")
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
    _raise_if_terminal(ledger, "record verifier request for")
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
    verdict = verification.get("verdict") if isinstance(verification.get("verdict"), Mapping) else None
    closeout = ledger.get("closeout") if isinstance(ledger.get("closeout"), Mapping) else None
    if ledger.get("status") == "done" and verdict is not None and closeout is not None and closeout.get("status") == "done":
        return ledger
    _raise_if_terminal(ledger, "capture verifier verdict for")
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


def _read_thread_messages_with_adapter(thread_adapter: Any,
                                       thread_id: str,
                                       *,
                                       turn_limit: int | None = None) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {"threadId": thread_id}
    if turn_limit is not None:
        kwargs["turnLimit"] = turn_limit
    result = _adapter_call(thread_adapter, "read_thread", **kwargs)
    return normalize_thread_read_messages(result)


def send_manager_plan_request_with_adapter(state_root: str | Path,
                                           project_id: str,
                                           task_id: str,
                                           *,
                                           thread_adapter: Any,
                                           permission: str,
                                           sent_at: str) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    _raise_if_terminal(ledger, "send manager plan request for")
    manager_thread_id = _role_thread_id(state_root, project_id, "manager")
    prompt = make_plan_request_message(task_id, ledger["objective"], permission)
    result = _adapter_call(
        thread_adapter,
        "send_message_to_thread",
        threadId=manager_thread_id,
        prompt=prompt,
    )
    anchor = thread_send_anchor(result, fallback_sent_at=sent_at)
    return record_plan_request_sent(
        state_root,
        project_id,
        task_id,
        manager_thread_id=manager_thread_id,
        sent_at=anchor["sentAt"],
        message_id=anchor["messageId"],
    )


def read_manager_plan_with_adapter(state_root: str | Path,
                                   project_id: str,
                                   task_id: str,
                                   *,
                                   thread_adapter: Any,
                                   captured_at: str,
                                   turn_limit: int | None = None) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    registry = load_registry(state_root, project_id)
    request = recovery_read_request(ledger, registry, "manager")
    messages = _read_thread_messages_with_adapter(
        thread_adapter,
        request["threadId"],
        turn_limit=turn_limit,
    )
    return capture_manager_plan_from_read(
        state_root,
        project_id,
        task_id,
        messages,
        captured_at=captured_at,
    )


def send_executor_dispatch_with_adapter(state_root: str | Path,
                                        project_id: str,
                                        task_id: str,
                                        *,
                                        thread_adapter: Any,
                                        permission: str,
                                        sent_at: str) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    _raise_if_terminal(ledger, "send executor dispatch for")
    plan = ledger.get("plan") if isinstance(ledger.get("plan"), Mapping) else None
    plan_fields = plan.get("fields") if isinstance(plan, Mapping) else None
    if not isinstance(plan_fields, Mapping):
        raise StateStoreError("missing manager plan fields for task: %s" % task_id)
    executor_thread_id = _role_thread_id(state_root, project_id, "executor")
    provisional_anchor = {"messageId": None, "sentAt": sent_at}
    prompt = make_executor_dispatch_message(
        task_id,
        plan_fields,
        permission,
        provisional_anchor,
    )
    result = _adapter_call(
        thread_adapter,
        "send_message_to_thread",
        threadId=executor_thread_id,
        prompt=prompt,
    )
    anchor = thread_send_anchor(result, fallback_sent_at=sent_at)
    return record_executor_dispatch_sent(
        state_root,
        project_id,
        task_id,
        executor_thread_id=executor_thread_id,
        sent_at=anchor["sentAt"],
        message_id=anchor["messageId"],
    )


def read_executor_callback_with_adapter(state_root: str | Path,
                                        project_id: str,
                                        task_id: str,
                                        *,
                                        thread_adapter: Any,
                                        captured_at: str,
                                        turn_limit: int | None = None) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    registry = load_registry(state_root, project_id)
    request = recovery_read_request(ledger, registry, "executor")
    messages = _read_thread_messages_with_adapter(
        thread_adapter,
        request["threadId"],
        turn_limit=turn_limit,
    )
    return capture_executor_callback_from_read(
        state_root,
        project_id,
        task_id,
        messages,
        captured_at=captured_at,
    )


def send_verifier_request_with_adapter(state_root: str | Path,
                                       project_id: str,
                                       task_id: str,
                                       *,
                                       thread_adapter: Any,
                                       permission: str,
                                       sent_at: str) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    _raise_if_terminal(ledger, "send verifier request for")
    callback_observation = ledger["observations"][-1] if ledger["observations"] else None
    if (
        not isinstance(callback_observation, Mapping)
        or callback_observation.get("role") != "executor"
        or callback_observation.get("type") != "callback_raw"
    ):
        raise StateStoreError("missing latest executor callback observation for task: %s" % task_id)
    callback_content = _required_str(callback_observation.get("content"), "executorCallback.content")
    plan = ledger.get("plan") if isinstance(ledger.get("plan"), Mapping) else None
    plan_fields = plan.get("fields") if isinstance(plan, Mapping) else {}
    scope = str(plan_fields.get("scope") or "unknown")
    verifier_thread_id = _role_thread_id(state_root, project_id, "verifier")
    prompt = make_verifier_request_message(
        task_id,
        callback_content,
        permission,
        scope,
    )
    result = _adapter_call(
        thread_adapter,
        "send_message_to_thread",
        threadId=verifier_thread_id,
        prompt=prompt,
    )
    anchor = thread_send_anchor(result, fallback_sent_at=sent_at)
    return record_verifier_request_sent(
        state_root,
        project_id,
        task_id,
        verifier_thread_id=verifier_thread_id,
        sent_at=anchor["sentAt"],
        message_id=anchor["messageId"],
    )


def read_verifier_verdict_with_adapter(state_root: str | Path,
                                       project_id: str,
                                       task_id: str,
                                       *,
                                       thread_adapter: Any,
                                       captured_at: str,
                                       turn_limit: int | None = None) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    registry = load_registry(state_root, project_id)
    request = recovery_read_request(ledger, registry, "verifier")
    messages = _read_thread_messages_with_adapter(
        thread_adapter,
        request["threadId"],
        turn_limit=turn_limit,
    )
    return capture_verifier_verdict_from_read(
        state_root,
        project_id,
        task_id,
        messages,
        captured_at=captured_at,
    )


def read_verifier_verdict_update_with_adapter(state_root: str | Path,
                                              project_id: str,
                                              task_id: str,
                                              *,
                                              thread_adapter: Any,
                                              captured_at: str,
                                              turn_limit: int | None = None) -> dict[str, Any]:
    ledger = read_verifier_verdict_with_adapter(
        state_root,
        project_id,
        task_id,
        thread_adapter=thread_adapter,
        captured_at=captured_at,
        turn_limit=turn_limit,
    )
    registry = load_registry(state_root, project_id)
    return {
        "ledger": ledger,
        "userOutput": format_task_update_for_user(ledger, registry),
    }


def _role_thread_lines(registry: Mapping[str, Any], project_id: str) -> list[str]:
    roles = _project_roles_from_registry(registry, project_id)
    lines = []
    for role in ("manager", "executor", "verifier"):
        record = roles.get(role) if isinstance(roles.get(role), Mapping) else {}
        thread_id = record.get("threadId") if isinstance(record, Mapping) else None
        lines.append("%s: %s" % (role, thread_id or "<missing>"))
    return lines


def _anchor_lines(ledger: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    plan_request = ledger.get("planRequest") if isinstance(ledger.get("planRequest"), Mapping) else None
    if plan_request is not None:
        lines.append("manager.planRequest: %s" % json.dumps(plan_request.get("searchAnchor"), ensure_ascii=False, sort_keys=True))
    dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
    if dispatches:
        latest = dispatches[-1]
        if isinstance(latest, Mapping):
            lines.append("executor.dispatch[%s]: %s" % (
                latest.get("attempt", len(dispatches)),
                json.dumps(latest.get("searchAnchor"), ensure_ascii=False, sort_keys=True),
            ))
    verification = ledger.get("verification") if isinstance(ledger.get("verification"), Mapping) else None
    request = verification.get("request") if isinstance(verification, Mapping) else None
    if isinstance(request, Mapping):
        lines.append("verification.request: %s" % json.dumps(request.get("searchAnchor"), ensure_ascii=False, sort_keys=True))
    return lines


def format_closeout_for_user(ledger: Mapping[str, Any], registry: Mapping[str, Any]) -> str:
    project_id = _required_str(ledger.get("projectId"), "ledger.projectId")
    closeout = ledger.get("closeout") if isinstance(ledger.get("closeout"), Mapping) else {}
    lines = [
        "Team Router Closeout",
        "taskId: %s" % ledger.get("taskId"),
        "status: %s" % ledger.get("status"),
        "threads:",
    ]
    lines.extend("  " + line for line in _role_thread_lines(registry, project_id))
    lines.extend((
        "summary: %s" % closeout.get("summary", ""),
        "evidenceChecked: %s" % closeout.get("evidenceChecked", ""),
        "risks: %s" % closeout.get("risks", ""),
        "nextAction: %s" % closeout.get("nextAction", ""),
    ))
    return "\n".join(lines)


def format_task_update_for_user(ledger: Mapping[str, Any], registry: Mapping[str, Any]) -> str:
    closeout = ledger.get("closeout") if isinstance(ledger.get("closeout"), Mapping) else None
    if ledger.get("status") in TERMINAL_STATUSES and closeout is not None:
        return format_closeout_for_user(ledger, registry)
    return format_handoff_for_user(ledger, registry)


def format_handoff_for_user(ledger: Mapping[str, Any], registry: Mapping[str, Any]) -> str:
    project_id = _required_str(ledger.get("projectId"), "ledger.projectId")
    lines = [
        "Team Router Handoff",
        "taskId: %s" % ledger.get("taskId"),
        "projectId: %s" % project_id,
        "status: %s" % ledger.get("status"),
        "stateRoot: %s" % ledger.get("stateRoot"),
        "threads:",
    ]
    lines.extend("  " + line for line in _role_thread_lines(registry, project_id))
    lines.append("read_thread anchors:")
    anchor_lines = _anchor_lines(ledger)
    lines.extend("  " + line for line in (anchor_lines or ["<none>"]))
    closeout = ledger.get("closeout") if isinstance(ledger.get("closeout"), Mapping) else {}
    lines.extend((
        "summary: %s" % closeout.get("summary", ""),
        "risks: %s" % closeout.get("risks", ""),
        "nextAction: %s" % closeout.get("nextAction", ""),
    ))
    return "\n".join(lines)


def _parse_thread_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        try:
            return datetime.fromtimestamp(float(raw), timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
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
