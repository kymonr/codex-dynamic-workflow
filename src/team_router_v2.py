# -*- coding: utf-8 -*-
"""Pure Version 2 Manager authorization and planning helpers."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from team_router_policy import (
    resolve_effective_gate,
    resolve_role_model,
    resolve_v2_execution_mode,
    resolve_v2_route,
)
from team_router_state import (
    StateStoreError,
    TERMINAL_STATUSES,
    THREAD_PERMISSIONS,
    cleanup_terminal_manager_pool_task,
    load_task_ledger,
    new_v2_task_ledger,
    next_rework_dispatch,
    release_role_claim,
    save_task_ledger,
    task_workflow_version,
)


DEFAULT_MODEL_COMBINATIONS = frozenset({
    "gpt-5.6-luna:medium",
    "gpt-5.6-terra:medium",
    "gpt-5.6-sol:high",
})
MODEL_AUTHORIZATION_SOURCES = frozenset({
    "explicit_cost_aware_entry",
    "complete_per_request_override",
})
BOOTSTRAP_MODEL = "gpt-5.6-luna"
BOOTSTRAP_THINKING = "medium"


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateStoreError("%s must be a non-empty string" % field)
    return value.strip()


def _role_thread_bootstrap_short_field(value: str, field: str, *,
                                       allowed: set[str] | None = None,
                                       max_chars: int = 160) -> str:
    text = _text(value, field)
    if "\r" in text or "\n" in text:
        raise StateStoreError("%s must be a single-line short field" % field)
    if len(text) > max_chars:
        raise StateStoreError("%s is too long for package bootstrap metadata" % field)
    evidence_markers = (
        "TEAM_ROUTER_REVIEW",
        "TEAM_ROUTER_VERDICT",
        "TEAM_ROUTER_CALLBACK",
        "evidenceChecked:",
        "findings:",
        "requiredChanges:",
        "<codex_delegation>",
    )
    if any(marker in text for marker in evidence_markers):
        raise StateStoreError("%s must be short metadata, not protocol evidence" % field)
    if allowed is not None and text not in allowed:
        raise StateStoreError("%s has unsupported value: %s" % (field, text))
    return text


def target_fingerprint_for(target: Mapping[str, Any], host_id: str) -> str:
    if not isinstance(target, Mapping) or not target:
        raise StateStoreError("invalid target fingerprint input")
    host_id = _text(host_id, "hostId")
    try:
        payload = json.dumps(
            {"hostId": host_id, "target": dict(target)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StateStoreError("invalid target fingerprint input") from exc
    return hashlib.sha256(payload).hexdigest()


def make_v2_role_bootstrap_prompt(*,
                                  request_id: str,
                                  project_id: str,
                                  parent_thread_id: str,
                                  role: str) -> str:
    return "\n".join((
        "TEAM_ROUTER_ROLE_BOOTSTRAP",
        "requestId: %s" % _role_thread_bootstrap_short_field(request_id, "requestId"),
        "projectId: %s" % _role_thread_bootstrap_short_field(project_id, "projectId"),
        "parentThreadId: %s" % _role_thread_bootstrap_short_field(parent_thread_id, "parentThreadId"),
        "role: %s" % _role_thread_bootstrap_short_field(
            role,
            "role",
            allowed={"executor", "reviewer", "verifier", "architect", "qa"},
            max_chars=32,
        ),
        "action: wait_for_formal_dispatch",
        "doNotExecuteTask: true",
    ))


def make_task_authorization_package(*,
                                    package_id: str,
                                    task_id: str,
                                    parent_thread_id: str,
                                    objective: str,
                                    scope: str,
                                    permission: str,
                                    stop_condition: str,
                                    created_at: str,
                                    model_routing_authorization: Mapping[str, Any] | None = None) -> dict[str, Any]:
    permission = _text(permission, "permission")
    if permission not in THREAD_PERMISSIONS:
        raise StateStoreError("invalid Team Router permission: %s" % permission)
    package = {
        "packageId": _text(package_id, "packageId"),
        "taskId": _text(task_id, "taskId"),
        "parentThreadId": _text(parent_thread_id, "parentThreadId"),
        "objective": _text(objective, "objective"),
        "scope": _text(scope, "scope"),
        "permission": permission,
        "stopCondition": _text(stop_condition, "stopCondition"),
        "createdAt": _text(created_at, "createdAt"),
        "status": "active",
    }
    if model_routing_authorization is not None:
        if not isinstance(model_routing_authorization, Mapping):
            raise StateStoreError("modelRoutingAuthorization must be a mapping")
        package["modelRoutingAuthorization"] = dict(model_routing_authorization)
    return package


def v2_continuation_allowed(ledger: Mapping[str, Any],
                            *,
                            parent_thread_id: str,
                            requested_task_id: str,
                            requested_objective: str,
                            requested_scope: str,
                            requested_permission: str,
                            requested_stop_condition: str,
                            requested_external_gates: tuple[str, ...] = ()) -> bool:
    if not isinstance(ledger, Mapping) or ledger.get("status") in TERMINAL_STATUSES:
        return False
    package = ledger.get("taskAuthorizationPackage")
    if not isinstance(package, Mapping) or package.get("status") != "active":
        return False
    if requested_external_gates:
        return False
    return (
        ledger.get("taskId") == requested_task_id == package.get("taskId")
        and ("parentThreadId" not in ledger or ledger.get("parentThreadId") == parent_thread_id)
        and package.get("parentThreadId") == parent_thread_id
        and ledger.get("objective") == requested_objective == package.get("objective")
        and package.get("scope") == requested_scope
        and package.get("permission") == requested_permission
        and package.get("stopCondition") == requested_stop_condition
    )


def validate_v2_authorization(*,
                              authorization_package: Mapping[str, Any] | None,
                              ledger_input: Mapping[str, Any],
                              scope: str,
                              permission: str,
                              stop_condition: str) -> dict[str, Any]:
    if not isinstance(authorization_package, Mapping):
        raise StateStoreError("authorization_missing: taskAuthorizationPackage is required")
    package = authorization_package
    expected = {
        "objective": ledger_input.get("objective"),
        "scope": scope,
        "permission": permission,
        "stopCondition": stop_condition,
    }
    for field, value in expected.items():
        if package.get(field) != value:
            raise StateStoreError("authorization_mismatch: %s" % field)
    for field in ("packageId", "taskId", "parentThreadId", "createdAt"):
        _text(package.get(field), field)
    if package.get("status") != "active":
        raise StateStoreError("authorization_missing: taskAuthorizationPackage is not active")
    for field in ("taskId", "parentThreadId"):
        actual = ledger_input.get(field)
        if actual is not None and package.get(field) != actual:
            raise StateStoreError("authorization_mismatch: %s" % field)
    if permission not in THREAD_PERMISSIONS:
        raise StateStoreError("invalid Team Router permission: %s" % permission)
    return {"workspaceWrite": permission == "local-package"}


def validate_model_routing_authorization(authorization: Mapping[str, Any] | None,
                                         *,
                                         route_roles: tuple[str, ...]) -> dict[str, Any]:
    if not route_roles:
        return {"allowedDefaults": frozenset()}
    if not isinstance(authorization, Mapping):
        raise StateStoreError("model_authorization_required")
    authorized_by = authorization.get("authorizedBy")
    if not isinstance(authorized_by, str) or authorized_by not in MODEL_AUTHORIZATION_SOURCES:
        raise StateStoreError("model_authorization_required")
    defaults = authorization.get("allowedDefaults", ())
    if isinstance(defaults, str) or not isinstance(defaults, (list, tuple, frozenset)):
        raise StateStoreError("model_authorization_required")
    allowed_defaults = frozenset(str(value) for value in defaults)
    if not allowed_defaults.issubset(DEFAULT_MODEL_COMBINATIONS):
        raise StateStoreError("model_authorization_required")
    if authorized_by == "explicit_cost_aware_entry" and allowed_defaults != DEFAULT_MODEL_COMBINATIONS:
        raise StateStoreError("model_authorization_required")
    if authorized_by == "complete_per_request_override" and allowed_defaults:
        raise StateStoreError("model_authorization_required")
    return {"allowedDefaults": allowed_defaults}


def _role_model_is_authorized(resolved: Mapping[str, Any],
                              model_authorization: Mapping[str, Any]) -> bool:
    override_reason = resolved.get("modelOverrideReason")
    if override_reason is None:
        combination = "%s:%s" % (resolved["requestedModel"], resolved["requestedThinking"])
        return combination in model_authorization["allowedDefaults"]
    return True


def resolve_v2_manager_plan(*,
                            objective: str,
                            scope: str,
                            permission: str,
                            stop_condition: str,
                            requested_gate_class: str,
                            authorization_package: Mapping[str, Any],
                            explicit_roles: tuple[str, ...] = (),
                            requested_role_routing: Mapping[str, Mapping[str, Any]] | None = None,
                            requires_parallelism: bool = False,
                            parallel_conflicts: tuple[str, ...] = (),
                            requires_independent_context: bool = False,
                            requires_independent_review: bool = False,
                            lightweight_verification_available: bool = True,
                            ledger_input: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ledger = dict(ledger_input or {})
    ledger.update({"objective": objective, "permission": permission, "workflowVersion": 2})
    plan_input = ledger.get("plan")
    plan = dict(plan_input) if isinstance(plan_input, Mapping) else {}
    fields_input = plan.get("fields")
    fields = dict(fields_input) if isinstance(fields_input, Mapping) else {}
    fields["scope"] = scope
    plan["fields"] = fields
    ledger["plan"] = plan
    authorization = validate_v2_authorization(
        authorization_package=authorization_package,
        ledger_input=ledger,
        scope=scope,
        permission=permission,
        stop_condition=stop_condition,
    )
    conflicts = tuple(parallel_conflicts)
    gate = resolve_effective_gate(requested_gate_class, ledger, authorization=authorization)
    execution_mode = resolve_v2_execution_mode(
        gate["effectiveGateClass"],
        explicit_roles=tuple(explicit_roles),
        requires_parallelism=requires_parallelism,
        requires_independent_context=requires_independent_context,
        requires_independent_review=requires_independent_review,
        lightweight_verification_available=lightweight_verification_available,
    )
    plan = {
        "objective": objective,
        "taskAuthorizationPackageId": authorization_package["packageId"],
        "taskId": authorization_package["taskId"],
        "parentThreadId": authorization_package["parentThreadId"],
        "executionMode": execution_mode,
        "requestedGateClass": gate["requestedGateClass"],
        "effectiveGateClass": gate["effectiveGateClass"],
        "gateReason": gate["gateReason"],
        "parallelAllowed": bool(requires_parallelism and not conflicts),
        "parallelConflicts": conflicts,
        "scope": scope,
        "permission": permission,
        "stopCondition": stop_condition,
    }
    if execution_mode == "manager_direct":
        return dict(plan, routeRoles=(), roleRouting={}, parallelAllowed=False)

    route_roles = resolve_v2_route(gate["effectiveGateClass"], tuple(explicit_roles))
    model_authorization = validate_model_routing_authorization(
        authorization_package.get("modelRoutingAuthorization"),
        route_roles=route_roles,
    )
    requests = requested_role_routing if isinstance(requested_role_routing, Mapping) else {}
    candidate_routing = {
        str(role): dict(request)
        for role, request in requests.items()
        if isinstance(request, Mapping)
    }
    resolved_routing = {}
    for role in route_roles:
        request = requests.get(role)
        if not isinstance(request, Mapping):
            raise StateStoreError("plan_invalid: missing roleRouting.%s" % role)
        try:
            resolved = resolve_role_model(
                request["executionClass"],
                model=request.get("model"),
                thinking=request.get("thinking"),
                override_reason=request.get("modelOverrideReason"),
            )
        except KeyError as exc:
            raise StateStoreError("plan_invalid: missing roleRouting.%s.executionClass" % role) from exc
        if not _role_model_is_authorized(resolved, model_authorization):
            raise StateStoreError("model_authorization_required")
        resolved_routing[role] = resolved
    return dict(
        plan,
        routeRoles=route_roles,
        roleRouting=resolved_routing,
        candidateRoleRouting=candidate_routing,
        modelRoutingAuthorization=dict(authorization_package["modelRoutingAuthorization"]),
    )


def _requested_plan_value(requested_plan: Mapping[str, Any], field: str) -> Any:
    if field not in requested_plan:
        raise StateStoreError("plan_invalid: missing %s" % field)
    return requested_plan[field]


def prepare_v2_manager_task(state_root: str,
                            project_id: str,
                            task_id: str,
                            *,
                            objective: str,
                            project_local_path: str,
                            parent_thread_id: str,
                            requested_plan: Mapping[str, Any],
                            authorization_package: Mapping[str, Any],
                            created_at: str) -> dict[str, Any]:
    if not isinstance(requested_plan, Mapping):
        raise StateStoreError("plan_invalid: requestedPlan must be a mapping")
    resolved_plan = resolve_v2_manager_plan(
        objective=objective,
        scope=_requested_plan_value(requested_plan, "scope"),
        permission=_requested_plan_value(requested_plan, "permission"),
        stop_condition=_requested_plan_value(requested_plan, "stopCondition"),
        requested_gate_class=_requested_plan_value(requested_plan, "requestedGateClass"),
        authorization_package=authorization_package,
        explicit_roles=tuple(requested_plan.get("explicitRoles", ())),
        requested_role_routing=requested_plan.get("requestedRoleRouting"),
        requires_parallelism=bool(requested_plan.get("requiresParallelism", False)),
        parallel_conflicts=tuple(requested_plan.get("parallelConflicts", ())),
        requires_independent_context=bool(requested_plan.get("requiresIndependentContext", False)),
        requires_independent_review=bool(requested_plan.get("requiresIndependentReview", False)),
        lightweight_verification_available=bool(requested_plan.get("lightweightVerificationAvailable", True)),
        ledger_input={"taskId": task_id, "parentThreadId": parent_thread_id},
    )
    if resolved_plan["executionMode"] == "manager_direct":
        return dict(resolved_plan, ledger=None)
    ledger = new_v2_task_ledger(
        state_root,
        project_id,
        task_id,
        objective=objective,
        project_local_path=project_local_path,
        parent_thread_id=parent_thread_id,
        resolved_plan=resolved_plan,
        task_authorization_package=authorization_package,
        created_at=created_at,
        max_rework=1,
    )
    return dict(
        resolved_plan,
        ledger=save_task_ledger(state_root, project_id, task_id, ledger),
    )


def _v2_plan(ledger: Mapping[str, Any]) -> Mapping[str, Any]:
    plan = ledger.get("resolvedPlan") or ledger.get("plan")
    if not isinstance(plan, Mapping):
        raise StateStoreError("plan_invalid: resolved V2 plan is required")
    return plan


_V2_GATE_RANK = {"FAST": 0, "NORMAL": 1, "STRICT": 2, "PACKAGE": 3}


def _v2_reclassification_gate(plan: Mapping[str, Any], evidence: Mapping[str, Any]) -> str:
    current = str(plan.get("effectiveGateClass", "")).upper()
    if current not in _V2_GATE_RANK:
        raise StateStoreError("plan_invalid: effectiveGateClass")
    requested = current
    for field in ("requestedGateClass", "effectiveGateClass", "gateClass", "riskClass"):
        value = str(evidence.get(field, "")).upper()
        if value in _V2_GATE_RANK:
            requested = max(requested, value, key=_V2_GATE_RANK.__getitem__)
    risk_text = " ".join(str(evidence.get(field, "")) for field in ("risks", "riskBoundary", "notes")).lower()
    if any(term in risk_text for term in ("package", "strict", "security", "production", "permission", "safety")):
        requested = max(requested, "STRICT", key=_V2_GATE_RANK.__getitem__)
    if evidence.get("requiresReviewer") or evidence.get("requiresIndependentReview"):
        requested = max(requested, "STRICT", key=_V2_GATE_RANK.__getitem__)
    return requested


def _v2_reclassification_role_routing(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    candidates = plan.get("candidateRoleRouting") if isinstance(plan.get("candidateRoleRouting"), Mapping) else {}
    routing = plan.get("roleRouting") if isinstance(plan.get("roleRouting"), Mapping) else {}
    requests: dict[str, dict[str, Any]] = {}
    for source in (candidates, routing):
        for role, resolved in source.items():
            if not isinstance(resolved, Mapping):
                continue
            request = {"executionClass": resolved.get("executionClass")}
            if resolved.get("modelOverrideReason") is not None:
                request.update({
                    "model": resolved.get("requestedModel") or resolved.get("model"),
                    "thinking": resolved.get("requestedThinking") or resolved.get("thinking"),
                    "modelOverrideReason": resolved.get("modelOverrideReason"),
                })
            requests[str(role)] = request
    return requests


def next_v2_route_after_evidence(ledger: Mapping[str, Any],
                                 evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Re-close a V2 route after evidence, without creating or messaging roles."""
    if task_workflow_version(ledger) != 2:
        raise StateStoreError("v2_route_reclassification_requires_v2")
    if not isinstance(evidence, Mapping):
        raise StateStoreError("evidence must be a mapping")
    plan = _v2_plan(ledger)
    for evidence_field, plan_field in (("scope", "scope"), ("permission", "permission"),
                                       ("stopCondition", "stopCondition")):
        if evidence_field in evidence and evidence[evidence_field] != plan.get(plan_field):
            raise StateStoreError("authorization_mismatch: %s" % plan_field)
    if evidence.get("externalGates"):
        raise StateStoreError("authorization_mismatch: externalGates")
    requested_gate = _v2_reclassification_gate(plan, evidence)
    existing_roles = tuple(plan.get("routeRoles", ()))
    replanned = resolve_v2_manager_plan(
        objective=_text(ledger.get("objective"), "objective"),
        scope=_text(plan.get("scope"), "scope"),
        permission=_text(plan.get("permission"), "permission"),
        stop_condition=_text(plan.get("stopCondition"), "stopCondition"),
        requested_gate_class=requested_gate,
        authorization_package=ledger.get("taskAuthorizationPackage"),
        explicit_roles=existing_roles,
        requested_role_routing=_v2_reclassification_role_routing(plan),
        requires_parallelism=bool(plan.get("parallelAllowed")),
        parallel_conflicts=tuple(plan.get("parallelConflicts", ())),
        ledger_input={
            "taskId": ledger.get("taskId"),
            "parentThreadId": ledger.get("parentThreadId"),
        },
    )
    replanned["requestedGateClass"] = plan.get("requestedGateClass")
    replanned["gateReason"] = "%s; evidence raised effective gate to %s" % (
        plan.get("gateReason", "requested %s" % plan.get("requestedGateClass")),
        replanned["effectiveGateClass"],
    )
    updated = dict(ledger)
    updated["plan"] = replanned
    if isinstance(ledger.get("resolvedPlan"), Mapping):
        updated["resolvedPlan"] = dict(replanned)
    route = tuple(replanned["routeRoles"])
    if "reviewer" in route:
        updated["status"] = "reviewing"
    elif "qa" in route:
        updated["status"] = "awaiting_qa_review"
    elif "verifier" in route:
        updated["status"] = "verifying"
    else:
        updated["status"] = "manager_acceptance_pending"
    observations = list(ledger.get("observations", ()))
    observations.append({
        "type": "v2_route_reclassified",
        "role": "manager",
        "parsedFields": {
            "previousEffectiveGateClass": plan.get("effectiveGateClass"),
            "effectiveGateClass": replanned["effectiveGateClass"],
            "routeRoles": list(route),
        },
    })
    updated["observations"] = observations
    return updated


