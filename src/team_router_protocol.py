# -*- coding: utf-8 -*-
"""Protocol parsing helpers for TEAM_ROUTER_* marker blocks."""
from __future__ import annotations

from dataclasses import dataclass
import re


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

CONDITIONAL_REQUIRED_BY_MARKER = {
    "TEAM_ROUTER_VERDICT": {
        "result": "required unless status: accepted is present; status: accepted implies result: pass",
    },
}

_ALLOWED_BY_MARKER = {
    "TEAM_ROUTER_PLAN": {
        "status": {"planned", "blocked"},
        "acknowledgedPermission": {"read-only", "design-only", "local-package", "escalation-required"},
    },
    "TEAM_ROUTER_CALLBACK": {
        "status": {"done", "blocked"},
        "final": {"true"},
    },
    "TEAM_ROUTER_VERDICT": {
        "result": {"pass", "needs_rework", "blocked"},
        "status": {"accepted"},
    },
    "TEAM_ROUTER_REVIEW": {
        "result": {"pass", "needs_rework", "blocked"},
    },
    "TEAM_ROUTER_ARCHITECT_REVIEW": {
        "result": {"pass", "needs_rework", "blocked"},
        "role": {"Architect"},
        "skillProfileUsed": {"architect-default"},
    },
    "TEAM_ROUTER_QA_REVIEW": {
        "result": {"pass", "needs_rework", "blocked"},
        "role": {"QA"},
        "skillProfileUsed": {"qa-default"},
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
        "summary",
        "requiredChanges",
        "evidenceChecked",
        "risks",
    ),
    "TEAM_ROUTER_REVIEW": (
        "result",
        "summary",
        "findings",
        "requiredChanges",
        "evidenceChecked",
        "risks",
    ),
    "TEAM_ROUTER_ARCHITECT_REVIEW": (
        "result",
        "sourceThreadId",
        "sourceRoleThreadId",
        "role",
        "summary",
        "findings",
        "requiredChanges",
        "evidenceChecked",
        "risks",
        "skillProfileUsed",
        "architectureImpact",
        "compatibilityNotes",
        "alternatives",
        "migrationRisks",
    ),
    "TEAM_ROUTER_QA_REVIEW": (
        "result",
        "sourceThreadId",
        "sourceRoleThreadId",
        "role",
        "summary",
        "findings",
        "requiredChanges",
        "evidenceChecked",
        "risks",
        "skillProfileUsed",
        "coverageGaps",
        "verificationPlan",
        "regressionRisks",
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
    _validate_task_id(task_id)
    candidates = [
        m for m in _iter_marker_blocks(text)
        if m.marker == "TEAM_ROUTER_VERDICT" and m.task_id == task_id
    ]
    if not candidates:
        raise ProtocolError("missing TEAM_ROUTER_VERDICT taskId=%s" % task_id)
    msg = candidates[-1]
    required = _REQUIRED_BY_MARKER["TEAM_ROUTER_VERDICT"]
    missing = [field for field in required if field not in msg.fields]
    if missing:
        raise ProtocolError("TEAM_ROUTER_VERDICT missing fields: %s" % ", ".join(missing))
    blank = [field for field in required if not msg.fields[field]]
    if blank:
        raise ProtocolError("TEAM_ROUTER_VERDICT blank fields: %s" % ", ".join(blank))
    status = msg.fields.get("status")
    if status not in (None, "accepted"):
        raise ProtocolError(
            "TEAM_ROUTER_VERDICT.status must be one of %s, got %r"
            % (["accepted"], status)
        )
    result = msg.fields.get("result")
    if result not in (None, "pass", "needs_rework", "blocked"):
        raise ProtocolError(
            "TEAM_ROUTER_VERDICT.result must be one of %s, got %r"
            % (["blocked", "needs_rework", "pass"], result)
        )
    if "result" not in msg.fields:
        if status == "accepted":
            msg.fields["result"] = "pass"
        else:
            raise ProtocolError("TEAM_ROUTER_VERDICT missing fields: result")
    elif status == "accepted" and msg.fields["result"] != "pass":
        raise ProtocolError("TEAM_ROUTER_VERDICT.status accepted requires result pass")
    return msg


def parse_review(text: str, task_id: str) -> ProtocolMessage:
    return parse_message(text, "TEAM_ROUTER_REVIEW", task_id)
