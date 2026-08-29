from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_contract
import fleet_escalation
import fleet_findings


def finding(*, severity: str = "P2", summary: str = "Concrete defect") -> dict:
    return {
        "category": "correctness",
        "severity": severity,
        "summary": summary,
        "evidence": ["module.py:10 demonstrates the defect"],
        "locations": ["module.py:10"],
        "confidence": "high",
    }


def discovery(agent_id: str, findings: list[dict] | None = None, unknown: list[str] | None = None) -> dict:
    findings = findings or []
    unknown = unknown or []
    verdict = "unknown" if unknown else ("findings" if findings else "accept")
    return {
        "candidate_revision": "sha256:" + "a" * 64,
        "agent_id": agent_id,
        "role_id": agent_id,
        "phase": "discovery",
        "verdict": verdict,
        "findings": findings,
        "unknown": unknown,
        "effects": [],
    }


def package(*, risk_tags: list[str] | None = None):
    raw = {
        "version": 1,
        "name": "finding-test",
        "preset": "adversarial-review",
        "agent_count": 12,
        "objective": "Review the candidate.",
        "acceptance_criteria": ["Evidence-backed result."],
        "scope": ["Candidate"],
        "exclusions": [],
        "candidate": {
            "repository_full_name": "owner/repo",
            "expected_head_sha": "b" * 40,
            "changed_files": [],
        },
        "risk_tags": risk_tags or [],
        "verification": {"required_ids": [], "commands": []},
        "limits": {
            "max_patch_bytes": 524288,
            "max_untracked_file_bytes": 131072,
            "max_candidate_bytes": 1048576,
            "max_agent_output_bytes": 524288,
            "max_agent_log_bytes": 1048576,
        },
    }
    return fleet_contract.validate_package(raw)


