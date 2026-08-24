from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]


class WriterUtf8IntegrationTests(unittest.TestCase):
    @staticmethod
    def _cp936_env(root: Path) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "cp936"
        env["PYTHONUTF8"] = "0"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["DYNWF_RUNS_ROOT"] = str(root / "runs")
        env["DYNWF_WORKTREE_ROOT"] = str(root / "worktrees")
        return env

    def test_writer_routes_emit_strict_utf8_errors_under_cp936(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing_package = root / "缺失🧪package.json"
            missing_run = root / "缺失🧪run"
            digest = "0" * 64
            head = "1" * 40
            env = self._cp936_env(root)
            commands = {
                "writer-plan": [
                    "writer-plan",
                    "--package",
                    str(missing_package),
                    "--repository",
                    str(root),
                    "--expected-package-digest",
                    digest,
                ],
                "writer-run": [
                    "writer-run",
                    "--package",
                    str(missing_package),
                    "--repository",
                    str(root),
                    "--expected-package-digest",
                    digest,
                    "--expected-head-sha",
                    head,
                    "--ack-isolated-worktree-write",
                ],
                "writer-status": [
                    "writer-status",
                    "--run-dir",
                    str(missing_run),
                ],
                "writer-export": [
                    "writer-export",
                    "--run-dir",
                    str(missing_run),
                ],
                "writer-cleanup": [
                    "writer-cleanup",
                    "--run-dir",
                    str(missing_run),
                    "--expected-run-id",
                    "缺失🧪run-id",
                    "--expected-package-digest",
                    digest,
                    "--ack-delete-isolated-worktree",
                ],
            }
            entrypoints = {
                "top-level-router": SKILL_DIR / "cli.py",
                "direct-writer-cli": SKILL_DIR / "writer_cli.py",
            }

            for entrypoint_label, entrypoint in entrypoints.items():
                for command_label, arguments in commands.items():
                    with self.subTest(
                        entrypoint=entrypoint_label,
                        command=command_label,
                    ):
                        completed = subprocess.run(
                            [sys.executable, "-B", str(entrypoint), *arguments],
                            cwd=SKILL_DIR,
                            env=env,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=False,
                        )
                        self.assertNotEqual(completed.returncode, 0)
                        output = completed.stdout.decode("utf-8", errors="strict")
                        error = completed.stderr.decode("utf-8", errors="strict")
                        self.assertIn("🧪", output + error)


if __name__ == "__main__":
    unittest.main()
