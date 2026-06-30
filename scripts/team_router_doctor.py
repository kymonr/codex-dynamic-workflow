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
SRC_DIR = SCRIPT_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import team_router_status_tools
import team_router_truth_check

try:
    import team_router as team_router_core
except ImportError:  # pragma: no cover - fallback for partial script copies.
    team_router_core = None


REQUIRED_THREAD_TOOLS = tuple(
    getattr(
        team_router_core,
        "THREAD_TOOL_NAMES",
        (
            "list_projects",
            "create_thread",
            "list_threads",
            "read_thread",
            "send_message_to_thread",
            "set_thread_title",
        ),
    )
)


_truth_status = team_router_status_tools.truth_status
_next_action = team_router_status_tools.next_action


ACTIVE_TURN_STATUSES = {"active", "inProgress", "running", "working"}
ROLE_PROTOCOL_MARKERS = {
    "manager": "TEAM_ROUTER_PLAN",
    "executor": "TEAM_ROUTER_CALLBACK",
    "reviewer": "TEAM_ROUTER_REVIEW",
    "verifier": "TEAM_ROUTER_VERDICT",
}
TRUE_VALUES = {"1", "true", "yes", "y", "available", "callable", "exposed", "ready"}


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in TRUE_VALUES
    return False


def _first_present(snapshot: dict[str, object], names: tuple[str, ...]) -> object:
    for name in names:
        if name in snapshot:
            return snapshot[name]
    return None


def _callable_tool_capabilities(snapshot: dict[str, object]) -> dict[str, bool]:
    raw = _first_present(snapshot, ("callableTools", "callable_tools", "pythonCallableTools"))
    if isinstance(raw, dict):
        return {tool: _as_bool(raw.get(tool)) for tool in REQUIRED_THREAD_TOOLS}
    if isinstance(raw, list):
        names = {str(item) for item in raw}
        return {tool: tool in names for tool in REQUIRED_THREAD_TOOLS}
    return {tool: False for tool in REQUIRED_THREAD_TOOLS}


def _thread_tool_surface_exposed(snapshot: dict[str, object]) -> bool:
    if _as_bool(
        _first_present(
            snapshot,
            (
                "codexAppThreadToolsExposed",
                "appThreadToolsExposed",
                "modelSideThreadToolsExposed",
                "threadToolSurfaceExposed",
            ),
        )
    ):
        return True
    raw_tools = _first_present(snapshot, ("codexAppThreadTools", "appThreadTools", "modelSideThreadTools"))
    if isinstance(raw_tools, dict):
        return any(_as_bool(value) for value in raw_tools.values())
    if isinstance(raw_tools, list):
        return bool(raw_tools)
    return False


def _heartbeat_scheduler_callable(snapshot: dict[str, object]) -> bool:
    direct = _first_present(
        snapshot,
        (
            "heartbeatSchedulerCallable",
            "heartbeat_scheduler_callable",
            "schedulerCallable",
        ),
    )
    if _as_bool(direct):
        return True
    heartbeat = _first_present(snapshot, ("heartbeatScheduler", "heartbeat_scheduler", "scheduler"))
    if isinstance(heartbeat, dict):
        return _as_bool(heartbeat.get("callable") or heartbeat.get("scheduleCallable"))
    return False


