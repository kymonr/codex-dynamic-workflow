from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_contract
import writer_process
import writer_runtime_base
import writer_review


class WriterPolicyConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = tomllib.loads(
            (ROOT / "config" / "worktree-writer-policy.toml").read_text(
                encoding="utf-8"
            )
        )["worktree_writer"]

    def test_runtime_and_activation_boundary(self) -> None:
        policy = self.policy
        self.assertEqual(policy["runtime_version"], writer_runtime_base.WRITER_RUNTIME_VERSION)
        self.assertTrue(policy["explicit_cli_only"])
        self.assertFalse(policy["auto_planner_activation"])
        self.assertFalse(policy["workflow_ir_activation"])
        for key in (
            "automatic_resume",
            "automatic_retry",
            "automatic_apply",
            "automatic_commit",
            "automatic_push",
            "automatic_merge",
            "automatic_release",
            "automatic_deploy",
        ):
            self.assertFalse(policy[key], key)

    def test_package_and_effect_policy(self) -> None:
        self.assertEqual(
            set(self.policy["package"]["allowed_actions"]),
            set(writer_contract.GRANTABLE_ACTIONS),
        )
        effects = self.policy["effects"]
        for key, value in effects.items():
            self.assertTrue(value, key)

    def test_writer_route_and_command_policy(self) -> None:
        policy = self.policy["writer"]
        self.assertEqual(policy["role"], writer_process.WRITER_ROUTE.role)
        self.assertEqual(policy["model"], writer_process.WRITER_ROUTE.model)
        self.assertEqual(policy["effort"], writer_process.WRITER_ROUTE.effort)
        self.assertEqual(policy["tier"], writer_process.WRITER_ROUTE.tier)
        self.assertEqual(policy["sandbox"], writer_process.WRITER_ROUTE.sandbox)
        self.assertEqual(policy["attempts"], 1)
        self.assertEqual(policy["retry"], 0)
        self.assertEqual(policy["upgrade"], "none")
        self.assertFalse(policy["network"])
        self.assertFalse(policy["shell_tool"])
        self.assertFalse(policy["code_mode"])
        self.assertFalse(policy["multi_agent"])
        command = writer_process._build_command(
            codex_prefix=["codex"],
            cwd=Path("/isolated"),
            route=writer_process.WRITER_ROUTE,
            schema_path=Path("/evidence/schema.json"),
            output_path=Path("/evidence/out.json"),
        )
        self.assertIn("features.shell_tool=false", command)
        self.assertIn("features.code_mode=false", command)
        self.assertIn("features.multi_agent=false", command)
        self.assertIn("web_search=disabled", command)
        self.assertIn("sandbox_workspace_write.network_access=false", command)

    def test_reviewer_identity_and_terminal_contract(self) -> None:
        policy = self.policy["reviewer"]
        self.assertEqual(policy["agent_type"], writer_review.REVIEWER_AGENT_TYPE)
        self.assertEqual(policy["model"], writer_process.REVIEWER_ROUTE.model)
        self.assertEqual(policy["effort"], writer_process.REVIEWER_ROUTE.effort)
        self.assertEqual(policy["sandbox"], writer_process.REVIEWER_ROUTE.sandbox)
        self.assertTrue(policy["fresh_process"])
        self.assertFalse(policy["write_authority"])
        self.assertEqual(
            set(self.policy["candidate"]["terminal_verdicts"]),
            {"ship_candidate", "fix_first", "rethink"},
        )


if __name__ == "__main__":
    unittest.main()
