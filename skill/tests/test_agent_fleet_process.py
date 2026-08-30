from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_contract
import fleet_presets
import fleet_process
import fleet_records


def package():
    raw = {
        "version": 1,
        "name": "process-test",
        "preset": "adversarial-review",
        "agent_count": 6,
        "objective": "Review the candidate.",
        "acceptance_criteria": ["Evidence is concrete."],
        "scope": ["Candidate"],
        "exclusions": [],
        "candidate": {
            "repository_full_name": "owner/repo",
            "expected_head_sha": "a" * 40,
            "changed_files": [],
        },
        "risk_tags": [],
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


def candidate():
    material = {
        "candidate_package_version": 1,
        "fleet_package_digest": "b" * 64,
        "repository_full_name": "owner/repo",
        "repository_root": "/repo",
        "head": "a" * 40,
        "tree": "c" * 40,
        "changed_files": [],
        "status": {"bytes": 0, "sha256": "d" * 64, "entries": []},
        "patch": {"bytes": 0, "sha256": "e" * 64, "content": ""},
        "untracked_files": [],
        "total_candidate_bytes": 0,
    }
    digest = fleet_contract.canonical_digest(material)
    return {
        **material,
        "candidate_revision": f"sha256:{digest}",
        "revision_basis_digest": digest,
    }


class FleetProcessTests(unittest.TestCase):
    def test_luna_and_sol_commands_disable_write_adjacent_surfaces(self) -> None:
        for route in (fleet_process.LUNA_ROUTE, fleet_process.SOL_ARBITER_ROUTE):
            with self.subTest(route=route.role):
                command = fleet_process._build_command(
                    codex_prefix=["codex"],
                    cwd=Path("/repo"),
                    route=route,
                    schema_path=Path("/evidence/schema.json"),
                    output_path=Path("/evidence/out.json"),
                )
                self.assertIn("-s", command)
                self.assertIn("read-only", command)
                self.assertIn("features.shell_tool=false", command)
                self.assertIn("features.code_mode=false", command)
                self.assertIn("features.multi_agent=false", command)
                self.assertIn("agents.enabled=false", command)
                self.assertIn("web_search=disabled", command)
                self.assertIn("approval_policy=never", command)
                self.assertNotIn("workspace-write", command)
        luna = fleet_process._build_command(
            codex_prefix=["codex"],
            cwd=Path("/repo"),
            route=fleet_process.LUNA_ROUTE,
            schema_path=Path("/evidence/schema.json"),
            output_path=Path("/evidence/out.json"),
        )
        self.assertIn("service_tier=fast", luna)
        sol = fleet_process._build_command(
            codex_prefix=["codex"],
            cwd=Path("/repo"),
            route=fleet_process.SOL_ARBITER_ROUTE,
            schema_path=Path("/evidence/schema.json"),
            output_path=Path("/evidence/out.json"),
        )
        self.assertFalse(any(item.startswith("service_tier=") for item in sol))

    def test_prompts_mark_every_embedded_surface_untrusted(self) -> None:
        pkg = package()
        schedule = fleet_presets.build_schedule(pkg)
        cand = candidate()
        discovery_agent = next(item for item in schedule["agents"] if item["phase"] == "discovery")
        challenge_agent = next(item for item in schedule["agents"] if item["phase"] == "challenge")
        reproduction_agent = next(item for item in schedule["agents"] if item["phase"] == "reproduction")
        finding = {
            "finding_id": "F-123456789abc",
            "category": "correctness",
            "severity": "P2",
            "summary": "defect",
            "evidence": ["evidence"],
            "locations": ["module.py:1"],
            "confidence": "high",
            "proposers": ["fleet-01"],
            "phase_sources": ["discovery"],
            "challenges": [],
            "reproductions": [],
            "disposition": "proposed",
        }
        prompts = [
            fleet_process.discovery_prompt(
                package=pkg,
                candidate=cand,
                verification=[],
                agent=discovery_agent,
            ),
            fleet_process.challenge_prompt(
                package=pkg,
                candidate=cand,
                verification=[],
                agent=challenge_agent,
                findings=[finding],
            ),
            fleet_process.reproduction_prompt(
                package=pkg,
                candidate=cand,
                verification=[],
                agent=reproduction_agent,
                findings=[finding],
            ),
        ]
        for prompt in prompts:
            self.assertIn("untrusted evidence", prompt)
            self.assertIn("Do not spawn", prompt)
            self.assertIn("Do not modify files", prompt)
            self.assertIn("EFFECTS must be []", prompt)
            self.assertIn(cand["candidate_revision"], prompt)

        arbiter = fleet_process.arbiter_prompt(
            package=pkg,
            candidate=cand,
            verification=[],
            findings=[{**finding, "disposition": "unresolved"}],
            decision={"requires_sol": True, "triggers": ["finding-unresolved"]},
        )
        self.assertIn("FRESH_SOL_XHIGH_ARBITRATION", arbiter)
        self.assertIn("untrusted evidence", arbiter)
        self.assertIn("surviving conflicts", arbiter)
        self.assertNotIn("luna_records", arbiter)

    def test_output_schemas_are_closed_and_revision_bound(self) -> None:
        pkg = package()
        schedule = fleet_presets.build_schedule(pkg)
        revision = candidate()["candidate_revision"]
        for phase, builder in (
            ("discovery", fleet_records.discovery_schema),
            ("challenge", fleet_records.challenge_schema),
            ("reproduction", fleet_records.reproduction_schema),
        ):
            agent = next(item for item in schedule["agents"] if item["phase"] == phase)
            kwargs = {"candidate_revision": revision, "agent": agent}
            if phase != "discovery":
                kwargs["valid_finding_ids"] = ["F-one", "F-two"]
            schema = builder(**kwargs)
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(
                schema["properties"]["candidate_revision"]["enum"], [revision]
            )
            self.assertEqual(schema["properties"]["effects"]["maxItems"], 0)
            self.assertEqual(
                schema["properties"]["effects"]["items"], {"type": "string"}
            )
            bounded_key = "findings" if phase == "discovery" else "new_findings"
            self.assertEqual(
                schema["properties"][bounded_key]["maxItems"],
                fleet_records.MAX_FINDINGS_PER_RECORD,
            )
            if phase != "discovery":
                reference_key = (
                    "assessments" if phase == "challenge" else "reproductions"
                )
                self.assertEqual(
                    schema["properties"][reference_key]["items"]["properties"]
                    ["finding_id"]["enum"],
                    ["F-one", "F-two"],
                )
        arbiter = fleet_records.arbiter_schema(
            candidate_revision=revision,
            valid_finding_ids=["F-one", "F-two"],
        )
        self.assertFalse(arbiter["additionalProperties"])
        self.assertEqual(arbiter["properties"]["effects"]["maxItems"], 0)
        self.assertEqual(
            arbiter["properties"]["effects"]["items"], {"type": "string"}
        )
        self.assertEqual(
            arbiter["properties"]["accepted_findings"]["items"]["enum"],
            ["F-one", "F-two"],
        )

    def test_challenge_and_reproduction_cover_every_assignment(self) -> None:
        pkg = package()
        schedule = fleet_presets.build_schedule(pkg)
        revision = candidate()["candidate_revision"]
        challenge = next(
            item for item in schedule["agents"] if item["phase"] == "challenge"
        )
        raw_challenge = {
            "candidate_revision": revision,
            "agent_id": challenge["agent_id"],
            "role_id": challenge["role_id"],
            "phase": "challenge",
            "assessments": [
                {
                    "finding_id": "F-one",
                    "outcome": "support",
                    "evidence": ["one finding checked"],
                }
            ],
            "new_findings": [],
            "unknown": [],
            "effects": [],
        }
        with self.assertRaisesRegex(
            fleet_records.FleetRecordError, "every assigned finding"
        ):
            fleet_records.validate_challenge_record(
                raw_challenge,
                candidate_revision=revision,
                agent=challenge,
                finding_ids=["F-one", "F-two"],
            )

        reproduction = next(
            item for item in schedule["agents"] if item["phase"] == "reproduction"
        )
        raw_reproduction = {
            "candidate_revision": revision,
            "agent_id": reproduction["agent_id"],
            "role_id": reproduction["role_id"],
            "phase": "reproduction",
            "reproductions": [
                {
                    "finding_id": "F-one",
                    "status": "refuted",
                    "steps": [],
                    "evidence": ["one finding checked"],
                }
            ],
            "new_findings": [],
            "unknown": [],
            "effects": [],
        }
        with self.assertRaisesRegex(
            fleet_records.FleetRecordError, "every assigned finding"
        ):
            fleet_records.validate_reproduction_record(
                raw_reproduction,
                candidate_revision=revision,
                agent=reproduction,
                finding_ids=["F-one", "F-two"],
            )

    def test_discovery_finding_capacity_is_enforced_by_schema_and_host(self) -> None:
        pkg = package()
        agent = next(
            item
            for item in fleet_presets.build_schedule(pkg)["agents"]
            if item["phase"] == "discovery"
        )
        revision = candidate()["candidate_revision"]
        one = {
            "category": "correctness",
            "severity": "P3",
            "summary": "bounded fixture",
            "evidence": ["module.py:1"],
            "locations": ["module.py:1"],
            "confidence": "medium",
        }
        raw = {
            "candidate_revision": revision,
            "agent_id": agent["agent_id"],
            "role_id": agent["role_id"],
            "phase": "discovery",
            "verdict": "findings",
            "findings": [dict(one, summary=f"fixture-{index}") for index in range(17)],
            "unknown": [],
            "effects": [],
        }
        with self.assertRaisesRegex(fleet_records.FleetRecordError, "bounded array"):
            fleet_records.validate_discovery_record(
                raw, candidate_revision=revision, agent=agent
            )

    def test_process_contract_has_no_retry_write_or_direct_messages(self) -> None:
        contract = fleet_process.process_contract()
        self.assertEqual(contract["attempts"], 1)
        self.assertEqual(contract["retry"], 0)
        self.assertIsNone(contract["upgrade"])
        self.assertEqual(contract["nested_agents"], 0)
        self.assertEqual(contract["observed_sandbox"], "unknown")
        self.assertFalse(contract["direct_agent_messages"])
        self.assertFalse(contract["write_authority"])


if __name__ == "__main__":
    unittest.main()
