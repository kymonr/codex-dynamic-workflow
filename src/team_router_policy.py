# -*- coding: utf-8 -*-
"""Pure gate policy helpers for Team Router."""
from __future__ import annotations

from typing import Any, Mapping

from team_router_protocol import ProtocolError


REVIEWER_GATE_REQUIRED_TERMS = (
    "router/manager/orchestration policy",
    "orchestration policy",
    "permission boundary",
    "safety boundary",
    "permission or safety boundary",
    "process rule",
    "process rules",
    "flow rule",
    "flow rules",
    "role protocol",
    "shared/high-risk logic",
    "shared logic",
    "high-risk logic",
    "runtime gate",
    "reviewer gate",
    "team router self change",
    "team router self changes",
    "reviewer review",
    "reviewer 审核",
    "审查者",
    "direct-return",
    "direct return",
)

REVIEWER_GATE_TEAM_ROUTER_QUALIFIERS = (
    "reviewer",
    "runtime",
    "role protocol",
    "manager",
    "orchestration",
    "policy",
    "permission",
    "safety",
    "process",
    "shared",
    "high-risk",
    "high risk",
    "gate",
)

REVIEWER_GATE_TRUE_VALUES = {"true", "yes", "1", "required", "high", "high-risk", "high risk", "critical"}

ARCHITECT_GATE_TERMS = (
    "architecture",
    "architectural",
    "cross-module",
    "contract change",
    "protocol",
    "state-machine",
    "direct-return",
    "role protocol",
    "permission boundary",
    "migration",
    "compatibility",
    "dependency-boundary",
    "high-risk refactor",
    "durable maintainability",
)

QA_GATE_TERMS = (
    "test strategy",
    "acceptance criteria",
    "regression",
    "verification plan",
    "coverage gap",
    "multiple paths",
    "multiple modes",
    "evidence insufficient",
    "smoke",
    "test matrix",
)

GATE_CLASSES = ("FAST", "NORMAL", "STRICT", "PACKAGE")
FAST_GATE_TERMS = (
    "bom",
    "encoding",
    "docs-only",
    "typo",
    "wording",
    "readme",
)
PACKAGE_GATE_TERMS = (
    "package gate",
    "bundle related",
    "bundle same task family",
    "compounded",
    "same task family",
    "discipline hardening",
)


def _reviewer_gate_plan_fields(ledger: Mapping[str, Any]) -> Mapping[str, Any]:
    plan = ledger.get("plan") if isinstance(ledger.get("plan"), Mapping) else None
    fields = plan.get("fields") if isinstance(plan, Mapping) else None
    return fields if isinstance(fields, Mapping) else {}


def _reviewer_gate_text(ledger: Mapping[str, Any]) -> str:
    parts = [str(ledger.get("objective") or "")]
    fields = _reviewer_gate_plan_fields(ledger)
    for key in ("scope", "riskBoundary", "executorPrompt", "notes"):
        parts.append(str(fields.get(key) or ""))
    return "\n".join(parts).lower()


def _reviewer_gate_explicitly_required(ledger: Mapping[str, Any]) -> bool:
    fields = _reviewer_gate_plan_fields(ledger)
    for source in (ledger, fields):
        for key in ("reviewerGateRequired", "requiresReviewer"):
            value = source.get(key) if isinstance(source, Mapping) else None
            if isinstance(value, bool):
                if value:
                    return True
            elif str(value or "").strip().lower() in REVIEWER_GATE_TRUE_VALUES:
                return True
        risk_class = str(source.get("riskClass") or "").strip().lower() if isinstance(source, Mapping) else ""
        if risk_class in REVIEWER_GATE_TRUE_VALUES:
            return True
    return False


