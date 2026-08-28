from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import install_cli
import installation
from installation import planner as install_planner
import cli
from installation import InstallManagerError
from platform_paths import default_codex_home


class InstallManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.codex = self.root / "codex"
        self.state = self.root / "state"
        (self.source / "skill" / "references").mkdir(parents=True)
        (self.source / "skill" / "__pycache__").mkdir()
        (self.source / "config" / "agents").mkdir(parents=True)
        (self.source / "integration").mkdir()
        (self.source / "skill" / "SKILL.md").write_text("skill-v1\n", encoding="utf-8")
        (self.source / "skill" / "cli.py").write_text("print('v1')\n", encoding="utf-8")
        (self.source / "skill" / "references" / "routing.md").write_text(
            "routing-v1\n", encoding="utf-8"
        )
        (self.source / "skill" / "__pycache__" / "cli.pyc").write_bytes(b"ignored")
        (self.source / "config" / "agents" / "luna.toml").write_text(
            'name = "luna"\n', encoding="utf-8"
        )
        (self.source / "config" / "agents" / "grok_writer.toml.disabled").write_text(
            'name = "disabled"\n', encoding="utf-8"
        )
        (self.source / "integration" / "AGENTS.dynamic-workflow.md").write_text(
            "merge me\n", encoding="utf-8"
        )
        self.git_identity = {"commit": "a" * 40, "dirty": False}
        self.git_patch = mock.patch.object(
            install_planner, "git_identity", return_value=self.git_identity
        )
        self.git_patch.start()

    def tearDown(self) -> None:
        self.git_patch.stop()
        self.temp.cleanup()

    def plan(self) -> dict:
        return installation.plan_install(
            self.source,
            codex_home=self.codex,
            state_root=self.state,
        )

    def apply(self) -> dict:
        plan = self.plan()
        return installation.apply_install(
            self.source,
            expected_plan_digest=plan["plan_digest"],
            ack_install=True,
            codex_home=self.codex,
            state_root=self.state,
        )

    def test_plan_is_zero_write_and_excludes_disabled_or_cache_files(self) -> None:
        result = self.plan()
        self.assertTrue(result["ready"])
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["writes"], [])
        self.assertFalse(self.codex.exists())
        self.assertFalse(self.state.exists())
        targets = {entry["target"] for entry in result["managed_files"]}
        self.assertIn("skills/dynamic-workflow/SKILL.md", targets)
        self.assertIn("skills/dynamic-workflow/references/routing.md", targets)
        self.assertIn("agents/luna.toml", targets)
        self.assertNotIn("agents/grok_writer.toml.disabled", targets)
        self.assertFalse(any("__pycache__" in target for target in targets))
        self.assertTrue(result["manual_integration"]["required"])

    def test_apply_publishes_manifest_and_status_is_clean(self) -> None:
        result = self.apply()
        self.assertEqual(result["state"], "applied")
        self.assertEqual(
            (self.codex / "skills" / "dynamic-workflow" / "SKILL.md").read_text(),
            "skill-v1\n",
        )
        self.assertEqual(
            (self.codex / "agents" / "luna.toml").read_text(),
            'name = "luna"\n',
        )
        self.assertFalse((self.codex / "agents" / "grok_writer.toml.disabled").exists())
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "clean")
        self.assertEqual(status["install_id"], result["install_id"])
        self.assertEqual(status["source_commit"], "a" * 40)
        self.assertFalse(status["source_dirty"])
        self.assertEqual(status["drift"], [])

    def test_apply_requires_ack_and_exact_fresh_plan(self) -> None:
        plan = self.plan()
        with self.assertRaisesRegex(InstallManagerError, "requires --ack-install"):
            installation.apply_install(
                self.source,
                expected_plan_digest=plan["plan_digest"],
                ack_install=False,
                codex_home=self.codex,
                state_root=self.state,
            )
        (self.source / "skill" / "SKILL.md").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(InstallManagerError, "plan changed"):
            installation.apply_install(
                self.source,
                expected_plan_digest=plan["plan_digest"],
                ack_install=True,
                codex_home=self.codex,
                state_root=self.state,
            )

    def test_managed_drift_blocks_reinstall_and_rollback(self) -> None:
        installed = self.apply()
        target = self.codex / "skills" / "dynamic-workflow" / "SKILL.md"
        target.write_text("manual edit\n", encoding="utf-8")
        plan = self.plan()
        self.assertFalse(plan["ready"])
        self.assertIn("managed_target_drift", {item["code"] for item in plan["blocked"]})
        with self.assertRaisesRegex(InstallManagerError, "not clean"):
            installation.rollback_install(
                expected_install_id=installed["install_id"],
                ack_rollback=True,
                codex_home=self.codex,
                state_root=self.state,
            )

    def test_rollback_restores_preexisting_files_and_removes_created_files(self) -> None:
        old_skill = self.codex / "skills" / "dynamic-workflow" / "SKILL.md"
        old_agent = self.codex / "agents" / "luna.toml"
        old_skill.parent.mkdir(parents=True)
        old_agent.parent.mkdir(parents=True)
        old_skill.write_text("old-skill\n", encoding="utf-8")
        old_agent.write_text("old-agent\n", encoding="utf-8")
        installed = self.apply()
        created = self.codex / "skills" / "dynamic-workflow" / "cli.py"
        self.assertTrue(created.exists())
        result = installation.rollback_install(
            expected_install_id=installed["install_id"],
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(result["state"], "rolled_back")
        self.assertIsNone(result["active_install_id"])
        self.assertEqual(old_skill.read_text(), "old-skill\n")
        self.assertEqual(old_agent.read_text(), "old-agent\n")
        self.assertFalse(created.exists())
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "not_installed")

    def test_second_install_deletes_stale_file_and_rollback_restores_first(self) -> None:
        extra_source = self.source / "skill" / "legacy.py"
        extra_source.write_text("legacy\n", encoding="utf-8")
        first = self.apply()
        extra_target = self.codex / "skills" / "dynamic-workflow" / "legacy.py"
        self.assertTrue(extra_target.exists())

        extra_source.unlink()
        (self.source / "skill" / "SKILL.md").write_text("skill-v2\n", encoding="utf-8")
        second = self.apply()
        self.assertFalse(extra_target.exists())
        self.assertNotEqual(first["install_id"], second["install_id"])

        rollback = installation.rollback_install(
            expected_install_id=second["install_id"],
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(rollback["active_install_id"], first["install_id"])
        self.assertTrue(extra_target.exists())
        self.assertEqual(
            (self.codex / "skills" / "dynamic-workflow" / "SKILL.md").read_text(),
            "skill-v1\n",
        )
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "clean")
        self.assertEqual(status["install_id"], first["install_id"])

    def test_prepared_history_record_is_accepted_when_manifest_is_active(self) -> None:
        installed = self.apply()
        record_path = Path(installed["history_record"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["state"] = "prepared"
        record["applied_at"] = None
        record_path.write_text(json.dumps(record), encoding="utf-8")
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "clean")
        self.assertEqual(status["history_state"], "prepared")
        rolled_back = installation.rollback_install(
            expected_install_id=installed["install_id"],
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(rolled_back["state"], "rolled_back")

    def test_rollback_resumes_from_a_partially_restored_record(self) -> None:
        old_skill = self.codex / "skills" / "dynamic-workflow" / "SKILL.md"
        old_skill.parent.mkdir(parents=True)
        old_skill.write_text("old-skill\n", encoding="utf-8")
        installed = self.apply()
        record_path = Path(installed["history_record"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        skill_change = next(
            change
            for change in record["changes"]
            if change["target"] == "skills/dynamic-workflow/SKILL.md"
        )
        backup = record_path.parent / skill_change["before"]["backup"]
        old_skill.write_bytes(backup.read_bytes())
        record["state"] = "rolling_back"
        record_path.write_text(json.dumps(record), encoding="utf-8")

        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "rollback_incomplete")
        rolled_back = installation.rollback_install(
            expected_install_id=installed["install_id"],
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(rolled_back["state"], "rolled_back")
        self.assertEqual(old_skill.read_text(), "old-skill\n")
        self.assertFalse(
            (self.codex / "skills" / "dynamic-workflow" / "cli.py").exists()
        )

    def test_status_reports_unmanaged_skill_files_without_treating_them_as_drift(self) -> None:
        self.apply()
        unmanaged = self.codex / "skills" / "dynamic-workflow" / "notes.local"
        unmanaged.write_text("personal\n", encoding="utf-8")
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "clean_with_unmanaged_files")
        self.assertEqual(
            status["unmanaged_skill_files"],
            ["skills/dynamic-workflow/notes.local"],
        )
        self.assertEqual(status["drift"], [])

    def test_default_codex_home_uses_environment_then_home_fallback(self) -> None:
        self.assertEqual(
            default_codex_home({"CODEX_HOME": "~/custom"}, home=self.root),
            Path("~/custom").expanduser(),
        )
        self.assertEqual(default_codex_home({}, home=self.root), self.root / ".codex")


class InstallCliTests(unittest.TestCase):
    def test_cli_plan_is_json_and_routes_arguments(self) -> None:
        expected = {"operation": "install-plan", "writes": [], "model_calls": 0}
        output = io.StringIO()
        with mock.patch.object(install_cli, "plan_install", return_value=expected) as routed, contextlib.redirect_stdout(output):
            code = install_cli.main(
                [
                    "install-plan",
                    "--source-root",
                    "source",
                    "--codex-home",
                    "codex",
                    "--state-root",
                    "state",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), expected)
        routed.assert_called_once_with("source", codex_home="codex", state_root="state")

    def test_portable_cli_routes_install_commands(self) -> None:
        with mock.patch.object(install_cli, "main", return_value=23) as routed:
            self.assertEqual(
                cli.main(["install-status", "--codex-home", "codex"]), 23
            )
        routed.assert_called_once_with(["install-status", "--codex-home", "codex"])

    def test_cli_apply_failure_is_exit_one(self) -> None:
        error = io.StringIO()
        with mock.patch.object(
            install_cli,
            "apply_install",
            side_effect=install_cli.InstallManagerError("blocked"),
        ), contextlib.redirect_stderr(error):
            code = install_cli.main(
                [
                    "install-apply",
                    "--source-root",
                    "source",
                    "--expected-plan-digest",
                    "a" * 64,
                    "--ack-install",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("blocked", error.getvalue())


class RepositoryInstallContractTests(unittest.TestCase):
    def test_repository_source_plan_contains_the_installation_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            install_planner,
            "git_identity",
            return_value={"commit": "b" * 40, "dirty": False},
        ):
            root = Path(temporary)
            result = installation.plan_install(
                SKILL_DIR.parent,
                codex_home=root / "codex",
                state_root=root / "state",
            )
        self.assertTrue(result["ready"])
        targets = {entry["target"] for entry in result["managed_files"]}
        self.assertIn("skills/dynamic-workflow/install_cli.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/apply.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/contract.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/filesystem.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/manager.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/planner.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/rollback.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/status.py", targets)
        self.assertNotIn("agents/grok_writer.toml.disabled", targets)


if __name__ == "__main__":
    unittest.main()
