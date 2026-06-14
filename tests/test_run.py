# -*- coding: utf-8 -*-
import unittest
import asyncio
import tempfile
from pathlib import Path

from helpers import MOCK_PREFIX, run_wf, runner, spec_dict, stage, task, mktemp


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

    def test_output_schema_hardened_on_disk(self):
        # 落盘给 codex 的 schema.json 顶层必须被自动补上 additionalProperties: false
        import json as _json
        raw = spec_dict([stage("s1", task("a", prompt="你好",
                                          output_schema={"type": "object",
                                                         "properties": {}}))])
        s, _ = run_wf(raw)
        sp = Path(s["tasks"][0]["task_dir"]) / "schema.json"
        written = _json.loads(sp.read_text(encoding="utf-8"))
        self.assertIs(written["additionalProperties"], False)

    def test_harden_schema_nested_and_keeps_explicit(self):
        from helpers import runner
        out = runner._harden_schema({
            "type": "object",
            "properties": {"inner": {"type": "object", "properties": {},
                                     "additionalProperties": True}}})
        self.assertIs(out["additionalProperties"], False)               # 顶层自动补
        self.assertIs(out["properties"]["inner"]["additionalProperties"], True)  # 显式不覆盖

    def test_existing_run_dir_is_rejected(self):
        raw = spec_dict([stage("s1", task("a"))])
        spec = runner.validate_spec(raw)
        existing = mktemp("dynwf-existing-")
        with self.assertRaises(runner.WorkflowError):
            asyncio.run(runner.run_workflow(spec, existing, MOCK_PREFIX))


if __name__ == "__main__":
    unittest.main()