def _gate_explicitly_required(ledger: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    fields = _reviewer_gate_plan_fields(ledger)
    for source in (ledger, fields):
        for key in keys:
            value = source.get(key) if isinstance(source, Mapping) else None
            if isinstance(value, bool):
                if value:
                    return True
            elif str(value or "").strip().lower() in REVIEWER_GATE_TRUE_VALUES:
                return True
    return False


def classify_architect_gate(ledger: Mapping[str, Any]) -> bool:
    if _gate_explicitly_required(ledger, ("requiresArchitect", "architectureGateRequired")):
        return True
    text = _reviewer_gate_text(ledger)
    return any(term in text for term in ARCHITECT_GATE_TERMS)


def classify_qa_gate(ledger: Mapping[str, Any]) -> bool:
    if _gate_explicitly_required(ledger, ("requiresQa", "qaGateRequired")):
        return True
    text = _reviewer_gate_text(ledger)
    return any(term in text for term in QA_GATE_TERMS)


def _ledger_has_local_package_permission(ledger: Mapping[str, Any]) -> bool:
    plan = ledger.get("plan") if isinstance(ledger, Mapping) else None
    plan_fields = plan.get("fields") if isinstance(plan, Mapping) else None
    sources: list[Any] = []
    if isinstance(ledger, Mapping):
        sources.append(ledger.get("permission"))
    if isinstance(plan_fields, Mapping):
        sources.extend((
            plan_fields.get("acknowledgedPermission"),
            plan_fields.get("permission"),
        ))
    dispatches = ledger.get("dispatches") if isinstance(ledger, Mapping) else None
    if isinstance(dispatches, list):
        for dispatch in dispatches:
            if isinstance(dispatch, Mapping):
                sources.append(dispatch.get("permission"))
    return any(str(value or "").strip().lower() == "local-package" for value in sources)


def reviewer_gate_required_for_ledger(ledger: Mapping[str, Any]) -> bool:
    if _ledger_has_local_package_permission(ledger):
        return True
    if _reviewer_gate_explicitly_required(ledger):
        return True
    text = _reviewer_gate_text(ledger)
    if any(term in text for term in REVIEWER_GATE_REQUIRED_TERMS):
        return True
    return "team router" in text and any(term in text for term in REVIEWER_GATE_TEAM_ROUTER_QUALIFIERS)


def classify_team_router_gate(ledger: Mapping[str, Any]) -> str:
    text = _reviewer_gate_text(ledger)
    if any(term in text for term in PACKAGE_GATE_TERMS):
        return "PACKAGE"
    if _ledger_has_local_package_permission(ledger):
        return "STRICT"
    if reviewer_gate_required_for_ledger(ledger):
        return "STRICT"
    if any(term in text for term in FAST_GATE_TERMS):
        return "FAST"
    return "NORMAL"


def explain_team_router_gate(ledger: Mapping[str, Any]) -> dict[str, Any]:
    text = _reviewer_gate_text(ledger)
    reasons: list[str] = []
    package_terms = [term for term in PACKAGE_GATE_TERMS if term in text]
    fast_terms = [term for term in FAST_GATE_TERMS if term in text]
    reviewer_terms = [term for term in REVIEWER_GATE_REQUIRED_TERMS if term in text]
    team_router_qualifiers = [
        term for term in REVIEWER_GATE_TEAM_ROUTER_QUALIFIERS if term in text
    ]
    if package_terms:
        reasons.append("package term")
    if _ledger_has_local_package_permission(ledger):
        reasons.append("local-package permission requires reviewer gate")
    if _reviewer_gate_explicitly_required(ledger):
        reasons.append("explicit reviewer requirement")
    if reviewer_terms or ("team router" in text and team_router_qualifiers):
        reasons.append("reviewer-required term")
    if classify_architect_gate(ledger):
        reasons.append("architect gate")
    if classify_qa_gate(ledger):
        reasons.append("QA gate")
    if fast_terms and not reasons:
        reasons.append("fast docs term")
    gate = classify_team_router_gate(ledger)
    if gate == "NORMAL" and not reasons:
        reasons.append("normal fallback")
    return {
        "gateClass": gate,
        "requiresReviewer": gate_class_requires_reviewer(gate),
        "requiresArchitect": classify_architect_gate(ledger),
        "requiresQa": classify_qa_gate(ledger),
        "reasons": reasons,
    }


def explain_team_router_route(ledger: Mapping[str, Any]) -> dict[str, Any]:
    explanation = explain_team_router_gate(ledger)
    roles = ["executor"]
    if explanation["requiresArchitect"]:
        roles.insert(0, "architect")
    if explanation["requiresReviewer"]:
        roles.append("reviewer")
    if explanation["requiresQa"]:
        roles.append("qa")
    roles.append("verifier")
    return {
        "gateClass": explanation["gateClass"],
        "requiresArchitect": explanation["requiresArchitect"],
        "requiresReviewer": explanation["requiresReviewer"],
        "requiresQa": explanation["requiresQa"],
        "route": " -> ".join(roles),
        "roles": roles,
        "reasons": explanation["reasons"],
    }


def _required_gate_class(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError("gateClass must be a non-empty string")
    return value


def gate_class_requires_reviewer(gate_class: str) -> bool:
    gate = _required_gate_class(gate_class).upper()
    if gate not in GATE_CLASSES:
        raise ProtocolError("invalid gateClass: %r" % (gate_class,))
    return gate in {"STRICT", "PACKAGE"}
