from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SimpleSwarmContractTests(unittest.TestCase):
    def test_default_policy_is_lightweight_and_bounded(self) -> None:
        with (ROOT / "config" / "workflow-policy.toml").open("rb") as handle:
            policy = tomllib.load(handle)
        self.assertEqual(policy["default_shape"], "simple_swarm")
        contract = policy["simple_swarm"]
        self.assertEqual(contract["implicit_min_ready_branches"], 2)
        self.assertEqual(contract["default_max_children"], 6)
        self.assertEqual(contract["hard_max_children"], 8)
        self.assertEqual(contract["typical_max_primary_files_per_branch"], 3)
        self.assertEqual(contract["max_objectives_per_branch"], 1)
        self.assertEqual(contract["max_wait_timeouts"], 2)
        self.assertTrue(contract["default_read_only"])
        self.assertFalse(contract["nested_delegation"])
        self.assertFalse(contract["root_duplicates_active_scope"])
        self.assertFalse(contract["managed_workflow_auto_trigger"])
        self.assertFalse(contract["worktree_writer_auto_trigger"])

    def test_skill_routes_advanced_modes_only_when_needed(self) -> None:
        skill = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")
        for token in (
            "Multi-agent first",
            "Mode: simple-swarm",
            "Implicit activation requires at least two useful child branches",
            "The root must not duplicate an active child",
            "Managed Workflow",
            "Writer Workflow",
        ):
            self.assertIn(token, skill)
        self.assertIn(
            "[references/simple-swarm.md](references/simple-swarm.md)",
            skill,
        )

    def test_default_prompt_does_not_over_split_one_branch(self) -> None:
        prompt = (ROOT / "skill" / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "When at least two useful non-overlapping branches are ready",
            prompt,
        )
        self.assertIn(
            "When only one bounded branch is useful",
            prompt,
        )
        self.assertIn("dispatch one child only if", prompt)
        self.assertIn("keep that single branch at root", prompt)
        self.assertNotIn(
            "Simple Swarm as the default: split ordinary work into 2–6",
            prompt,
        )

    def test_scoped_writer_keeps_path_and_isolation_authority(self) -> None:
        work_package = (
            ROOT / "skill" / "references" / "work-package.md"
        ).read_text(encoding="utf-8")
        for token in (
            "root-normalized absolute literal paths",
            "An unnormalizable or unmatched target is out of scope",
            "Adjacent files are excluded unless root separately assigns them",
            "disjoint closed `owned_targets`",
            "including temporary artifacts",
            "separate worktrees",
            "reads back actual effects",
        ):
            self.assertIn(token, work_package)

    def test_simple_swarm_packet_stays_compact(self) -> None:
        contract = (
            ROOT / "skill" / "references" / "simple-swarm.md"
        ).read_text(encoding="utf-8")
        work_package = (
            ROOT / "skill" / "references" / "work-package.md"
        ).read_text(encoding="utf-8")
        for token in (
            "Default child count is 2–6",
            "one module or 1–3 primary files",
            "The root must not repeat an active child",
            "Simple Swarm forbids nested delegation",
            "After the first timeout",
        ):
            self.assertIn(token, contract)
        self.assertIn(
            "does **not** require a JSON authority manifest",
            work_package,
        )
        self.assertIn("Scoped native writer packet", work_package)

    def test_tabletop_evals_cover_mode_boundaries(self) -> None:
        data = json.loads(
            (ROOT / "skill" / "evals" / "evals.json").read_text(
                encoding="utf-8"
            )
        )
        names = {item["name"] for item in data["evals"]}
        for name in (
            "broad-audit-splits-into-narrow-simple-swarm",
            "root-does-not-duplicate-active-child",
            "managed-workflow-is-explicit",
            "writer-workflow-is-explicit",
            "wide-child-package-is-resplit",
            "worktree-writer-route-is-fixed-sol-high",
            "explicit-eight-agent-adversarial-review-uses-fleet",
            "ordinary-broad-audit-does-not-imply-agent-fleet",
            "fleet-roles-are-distinct",
            "twelve-agent-test-matrix-is-flat-and-host-mediated",
            "minority-reproduced-blocker-defeats-majority",
            "clean-low-risk-fleet-skips-sol",
        ):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
