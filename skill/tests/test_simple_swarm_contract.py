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
        self.assertNotIn("max_wait_timeouts", contract)
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

    def test_scoped_writer_keeps_path_and_explicit_route_authority(self) -> None:
        work_package = (
            ROOT / "skill" / "references" / "work-package.md"
        ).read_text(encoding="utf-8")
        for token in (
            "root-normalized absolute literal paths",
            "An unnormalizable or unmatched target is out of scope",
            "Adjacent files are excluded unless root separately assigns them",
            "Only one native writer is active",
            "Luna has writer authority only when explicitly selected by the user",
            "Grok has no writer authority",
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
            "later timeout, wait count, or silence alone never authorizes",
            "Live behavior beyond two waits is unproven",
        ):
            self.assertIn(token, contract)
        self.assertIn(
            "does **not** require a JSON authority manifest",
            work_package,
        )
        self.assertIn("Scoped native writer packet", work_package)

    def test_design_routes_by_deliverable_and_root_accepts(self) -> None:
        skill = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")
        for token in (
            "facts, constraints, current-state inspection, non-selecting organization",
            "formatting an already-decided plan",
            "create or revise design candidates, choose alternatives",
            "resolve material tradeoffs, recommend a target design",
            "Root retains adoption and final acceptance",
        ):
            self.assertIn(token, skill)

    def test_routing_table_and_uncertain_fallback_keep_design_work_on_sol(self) -> None:
        routing = (ROOT / "skill" / "references" / "routing.md").read_text(
            encoding="utf-8"
        )
        luna_row = next(
            line for line in routing.splitlines() if line.startswith("| Luna |")
        )
        sol_row = next(
            line for line in routing.splitlines() if line.startswith("| Sol |")
        )
        design_tokens = (
            "design candidates",
            "choose alternatives",
            "material tradeoffs",
            "target design",
            "design judgment",
        )
        for token in design_tokens:
            self.assertNotIn(token, luna_row)
            self.assertIn(token, sol_row)

        fallback = routing.split("If the route is genuinely uncertain:", 1)[1]
        precedence = routing.split("## Precedence", 1)[1].split(
            "Role files under the active", 1
        )[0]
        self.assertNotIn("Luna for ordinary read-only delegated work", precedence)
        self.assertIn("Sol for design candidates and judgments", precedence)
        self.assertIn("choose Sol for creating or revising design candidates", fallback)
        self.assertIn("otherwise choose Luna for facts, constraints", fallback)
        self.assertIn("only when the user explicitly selected it", fallback)

    def test_tabletop_evals_cover_mode_boundaries(self) -> None:
        data = json.loads(
            (ROOT / "skill" / "evals" / "evals.json").read_text(
                encoding="utf-8"
            )
        )
        evals = {item["name"]: item["expected_output"] for item in data["evals"]}
        for name in (
            "event-driven-native-coordination",
            "healthy-long-running-child-is-not-interrupted",
            "natural-deep-audit-uses-native-agent-fleet",
            "root-does-not-duplicate-active-child",
            "managed-workflow-is-explicit",
            "writer-workflow-is-explicit",
            "wide-child-package-is-resplit",
            "worktree-writer-route-is-fixed-sol-high",
            "explicit-eight-agent-adversarial-review-uses-fleet",
            "ordinary-check-does-not-imply-agent-fleet",
            "fleet-roles-are-distinct",
            "unsupported-twelve-agent-request-is-not-silently-remapped",
            "minority-reproduced-blocker-defeats-majority",
            "clean-low-risk-fleet-still-uses-sol",
            "design-routing-by-deliverable",
        ):
            self.assertIn(name, evals)
        self.assertIn(
            "Later timeout, wait count, or silence alone never authorizes",
            evals["event-driven-native-coordination"],
        )
        self.assertIn(
            "Keep the healthy child in Simple Swarm",
            evals["healthy-long-running-child-is-not-interrupted"],
        )
        self.assertIn("Route B to Sol", evals["design-routing-by-deliverable"])


if __name__ == "__main__":
    unittest.main()