def resume_v2_manager_routing(state_root: str | Path,
                              project_id: str,
                              task_id: str,
                              *,
                              objective: str,
                              parent_thread_id: str,
                              manager_plan: Mapping[str, Any],
                              authorization_package: Mapping[str, Any]) -> dict[str, Any]:
    """Resume only a callback-paused V2 route with explicit STRICT candidates."""
    ledger = load_task_ledger(state_root, project_id, task_id)
    if ledger.get("status") != "manager_routing_pending":
        raise StateStoreError("manager_routing_resume_requires_manager_routing_pending")
    plan = _v2_plan(ledger)
    if not isinstance(manager_plan, Mapping):
        raise StateStoreError("plan_invalid: managerPlan must be a mapping")
    if _text(objective, "objective") != _text(ledger.get("objective"), "objective"):
        raise StateStoreError("authorization_mismatch: objective")
    if _text(parent_thread_id, "parentThreadId") != _text(ledger.get("parentThreadId"), "parentThreadId"):
        raise StateStoreError("authorization_mismatch: parentThreadId")
    package = ledger.get("taskAuthorizationPackage")
    if not isinstance(package, Mapping) or dict(authorization_package) != dict(package):
        raise StateStoreError("authorization_mismatch: taskAuthorizationPackage")
    for field in ("scope", "permission", "stopCondition"):
        if manager_plan.get(field) != plan.get(field):
            raise StateStoreError("authorization_mismatch: %s" % field)
    if manager_plan.get("externalGates"):
        raise StateStoreError("authorization_mismatch: externalGates")
    if str(manager_plan.get("requestedGateClass", "")).upper() != "STRICT":
        raise StateStoreError("plan_invalid: manager routing resume requires STRICT")
    explicit = manager_plan.get("requestedRoleRouting")
    if not isinstance(explicit, Mapping):
        raise StateStoreError("plan_invalid: requestedRoleRouting is required")
    candidates = plan.get("candidateRoleRouting") if isinstance(plan.get("candidateRoleRouting"), Mapping) else {}
    merged = {str(role): dict(request) for role, request in candidates.items() if isinstance(request, Mapping)}
    merged.update({str(role): dict(request) for role, request in explicit.items() if isinstance(request, Mapping)})
    staged_plan = dict(plan, candidateRoleRouting=merged)
    staged = dict(ledger, plan=staged_plan)
    if isinstance(ledger.get("resolvedPlan"), Mapping):
        staged["resolvedPlan"] = dict(staged_plan)
    resumed = next_v2_route_after_evidence(staged, {"requestedGateClass": "STRICT"})
    resumed["status"] = "planned"
    resumed.pop("routingError", None)
    return save_task_ledger(state_root, project_id, task_id, resumed)


