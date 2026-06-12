# -*- coding: utf-8 -*-
import unittest
from pathlib import Path

from helpers import run_wf, spec_dict, stage, task


class TestRunWorkflow(unittest.TestCase):
    def test_ok_with_schema_parses_json(self):
        raw = spec_dict([stage("s1", task("a", prompt="你好",
                                          output_schema={"type": "object"}))])
        s, rd = run_wf(raw)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["output"]["echo"], "你好")
        self.assertTrue((rd / "summary.json").exists())
        self.assertTrue((rd / "tasks" / "a" / "prompt.txt").exists())

    def test_ok_without_schema_returns_text(self):
        raw = spec_dict([stage("s1", task("a", prompt="你好"))])
        s, _ = run_wf(raw)
        self.assertEqual(s["tasks"][0]["status"], "ok")
        self.assertEqual(s["tasks"][0]["output"], "ECHO:你好")

    def test_nonzero_exit_is_error(self):
        raw = spec_dict([stage("s1", task("a", prompt="[MOCK:exit=3] 干活"))])
        s, _ = run_wf(raw)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "error")
        self.assertEqual(t["exit_code"], 3)
        self.assertIsNone(t["output"])

    def test_bad_json_is_parse_error(self):
        raw = spec_dict([stage("s1", task("a", prompt="[MOCK:badjson] 干活",
                                          output_schema={"type": "object"}))])
        s, _ = run_wf(raw)
        self.assertEqual(s["tasks"][0]["status"], "parse_error")

    def test_missing_required_key_is_schema_mismatch(self):
        raw = spec_dict([stage("s1", task("a", prompt="你好",
                                          output_schema={"type": "object",
                                                         "required": ["findings"]}))])
        s, _ = run_wf(raw)
        # mock 只会回 {"echo": ...},缺 findings → 最小 schema 检查拦下
        self.assertEqual(s["tasks"][0]["status"], "schema_mismatch")

    def test_timeout_kills_agent(self):
        raw = spec_dict([stage("s1", task("a", prompt="[MOCK:sleep=30] 干活"))])
        s, _ = run_wf(raw, timeout_override=1)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "timeout")
        self.assertLess(t["duration_s"], 10)


if __name__ == "__main__":
    unittest.main()
