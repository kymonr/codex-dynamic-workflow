# -*- coding: utf-8 -*-
"""Read-only feasibility check for a Team Router Codex Desktop broker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from team_router_broker_adapter import BrokerConfig, fetch_broker_readiness  # noqa: E402
from team_router_state import StateStoreError  # noqa: E402


def _authorization() -> dict[str, bool]:
    return {
        "desktopPluginChange": False,
        "commit": False,
        "push": False,
        "pullRequest": False,
        "merge": False,
        "deploy": False,
        "globalSync": False,
    }


def _blocked(missing: list[str], reason: str) -> dict[str, object]:
    return {
        "mode": "read-only",
        "status": "blocked",
        "missing": missing,
        "reason": reason,
        "authorization": _authorization(),
    }


def build_report(broker_url: str | None, session_token: str | None) -> tuple[int, dict[str, object]]:
    missing = []
    if not broker_url:
        missing.append("broker-url")
    if not session_token:
        missing.append("session-token")
    if missing:
        return 2, _blocked(missing, "broker URL and session token are required")
    try:
        readiness = fetch_broker_readiness(BrokerConfig(base_url=broker_url, session_token=session_token))
    except StateStoreError as exc:
        return 1, _blocked(["broker readiness"], str(exc))
    status = "ready" if readiness.get("status") == "ready" else "blocked"
    report = {
        "mode": "read-only",
        "status": status,
        "authorization": _authorization(),
        "runtimeProbe": readiness.get("runtimeProbe"),
        "readiness": readiness,
    }
    if status != "ready":
        report["missing"] = readiness.get("missing", [])
    return (0 if status == "ready" else 1), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Team Router broker feasibility without mutating Desktop state.")
    parser.add_argument("--broker-url")
    parser.add_argument("--session-token")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    code, report = build_report(args.broker_url, args.session_token)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("status: %s" % report["status"])
        if report["status"] != "ready":
            print("reason: %s" % report.get("reason", "broker readiness blocked"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())