class FleetFindingTests(unittest.TestCase):
    def test_exact_normalized_duplicates_merge_without_becoming_votes(self) -> None:
        graph = fleet_findings.build_finding_graph(
            [
                discovery("a", [finding(summary="Concrete   defect")]),
                discovery("b", [finding(summary="concrete defect")]),
            ]
        )
        self.assertEqual(len(graph), 1)
        record = next(iter(graph.values()))
        self.assertEqual(record["proposers"], ["a", "b"])
        self.assertEqual(record["disposition"], "proposed")

    def test_reproduced_is_accepted_and_clean_refutation_is_discarded(self) -> None:
        graph = fleet_findings.build_finding_graph([discovery("a", [finding()])])
        finding_id = next(iter(graph))
        fleet_findings.apply_challenges(
            graph,
            [
                {
                    "agent_id": "challenger",
                    "assessments": [
                        {"finding_id": finding_id, "outcome": "support", "evidence": ["confirmed path"]}
                    ],
                }
            ],
        )
        fleet_findings.apply_reproductions(
            graph,
            [
                {
                    "agent_id": "reproducer",
                    "reproductions": [
                        {
                            "finding_id": finding_id,
                            "status": "reproduced",
                            "steps": ["exercise the path"],
                            "evidence": ["failure observed"],
                        }
                    ],
                }
            ],
        )
        self.assertEqual(fleet_findings.finalize_findings(graph)[0]["disposition"], "accepted")

        graph = fleet_findings.build_finding_graph([discovery("a", [finding()])])
        finding_id = next(iter(graph))
        fleet_findings.apply_challenges(
            graph,
            [
                {
                    "agent_id": "challenger",
                    "assessments": [
                        {"finding_id": finding_id, "outcome": "refute", "evidence": ["guard prevents it"]}
                    ],
                }
            ],
        )
        self.assertEqual(fleet_findings.finalize_findings(graph)[0]["disposition"], "discarded")

    def test_support_and_refutation_create_conflict(self) -> None:
        graph = fleet_findings.build_finding_graph([discovery("a", [finding()])])
        finding_id = next(iter(graph))
        fleet_findings.apply_challenges(
            graph,
            [
                {
                    "agent_id": "c1",
                    "assessments": [
                        {"finding_id": finding_id, "outcome": "support", "evidence": ["support"]}
                    ],
                },
                {
                    "agent_id": "c2",
                    "assessments": [
                        {"finding_id": finding_id, "outcome": "refute", "evidence": ["refute"]}
                    ],
                },
            ],
        )
        self.assertEqual(fleet_findings.finalize_findings(graph)[0]["disposition"], "conflict")

    def test_proposer_cannot_challenge_or_reproduce_own_finding(self) -> None:
        graph = fleet_findings.build_finding_graph([discovery("a", [finding()])])
        finding_id = next(iter(graph))
        with self.assertRaisesRegex(fleet_findings.FleetFindingError, "own finding"):
            fleet_findings.apply_challenges(
                graph,
                [
                    {
                        "agent_id": "a",
                        "assessments": [
                            {"finding_id": finding_id, "outcome": "support", "evidence": ["self"]}
                        ],
                    }
                ],
            )
        with self.assertRaisesRegex(fleet_findings.FleetFindingError, "own finding"):
            fleet_findings.apply_reproductions(
                graph,
                [
                    {
                        "agent_id": "a",
                        "reproductions": [
                            {
                                "finding_id": finding_id,
                                "status": "reproduced",
                                "steps": ["self"],
                                "evidence": ["self"],
                            }
                        ],
                    }
                ],
            )

    def test_one_reproduced_p1_overrides_eleven_clean_agents(self) -> None:
        records = [discovery(f"clean-{index}") for index in range(11)]
        graph = fleet_findings.build_finding_graph([discovery("minority", [finding(severity="P1")])])
        finding_id = next(iter(graph))
        fleet_findings.apply_reproductions(
            graph,
            [
                {
                    "agent_id": "independent",
                    "reproductions": [
                        {
                            "finding_id": finding_id,
                            "status": "reproduced",
                            "steps": ["run failing case"],
                            "evidence": ["failure"],
                        }
                    ],
                }
            ],
        )
        findings = fleet_findings.finalize_findings(graph)
        decision = fleet_escalation.decide_sol_escalation(
            package=package(),
            findings=findings,
            records=[*records, discovery("minority", [finding(severity="P1")])],
            verification_passed=True,
            candidate_stable=True,
        )
        self.assertTrue(decision["requires_sol"])
        self.assertIn("accepted-blocker", {item["code"] for item in decision["triggers"]})
        self.assertFalse(decision["majority_vote_used"])

    def test_clean_low_risk_skips_sol_but_unknown_or_high_risk_does_not(self) -> None:
        clean = fleet_escalation.decide_sol_escalation(
            package=package(),
            findings=[],
            records=[discovery("a"), discovery("b"), discovery("c"), discovery("d")],
            verification_passed=True,
            candidate_stable=True,
        )
        self.assertFalse(clean["requires_sol"])
        self.assertEqual(clean["preliminary_verdict"], "accept")

        unknown = fleet_escalation.decide_sol_escalation(
            package=package(),
            findings=[],
            records=[discovery("a", unknown=["cannot establish caller behavior"])],
            verification_passed=True,
            candidate_stable=True,
        )
        self.assertTrue(unknown["requires_sol"])

        high_risk = fleet_escalation.decide_sol_escalation(
            package=package(risk_tags=["security"]),
            findings=[],
            records=[discovery("a")],
            verification_passed=True,
            candidate_stable=True,
        )
        self.assertTrue(high_risk["requires_sol"])
        self.assertIn("high-risk-scope", {item["code"] for item in high_risk["triggers"]})


    def test_host_graph_rejects_more_than_128_unique_findings(self) -> None:
        findings = [
            finding(summary=f"unique finding {index}")
            for index in range(fleet_findings.MAX_GRAPH_FINDINGS + 1)
        ]
        with self.assertRaisesRegex(
            fleet_findings.FleetFindingError, "exceeds 128 unique findings"
        ):
            fleet_findings.build_finding_graph([discovery("a", findings)])


if __name__ == "__main__":
    unittest.main()
