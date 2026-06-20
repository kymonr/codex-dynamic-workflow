# -*- coding: utf-8 -*-
import unittest

from helpers import runner


class TestBuildClaudeReadCmd(unittest.TestCase):
    def test_full_argv_with_schema_and_effort(self):
        cmd = runner.build_claude_read_cmd(
            ["claude"], "审查代码",
            schema_inline='{"type":"object"}', reasoning_effort="high")
        self.assertEqual(cmd, [
            "claude", "-p",
            "--output-format", "json",
            "--strict-mcp-config",
            "--tools", "Read,Grep,Glob",
            "--effort", "high",
            "--json-schema", '{"type":"object"}',
            "--", "审查代码",
        ])

    def test_minimal_no_schema_no_effort(self):
        cmd = runner.build_claude_read_cmd(["claude"], "p")
        self.assertEqual(cmd, [
            "claude", "-p",
            "--output-format", "json",
            "--strict-mcp-config",
            "--tools", "Read,Grep,Glob",
            "--", "p",
        ])
        self.assertNotIn("--json-schema", cmd)
        self.assertNotIn("--effort", cmd)
        self.assertNotIn("-C", cmd)
        self.assertNotIn("-o", cmd)

    def test_tools_locked_to_readonly(self):
        cmd = runner.build_claude_read_cmd(["claude"], "p")
        i = cmd.index("--tools")
        self.assertEqual(cmd[i + 1], "Read,Grep,Glob")

    def test_prompt_after_separator(self):
        cmd = runner.build_claude_read_cmd(["claude"], "--help 其实是 prompt")
        self.assertEqual(cmd[-2:], ["--", "--help 其实是 prompt"])

    def test_prefix_can_be_multi_token(self):
        cmd = runner.build_claude_read_cmd(["python", "mock_claude.py"], "p")
        self.assertEqual(cmd[:2], ["python", "mock_claude.py"])


if __name__ == "__main__":
    unittest.main()
