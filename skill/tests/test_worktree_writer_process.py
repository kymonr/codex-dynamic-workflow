from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_process


class WriterProcessTests(unittest.TestCase):
    def test_writer_command_disables_shell_code_mode_network_and_agents(self) -> None:
        command = writer_process._build_command(
            codex_prefix=["codex"],
            cwd=Path("/isolated/worktree"),
            route=writer_process.WRITER_ROUTE,
            schema_path=Path("/evidence/schema.json"),
            output_path=Path("/evidence/out.json"),
        )
        joined = "\n".join(command)
        self.assertIn("workspace-write", command)
        self.assertIn("features.shell_tool=false", command)
        self.assertIn("features.code_mode=false", command)
        self.assertIn("features.multi_agent=false", command)
        self.assertIn("agents.enabled=false", command)
        self.assertIn("web_search=disabled", command)
        self.assertIn("sandbox_workspace_write.network_access=false", command)
        self.assertIn("sandbox_workspace_write.writable_roots=[]", command)
        self.assertIn("approval_policy=never", command)
        self.assertNotIn("danger-full-access", joined)
        self.assertNotIn("full-auto", joined)
        self.assertNotIn("approval_policy=on-request", joined)
        self.assertEqual(command.count("-C"), 1)

    def test_reviewer_command_is_read_only_and_has_same_no_command_surface(self) -> None:
        command = writer_process._build_command(
            codex_prefix=["codex"],
            cwd=Path("/empty/reviewer"),
            route=writer_process.REVIEWER_ROUTE,
            schema_path=Path("/evidence/schema.json"),
            output_path=Path("/evidence/out.json"),
        )
        self.assertIn("read-only", command)
        self.assertIn("features.shell_tool=false", command)
        self.assertIn("features.code_mode=false", command)
        self.assertIn("features.multi_agent=false", command)
        self.assertIn("web_search=disabled", command)
        self.assertNotIn("sandbox_workspace_write.network_access=false", command)

    def test_capability_probe_requires_shell_tool_feature(self) -> None:
        responses = [
            subprocess.CompletedProcess(
                ["codex", "exec", "--help"],
                0,
                stdout=(
                    b"--ephemeral --ignore-user-config --ignore-rules "
                    b"--output-schema --skip-git-repo-check"
                ),
                stderr=b"",
            ),
            subprocess.CompletedProcess(
                ["codex", "features", "list"],
                0,
                stdout=b"shell_tool stable true\nmulti_agent stable true\ncode_mode beta false\n",
                stderr=b"",
            ),
        ]
        with mock.patch.object(writer_process.subprocess, "run", side_effect=responses) as run:
            result = writer_process.probe_codex_capabilities(["codex"])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result["command_policy"]["shell_tool"], "disabled")
        self.assertEqual(result["command_policy"]["writer_edit_tool"], "apply_patch_only")

    def test_capability_probe_fails_before_writer_when_shell_disable_is_unavailable(self) -> None:
        responses = [
            subprocess.CompletedProcess(
                ["codex", "exec", "--help"],
                0,
                stdout=(
                    b"--ephemeral --ignore-user-config --ignore-rules "
                    b"--output-schema --skip-git-repo-check"
                ),
                stderr=b"",
            ),
            subprocess.CompletedProcess(
                ["codex", "features", "list"],
                0,
                stdout=b"multi_agent stable true\ncode_mode beta false\n",
                stderr=b"",
            ),
        ]
        with mock.patch.object(writer_process.subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(writer_process.WriterProcessError, "shell_tool"):
                writer_process.probe_codex_capabilities(["codex"])


if __name__ == "__main__":
    unittest.main()
