# -*- coding: utf-8 -*-
import json
import subprocess
import unittest

from helpers import MOCK_CLAUDE_PREFIX


def run_mock(prompt, schema=None):
    cmd = list(MOCK_CLAUDE_PREFIX) + [
        "-p", "--output-format", "json", "--strict-mcp-config",
        "--tools", "Read,Grep,Glob"]
    if schema:
        cmd += ["--json-schema", schema]
    cmd += ["--", prompt]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


class TestMockClaude(unittest.TestCase):
    def test_text_envelope(self):
        r = run_mock("你好")
        env = json.loads(r.stdout)
        self.assertEqual(env["result"], "ECHO:你好")
        self.assertFalse(env["is_error"])
        self.assertEqual(env["subtype"], "success")

    def test_schema_structured(self):
        r = run_mock("你好", schema='{"type":"object"}')
        env = json.loads(r.stdout)
        self.assertEqual(env["structured_output"]["echo"], "你好")

    def test_exit_code(self):
        r = run_mock("[MOCK:exit=3][MOCK:empty] x")
        self.assertEqual(r.returncode, 3)

    def test_tokens(self):
        r = run_mock("你好[MOCK:tokens=88]")
        env = json.loads(r.stdout)
        self.assertEqual(env["usage"]["output_tokens"], 88)


if __name__ == "__main__":
    unittest.main()
