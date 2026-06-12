# -*- coding: utf-8 -*-
import unittest

from helpers import run_wf, spec_dict, stage, task


class TestPipeline(unittest.TestCase):
    def test_stage2_sees_stage1_result(self):
        raw = spec_dict([
            stage("find", task("a", prompt="第一阶段发现",
                               output_schema={"type": "object"})),
            stage("verify", task("b", prompt="复核:{{result:a}}")),
        ])
        s, _ = run_wf(raw)
        b = [t for t in s["tasks"] if t["id"] == "b"][0]
        self.assertEqual(b["status"], "ok")
        # a 的输出 {"echo":"第一阶段发现"} 被注入 b 的 prompt,mock 又原样回显
        self.assertIn("第一阶段发现", b["output"])

    def test_failed_upstream_skips_downstream(self):
        raw = spec_dict([
            stage("find", task("a", prompt="[MOCK:exit=3] 干活")),
            stage("verify", task("b", prompt="复核:{{result:a}}")),
        ])
        s, _ = run_wf(raw)
        statuses = {t["id"]: t["status"] for t in s["tasks"]}
        self.assertEqual(statuses["a"], "error")
        self.assertEqual(statuses["b"], "skipped_missing_input")

    def test_substituted_prompt_too_long_is_blocked(self):
        raw = spec_dict([
            stage("find", task("a", prompt="x" * 19990,
                               output_schema={"type": "object"})),
            stage("verify", task("b", prompt="复核:{{result:a}}")),
        ])
        s, _ = run_wf(raw)
        statuses = {t["id"]: t["status"] for t in s["tasks"]}
        self.assertEqual(statuses["a"], "ok")
        # a 的输出注入后 b 的 prompt 超 20000 字符上限 → 不运行,如实标注
        self.assertEqual(statuses["b"], "prompt_too_long")


if __name__ == "__main__":
    unittest.main()
