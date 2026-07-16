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
CORE_THREAD_TOOL_NAMES = tuple(
    tool_name for tool_name in THREAD_TOOL_NAMES
    if tool_name != "set_thread_title"
)
READINESS_TIERS = (
    "manual/pre-created",
    "interactive_contract_ready",
    "unattended_contract_ready",
    "interactive_live_verified",
    "unattended_live_verified",
)


def probe_thread_adapter_capabilities(
    thread_adapter: Any,
    required_tools: Iterable[str] = CORE_THREAD_TOOL_NAMES,
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
    identity_evidence: Mapping[str, Any] | None = None,
    live_verification_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    capabilities = {
        tool_name: bool(thread_adapter is not None and callable(_adapter_method(thread_adapter, tool_name)))
        for tool_name in THREAD_TOOL_NAMES
    }
    if thread_adapter is None:
        missing.append("callable adapter")
    else:
        for tool_name in required_tools:
            if tool_name == "set_thread_title":
                continue
            if not capabilities.get(tool_name, False):
                missing.append("callable %s" % tool_name)
    if not capabilities["set_thread_title"]:
        warnings.append("callable set_thread_title")
    if identity_evidence is None and thread_adapter is not None:
        candidate = _adapter_method(thread_adapter, "team_router_identity_evidence")
        identity_evidence = candidate if isinstance(candidate, Mapping) else None
    identity = dict(identity_evidence or {})
    capabilities["trusted_sender_provenance"] = identity.get("trustedSenderProvenance") is True
    capabilities["trusted_execution_domain"] = identity.get("trustedExecutionDomain") is True
    if not capabilities["trusted_sender_provenance"]:
        missing.append("trusted sender provenance")
    if not capabilities["trusted_execution_domain"]:
        missing.append("trusted execution domain")
    capabilities["heartbeat_scheduler"] = _is_callable_heartbeat_scheduler(heartbeat_scheduler)
    if not str(parent_thread_id or "").strip():
        missing.append("parent_thread_id")
    if not capabilities["heartbeat_scheduler"]:
        warnings.append("callable heartbeat scheduler")
    if missing:
        tier = "manual/pre-created"
    elif capabilities["heartbeat_scheduler"]:
        tier = "unattended_contract_ready"
    else:
        tier = "interactive_contract_ready"
    live_evidence = dict(live_verification_evidence or {})
    live_source = live_evidence.get("source") == "codex-desktop-live"
    live_thread_calls = live_evidence.get("threadToolCallsExecuted")
    live_thread_verified = (
        live_source
        and isinstance(live_thread_calls, int)
        and not isinstance(live_thread_calls, bool)
        and live_thread_calls > 0
    )
    if tier == "interactive_contract_ready" and live_thread_verified:
        tier = "interactive_live_verified"
    elif tier == "unattended_contract_ready" and live_thread_verified:
        scheduler_calls = live_evidence.get("heartbeatSchedulesExecuted")
        if isinstance(scheduler_calls, int) and not isinstance(scheduler_calls, bool) and scheduler_calls > 0:
            tier = "unattended_live_verified"
        else:
            tier = "interactive_live_verified"
    status = "blocked" if tier == "manual/pre-created" else "ready"
    return {
        "status": status,
        "tier": tier,
        "missing": missing,
        "warnings": warnings,
        "capabilities": capabilities,
        "identityEvidence": identity,
        "liveVerificationEvidence": live_evidence,
        "reason": (
            "live orchestration contract tier: %s" % tier
            if status == "ready"
            else "manual/pre-created only; requires " + ", ".join(missing)
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
