from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import installation
from installation import InstallManagerError
from installation import apply as install_apply
from installation import contract as install_contract
from installation import filesystem as install_filesystem
from installation import planner as install_planner
from installation import rollback as install_rollback


class InstallRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.codex = self.root / "codex"
        self.state = self.root / "state"
        (self.source / "skill").mkdir(parents=True)
        (self.source / "config" / "agents").mkdir(parents=True)
        (self.source / "integration").mkdir()
        (self.source / "skill" / "VERSION").write_text(
            "1.0.0-rc.2\n", encoding="utf-8"
        )
        (self.source / "skill" / "SKILL.md").write_text(
            "new-skill-v1\n", encoding="utf-8"
        )
        (self.source / "skill" / "payload.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        (self.source / "config" / "agents" / "luna.toml").write_text(
            'name = "new-luna-v1"\n', encoding="utf-8"
        )
        (self.source / "integration" / "AGENTS.dynamic-workflow.md").write_text(
            "merge manually\n", encoding="utf-8"
        )
        self.git_patch = mock.patch.object(
            install_planner,
            "git_identity",
            return_value={"commit": "c" * 40, "dirty": False},
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

    def seed_old_targets(self) -> dict[str, str]:
        values = {
            "agents/luna.toml": 'name = "old-luna"\n',
            "skills/dynamic-workflow/SKILL.md": "old-skill\n",
            "skills/dynamic-workflow/VERSION": "old-version\n",
            "skills/dynamic-workflow/payload.py": "VALUE = 0\n",
        }
        for relative, value in values.items():
            path = self.codex.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        return values

    def interrupt_after_first_target_write(self):
        original = install_apply.atomic_write_bytes
        fired = False

        def interrupted(path, payload, *, root, label):
            nonlocal fired
            original(path, payload, root=root, label=label)
            if not fired and label == "managed installation target":
                fired = True
                raise RuntimeError("injected apply interruption")

        return mock.patch.object(
            install_apply,
            "atomic_write_bytes",
            side_effect=interrupted,
        )

    def assert_target_values(self, expected: dict[str, str]) -> None:
        for relative, value in expected.items():
            path = self.codex.joinpath(*relative.split("/"))
            self.assertEqual(path.read_text(encoding="utf-8"), value)

    def test_interrupted_first_apply_recovers_before(self) -> None:
        before = self.seed_old_targets()
        plan = self.plan()
        with self.interrupt_after_first_target_write(), self.assertRaisesRegex(
            RuntimeError, "injected apply interruption"
        ):
            installation.apply_install(
                self.source,
                expected_plan_digest=plan["plan_digest"],
                ack_install=True,
                codex_home=self.codex,
                state_root=self.state,
            )

        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "apply_incomplete")
        self.assertEqual(status["recommended_action"], "install-rollback")
        pending_id = status["pending_install_id"]
        blocked = self.plan()
        self.assertFalse(blocked["ready"])
        self.assertIn(
            "active_install_transaction",
            {item["code"] for item in blocked["blocked"]},
        )

        recovered = installation.rollback_install(
            expected_install_id=pending_id,
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(recovered["state"], "apply_recovered")
        self.assert_target_values(before)
        self.assertEqual(
            installation.install_status(
                codex_home=self.codex,
                state_root=self.state,
            )["state"],
            "not_installed",
        )
        self.assertFalse(
            install_filesystem.active_transaction_path(self.state).exists()
        )

    def test_interrupted_upgrade_restores_previous_snapshot(self) -> None:
        first = self.apply()
        self.assertTrue(
            installation.install_status(
                codex_home=self.codex,
                state_root=self.state,
            )["rollback_available"]
        )
        (self.source / "skill" / "VERSION").write_text(
            "1.0.0-rc.3\n", encoding="utf-8"
        )
        (self.source / "skill" / "SKILL.md").write_text(
            "new-skill-v2\n", encoding="utf-8"
        )
        (self.source / "config" / "agents" / "luna.toml").write_text(
            'name = "new-luna-v2"\n', encoding="utf-8"
        )
        plan = self.plan()
        with self.interrupt_after_first_target_write(), self.assertRaisesRegex(
            RuntimeError, "injected apply interruption"
        ):
            installation.apply_install(
                self.source,
                expected_plan_digest=plan["plan_digest"],
                ack_install=True,
                codex_home=self.codex,
                state_root=self.state,
            )

        pending = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        recovered = installation.rollback_install(
            expected_install_id=pending["pending_install_id"],
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(recovered["state"], "apply_recovered")
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "clean")
        self.assertEqual(status["install_id"], first["install_id"])
        self.assertEqual(status["skill_version"], "1.0.0-rc.2")
        self.assertTrue(status["rollback_available"])
        self.assertEqual(
            (
                self.codex
                / "skills"
                / "dynamic-workflow"
                / "SKILL.md"
            ).read_text(encoding="utf-8"),
            "new-skill-v1\n",
        )

    def test_interrupted_rollback_resumes_after_manifest_switch(self) -> None:
        self.seed_old_targets()
        installed = self.apply()
        original = install_rollback.atomic_write_json

        def interrupted(path, value, *, root, label):
            if (
                label == "installation history record"
                and value.get("state") == "rolled_back"
            ):
                raise RuntimeError("injected rollback interruption")
            return original(path, value, root=root, label=label)

        with mock.patch.object(
            install_rollback,
            "atomic_write_json",
            side_effect=interrupted,
        ), self.assertRaisesRegex(
            RuntimeError, "injected rollback interruption"
        ):
            installation.rollback_install(
                expected_install_id=installed["install_id"],
                ack_rollback=True,
                codex_home=self.codex,
                state_root=self.state,
            )

        pending = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(pending["state"], "rollback_incomplete")
        retried = installation.rollback_install(
            expected_install_id=installed["install_id"],
            ack_rollback=True,
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(retried["state"], "rolled_back")
        self.assertEqual(
            installation.install_status(
                codex_home=self.codex,
                state_root=self.state,
            )["state"],
            "not_installed",
        )

    def test_pointerless_rolling_back_record_is_not_clean(self) -> None:
        installed = self.apply()
        record_path = Path(installed["history_record"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["state"] = "rolling_back"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "rollback_incomplete")

    def test_malformed_active_pointer_reports_metadata_error(self) -> None:
        pointer = install_filesystem.active_transaction_path(self.state)
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(
            '{"version":1,"operation":"apply",'
            '"install_id":"bad","record":"bad"}',
            encoding="utf-8",
        )
        status = installation.install_status(
            codex_home=self.codex,
            state_root=self.state,
        )
        self.assertEqual(status["state"], "metadata_error")
        self.assertFalse(status["rollback_available"])

    def test_persisted_paths_reject_backslashes(self) -> None:
        installed = self.apply()
        manifest = json.loads(
            Path(installed["manifest_path"]).read_text(encoding="utf-8")
        )
        bad_target = copy.deepcopy(manifest)
        bad_target["managed_files"][0]["target"] = (
            "agents/..\\outside.toml"
        )
        with self.assertRaisesRegex(
            InstallManagerError, "canonical POSIX relative path"
        ):
            install_contract.validate_manifest(
                bad_target, label="bad manifest"
            )

        bad_history = copy.deepcopy(manifest)
        bad_history["history_record"] = (
            "installations\\bad\\record.json"
        )
        with self.assertRaisesRegex(
            InstallManagerError, "canonical POSIX relative path"
        ):
            install_contract.validate_manifest(
                bad_history, label="bad manifest"
            )

        with self.assertRaisesRegex(
            InstallManagerError, "safe relative path"
        ):
            install_filesystem.safe_target(
                self.codex,
                "agents/..\\outside.toml",
                label="bad target",
            )

    @unittest.skipUnless(os.name == "nt", "Windows target identity")
    def test_case_only_target_change_is_blocked_before_write(self) -> None:
        upper = self.source / "skill" / "Foo.py"
        upper.write_text("VALUE = 1\n", encoding="utf-8")
        self.apply()

        temporary = self.source / "skill" / "case.tmp"
        upper.rename(temporary)
        lower = self.source / "skill" / "foo.py"
        temporary.rename(lower)
        lower.write_text("VALUE = 2\n", encoding="utf-8")
        (self.source / "skill" / "VERSION").write_text(
            "1.0.0-rc.3\n", encoding="utf-8"
        )

        plan = self.plan()
        self.assertFalse(plan["ready"])
        self.assertIn(
            "target_identity_collision",
            {item["code"] for item in plan["blocked"]},
        )


if __name__ == "__main__":
    unittest.main()
