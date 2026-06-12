# -*- coding: utf-8 -*-
import unittest

from helpers import runner


class TestBuildCmd(unittest.TestCase):
    def test_full_argv_exact(self):
        cmd = runner.build_cmd(["codex"], r"D:\proj", "审查代码", r"D:\o.json",
                               schema_path=r"D:\s.json", reasoning_effort="high")
        self.assertEqual(cmd, [
            "codex", "exec",
            "-s", "read-only",
            "--skip-git-repo-check",
            "--color", "never",
            "-C", r"D:\proj",
            "--output-schema", r"D:\s.json",
            "-o", r"D:\o.json",
            "-c", "model_reasoning_effort=high",
            "审查代码",
        ])

    def test_minimal_is_readonly_no_schema(self):
        cmd = runner.build_cmd(["codex"], "wd", "p", "out")
        i = cmd.index("-s")
        self.assertEqual(cmd[i + 1], "read-only")
        self.assertNotIn("--output-schema", cmd)
        self.assertNotIn("-m", cmd)
        self.assertEqual(cmd[-1], "p")

    def test_prefix_can_be_multi_token(self):
        cmd = runner.build_cmd(["python", "mock.py"], "wd", "p", "out")
        self.assertEqual(cmd[:3], ["python", "mock.py", "exec"])


if __name__ == "__main__":
    unittest.main()
