# -*- coding: utf-8 -*-
import unittest

from helpers import runner


class TestResolveBackendCmd(unittest.TestCase):
    def test_user_prefix_wins_codex(self):
        self.assertEqual(
            runner.resolve_backend_cmd("codex", ["x", "y"]), ["x", "y"])

    def test_user_prefix_wins_claude(self):
        self.assertEqual(
            runner.resolve_backend_cmd("claude", ["x", "y"]), ["x", "y"])

    def test_unknown_backend_raises(self):
        with self.assertRaises(runner.WorkflowError):
            runner.resolve_backend_cmd("gpt", None)

    def test_claude_prefix_user_override(self):
        self.assertEqual(
            runner.resolve_claude_prefix(["python", "mock_claude.py"]),
            ["python", "mock_claude.py"])


if __name__ == "__main__":
    unittest.main()
