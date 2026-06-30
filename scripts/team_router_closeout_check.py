# -*- coding: utf-8 -*-
"""Read-only Team Router local closeout status check."""
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
    ENTRYPOINT_RELATIVE,
    HARD_CAP_BYTES,
    SKILL_RELATIVE,
    TARGET_BYTES,
    build_closeout_report as build_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Team Router closeout status check.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--global-skill", type=Path, default=DEFAULT_GLOBAL_SKILL)
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    report = build_report(args.repo_root, args.global_skill)
    report["gitErrors"] = [item for item in report["gitErrors"] if item is not None]
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("mode: %s" % report["mode"])
        print("repoRoot: %s" % report["repoRoot"])
        print("gitStatusShort:")
        for line in report["gitStatusShort"]:
            print("  %s" % line)
        print("diffFiles:")
        for line in report["diffFiles"]:
            print("  %s" % line)
        print("skill.entrypointBytes: %s" % report["skill"]["entrypointBytes"])
        print("skill.underTarget: %s" % report["skill"]["underTarget"])
        print("skillSync.status: %s" % report["skillSync"]["status"])
        print("authorization: no commit, no push, no PR, no merge, no deploy, no global sync")
        print("readOnlyGuarantee: %s" % report["readOnlyGuarantee"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())