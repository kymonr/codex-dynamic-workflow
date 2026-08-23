#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def option(name: str) -> str:
    index = sys.argv.index(name)
    return sys.argv[index + 1]


def field(prompt: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}=(.+)$", prompt, flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"missing planner prompt field: {name}")
    return match.group(1).strip()


def main() -> int:
    output_path = Path(option("-o"))
    prompt_arg = sys.argv[sys.argv.index("--") + 1]
    prompt = sys.stdin.read() if prompt_arg == "-" else prompt_arg
    if "AUTO_PLANNER_V1_SELECT_PRESET" not in prompt:
        print("unknown Auto Planner prompt", file=sys.stderr)
        return 7

    eligible = json.loads(field(prompt, "ELIGIBLE_PRESETS_JSON"))
    if not isinstance(eligible, list) or not eligible:
        print("eligible preset fixture is malformed", file=sys.stderr)
        return 8
    registry_version = int(field(prompt, "REGISTRY_VERSION"))
    registry_digest = field(prompt, "REGISTRY_DIGEST")
    contract_digest = field(prompt, "CONTRACT_DIGEST")
    parameter_digest = field(prompt, "PARAMETER_DIGEST")

    if "AUTO_TEST_NEEDS_ESCALATION" in prompt:
        envelope = {
            "workflow_status": "needs_escalation",
            "reason": "fixture requested planner escalation",
            "result": {},
        }
    else:
        preferred = "design-swarm"
        if "AUTO_TEST_REVIEW" in prompt:
            preferred = "ultra-review"
        elif "AUTO_TEST_SWEEP" in prompt:
            preferred = "repo-sweep"
        selected = preferred if preferred in eligible else eligible[0]
        considered = [
            {
                "preset": name,
                "fit": "best" if name == selected else "possible",
                "reason": f"fixture evaluation for {name}",
            }
            for name in eligible
        ]
        if "AUTO_TEST_INVALID_CONSIDERED" in prompt:
            considered = considered[:-1]
        result = {
            "registry_version": registry_version,
            "registry_digest": registry_digest,
            "contract_digest": contract_digest,
            "parameter_digest": parameter_digest,
            "action": "select_preset",
            "selected_preset": selected,
            "rationale": "fixture selected the closest registered preset",
            "signals": ["fixture objective signal"],
            "uncertainty": [],
            "considered_presets": considered,
        }
        envelope = {
            "workflow_status": "ok",
            "reason": "fixture success",
            "result": result,
        }

    output_path.write_text(json.dumps(envelope), encoding="utf-8")
    print("17 tokens used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
