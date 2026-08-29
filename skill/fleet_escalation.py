"""Deterministic Sol escalation policy for Agent Fleet v1."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

try:
    from skill.fleet_contract import FleetPackage
except ModuleNotFoundError:
    from fleet_contract import FleetPackage

MANDATORY_SOL_RISK_TAGS = frozenset(
    {
        "public-api",
        "schema",
        "migration",
        "security",
        "credentials",
        "permissions",
        "concurrency",
        "state-machine",
        "recovery",
        "persistence",
        "release",
        "sandbox",
        "integrity",
    }
)


class FleetEscalationError(RuntimeError):
    """The fleet aggregation inputs are inconsistent."""


def _unknowns(records: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for record in records:
        for item in record.get("unknown", []):
            values.append({"agent_id": record["agent_id"], "unknown": item})
    return values


def decide_sol_escalation(
    *,
    package: FleetPackage,
    findings: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    verification_passed: bool,
    candidate_stable: bool,
) -> dict[str, Any]:
    if not verification_passed:
        raise FleetEscalationError(
            "Sol arbitration cannot replace failed deterministic verification"
        )
    if not candidate_stable:
        raise FleetEscalationError(
            "Sol arbitration cannot replace a stable candidate revision"
        )
    triggers: list[dict[str, Any]] = []

    unknown = _unknowns(records)
    if unknown:
        triggers.append({"code": "agent-unknown", "evidence": unknown})

    high_risk = sorted(set(package.risk_tags) & MANDATORY_SOL_RISK_TAGS)
    if high_risk:
        triggers.append({"code": "high-risk-scope", "evidence": high_risk})

    accepted_blockers = [
        item["finding_id"]
        for item in findings
        if item["disposition"] == "accepted" and item["severity"] in {"P1", "P2"}
    ]
    if accepted_blockers:
        triggers.append(
            {"code": "accepted-blocker", "evidence": accepted_blockers}
        )

    conflicts = [
        item["finding_id"] for item in findings if item["disposition"] == "conflict"
    ]
    if conflicts:
        triggers.append({"code": "finding-conflict", "evidence": conflicts})

    unresolved = [
        item["finding_id"] for item in findings if item["disposition"] == "unresolved"
    ]
    if unresolved:
        triggers.append({"code": "finding-unresolved", "evidence": unresolved})

    requires_sol = bool(triggers)
    accepted_p3 = [
        item["finding_id"]
        for item in findings
        if item["disposition"] == "accepted" and item["severity"] == "P3"
    ]
    if requires_sol:
        preliminary = "needs-sol"
    elif accepted_p3:
        preliminary = "accept-with-notes"
    else:
        preliminary = "accept"
    return {
        "decision_version": 1,
        "candidate_revision": records[0]["candidate_revision"] if records else None,
        "requires_sol": requires_sol,
        "preliminary_verdict": preliminary,
        "triggers": triggers,
        "accepted_nonblocking_findings": accepted_p3,
        "discarded_findings": [
            item["finding_id"]
            for item in findings
            if item["disposition"] == "discarded"
        ],
        "majority_vote_used": False,
    }


def escalation_contract() -> dict[str, Any]:
    return {
        "mandatory_sol_risk_tags": sorted(MANDATORY_SOL_RISK_TAGS),
        "sol_triggers": [
            "agent-unknown",
            "high-risk-scope",
            "accepted-blocker",
            "finding-conflict",
            "finding-unresolved",
        ],
        "clean_skip_requires": [
            "verification passed",
            "candidate stable",
            "no UNKNOWN",
            "no high-risk tag",
            "no accepted P1/P2",
            "no conflict",
            "no unresolved finding",
        ],
        "majority_vote": False,
    }
