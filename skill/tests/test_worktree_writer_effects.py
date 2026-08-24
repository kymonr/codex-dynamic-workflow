from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_contract
import writer_effects


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def package(root: Path, targets: list[str], actions: list[str]) -> writer_contract.WriterPackage:
    return writer_contract.validate_package(
        {
            "version": 1,
            "name": "candidate",
            "objective": "Produce an exact bounded text candidate.",
            "base": {
                "repository_full_name": "owner/repo",
                "expected_head_sha": git(root, "rev-parse", "HEAD"),
                "expected_tree_sha": git(root, "rev-parse", "HEAD^{tree}"),
            },
            "authority": {"owned_targets": targets, "allowed_actions": actions},
            "limits": {
                "max_changed_files": len(targets),
                "max_patch_bytes": 1024 * 1024,
                "max_created_file_bytes": 1024 * 1024,
                "max_total_candidate_bytes": 2 * 1024 * 1024,
            },
            "verification": {
                "required_verification_ids": ["unit"],
                "commands": [
                    {"id": "unit", "argv": ["python", "-m", "unittest"], "timeout_seconds": 60}
                ],
            },
        }
    )


class WriterEffectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init")
        git(self.root, "config", "user.email", "fixture@example.invalid")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "remote", "add", "origin", "https://github.com/owner/repo.git")
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "base.txt")
        git(self.root, "commit", "-m", "base")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_base_identity_and_clean_snapshot(self) -> None:
        candidate = package(self.root, ["base.txt"], ["modify"])
        snapshot = writer_effects.validate_base(self.root, candidate)
        self.assertEqual(snapshot["head"], candidate.expected_head_sha)
        self.assertEqual(snapshot["status_bytes"], 0)

    def test_allowed_modify_and_create_capture_deterministic_patch(self) -> None:
        candidate = package(
            self.root,
            ["base.txt", "docs/new.md"],
            ["create", "modify"],
        )
        (self.root / "base.txt").write_text("changed\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "new.md").write_text("new\n", encoding="utf-8")
        first = writer_effects.reconcile_candidate(self.root, candidate)
        second = writer_effects.reconcile_candidate(self.root, candidate)
        self.assertEqual(first, second)
        self.assertEqual(first["manifest"]["changed_paths"], ["base.txt", "docs/new.md"])
        self.assertIn(b"diff --git a/base.txt b/base.txt", first["patch"])
        self.assertIn(b"diff --git a/docs/new.md b/docs/new.md", first["patch"])

    def test_unowned_delete_stage_binary_and_lfs_are_rejected(self) -> None:
        candidate = package(self.root, ["base.txt"], ["modify"])
        (self.root / "other.txt").write_text("other\n", encoding="utf-8")
        with self.assertRaisesRegex(writer_effects.WriterEffectError, "owned target"):
            writer_effects.reconcile_candidate(self.root, candidate)
        (self.root / "other.txt").unlink()

        (self.root / "base.txt").unlink()
        with self.assertRaises(writer_effects.WriterEffectError):
            writer_effects.reconcile_candidate(self.root, candidate)
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")

        (self.root / "base.txt").write_text("staged\n", encoding="utf-8")
        git(self.root, "add", "base.txt")
        with self.assertRaisesRegex(writer_effects.WriterEffectError, "index"):
            writer_effects.reconcile_candidate(self.root, candidate)
        git(self.root, "reset", "--", "base.txt")

        (self.root / "base.txt").write_bytes(b"bad\x00binary")
        with self.assertRaisesRegex(writer_effects.WriterEffectError, "NUL"):
            writer_effects.reconcile_candidate(self.root, candidate)

        (self.root / "base.txt").write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
        with self.assertRaisesRegex(writer_effects.WriterEffectError, "LFS"):
            writer_effects.reconcile_candidate(self.root, candidate)

    @unittest.skipIf(os.name == "nt", "POSIX symlink test")
    def test_symlink_candidate_is_rejected(self) -> None:
        candidate = package(self.root, ["docs/new.md"], ["create"])
        (self.root / "docs").mkdir()
        (self.root / "outside.txt").write_text("outside\n", encoding="utf-8")
        (self.root / "docs" / "new.md").symlink_to(self.root / "outside.txt")
        with self.assertRaises(writer_effects.WriterEffectError):
            writer_effects.reconcile_candidate(self.root, candidate)

    def test_snapshot_comparison_separates_expected_registry_effect(self) -> None:
        before = writer_effects.repository_snapshot(self.root)
        after = dict(before)
        after["worktree_registry_digest"] = "changed"
        self.assertEqual(
            writer_effects.compare_snapshots(
                before, after, allow_worktree_registry_change=True
            ),
            [],
        )
        self.assertEqual(
            writer_effects.compare_snapshots(before, after),
            ["worktree_registry_digest"],
        )


if __name__ == "__main__":
    unittest.main()
