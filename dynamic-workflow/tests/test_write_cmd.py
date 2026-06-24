# -*- coding: utf-8 -*-
"""build_write_cmd 单测 + 读模式 build_cmd 回归。

写模式命令必须硬编码 -s workspace-write、带 -C <wt>、prompt 前有 -- 分隔符;
回归断言:同一 runner 里读模式 build_cmd 仍是 -s read-only、绝不出现 workspace-write。
"""
import unittest

from helpers import runner


class TestBuildWriteCmd(unittest.TestCase):
    def test_full_argv_exact_with_reasoning(self):
        # 给定 reasoning_effort，完整 argv 逐项精确相等（含 -c）
        cmd = runner.build_write_cmd(["codex"], r"D:\wt\moduleA", "改 src/moduleA",
                                     reasoning_effort="high")
        self.assertEqual(cmd, [
            "codex", "exec",
            "-s", "workspace-write",
            "--skip-git-repo-check",
            "--color", "never",
            "-C", r"D:\wt\moduleA",
            "-c", "model_reasoning_effort=high",
            "--", "改 src/moduleA",
        ])

    def test_full_argv_exact_no_reasoning(self):
        # 不给 reasoning_effort（默认 None）：完整 argv 精确相等，且不含任何 -c
        cmd = runner.build_write_cmd(["codex"], r"D:\wt\docs", "改 docs")
        self.assertEqual(cmd, [
            "codex", "exec",
            "-s", "workspace-write",
            "--skip-git-repo-check",
            "--color", "never",
            "-C", r"D:\wt\docs",
            "--", "改 docs",
        ])
        self.assertNotIn("-c", cmd)

    def test_is_workspace_write_not_readonly(self):
        # 写模式:-s 后必须是 workspace-write，绝不能是 read-only
        cmd = runner.build_write_cmd(["codex"], "wd", "p")
        i = cmd.index("-s")
        self.assertEqual(cmd[i + 1], "workspace-write")
        self.assertNotIn("read-only", cmd)

    def test_prompt_after_separator(self):
        # prompt 前必有 -- 分隔符；以 - 开头的 prompt 也不会被当成选项
        cmd = runner.build_write_cmd(["codex"], "wd", "--help 其实是 prompt")
        self.assertEqual(cmd[-2:], ["--", "--help 其实是 prompt"])

    def test_no_output_flags(self):
        # 写模式不带读模式的 -o / --output-schema（写模式不收结构化输出）
        cmd = runner.build_write_cmd(["codex"], "wd", "p", reasoning_effort="low")
        self.assertNotIn("-o", cmd)
        self.assertNotIn("--output-schema", cmd)

    def test_str_workdir_when_path_like(self):
        # workdir 经 str() 归一化（防 Path 对象漏进 argv）
        from pathlib import Path
        cmd = runner.build_write_cmd(["codex"], Path(r"D:\wt\x"), "p")
        i = cmd.index("-C")
        self.assertEqual(cmd[i + 1], r"D:\wt\x")
        self.assertIsInstance(cmd[i + 1], str)

    def test_prefix_can_be_multi_token(self):
        # 前缀可多段（测试用 python mock_codex.py 这类前缀）
        cmd = runner.build_write_cmd(["python", "mock.py"], "wd", "p")
        self.assertEqual(cmd[:3], ["python", "mock.py", "exec"])
        # 前缀不被原地修改
        pref = ["python", "mock.py"]
        runner.build_write_cmd(pref, "wd", "p")
        self.assertEqual(pref, ["python", "mock.py"])


class TestReadModeRegression(unittest.TestCase):
    """回归:加了写模式后，读模式 build_cmd 行为绝不能被污染。"""

    def test_read_build_cmd_still_readonly(self):
        cmd = runner.build_cmd(["codex"], "wd", "p", "out")
        i = cmd.index("-s")
        self.assertEqual(cmd[i + 1], "read-only")
        self.assertNotIn("workspace-write", cmd)

    def test_read_build_cmd_full_argv_unchanged(self):
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
            "--", "审查代码",
        ])


if __name__ == "__main__":
    unittest.main()
