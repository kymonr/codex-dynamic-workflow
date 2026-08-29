from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_contract
import writer_git_state


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


class WriterPreflightTests(unittest.TestCase):
    def test_validate_base_uses_owned_path_metadata_without_git_show(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            git(root, "init")
            git(root, "config", "user.email", "fixture@example.invalid")
            git(root, "config", "user.name", "Fixture")
            git(root, "config", "core.autocrlf", "false")
            git(root, "config", "core.eol", "lf")
            git(root, "remote", "add", "origin", "https://github.com/owner/repo.git")
            (root / "owned.txt").write_text("sensitive fixture body\n", encoding="utf-8")
            git(root, "add", "owned.txt")
            git(root, "commit", "-m", "base")
            package = writer_contract.validate_package(
                {
                    "version": 2,
                    "name": "metadata-only",
                    "objective": "Modify one exact file.",
                    "acceptance_criteria": ["The fixed verification command passes."],
                    "constraints": ["Preserve unrelated repository behavior."],
                    "non_goals": ["Do not expand authority."],
                    "behavior": {
                        "before": "The requested bounded change is absent.",
                        "after": "The requested bounded change is present.",
                    },
                    "implementation_context": {
                        "relevant_symbols": ["owned.txt"],
                        "analysis_summary": "Only declared targets are relevant.",
                    },
                    "base": {
                        "repository_full_name": "owner/repo",
                        "expected_head_sha": git(root, "rev-parse", "HEAD"),
                        "expected_tree_sha": git(root, "rev-parse", "HEAD^{tree}"),
                    },
                    "authority": {
                        "owned_targets": ["owned.txt"],
                        "allowed_actions": ["modify"],
                    },
                    "limits": {
                        "max_changed_files": 1,
                        "max_patch_bytes": 65536,
                        "max_created_file_bytes": 65536,
                        "max_total_candidate_bytes": 131072,
                    },
                    "verification": {
                        "required_verification_ids": ["unit"],
                        "commands": [
                            {
                                "id": "unit",
                                "argv": ["python", "-m", "unittest"],
                                "timeout_seconds": 60,
                            }
                        ],
                    },
                }
            )
            calls: list[tuple[str, ...]] = []
            original = writer_git_state.run_git

            def recording(repository, args, **kwargs):
                calls.append(tuple(args))
                return original(repository, args, **kwargs)

            with mock.patch.object(writer_git_state, "run_git", side_effect=recording):
                snapshot = writer_git_state.validate_base(root, package)
            self.assertEqual(snapshot["head"], package.expected_head_sha)
            self.assertIn(("ls-tree", "-z", "HEAD", "--", "owned.txt"), calls)
            self.assertFalse(
                any(args and args[0] in {"show", "cat-file"} for args in calls),
                calls,
            )


if __name__ == "__main__":
    unittest.main()
