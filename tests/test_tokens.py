# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from helpers import runner, run_wf, spec_dict, stage, task


class TestExtractTokens(unittest.TestCase):
    def _write(self, text):
        p = Path(tempfile.mkdtemp(prefix="dynwf-tok-")) / "agent.log"
        p.write_text(text, encoding="utf-8")
        return p

    def test_extracts_tokens_used(self):
        p = self._write("一些日志\ntokens used: 1234\n收尾\n")
        self.assertEqual(runner._extract_tokens(p), 1234)

    def test_extracts_total_with_commas(self):
        p = self._write("Total tokens: 12,345\n")
        self.assertEqual(runner._extract_tokens(p), 12345)

    def test_garbage_returns_none(self):
        p = self._write("没有用量信息\n只有普通日志\n")
        self.assertIsNone(runner._extract_tokens(p))

    def test_missing_file_returns_none(self):
        self.assertIsNone(
            runner._extract_tokens(Path(r"D:\不存在-dynwf-tok\agent.log")))


class TestTokensInSummary(unittest.TestCase):
    def test_task_and_total_tokens_captured(self):
        raw = spec_dict([stage("s1", task("a", prompt="你好[MOCK:tokens=4242]"))])
        s, _ = run_wf(raw)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["tokens"], 4242)
        self.assertEqual(s["total_tokens"], 4242)

    def test_total_tokens_null_when_none_reported(self):
        raw = spec_dict([stage("s1", task("a", prompt="你好"))])
        s, _ = run_wf(raw)
        self.assertIsNone(s["tasks"][0]["tokens"])
        self.assertIsNone(s["total_tokens"])

    def test_total_tokens_sums_multiple(self):
        raw = spec_dict([stage("s1",
                               task("a", prompt="甲[MOCK:tokens=100]"),
                               task("b", prompt="乙[MOCK:tokens=250]"))])
        s, _ = run_wf(raw)
        self.assertEqual(s["total_tokens"], 350)


if __name__ == "__main__":
    unittest.main()
