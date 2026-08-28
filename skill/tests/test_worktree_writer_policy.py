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
            policy["default_writer_profile"], writer_process.DEFAULT_WRITER_PROFILE
        )
        self.assertTrue(policy["explicit_cli_only"])
        self.assertTrue(policy["single_active_writer_per_repository"])
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
        self.assertEqual(package["v1_profile_compatibility"], ["bounded-luna"])
        for key, value in self.policy["effects"].items():
            self.assertTrue(value, key)
        self.assertTrue(self.policy["candidate"]["bind_writer_profile"])

    def test_writer_profiles_and_command_policy(self) -> None:
        common = self.policy["writer"]
        self.assertEqual(common["attempts"], 1)
        self.assertEqual(common["retry"], 0)
        self.assertEqual(common["upgrade"], "none")
        self.assertEqual(common["sandbox"], "workspace-write")
        self.assertFalse(common["network"])
        self.assertFalse(common["shell_tool"])
        self.assertFalse(common["code_mode"])
        self.assertFalse(common["multi_agent"])

        policy_profiles = self.policy["writer_profiles"]
        self.assertEqual(set(policy_profiles), set(writer_process.WRITER_PROFILES))
        for profile_id, runtime_profile in writer_process.WRITER_PROFILES.items():
            policy = policy_profiles[profile_id]
            self.assertEqual(policy["role"], runtime_profile.route.role)
            self.assertEqual(policy["model"], runtime_profile.route.model)
            self.assertEqual(policy["effort"], runtime_profile.route.effort)
            self.assertEqual(policy.get("tier"), runtime_profile.route.tier)
            self.assertEqual(
                set(policy["accepted_package_versions"]),
                set(runtime_profile.package_versions),
            )
            self.assertEqual(
                policy["max_owned_targets"], runtime_profile.max_owned_targets
            )
            self.assertEqual(
                policy["max_changed_files"], runtime_profile.max_changed_files
            )
            self.assertEqual(
                policy["max_patch_bytes"], runtime_profile.max_patch_bytes
            )
            self.assertEqual(
                policy["max_created_file_bytes"],
                runtime_profile.max_created_file_bytes,
            )
            self.assertEqual(
                policy["max_total_candidate_bytes"],
                runtime_profile.max_total_candidate_bytes,
            )
            self.assertEqual(
                policy["requires_quality_context"],
                runtime_profile.requires_quality_context,
            )
            command = writer_process._build_command(
                codex_prefix=["codex"],
                cwd=Path("/isolated"),
                route=runtime_profile.route,
                schema_path=Path("/evidence/schema.json"),
                output_path=Path("/evidence/out.json"),
            )
            self.assertIn("features.shell_tool=false", command)
            self.assertIn("features.code_mode=false", command)
            self.assertIn("features.multi_agent=false", command)
            self.assertIn("web_search=disabled", command)
            self.assertIn(
                "sandbox_workspace_write.network_access=false", command
            )

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
