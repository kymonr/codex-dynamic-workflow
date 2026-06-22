# -*- coding: utf-8 -*-
"""Helpers for the codex-team-router MVP.

This module is intentionally local and deterministic. It does not call Codex
thread tools; callers pass thread/tool observations in as plain data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Mapping


class ProtocolError(ValueError):
    """Raised when a TEAM_ROUTER_* marker block is missing or invalid."""


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
        return Path(explicit_state_root).resolve()
    root = Path(canonical_root if canonical_root is not None else current_root)
    return root.resolve() / ".codex-team-router"


def registry_path(state_root: str | Path, project_id: str) -> Path:
    _validate_task_id(project_id)
    return Path(state_root).resolve() / "projects" / project_id / "registry.json"


def task_path(state_root: str | Path, project_id: str, task_id: str) -> Path:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    return Path(state_root).resolve() / "projects" / project_id / "tasks" / (task_id + ".json")


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