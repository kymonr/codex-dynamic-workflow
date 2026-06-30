# -*- coding: utf-8 -*-
"""Host readiness and live orchestration context helpers for Team Router."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from team_router_runtime import _adapter_method
from team_router_state import StateStoreError


THREAD_TOOL_NAMES = (
    "list_projects",
    "create_thread",
    "list_threads",
    "read_thread",
    "send_message_to_thread",
    "set_thread_title",
)


def probe_thread_adapter_capabilities(
    thread_adapter: Any,
    required_tools: Iterable[str] = THREAD_TOOL_NAMES,
) -> dict[str, bool]:
    capabilities = {
        tool_name: callable(_adapter_method(thread_adapter, tool_name))
        for tool_name in THREAD_TOOL_NAMES
    }
    missing = [
        tool_name for tool_name in required_tools
        if not callable(_adapter_method(thread_adapter, tool_name))
    ]
    if missing:
        non_callable = [
            tool_name for tool_name in missing
            if _adapter_method(thread_adapter, tool_name) is not None
        ]
        boundary = "thread adapter boundary requires in-process Python callables"
        if non_callable:
            boundary += (
                "; non-callable adapter entries are not usable as Python callables; "
                "model-side Codex app tool descriptors need a host adapter wrapper before use; "
                "non-callable adapter entries: %s" % ", ".join(sorted(non_callable))
            )
        raise StateStoreError(
            "thread adapter missing callable(s): %s; %s" % (
                ", ".join(sorted(missing)),
                boundary,
            )
        )
    return capabilities


def _is_callable_heartbeat_scheduler(heartbeat_scheduler: Any) -> bool:
    if callable(heartbeat_scheduler):
        return True
    return callable(getattr(heartbeat_scheduler, "schedule", None))


def _heartbeat_scheduler_call(heartbeat_scheduler: Any) -> Any:
    if callable(heartbeat_scheduler):
        return heartbeat_scheduler
    schedule = getattr(heartbeat_scheduler, "schedule", None)
    if callable(schedule):
        return schedule
    raise StateStoreError("heartbeat scheduler must be callable or expose callable .schedule(**kwargs)")


def assess_live_orchestration_readiness(
    thread_adapter: Any | None,
    *,
    parent_thread_id: str | None,
    heartbeat_scheduler: Any,
    required_tools: Iterable[str] = THREAD_TOOL_NAMES,
) -> dict[str, Any]:
    missing: list[str] = []
    capabilities: dict[str, bool] = {}
    if thread_adapter is None:
        missing.append("callable adapter")
    else:
        for tool_name in required_tools:
            is_callable = callable(_adapter_method(thread_adapter, tool_name))
            capabilities[tool_name] = is_callable
            if not is_callable:
                missing.append("callable %s" % tool_name)
    capabilities["heartbeat_scheduler"] = _is_callable_heartbeat_scheduler(heartbeat_scheduler)
    if not str(parent_thread_id or "").strip():
        missing.append("parent_thread_id")
    if not capabilities["heartbeat_scheduler"]:
        missing.append("callable heartbeat scheduler")
    status = "ready" if not missing else "blocked"
    return {
        "status": status,
        "missing": missing,
        "capabilities": capabilities,
        "reason": (
            "live orchestration ready"
            if status == "ready"
            else "live orchestration requires " + ", ".join(missing)
        ),
    }


@dataclass(frozen=True)
class LiveOrchestrationHostContext:
    thread_adapter: Any
    parent_thread_id: str
    heartbeat_scheduler: Any
    codex_project_id: str | None
    readiness: Mapping[str, Any]
    capabilities: Mapping[str, bool]


def make_live_orchestration_host_context(
    thread_adapter: Any | None,
    *,
    parent_thread_id: str | None,
    heartbeat_scheduler: Any,
    codex_project_id: str | None = None,
    required_tools: Iterable[str] = THREAD_TOOL_NAMES,
) -> LiveOrchestrationHostContext:
    readiness = assess_live_orchestration_readiness(
        thread_adapter,
        parent_thread_id=parent_thread_id,
        heartbeat_scheduler=heartbeat_scheduler,
        required_tools=required_tools,
    )
    if readiness["status"] != "ready":
        raise StateStoreError("live orchestration host context unavailable; %s" % readiness["reason"])
    return LiveOrchestrationHostContext(
        thread_adapter=thread_adapter,
        parent_thread_id=str(parent_thread_id or "").strip(),
        heartbeat_scheduler=heartbeat_scheduler,
        codex_project_id=str(codex_project_id).strip() if codex_project_id is not None and str(codex_project_id).strip() else None,
        readiness=readiness,
        capabilities=dict(readiness["capabilities"]),
    )


def _raise_if_host_context_conflict(name: str, explicit_value: Any, context_value: Any) -> None:
    if explicit_value is None:
        return
    if name in {"thread_adapter", "heartbeat_scheduler"}:
        conflicts = explicit_value is not context_value
    else:
        conflicts = explicit_value != context_value
    if conflicts:
        raise StateStoreError("host_context conflicts with explicit %s" % name)
