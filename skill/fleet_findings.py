"""Host-owned finding graph for Agent Fleet v1.

Findings are not counted as votes. Each claim is challenged and, when capacity
exists, independently reproduced or refuted before final aggregation.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

try:
    from skill.fleet_contract import canonical_digest
except ModuleNotFoundError as exc:
    if exc.name != "skill":
        raise
    from fleet_contract import canonical_digest

SEVERITY_ORDER = {"P1": 0, "P2": 1, "P3": 2}
MAX_GRAPH_FINDINGS = 128


class FleetFindingError(RuntimeError):
    """The host finding graph is inconsistent."""


def _normalized_summary(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _dedupe_basis(finding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "category": finding["category"],
        "summary": _normalized_summary(finding["summary"]),
        "locations": sorted({item.casefold() for item in finding["locations"]}),
    }


def _finding_id(finding: Mapping[str, Any]) -> str:
    return f"F-{canonical_digest(_dedupe_basis(finding))[:12]}"


def _merge_finding(
    graph: dict[str, dict[str, Any]],
    finding: Mapping[str, Any],
    *,
    agent_id: str,
    phase: str,
) -> str:
    finding_id = _finding_id(finding)
    existing = graph.get(finding_id)
    if existing is None:
        if len(graph) >= MAX_GRAPH_FINDINGS:
            raise FleetFindingError(
                f"finding graph exceeds {MAX_GRAPH_FINDINGS} unique findings"
            )
        graph[finding_id] = {
            "finding_id": finding_id,
            "category": finding["category"],
            "severity": finding["severity"],
            "summary": finding["summary"],
            "evidence": list(dict.fromkeys(finding["evidence"])),
            "locations": list(dict.fromkeys(finding["locations"])),
            "confidence": finding["confidence"],
            "proposers": [agent_id],
            "phase_sources": [phase],
            "challenges": [],
            "reproductions": [],
            "disposition": "proposed",
        }
        return finding_id
    if _dedupe_basis(existing) != _dedupe_basis(finding):
        raise FleetFindingError(f"finding digest collision for {finding_id}")
    if SEVERITY_ORDER[finding["severity"]] < SEVERITY_ORDER[existing["severity"]]:
        existing["severity"] = finding["severity"]
    existing["evidence"] = list(
        dict.fromkeys([*existing["evidence"], *finding["evidence"]])
    )
    existing["locations"] = list(
        dict.fromkeys([*existing["locations"], *finding["locations"]])
    )
    if agent_id not in existing["proposers"]:
        existing["proposers"].append(agent_id)
    if phase not in existing["phase_sources"]:
        existing["phase_sources"].append(phase)
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    if confidence_rank[finding["confidence"]] > confidence_rank[existing["confidence"]]:
        existing["confidence"] = finding["confidence"]
    return finding_id


def build_finding_graph(
    discovery_records: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    graph: dict[str, dict[str, Any]] = {}
    for record in discovery_records:
        for finding in record["findings"]:
            _merge_finding(
                graph,
                finding,
                agent_id=record["agent_id"],
                phase="discovery",
            )
    return graph


def add_new_findings(
    graph: dict[str, dict[str, Any]],
    records: Sequence[Mapping[str, Any]],
    *,
    phase: str,
) -> list[str]:
    added: list[str] = []
    for record in records:
        for finding in record["new_findings"]:
            finding_id = _merge_finding(
                graph,
                finding,
                agent_id=record["agent_id"],
                phase=phase,
            )
            if finding_id not in added:
                added.append(finding_id)
    return added


def apply_challenges(
    graph: dict[str, dict[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> None:
    for record in records:
        for assessment in record["assessments"]:
            finding_id = assessment["finding_id"]
            if finding_id not in graph:
                raise FleetFindingError(f"challenge references missing finding {finding_id}")
            if record["agent_id"] in graph[finding_id]["proposers"]:
                raise FleetFindingError(
                    f"finding proposer cannot challenge its own finding: {finding_id}"
                )
            graph[finding_id]["challenges"].append(
                {
                    "agent_id": record["agent_id"],
                    "outcome": assessment["outcome"],
                    "evidence": list(assessment["evidence"]),
                }
            )
            graph[finding_id]["disposition"] = "challenged"


def apply_reproductions(
    graph: dict[str, dict[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> None:
    for record in records:
        for reproduction in record["reproductions"]:
            finding_id = reproduction["finding_id"]
            if finding_id not in graph:
                raise FleetFindingError(
                    f"reproduction references missing finding {finding_id}"
                )
            if record["agent_id"] in graph[finding_id]["proposers"]:
                raise FleetFindingError(
                    f"finding proposer cannot reproduce its own finding: {finding_id}"
                )
            graph[finding_id]["reproductions"].append(
                {
                    "agent_id": record["agent_id"],
                    "status": reproduction["status"],
                    "steps": list(reproduction["steps"]),
                    "evidence": list(reproduction["evidence"]),
                }
            )


def finalize_findings(
    graph: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for finding_id, source in graph.items():
        finding = deepcopy(dict(source))
        challenge_outcomes = [item["outcome"] for item in finding["challenges"]]
        reproduction_statuses = [item["status"] for item in finding["reproductions"]]
        support = challenge_outcomes.count("support")
        refute = challenge_outcomes.count("refute")
        challenge_unknown = challenge_outcomes.count("unresolved")
        reproduced = reproduction_statuses.count("reproduced")
        reproduction_refuted = reproduction_statuses.count("refuted")
        reproduction_unknown = reproduction_statuses.count("inconclusive")

        conflict = (
            (support > 0 and refute > 0)
            or (reproduced > 0 and (refute > 0 or reproduction_refuted > 0))
        )
        if conflict:
            disposition = "conflict"
        elif reproduced > 0:
            disposition = "accepted"
        elif (
            (refute > 0 or reproduction_refuted > 0)
            and support == 0
            and reproduced == 0
            and challenge_unknown == 0
            and reproduction_unknown == 0
        ):
            disposition = "discarded"
        else:
            disposition = "unresolved"
        finding["disposition"] = disposition
        finding["assessment"] = {
            "support": support,
            "refute": refute,
            "challenge_unresolved": challenge_unknown,
            "reproduced": reproduced,
            "reproduction_refuted": reproduction_refuted,
            "reproduction_inconclusive": reproduction_unknown,
            "conflict": conflict,
        }
        result.append(finding)
    result.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["finding_id"]))
    return result


def finding_ids(graph: Mapping[str, Any]) -> list[str]:
    return sorted(graph)


def assign_findings(
    finding_ids_value: Sequence[str],
    agent_ids: Sequence[str],
) -> dict[str, list[str]]:
    """Assign every finding to every independent challenger/reproducer.

    Fleet size is bounded at 12 and finding count is bounded at 128, so this
    intentional overlap is small and improves adversarial coverage. It is not a
    vote: all records feed one claim lifecycle.
    """

    return {agent_id: list(finding_ids_value) for agent_id in agent_ids}


def graph_contract() -> dict[str, Any]:
    return {
        "dedupe": "exact-normalized-category-summary-locations",
        "majority_vote": False,
        "proposer_may_self_challenge": False,
        "proposer_may_self_reproduce": False,
        "dispositions": ["accepted", "discarded", "unresolved", "conflict"],
    }
