# -*- coding: utf-8 -*-
import unittest
from pathlib import Path

from helpers import (MOCK_CLAUDE_PREFIX, run_wf, spec_dict, stage, task,
                     mktemp, runner)


def claude_raw(*tasks_, **over):
    return spec_dict([stage("s1", *tasks_)], backend="claude", **over)


class TestClaudeRun(unittest.TestCase):
    def test_text_ok(self):
        s, _ = run_wf(claude_raw(task("a", prompt="你好")),
                      prefix=MOCK_CLAUDE_PREFIX)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["output"], "ECHO:你好")

    def test_schema_ok(self):
        s, _ = run_wf(claude_raw(task("a", prompt="你好",
                                      output_schema={"type": "object"})),
                      prefix=MOCK_CLAUDE_PREFIX)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["output"]["echo"], "你好")

    def test_is_error_envelope_is_error(self):
        s, _ = run_wf(claude_raw(task("a", prompt="[MOCK:iserror] x")),
                      prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "error")

    def test_nonzero_exit_is_error(self):
        s, _ = run_wf(claude_raw(task("a", prompt="[MOCK:exit=4][MOCK:empty] x")),
                      prefix=MOCK_CLAUDE_PREFIX)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "error")
        self.assertEqual(t["exit_code"], 4)

    def test_bad_json_is_parse_error(self):
        s, _ = run_wf(claude_raw(task("a", prompt="[MOCK:badjson] x")),
                      prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "parse_error")

    def test_tokens_from_envelope(self):
        s, _ = run_wf(claude_raw(task("a", prompt="你好[MOCK:tokens=99]")),
                      prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["tokens"], 99)
        self.assertEqual(s["total_tokens"], 99)

    def test_runs_in_workdir_cwd(self):
        wd = mktemp("dynwf-claude-cwd-")
        raw = spec_dict([stage("s1", task("a", prompt="[MOCK:cwdfile] x"))],
                        backend="claude", workdir=str(wd))
        s, _ = run_wf(raw, prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "ok")
        self.assertTrue((wd / "claude_cwd_marker.txt").exists())

    def test_argv_guard_rejects_oversized(self):
        # schema 内联后约 3 万字符,加 prompt 超过 MAX_CLAUDE_ARGV_CHARS(28000)→ 拒
        big_schema = {"type": "object",
                      "properties": {"x": {"type": "string",
                                           "description": "d" * 30000}}}
        raw = claude_raw(task("a", prompt="你好", output_schema=big_schema))
        s, _ = run_wf(raw, prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "prompt_too_long")


if __name__ == "__main__":
    unittest.main()
