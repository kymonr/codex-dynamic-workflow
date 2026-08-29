from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_contract


class FleetDocumentationTests(unittest.TestCase):
    def test_public_surfaces_define_agent_fleet_boundary(self) -> None:
        surfaces = {
            "README.md": ["## Agent Fleet v1", "fleet-plan", "不采用多数投票"],
            "skill/SKILL.md": ["## Agent Fleet", "fleet-run", "fresh Sol/xhigh"],
            "skill/references/routing.md": [
                "## Agent Fleet boundary",
                "ordinary audit with 2–6 useful non-overlapping questions remains Simple Swarm",
                "cannot be outvoted",
            ],
            "skill/references/simple-swarm.md": ["Agent Fleet", "4–12"],
            "skill/references/work-package.md": ["## Agent Fleet packet", "closed JSON package"],
            "integration/AGENTS.dynamic-workflow.md": ["Agent Fleet v1", "finding graph"],
        }
        for relative, tokens in surfaces.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            for token in tokens:
                with self.subTest(relative=relative, token=token):
                    self.assertIn(token, text)

    def test_contract_and_usage_docs_cover_finding_lifecycle(self) -> None:
        contract = (
            ROOT / "skill" / "references" / "agent-fleet-v1.md"
        ).read_text(encoding="utf-8")
        usage = (
            ROOT / "skill" / "references" / "agent-fleet-usage.md"
        ).read_text(encoding="utf-8")
        for token in (
            "proposed",
            "challenged",
            "reproduced | refuted | unresolved",
            "accepted | discarded | conflict | unresolved",
            "一个可复现的 P1",
            "fresh Sol/xhigh",
            "不按多数票",
            "observed_sandbox=unknown",
        ):
            self.assertIn(token, contract)
        for token in (
            "fleet-plan",
            "fleet-run",
            "fleet-status",
            "accepted_with_notes",
            "attention_required",
        ):
            self.assertIn(token, usage)

    def test_example_is_a_valid_six_agent_package(self) -> None:
        raw = json.loads(
            (ROOT / "examples" / "agent-fleet-package.json").read_text(
                encoding="utf-8"
            )
        )
        package = fleet_contract.validate_package(raw)
        self.assertEqual(package.agent_count, 6)
        self.assertEqual(package.preset, "adversarial-review")
        self.assertIn("integrity", package.risk_tags)

    def test_tabletop_evals_cover_fleet_selection_and_no_voting(self) -> None:
        data = json.loads(
            (ROOT / "skill" / "evals" / "evals.json").read_text(
                encoding="utf-8"
            )
        )
        names = {item["name"] for item in data["evals"]}
        for name in (
            "explicit-twelve-agent-adversarial-review",
            "ordinary-four-branch-audit-stays-simple-swarm",
            "fleet-roles-are-distinct",
            "minority-reproduced-blocker-defeats-majority",
            "clean-low-risk-fleet-skips-sol",
        ):
            self.assertIn(name, names)

    def test_agent_fleet_has_one_package_runtime_surface(self) -> None:
        self.assertFalse((ROOT / "skill" / "agent_fleet.py").exists())
        cli = (ROOT / "skill" / "cli.py").read_text(encoding="utf-8")
        for command in ("fleet-plan", "fleet-run", "fleet-status"):
            self.assertIn(command, cli)
        for command in ("fleet-list", "fleet-ir"):
            self.assertNotIn(command, cli)

        workflow_ir = (
            ROOT / "skill" / "runtime" / "workflow_ir.py"
        ).read_text(encoding="utf-8")
        control_flow = (
            ROOT / "skill" / "runtime" / "control_flow.py"
        ).read_text(encoding="utf-8")
        workflow_policy = (
            ROOT / "config" / "workflow-policy.toml"
        ).read_text(encoding="utf-8")
        for surface in (workflow_ir, control_flow, workflow_policy):
            self.assertNotIn("fleet_aggregate", surface)
        self.assertTrue(
            (ROOT / "config" / "agent-fleet-policy.toml").is_file()
        )

    def test_import_fallbacks_only_handle_a_missing_skill_package(self) -> None:
        for relative in (
            "fleet_candidate.py",
            "fleet_cli.py",
            "fleet_escalation.py",
            "fleet_findings.py",
            "fleet_integrity.py",
            "fleet_presets.py",
            "fleet_process.py",
            "fleet_runtime.py",
        ):
            text = (SKILL / relative).read_text(encoding="utf-8")
            self.assertNotIn("except ModuleNotFoundError:\n", text, relative)
            self.assertIn("except ModuleNotFoundError as exc:", text, relative)
            self.assertIn('if exc.name != "skill":', text, relative)

    def test_portable_cli_exposes_only_plan_run_and_status(self) -> None:
        text = (ROOT / "skill" / "cli.py").read_text(encoding="utf-8")
        for command in ("fleet-plan", "fleet-run", "fleet-status"):
            self.assertIn(command, text)
        self.assertNotIn("fleet-message", text)
        self.assertNotIn("fleet-retry", text)


if __name__ == "__main__":
    unittest.main()
