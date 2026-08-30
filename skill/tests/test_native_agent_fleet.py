from __future__ import annotations

import json
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skill.installation.filesystem import payload_entries


class NativeAgentFleetContractTests(unittest.TestCase):
    def test_policy_uses_only_approved_native_sizes_and_mixes(self) -> None:
        with (ROOT / "config" / "workflow-policy.toml").open("rb") as handle:
            policy = tomllib.load(handle)
        fleet = policy["agent_fleet"]
        self.assertEqual(fleet["implementation"], "native_subagents")
        self.assertEqual(fleet["supported_sizes"], [4, 6, 8])
        self.assertEqual(fleet["default_size"], 6)
        for key in (
            "disclose_before_start",
            "visible_top_level",
            "read_only",
            "root_final_decision",
            "root_must_address_sol",
            "reproduced_severe_cannot_be_outvoted",
        ):
            self.assertTrue(fleet[key], key)
        for key in (
            "confirmation_after_disclosure",
            "nested_delegation",
            "direct_agent_messages",
            "majority_vote",
        ):
            self.assertFalse(fleet[key], key)
        self.assertEqual(fleet["fork_turns"], "none")
        self.assertEqual(fleet["unresolved_conflict"], "unknown")
        self.assertEqual(fleet["technical_failure_replacement_limit"], 1)
        expected = {
            "size_4": {
                "discovery_luna": 1,
                "challenge_luna": 1,
                "reproduction_luna": 1,
                "sol_final_review": 1,
            },
            "size_6": {
                "discovery_luna": 3,
                "challenge_luna": 1,
                "reproduction_luna": 1,
                "sol_final_review": 1,
            },
            "size_8": {
                "discovery_luna": 4,
                "challenge_luna": 1,
                "reproduction_luna": 1,
                "sol_evidence_review": 1,
                "sol_system_review": 1,
            },
        }
        for name, allocation in expected.items():
            self.assertEqual(fleet[name], allocation)
            self.assertEqual(sum(allocation.values()), int(name.removeprefix("size_")))

    def test_native_contract_covers_visibility_phases_and_sol_accountability(self) -> None:
        contract = (ROOT / "skill" / "references" / "agent-fleet.md").read_text(
            encoding="utf-8"
        )
        for token in (
            "UI-visible native subagent",
            "4 | 3 Luna + 1 Sol",
            "6 | 5 Luna + 1 Sol",
            "8 | 6 Luna + 2 Sol",
            "spawn_agent",
            "fork_turns=none",
            "F-001",
            "cannot be outvoted",
            "Root may not silently omit it",
            "report `UNKNOWN`",
            "Managed Workflow",
        ):
            self.assertIn(token, contract)

    def test_old_fleet_runtime_and_commands_are_removed(self) -> None:
        for relative in (
            "config/agent-fleet-policy.toml",
            "examples/agent-fleet-package.json",
            "skill/fleet_candidate.py",
            "skill/fleet_cli.py",
            "skill/fleet_contract.py",
            "skill/fleet_escalation.py",
            "skill/fleet_findings.py",
            "skill/fleet_integrity.py",
            "skill/fleet_presets.py",
            "skill/fleet_process.py",
            "skill/fleet_records.py",
            "skill/fleet_runtime.py",
            "skill/references/agent-fleet-usage.md",
            "skill/references/agent-fleet-v1.md",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)
        cli = (ROOT / "skill" / "cli.py").read_text(encoding="utf-8")
        for command in ("fleet-plan", "fleet-run", "fleet-status"):
            self.assertNotIn(command, cli)

    def test_retired_fleet_commands_fail_without_traceback(self) -> None:
        for command in ("fleet-plan", "fleet-run", "fleet-status"):
            completed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "skill" / "cli.py"), command],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            combined = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0, command)
            self.assertIn(command, combined)
            self.assertNotIn("Traceback", combined)

    def test_active_surfaces_do_not_advertise_package_runtime(self) -> None:
        surfaces = (
            "README.md",
            "integration/AGENTS.dynamic-workflow.md",
            "skill/SKILL.md",
            "skill/agents/openai.yaml",
            "skill/references/agent-fleet.md",
            "skill/references/cli-runner.md",
            "skill/references/operations.md",
            "skill/references/routing.md",
            "skill/references/simple-swarm.md",
            "skill/references/swarm-presets.md",
            "skill/references/work-package.md",
        )
        forbidden = (
            "fleet-plan",
            "fleet-run",
            "fleet-status",
            "agent-fleet-package.json",
            "separate package runtime",
            "独立只读 package runtime",
        )
        for relative in surfaces:
            text = (ROOT / relative).read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{relative}: {token}")

    def test_install_payload_excludes_retired_fleet_files(self) -> None:
        targets = {entry["target"] for entry in payload_entries(ROOT)}
        for target in targets:
            self.assertNotIn("/fleet_", target)
            self.assertNotIn("test_agent_fleet_", target)
        self.assertIn(
            "skills/dynamic-workflow/references/agent-fleet.md",
            targets,
        )

    def test_tabletop_evals_distinguish_deep_and_ordinary_requests(self) -> None:
        data = json.loads(
            (ROOT / "skill" / "evals" / "evals.json").read_text(
                encoding="utf-8"
            )
        )
        by_name = {item["name"]: item for item in data["evals"]}
        self.assertIn(
            "6 native, UI-visible subagents: 5 Luna and 1 Sol",
            by_name["natural-deep-audit-uses-native-agent-fleet"]["expected_output"],
        )
        self.assertIn(
            "Simple Swarm",
            by_name["ordinary-check-does-not-imply-agent-fleet"]["expected_output"],
        )
        self.assertIn(
            "unsupported exact-count conflict",
            by_name["unsupported-twelve-agent-request-is-not-silently-remapped"]["expected_output"],
        )


if __name__ == "__main__":
    unittest.main()
