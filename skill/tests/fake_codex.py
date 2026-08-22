#!/usr/bin/env python3
"""Small codex-exec stand-in used only by the offline runner tests."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def option(name: str) -> str:
    index = sys.argv.index(name)
    return sys.argv[index + 1]


def main() -> int:
    output_path = Path(option("-o"))
    model = option("-m")
    prompt_arg = sys.argv[sys.argv.index("--") + 1]
    prompt = sys.stdin.read() if prompt_arg == "-" else prompt_arg

    if "FAKE_FAIL_PERMANENT" in prompt:
        print("permanent fixture failure")
        return 7
    if "FAKE_TRANSIENT_ONCE" in prompt:
        print("429 rate limit fixture")
        return 9
    if "FAKE_RETRY_UPGRADE_COMBO" in prompt:
        print("503 temporary fixture")
        return 9
    if "FAKE_SLEEP" in prompt:
        time.sleep(30)

    if (
        "FAKE_NEEDS_ESCALATION" in prompt and "spark" in model
    ):
        envelope = {
            "workflow_status": "needs_escalation",
            "reason": "fixture requests more capability",
            "result": "",
        }
    else:
        if "FAKE_OBJECT" in prompt:
            result = {"finding": "ok"}
        elif "FAKE_ECHO_UPSTREAM" in prompt:
            result = "boundary-ok" if "<UPSTREAM_RESULT" in prompt else "boundary-missing"
        else:
            result = f"ok:{model}"
        envelope = {
            "workflow_status": "ok",
            "reason": "fixture success",
            "result": result,
        }
    output_path.write_text(json.dumps(envelope), encoding="utf-8")
    print("42 tokens used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