def build_v2_routing_receipt(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Project recorded dispatch requests without claiming host billing facts."""
    model_sources: list[Mapping[str, Any]] = []
    dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
    model_sources.extend(item for item in dispatches if isinstance(item, Mapping))
    plan = _v2_plan(ledger)
    routing = plan.get("roleRouting") if isinstance(plan.get("roleRouting"), Mapping) else {}
    model_sources.extend(item for item in routing.values() if isinstance(item, Mapping))
    pending = ledger.get("pendingModelUpgrade")
    if isinstance(pending, Mapping):
        model_sources.append(pending)
    for source in model_sources:
        if (source.get("requestedModel"), source.get("requestedThinking")) == ("gpt-5.6-sol", "ultra"):
            raise StateStoreError("model_forbidden: gpt-5.6-sol ultra")
    roles: list[dict[str, Any]] = []
    for dispatch in dispatches:
        if not isinstance(dispatch, Mapping):
            continue
        role = dispatch.get("role")
        if not isinstance(role, str) or not role:
            continue
        item: dict[str, Any] = {
            "role": role,
            "binding": dispatch.get("binding", "unknown"),
            "dispatchAccepted": bool(dispatch.get("dispatchAccepted")),
        }
        for field in ("binding", "threadId", "requestedModel", "requestedThinking",
                      "bootstrapModel", "bootstrapThinking", "creationAccepted",
                      "dispatchAccepted", "modelOverrideReason", "upgradedFrom"):
            if field in dispatch:
                item[field] = dispatch[field]
        item["reworkCount"] = ledger.get("reworkCount", 0)
        roles.append(item)
    return {"roles": roles, "solUltraDispatched": False}


def _required_nonempty_strings(value: Any, field: str) -> list[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)) or not value:
        raise StateStoreError("model_upgrade_invalid: %s is required" % field)
    values = [_text(item, field) for item in value]
    if not values:
        raise StateStoreError("model_upgrade_invalid: %s is required" % field)
    return values


def _latest_v2_role_dispatch(ledger: Mapping[str, Any], role: str) -> Mapping[str, Any] | None:
    dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
    for dispatch in reversed(dispatches):
        if isinstance(dispatch, Mapping) and dispatch.get("role") == role:
            return dispatch
    return None


def record_v2_model_upgrade(state_root: str,
                            project_id: str,
                            task_id: str,
                            *,
                            parent_thread_id: str,
                            role: str,
                            failed_request_id: str,
                            execution_class: str,
                            model: str | None = None,
                            thinking: str | None = None,
                            override_reason: str | None = None,
                            completed_results: Any,
                            read_files: Any,
                            exact_failure: str,
                            unresolved: Any,
                            requested_at: str) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    if task_workflow_version(ledger) != 2:
        raise StateStoreError("model_upgrade_requires_v2")
    if _text(parent_thread_id, "parentThreadId") != _text(ledger.get("parentThreadId"), "parentThreadId"):
        raise StateStoreError("model_upgrade_identity_mismatch: parentThreadId")
    role = _text(role, "role")
    failed_request_id = _text(failed_request_id, "failedRequestId")
    failed = _latest_v2_role_dispatch(ledger, role)
    if failed is None or failed.get("requestId") != failed_request_id:
        raise StateStoreError("model_upgrade_identity_mismatch: failedRequestId")
    if failed.get("dispatchAccepted") is not False and not str(failed.get("failureReason", "")).strip():
        raise StateStoreError("model_upgrade_identity_mismatch: latest request is not failed")
    failed_model = _text(failed.get("requestedModel"), "failedRequest.requestedModel")
    failed_thinking = _text(failed.get("requestedThinking"), "failedRequest.requestedThinking")
    completed = _required_nonempty_strings(completed_results, "completedResults")
    files = _required_nonempty_strings(read_files, "readFiles")
    failure = _text(exact_failure, "exactFailure")
    remaining = _required_nonempty_strings(unresolved, "unresolved")
    resolved = resolve_role_model(
        _text(execution_class, "executionClass"),
        model=model,
        thinking=thinking,
        override_reason=override_reason,
    )
    if (resolved["requestedModel"], resolved["requestedThinking"]) == (failed_model, failed_thinking):
        raise StateStoreError("model_upgrade_invalid: target model must differ from failed request")
    plan = _v2_plan(ledger)
    if role not in tuple(plan.get("routeRoles", ())):
        raise StateStoreError("model_upgrade_identity_mismatch: role")
    model_authorization = validate_model_routing_authorization(
        ledger.get("taskAuthorizationPackage", {}).get("modelRoutingAuthorization")
        if isinstance(ledger.get("taskAuthorizationPackage"), Mapping) else None,
        route_roles=(role,),
    )
    if not _role_model_is_authorized(resolved, model_authorization):
        raise StateStoreError("model_authorization_required")
    if int(ledger.get("modelUpgradeCount", 0)) >= 1:
        ledger["status"] = "blocked"
        ledger["reason"] = "model_upgrade_limit"
        ledger["modelUpgradeError"] = {"reason": "model_upgrade_limit", "requestedAt": _text(requested_at, "requestedAt")}
        saved = save_task_ledger(state_root, project_id, task_id, ledger)
        cleanup_terminal_manager_pool_task(
            state_root,
            project_id,
            parent_thread_id=parent_thread_id,
            task_id=task_id,
            cleaned_at=requested_at,
        )
        return load_task_ledger(state_root, project_id, task_id)
    pending = {
        "parentThreadId": parent_thread_id,
        "role": role,
        "failedRequestId": failed_request_id,
        "executionClass": resolved["executionClass"],
        "requestedModel": resolved["requestedModel"],
        "requestedThinking": resolved["requestedThinking"],
        "upgradedFrom": failed_model,
        "completedResults": completed,
        "readFiles": files,
        "exactFailure": failure,
        "unresolved": remaining,
        "requestedAt": _text(requested_at, "requestedAt"),
    }
    if isinstance(failed.get("threadId"), str) and failed.get("threadId"):
        pending["preferredThreadId"] = failed["threadId"]
    elif isinstance(ledger.get("preferredThreadId"), str) and ledger.get("preferredThreadId"):
        pending["preferredThreadId"] = ledger["preferredThreadId"]
    if "modelOverrideReason" in resolved:
        pending["modelOverrideReason"] = resolved["modelOverrideReason"]
    ledger["pendingModelUpgrade"] = pending
    ledger["modelUpgradeCount"] = 1
    ledger["status"] = "needs_rework"
    ledger["modelUpgradePending"] = True
    return save_task_ledger(state_root, project_id, task_id, ledger)


def _v2_final_executor_callback(ledger: Mapping[str, Any]) -> Mapping[str, Any] | None:
    observations = ledger.get("observations") if isinstance(ledger.get("observations"), list) else []
    for observation in reversed(observations):
        if not isinstance(observation, Mapping):
            continue
        if observation.get("type") != "callback_raw" or observation.get("role") != "executor":
            continue
        fields = observation.get("parsedFields")
        if not isinstance(fields, Mapping):
            continue
        final = str(fields.get("final", "")).strip().lower() == "true"
        if final and str(fields.get("status", "")).strip().lower() == "done":
            return fields
    return None


def _apply_v2_closeout_receipt(closeout: dict[str, Any],
                               receipt: Mapping[str, Any] | None) -> None:
    if not isinstance(receipt, Mapping):
        return
    source = str(receipt.get("source", "")).strip()
    channel = str(receipt.get("channel", "")).strip()
    if source:
        closeout["receiptSource"] = source
    if channel:
        closeout["receiptChannel"] = channel
    role_thread_id = receipt.get("roleThreadId")
    if role_thread_id:
        closeout["receiptRoleThreadId"] = str(role_thread_id)
    return_thread_id = receipt.get("returnThreadId")
    if return_thread_id:
        closeout["returnThreadId"] = str(return_thread_id)
    if source == "self-thread-fallback/read_thread" or channel == "read_thread":
        closeout["deliveryStatus"] = "fallback_only"
        closeout["deliveryDegraded"] = True
    elif source == "manager-inbox/direct-send" or channel == "manager-inbox":
        closeout["deliveryStatus"] = "direct_send"


def _release_v2_executor_claim(state_root: str, project_id: str,
                               task_id: str, ledger: Mapping[str, Any]) -> None:
    dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
    for dispatch in reversed(dispatches):
        if not isinstance(dispatch, Mapping) or dispatch.get("role") != "executor":
            continue
        thread_id = dispatch.get("threadId")
        request_id = dispatch.get("requestId")
        if isinstance(thread_id, str) and thread_id and isinstance(request_id, str) and request_id:
            release_role_claim(
                state_root,
                project_id,
                parent_thread_id=_text(ledger.get("parentThreadId"), "parentThreadId"),
                role="executor",
                thread_id=thread_id,
                task_id=task_id,
                request_id=request_id,
            )
        return


def make_manager_acceptance_closeout(ledger: Mapping[str, Any], *,
                                     completed_at: str) -> dict[str, Any]:
    acceptance = ledger.get("managerAcceptance")
    if not isinstance(acceptance, Mapping):
        raise StateStoreError("manager_acceptance_missing")
    accepted = ledger.get("status") == "done" and acceptance.get("result") == "pass"
    callback = _v2_final_executor_callback(ledger) or {}
    next_gate = "none" if accepted else "user direction"
    terminal = ledger.get("status") in TERMINAL_STATUSES
    changed = callback.get("summary", "executor callback")
    verified = acceptance.get("evidenceChecked", "")
    closeout = {
        "status": "accepted" if accepted else ledger.get("status"),
        "capturedAt": _text(completed_at, "completedAt"),
        "acceptedBy": "manager",
        "changed": changed,
        "verified": verified,
        "summary": changed,
        "evidenceChecked": verified,
        "notDone": "stage/commit/push/PR/publish/release were not done",
        "risks": acceptance.get("remainingRisks", ""),
        "nextGate": next_gate,
        "nextAction": next_gate,
        "remainingTodos": "none" if accepted else next_gate,
        "routingReceipt": build_v2_routing_receipt(ledger),
        "compoundingDecision": "skipped",
        "reason": acceptance.get("reason") or "ordinary successful implementation/testing with no new reusable risk",
        "watcherAction": "stop_and_delete_heartbeat" if terminal else "",
    }
    _apply_v2_closeout_receipt(
        closeout,
        ledger.get("callbackReceipt") if isinstance(ledger.get("callbackReceipt"), Mapping) else None,
    )
    if terminal:
        closeout.update({
            "reportAction": "emit one plain language closeout report to the user",
            "plainLanguageReport": "required",
        })
    return closeout


def record_manager_acceptance(state_root: str,
                              project_id: str,
                              task_id: str,
                              *,
                              result: str,
                              accepted_at: str,
                              callback_receipt: str,
                              scope_checked: str,
                              evidence_checked: str,
                              risk_boundary_checked: str,
                              remaining_risks: str,
                              reason: str | None = None) -> dict[str, Any]:
    ledger = load_task_ledger(state_root, project_id, task_id)
    if task_workflow_version(ledger) != 2:
        raise StateStoreError("manager_acceptance_requires_v2")
    if ledger.get("status") != "manager_acceptance_pending":
        raise StateStoreError("manager_acceptance_not_pending")
    ledger = next_v2_route_after_evidence(ledger, _v2_final_executor_callback(ledger) or {})
    if ledger.get("status") != "manager_acceptance_pending":
        raise StateStoreError("manager_acceptance_not_allowed")
    result = _text(result, "result")
    if result not in {"pass", "needs_rework", "blocked"}:
        raise StateStoreError("invalid manager acceptance result: %s" % result)
    plan = _v2_plan(ledger)
    route = tuple(plan.get("routeRoles", ()))
    gate = str(plan.get("effectiveGateClass", "")).upper()
    if result == "pass":
        if gate not in {"FAST", "NORMAL"} or any(role in route for role in ("reviewer", "qa", "verifier")):
            raise StateStoreError("manager_acceptance_not_allowed")
        if _v2_final_executor_callback(ledger) is None:
            raise StateStoreError("manager_acceptance_requires_final_executor_callback")
    acceptance = {
        "result": result,
        "acceptedAt": _text(accepted_at, "acceptedAt"),
        "callbackReceipt": _text(callback_receipt, "callbackReceipt"),
        "scopeChecked": _text(scope_checked, "scopeChecked"),
        "evidenceChecked": _text(evidence_checked, "evidenceChecked"),
        "riskBoundaryChecked": _text(risk_boundary_checked, "riskBoundaryChecked"),
        "remainingRisks": _text(remaining_risks, "remainingRisks"),
    }
    if reason is not None:
        acceptance["reason"] = _text(reason, "reason")
    ledger["managerAcceptance"] = acceptance
    if result == "pass":
        ledger["status"] = "done"
    elif result == "needs_rework":
        _release_v2_executor_claim(state_root, project_id, task_id, ledger)
        ledger = load_task_ledger(state_root, project_id, task_id)
        ledger["managerAcceptance"] = acceptance
        ledger["status"], ledger["reworkCount"] = next_rework_dispatch(
            ledger["reworkCount"], ledger["maxRework"],
        )
    else:
        ledger["status"] = "blocked"
    if ledger["status"] in TERMINAL_STATUSES:
        ledger["closeout"] = make_manager_acceptance_closeout(ledger, completed_at=accepted_at)
    saved = save_task_ledger(state_root, project_id, task_id, ledger)
    if saved["status"] in TERMINAL_STATUSES:
        cleanup_terminal_manager_pool_task(
            state_root,
            project_id,
            parent_thread_id=_text(saved.get("parentThreadId"), "parentThreadId"),
            task_id=task_id,
            cleaned_at=accepted_at,
        )
    return load_task_ledger(state_root, project_id, task_id)


def run_v2_team_task_with_adapter(state_root: str | Path,
                                  project_id: str,
                                  task_id: str,
                                  *,
                                  objective: str,
                                  project_local_path: str | Path,
                                  thread_adapter: Any,
                                  permission: str,
                                  observed_at: str,
                                  target: Mapping[str, Any],
                                  target_fingerprint: str | None,
                                  host_id: str,
                                  parent_thread_id: str,
                                  manager_plan: Mapping[str, Any] | None,
                                  task_authorization_package: Mapping[str, Any] | None,
                                  turn_limit: int | None = None,
                                  confirm_rework: bool = False,
                                  return_thread_id: str | None = None) -> dict[str, Any]:
    """Expose the facade runner without importing the facade during module load."""
    from team_router import run_v2_team_task_with_adapter as run
    return run(
        state_root,
        project_id,
        task_id,
        objective=objective,
        project_local_path=project_local_path,
        thread_adapter=thread_adapter,
        permission=permission,
        observed_at=observed_at,
        target=target,
        target_fingerprint=target_fingerprint,
        host_id=host_id,
        parent_thread_id=parent_thread_id,
        manager_plan=manager_plan,
        task_authorization_package=task_authorization_package,
        turn_limit=turn_limit,
        confirm_rework=confirm_rework,
        return_thread_id=return_thread_id,
    )
