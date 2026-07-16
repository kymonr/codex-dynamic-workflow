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

from team_router_broker_adapter import BROKER_CORE_THREAD_TOOL_METHODS, BrokerConfig, broker_host_readiness_snapshot, fetch_broker_readiness, validate_broker_config  # noqa: E402
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
    config = BrokerConfig(base_url=broker_url, session_token=session_token)
    try:
        validate_broker_config(config)
    except StateStoreError as exc:
        return 2, _blocked(["broker configuration"], str(exc))
    try:
        readiness = fetch_broker_readiness(config)
    except StateStoreError as exc:
        return 1, _blocked(["broker readiness"], str(exc))
    runtime_probe = readiness.get("runtimeProbe")
    runtime_probe_ready = (
        isinstance(runtime_probe, dict)
        and runtime_probe.get("status") == "ready"
        and isinstance(runtime_probe.get("missing"), list)
        and not runtime_probe.get("missing")
    )
    readiness_missing = readiness.get("missing")
    readiness_missing_clear = isinstance(readiness_missing, list) and not readiness_missing
    capabilities = readiness.get("capabilities") if isinstance(readiness.get("capabilities"), dict) else {}
    trusted_sender = readiness.get("trustedSenderProvenance") is True or capabilities.get("trusted_sender_provenance") is True
    trusted_domain = readiness.get("trustedExecutionDomain") is True or capabilities.get("trusted_execution_domain") is True
    core_tools_ready = all(capabilities.get(method_name) is True for method_name in BROKER_CORE_THREAD_TOOL_METHODS)
    status = "ready" if (
        readiness.get("status") == "ready"
        and readiness_missing_clear
        and runtime_probe_ready
        and trusted_sender
        and trusted_domain
        and core_tools_ready
    ) else "blocked"
    tier = "unattended_contract_ready" if status == "ready" and (
        readiness.get("schedulerReady") is True or capabilities.get("heartbeat_scheduler") is True
    ) else ("interactive_contract_ready" if status == "ready" else "manual/pre-created")
    report = {
        "mode": "read-only",
        "status": status,
        "tier": tier,
        "authorization": _authorization(),
        "runtimeProbe": readiness.get("runtimeProbe"),
        "readiness": readiness,
        "hostReadinessSnapshot": broker_host_readiness_snapshot(readiness),
    }
    if status != "ready":
        report["missing"] = list(readiness.get("missing", []))
        if not trusted_sender:
            report["missing"].append("trusted sender provenance")
        if not trusted_domain:
            report["missing"].append("trusted execution domain")
        for method_name in BROKER_CORE_THREAD_TOOL_METHODS:
            if capabilities.get(method_name) is not True:
                report["missing"].append("callable %s" % method_name)
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