def classify_host_readiness_snapshot(snapshot: dict[str, object] | None) -> dict[str, object]:
    if snapshot is None:
        capabilities = {tool: False for tool in REQUIRED_THREAD_TOOLS}
        capabilities["heartbeat_scheduler"] = False
        return {
            "mode": "read-only",
            "status": "not_supplied",
            "orchestrationStatus": "manual_only",
            "missing": [],
            "capabilities": capabilities,
            "summary": "no host readiness snapshot supplied; manual orchestration only",
            "boundary": "evidence-only; no thread tools are called by doctor",
        }
    tool_capabilities = _callable_tool_capabilities(snapshot)
    heartbeat_callable = _heartbeat_scheduler_callable(snapshot)
    parent_thread_id = str(_first_present(snapshot, ("parentThreadId", "parent_thread_id")) or "").strip()
    adapter_callable = _as_bool(_first_present(snapshot, ("adapterCallable", "callableAdapter", "pythonCallableAdapter")))
    tool_surface_exposed = _thread_tool_surface_exposed(snapshot)
    missing = []
    if not adapter_callable:
        missing.append("callable adapter")
    for tool_name, is_callable in tool_capabilities.items():
        if not is_callable:
            missing.append("callable %s" % tool_name)
    if not parent_thread_id:
        missing.append("parent_thread_id")
    if not heartbeat_callable:
        missing.append("callable heartbeat scheduler")
    status = "ready" if not missing else "blocked"
    orchestration_status = "adapter_smoke_ready" if status == "ready" else "host_contract_blocked"
    capabilities = dict(tool_capabilities)
    capabilities["heartbeat_scheduler"] = heartbeat_callable
    return {
        "mode": "read-only",
        "status": status,
        "orchestrationStatus": orchestration_status,
        "missing": missing,
        "capabilities": capabilities,
        "evidence": {
            "threadToolSurfaceExposed": tool_surface_exposed,
            "parentThreadIdPresent": bool(parent_thread_id),
            "adapterCallable": adapter_callable,
            "heartbeatSchedulerCallable": heartbeat_callable,
        },
        "summary": (
            "host readiness evidence supports adapter heartbeat smoke path"
            if status == "ready"
            else "host readiness evidence supplied but live orchestration requires " + ", ".join(missing)
        ),
        "boundary": "evidence-only; model-side Codex app tool exposure is not a Python callable adapter",
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


def _load_host_readiness_snapshot(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return data
    raise ValueError("host readiness snapshot must be a JSON object")


def build_doctor_report(
    repo_root: Path = team_router_truth_check.DEFAULT_REPO_ROOT,
    global_skill: Path = team_router_truth_check.DEFAULT_GLOBAL_SKILL,
    scan_files: list[Path] | None = None,
    role_status_snapshot: dict[str, object] | list[dict[str, object]] | None = None,
    host_readiness_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    truth = team_router_truth_check.build_truth_report(repo_root, global_skill, scan_files)
    truth_status = _truth_status(truth)
    next_action = _next_action(truth_status, truth)
    role_status = classify_role_thread_status_snapshot(role_status_snapshot)
    host_readiness = classify_host_readiness_snapshot(host_readiness_snapshot)
    orchestration_status = str(host_readiness["orchestrationStatus"])
    summary = (
        "currentMode=read-only; "
        "truthStatus=%s; "
        "orchestrationStatus=%s; "
        "hostReadiness=%s; "
        "nextAction=%s; "
        "unauthorized=commit,push,PR,merge,deploy,global skill sync"
    ) % (truth_status, orchestration_status, host_readiness["status"], next_action)
    return {
        "mode": "read-only",
        "truthStatus": truth_status,
        "orchestrationStatus": orchestration_status,
        "summary": summary,
        "nextAction": next_action,
        "authorization": truth["authorization"],
        "roleThreadStatus": role_status,
        "hostReadiness": host_readiness,
        "truth": truth,
    }


def _print_text_report(report: dict[str, object]) -> None:
    print("mode: %s" % report["mode"])
    print("truthStatus: %s" % report["truthStatus"])
    print("orchestrationStatus: %s" % report["orchestrationStatus"])
    print("hostReadiness: %s" % report["hostReadiness"]["summary"])
    print("summary: %s" % report["summary"])
    print("authorization: no commit, no push, no PR, no merge, no deploy, no global sync")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Team Router doctor/status report.")
    parser.add_argument("--repo-root", type=Path, default=team_router_truth_check.DEFAULT_REPO_ROOT)
    parser.add_argument("--global-skill", type=Path, default=team_router_truth_check.DEFAULT_GLOBAL_SKILL)
    parser.add_argument("--scan-file", type=Path, action="append", default=[])
    parser.add_argument("--role-status-json", type=Path, help="read-only JSON snapshot of role thread observations")
    parser.add_argument("--host-readiness-json", type=Path, help="read-only JSON snapshot of host adapter readiness evidence")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    role_status_snapshot = _load_role_status_snapshot(args.role_status_json)
    host_readiness_snapshot = _load_host_readiness_snapshot(args.host_readiness_json)
    report = build_doctor_report(
        args.repo_root,
        args.global_skill,
        args.scan_file,
        role_status_snapshot,
        host_readiness_snapshot,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())