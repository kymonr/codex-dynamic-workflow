#!/usr/bin/env python3
"""Offline codex-exec stand-in for trusted Workflow IR integration tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def option(name: str) -> str:
    index = sys.argv.index(name)
    return sys.argv[index + 1]


def main() -> int:
    output_path = Path(option("-o"))
    prompt_arg = sys.argv[sys.argv.index("--") + 1]
    prompt = sys.stdin.read() if prompt_arg == "-" else prompt_arg

    if "IR_DISCOVER" in prompt:
        result = [{"name": "alpha"}, {"name": "beta"}]
    elif "IR_MAP" in prompt:
        result = {"finding": "mapped"}
    elif "IR_VERIFY" in prompt:
        result = {
            "verdict": "accept",
            "summary": "verified",
            "evidence": ["offline fixture"],
        }
    elif "IR_REDUCE" in prompt:
        result = {"summary": "reduced"}
    else:
        result = "ok"

    output_path.write_text(
        json.dumps(
            {
                "workflow_status": "ok",
                "reason": "offline IR fixture",
                "result": result,
            }
        ),
        encoding="utf-8",
    )
    print("64 tokens used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
