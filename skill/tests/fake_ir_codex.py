#!/usr/bin/env python3
"""Offline codex-exec stand-in for trusted Workflow IR integration tests."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path


SLOW_FIXTURE_SECONDS = 0.05


def option(name: str) -> str:
    index = sys.argv.index(name)
    return sys.argv[index + 1]


def _write_envelope(output_path: Path, *, status: str, result: object, reason: str) -> None:
    output_path.write_text(
        json.dumps(
            {
                "workflow_status": status,
                "reason": reason,
                "result": result,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _has_upstream(prompt: str, task_id: str) -> bool:
    return bool(
        re.search(
            rf'<UPSTREAM_(?:RESULT|ARTIFACT_REFERENCE)\b[^>]*\btask_id="{re.escape(task_id)}">',
            prompt,
        )
    )


def _loop_scenario(prompt: str, marker: str) -> tuple[str, int]:
    match = re.search(
        rf"\b{re.escape(marker)}\s+scenario=([a-z_]+)\s+ITER=(\d+)\b",
        prompt,
    )
    if match is None:
        raise ValueError(f"malformed {marker} marker")
    if "<BOUNDED_LOOP_HOST_RESULTS_V1>" not in prompt:
        raise ValueError(f"{marker} is missing host result marker")
    return match.group(1), int(match.group(2))


def main() -> int:
    output_path = Path(option("-o"))
    prompt_arg = sys.argv[sys.argv.index("--") + 1]
    prompt = sys.stdin.read() if prompt_arg == "-" else prompt_arg

    if "BOUNDED_LOOP_INITIAL" in prompt:
        result = "initial-fixture"
    elif "BOUNDED_LOOP_REVISE" in prompt:
        try:
            scenario, iteration = _loop_scenario(prompt, "BOUNDED_LOOP_REVISE")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if scenario not in {
            "reject_accept",
            "unknown",
            "identical_candidate",
            "slow_deadline",
            "interrupt",
        }:
            print(f"unknown bounded loop scenario: {scenario}", file=sys.stderr)
            return 2
        if scenario == "interrupt":
            _write_envelope(
                output_path,
                status="needs_escalation",
                result={"candidate": "", "changes": []},
                reason="offline bounded loop interrupt fixture",
            )
            return 0
        if scenario == "slow_deadline":
            time.sleep(SLOW_FIXTURE_SECONDS)
        candidate = (
            "identical-candidate"
            if scenario == "identical_candidate"
            else f"candidate-{iteration}"
        )
        changes = (
            ["identical-change"]
            if scenario == "identical_candidate"
            else [f"iteration-{iteration}"]
        )
        result = {"candidate": candidate, "changes": changes}
    elif "BOUNDED_LOOP_VERIFY" in prompt:
        try:
            scenario, iteration = _loop_scenario(prompt, "BOUNDED_LOOP_VERIFY")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if scenario == "slow_deadline":
            time.sleep(SLOW_FIXTURE_SECONDS)
        if scenario == "unknown":
            verdict = "unknown"
        elif scenario in {"identical_candidate", "slow_deadline"}:
            verdict = "reject"
        elif scenario == "reject_accept":
            verdict = "reject" if iteration == 1 else "accept"
        elif scenario == "interrupt":
            _write_envelope(
                output_path,
                status="needs_escalation",
                result={
                    "verdict": "unknown",
                    "summary": "offline bounded loop interrupt fixture",
                    "evidence": [],
                },
                reason="offline bounded loop interrupt fixture",
            )
            return 0
        else:
            print(f"unknown bounded loop scenario: {scenario}", file=sys.stderr)
            return 2
        result = {
            "verdict": verdict,
            "summary": f"bounded-loop-{scenario}-{iteration}",
            "evidence": ["offline bounded loop fixture"],
        }
    elif "IR_DISCOVER" in prompt:
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
    elif "IR_GATE_CANDIDATE" in prompt:
        result = "gate candidate fixture"
    elif "IR_GATE_ACCEPT" in prompt:
        result = "accepted gate fixture"
    elif "IR_GATE_REJECT" in prompt:
        result = "rejected gate fixture"
    elif "IR_GATE_JOIN" in prompt:
        result = "terminal gate fixture"
    elif "REFERENCE_DISCOVER" in prompt:
        result = [
            {
                "name": f"module-{index}",
                "path": f"src/module_{index}.py",
                "reason": "bounded fixture module",
            }
            for index in range(6)
        ]
    elif "REFERENCE_MAP" in prompt:
        result = {
            "module": "fixture-module",
            "findings": [
                {
                    "severity": "none",
                    "summary": "fixture audit is clean",
                    "evidence": ["offline fixture"],
                }
            ],
        }
    elif "REFERENCE_VERIFY" in prompt:
        result = {
            "verdict": "accept",
            "summary": "fixture evidence verified",
            "evidence": ["offline fixture"],
        }
    elif "REFERENCE_REDUCE" in prompt:
        result = {
            "verdict": "clean_candidate",
            "summary": "verified audit fixture",
            "blockers": [],
            "next_actions": ["review gate"],
        }
    elif "REFERENCE_PREPARE_CLEAN" in prompt:
        result = "clean-candidate review fixture"
    elif "REFERENCE_PREPARE_BLOCKER" in prompt:
        result = "blocker review fixture"
    elif "REFERENCE_RECORD_ACCEPTED" in prompt or "REFERENCE_RECORD_REJECTED" in prompt:
        is_accepted = "REFERENCE_RECORD_ACCEPTED" in prompt
        required_inputs = ("review-gate", "summarize-audit")
        missing = [
            task_id for task_id in required_inputs if not _has_upstream(prompt, task_id)
        ]
        if missing:
            _write_envelope(
                output_path,
                status="needs_escalation",
                result="",
                reason="record prompt is missing required upstream input: "
                + ", ".join(missing),
            )
            print("record fixture requires gate and summary inputs", file=sys.stderr)
            return 0
        result = {
            "decision": "approve" if is_accepted else "reject",
            "summary": "recorded accepted fixture"
            if is_accepted
            else "recorded rejected fixture",
            "evidence": ["gate decision", "verified audit"],
            "next_actions": ["publish closeout" if is_accepted else "address blockers"],
        }
    elif "REFERENCE_FINALIZE_ACCEPTED" in prompt or "REFERENCE_FINALIZE_REJECTED" in prompt:
        is_accepted = "REFERENCE_FINALIZE_ACCEPTED" in prompt
        record_id = "record-accepted" if is_accepted else "record-rejected"
        if not _has_upstream(prompt, record_id):
            _write_envelope(
                output_path,
                status="needs_escalation",
                result="",
                reason="finalizer prompt is missing selected record input: " + record_id,
            )
            print("finalizer fixture requires selected record input", file=sys.stderr)
            return 0
        result = {
            "status": "accepted" if is_accepted else "rejected",
            "decision": "approve" if is_accepted else "reject",
            "summary": "finalized accepted fixture"
            if is_accepted
            else "finalized rejected fixture",
            "evidence": ["record fixture"],
            "next_actions": ["closeout complete"],
            "uncertainty": [],
        }
    else:
        print(
            "unknown fake_ir_codex prompt marker; refusing catch-all success",
            file=sys.stderr,
        )
        return 2

    _write_envelope(
        output_path,
        status="ok",
        reason="offline IR fixture",
        result=result,
    )
    print("64 tokens used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
