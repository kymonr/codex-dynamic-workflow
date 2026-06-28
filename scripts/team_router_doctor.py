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



ACTIVE_TURN_STATUSES = {"active", "inProgress", "running", "working"}
ROLE_PROTOCOL_MARKERS = {
    "manager": "TEAM_ROUTER_PLAN",
    "executor": "TEAM_ROUTER_CALLBACK",
    "reviewer": "TEAM_ROUTER_REVIEW",
    "verifier": "TEAM_ROUTER_VERDICT",
}


def _message_text(message: object) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        text = message.get("text")
        if isinstance(text, str):
            return text
        agent_message = message.get("agentMessage")
        if isinstance(agent_message, dict):
            agent_text = agent_message.get("text")
            if isinstance(agent_text, str):
                return agent_text
    return ""


def _role_messages(snapshot: dict[str, object]) -> list[str]:
    messages = snapshot.get("messages", [])
    if not isinstance(messages, list):
        return []
    return [_message_text(message) for message in messages]


def _has_marker(messages: list[str], marker: str) -> bool:
    return any(marker in message for message in messages)


def classify_role_thread_status(snapshot: dict[str, object]) -> dict[str, object]:
    role = str(snapshot.get("role") or "unknown")
    thread_id = snapshot.get("threadId")
    expected_marker = str(snapshot.get("expectedMarker") or ROLE_PROTOCOL_MARKERS.get(role, "TEAM_ROUTER_"))
    base = {"role": role, "threadId": thread_id, "expectedMarker": expected_marker}

    if not thread_id:
        return {
            **base,
            "status": "missing",
            "summary": "no role thread id recorded",
        }

    read_error = snapshot.get("readError")
    if read_error:
        return {
            **base,
            "status": "created_not_visible",
            "summary": "read_thread failed: %s" % read_error,
        }

    if snapshot.get("visible", True) is False:
        return {
            **base,
            "status": "created_not_visible",
            "summary": "thread id exists but is not visible/readable",
        }

    turn_status = snapshot.get("turnStatus")
    if turn_status in ACTIVE_TURN_STATUSES:
        return {
            **base,
            "status": "active_wait",
            "summary": "role thread has an active turn; wait before bounded read",
        }

    messages = _role_messages(snapshot)
    if _has_marker(messages, expected_marker):
        return {
            **base,
            "status": "protocol_returned",
            "summary": "expected protocol marker found",
        }

    return {
        **base,
        "status": "visible_waiting",
        "summary": "visible but no expected protocol marker",
    }


def classify_role_thread_status_snapshot(snapshot: dict[str, object] | list[dict[str, object]] | None) -> dict[str, object]:
    expected_markers: dict[str, object] = {}
    if snapshot is None:
        roles: list[dict[str, object]] = []
    elif isinstance(snapshot, list):
        roles = snapshot
    else:
        raw_expected = snapshot.get("expectedMarkers", {})
        expected_markers = raw_expected if isinstance(raw_expected, dict) else {}
        raw_roles = snapshot.get("roles", [])
        roles = raw_roles if isinstance(raw_roles, list) else []

    statuses = []
    for role_snapshot in roles:
        if not isinstance(role_snapshot, dict):
            continue
        normalized_role = dict(role_snapshot)
        role = str(normalized_role.get("role") or "")
        if "expectedMarker" not in normalized_role and role in expected_markers:
            normalized_role["expectedMarker"] = expected_markers[role]
        statuses.append(classify_role_thread_status(normalized_role))
    return {
        "mode": "read-only",
        "roles": statuses,
    }


def _load_role_status_snapshot(path: Path | None) -> dict[str, object] | list[dict[str, object]] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, (dict, list)):
        return data
    raise ValueError("role status snapshot must be a JSON object or array")


def build_doctor_report(
    repo_root: Path = team_router_truth_check.DEFAULT_REPO_ROOT,
    global_skill: Path = team_router_truth_check.DEFAULT_GLOBAL_SKILL,
    scan_files: list[Path] | None = None,
    role_status_snapshot: dict[str, object] | list[dict[str, object]] | None = None,
) -> dict[str, object]:
    truth = team_router_truth_check.build_truth_report(repo_root, global_skill, scan_files)
    truth_status = _truth_status(truth)
    next_action = _next_action(truth_status, truth)
    role_status = classify_role_thread_status_snapshot(role_status_snapshot)
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
        "roleThreadStatus": role_status,
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
    parser.add_argument("--role-status-json", type=Path, help="read-only JSON snapshot of role thread observations")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    role_status_snapshot = _load_role_status_snapshot(args.role_status_json)
    report = build_doctor_report(args.repo_root, args.global_skill, args.scan_file, role_status_snapshot)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
