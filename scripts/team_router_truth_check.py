# -*- coding: utf-8 -*-
"""Read-only Team Router current-truth and stale-claim check."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from team_router_status_tools import (  # noqa: E402
    DEFAULT_GLOBAL_SKILL,
    DEFAULT_REPO_ROOT,
    DEFAULT_SCAN_FILES,
    DIRTY_DIFF_MARKERS,
    ENTRYPOINT_RELATIVE,
    HARD_CAP_BYTES,
    NEUTRAL_GATE_MARKERS,
    OLD_OPTIMIZATION_PACKAGE,
    PACKAGE_DATE_RE,
    PACKAGE_ID_RE,
    PENDING_GATE_MARKERS,
    SKILL_RELATIVE,
    TARGET_BYTES,
    ACTIVE_CURRENT_STATE_MARKERS,
    CURRENT_STATE_HEADINGS,
    build_truth_report,
    find_stale_state_claims,
)


def _print_text_report(report: dict[str, object]) -> None:
    print("mode: %s" % report["mode"])
    print("repoRoot: %s" % report["repoRoot"])
    print("gitStatusShort:")
    for line in report["gitStatusShort"]:
        print("  %s" % line)
    print("diffFiles:")
    for line in report["diffFiles"]:
        print("  %s" % line)
    print("skill.entrypointBytes: %s" % report["skill"]["entrypointBytes"])
    print("skillSync.status: %s" % report["skillSync"]["status"])
    print("staleClaims:")
    for claim in report["staleClaims"]:
        print("  %s: %s" % (claim["path"], claim["reason"]))
    print("authorization: no commit, no push, no PR, no merge, no deploy, no global sync")
    print("readOnlyGuarantee: %s" % report["readOnlyGuarantee"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Team Router current-truth and stale-claim check.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--global-skill", type=Path, default=DEFAULT_GLOBAL_SKILL)
    parser.add_argument("--scan-file", type=Path, action="append", default=[])
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    report = build_truth_report(args.repo_root, args.global_skill, args.scan_file)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())