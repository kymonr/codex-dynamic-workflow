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
        self.assertEqual(
            policy["runtime_version"], writer_runtime_base.WRITER_RUNTIME_VERSION
        )
        self.assertEqual(
            policy["writer_route_binding_version"],
            writer_process.WRITER_BINDING_VERSION,
        )
        self.assertTrue(policy["explicit_cli_only"])
        self.assertTrue(policy["single_active_writer_per_repository"])
        for key in (
            "auto_planner_activation",
            "workflow_ir_activation",
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
        package = self.policy["package"]
        self.assertEqual(
            set(package["allowed_actions"]), set(writer_contract.GRANTABLE_ACTIONS)
        )
        self.assertEqual(
            set(package["supported_versions"]),
            set(writer_contract.SUPPORTED_PACKAGE_VERSIONS),
        )
        self.assertEqual(
            package["max_v2_quality_context_bytes"],
            writer_contract.MAX_QUALITY_CONTEXT_BYTES,
        )
        self.assertEqual(
            set(package["v2_quality_fields"]),
            {
                "acceptance_criteria",
                "constraints",
                "non_goals",
                "behavior",
                "implementation_context",
            },
        )
        for key, value in self.policy["effects"].items():
            self.assertTrue(value, key)
        self.assertTrue(self.policy["candidate"]["bind_writer_route"])

    def test_fixed_sol_writer_and_command_policy(self) -> None:
        writer = self.policy["writer"]
        binding = writer_process.writer_binding_record()
        route = binding["route"]
        limits = binding["limits"]
        self.assertEqual(writer["selection"], binding["selection"])
        self.assertEqual(writer["role"], route["role"])
        self.assertEqual(writer["model"], route["model"])
        self.assertEqual(writer["effort"], route["effort"])
        self.assertEqual(writer["tier"], "inherit")
        self.assertIsNone(route["tier"])
        self.assertEqual(writer["package_version"], binding["package_version"])
        for key, value in limits.items():
            self.assertEqual(writer[key], value)
        self.assertTrue(writer["requires_quality_context"])
        self.assertEqual(writer["attempts"], 1)
        self.assertEqual(writer["retry"], 0)
        self.assertEqual(writer["upgrade"], "none")
        self.assertEqual(writer["sandbox"], "workspace-write")
        self.assertFalse(writer["network"])
        self.assertFalse(writer["shell_tool"])
        self.assertFalse(writer["code_mode"])
        self.assertFalse(writer["multi_agent"])
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
