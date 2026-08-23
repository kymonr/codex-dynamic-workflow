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

    known_presets = {"design-swarm", "repo-sweep", "ultra-review"}
    try:
        eligible = json.loads(field(prompt, "ELIGIBLE_PRESETS_JSON"))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"eligible preset fixture is malformed: {exc}", file=sys.stderr)
        return 8
    if (
        not isinstance(eligible, list)
        or not eligible
        or any(not isinstance(item, str) or item not in known_presets for item in eligible)
        or len(eligible) != len(set(eligible))
    ):
        print("eligible preset fixture is malformed", file=sys.stderr)
        return 8
    registry_version_text = field(prompt, "REGISTRY_VERSION")
    if not re.fullmatch(r"[0-9]+", registry_version_text):
        print("registry version fixture is malformed", file=sys.stderr)
        return 8
    registry_version = int(registry_version_text)
    registry_digest = field(prompt, "REGISTRY_DIGEST")
    contract_digest = field(prompt, "CONTRACT_DIGEST")
    parameter_digest = field(prompt, "PARAMETER_DIGEST")

    markers = set(re.findall(r"\bAUTO_TEST_[A-Z0-9_]+\b", prompt))
    known_markers = {
        "AUTO_TEST_DESIGN",
        "AUTO_TEST_REVIEW",
        "AUTO_TEST_SWEEP",
        "AUTO_TEST_INVALID_CONSIDERED",
        "AUTO_TEST_NEEDS_ESCALATION",
    }
    unknown_markers = sorted(markers - known_markers)
    if unknown_markers:
        print(f"unknown fixture route: {unknown_markers}", file=sys.stderr)
        return 9
    if len(markers) != 1:
        print("fixture objective must select exactly one explicit route", file=sys.stderr)
        return 9
    marker = next(iter(markers))
    if marker == "AUTO_TEST_NEEDS_ESCALATION":
        envelope = {
            "workflow_status": "needs_escalation",
            "reason": "fixture requested planner escalation",
            "result": {},
        }
    else:
        preferred = {
            "AUTO_TEST_DESIGN": "design-swarm",
            "AUTO_TEST_REVIEW": "ultra-review",
            "AUTO_TEST_SWEEP": "repo-sweep",
            "AUTO_TEST_INVALID_CONSIDERED": "design-swarm",
        }[marker]
        if preferred not in eligible:
            print(f"fixture route preset is not eligible: {preferred}", file=sys.stderr)
            return 9
        selected = preferred
        considered = [
            {
                "preset": name,
                "fit": "best" if name == selected else "possible",
                "reason": f"fixture evaluation for {name}",
            }
            for name in eligible
        ]
        if marker == "AUTO_TEST_INVALID_CONSIDERED":
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
