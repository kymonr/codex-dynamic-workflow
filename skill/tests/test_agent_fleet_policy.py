from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_contract
import fleet_escalation
import fleet_presets
import fleet_process
import fleet_runtime


class FleetPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = tomllib.loads(
            (ROOT / "config" / "agent-fleet-policy.toml").read_text(
                encoding="utf-8"
            )
        )["agent_fleet"]

    def test_runtime_size_and_effect_boundary(self) -> None:
        policy = self.policy
        self.assertEqual(policy["runtime_version"], fleet_runtime.FLEET_RUNTIME_VERSION)
        self.assertEqual(policy["minimum_agents"], fleet_contract.MIN_AGENTS)
        self.assertEqual(policy["default_agents"], fleet_contract.DEFAULT_AGENTS)
        self.assertEqual(policy["maximum_agents"], fleet_contract.MAX_AGENTS)
        self.assertTrue(policy["explicit_or_advanced_only"])
        for key in (
            "direct_agent_messages",
            "majority_vote",
            "automatic_retry",
            "automatic_write",
            "automatic_commit",
            "automatic_push",
            "automatic_merge",
            "automatic_release",
            "automatic_deploy",
        ):
            self.assertFalse(policy[key], key)

    def test_package_presets_and_risk_tags_match_runtime(self) -> None:
        package = self.policy["package"]
        self.assertEqual(package["version"], fleet_contract.FLEET_PACKAGE_VERSION)
        self.assertTrue(package["closed_schema"])
        self.assertFalse(package["model_selectable"])
        self.assertEqual(set(package["risk_tags"]), set(fleet_contract.RISK_TAGS))
        self.assertEqual(
            set(self.policy["presets"]["values"]), set(fleet_contract.PRESETS)
        )
        self.assertEqual(
            set(self.policy["escalation"]["mandatory_risk_tags"]),
            set(fleet_escalation.MANDATORY_SOL_RISK_TAGS),
        )

    def test_fixed_luna_and_conditional_sol_routes(self) -> None:
        luna = self.policy["luna"]
        self.assertEqual(luna["role"], fleet_process.LUNA_ROUTE.role)
        self.assertEqual(luna["model"], fleet_process.LUNA_ROUTE.model)
        self.assertEqual(luna["effort"], fleet_process.LUNA_ROUTE.effort)
        self.assertEqual(luna["tier"], fleet_process.LUNA_ROUTE.tier)
        self.assertEqual(luna["sandbox"], fleet_process.LUNA_ROUTE.sandbox)
        self.assertTrue(luna["fresh"])
        self.assertEqual(luna["attempts"], 1)
        self.assertEqual(luna["retry"], 0)
        self.assertEqual(luna["nested_agents"], 0)
        self.assertFalse(luna["network"])
        self.assertFalse(luna["shell_tool"])
        self.assertFalse(luna["code_mode"])

        sol = self.policy["sol_arbiter"]
        self.assertEqual(sol["role"], fleet_process.SOL_ARBITER_ROUTE.role)
        self.assertEqual(sol["model"], fleet_process.SOL_ARBITER_ROUTE.model)
        self.assertEqual(sol["effort"], fleet_process.SOL_ARBITER_ROUTE.effort)
        self.assertEqual(sol["tier"], "inherit")
        self.assertEqual(sol["sandbox"], fleet_process.SOL_ARBITER_ROUTE.sandbox)
        self.assertTrue(sol["fresh"])
        self.assertTrue(sol["conditional"])
        self.assertFalse(sol["write_authority"])

    def test_phase_policy_matches_all_supported_sizes(self) -> None:
        phases = self.policy["phases"]
        self.assertEqual(
            phases["order"],
            [
                "discovery",
                "challenge",
                "reproduction",
                "host-aggregation",
                "conditional-sol",
            ],
        )
        self.assertFalse(phases["proposer_may_self_challenge"])
        self.assertFalse(phases["proposer_may_self_reproduce"])
        for count in range(fleet_contract.MIN_AGENTS, fleet_contract.MAX_AGENTS + 1):
            allocation = fleet_presets.phase_counts(count)
            self.assertEqual(sum(allocation.values()), count)
            self.assertGreaterEqual(allocation["discovery"], 4)
            self.assertLessEqual(allocation["discovery"], 8)
            self.assertLessEqual(allocation["challenge"], 2)
            self.assertLessEqual(allocation["reproduction"], 2)


if __name__ == "__main__":
    unittest.main()
