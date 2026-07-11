# -*- coding: utf-8 -*-
"""Status, handoff, and closeout text helpers for Team Router.

This module is deterministic and does not call Codex thread tools. The facade may
pass a watcher builder callback when handoff text needs current watcher metadata.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from team_router_state import (
    TERMINAL_STATUSES,
    _project_roles_from_registry,
    _required_str,
    task_workflow_version,
)


WatcherBuilder = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]

DEFAULT_CLOSEOUT_COMPOUNDING_REASON = "ordinary successful implementation/testing with no new reusable risk"


def role_thread_lines(registry: Mapping[str, Any], project_id: str, *,
                      parent_thread_id: str | None = None) -> list[str]:
    if parent_thread_id is not None:
        projects = registry.get("projects") if isinstance(registry.get("projects"), Mapping) else {}
        project = projects.get(project_id) if isinstance(projects.get(project_id), Mapping) else {}
        pools = project.get("managerPools") if isinstance(project.get("managerPools"), Mapping) else {}
        pool = pools.get(parent_thread_id) if isinstance(pools.get(parent_thread_id), Mapping) else {}
        pool_roles = pool.get("roles") if isinstance(pool.get("roles"), Mapping) else {}
        lines = []
        for role in ("executor", "reviewer", "verifier", "architect", "qa"):
            records = pool_roles.get(role) if isinstance(pool_roles.get(role), list) else []
            thread_ids = [str(record.get("threadId")) for record in records
                          if isinstance(record, Mapping) and record.get("threadId")]
            if thread_ids:
                lines.append("%s: %s" % (role, ", ".join(thread_ids)))
        return lines or ["<none>"]
    roles = _project_roles_from_registry(registry, project_id)
    lines = []
    for role in ("manager", "executor", "reviewer", "verifier"):
        record = roles.get(role) if isinstance(roles.get(role), Mapping) else {}
        if role == "reviewer" and not record:
            continue
        thread_id = record.get("threadId") if isinstance(record, Mapping) else None
        lines.append("%s: %s" % (role, thread_id or "<missing>"))
    return lines


def anchor_lines(ledger: Mapping[str, Any]) -> list[str]:
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
    review = ledger.get("review") if isinstance(ledger.get("review"), Mapping) else None
    review_request = review.get("request") if isinstance(review, Mapping) else None
    if isinstance(review_request, Mapping):
        lines.append("review.request: %s" % json.dumps(review_request.get("searchAnchor"), ensure_ascii=False, sort_keys=True))
    verification = ledger.get("verification") if isinstance(ledger.get("verification"), Mapping) else None
    request = verification.get("request") if isinstance(verification, Mapping) else None
    if isinstance(request, Mapping):
        lines.append("verification.request: %s" % json.dumps(request.get("searchAnchor"), ensure_ascii=False, sort_keys=True))
    return lines


def closeout_compounding_fields(closeout: Mapping[str, Any]) -> tuple[str, str]:
    decision = str(closeout.get("compoundingDecision", "")).strip().lower()
    if decision not in {"recorded", "skipped"}:
        decision = "skipped"
    reason = str(closeout.get("reason", "")).strip()
    if not reason:
        reason = DEFAULT_CLOSEOUT_COMPOUNDING_REASON
    return decision, reason


def manager_polling_status_lines(ledger: Mapping[str, Any]) -> list[str]:
    polling = ledger.get("managerPollingStatus")
    if not isinstance(polling, Mapping):
        return []
    lines = [
        "managerPolling:",
        "  status: %s" % polling.get("status", ""),
        "  shouldRead: %s" % polling.get("shouldRead", ""),
        "  shouldReport: %s" % polling.get("shouldReport", ""),
    ]
    if polling.get("nextAllowedReadAt"):
        lines.append("  nextAllowedReadAt: %s" % polling.get("nextAllowedReadAt", ""))
    if polling.get("summary"):
        lines.append("  summary: %s" % polling.get("summary", ""))
    return lines


def format_closeout_for_user(ledger: Mapping[str, Any], registry: Mapping[str, Any]) -> str:
    project_id = _required_str(ledger.get("projectId"), "ledger.projectId")
    closeout = ledger.get("closeout") if isinstance(ledger.get("closeout"), Mapping) else {}
    is_v2 = task_workflow_version(ledger) == 2
    compounding_decision, compounding_reason = closeout_compounding_fields(closeout)
    lines = [
        "Team Router Closeout",
        "taskId: %s" % ledger.get("taskId"),
        "status: %s" % ledger.get("status"),
        "threads:",
    ]
    lines.extend("  " + line for line in role_thread_lines(
        registry,
        project_id,
        parent_thread_id=ledger.get("parentThreadId") if is_v2 else None,
    ))
    if is_v2:
        lines.extend((
            "acceptedBy: %s" % closeout.get("acceptedBy", ""),
            "changed: %s" % closeout.get("changed", ""),
            "verified: %s" % closeout.get("verified", ""),
            "notDone: %s" % closeout.get("notDone", ""),
            "nextGate: %s" % closeout.get("nextGate", ""),
            "routingReceipt: %s" % json.dumps(closeout.get("routingReceipt", {}), ensure_ascii=False, sort_keys=True),
        ))
    lines.extend((
        "summary: %s" % closeout.get("summary", ""),
        "evidenceChecked: %s" % closeout.get("evidenceChecked", ""),
        "risks: %s" % closeout.get("risks", ""),
        "nextAction: %s" % closeout.get("nextAction", ""),
        "remainingTodos: %s" % closeout.get("remainingTodos", closeout.get("nextAction", "")),
    ))
    lines.extend(manager_polling_status_lines(ledger))
    if closeout.get("receiptSource") or closeout.get("receiptChannel"):
        lines.extend((
            "receiptSource: %s" % closeout.get("receiptSource", ""),
            "receiptChannel: %s" % closeout.get("receiptChannel", ""),
        ))
        if closeout.get("receiptRoleThreadId"):
            lines.append("receiptRoleThreadId: %s" % closeout.get("receiptRoleThreadId", ""))
        if closeout.get("returnThreadId"):
            lines.append("returnThreadId: %s" % closeout.get("returnThreadId", ""))
    if closeout.get("deliveryStatus"):
        lines.append("deliveryStatus: %s" % closeout.get("deliveryStatus", ""))
    if closeout.get("deliveryDegraded"):
        lines.append("delivery: degraded")
    lines.extend((
        "compoundingDecision: %s" % compounding_decision,
        "reason: %s" % compounding_reason,
    ))
    if closeout.get("watcherAction"):
        lines.extend((
            "heartbeatAction: %s" % closeout.get("watcherAction", ""),
            "plainLanguageReport: %s" % closeout.get("plainLanguageReport", ""),
        ))
        if not is_v2:
            lines.append("notDone: %s" % closeout.get("notDone", ""))
    return "\n".join(lines)


def _handoff_watcher(ledger: Mapping[str, Any], watcher_builder: WatcherBuilder | None) -> Mapping[str, Any] | None:
    watcher = ledger.get("watcher") if isinstance(ledger.get("watcher"), Mapping) else None
    if watcher is not None:
        return watcher
    if watcher_builder is None:
        return None
    built = watcher_builder(ledger)
    return built if isinstance(built, Mapping) else None


def format_handoff_for_user(ledger: Mapping[str, Any], registry: Mapping[str, Any], *,
                            watcher_builder: WatcherBuilder | None = None) -> str:
    project_id = _required_str(ledger.get("projectId"), "ledger.projectId")
    lines = [
        "Team Router Handoff",
        "taskId: %s" % ledger.get("taskId"),
        "projectId: %s" % project_id,
        "status: %s" % ledger.get("status"),
        "stateRoot: %s" % ledger.get("stateRoot"),
        "threads:",
    ]
    lines.extend("  " + line for line in role_thread_lines(
        registry,
        project_id,
        parent_thread_id=ledger.get("parentThreadId") if task_workflow_version(ledger) == 2 else None,
    ))
    lines.append("read_thread anchors:")
    anchors = anchor_lines(ledger)
    lines.extend("  " + line for line in (anchors or ["<none>"]))
    watcher = _handoff_watcher(ledger, watcher_builder)
    if watcher is not None:
        lines.extend((
            "manager watcher:",
            "  role: %s" % watcher.get("role"),
            "  threadId: %s" % watcher.get("threadId"),
            "  expectedMarker: %s" % watcher.get("expectedMarker"),
            "  lastReadAt: %s" % watcher.get("lastReadAt"),
            "  firstCheckAt: %s" % watcher.get("firstCheckAt"),
            "  nextAllowedReadAt: %s" % watcher.get("nextAllowedReadAt"),
            "  waitingReason: %s" % watcher.get("waitingReason"),
            "  nextManagerAction: %s" % watcher.get("nextManagerAction"),
            "  actionOnWake: %s" % watcher.get("actionOnWake"),
        ))
    closeout = ledger.get("closeout") if isinstance(ledger.get("closeout"), Mapping) else {}
    lines.extend((
        "summary: %s" % closeout.get("summary", ""),
        "risks: %s" % closeout.get("risks", ""),
        "nextAction: %s" % closeout.get("nextAction", ""),
        "remainingTodos: %s" % closeout.get("remainingTodos", closeout.get("nextAction", "")),
    ))
    lines.extend(manager_polling_status_lines(ledger))
    return "\n".join(lines)


def format_task_update_for_user(ledger: Mapping[str, Any], registry: Mapping[str, Any], *,
                                watcher_builder: WatcherBuilder | None = None) -> str:
    closeout = ledger.get("closeout") if isinstance(ledger.get("closeout"), Mapping) else None
    if ledger.get("status") in TERMINAL_STATUSES and closeout is not None:
        return format_closeout_for_user(ledger, registry)
    return format_handoff_for_user(ledger, registry, watcher_builder=watcher_builder)
