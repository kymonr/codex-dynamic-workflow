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

import cli
import install_cli
import installation
import versioning
from installation import InstallManagerError
from installation import planner as install_planner
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
        (self.source / "skill" / "VERSION").write_text(
            "1.0.0-rc.2\n", encoding="utf-8"
        )
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
        self.assertEqual(result["skill_version"], "1.0.0-rc.2")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["writes"], [])
        self.assertFalse(self.codex.exists())
        self.assertFalse(self.state.exists())
        targets = {entry["target"] for entry in result["managed_files"]}
        self.assertIn("skills/dynamic-workflow/VERSION", targets)
        self.assertIn("skills/dynamic-workflow/SKILL.md", targets)
        self.assertIn("skills/dynamic-workflow/references/routing.md", targets)
        self.assertIn("agents/luna.toml", targets)
        self.assertNotIn("agents/grok_writer.toml.disabled", targets)
        self.assertFalse(any("__pycache__" in target for target in targets))
        self.assertTrue(result["manual_integration"]["required"])

    def test_plan_rejects_invalid_version(self) -> None:
        (self.source / "skill" / "VERSION").write_text("release-two\n", encoding="utf-8")
        with self.assertRaisesRegex(InstallManagerError, "MAJOR.MINOR.PATCH"):
            self.plan()

    def test_apply_publishes_manifest_and_status_is_clean(self) -> None:
        result = self.apply()
        self.assertEqual(result["state"], "applied")
        self.assertEqual(result["skill_version"], "1.0.0-rc.2")
        self.assertEqual(
            (self.codex / "skills" / "dynamic-workflow" / "VERSION").read_text(),
            "1.0.0-rc.2\n",
        )
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
        self.assertEqual(status["skill_version"], "1.0.0-rc.2")
        self.assertTrue(status["rollback_available"])
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
        history = Path(installed["history_record"]).parent
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
        self.assertIsNone(result["active_skill_version"])
        self.assertEqual(old_skill.read_text(), "old-skill\n")
        self.assertEqual(old_agent.read_text(), "old-agent\n")
        self.assertFalse(created.exists())
        self.assertFalse(history.exists())
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "not_installed")

    def test_second_install_keeps_only_one_rollback_step(self) -> None:
        extra_source = self.source / "skill" / "legacy.py"
        extra_source.write_text("legacy\n", encoding="utf-8")
        first = self.apply()
        first_history = Path(first["history_record"]).parent
        extra_target = self.codex / "skills" / "dynamic-workflow" / "legacy.py"
        self.assertTrue(extra_target.exists())

        extra_source.unlink()
        (self.source / "skill" / "SKILL.md").write_text("skill-v2\n", encoding="utf-8")
        (self.source / "skill" / "VERSION").write_text(
            "1.0.0-rc.3\n", encoding="utf-8"
        )
        second = self.apply()
        second_history = Path(second["history_record"]).parent
        self.assertFalse(extra_target.exists())
        self.assertFalse(first_history.exists())
        self.assertTrue(second_history.exists())
        self.assertNotEqual(first["install_id"], second["install_id"])

        rollback = installation.rollback_install(
            expected_install_id=second["install_id"],
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(rollback["active_install_id"], first["install_id"])
        self.assertEqual(rollback["active_skill_version"], "1.0.0-rc.2")
        self.assertFalse(rollback["rollback_available"])
        self.assertFalse(second_history.exists())
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
        self.assertEqual(status["skill_version"], "1.0.0-rc.2")
        self.assertFalse(status["rollback_available"])
        with self.assertRaisesRegex(InstallManagerError, "no previous rollback snapshot"):
            installation.rollback_install(
                expected_install_id=first["install_id"],
                ack_rollback=True,
                codex_home=self.codex,
                state_root=self.state,
            )

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


class VersioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "skill").mkdir()
        self.version_file = self.root / "skill" / "VERSION"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, value: str) -> None:
        self.version_file.write_text(value + "\n", encoding="utf-8")

    def test_default_and_explicit_bumps(self) -> None:
        cases = (
            ("1.0.0-rc.2", None, "1.0.0-rc.3"),
            ("1.0.0-rc.2", "release", "1.0.0"),
            ("1.0.0", None, "1.0.1"),
            ("1.0.0", "prerelease", "1.0.1-rc.1"),
            ("1.2.3-rc.4", "patch", "1.2.4"),
            ("1.2.3-rc.4", "minor", "1.3.0"),
            ("1.2.3-rc.4", "major", "2.0.0"),
        )
        for current, bump_type, expected in cases:
            with self.subTest(current=current, bump_type=bump_type):
                self.write(current)
                result = versioning.bump_skill_version(
                    self.root, bump_type=bump_type
                )
                self.assertEqual(result["version"], expected)
                self.assertEqual(versioning.read_skill_version(self.root), expected)
                self.assertEqual(result["model_calls"], 0)
                self.assertEqual(result["writes"], [str(self.version_file.absolute())])

    def test_release_rejects_stable_version(self) -> None:
        self.write("1.0.0")
        with self.assertRaisesRegex(versioning.VersionError, "requires a current prerelease"):
            versioning.bump_skill_version(self.root, bump_type="release")

    def test_version_file_is_strict(self) -> None:
        self.version_file.write_text("01.0.0\n", encoding="utf-8")
        with self.assertRaisesRegex(versioning.VersionError, "MAJOR.MINOR.PATCH"):
            versioning.read_skill_version(self.root)


class InstallCliTests(unittest.TestCase):
    def test_cli_plan_is_json_and_routes_arguments(self) -> None:
        expected = {"operation": "install-plan", "writes": [], "model_calls": 0}
        output = io.StringIO()
        with mock.patch.object(
            install_cli, "plan_install", return_value=expected
        ) as routed, contextlib.redirect_stdout(output):
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

    def test_cli_version_bump_routes_explicit_type(self) -> None:
        expected = {"operation": "version-bump", "version": "1.1.0"}
        output = io.StringIO()
        with mock.patch.object(
            install_cli, "bump_skill_version", return_value=expected
        ) as routed, contextlib.redirect_stdout(output):
            code = install_cli.main(
                ["version-bump", "--source-root", "source", "--minor"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), expected)
        routed.assert_called_once_with("source", bump_type="minor")

    def test_portable_cli_routes_personal_commands(self) -> None:
        with mock.patch.object(install_cli, "main", return_value=23) as routed:
            self.assertEqual(
                cli.main(["version-bump", "--source-root", "source"]), 23
            )
        routed.assert_called_once_with(["version-bump", "--source-root", "source"])

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
    def test_repository_source_plan_contains_version_and_installation_modules(self) -> None:
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
        self.assertEqual(result["skill_version"], "1.0.0-rc.3")
        targets = {entry["target"] for entry in result["managed_files"]}
        self.assertIn("skills/dynamic-workflow/VERSION", targets)
        self.assertIn("skills/dynamic-workflow/versioning.py", targets)
        self.assertIn("skills/dynamic-workflow/install_cli.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/apply.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/contract.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/filesystem.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/manager.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/planner.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/rollback.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/status.py", targets)
        self.assertIn("skills/dynamic-workflow/installation/transaction.py", targets)
        self.assertNotIn("agents/grok_writer.toml.disabled", targets)


if __name__ == "__main__":
    unittest.main()
