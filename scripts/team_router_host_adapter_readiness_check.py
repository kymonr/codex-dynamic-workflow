#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only host-adapter readiness probe for Team Router.

This script proves whether caller-supplied host evidence can be shaped into
in-process Python callables for the Team Router adapter boundary. It never calls
the thread tools represented by the snapshot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import team_router  # noqa: E402
import team_router_doctor  # noqa: E402


REQUIRED_THREAD_TOOLS = tuple(getattr(team_router, "THREAD_TOOL_NAMES", (
    "list_projects",
    "create_thread",
    "list_threads",
    "read_thread",
    "send_message_to_thread",
    "set_thread_title",
)))


class SyntheticThreadAdapter:
    """Callable-shape adapter that refuses to execute represented tools."""

    def __init__(self, callable_tools: Mapping[str, bool], tool_descriptors: Mapping[str, Any] | None = None):
        self.calls: list[dict[str, Any]] = []
        descriptors = tool_descriptors or {}
        for tool_name in REQUIRED_THREAD_TOOLS:
            if bool(callable_tools.get(tool_name)):
                setattr(self, tool_name, self._forbidden_tool(tool_name))
            elif tool_name in descriptors:
                setattr(self, tool_name, descriptors[tool_name])

    def _forbidden_tool(self, tool_name: str):
        def _call(**kwargs: Any) -> dict[str, Any]:
            self.calls.append({"tool": tool_name, "kwargs": dict(kwargs)})
            raise RuntimeError("host adapter readiness check must not call thread tool: %s" % tool_name)

        return _call


class SyntheticHeartbeatScheduler:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def schedule(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        raise RuntimeError("host adapter readiness check must not schedule heartbeat")


def _load_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("host adapter snapshot must be a JSON object")
    return data


def _callable_tools(snapshot: Mapping[str, Any]) -> dict[str, bool]:
    raw = snapshot.get("callableTools")
    raw_tools = raw if isinstance(raw, Mapping) else {}
    return {tool_name: bool(raw_tools.get(tool_name)) for tool_name in REQUIRED_THREAD_TOOLS}


def _tool_descriptors(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = snapshot.get("toolDescriptors")
    return raw if isinstance(raw, Mapping) else {}


def _runtime_probe(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    raw = snapshot.get("runtimeProbe")
    if isinstance(raw, Mapping):
        return dict(raw)
    return {"status": "blocked", "missing": ["runtime readiness probe"]}


def host_readiness_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "source": snapshot.get("source", "host-adapter-readiness-check"),
        "codexAppThreadToolsExposed": bool(snapshot.get("codexAppThreadToolsExposed")) or bool(_tool_descriptors(snapshot)),
        "adapterCallable": bool(snapshot.get("adapterCallable")),
        "callableTools": _callable_tools(snapshot),
        "parentThreadId": str(snapshot.get("parentThreadId") or snapshot.get("parent_thread_id") or "").strip(),
        "heartbeatSchedulerCallable": bool(snapshot.get("heartbeatSchedulerCallable")),
        "runtimeProbe": _runtime_probe(snapshot),
    }


def build_report(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    host_snapshot = host_readiness_snapshot(snapshot)
    if snapshot is None or host_snapshot is None:
        doctor_host = team_router_doctor.classify_host_readiness_snapshot(None)
        return {
            "mode": "read-only",
            "status": "not_supplied",
            "orchestrationStatus": "manual_only",
            "adapterInjection": {
                "source": None,
                "pythonCallableAdapter": False,
                "threadToolCallsExecuted": 0,
                "heartbeatSchedulesExecuted": 0,
            },
            "readiness": {
                "status": "blocked",
                "missing": ["host adapter snapshot"],
                "capabilities": {**{tool: False for tool in REQUIRED_THREAD_TOOLS}, "heartbeat_scheduler": False},
                "reason": "host adapter snapshot is required to prove Python callable injection",
            },
            "hostReadinessSnapshot": None,
            "doctorHostReadiness": doctor_host,
            "summary": "no host adapter snapshot supplied; cannot prove Python callable injection",
            "boundary": "read-only; no thread tools are called",
        }

    adapter_callable = bool(host_snapshot["adapterCallable"])
    adapter = SyntheticThreadAdapter(host_snapshot["callableTools"], _tool_descriptors(snapshot)) if adapter_callable else None
    scheduler_callable = bool(host_snapshot["heartbeatSchedulerCallable"])
    scheduler = SyntheticHeartbeatScheduler() if scheduler_callable else None
    readiness = team_router.assess_live_orchestration_readiness(
        adapter,
        parent_thread_id=host_snapshot["parentThreadId"],
        heartbeat_scheduler=scheduler,
    )
    doctor_host = team_router_doctor.classify_host_readiness_snapshot(host_snapshot)
    thread_calls = len(adapter.calls) if adapter is not None else 0
    scheduler_calls = len(scheduler.calls) if scheduler is not None else 0
    return {
        "mode": "read-only",
        "status": doctor_host["status"],
        "orchestrationStatus": doctor_host["orchestrationStatus"],
        "adapterInjection": {
            "source": host_snapshot.get("source"),
            "pythonCallableAdapter": adapter_callable,
            "threadToolCallsExecuted": thread_calls,
            "heartbeatSchedulesExecuted": scheduler_calls,
        },
        "readiness": readiness,
        "hostReadinessSnapshot": host_snapshot,
        "doctorHostReadiness": doctor_host,
        "summary": (
            "host adapter snapshot proves Python callable injection without executing thread tools"
            if doctor_host["status"] == "ready"
            else "host adapter snapshot does not prove Python callable injection"
        ),
        "boundary": "read-only; no thread tools are called",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Team Router host adapter readiness check.")
    parser.add_argument("--adapter-snapshot-json", type=Path, help="JSON evidence for host adapter injectable callables")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)

    try:
        report = build_report(_load_snapshot(args.adapter_snapshot_json))
    except Exception as exc:  # pragma: no cover - defensive CLI boundary.
        print("host adapter readiness check failed: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("status: %s" % report["status"])
        print("orchestrationStatus: %s" % report["orchestrationStatus"])
        print("summary: %s" % report["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
