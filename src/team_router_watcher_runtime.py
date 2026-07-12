# -*- coding: utf-8 -*-
"""Watcher timing and heartbeat helpers for Team Router.

This module keeps watcher cadence and heartbeat payload construction separate
from the facade orchestration that reads/writes ledgers and talks to role
threads.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from team_router_policy import classify_team_router_gate
from team_router_protocol import ProtocolError
from team_router_state import TERMINAL_STATUSES, _required_str


MIN_ROLE_POLL_INTERVAL_SECONDS = 300
FIRST_ROLE_CHECK_DELAY_SECONDS = 30
GATE_READ_INTERVAL_SECONDS = {
    "FAST": MIN_ROLE_POLL_INTERVAL_SECONDS,
    "NORMAL": MIN_ROLE_POLL_INTERVAL_SECONDS,
    "STRICT": MIN_ROLE_POLL_INTERVAL_SECONDS,
    "PACKAGE": MIN_ROLE_POLL_INTERVAL_SECONDS,
}
ACTIVE_ROLE_CONVERGENCE_STATUSES = {"active", "inprogress", "in_progress", "running", "working"}
EXPLICIT_ROLE_READ_BYPASS_TERMS = (
    "user-triggered",
    "user requested",
    "user_requested",
    "status now",
    "immediate",
    "user_stop",
    "stop_requested",
    "user requested stop",
    "user-requested-stop",
)


def role_read_interval_seconds(gate_class: str) -> int:
    gate = _required_str(gate_class, "gateClass").upper()
    if gate not in GATE_READ_INTERVAL_SECONDS:
        raise ProtocolError("invalid gateClass: %r" % (gate_class,))
    return GATE_READ_INTERVAL_SECONDS[gate]


def _parse_iso_timestamp(value: str, field_name: str) -> datetime:
    raw = _required_str(value, field_name)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ProtocolError("invalid %s: %r" % (field_name, value)) from exc


def _isoformat_plus_seconds(value: str, seconds: int) -> str:
    return (_parse_iso_timestamp(value, "observed_at") + timedelta(seconds=seconds)).isoformat()


def _iso_timestamp_before(left: str, right: str) -> bool:
    return _parse_iso_timestamp(left, "observed_at") < _parse_iso_timestamp(right, "nextAllowedReadAt")


def _latest_iso_timestamp(values: list[str]) -> str | None:
    latest_value: str | None = None
    latest_dt: datetime | None = None
    for value in values:
        dt = _parse_iso_timestamp(value, "readDiscipline timestamp")
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt
            latest_value = value
    return latest_value


def next_role_read_policy(ledger: Mapping[str, Any], *, observed_at: str) -> dict[str, Any]:
    gate = classify_team_router_gate(ledger)
    seconds = role_read_interval_seconds(gate)
    return {
        "gateClass": gate,
        "lastReadAt": None,
        "nextAllowedReadAt": _isoformat_plus_seconds(observed_at, seconds),
        "readReason": "awaiting direct return fallback",
        "directReturnExpected": True,
        "minimumIntervalSeconds": MIN_ROLE_POLL_INTERVAL_SECONDS,
        "completionFeedbackRequired": True,
        "convergenceMode": "observe-only until idle/blocked/user-triggered or timeout-confirmed-no-progress",
    }


def role_read_allowed(ledger: Mapping[str, Any], *, observed_at: str, reason: str) -> dict[str, Any]:
    reason_text = _required_str(reason, "reason")
    lowered = reason_text.lower()
    user_requested = any(term in lowered for term in EXPLICIT_ROLE_READ_BYPASS_TERMS)
    if user_requested or "timeout" in lowered or "blocker" in lowered:
        return {"allowed": True, "action": "read_allowed", "reason": reason_text}
    discipline = ledger.get("readDiscipline") if isinstance(ledger.get("readDiscipline"), Mapping) else {}
    candidates: list[str] = []
    next_allowed = discipline.get("nextAllowedReadAt")
    if isinstance(next_allowed, str):
        candidates.append(next_allowed)
    last_read_at = discipline.get("lastReadAt")
    min_seconds = discipline.get("minimumIntervalSeconds", MIN_ROLE_POLL_INTERVAL_SECONDS)
    try:
        min_seconds_int = int(min_seconds)
    except (TypeError, ValueError):
        min_seconds_int = MIN_ROLE_POLL_INTERVAL_SECONDS
    min_seconds_int = max(MIN_ROLE_POLL_INTERVAL_SECONDS, min_seconds_int)
    if isinstance(last_read_at, str):
        candidates.append(_isoformat_plus_seconds(last_read_at, min_seconds_int))
    effective_next_allowed = _latest_iso_timestamp(candidates) if candidates else None
    if isinstance(effective_next_allowed, str) and _iso_timestamp_before(observed_at, effective_next_allowed):
        return {
            "allowed": False,
            "action": "read_suppressed",
            "reason": "await direct return until nextAllowedReadAt",
            "nextAllowedReadAt": effective_next_allowed,
            "minimumIntervalSeconds": min_seconds_int,
        }
    return {"allowed": True, "action": "read_allowed", "reason": reason_text}


def _normalized_role_activity_status(status: Any) -> str:
    normalized = str(status or "").strip().replace("-", "_").replace(" ", "_")
    normalized = normalized.replace("inProgress", "in_progress")
    return normalized.lower()


def convergence_prompt_allowed(ledger: Mapping[str, Any], *, observed_at: str, reason: str,
                               observed_status: str | None = None) -> dict[str, Any]:
    reason_text = _required_str(reason, "reason")
    lowered = reason_text.lower()
    if "user-triggered" in lowered or "user requested" in lowered:
        return {"allowed": True, "action": "convergence_allowed", "reason": reason_text}
    status_text = _normalized_role_activity_status(
        observed_status if observed_status is not None else ledger.get("roleThreadStatus"),
    )
    if status_text in ACTIVE_ROLE_CONVERGENCE_STATUSES:
        return {
            "allowed": False,
            "action": "observe_only_wait",
            "reason": "active role thread status requires observation-only waiting",
            "observedStatus": status_text,
        }
    if "blocked" in status_text or "ask_context" in status_text or "needs_context" in status_text:
        return {"allowed": True, "action": "convergence_allowed", "reason": reason_text}
    if "timeout" in lowered:
        discipline = ledger.get("readDiscipline") if isinstance(ledger.get("readDiscipline"), Mapping) else {}
        observed_no_progress_at = discipline.get("lastObservedNoProgressAt")
        if isinstance(observed_no_progress_at, str):
            return {
                "allowed": True,
                "action": "convergence_allowed",
                "reason": reason_text,
                "observedNoProgressAt": observed_no_progress_at,
            }
        return {
            "allowed": False,
            "action": "observe_only_read_first",
            "reason": "timeout convergence requires an observation-only read confirming no recent progress",
        }
    return {"allowed": True, "action": "convergence_allowed", "reason": reason_text}


def _waiting_read_discipline(ledger: Mapping[str, Any], *, observed_at: str) -> dict[str, Any]:
    discipline = ledger.get("readDiscipline") if isinstance(ledger.get("readDiscipline"), Mapping) else None
    if discipline is None:
        discipline = next_role_read_policy(ledger, observed_at=observed_at)
    else:
        discipline = dict(discipline)
    minimum_seconds = discipline.get("minimumIntervalSeconds", MIN_ROLE_POLL_INTERVAL_SECONDS)
    try:
        minimum_seconds_int = int(minimum_seconds)
    except (TypeError, ValueError):
        minimum_seconds_int = MIN_ROLE_POLL_INTERVAL_SECONDS
    minimum_seconds_int = max(MIN_ROLE_POLL_INTERVAL_SECONDS, minimum_seconds_int)
    discipline["lastReadAt"] = observed_at
    discipline["minimumIntervalSeconds"] = minimum_seconds_int
    discipline["nextAllowedReadAt"] = _isoformat_plus_seconds(observed_at, minimum_seconds_int)
    return discipline


def build_watcher_ledger(wakeup: Mapping[str, Any] | None,
                         ledger: Mapping[str, Any],
                         *,
                         observed_at: str | None = None) -> dict[str, Any] | None:
    if wakeup is None:
        return None
    discipline = ledger.get("readDiscipline") if isinstance(ledger.get("readDiscipline"), Mapping) else {}
    anchor = wakeup.get("searchAnchor") if isinstance(wakeup.get("searchAnchor"), Mapping) else {}
    last_read_at = observed_at
    if last_read_at is None and isinstance(discipline.get("lastReadAt"), str):
        last_read_at = discipline["lastReadAt"]
    anchor_sent_at = anchor.get("sentAt") if isinstance(anchor.get("sentAt"), str) else None
    if last_read_at is None and isinstance(anchor_sent_at, str):
        last_read_at = anchor_sent_at
    next_allowed = discipline.get("nextAllowedReadAt") if isinstance(discipline.get("nextAllowedReadAt"), str) else None
    first_check_at = _isoformat_plus_seconds(anchor_sent_at, FIRST_ROLE_CHECK_DELAY_SECONDS) if isinstance(anchor_sent_at, str) else None
    if isinstance(last_read_at, str):
        minimum_next = _isoformat_plus_seconds(last_read_at, MIN_ROLE_POLL_INTERVAL_SECONDS)
        if next_allowed is None or _iso_timestamp_before(next_allowed, minimum_next):
            next_allowed = minimum_next
    status = _normalized_role_activity_status(ledger.get("roleThreadStatus"))
    if not status:
        status = str(ledger.get("status") or "")
    return {
        "role": wakeup.get("role"),
        "threadId": wakeup.get("threadId"),
        "expectedMarker": wakeup.get("expectedMarker"),
        "searchAnchor": wakeup.get("searchAnchor"),
        "lastReadAt": last_read_at,
        "firstCheckAt": first_check_at,
        "firstCheckAction": "read_thread",
        "firstCheckReason": "initial short follow-up after dispatch",
        "nextAllowedReadAt": next_allowed,
        "minimumIntervalSeconds": MIN_ROLE_POLL_INTERVAL_SECONDS,
        "status": status,
        "waitingReason": wakeup.get("reason"),
        "nextManagerAction": "watch_team_task_with_adapter",
        "actionOnWake": "read_thread",
        "heartbeatFallback": "Codex role threads do not push completion events reliably; manager/app heartbeat must read once at firstCheckAt, then at nextAllowedReadAt unless current user asks status/stop/immediate.",
    }


def manager_polling_status_update(ledger: Mapping[str, Any],
                                  wakeup: Mapping[str, Any] | None,
                                  *,
                                  observed_at: str,
                                  observed_status: str | None = None,
                                  read_reason: str = "scheduled watcher heartbeat") -> dict[str, Any]:
    read_decision = watcher_read_allowed(
        ledger,
        wakeup,
        observed_at=observed_at,
        read_reason=read_reason,
    )
    status = _normalized_role_activity_status(
        observed_status if observed_status is not None else ledger.get("roleThreadStatus"),
    )
    if not status:
        status = _normalized_role_activity_status(ledger.get("status"))
    discipline = ledger.get("readDiscipline") if isinstance(ledger.get("readDiscipline"), Mapping) else {}
    previous_reported = _normalized_role_activity_status(discipline.get("lastReportedRoleStatus"))
    base: dict[str, Any] = {
        "shouldRead": bool(read_decision.get("allowed")),
        "shouldReport": False,
        "observedStatus": status,
        "previousReportedStatus": previous_reported or None,
        "readDecision": read_decision,
    }
    next_allowed = read_decision.get("nextAllowedReadAt")
    if isinstance(next_allowed, str):
        base["nextAllowedReadAt"] = next_allowed
    if not read_decision.get("allowed"):
        base.update({
            "action": "read_suppressed",
            "reportReason": "wait until nextAllowedReadAt without repeated status narration",
        })
        return base
    if status in ACTIVE_ROLE_CONVERGENCE_STATUSES and previous_reported == status:
        base.update({
            "action": "unchanged_active_status_suppressed",
            "reportReason": "unchanged active role status; report only status changes, timeout/blocker, or completion",
        })
        return base
    if status and previous_reported != status:
        base.update({
            "shouldReport": True,
            "action": "status_change_report",
            "reportReason": "role status changed since last manager report",
        })
        return base
    base.update({
        "action": "no_status_report",
        "reportReason": "no status change to report",
    })
    return base

def watcher_read_allowed(ledger: Mapping[str, Any],
                         wakeup: Mapping[str, Any] | None,
                         *,
                         observed_at: str,
                         read_reason: str) -> dict[str, Any]:
    reason = _required_str(read_reason, "readReason")
    lowered = reason.lower()
    if any(term in lowered for term in EXPLICIT_ROLE_READ_BYPASS_TERMS) or "timeout" in lowered or "blocker" in lowered:
        return {"allowed": True, "action": "read_allowed", "reason": reason}
    watcher = build_watcher_ledger(wakeup, ledger)
    if watcher is None:
        return {"allowed": True, "action": "read_allowed", "reason": reason}
    first_check_at = watcher.get("firstCheckAt") if isinstance(watcher.get("firstCheckAt"), str) else None
    anchor = watcher.get("searchAnchor") if isinstance(watcher.get("searchAnchor"), Mapping) else {}
    anchor_sent_at = anchor.get("sentAt") if isinstance(anchor.get("sentAt"), str) else None
    discipline = ledger.get("readDiscipline") if isinstance(ledger.get("readDiscipline"), Mapping) else {}
    last_read_at = discipline.get("lastReadAt") if isinstance(discipline.get("lastReadAt"), str) else None
    first_check_unused = (
        last_read_at is None
        or (anchor_sent_at is not None and last_read_at == anchor_sent_at)
        or (anchor_sent_at is not None and _iso_timestamp_before(last_read_at, anchor_sent_at))
    )
    if (
        first_check_at is not None
        and not _iso_timestamp_before(observed_at, first_check_at)
        and first_check_unused
    ):
        return {
            "allowed": True,
            "action": "first_check_read_allowed",
            "reason": "firstCheckAt reached for one short observation-only read",
            "firstCheckAt": first_check_at,
        }
    return role_read_allowed(ledger, observed_at=observed_at, reason=reason)


def _watch_arg(payload_args: Mapping[str, Any], snake_name: str, camel_name: str) -> Any:
    if snake_name in payload_args:
        return payload_args[snake_name]
    return payload_args.get(camel_name)


def materialize_watcher_call_kwargs(payload: Mapping[str, Any],
                                    *,
                                    thread_adapter: Any,
                                    observed_at: str | None = None,
                                    heartbeat_scheduler: Any = None,
                                    turn_limit: int | None = None) -> dict[str, Any]:
    callbacks = [payload.get(name) for name in ("callback", "managerAction") if payload.get(name) is not None]
    if not callbacks:
        raise ProtocolError("scheduler payload callback must be watch_team_task_with_adapter")
    for callback in callbacks:
        if callback != "watch_team_task_with_adapter":
            raise ProtocolError("scheduler payload callback not allowed: %s; expected watch_team_task_with_adapter" % callback)
    raw_args = payload.get("kwargs") if isinstance(payload.get("kwargs"), Mapping) else payload.get("watchArgs")
    if not isinstance(raw_args, Mapping):
        raise ProtocolError("scheduler payload requires kwargs or watchArgs")
    observed = observed_at or payload.get("runAt")
    if not isinstance(observed, str) or not observed:
        raise ProtocolError("scheduler payload requires runAt or explicit observed_at")
    out = {
        "state_root": _required_str(_watch_arg(raw_args, "state_root", "stateRoot"), "state_root"),
        "project_id": _required_str(_watch_arg(raw_args, "project_id", "projectId"), "project_id"),
        "task_id": _required_str(_watch_arg(raw_args, "task_id", "taskId"), "task_id"),
        "permission": _required_str(raw_args.get("permission"), "permission"),
        "thread_adapter": thread_adapter,
        "observed_at": observed,
        "read_reason": _required_str(_watch_arg(raw_args, "read_reason", "readReason"), "read_reason"),
    }
    return_thread_id = _watch_arg(raw_args, "return_thread_id", "returnThreadId")
    if isinstance(return_thread_id, str) and return_thread_id:
        out["return_thread_id"] = return_thread_id
    if heartbeat_scheduler is not None:
        out["heartbeat_scheduler"] = heartbeat_scheduler
    if turn_limit is not None:
        out["turn_limit"] = turn_limit
    return out

def build_watcher_heartbeat_payload(update: dict[str, Any],
                                    *,
                                    state_root: str | Path,
                                    project_id: str,
                                    task_id: str,
                                    permission: str,
                                    watcher: Mapping[str, Any] | None = None,
                                    return_thread_id: str | None = None,
                                    read_reason: str = "scheduled watcher heartbeat") -> dict[str, Any] | None:

    update_watcher = update.get("watcher") if isinstance(update.get("watcher"), Mapping) else None
    next_wakeup = update.get("nextWakeup") if isinstance(update.get("nextWakeup"), Mapping) else None
    if watcher is None:
        watcher = update_watcher
    if watcher is None and next_wakeup is None:
        return None
    if update.get("status") in TERMINAL_STATUSES | {"needs_rework", "manager_acceptance_pending"}:
        return None
    if update.get("action") in {"watch_no_action"}:
        return None
    if watcher is None:
        return None
    first_check_at = watcher.get("firstCheckAt") if isinstance(watcher.get("firstCheckAt"), str) else None
    next_allowed_at = watcher.get("nextAllowedReadAt") if isinstance(watcher.get("nextAllowedReadAt"), str) else None
    last_read_at = watcher.get("lastReadAt") if isinstance(watcher.get("lastReadAt"), str) else None
    run_at = next_allowed_at
    if first_check_at is not None and (
        last_read_at is None or _iso_timestamp_before(last_read_at, first_check_at)
    ):
        run_at = first_check_at
    if run_at is None:
        run_at = first_check_at
    if run_at is None:
        return None
    role = watcher.get("role")
    thread_id = watcher.get("threadId")
    expected_marker = watcher.get("expectedMarker")
    watch_args = {
        "state_root": str(Path(state_root)),
        "stateRoot": str(Path(state_root)),
        "project_id": project_id,
        "projectId": project_id,
        "task_id": task_id,
        "taskId": task_id,
        "permission": permission,
        "read_reason": read_reason,
        "readReason": read_reason,
    }
    if return_thread_id is not None:
        watch_args["return_thread_id"] = return_thread_id
        watch_args["returnThreadId"] = return_thread_id
    return {
        "taskId": task_id,
        "projectId": project_id,
        "runAt": run_at,
        "callback": "watch_team_task_with_adapter",
        "managerAction": "watch_team_task_with_adapter",
        "threadId": thread_id,
        "role": role,
        "expectedMarker": expected_marker,
        "readReason": read_reason,
        "watchArgs": watch_args,
        "kwargs": dict(watch_args),
    }
