# -*- coding: utf-8 -*-
"""Pure Version 2 Manager authorization and planning helpers."""
from __future__ import annotations

from typing import Any, Mapping

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
    new_v2_task_ledger,
    save_task_ledger,
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


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateStoreError("%s must be a non-empty string" % field)
    return value.strip()


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
