# -*- coding: utf-8 -*-
import json
import unittest

from helpers import runner


def env(**kw):
    base = {"type": "result", "subtype": "success", "is_error": False}
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


class TestParseClaudeResult(unittest.TestCase):
    def test_success_text(self):
        st, out, tok, err = runner._parse_claude_result(
            env(result="答案", usage={"output_tokens": 12}), has_schema=False)
        self.assertEqual(st, "ok")
        self.assertEqual(out, "答案")
        self.assertEqual(tok, 12)
        self.assertIsNone(err)

    def test_success_structured(self):
        st, out, tok, err = runner._parse_claude_result(
            env(result="x", structured_output={"k": 1},
                usage={"output_tokens": 5}), has_schema=True)
        self.assertEqual(st, "ok")
        self.assertEqual(out, {"k": 1})
        self.assertEqual(tok, 5)

    def test_is_error_true(self):
        st, out, tok, err = runner._parse_claude_result(
            env(is_error=True, result=""), has_schema=False)
        self.assertEqual(st, "error")
        self.assertIsNone(out)

    def test_subtype_not_success(self):
        st, out, tok, err = runner._parse_claude_result(
            env(subtype="error_max_turns"), has_schema=False)
        self.assertEqual(st, "error")

    def test_empty_is_parse_error(self):
        st, out, tok, err = runner._parse_claude_result("", has_schema=False)
        self.assertEqual(st, "parse_error")

    def test_bad_json_is_parse_error(self):
        st, out, tok, err = runner._parse_claude_result("{不是json", has_schema=False)
        self.assertEqual(st, "parse_error")

    def test_schema_missing_structured_output(self):
        st, out, tok, err = runner._parse_claude_result(
            env(result="x"), has_schema=True)
        self.assertEqual(st, "error")


if __name__ == "__main__":
    unittest.main()
