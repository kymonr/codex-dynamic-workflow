# -*- coding: utf-8 -*-
"""Helpers for the codex-team-router MVP.

This module is intentionally local and deterministic. It does not call Codex
thread tools; callers pass thread/tool observations in as plain data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    ledger.setdefault("verification", None)
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