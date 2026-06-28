# -*- coding: utf-8 -*-
"""Plain-language, read-only Team Router status report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import team_router_truth_check


def _truth_status(truth: dict[str, object]) -> str:
    dirty = bool(truth["gitStatusShort"] or truth["diffFiles"])
    stale = bool(truth["staleClaims"])
    if dirty and stale:
        return "dirty_or_stale"
    if dirty:
        return "dirty"
    if stale:
        return "stale"
    if truth["skillSync"]["status"] == "match":
        return "clean_synced"
    return "needs_attention"


def _next_action(truth_status: str, truth: dict[str, object]) -> str:
    if truth_status in {"dirty_or_stale", "stale"}:
        return "refresh workbench/package current-state docs from team_router_truth_check.py before claiming current truth"
    if truth_status == "dirty":
        return "review the local diff, run the required reviewer pass, then run the required verifier pass before closeout"
    if truth["skillSync"]["status"] != "match":
        return "decide whether global skill sync is explicitly authorized; do not sync by default"
    return "no action required unless the manager opens a new package"


def build_doctor_report(
    repo_root: Path = team_router_truth_check.DEFAULT_REPO_ROOT,
    global_skill: Path = team_router_truth_check.DEFAULT_GLOBAL_SKILL,
    scan_files: list[Path] | None = None,
) -> dict[str, object]:
    truth = team_router_truth_check.build_truth_report(repo_root, global_skill, scan_files)
    truth_status = _truth_status(truth)
    next_action = _next_action(truth_status, truth)
    summary = (
        "currentMode=read-only; "
        "truthStatus=%s; "
        "orchestrationStatus=manual_only; "
        "nextAction=%s; "
        "unauthorized=commit,push,PR,merge,deploy,global skill sync"
    ) % (truth_status, next_action)
    return {
        "mode": "read-only",
        "truthStatus": truth_status,
        "orchestrationStatus": "manual_only",
        "summary": summary,
        "authorization": truth["authorization"],
        "truth": truth,
    }


def _print_text_report(report: dict[str, object]) -> None:
    print("mode: %s" % report["mode"])
    print("truthStatus: %s" % report["truthStatus"])
    print("orchestrationStatus: %s" % report["orchestrationStatus"])
    print("summary: %s" % report["summary"])
    print("authorization: no commit, no push, no PR, no merge, no deploy, no global sync")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Team Router doctor/status report.")
    parser.add_argument("--repo-root", type=Path, default=team_router_truth_check.DEFAULT_REPO_ROOT)
    parser.add_argument("--global-skill", type=Path, default=team_router_truth_check.DEFAULT_GLOBAL_SKILL)
    parser.add_argument("--scan-file", type=Path, action="append", default=[])
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    report = build_doctor_report(args.repo_root, args.global_skill, args.scan_file)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

