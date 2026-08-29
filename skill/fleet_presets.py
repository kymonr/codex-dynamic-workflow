"""Deterministic Agent Fleet v1 preset and schedule registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from skill.fleet_contract import FleetPackage, canonical_digest
except ModuleNotFoundError:
    from fleet_contract import FleetPackage, canonical_digest

SCHEDULE_VERSION = 1
PHASES = ("discovery", "challenge", "reproduction")


@dataclass(frozen=True)
class RoleSpec:
    role_id: str
    title: str
    focus: str
    phase: str = "discovery"

    def record(self) -> dict[str, str]:
        return {
            "role_id": self.role_id,
            "title": self.title,
            "focus": self.focus,
            "phase": self.phase,
        }


COMMON_CHALLENGERS = (
    RoleSpec(
        "finding-challenger-a",
        "Finding Challenger A",
        "Try to falsify proposed findings, identify missing counterevidence, and expose weak inference.",
        "challenge",
    ),
    RoleSpec(
        "finding-challenger-b",
        "Finding Challenger B",
        "Independently challenge surviving findings and the fleet's clean-result assumptions.",
        "challenge",
    ),
)
COMMON_REPRODUCERS = (
    RoleSpec(
        "reproduction-verifier-a",
        "Reproduction Verifier A",
        "Independently reproduce or refute assigned findings from code paths and declared verification evidence.",
        "reproduction",
    ),
    RoleSpec(
        "reproduction-verifier-b",
        "Reproduction Verifier B",
        "Use an independent reasoning path to reproduce, refute, or mark assigned findings inconclusive.",
        "reproduction",
    ),
)


DISCOVERY_POOLS: dict[str, tuple[RoleSpec, ...]] = {
    "adversarial-review": (
        RoleSpec("correctness-hunter", "Correctness Hunter", "Find concrete logic, state, and error-path defects."),
        RoleSpec("regression-hunter", "Regression Hunter", "Find caller, compatibility, and existing-behavior regressions."),
        RoleSpec("test-evidence-auditor", "Test and Evidence Auditor", "Check whether tests and evidence actually prove the acceptance criteria."),
        RoleSpec("devils-advocate", "Devil's Advocate", "Assume the candidate is wrong and construct counterexamples."),
        RoleSpec("api-compatibility", "API and Compatibility Reviewer", "Inspect public interfaces, formats, callers, and upgrade compatibility."),
        RoleSpec("security-reviewer", "Security Reviewer", "Inspect trust boundaries, authorization, secrets, and unsafe input handling."),
        RoleSpec("concurrency-lifecycle", "Concurrency and Lifecycle Reviewer", "Inspect ordering, cancellation, recovery, state machines, and resource lifecycle."),
        RoleSpec("scope-platform-performance", "Scope, Platform, and Performance Auditor", "Inspect unauthorized scope, platform differences, and material performance risk."),
    ),
    "competing-hypotheses": (
        RoleSpec("hypothesis-1", "Hypothesis Investigator 1", "Develop and test the strongest plausible root-cause hypothesis."),
        RoleSpec("hypothesis-2", "Hypothesis Investigator 2", "Develop a materially different root-cause hypothesis."),
        RoleSpec("hypothesis-3", "Hypothesis Investigator 3", "Search for a hidden dependency or state-transition explanation."),
        RoleSpec("hypothesis-4", "Hypothesis Investigator 4", "Search for an environmental, data, or platform explanation."),
        RoleSpec("evidence-falsifier", "Evidence Falsifier", "Try to disprove the leading hypotheses using repository evidence."),
        RoleSpec("alternative-mechanism", "Alternative Mechanism Analyst", "Find an explanation that fits the evidence with fewer assumptions."),
        RoleSpec("timeline-state", "Timeline and State Analyst", "Reconstruct ordering and state changes relevant to the question."),
        RoleSpec("boundary-conditions", "Boundary Conditions Analyst", "Test hypotheses at edge cases and failure boundaries."),
    ),
    "architecture-council": (
        RoleSpec("architecture-constraints", "Constraints Analyst", "Identify hard product, technical, and operational constraints."),
        RoleSpec("architecture-api", "API Architect", "Evaluate contracts, module boundaries, and evolvability."),
        RoleSpec("architecture-data", "Data and State Architect", "Evaluate data model, invariants, persistence, and state transitions."),
        RoleSpec("architecture-operations", "Operations Architect", "Evaluate deployability, observability, recovery, and failure isolation."),
        RoleSpec("architecture-security", "Security Architect", "Evaluate trust boundaries and least-privilege design."),
        RoleSpec("architecture-performance", "Performance Architect", "Evaluate scaling behavior, hot paths, and resource cost."),
        RoleSpec("architecture-migration", "Migration Architect", "Evaluate compatibility, rollout, rollback, and transition design."),
        RoleSpec("architecture-simplicity", "Simplicity Advocate", "Challenge unnecessary machinery and search for a smaller design."),
    ),
    "security-red-blue": (
        RoleSpec("red-auth", "Red Team: Authentication", "Attack identity, authentication, and session assumptions."),
        RoleSpec("red-input", "Red Team: Input", "Attack parsing, validation, injection, and untrusted-data boundaries."),
        RoleSpec("red-boundary", "Red Team: Boundary", "Attack filesystem, process, network, and privilege boundaries."),
        RoleSpec("red-supply-chain", "Red Team: Supply Chain", "Attack dependency, configuration, and build/release assumptions."),
        RoleSpec("blue-controls", "Blue Team: Controls", "Evaluate preventive and detective controls."),
        RoleSpec("blue-observability", "Blue Team: Observability", "Evaluate auditability, alerts, incident evidence, and safe failure."),
        RoleSpec("secrets-permissions", "Secrets and Permissions Reviewer", "Inspect credential handling and least privilege."),
        RoleSpec("security-platform", "Security Platform Reviewer", "Inspect OS, sandbox, runtime, and deployment-specific exposure."),
    ),
    "test-matrix": (
        RoleSpec("test-unit", "Unit-Test Analyst", "Find missing unit-level behavioral assertions."),
        RoleSpec("test-integration", "Integration-Test Analyst", "Find missing caller, subsystem, and end-to-end coverage."),
        RoleSpec("test-error-path", "Error-Path Analyst", "Exercise failures, cleanup, cancellation, and malformed inputs."),
        RoleSpec("test-property", "Property and Invariant Analyst", "Identify invariants and generative/property tests."),
        RoleSpec("test-compatibility", "Compatibility Test Analyst", "Check API, format, migration, and backward-compatibility cases."),
        RoleSpec("test-platform", "Platform Test Analyst", "Check OS, path, encoding, locale, and environment variation."),
        RoleSpec("test-concurrency", "Concurrency Test Analyst", "Check races, ordering, retries, and lifecycle transitions."),
        RoleSpec("test-performance", "Performance Test Analyst", "Check cost regressions, scale limits, and resource pressure."),
    ),
    "repository-audit": (
        RoleSpec("audit-cli", "CLI Auditor", "Inspect command routing, arguments, exit codes, and user-visible contracts."),
        RoleSpec("audit-runtime", "Runtime Auditor", "Inspect execution, state, recovery, and error propagation."),
        RoleSpec("audit-security", "Security Auditor", "Inspect authority, trust boundaries, and fail-closed behavior."),
        RoleSpec("audit-persistence", "Persistence Auditor", "Inspect checkpoints, journals, identity, and tamper evidence."),
        RoleSpec("audit-tests", "Test Auditor", "Inspect coverage quality, fixtures, and untested contracts."),
        RoleSpec("audit-docs", "Documentation Auditor", "Inspect implementation/documentation drift and operator guidance."),
        RoleSpec("audit-packaging", "Packaging Auditor", "Inspect installation, configuration, release, and compatibility surfaces."),
        RoleSpec("audit-platform", "Platform Auditor", "Inspect Windows/Linux, path, encoding, and environment behavior."),
    ),
    "research-synthesis": (
        RoleSpec("research-primary", "Primary-Source Analyst", "Identify the strongest direct evidence and primary sources."),
        RoleSpec("research-counter", "Counterevidence Analyst", "Search for evidence that contradicts the leading conclusion."),
        RoleSpec("research-methods", "Methods Analyst", "Evaluate methodology, definitions, and measurement validity."),
        RoleSpec("research-statistics", "Quantitative Analyst", "Evaluate numerical claims, uncertainty, and statistical reasoning."),
        RoleSpec("research-chronology", "Chronology Analyst", "Reconstruct timing, causality, and version changes."),
        RoleSpec("research-assumptions", "Assumptions Analyst", "Expose hidden assumptions and alternative interpretations."),
        RoleSpec("research-replication", "Replication Analyst", "Check whether important claims can be independently reconstructed."),
        RoleSpec("research-skeptic", "Synthesis Skeptic", "Challenge the emerging synthesis and unresolved gaps."),
    ),
}


def phase_counts(agent_count: int) -> dict[str, int]:
    if not 4 <= agent_count <= 12:
        raise ValueError("agent_count must be 4..12")
    if agent_count == 4:
        return {"discovery": 4, "challenge": 0, "reproduction": 0}
    if agent_count == 5:
        return {"discovery": 4, "challenge": 1, "reproduction": 0}
    reproduction = 2 if agent_count == 12 else 1
    challenge = 2 if agent_count >= 9 else 1
    discovery = agent_count - challenge - reproduction
    if discovery < 4 or discovery > 8:
        raise AssertionError("invalid deterministic phase allocation")
    return {
        "discovery": discovery,
        "challenge": challenge,
        "reproduction": reproduction,
    }


def build_schedule(package: FleetPackage) -> dict[str, Any]:
    counts = phase_counts(package.agent_count)
    discovery_pool = DISCOVERY_POOLS[package.preset]
    roles = [
        *discovery_pool[: counts["discovery"]],
        *COMMON_CHALLENGERS[: counts["challenge"]],
        *COMMON_REPRODUCERS[: counts["reproduction"]],
    ]
    if len(roles) != package.agent_count:
        raise AssertionError("schedule did not allocate the requested fleet size")
    agents: list[dict[str, Any]] = []
    for index, role in enumerate(roles, start=1):
        agents.append(
            {
                "agent_id": f"fleet-{index:02d}",
                **role.record(),
                "route": {
                    "role": "luna",
                    "model": "gpt-5.6-luna",
                    "effort": "max",
                    "tier": "fast",
                    "sandbox": "read-only",
                    "fresh": True,
                    "attempts": 1,
                    "retry": 0,
                    "nested_agents": 0,
                },
            }
        )
    basis = {
        "schedule_version": SCHEDULE_VERSION,
        "package_digest": package.digest,
        "preset": package.preset,
        "agent_count": package.agent_count,
        "phase_counts": counts,
        "agents": agents,
        "aggregation": {
            "majority_vote": False,
            "finding_lifecycle": [
                "proposed",
                "challenged",
                "reproduced|refuted|unresolved",
                "accepted|discarded|sol-arbitration",
            ],
            "conditional_sol": True,
        },
    }
    return {**basis, "schedule_digest": canonical_digest(basis)}


def preset_contract() -> dict[str, Any]:
    return {
        "schedule_version": SCHEDULE_VERSION,
        "phases": list(PHASES),
        "presets": {
            name: [role.record() for role in roles]
            for name, roles in sorted(DISCOVERY_POOLS.items())
        },
        "challenge_roles": [role.record() for role in COMMON_CHALLENGERS],
        "reproduction_roles": [role.record() for role in COMMON_REPRODUCERS],
    }
