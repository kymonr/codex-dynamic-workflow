# -*- coding: utf-8 -*-
"""Read-only dry-run check for automatic Team Router runtime wiring."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parent / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import team_router_doctor  # noqa: E402
from team_router_broker_adapter import (  # noqa: E402
    BROKER_THREAD_TOOL_METHODS,
    BrokerConfig,
    broker_host_context_kwargs,
    broker_host_readiness_snapshot,
    fetch_broker_readiness,
    validate_broker_config,
)
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


def _dry_run() -> dict[str, object]:
    return {
        "callsExecuted": ["GET /readiness"],
        "threadToolCallsExecuted": [],
        "threadToolCallsNotExecuted": list(BROKER_THREAD_TOOL_METHODS),
        "liveRoleDispatch": False,
    }


def _manager_startup_path(injection: str, host_context_keys: list[str] | None = None) -> dict[str, object]:
    return {
        "caller": "manager runtime entrypoint",
        "brokerArgs": ["--broker-url", "--session-token"],
        "readinessGate": "hostReadiness.status must be ready before automatic entry",
        "adapterFactory": "broker_host_context_kwargs(BrokerConfig(...))",
        "orchestratorCall": "orchestrate_team_task_with_adapter(..., host_context=host_context)",
        "injection": injection,
        "hostContextKeys": host_context_keys or [],
    }


def _manual_report(missing: list[str], reason: str, *, orchestration_status: str = "manual/pre-created") -> dict[str, object]:
    return {
        "mode": "read-only",
        "status": "manual_only",
        "orchestrationStatus": orchestration_status,
        "automaticEntryAllowed": False,
        "missing": missing,
        "reason": reason,
        "authorization": _authorization(),
        "dryRun": {
            "callsExecuted": [],
            "threadToolCallsExecuted": [],
            "threadToolCallsNotExecuted": list(BROKER_THREAD_TOOL_METHODS),
            "liveRoleDispatch": False,
        },
        "managerStartupPath": _manager_startup_path("blocked"),
    }


def build_report(broker_url: str | None, session_token: str | None) -> tuple[int, dict[str, object]]:
    missing = []
    if not broker_url:
        missing.append("broker-url")
    if not session_token:
        missing.append("session-token")
    if missing:
        return 2, _manual_report(missing, "broker URL and session token are required")

    config = BrokerConfig(base_url=broker_url, session_token=session_token)
    try:
        validate_broker_config(config)
    except StateStoreError as exc:
        return 2, _manual_report(["broker configuration"], str(exc))
    try:
        readiness = fetch_broker_readiness(config)
    except StateStoreError as exc:
        return 1, _manual_report(["broker readiness"], str(exc))

    host_snapshot = broker_host_readiness_snapshot(readiness)
    host_readiness = team_router_doctor.classify_host_readiness_snapshot(host_snapshot)
    orchestration_status = str(host_readiness["orchestrationStatus"])
    if host_readiness["status"] != "ready":
        return 1, {
            "mode": "read-only",
            "status": "manual_only",
            "orchestrationStatus": orchestration_status,
            "automaticEntryAllowed": False,
            "missing": list(host_readiness.get("missing", [])),
            "reason": host_readiness.get("summary", "host readiness blocked"),
            "authorization": _authorization(),
            "readiness": readiness,
            "hostReadiness": host_readiness,
            "hostReadinessSnapshot": host_snapshot,
            "dryRun": _dry_run(),
            "managerStartupPath": _manager_startup_path("blocked"),
        }

    try:
        host_context_kwargs = broker_host_context_kwargs(config)
    except StateStoreError as exc:
        return 1, {
            "mode": "read-only",
            "status": "manual_only",
            "orchestrationStatus": "manual/pre-created",
            "automaticEntryAllowed": False,
            "missing": ["host_context"],
            "reason": str(exc),
            "authorization": _authorization(),
            "readiness": readiness,
            "hostReadiness": host_readiness,
            "hostReadinessSnapshot": host_snapshot,
            "dryRun": _dry_run(),
            "managerStartupPath": _manager_startup_path("blocked"),
        }

    return 0, {
        "mode": "read-only",
        "status": "ready",
        "orchestrationStatus": orchestration_status,
        "automaticEntryAllowed": True,
        "missing": [],
        "reason": "broker host readiness allows automatic manager runtime entry",
        "authorization": _authorization(),
        "readiness": readiness,
        "hostReadiness": host_readiness,
        "hostReadinessSnapshot": host_snapshot,
        "dryRun": _dry_run(),
        "managerStartupPath": _manager_startup_path("host_context", sorted(host_context_kwargs.keys())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run Team Router automatic runtime wiring without thread-tool mutation.")
    parser.add_argument("--broker-url")
    parser.add_argument("--session-token")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    code, report = build_report(args.broker_url, args.session_token)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("status: %s" % report["status"])
        print("orchestrationStatus: %s" % report["orchestrationStatus"])
        print("automaticEntryAllowed: %s" % report["automaticEntryAllowed"])
        if report["status"] != "ready":
            print("reason: %s" % report.get("reason", "runtime wiring blocked"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
