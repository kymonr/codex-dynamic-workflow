# -*- coding: utf-8 -*-
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _test_tmp_root():
    configured = os.environ.get("TEAM_ROUTER_TEST_TMP_ROOT")
    if configured:
        return Path(configured)
    if os.name == "nt":
        return Path("C:/tmp/team-router-test-tmp")
    return ROOT / "test-tmp" / "test_team_router"


TEST_TMP_ROOT = _test_tmp_root()


class _WorkspaceTempDir:
    def __init__(self, suffix=None, prefix=None, dir=None):
        self.root = Path(dir) if dir is not None else TEST_TMP_ROOT
        dirname = "%s%s%s" % (prefix or "tmp", uuid.uuid4().hex, suffix or "")
        self.name = str(self.root / dirname)

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        Path(self.name).mkdir(parents=True, exist_ok=False)
        return self.name

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False

    def cleanup(self):
        shutil.rmtree(self.name, ignore_errors=True)


def workspace_temp_dir():
    return _WorkspaceTempDir()

_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import team_router
import team_router_state
import team_router_policy
import team_router_protocol
import team_router_direct_return
import team_router_v2
import team_router_watcher_runtime


class FakeThreadAdapter:
    def __init__(self):
        self.created = []
        self.sent = []
        self.renamed = []
        self.messages = {}
        self.create_error = None
        self.send_error = None
        self._thread_count = 0
        self._message_count = 0

    def create_thread(self, **kwargs):
        if self.create_error is not None:
            raise self.create_error
        prompt = kwargs["prompt"]
        role = "role"
        for line in prompt.splitlines():
            match = re.match(r"^\s*role\s*:\s*(manager|executor|reviewer|verifier|architect|qa)\s*$", line, re.IGNORECASE)
            if match:
                role = match.group(1).lower()
                break
        else:
            for candidate in ("manager", "executor", "verifier", "reviewer"):
                if candidate in prompt:
                    role = candidate
                    break
        self._thread_count += 1
        thread_id = "thread-%s" % role
        self.messages[thread_id] = []
        record = {"threadId": thread_id, "title": "TeamRouter %s" % role}
        self.created.append({"kwargs": kwargs, "result": record})
        return record

    def send_message_to_thread(self, **kwargs):
        if self.send_error is not None:
            raise self.send_error
        self._message_count += 1
        message_id = "msg-%02d" % self._message_count
        sent_at = "2026-06-22T20:%02d:00+08:00" % self._message_count
        message = {
            "messageId": message_id,
            "sentAt": sent_at,
            "text": kwargs["prompt"],
        }
        self.messages.setdefault(kwargs["threadId"], []).append(message)
        self.sent.append({"kwargs": kwargs, "result": message})
        return {"message": {"id": message_id, "createdAt": sent_at}}

    def read_thread(self, **kwargs):
        return {"thread": {"messages": list(self.messages.get(kwargs["threadId"], []))}}

    def set_thread_title(self, **kwargs):
        self.renamed.append(dict(kwargs))
        return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

    def append_reply(self, thread_id, text, *, message_id, sent_at):
        self.messages.setdefault(thread_id, []).append({
            "messageId": message_id,
            "sentAt": sent_at,
            "text": text,
        })


class FullThreadAdapter(FakeThreadAdapter):
    def list_projects(self, **kwargs):
        return {"projects": []}

    def list_threads(self, **kwargs):
        return {"threads": []}

    def set_thread_title(self, **kwargs):
        self.renamed.append(dict(kwargs))
        return {"threadId": kwargs["threadId"], "title": kwargs["title"]}


class FakeHeartbeatScheduler:
    def __init__(self):
        self.scheduled = []

    def schedule(self, **kwargs):
        self.scheduled.append(dict(kwargs))
        return {"scheduled": True}


class _FakeBrokerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    routes = {}
    calls = []

    def log_message(self, format, *args):
        return

    def _write_response(self, status, response):
        body = response
        content_type = "application/json"
        if isinstance(response, dict) and "__raw__" in response:
            raw = response["__raw__"]
            body = raw.encode("utf-8") if isinstance(raw, str) else raw
            content_type = response.get("content_type", "application/octet-stream")
        else:
            body = json.dumps(response).encode("utf-8")
            content_type = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body)
        self.__class__.calls.append({"method": "POST", "path": self.path, "payload": payload})
        status, response = self.__class__.routes.get(
            self.path,
            (404, {"ok": False, "error": {"message": self.path}}),
        )
        self._write_response(status, response)

    def do_GET(self):
        self.__class__.calls.append({"method": "GET", "path": self.path, "payload": None, "headers": dict(self.headers)})
        status, response = self.__class__.routes.get(
            self.path,
            (404, {"ok": False, "error": {"message": self.path}}),
        )
        self._write_response(status, response)


@contextmanager
def fake_broker(routes):
    handler = type("FakeBrokerHandler", (_FakeBrokerHandler,), {"routes": dict(routes), "calls": []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_address[1], handler.calls
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


class TestTeamRouterBrokerAdapter(unittest.TestCase):
    def test_broker_request_posts_json_with_session_token_and_request_id(self):
        import team_router_broker_adapter

        with fake_broker({
            "/thread-tools/list_projects": (200, {"ok": True, "result": {"projects": []}}),
        }) as (base_url, calls):
            config = team_router_broker_adapter.BrokerConfig(
                base_url=base_url,
                session_token="session-123",
                timeout_ms=1000,
            )
            result = team_router_broker_adapter.broker_request(
                config,
                "/thread-tools/list_projects",
                {"timeoutMs": 1000},
            )

        self.assertEqual(result, {"projects": []})
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["path"], "/thread-tools/list_projects")
        self.assertEqual(calls[0]["payload"]["sessionToken"], "session-123")
        self.assertIn("requestId", calls[0]["payload"])

    def test_broker_request_get_allowed_only_for_readiness(self):
        import team_router_broker_adapter

        readiness = {"status": "blocked", "runtimeProbe": {"status": "blocked", "missing": ["parent_thread_id"]}}
        with fake_broker({
            "/readiness": (200, {"ok": True, "result": readiness}),
        }) as (base_url, calls):
            config = team_router_broker_adapter.BrokerConfig(
                base_url=base_url,
                session_token="session-123",
                timeout_ms=1000,
            )
            result = team_router_broker_adapter.broker_request(config, "/readiness", method="GET")

        self.assertEqual(result, readiness)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(calls[0]["path"], "/readiness")
        self.assertIsNone(calls[0]["payload"])
        self.assertIn("X-Request-Id", calls[0]["headers"])
        self.assertEqual(calls[0]["headers"]["X-Session-Token"], "session-123")
        self.assertEqual(calls[0]["headers"]["X-Timeout-Ms"], "1000")

    def test_broker_request_rejects_get_for_thread_tools_and_scheduler_wake(self):
        import team_router_broker_adapter

        with fake_broker({}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            for path in ("/thread-tools/list_projects", "/scheduler/wake"):
                with self.subTest(path=path):
                    with self.assertRaises(team_router_broker_adapter.BrokerProtocolError) as ctx:
                        team_router_broker_adapter.broker_request(
                            config,
                            path,
                            {"callback": "watch_team_task_with_adapter"} if path == "/scheduler/wake" else {},
                            method="GET",
                        )
                    self.assertIn("broker HTTP method not allowed", str(ctx.exception))

    def test_broker_request_rejects_non_localhost_base_url(self):
        import team_router_broker_adapter

        config = team_router_broker_adapter.BrokerConfig(
            base_url="https://example.com:443",
            session_token="session-123",
        )
        with self.assertRaises(team_router_broker_adapter.BrokerProtocolError) as ctx:
            team_router_broker_adapter.broker_request(config, "/thread-tools/list_projects", {})

        self.assertIsInstance(ctx.exception, team_router.StateStoreError)
        self.assertIn("localhost broker", str(ctx.exception))

    def test_broker_request_rejects_unknown_thread_tool_path(self):
        import team_router_broker_adapter

        with fake_broker({}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router_broker_adapter.BrokerProtocolError) as ctx:
                team_router_broker_adapter.broker_request(config, "/thread-tools/delete_thread", {})

        self.assertIsInstance(ctx.exception, team_router.StateStoreError)
        self.assertIn("broker method not allowed", str(ctx.exception))

    def test_broker_heartbeat_scheduler_posts_only_allowed_watcher_callback(self):
        import team_router_broker_adapter

        with fake_broker({
            "/scheduler/wake": (200, {"ok": True, "result": {"scheduled": True}}),
        }) as (base_url, calls):
            scheduler = team_router_broker_adapter.BrokerHeartbeatScheduler(
                team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            )
            result = scheduler.schedule(
                callback="watch_team_task_with_adapter",
                runAt="2026-07-01T10:05:00+08:00",
                kwargs={"task_id": "task-1"},
            )

        self.assertEqual(result, {"scheduled": True})
        self.assertEqual(calls[0]["path"], "/scheduler/wake")
        self.assertEqual(calls[0]["payload"]["callback"], "watch_team_task_with_adapter")

    def test_broker_heartbeat_scheduler_rejects_arbitrary_callback(self):
        import team_router_broker_adapter

        with fake_broker({}) as (base_url, _calls):
            scheduler = team_router_broker_adapter.BrokerHeartbeatScheduler(
                team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            )
            with self.assertRaises(team_router.StateStoreError) as ctx:
                scheduler.schedule(callback="run_arbitrary_python", runAt="2026-07-01T10:05:00+08:00")

        self.assertIn("scheduler callback not allowed", str(ctx.exception))

    def test_broker_request_rejects_scheduler_wake_arbitrary_callback(self):
        import team_router_broker_adapter

        with fake_broker({}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router.StateStoreError) as ctx:
                team_router_broker_adapter.broker_request(
                    config,
                    "/scheduler/wake",
                    {"callback": "run_arbitrary_python", "runAt": "2026-07-01T10:05:00+08:00"},
                )

        self.assertIn("scheduler callback not allowed", str(ctx.exception))

    def test_broker_request_rejects_scheduler_wake_mixed_callback_fields(self):
        import team_router_broker_adapter

        with fake_broker({}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router.StateStoreError) as ctx:
                team_router_broker_adapter.broker_request(
                    config,
                    "/scheduler/wake",
                    {
                        "callback": "watch_team_task_with_adapter",
                        "managerAction": "run_arbitrary_python",
                        "runAt": "2026-07-01T10:05:00+08:00",
                    },
                )

        self.assertIn("scheduler callback not allowed: run_arbitrary_python", str(ctx.exception))

    def test_broker_request_rejects_non_json_response(self):
        import team_router_broker_adapter

        with fake_broker({
            "/thread-tools/list_projects": (200, {"__raw__": "not json", "content_type": "text/plain"}),
        }) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router_broker_adapter.BrokerProtocolError) as ctx:
                team_router_broker_adapter.broker_request(config, "/thread-tools/list_projects", {})

        self.assertIsInstance(ctx.exception, team_router.StateStoreError)
        self.assertEqual(str(ctx.exception), "broker response must be JSON")

    def test_broker_request_rejects_json_non_object_response(self):
        import team_router_broker_adapter

        with fake_broker({
            "/thread-tools/list_projects": (200, ["not", "an", "object"]),
        }) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router_broker_adapter.BrokerProtocolError) as ctx:
                team_router_broker_adapter.broker_request(config, "/thread-tools/list_projects", {})

        self.assertIsInstance(ctx.exception, team_router.StateStoreError)
        self.assertEqual(str(ctx.exception), "broker response must be a JSON object")

    def test_broker_request_raises_protocol_error_with_broker_message(self):
        import team_router_broker_adapter

        with fake_broker({
            "/thread-tools/list_projects": (200, {"ok": False, "error": {"message": "broker said no"}}),
        }) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router_broker_adapter.BrokerProtocolError) as ctx:
                team_router_broker_adapter.broker_request(config, "/thread-tools/list_projects", {})

        self.assertIsInstance(ctx.exception, team_router.StateStoreError)
        self.assertEqual(str(ctx.exception), "broker said no")

    def test_broker_request_maps_http_error_to_transport_error(self):
        import team_router_broker_adapter

        with fake_broker({
            "/thread-tools/list_projects": (503, {"ok": False, "error": {"message": "down"}}),
        }) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router_broker_adapter.BrokerTransportError) as ctx:
                team_router_broker_adapter.broker_request(config, "/thread-tools/list_projects", {})

        self.assertIsInstance(ctx.exception, team_router.StateStoreError)
        self.assertIn("broker HTTP error: 503", str(ctx.exception))

    def test_broker_request_maps_unreachable_broker_to_transport_error(self):
        import team_router_broker_adapter

        config = team_router_broker_adapter.BrokerConfig(
            base_url="http://127.0.0.1:1",
            session_token="session-123",
            timeout_ms=100,
        )
        with self.assertRaises(team_router_broker_adapter.BrokerTransportError) as ctx:
            team_router_broker_adapter.broker_request(config, "/thread-tools/list_projects", {})

        self.assertIsInstance(ctx.exception, team_router.StateStoreError)
        self.assertIn("broker transport error", str(ctx.exception))

    def test_codex_app_thread_adapter_exposes_required_callable_tools(self):
        import team_router_broker_adapter

        routes = {
            "/thread-tools/list_projects": (200, {"ok": True, "result": {"projects": [{"projectId": "project-1"}]}}),
            "/thread-tools/list_threads": (200, {"ok": True, "result": {"threads": [{"threadId": "thread-manager", "archived": False}]}}),
            "/thread-tools/create_thread": (200, {"ok": True, "result": {"threadId": "thread-new"}}),
            "/thread-tools/send_message_to_thread": (200, {"ok": True, "result": {"messageId": "msg-1", "sentAt": "2026-07-01T10:00:00+08:00"}}),
            "/thread-tools/read_thread": (200, {"ok": True, "result": {"messages": [{"messageId": "msg-2", "text": "ok"}]}}),
            "/thread-tools/set_thread_title": (200, {"ok": True, "result": {"threadId": "thread-parent", "title": "new title"}}),
        }
        with fake_broker(routes) as (base_url, calls):
            adapter = team_router_broker_adapter.CodexAppThreadAdapter(
                team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            )

            self.assertEqual(adapter.list_projects(), {"projects": [{"projectId": "project-1"}]})
            self.assertEqual(adapter.list_threads(projectId="project-1"), {"threads": [{"threadId": "thread-manager", "archived": False}]})
            self.assertEqual(adapter.create_thread(prompt="role: executor", target={"type": "project", "projectId": "project-1"}), {"threadId": "thread-new"})
            self.assertEqual(adapter.send_message_to_thread(threadId="thread-parent", prompt="TEAM_ROUTER_CALLBACK"), {"messageId": "msg-1", "sentAt": "2026-07-01T10:00:00+08:00"})
            self.assertEqual(adapter.read_thread(threadId="thread-new", turnLimit=20), {"messages": [{"messageId": "msg-2", "text": "ok"}]})
            self.assertEqual(adapter.set_thread_title(threadId="thread-parent", title="new title"), {"threadId": "thread-parent", "title": "new title"})

        self.assertEqual([call["path"] for call in calls], [
            "/thread-tools/list_projects",
            "/thread-tools/list_threads",
            "/thread-tools/create_thread",
            "/thread-tools/send_message_to_thread",
            "/thread-tools/read_thread",
            "/thread-tools/set_thread_title",
        ])
        for call in calls:
            self.assertEqual(call["payload"]["sessionToken"], "session-123")

    def test_codex_app_thread_adapter_is_usable_by_runtime_capability_probe(self):
        import team_router_broker_adapter

        with fake_broker({}) as (base_url, _calls):
            adapter = team_router_broker_adapter.CodexAppThreadAdapter(
                team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            )

        readiness = team_router.assess_live_orchestration_readiness(
            adapter,
            parent_thread_id="thread-parent",
            heartbeat_scheduler=FakeHeartbeatScheduler(),
        )

        self.assertEqual(readiness["status"], "ready")
        self.assertTrue(readiness["capabilities"]["create_thread"])
        self.assertTrue(readiness["capabilities"]["read_thread"])

    def test_fetch_broker_readiness_requires_runtime_probe_ready(self):
        import team_router_broker_adapter

        readiness = {
            "status": "blocked",
            "brokerReady": True,
            "toolSmokeReady": False,
            "schedulerReady": False,
            "parentThreadId": None,
            "projectId": "project-1",
            "capabilities": {"create_thread": False},
            "runtimeProbe": {"status": "blocked", "missing": ["parent_thread_id"]},
            "missing": ["parent_thread_id"],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            result = team_router_broker_adapter.fetch_broker_readiness(config)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["runtimeProbe"], {"status": "blocked", "missing": ["parent_thread_id"]})
        self.assertEqual(calls[0]["method"], "GET")

    def test_broker_host_context_kwargs_returns_adapter_parent_and_project(self):
        import team_router_broker_adapter

        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": [],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            kwargs = team_router_broker_adapter.broker_host_context_kwargs(config)

        self.assertIsInstance(kwargs["thread_adapter"], team_router_broker_adapter.CodexAppThreadAdapter)
        self.assertIsInstance(kwargs["heartbeat_scheduler"], team_router_broker_adapter.BrokerHeartbeatScheduler)
        self.assertEqual(kwargs["parent_thread_id"], "thread-parent")
        self.assertEqual(kwargs["codex_project_id"], "project-1")

    def test_broker_host_context_kwargs_returns_heartbeat_scheduler_after_task_4(self):
        import team_router_broker_adapter

        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {"heartbeat_scheduler": True},
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": [],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            kwargs = team_router_broker_adapter.broker_host_context_kwargs(config)

        self.assertIsInstance(kwargs["heartbeat_scheduler"], team_router_broker_adapter.BrokerHeartbeatScheduler)

    def test_broker_host_context_kwargs_blocks_without_ready_runtime_probe(self):
        import team_router_broker_adapter

        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {},
            "runtimeProbe": {"status": "blocked", "missing": ["scheduler smoke"]},
            "missing": [],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router.StateStoreError) as ctx:
                team_router_broker_adapter.broker_host_context_kwargs(config)

        self.assertIn("runtimeProbe", str(ctx.exception))


    def test_broker_host_readiness_snapshot_maps_ready_broker_for_doctor(self):
        import team_router_broker_adapter

        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
                "heartbeat_scheduler": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": [],
        }

        snapshot = team_router_broker_adapter.broker_host_readiness_snapshot(readiness)

        self.assertTrue(snapshot["adapterCallable"])
        self.assertEqual(snapshot["parentThreadId"], "thread-parent")
        self.assertTrue(snapshot["heartbeatSchedulerCallable"])
        self.assertEqual(snapshot["runtimeProbe"], {"status": "ready", "missing": []})
        for tool_name in team_router_broker_adapter.BROKER_THREAD_TOOL_METHODS:
            self.assertTrue(snapshot["callableTools"][tool_name])

    def test_broker_host_readiness_snapshot_maps_blocked_broker_for_doctor(self):
        import team_router_broker_adapter

        readiness = {
            "status": "blocked",
            "brokerReady": True,
            "toolSmokeReady": False,
            "schedulerReady": False,
            "parentThreadId": "",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": False,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": False,
                "set_thread_title": False,
                "heartbeat_scheduler": False,
            },
            "runtimeProbe": {"status": "blocked", "missing": ["parent_thread_id", "callable heartbeat scheduler"]},
            "missing": ["parent_thread_id", "scheduler smoke"],
        }

        snapshot = team_router_broker_adapter.broker_host_readiness_snapshot(readiness)

        self.assertTrue(snapshot["adapterCallable"])
        self.assertEqual(snapshot["parentThreadId"], "")
        self.assertFalse(snapshot["heartbeatSchedulerCallable"])
        self.assertFalse(snapshot["callableTools"]["create_thread"])
        self.assertEqual(snapshot["runtimeProbe"]["missing"], ["parent_thread_id", "callable heartbeat scheduler", "broker readiness"])
        self.assertEqual(snapshot["brokerMissing"], ["parent_thread_id", "scheduler smoke"])

    def test_broker_host_readiness_snapshot_keeps_blocked_broker_from_reporting_ready(self):
        import importlib.util
        import team_router_broker_adapter

        doctor_spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        doctor_module = importlib.util.module_from_spec(doctor_spec)
        doctor_spec.loader.exec_module(doctor_module)
        readiness = {
            "status": "blocked",
            "brokerReady": False,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
                "heartbeat_scheduler": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": ["broker not ready"],
        }

        snapshot = team_router_broker_adapter.broker_host_readiness_snapshot(readiness)
        classified = doctor_module.classify_host_readiness_snapshot(snapshot)

        self.assertEqual(classified["status"], "blocked")
        self.assertEqual(classified["orchestrationStatus"], "host_contract_blocked")
        self.assertIn("runtime readiness probe", classified["missing"])
        self.assertIn("broker readiness", snapshot["runtimeProbe"]["missing"])
        self.assertFalse(classified["evidence"]["runtimeProbeReady"])

class TestTeamRouterBrokerFeasibilityScript(unittest.TestCase):
    def test_broker_feasibility_check_blocks_without_broker_arguments(self):
        script = ROOT / "scripts" / "team_router_broker_feasibility_check.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("broker-url", report["missing"])
        self.assertIn("session-token", report["missing"])
        self.assertFalse(report["authorization"]["desktopPluginChange"])

    def test_broker_feasibility_check_reports_ready_readiness(self):
        script = ROOT / "scripts" / "team_router_broker_feasibility_check.py"
        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
                "heartbeat_scheduler": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": [],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--broker-url", base_url, "--session-token", "session-123", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["runtimeProbe"], {"status": "ready", "missing": []})
        self.assertFalse(report["authorization"]["desktopPluginChange"])

    def test_broker_feasibility_check_blocks_inconsistent_runtime_probe(self):
        script = ROOT / "scripts" / "team_router_broker_feasibility_check.py"
        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": False,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {"heartbeat_scheduler": False},
            "runtimeProbe": {"status": "blocked", "missing": ["scheduler smoke"]},
            "missing": [],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--broker-url", base_url, "--session-token", "session-123", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["runtimeProbe"], {"status": "blocked", "missing": ["scheduler smoke"]})

    def test_broker_feasibility_check_blocks_top_level_missing(self):
        script = ROOT / "scripts" / "team_router_broker_feasibility_check.py"
        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {"heartbeat_scheduler": True},
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": ["manual_only"],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--broker-url", base_url, "--session-token", "session-123", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["missing"], ["manual_only"])

    def test_broker_feasibility_check_includes_host_readiness_snapshot(self):
        script = ROOT / "scripts" / "team_router_broker_feasibility_check.py"
        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
                "heartbeat_scheduler": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": [],
        }
        with fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--broker-url", base_url, "--session-token", "session-123", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        snapshot = report["hostReadinessSnapshot"]
        self.assertTrue(snapshot["adapterCallable"])
        self.assertTrue(snapshot["callableTools"]["set_thread_title"])
        self.assertTrue(snapshot["heartbeatSchedulerCallable"])
        self.assertEqual(snapshot["parentThreadId"], "thread-parent")

    def test_scheduler_payload_materializes_with_broker_scheduler(self):
        import team_router_broker_adapter

        adapter = FakeThreadAdapter()
        with fake_broker({
            "/scheduler/wake": (200, {"ok": True, "result": {"scheduled": True}}),
        }) as (base_url, _calls):
            scheduler = team_router_broker_adapter.BrokerHeartbeatScheduler(
                team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            )
            payload = {
                "callback": "watch_team_task_with_adapter",
                "runAt": "2026-07-01T10:05:00+08:00",
                "kwargs": {
                    "state_root": str(ROOT),
                    "project_id": "project-1",
                    "task_id": "task-1",
                    "permission": "read-only",
                    "return_thread_id": "thread-parent",
                    "read_reason": "scheduled watcher heartbeat",
                },
            }

            kwargs = team_router.materialize_watcher_call_kwargs(
                payload,
                thread_adapter=adapter,
                heartbeat_scheduler=scheduler,
                turn_limit=3,
            )

        self.assertIs(kwargs["thread_adapter"], adapter)
        self.assertIs(kwargs["heartbeat_scheduler"], scheduler)
        self.assertEqual(kwargs["observed_at"], "2026-07-01T10:05:00+08:00")
        self.assertEqual(kwargs["turn_limit"], 3)

    def test_scheduler_payload_materializer_rejects_mixed_callback_fields(self):
        adapter = FakeThreadAdapter()
        payload = {
            "callback": "watch_team_task_with_adapter",
            "managerAction": "run_arbitrary_python",
            "runAt": "2026-07-01T10:05:00+08:00",
            "kwargs": {
                "state_root": str(ROOT),
                "project_id": "project-1",
                "task_id": "task-1",
                "permission": "read-only",
                "read_reason": "scheduled watcher heartbeat",
            },
        }

        with self.assertRaises(team_router.ProtocolError) as ctx:
            team_router.materialize_watcher_call_kwargs(payload, thread_adapter=adapter)

        self.assertIn("scheduler payload callback not allowed: run_arbitrary_python", str(ctx.exception))

class TestTeamRouterRuntimeWiringScript(unittest.TestCase):
    def test_runtime_wiring_check_reports_manual_only_without_broker_arguments(self):
        script = ROOT / "scripts" / "team_router_runtime_wiring_check.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "manual_only")
        self.assertEqual(report["orchestrationStatus"], "manual_only")
        self.assertFalse(report["automaticEntryAllowed"])
        self.assertIn("broker-url", report["missing"])
        self.assertIn("session-token", report["missing"])
        self.assertEqual(report["dryRun"]["threadToolCallsExecuted"], [])

    def test_runtime_wiring_check_blocks_automatic_entry_for_blocked_readiness(self):
        script = ROOT / "scripts" / "team_router_runtime_wiring_check.py"
        readiness = {
            "status": "blocked",
            "brokerReady": False,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
                "heartbeat_scheduler": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": ["broker not ready"],
        }
        with fake_broker({"/readiness": (200, {"ok": True, "result": readiness})}) as (base_url, calls):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--broker-url", base_url, "--session-token", "session-123", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "manual_only")
        self.assertEqual(report["orchestrationStatus"], "host_contract_blocked")
        self.assertFalse(report["automaticEntryAllowed"])
        self.assertEqual(report["managerStartupPath"]["injection"], "blocked")
        self.assertEqual(report["dryRun"]["threadToolCallsExecuted"], [])
        self.assertEqual([call["path"] for call in calls], ["/readiness"])

    def test_runtime_wiring_check_allows_automatic_entry_only_from_ready_host_context(self):
        script = ROOT / "scripts" / "team_router_runtime_wiring_check.py"
        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
                "heartbeat_scheduler": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": [],
        }
        with fake_broker({"/readiness": (200, {"ok": True, "result": readiness})}) as (base_url, calls):
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--broker-url", base_url, "--session-token", "session-123", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["orchestrationStatus"], "adapter_smoke_ready")
        self.assertTrue(report["automaticEntryAllowed"])
        self.assertEqual(report["managerStartupPath"]["injection"], "host_context")
        self.assertEqual(report["managerStartupPath"]["hostContextKeys"], [
            "codex_project_id",
            "heartbeat_scheduler",
            "host_readiness_snapshot",
            "parent_thread_id",
            "readiness",
            "thread_adapter",
        ])
        self.assertTrue(report["hostReadiness"]["capabilities"]["create_thread"])
        self.assertTrue(report["hostReadiness"]["capabilities"]["read_thread"])
        self.assertTrue(report["hostReadiness"]["capabilities"]["send_message_to_thread"])
        self.assertTrue(report["hostReadiness"]["capabilities"]["set_thread_title"])
        self.assertEqual(report["dryRun"]["threadToolCallsExecuted"], [])
        self.assertTrue(all(call["path"] == "/readiness" for call in calls))
class TestTeamRouterProtocol(unittest.TestCase):
    def test_facade_reexports_broker_adapter_symbols(self):
        import team_router_broker_adapter

        for name in (
            "BrokerConfig",
            "BrokerProtocolError",
            "BrokerTransportError",
            "CodexAppThreadAdapter",
        ):
            self.assertIs(getattr(team_router, name), getattr(team_router_broker_adapter, name))

    def test_facade_reexports_extracted_protocol_and_policy_symbols(self):
        self.assertIs(team_router.ProtocolError, team_router_protocol.ProtocolError)
        self.assertIs(team_router.ProtocolMessage, team_router_protocol.ProtocolMessage)
        self.assertIs(team_router.parse_callback, team_router_protocol.parse_callback)
        self.assertIs(team_router.parse_verdict, team_router_protocol.parse_verdict)
        self.assertIs(team_router.classify_team_router_gate, team_router_policy.classify_team_router_gate)
        self.assertIs(team_router.gate_class_requires_reviewer, team_router_policy.gate_class_requires_reviewer)


    def test_facade_reexports_extracted_state_symbols(self):
        self.assertIs(team_router.StateStoreError, team_router_state.StateStoreError)
        self.assertIs(team_router.create_task_id, team_router_state.create_task_id)
        self.assertIs(team_router.load_registry, team_router_state.load_registry)
        self.assertIs(team_router.save_task_ledger, team_router_state.save_task_ledger)
        self.assertIs(team_router.STATE_MACHINE_SNAPSHOT, team_router_state.STATE_MACHINE_SNAPSHOT)
        self.assertIs(team_router._search_anchor, team_router_state._search_anchor)
        self.assertIs(team_router._role_review_request_record, team_router_state._role_review_request_record)
        self.assertIs(team_router._latest_executor_dispatch, team_router_state._latest_executor_dispatch)
        self.assertIs(team_router._latest_executor_callback_observation, team_router_state._latest_executor_callback_observation)
        self.assertIs(team_router._has_observation_content, team_router_state._has_observation_content)
        self.assertIs(team_router._inherited_verifier_return_thread_id, team_router_state._inherited_verifier_return_thread_id)

    def test_facade_reexports_host_runtime_symbols(self):
        import team_router_host_runtime

        names = (
            "THREAD_TOOL_NAMES",
            "LiveOrchestrationHostContext",
            "probe_thread_adapter_capabilities",
            "_heartbeat_scheduler_call",
            "assess_live_orchestration_readiness",
            "make_live_orchestration_host_context",
            "_raise_if_host_context_conflict",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIs(getattr(team_router, name), getattr(team_router_host_runtime, name))

    def test_facade_delegates_to_extracted_status_symbols(self):
        self.assertIsNotNone(importlib.util.find_spec("team_router_status"))
        status = __import__("team_router_status")

        self.assertEqual(
            team_router.DEFAULT_CLOSEOUT_COMPOUNDING_REASON,
            status.DEFAULT_CLOSEOUT_COMPOUNDING_REASON,
        )
        self.assertIs(team_router._role_thread_lines, status.role_thread_lines)
        self.assertIs(team_router._anchor_lines, status.anchor_lines)
        self.assertIs(team_router._closeout_compounding_fields, status.closeout_compounding_fields)
        self.assertIs(team_router.format_closeout_for_user, status.format_closeout_for_user)
        self.assertIs(team_router._status_format_handoff_for_user, status.format_handoff_for_user)
        self.assertIs(team_router._status_format_task_update_for_user, status.format_task_update_for_user)


    def test_status_tools_module_extracts_read_only_script_helpers(self):
        self.assertIsNotNone(importlib.util.find_spec("team_router_status_tools"))
        status_tools = __import__("team_router_status_tools")

        truth_spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        truth_module = importlib.util.module_from_spec(truth_spec)
        truth_spec.loader.exec_module(truth_module)
        closeout_spec = importlib.util.spec_from_file_location(
            "team_router_closeout_check_under_test",
            ROOT / "scripts" / "team_router_closeout_check.py",
        )
        closeout_module = importlib.util.module_from_spec(closeout_spec)
        closeout_spec.loader.exec_module(closeout_module)
        doctor_spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        doctor_module = importlib.util.module_from_spec(doctor_spec)
        doctor_spec.loader.exec_module(doctor_module)

        self.assertIs(truth_module.build_truth_report, status_tools.build_truth_report)
        self.assertIs(truth_module.find_stale_state_claims, status_tools.find_stale_state_claims)
        self.assertIs(closeout_module.build_report, status_tools.build_closeout_report)
        self.assertIs(doctor_module._truth_status, status_tools.truth_status)
        self.assertIs(doctor_module._next_action, status_tools.next_action)
        self.assertEqual(truth_module.DEFAULT_REPO_ROOT, status_tools.DEFAULT_REPO_ROOT)
        self.assertEqual(closeout_module.DEFAULT_GLOBAL_SKILL, status_tools.DEFAULT_GLOBAL_SKILL)
    def test_test_case_names_are_unique(self):
        names = [name for name, value in TestTeamRouterProtocol.__dict__.items() if name.startswith("test_")]
        self.assertEqual(len(names), len(set(names)))

    def test_state_observation_content_checks_existing_ledger_observations(self):
        ledger = {
            "observations": [
                {
                    "type": "callback_raw",
                    "role": "executor",
                    "threadId": "executor-thread",
                    "content": "TEAM_ROUTER_CALLBACK taskId=ctr-1",
                },
                "ignored",
            ]
        }

        self.assertTrue(
            team_router_state._has_observation_content(
                ledger,
                "callback_raw",
                "executor",
                "executor-thread",
                "TEAM_ROUTER_CALLBACK taskId=ctr-1",
            )
        )
        self.assertFalse(
            team_router_state._has_observation_content(
                ledger,
                "callback_raw",
                "executor",
                "other-thread",
                "TEAM_ROUTER_CALLBACK taskId=ctr-1",
            )
        )

    def test_state_latest_executor_callback_observation_returns_latest_callback(self):
        first = {
            "type": "callback_raw",
            "role": "executor",
            "threadId": "executor-thread",
            "content": "first callback",
        }
        latest = {
            "type": "callback_raw",
            "role": "executor",
            "threadId": "executor-thread",
            "content": "latest callback",
        }
        ledger = {
            "observations": [
                first,
                {"type": "callback_raw", "role": "reviewer"},
                "ignored",
                {"type": "review_raw", "role": "executor"},
                latest,
            ]
        }

        self.assertIs(
            team_router_state._latest_executor_callback_observation(ledger),
            latest,
        )
        self.assertIsNone(
            team_router_state._latest_executor_callback_observation(
                {"observations": [{"type": "review_raw", "role": "executor"}]}
            )
        )

    def test_callback_parser_rejects_colon_marker(self):
        text = """TEAM_ROUTER_CALLBACK taskId: ctr-1
status: done
final: true
summary: ok
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_callback(text, "ctr-1")

    def test_callback_parser_rejects_malformed_marker_after_valid_block(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary: old
evidence: old
risks: none
next: none

TEAM_ROUTER_CALLBACK taskId: ctr-1
status: blocked
final: true
summary: new
evidence: new
risks: none
next: none
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_callback(text, "ctr-1")

    def test_callback_parser_rejects_duplicate_field_in_one_block(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary: first
summary: overwritten
evidence: tests
risks: none
next: none
"""
        with self.assertRaisesRegex(team_router.ProtocolError, "duplicate field"):
            team_router.parse_callback(text, "ctr-1")

    def test_callback_parser_uses_last_final_message(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary: draft
evidence: old
risks: none
next: none

TEAM_ROUTER_CALLBACK taskId=ctr-1
status: blocked
final: true
summary: final
evidence: latest
risks: missing data
next: retry
"""
        msg = team_router.parse_callback(text, "ctr-1")
        self.assertEqual(msg.fields["status"], "blocked")
        self.assertEqual(msg.fields["summary"], "final")

    def test_direct_return_rejects_two_final_markers_in_one_message(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary: first
evidence: tests
risks: none
next: none
TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary: second
evidence: tests
risks: none
next: none
"""
        parsed, malformed, _ = team_router_direct_return._direct_return_protocol_message(
            [{"sourceThreadId": "executor-thread", "messageId": "msg-1", "text": text}],
            marker="TEAM_ROUTER_CALLBACK", task_id="ctr-1", source_thread_id="executor-thread",
        )
        self.assertIsNone(parsed)
        self.assertIn("multiple", malformed["error"])

    def test_callback_parser_keeps_multiline_summary(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary:
checked protocol parser
confirmed no missing fields
evidence: tests
risks: none
next: none
"""
        msg = team_router.parse_callback(text, "ctr-1")
        self.assertEqual(
            msg.fields["summary"],
            "checked protocol parser\nconfirmed no missing fields",
        )

    def test_plan_requires_acknowledged_permission(self):
        text = """TEAM_ROUTER_PLAN taskId=ctr-1
status: planned
scope: docs
stopWhen: done
riskBoundary: read only
executorPrompt: inspect docs
notes: none
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_plan(text, "ctr-1")

    def test_plan_rejects_empty_required_fields(self):
        text = """TEAM_ROUTER_PLAN taskId=ctr-1
status: planned
acknowledgedPermission: read-only
scope:
stopWhen: done
riskBoundary: read only
executorPrompt:
notes: none
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_plan(text, "ctr-1")

    def test_plan_accepts_local_package_acknowledgement(self):
        text = """TEAM_ROUTER_PLAN taskId=ctr-1
status: planned
acknowledgedPermission: local-package
scope: src tests docs
stopWhen: done
riskBoundary: authorized local-package workspace writes only; no manager direct edits
executorPrompt: implement authorized write package
notes: reviewer/verifier gates required
"""
        msg = team_router.parse_plan(text, "ctr-1")
        self.assertEqual(msg.fields["acknowledgedPermission"], "local-package")

    def test_verdict_result_is_structured(self):
        text = """TEAM_ROUTER_VERDICT taskId=ctr-1
result: needs_rework
summary: missing edge case
requiredChanges: add state test
evidenceChecked: test plan
risks: none
"""
        msg = team_router.parse_verdict(text, "ctr-1")
        self.assertEqual(msg.fields["result"], "needs_rework")

    def test_architect_and_qa_are_fixed_conditional_roles(self):
        snapshot = team_router.protocol_contract_snapshot()

        self.assertEqual(snapshot["coreRoleNames"], ["executor", "manager", "verifier"])
        self.assertIn("architect", snapshot["conditionalRoleNames"])
        self.assertIn("qa", snapshot["conditionalRoleNames"])
        self.assertNotIn("architect", team_router.CORE_ROLE_NAMES)
        self.assertNotIn("qa", team_router.CORE_ROLE_NAMES)
        self.assertIn("architect", team_router.ROLE_NAMES)
        self.assertIn("qa", team_router.ROLE_NAMES)
        self.assertEqual(snapshot["roleThreads"]["architect"]["englishAlias"], "Architect")
        self.assertEqual(snapshot["roleThreads"]["qa"]["englishAlias"], "QA")
        self.assertTrue(snapshot["roleThreads"]["architect"]["conditional"])
        self.assertTrue(snapshot["roleThreads"]["qa"]["conditional"])
        self.assertTrue(snapshot["conditionalRolePolicy"]["noCustomRoleRegistry"])
        self.assertEqual(snapshot["conditionalRolePolicy"]["runtimeSkillLoading"], "not supported")

    def test_versioned_role_contract_keeps_legacy_manager_but_v2_does_not_create_it(self):
        self.assertEqual(
            team_router.LEGACY_CORE_ROLE_NAMES,
            frozenset({"manager", "executor", "verifier"}),
        )
        self.assertEqual(team_router.V2_DELEGATED_BASE_ROLE_NAMES, frozenset({"executor"}))
        self.assertNotIn("manager", team_router.V2_DELEGATED_BASE_ROLE_NAMES)
        snapshot = team_router.protocol_contract_snapshot()
        self.assertEqual(snapshot["workflowContracts"]["v1"]["coreRoles"], ["executor", "manager", "verifier"])
        self.assertEqual(snapshot["workflowContracts"]["v2"]["baseRoles"], ["executor"])

    def test_resolve_role_model_defaults_and_rejects_sol_ultra(self):
        self.assertEqual(
            team_router.resolve_role_model("mechanical"),
            {
                "executionClass": "mechanical",
                "requestedModel": "gpt-5.6-luna",
                "requestedThinking": "medium",
            },
        )
        with self.assertRaisesRegex(team_router.StateStoreError, "model_override_invalid"):
            team_router.resolve_role_model("standard", model="gpt-5.5")
        with self.assertRaisesRegex(team_router.StateStoreError, "model_forbidden"):
            team_router.resolve_role_model(
                "high",
                model="gpt-5.6-sol",
                thinking="ultra",
                override_reason="manual override",
            )

    def test_v2_manager_direct_is_decided_before_route_closure(self):
        mode = team_router.resolve_v2_execution_mode(
            "NORMAL",
            explicit_roles=(),
            requires_parallelism=False,
            requires_independent_context=False,
            requires_independent_review=False,
            lightweight_verification_available=True,
        )
        self.assertEqual(mode, "manager_direct")
        delegated_cases = (
            {"explicit_roles": ("architect",)},
            {"requires_parallelism": True},
            {"requires_independent_context": True},
            {"requires_independent_review": True},
            {"lightweight_verification_available": False},
        )
        for overrides in delegated_cases:
            with self.subTest(overrides=overrides):
                arguments = {
                    "explicit_roles": (),
                    "requires_parallelism": False,
                    "requires_independent_context": False,
                    "requires_independent_review": False,
                    "lightweight_verification_available": True,
                }
                arguments.update(overrides)
                self.assertEqual(
                    team_router.resolve_v2_execution_mode("NORMAL", **arguments),
                    "delegated",
                )
        for gate in ("STRICT", "PACKAGE"):
            with self.subTest(gate=gate):
                self.assertEqual(team_router.resolve_v2_execution_mode(gate), "delegated")

    def test_v2_local_package_permission_does_not_raise_risk_by_name(self):
        ledger = {
            "workflowVersion": 2,
            "objective": "ordinary local docs update",
            "permission": "local-package",
        }
        resolved = team_router.resolve_effective_gate(
            "NORMAL",
            ledger,
            authorization={"workspaceWrite": True},
        )
        self.assertEqual(resolved["requestedGateClass"], "NORMAL")
        self.assertEqual(resolved["effectiveGateClass"], "NORMAL")
        self.assertEqual(team_router.classify_team_router_gate(ledger), "STRICT")
        with self.assertRaisesRegex(team_router.StateStoreError, "authorization_missing"):
            team_router.resolve_effective_gate(
                "NORMAL",
                ledger,
                authorization={"workspaceWrite": False},
            )

        strict = team_router.resolve_effective_gate(
            "NORMAL",
            {"workflowVersion": 2, "objective": "Team Router permission policy change"},
            authorization={},
        )
        self.assertEqual(strict["effectiveGateClass"], "STRICT")
        self.assertEqual(
            team_router.resolve_effective_gate(
                "STRICT",
                {"workflowVersion": 2, "objective": "ordinary helper"},
                authorization={},
            )["effectiveGateClass"],
            "STRICT",
        )

    def test_v2_route_closes_conditional_role_dependencies(self):
        self.assertEqual(team_router.resolve_v2_route("NORMAL"), ("executor",))
        self.assertEqual(
            team_router.resolve_v2_route("STRICT"),
            ("executor", "reviewer", "verifier"),
        )
        self.assertEqual(
            team_router.resolve_v2_route("NORMAL", ("reviewer",)),
            ("executor", "reviewer", "verifier"),
        )
        self.assertEqual(
            team_router.resolve_v2_route("NORMAL", ("qa",)),
            ("executor", "qa", "verifier"),
        )
        self.assertEqual(
            team_router.resolve_v2_route("NORMAL", ("architect",)),
            ("architect", "executor"),
        )
        with self.assertRaisesRegex(team_router.StateStoreError, "invalid v2 role"):
            team_router.resolve_v2_route("NORMAL", ("manager",))

    def test_completion_package_allows_in_scope_terse_continuation_only(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-1",
            task_id="task-1",
            parent_thread_id="parent-1",
            objective="完成 X",
            scope="src/x.py",
            permission="local-package",
            stop_condition="tests pass",
            created_at="2026-07-11T20:00:00+08:00",
        )
        ledger = {
            "taskId": "task-1",
            "objective": "完成 X",
            "status": "planned",
            "taskAuthorizationPackage": package,
        }
        request = {
            "requested_task_id": "task-1",
            "requested_objective": "完成 X",
            "requested_scope": "src/x.py",
            "requested_permission": "local-package",
            "requested_stop_condition": "tests pass",
        }

        self.assertTrue(
            team_router.v2_continuation_allowed(
                ledger,
                parent_thread_id="parent-1",
                **request,
            )
        )
        for name, overrides in (
            ("parent", {"parent_thread_id": "parent-2"}),
            ("task", {"requested_task_id": "task-2"}),
            ("objective", {"requested_objective": "完成 Y"}),
            ("scope", {"requested_scope": "src/x.py src/y.py"}),
            ("permission", {"requested_permission": "read-only"}),
            ("stop", {"requested_stop_condition": "publish"}),
            ("external", {"requested_external_gates": ("push",)}),
        ):
            with self.subTest(name=name):
                arguments = {"parent_thread_id": "parent-1", **request}
                arguments.update(overrides)
                self.assertFalse(team_router.v2_continuation_allowed(ledger, **arguments))
        terminal = dict(ledger, status="done")
        self.assertFalse(
            team_router.v2_continuation_allowed(
                terminal,
                parent_thread_id="parent-1",
                **request,
            )
        )
        self.assertFalse(
            team_router.v2_continuation_allowed(
                dict(ledger, parentThreadId="other-parent"),
                parent_thread_id="parent-1",
                **request,
            )
        )

    def test_v2_plan_resolves_effective_gate_before_route_and_models(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-1",
            task_id="task-1",
            parent_thread_id="parent-1",
            objective="Team Router permission policy change",
            scope="src/team_router_policy.py",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
            model_routing_authorization={
                "allowedDefaults": [
                    "gpt-5.6-luna:medium",
                    "gpt-5.6-terra:medium",
                    "gpt-5.6-sol:high",
                ],
                "authorizedBy": "explicit_cost_aware_entry",
            },
        )

        plan = team_router.resolve_v2_manager_plan(
            objective="Team Router permission policy change",
            scope="src/team_router_policy.py",
            permission="local-package",
            stop_condition="focused tests pass",
            requested_gate_class="NORMAL",
            authorization_package=package,
            requested_role_routing={
                "executor": {"executionClass": "standard"},
                "reviewer": {"executionClass": "high"},
                "verifier": {"executionClass": "standard"},
            },
            requires_independent_review=True,
        )

        self.assertEqual(plan["effectiveGateClass"], "STRICT")
        self.assertEqual(plan["taskId"], "task-1")
        self.assertEqual(plan["parentThreadId"], "parent-1")
        self.assertEqual(plan["routeRoles"], ("executor", "reviewer", "verifier"))
        self.assertEqual(
            plan["roleRouting"]["reviewer"]["requestedModel"],
            "gpt-5.6-sol",
        )

    def test_v2_plan_classifies_scope_before_direct_branch(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-scope",
            task_id="task-scope",
            parent_thread_id="parent-scope",
            objective="ordinary maintenance",
            scope="src/team_router.py; permission boundary",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
            model_routing_authorization={
                "allowedDefaults": [
                    "gpt-5.6-luna:medium",
                    "gpt-5.6-terra:medium",
                    "gpt-5.6-sol:high",
                ],
                "authorizedBy": "explicit_cost_aware_entry",
            },
        )

        plan = team_router.resolve_v2_manager_plan(
            objective="ordinary maintenance",
            scope="src/team_router.py; permission boundary",
            permission="local-package",
            stop_condition="focused tests pass",
            requested_gate_class="NORMAL",
            authorization_package=package,
            requested_role_routing={
                "executor": {"executionClass": "standard"},
                "reviewer": {"executionClass": "high"},
                "verifier": {"executionClass": "standard"},
            },
        )

        self.assertEqual(plan["effectiveGateClass"], "STRICT")
        self.assertEqual(plan["executionMode"], "delegated")

    def test_prepare_v2_manager_direct_is_stateless(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-direct",
            task_id="task-direct",
            parent_thread_id="parent-direct",
            objective="ordinary docs update",
            scope="docs/x.md",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
        )
        requested_plan = {
            "scope": "docs/x.md",
            "permission": "local-package",
            "stopCondition": "focused tests pass",
            "requestedGateClass": "NORMAL",
        }
        with workspace_temp_dir() as td, mock.patch("team_router_v2.new_v2_task_ledger") as new_ledger, mock.patch(
            "team_router_v2.save_task_ledger"
        ) as save_ledger:
            result = team_router.prepare_v2_manager_task(
                Path(td) / "state",
                "project-1",
                "task-direct",
                objective="ordinary docs update",
                project_local_path=td,
                parent_thread_id="parent-direct",
                requested_plan=requested_plan,
                authorization_package=package,
                created_at="2026-07-11T20:00:00+08:00",
            )

        self.assertEqual(result["executionMode"], "manager_direct")
        self.assertIsNone(result["ledger"])
        new_ledger.assert_not_called()
        save_ledger.assert_not_called()

    def test_prepare_v2_rejects_bare_manager_mode_before_state(self):
        requested_plan = {
            "scope": "docs/x.md",
            "permission": "local-package",
            "stopCondition": "focused tests pass",
            "requestedGateClass": "NORMAL",
        }
        with workspace_temp_dir() as td, mock.patch("team_router_v2.new_v2_task_ledger") as new_ledger, mock.patch(
            "team_router_v2.save_task_ledger"
        ) as save_ledger:
            with self.assertRaisesRegex(team_router.StateStoreError, "authorization_missing"):
                team_router.prepare_v2_manager_task(
                    Path(td) / "state",
                    "project-1",
                    "task-direct",
                    objective="ordinary docs update",
                    project_local_path=td,
                    parent_thread_id="parent-direct",
                    requested_plan=requested_plan,
                    authorization_package=None,
                    created_at="2026-07-11T20:00:00+08:00",
                )

        new_ledger.assert_not_called()
        save_ledger.assert_not_called()

    def test_prepare_v2_rejects_foreign_package_before_state(self):
        model_authorization = {
            "allowedDefaults": [
                "gpt-5.6-luna:medium",
                "gpt-5.6-terra:medium",
                "gpt-5.6-sol:high",
            ],
            "authorizedBy": "explicit_cost_aware_entry",
        }
        requested_plan = {
            "scope": "src/x.py",
            "permission": "local-package",
            "stopCondition": "focused tests pass",
            "requestedGateClass": "NORMAL",
            "explicitRoles": ("executor",),
            "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
        }
        for name, actual_task_id, actual_parent_thread_id in (
            ("task", "task-actual", "parent-package"),
            ("parent", "task-package", "parent-actual"),
        ):
            with self.subTest(name=name), workspace_temp_dir() as td, mock.patch(
                "team_router_v2.new_v2_task_ledger"
            ) as new_ledger, mock.patch("team_router_v2.save_task_ledger") as save_ledger:
                package = team_router.make_task_authorization_package(
                    package_id="auth-foreign",
                    task_id="task-package",
                    parent_thread_id="parent-package",
                    objective="delegated task",
                    scope="src/x.py",
                    permission="local-package",
                    stop_condition="focused tests pass",
                    created_at="2026-07-11T20:00:00+08:00",
                    model_routing_authorization=model_authorization,
                )
                with self.assertRaisesRegex(team_router.StateStoreError, "authorization_mismatch"):
                    team_router.prepare_v2_manager_task(
                        Path(td) / "state",
                        "project-1",
                        actual_task_id,
                        objective="delegated task",
                        project_local_path=td,
                        parent_thread_id=actual_parent_thread_id,
                        requested_plan=requested_plan,
                        authorization_package=package,
                        created_at="2026-07-11T20:00:00+08:00",
                    )
                new_ledger.assert_not_called()
                save_ledger.assert_not_called()

    def test_prepare_v2_delegated_requires_model_authorization_before_state(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-1",
            task_id="task-1",
            parent_thread_id="parent-1",
            objective="delegated task",
            scope="src/x.py",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
        )
        requested_plan = {
            "scope": "src/x.py",
            "permission": "local-package",
            "stopCondition": "focused tests pass",
            "requestedGateClass": "NORMAL",
            "explicitRoles": ("executor",),
            "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
        }
        with workspace_temp_dir() as td, mock.patch("team_router_v2.new_v2_task_ledger") as new_ledger, mock.patch(
            "team_router_v2.save_task_ledger"
        ) as save_ledger:
            with self.assertRaisesRegex(team_router.StateStoreError, "model_authorization_required"):
                team_router.prepare_v2_manager_task(
                    Path(td) / "state",
                    "project-1",
                    "task-1",
                    objective="delegated task",
                    project_local_path=td,
                    parent_thread_id="parent-1",
                    requested_plan=requested_plan,
                    authorization_package=package,
                    created_at="2026-07-11T20:00:00+08:00",
                )

        new_ledger.assert_not_called()
        save_ledger.assert_not_called()

    def test_prepare_v2_delegated_saves_one_planned_ledger(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-1",
            task_id="task-1",
            parent_thread_id="parent-1",
            objective="delegated task",
            scope="src/x.py",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
            model_routing_authorization={
                "allowedDefaults": [
                    "gpt-5.6-luna:medium",
                    "gpt-5.6-terra:medium",
                    "gpt-5.6-sol:high",
                ],
                "authorizedBy": "explicit_cost_aware_entry",
            },
        )
        requested_plan = {
            "scope": "src/x.py",
            "permission": "local-package",
            "stopCondition": "focused tests pass",
            "requestedGateClass": "NORMAL",
            "explicitRoles": ("executor",),
            "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
        }
        with workspace_temp_dir() as td, mock.patch(
            "team_router_v2.save_task_ledger",
            wraps=team_router_state.save_task_ledger,
        ) as save_ledger:
            result = team_router.prepare_v2_manager_task(
                Path(td) / "state",
                "project-1",
                "task-1",
                objective="delegated task",
                project_local_path=td,
                parent_thread_id="parent-1",
                requested_plan=requested_plan,
                authorization_package=package,
                created_at="2026-07-11T20:00:00+08:00",
            )

        self.assertEqual(result["executionMode"], "delegated")
        self.assertEqual(result["ledger"]["status"], "planned")
        self.assertEqual(result["ledger"]["taskAuthorizationPackage"], package)
        save_ledger.assert_called_once()

    def test_v2_delegated_plan_requires_model_authorization_and_complete_route(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-1",
            task_id="task-1",
            parent_thread_id="parent-1",
            objective="ordinary delegated task",
            scope="src/x.py",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
        )
        common = {
            "objective": "ordinary delegated task",
            "scope": "src/x.py",
            "permission": "local-package",
            "stop_condition": "focused tests pass",
            "requested_gate_class": "NORMAL",
            "explicit_roles": ("executor",),
            "requested_role_routing": {"executor": {"executionClass": "standard"}},
        }
        with self.assertRaisesRegex(team_router.StateStoreError, "model_authorization_required"):
            team_router.resolve_v2_manager_plan(authorization_package=package, **common)

        package["modelRoutingAuthorization"] = {
            "allowedDefaults": [
                "gpt-5.6-luna:medium",
                "gpt-5.6-terra:medium",
                "gpt-5.6-sol:high",
            ],
            "authorizedBy": "explicit_cost_aware_entry",
        }
        strict = dict(common, requested_gate_class="STRICT", explicit_roles=())
        strict["requested_role_routing"] = {
            "executor": {"executionClass": "standard"},
            "reviewer": {"executionClass": "high"},
        }
        with self.assertRaisesRegex(team_router.StateStoreError, "plan_invalid: missing roleRouting.verifier"):
            team_router.resolve_v2_manager_plan(authorization_package=package, **strict)
        package["modelRoutingAuthorization"]["authorizedBy"] = "arbitrary_marker"
        with self.assertRaisesRegex(team_router.StateStoreError, "model_authorization_required"):
            team_router.resolve_v2_manager_plan(authorization_package=package, **common)

    def test_v2_plan_retains_parallel_conflicts_for_audit(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-1",
            task_id="task-1",
            parent_thread_id="parent-1",
            objective="ordinary delegated task",
            scope="src/x.py",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
            model_routing_authorization={
                "allowedDefaults": [
                    "gpt-5.6-luna:medium",
                    "gpt-5.6-terra:medium",
                    "gpt-5.6-sol:high",
                ],
                "authorizedBy": "explicit_cost_aware_entry",
            },
        )
        common = {
            "objective": "ordinary delegated task",
            "scope": "src/x.py",
            "permission": "local-package",
            "stop_condition": "focused tests pass",
            "requested_gate_class": "NORMAL",
            "authorization_package": package,
            "requested_role_routing": {"executor": {"executionClass": "standard"}},
            "requires_parallelism": True,
        }
        allowed = team_router.resolve_v2_manager_plan(parallel_conflicts=(), **common)
        blocked = team_router.resolve_v2_manager_plan(
            parallel_conflicts=("shared-write",),
            **common,
        )

        self.assertTrue(allowed["parallelAllowed"])
        self.assertFalse(blocked["parallelAllowed"])
        self.assertEqual(blocked["parallelConflicts"], ("shared-write",))

    def test_v2_plan_accepts_complete_per_request_model_override(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-1",
            task_id="task-1",
            parent_thread_id="parent-1",
            objective="delegated task",
            scope="src/x.py",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T20:00:00+08:00",
            model_routing_authorization={
                "allowedDefaults": [],
                "authorizedBy": "complete_per_request_override",
                "allowedOverrides": [{"role": "executor", "model": "gpt-5.6-sol", "thinking": "high"}],
            },
        )
        plan = team_router.resolve_v2_manager_plan(
            objective="delegated task",
            scope="src/x.py",
            permission="local-package",
            stop_condition="focused tests pass",
            requested_gate_class="NORMAL",
            authorization_package=package,
            explicit_roles=("executor",),
            requested_role_routing={
                "executor": {
                    "executionClass": "standard",
                    "model": "gpt-5.6-sol",
                    "thinking": "high",
                    "modelOverrideReason": "user explicitly requested high-risk analysis",
                },
            },
        )

        self.assertEqual(plan["roleRouting"]["executor"]["requestedModel"], "gpt-5.6-sol")
        self.assertEqual(plan["roleRouting"]["executor"]["requestedThinking"], "high")

    def test_role_delivery_fields_cover_all_direct_return_roles(self):
        expected = {
            "executor": ("callbackDelivery", "callbackFallback"),
            "reviewer": ("reviewDelivery", "reviewFallback"),
            "verifier": ("verdictDelivery", "verdictFallback"),
            "architect": ("architectReviewDelivery", "architectReviewFallback"),
            "qa": ("qaReviewDelivery", "qaReviewFallback"),
        }

        self.assertEqual(team_router.ROLE_DELIVERY_FIELDS, expected)

    def test_architect_and_qa_markers_have_required_fields_and_enums(self):
        markers = team_router.protocol_contract_snapshot()["markers"]
        architect_required = set(markers["TEAM_ROUTER_ARCHITECT_REVIEW"]["requiredFields"])
        qa_required = set(markers["TEAM_ROUTER_QA_REVIEW"]["requiredFields"])

        self.assertTrue({
            "result", "sourceThreadId", "sourceRoleThreadId", "role", "summary",
            "findings", "requiredChanges", "evidenceChecked", "risks",
            "skillProfileUsed", "architectureImpact", "compatibilityNotes",
            "alternatives", "migrationRisks",
        }.issubset(architect_required))
        self.assertTrue({
            "result", "sourceThreadId", "sourceRoleThreadId", "role", "summary",
            "findings", "requiredChanges", "evidenceChecked", "risks",
            "skillProfileUsed", "coverageGaps", "verificationPlan", "regressionRisks",
        }.issubset(qa_required))
        self.assertEqual(markers["TEAM_ROUTER_ARCHITECT_REVIEW"]["allowedValues"]["result"], ["blocked", "needs_rework", "pass"])
        self.assertEqual(markers["TEAM_ROUTER_ARCHITECT_REVIEW"]["allowedValues"]["role"], ["Architect"])
        self.assertEqual(markers["TEAM_ROUTER_ARCHITECT_REVIEW"]["allowedValues"]["skillProfileUsed"], ["architect-default"])
        self.assertEqual(markers["TEAM_ROUTER_QA_REVIEW"]["allowedValues"]["result"], ["blocked", "needs_rework", "pass"])
        self.assertEqual(markers["TEAM_ROUTER_QA_REVIEW"]["allowedValues"]["role"], ["QA"])
        self.assertEqual(markers["TEAM_ROUTER_QA_REVIEW"]["allowedValues"]["skillProfileUsed"], ["qa-default"])

    def test_architect_and_qa_marker_parser_accepts_required_fields(self):
        architect = """TEAM_ROUTER_ARCHITECT_REVIEW taskId=ctr-1
result: pass
sourceThreadId: parent-thread
sourceRoleThreadId: thread-architect
role: Architect
summary: ok
findings: none
requiredChanges: none
evidenceChecked: tests
risks: none
skillProfileUsed: architect-default
architectureImpact: shared state
compatibilityNotes: ok
alternatives: none
migrationRisks: low
"""
        qa = """TEAM_ROUTER_QA_REVIEW taskId=ctr-1
result: pass
sourceThreadId: parent-thread
sourceRoleThreadId: thread-qa
role: QA
summary: ok
findings: none
requiredChanges: none
evidenceChecked: tests
risks: none
skillProfileUsed: qa-default
coverageGaps: none
verificationPlan: py -B -m unittest tests.test_team_router
regressionRisks: low
"""

        self.assertEqual(
            team_router.parse_message(architect, "TEAM_ROUTER_ARCHITECT_REVIEW", "ctr-1").fields["role"],
            "Architect",
        )
        self.assertEqual(
            team_router.parse_message(qa, "TEAM_ROUTER_QA_REVIEW", "ctr-1").fields["skillProfileUsed"],
            "qa-default",
        )

    def test_architect_and_qa_markers_reject_missing_identity_fields(self):
        cases = [
            (
                "TEAM_ROUTER_ARCHITECT_REVIEW",
                "Architect",
                "skillProfileUsed: architect-default\narchitectureImpact: shared state\ncompatibilityNotes: ok\nalternatives: none\nmigrationRisks: low",
            ),
            (
                "TEAM_ROUTER_QA_REVIEW",
                "QA",
                "skillProfileUsed: qa-default\ncoverageGaps: none\nverificationPlan: py -B -m unittest tests.test_team_router\nregressionRisks: low",
            ),
        ]
        for marker, role, extra in cases:
            base = (
                f"{marker} taskId=ctr-1\nresult: pass\nsourceThreadId: parent-thread\n"
                f"sourceRoleThreadId: role-thread\nrole: {role}\nsummary: ok\nfindings: none\n"
                f"requiredChanges: none\nevidenceChecked: tests\nrisks: none\n{extra}\n"
            )
            for field in ("sourceThreadId", "sourceRoleThreadId", "role", "skillProfileUsed"):
                with self.subTest(marker=marker, missing=field):
                    broken = "\n".join(
                        line for line in base.splitlines()
                        if not line.startswith(field + ":")
                    )
                    with self.assertRaises(team_router.ProtocolError):
                        team_router.parse_message(broken, marker, "ctr-1")

    def test_architect_and_qa_markers_reject_wrong_role_and_skill_profile_enums(self):
        architect = """TEAM_ROUTER_ARCHITECT_REVIEW taskId=ctr-1
result: pass
sourceThreadId: parent-thread
sourceRoleThreadId: thread-architect
role: Architect
summary: ok
findings: none
requiredChanges: none
evidenceChecked: tests
risks: none
skillProfileUsed: architect-default
architectureImpact: shared state
compatibilityNotes: ok
alternatives: none
migrationRisks: low
"""
        qa = """TEAM_ROUTER_QA_REVIEW taskId=ctr-1
result: pass
sourceThreadId: parent-thread
sourceRoleThreadId: thread-qa
role: QA
summary: ok
findings: none
requiredChanges: none
evidenceChecked: tests
risks: none
skillProfileUsed: qa-default
coverageGaps: none
verificationPlan: py -B -m unittest tests.test_team_router
regressionRisks: low
"""
        for marker, text in (
            ("TEAM_ROUTER_ARCHITECT_REVIEW", architect.replace("role: Architect", "role: QA")),
            ("TEAM_ROUTER_ARCHITECT_REVIEW", architect.replace("skillProfileUsed: architect-default", "skillProfileUsed: qa-default")),
            ("TEAM_ROUTER_QA_REVIEW", qa.replace("role: QA", "role: Architect")),
            ("TEAM_ROUTER_QA_REVIEW", qa.replace("skillProfileUsed: qa-default", "skillProfileUsed: architect-default")),
        ):
            with self.subTest(marker=marker):
                with self.assertRaises(team_router.ProtocolError):
                    team_router.parse_message(text, marker, "ctr-1")

    def test_architect_and_qa_unreachable_states_are_recoverable_not_terminal(self):
        snapshot = team_router.protocol_contract_snapshot()

        self.assertEqual(team_router.manual_recovery_target("architect_review_unreachable"), "awaiting_architect_review")
        self.assertEqual(team_router.manual_recovery_target("qa_review_unreachable"), "awaiting_qa_review")
        self.assertNotIn("architect_review_blocked", snapshot["recoverableStatuses"])
        self.assertNotIn("qa_review_blocked", snapshot["recoverableStatuses"])
        self.assertNotIn("architect_review_blocked", snapshot["stateMachine"]["main"])
        self.assertNotIn("qa_review_blocked", snapshot["stateMachine"]["main"])
        self.assertIn("blocked", snapshot["terminalStatuses"])
        self.assertIn("TEAM_ROUTER_ARCHITECT_REVIEW", snapshot["managerOrchestrationPolicy"]["completionFeedback"]["requiredMarkers"])
        self.assertIn("TEAM_ROUTER_QA_REVIEW", snapshot["managerOrchestrationPolicy"]["completionFeedback"]["requiredMarkers"])

    def test_architect_gate_classifier_uses_explicit_fields_and_baseline_terms(self):
        self.assertTrue(team_router.classify_architect_gate({"plan": {"fields": {"requiresArchitect": True}}}))
        self.assertTrue(team_router.classify_architect_gate({"architectureGateRequired": "required"}))
        for ledger in (
            {"objective": "change shared protocol contract"},
            {"plan": {"fields": {"scope": "state-machine and direct-return behavior"}}},
            {"plan": {"fields": {"riskBoundary": "migration compatibility uncertainty"}}},
        ):
            self.assertTrue(team_router.classify_architect_gate(ledger))
        self.assertFalse(team_router.classify_architect_gate({"objective": "ask architect to look at typo"}))

    def test_qa_gate_classifier_uses_explicit_fields_and_baseline_terms(self):
        self.assertTrue(team_router.classify_qa_gate({"plan": {"fields": {"requiresQa": True}}}))
        self.assertTrue(team_router.classify_qa_gate({"qaGateRequired": "yes"}))
        for ledger in (
            {"objective": "define test strategy and acceptance criteria"},
            {"plan": {"fields": {"scope": "regression verification plan"}}},
            {"plan": {"fields": {"riskBoundary": "coverage gap across multiple modes"}}},
        ):
            self.assertTrue(team_router.classify_qa_gate(ledger))
        self.assertFalse(team_router.classify_qa_gate({"objective": "qa should glance at this later"}))

    def test_route_explanation_reports_architect_and_qa_gates(self):
        route = team_router.explain_team_router_route({
            "plan": {
                "fields": {
                    "requiresArchitect": True,
                    "requiresQa": True,
                    "scope": "state-machine regression verification plan",
                }
            }
        })

        self.assertTrue(route["requiresArchitect"])
        self.assertTrue(route["requiresQa"])
        self.assertIn("architect", route["roles"])
        self.assertIn("qa", route["roles"])
        self.assertTrue(route["route"].startswith("architect -> executor"))
        self.assertTrue(route["route"].endswith("qa -> verifier"))

    def test_fake_thread_adapter_infers_architect_and_qa_from_explicit_role_field(self):
        adapter = FakeThreadAdapter()
        self.assertEqual(adapter.create_thread(prompt="中文说明\nrole: Architect\n")["threadId"], "thread-architect")
        self.assertEqual(adapter.create_thread(prompt="中文说明\nrole: QA\n")["threadId"], "thread-qa")

    def test_fake_thread_adapter_does_not_infer_architect_or_qa_from_free_text(self):
        adapter = FakeThreadAdapter()
        self.assertNotEqual(adapter.create_thread(prompt="please ask architect about this\n")["threadId"], "thread-architect")
        self.assertNotEqual(adapter.create_thread(prompt="qa should glance at this later\n")["threadId"], "thread-qa")


    def test_direct_return_receipt_requires_explicit_role_and_source_role_thread_id(self):
        cases = (
            ("TEAM_ROUTER_CALLBACK", "executor", team_router.parse_callback, "status: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: verifier"),
            ("TEAM_ROUTER_REVIEW", "reviewer", team_router.parse_review, "result: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"),
            ("TEAM_ROUTER_VERDICT", "verifier", team_router.parse_verdict, "result: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"),
        )
        for marker, role, parser, body in cases:
            with self.subTest(marker=marker, missing="role"):
                msg = parser(
                    "%s taskId=ctr-1\nsourceThreadId: parent-manager-thread\nsourceRoleThreadId: thread-%s\n%s" % (marker, role, body),
                    "ctr-1",
                )
                malformed = team_router._validate_direct_return_receipt(
                    msg,
                    {"messageId": "msg-return", "sentAt": "2026-06-22T20:00:00+08:00", "sourceThreadId": "thread-%s" % role},
                    task_id="ctr-1",
                    expected_role=role,
                    expected_role_thread_id="thread-%s" % role,
                    expected_return_thread_id="parent-manager-thread",
                )
                self.assertIsNotNone(malformed)
                self.assertIn("role", malformed["error"])

            with self.subTest(marker=marker, missing="sourceRoleThreadId"):
                msg = parser(
                    "%s taskId=ctr-1\nsourceThreadId: parent-manager-thread\nrole: %s\n%s" % (marker, role.title(), body),
                    "ctr-1",
                )
                malformed = team_router._validate_direct_return_receipt(
                    msg,
                    {"messageId": "msg-return", "sentAt": "2026-06-22T20:00:00+08:00", "sourceThreadId": "thread-%s" % role},
                    task_id="ctr-1",
                    expected_role=role,
                    expected_role_thread_id="thread-%s" % role,
                    expected_return_thread_id="parent-manager-thread",
                )
                self.assertIsNotNone(malformed)
                self.assertIn("sourceRoleThreadId", malformed["error"])

    def test_strict_v2_receipts_require_exact_dispatch_identity_for_all_roles_and_channels(self):
        bodies = {
            "executor": ("TEAM_ROUTER_CALLBACK", "status: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: verifier"),
            "architect": ("TEAM_ROUTER_ARCHITECT_REVIEW", "result: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none\nskillProfileUsed: architect-default\narchitectureImpact: shared\ncompatibilityNotes: ok\nalternatives: none\nmigrationRisks: low"),
            "reviewer": ("TEAM_ROUTER_REVIEW", "result: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"),
            "qa": ("TEAM_ROUTER_QA_REVIEW", "result: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none\nskillProfileUsed: qa-default\ncoverageGaps: none\nverificationPlan: tests\nregressionRisks: low"),
            "verifier": ("TEAM_ROUTER_VERDICT", "result: pass\nstatus: accepted\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"),
        }
        expected = {"protocolVersion": 2, "dispatchId": "dispatch-current", "requestId": "request-current", "attempt": 2}
        for role, (marker, body) in bodies.items():
            role_label = "QA" if role == "qa" else role.title()
            base = "%s taskId=ctr-1\nsourceThreadId: parent\nsourceRoleThreadId: thread-%s\nrole: %s\nprotocolVersion: 2\ndispatchId: dispatch-current\nrequestId: request-current\nattempt: 2\n%s" % (marker, role, role_label, body)
            msg = team_router.parse_message(base, marker, "ctr-1")
            receipt = {"messageId": "msg-1", "sentAt": "now", "sourceThreadId": "thread-%s" % role}
            for validator in (team_router._validate_direct_return_receipt, team_router._validate_self_thread_fallback_receipt):
                self.assertIsNone(validator(msg, receipt, task_id="ctr-1", expected_role=role, expected_role_thread_id="thread-%s" % role, expected_return_thread_id="parent", expected_dispatch=expected))
            for field, value in (("protocolVersion", "9"), ("dispatchId", "wrong"), ("requestId", "wrong"), ("attempt", "1"), ("attempt", "0"), ("attempt", "two")):
                mutated = base.replace("%s: %s" % (field, "2" if field in {"protocolVersion", "attempt"} else "dispatch-current" if field == "dispatchId" else "request-current"), "%s: %s" % (field, value))
                malformed = team_router._validate_direct_return_receipt(team_router.parse_message(mutated, marker, "ctr-1"), receipt, task_id="ctr-1", expected_role=role, expected_role_thread_id="thread-%s" % role, expected_return_thread_id="parent", expected_dispatch=expected)
                self.assertIsNotNone(malformed)
            missing = base.replace("\nrequestId: request-current", "")
            self.assertIsNotNone(team_router._validate_direct_return_receipt(team_router.parse_message(missing, marker, "ctr-1"), receipt, task_id="ctr-1", expected_role=role, expected_role_thread_id="thread-%s" % role, expected_return_thread_id="parent", expected_dispatch=expected))

    def test_strict_dispatch_never_falls_back_to_an_older_role_receipt(self):
        ledger = {"workflowVersion": 2, "dispatches": [
            {"role": "executor", "threadId": "legacy-thread", "returnThreadId": "parent", "callbackDelivery": "direct-send"},
            {"role": "executor", "protocolVersion": 2, "dispatchId": "current", "deliveryStatus": "prepared"},
        ]}

        self.assertIsNone(team_router_direct_return._direct_return_record(ledger, "executor"))

    def test_v1_and_legacy_v2_receipt_migration_matrix(self):
        base = "TEAM_ROUTER_CALLBACK taskId=ctr-1\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: verifier\nsourceThreadId: parent\nsourceRoleThreadId: thread-executor\nrole: Executor"
        receipt = {"messageId": "msg-1", "sentAt": "now", "sourceThreadId": "thread-executor"}
        legacy = {"role": "executor", "requestId": "legacy-request"}
        strict = {"role": "executor", "protocolVersion": 2, "dispatchId": "dispatch-1", "requestId": "request-1", "attempt": 1}

        self.assertIsNone(team_router._validate_direct_return_receipt(team_router.parse_callback(base, "ctr-1"), receipt, task_id="ctr-1", expected_role="executor", expected_role_thread_id="thread-executor", expected_return_thread_id="parent", expected_dispatch=legacy))
        strict_only = base + "\nprotocolVersion: 2\ndispatchId: dispatch-1\nrequestId: request-1\nattempt: 1"
        self.assertIsNotNone(team_router._validate_direct_return_receipt(team_router.parse_callback(strict_only, "ctr-1"), receipt, task_id="ctr-1", expected_role="executor", expected_role_thread_id="thread-executor", expected_return_thread_id="parent", expected_dispatch=legacy))
        self.assertIsNotNone(team_router._validate_direct_return_receipt(team_router.parse_callback(base, "ctr-1"), receipt, task_id="ctr-1", expected_role="executor", expected_role_thread_id="thread-executor", expected_return_thread_id="parent", expected_dispatch=strict))
        unknown = strict_only.replace("protocolVersion: 2", "protocolVersion: 9")
        self.assertIsNotNone(team_router._validate_direct_return_receipt(team_router.parse_callback(unknown, "ctr-1"), receipt, task_id="ctr-1", expected_role="executor", expected_role_thread_id="thread-executor", expected_return_thread_id="parent", expected_dispatch=strict))
    def test_manager_direct_return_messages_reads_return_thread(self):
        adapter = FakeThreadAdapter()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-return",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "sourceThreadId": "thread-executor",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-1\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: verifier",
            },
        ]
        adapter.messages["thread-executor"] = [
            {
                "messageId": "msg-fallback",
                "sentAt": "2026-06-22T20:03:30+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-1\nstatus: blocked\nfinal: true\nsummary: wrong inbox\nevidence: tests\nrisks: none\nnext: none",
            },
        ]

        messages = team_router._manager_direct_return_messages_with_adapter(
            adapter,
            {"returnThreadId": "parent-manager-thread", "threadId": "thread-executor"},
            turn_limit=7,
        )

        self.assertEqual(adapter.sent, [])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["messageId"], "msg-return")
        self.assertIn("summary: ok", messages[0]["text"])

    def test_direct_return_protocol_message_filters_anchor_and_source_thread(self):
        messages = [
            {
                "messageId": "msg-anchor",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "sourceThreadId": "thread-executor",
                "text": "dispatch anchor",
            },
            {
                "messageId": "msg-wrong-source",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "sourceThreadId": "thread-other",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-1\nstatus: done\nfinal: true\nsummary: wrong source\nevidence: tests\nrisks: none\nnext: verifier",
            },
            {
                "messageId": "msg-return",
                "sentAt": "2026-06-22T20:04:00+08:00",
                "sourceThreadId": "thread-executor",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-1\nstatus: done\nfinal: true\nsummary: direct return\nevidence: tests\nrisks: none\nnext: verifier",
            },
        ]

        msg, malformed, manager_message = team_router._direct_return_protocol_message(
            messages,
            marker="TEAM_ROUTER_CALLBACK",
            task_id="ctr-1",
            source_thread_id="thread-executor",
            anchor={"messageId": "msg-anchor"},
        )

        self.assertIsNone(malformed)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.fields["summary"], "direct return")
        self.assertEqual(manager_message["messageId"], "msg-return")

    def test_direct_return_protocol_message_uses_marker_bearing_message_metadata(self):
        messages = [
            {
                "messageId": "msg-return",
                "sentAt": "2026-06-22T20:04:00+08:00",
                "sourceThreadId": "thread-executor",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-1\nstatus: done\nfinal: true\nsummary: direct return\nevidence: tests\nrisks: none\nnext: verifier",
            },
            {
                "messageId": "msg-later-chat",
                "sentAt": "2026-06-22T20:05:00+08:00",
                "sourceThreadId": "thread-executor",
                "text": "I also left a plain-language note after the protocol block.",
            },
        ]

        msg, malformed, manager_message = team_router._direct_return_protocol_message(
            messages,
            marker="TEAM_ROUTER_CALLBACK",
            task_id="ctr-1",
            source_thread_id="thread-executor",
            anchor=None,
        )

        self.assertIsNone(malformed)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.fields["summary"], "direct return")
        self.assertEqual(manager_message["messageId"], "msg-return")
        self.assertEqual(manager_message["sentAt"], "2026-06-22T20:04:00+08:00")

    def test_direct_return_protocol_message_reports_wrong_task_for_candidate(self):
        messages = [
            {
                "messageId": "msg-return",
                "sentAt": "2026-06-22T20:04:00+08:00",
                "sourceThreadId": "thread-executor",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-other\nstatus: done\nfinal: true\nsummary: wrong task\nevidence: tests\nrisks: none\nnext: verifier",
            },
        ]

        msg, malformed, manager_message = team_router._direct_return_protocol_message(
            messages,
            marker="TEAM_ROUTER_CALLBACK",
            task_id="ctr-1",
            source_thread_id="thread-executor",
            anchor=None,
        )

        self.assertIsNone(msg)
        self.assertIsNotNone(malformed)
        self.assertEqual(manager_message["messageId"], "msg-return")
        self.assertEqual(malformed["messageId"], "msg-return")
        self.assertIn("taskId", malformed["error"])

    def test_protocol_contract_snapshot_includes_active_role_return_model(self):
        policy = team_router.protocol_contract_snapshot()["managerOrchestrationPolicy"]
        model = policy["callbackDeliveryModel"]

        self.assertIn("direct-send", model["primaryDelivery"])
        self.assertIn("threadId=<returnThreadId>", model["primaryDelivery"])
        self.assertIn("prompt=<完整 TEAM_ROUTER_* block>", model["primaryDelivery"])
        self.assertNotIn("send_message_to_thread(sourceThreadId, protocolBlock)", model["primaryDelivery"])
        self.assertIn("self-thread-marker", model["fallback"])
        self.assertIn("sourceThreadId", model["requiredDispatchFields"])
        self.assertIn("sourceRoleThreadId", model["requiredDispatchFields"])
        self.assertIn("role", model["requiredDispatchFields"])
        self.assertIn("callbackMarker", model["requiredDispatchFields"])
        self.assertIn("returnThreadId", model["requiredDispatchFields"])
        self.assertIn("callbackDelivery: direct-send", model["requiredDispatchFields"])
        self.assertIn("callbackFallback: self-thread-marker", model["requiredDispatchFields"])
        self.assertIn("reviewDelivery: direct-send", model["requiredDispatchFields"])
        self.assertIn("reviewFallback: self-thread-marker", model["requiredDispatchFields"])
        self.assertIn("verdictDelivery: direct-send", model["requiredDispatchFields"])
        self.assertIn("verdictFallback: self-thread-marker", model["requiredDispatchFields"])
        self.assertIn("architectReviewDelivery: direct-send", model["requiredDispatchFields"])
        self.assertIn("architectReviewFallback: self-thread-marker", model["requiredDispatchFields"])
        self.assertIn("qaReviewDelivery: direct-send", model["requiredDispatchFields"])
        self.assertIn("qaReviewFallback: self-thread-marker", model["requiredDispatchFields"])
        self.assertIn("taskId", model["managerReceiptValidation"])
        self.assertIn("sourceThreadId", model["managerReceiptValidation"])
        self.assertIn("role", model["managerReceiptValidation"])
        self.assertIn("sourceRoleThreadId", model["managerReceiptValidation"])
        self.assertIn("returnThreadId", model["managerReceiptValidation"])
        self.assertIn("same protocol block body", model["fallbackBodyInvariant"])
        self.assertIn("deliveryStatus: fallback_only", model["fallbackMetadata"])
        self.assertIn("deliveryError", model["fallbackMetadata"])
        self.assertIn("two-step bootstrap", model["roleThreadBootstrap"])
        self.assertIn("create", model["roleThreadBootstrap"])
        self.assertIn("dispatch", model["roleThreadBootstrap"])
        self.assertIn("direct-send", model["proactiveReturnRule"])
        self.assertIn("key checks complete", model["proactiveReturnRule"])
        self.assertIn("must not rely on parent polling", model["proactiveReturnRule"])
        self.assertIn("watcher-only", model["boundedControlFallback"])
        self.assertIn("deliveryStatus: fallback_only", model["boundedControlFallback"])
        self.assertIn("delivery degraded", model["boundedControlFallback"])
        self.assertIn("not normal success", model["boundedControlFallback"])
        self.assertIn("bounded wait/read", model["boundedControlFallback"])
        self.assertIn("scope-limited closeout", model["boundedControlFallback"])
        self.assertIn("already-confirmed facts", model["boundedControlFallback"])

    def test_protocol_contract_snapshot_defends_active_role_wait_and_polling_backoff(self):
        policy = team_router.protocol_contract_snapshot()["managerOrchestrationPolicy"]
        polling = policy["polling"]
        convergence = policy["convergence"]

        self.assertEqual(polling["manualPollBackoffSeconds"], (10, 20, 40))
        self.assertIn("active/inProgress/running/working", polling["activeRoleStatusMeaning"])
        self.assertIn("normal processing", polling["activeRoleStatusMeaning"])
        self.assertIn("do not restart", polling["activeRoleInterventionBoundary"])
        self.assertIn("do not send a shorter delta prompt", polling["activeRoleInterventionBoundary"])
        self.assertIn("first active observation", polling["userVisibleUpdates"])
        self.assertIn("status changes", polling["userVisibleUpdates"])
        self.assertIn("do not repeat unchanged active status", polling["userVisibleUpdates"])
        self.assertIn("one timeout notice", polling["timeoutNoticePolicy"])
        self.assertIn("firstCheckAt", polling["scheduleRespect"])
        self.assertIn("nextAllowedReadAt", polling["scheduleRespect"])
        self.assertIn("no manual reads before nextAllowedReadAt", polling["scheduleRespect"])
        self.assertIn("slow progress alone is not enough", convergence["retryWithFreshRoleThread"])
        self.assertIn("active/inProgress/running/working means the role is still processing", convergence["activeRoleMeaning"])
    def test_protocol_contract_snapshot_includes_standing_role_reuse_policy(self):
        policy = team_router.protocol_contract_snapshot()["managerOrchestrationPolicy"]
        reuse = policy["roleReuse"]
        reviewer_gate = policy["conditionalReviewerGate"]

        self.assertIn("standing", reuse["default"])
        self.assertIn("existing executor", reuse["default"])
        self.assertIn("existing reviewer", reuse["default"])
        self.assertIn("existing verifier", reuse["default"])
        self.assertIn("same taskId or task family", reuse["default"])
        self.assertIn("first missing role binding", reuse["newThreadOnlyWhen"])
        self.assertIn("role/thread unavailable or archived/broken", reuse["newThreadOnlyWhen"])
        self.assertIn("permission boundary changes", reuse["newThreadOnlyWhen"])
        self.assertIn("workspace boundary changes", reuse["newThreadOnlyWhen"])
        self.assertIn("task-family boundary changes", reuse["newThreadOnlyWhen"])
        self.assertIn("isolation/audit boundary changes", reuse["newThreadOnlyWhen"])
        self.assertIn("concurrency conflict", reuse["newThreadOnlyWhen"])
        self.assertIn("model/capability requirement", reuse["newThreadOnlyWhen"])
        self.assertIn("archived role/thread", reuse["archivedNoReuseRequirement"])
        self.assertIn("unavailable for reuse, period", reuse["archivedNoReuseRequirement"])
        self.assertIn("non-archived visible replacement role", reuse["archivedNoReuseRequirement"])
        self.assertIn("replacement reason", reuse["archivedNoReuseRequirement"])
        self.assertNotIn("unarchived", reuse["archivedNoReuseRequirement"])
        self.assertNotIn("history/current turn load normally", reuse["archivedNoReuseRequirement"])
        self.assertIn("original executor", reuse["reworkExecutor"])
        self.assertIn("original reviewer", reuse["reworkReviewer"])
        self.assertIn("original verifier", reuse["reworkVerifier"])
        self.assertIn("fresh searchAnchor", reuse["dispatchFreshness"])
        self.assertIn("stale search anchor", reuse["dispatchFreshness"])
        self.assertNotIn("max", reuse["default"].lower())
        self.assertIn("same reviewer", reviewer_gate["roleReuse"])
        self.assertIn("review lens", reviewer_gate["roleReuse"])
        self.assertIn("compliance review", reviewer_gate["roleReuse"])
        self.assertIn("code-quality review", reviewer_gate["roleReuse"])
        self.assertIn("original reviewer", reviewer_gate["roleReuse"])

    def test_executor_dispatch_has_one_canonical_role_and_dispatch_role(self):
        message = team_router.make_executor_dispatch_message(
            "ctr-20260715-executor-role",
            {"scope": "src/team_router.py", "stopWhen": "tests pass", "executorPrompt": "fix one issue"},
            "local-package",
            {"messageId": "msg-1", "sentAt": "2026-07-15T10:00:00+08:00"},
        )
        self.assertIn("dispatchRole: executor", message)
        self.assertEqual(message.count("role: Executor"), 1)
        self.assertNotIn("role: executor", message)

    def test_role_request_messages_keep_protocol_keys_but_require_chinese_human_text(self):
        task_id = "ctr-20260628-chinese-callback"
        plan_fields = {
            "scope": "docs/compounding.md tests/test_team_router.py",
            "stopWhen": "中文模板和测试完成",
            "executorPrompt": "更新中文复利模板，并用中文说明变更、证据和风险。",
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: 已更新中文规则\n"
            "evidence: tests\n"
            "risks: none\n"
            "next: reviewer"
        ) % task_id
        messages = (
            team_router.make_role_thread_prompt(
                task_id,
                "executor",
                "用中文完成 Team Router 任务。",
            ),
            team_router.make_plan_request_message(
                task_id,
                "规划一次中文 Team Router 任务。",
                "local-package",
            ),
            team_router.make_executor_dispatch_message(
                task_id,
                plan_fields,
                "local-package",
                {"messageId": "msg-dispatch", "sentAt": "2026-06-28T10:00:00+08:00"},
            ),
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
            ),
        )

        for message in messages:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("语言规则：协议 marker、字段名和枚举值保持英文", message)
                self.assertIn("默认用中文", message)
                self.assertIn("命令、路径、文件名", message)
                self.assertIn("TEAM_ROUTER_", message)
        self.assertIn("等待 TEAM_ROUTER_* 协议消息后再行动。", messages[0])
        self.assertIn("请在本线程按以下格式回复：", messages[1])
        self.assertIn("summary", messages[2])
        self.assertIn("evidence", messages[2])
        self.assertIn("risks", messages[2])
        self.assertIn("next", messages[2])
        self.assertIn("findings", messages[3])
        self.assertIn("requiredChanges", messages[3])
        self.assertIn("evidenceChecked", messages[3])
        self.assertIn("requiredChanges", messages[4])
        self.assertIn("evidenceChecked", messages[4])

    def test_role_request_templates_default_to_compact_path_based_outputs(self):
        task_id = "ctr-20260628-compact-templates"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "stopWhen": "模板默认变短并且测试通过",
            "riskBoundary": "不改变 gate 语义，不做 push/global sync",
            "executorPrompt": "把 Team Router 角色模板默认改短。",
            "taskBriefPath": "docs/team-router/packages/ctr-compact-brief.md",
            "executorReportPath": "docs/team-router/packages/ctr-compact-executor.md",
            "reviewPackagePath": "docs/team-router/packages/ctr-compact-review.md",
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: 模板已改短\n"
            "evidence: tests\n"
            "risks: none\n"
            "next: verifier"
        ) % task_id
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": plan_fields["taskBriefPath"],
                "executorReportPath": plan_fields["executorReportPath"],
                "reviewPackagePath": plan_fields["reviewPackagePath"],
            },
        }

        messages = (
            team_router.make_executor_dispatch_message(
                task_id,
                plan_fields,
                "local-package",
                {"messageId": "msg-dispatch", "sentAt": "2026-06-28T10:00:00+08:00"},
                review_package=review_package,
            ),
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
                review_package=review_package,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
                review_package=review_package,
            ),
        )

        for message in messages:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("roleCommunicationMode: concise-protocol-plus-paths", message)
                self.assertIn("taskBriefPath", message)
                self.assertIn("executorReportPath", message)
                self.assertIn("reviewPackagePath", message)
        self.assertIn("returnPayload: one summary field + path/counts; no logs", messages[0])
        self.assertIn("不要复制完整 diff、完整日志、完整背景或完整角色推理", messages[0])
        self.assertIn("保留 executor/reviewer/verifier gate；省 token 只改变交接形状", messages[0])
        self.assertIn("deltaSince: <first-response 或上一个 TEAM_ROUTER_* marker/package path>", messages[0])
        self.assertIn("executorReportPath: <报告路径或 inline>", messages[0])
        self.assertIn("reviewPackagePath: <review package 路径或 inline>", messages[0])
        self.assertIn("summary: <中文 1-2 行，不复述背景；done 只写结果>", messages[0])
        self.assertIn("evidence: <executorReportPath/reviewPackagePath 路径；tests: 短计数；不要粘贴完整日志>", messages[0])
        self.assertIn("longEvidencePolicy: 长 evidence/checklist/log transcript 写入 executorReportPath 或 reviewPackagePath；blocked 可写短原因加路径", messages[0])
        self.assertIn("reviewPackagePath: <path|inline>", messages[1])
        self.assertIn("reviewPackagePath: <path|inline>", messages[2])
        for message in messages[1:]:
            with self.subTest(reply_policy=message.splitlines()[0]):
                self.assertIn(
                    "replyPolicy: pass/done exactly one summary field; evidenceChecked format: <reviewPackagePath>; tests: N OK; checks: M OK",
                    message,
                )

    def test_role_request_templates_codify_md_first_caveman_transport(self):
        task_id = "ctr-20260702-md-first-caveman-transport"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py docs/workbench.md",
            "stopWhen": "md-first + caveman transport prompt contract is documented and verified",
            "riskBoundary": "prompt/policy wording only; no parser/runtime/watcher changes",
            "executorPrompt": (
                "把重要事实、证据、完整 checklist 和 transcript 放进 Markdown package/report，"
                "parent/role chat 只回 marker/path/result/counts/next。"
            ),
            "taskBriefPath": "docs/team-router/packages/ctr-20260702-md-first-caveman-transport.md",
            "executorReportPath": "docs/team-router/packages/ctr-20260702-md-first-caveman-transport.md#executor-report",
            "reviewPackagePath": "docs/team-router/packages/ctr-20260702-md-first-caveman-transport.md",
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: md-first transport 已写入 prompt。\n"
            "evidence: %s; tests: short counts only\n"
            "risks: none\n"
            "next: reviewer"
        ) % (task_id, plan_fields["reviewPackagePath"])
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": plan_fields["taskBriefPath"],
                "executorReportPath": plan_fields["executorReportPath"],
                "reviewPackagePath": plan_fields["reviewPackagePath"],
            },
        }

        messages = (
            team_router.make_executor_dispatch_message(
                task_id,
                plan_fields,
                "local-package",
                {"messageId": "msg-dispatch", "sentAt": "2026-07-02T10:00:00+08:00"},
                return_thread_id="manager-thread",
                role_thread_id="executor-thread",
                review_package=review_package,
            ),
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                return_thread_id="manager-thread",
                role_thread_id="reviewer-thread",
                plan_fields=plan_fields,
                review_package=review_package,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                return_thread_id="manager-thread",
                role_thread_id="verifier-thread",
                plan_fields=plan_fields,
                review_package=review_package,
                reviewer_result={
                    "fields": {
                        "result": "pass",
                        "summary": "短审查摘要",
                        "requiredChanges": "none",
                        "risks": "none",
                    }
                },
            ),
        )

        snapshot = team_router.protocol_contract_snapshot()
        economy = snapshot["roleHandoffReviewPackagePolicy"]["roleCommunicationEconomy"]
        self.assertEqual(
            economy["mdFirstPolicy"],
            "important facts, decisions, evidence, full logs, checklists, and transcripts go to taskBriefPath, executorReportPath, or reviewPackagePath",
        )
        self.assertEqual(
            economy["parentRoleChatPolicy"],
            "parent/role chat carries only TEAM_ROUTER_* marker blocks, path pointers, result, short counts, risks, and next",
        )
        self.assertEqual(
            economy["cavemanTransportPolicy"],
            "compress only ordinary prose, fluff, and repeated context; preserve TEAM_ROUTER_* schema, field names, enum values, paths, commands, errors, and requiredChanges exactly",
        )

        for message in messages:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("mdFirstPolicy", message)
                self.assertIn("cavemanTransportPolicy", message)
                self.assertIn("TEAM_ROUTER_* schema", message)
                self.assertIn("paths", message)
                self.assertIn("commands", message)
                self.assertIn("errors", message)
                self.assertIn("requiredChanges", message)
                self.assertNotIn("full checklist:", message)
                self.assertNotIn("full transcript:", message)

        self.assertIn("importantFactsRoute: taskBriefPath/executorReportPath/reviewPackagePath", messages[0])
        self.assertIn("parentRoleChatPolicy: marker,path,result,short-counts,next only", messages[0])
        self.assertIn(
            "noFullLogsInParentThread: full logs/checklists/transcripts stay in package/report paths",
            messages[0],
        )

        for message in messages[1:]:
            with self.subTest(minimal_role_prompt=message.splitlines()[0]):
                self.assertIn("replyFields:", message)
                self.assertIn("reviewPackagePath: <path|inline>", message)
                self.assertIn(
                    "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
                    message,
                )

    def test_compact_reply_examples_accept_path_valued_evidence_checked(self):
        task_id = "ctr-20260702-compact-role-return-payload"
        package_path = "docs/team-router/packages/ctr-20260702-compact-role-return-payload.md"
        review_block = (
            "TEAM_ROUTER_REVIEW taskId=%s\n"
            "result: pass\n"
            "summary: 短返回模板已审查，证据指向 package。\n"
            "findings: none\n"
            "requiredChanges: none\n"
            "evidenceChecked: %s; tests: 4 OK; checks: 2 OK\n"
            "risks: none\n"
            "next: verifier"
        ) % (task_id, package_path)
        verdict_block = (
            "TEAM_ROUTER_VERDICT taskId=%s\n"
            "result: pass\n"
            "summary: 短返回模板验收通过，未改变 runtime 行为。\n"
            "requiredChanges: none\n"
            "evidenceChecked: %s; tests: 4 OK; checks: 2 OK\n"
            "risks: none\n"
            "next: closeout"
        ) % (task_id, package_path)

        review = team_router.parse_review(review_block, task_id)
        verdict = team_router.parse_verdict(verdict_block, task_id)

        self.assertEqual(review.fields["evidenceChecked"], "%s; tests: 4 OK; checks: 2 OK" % package_path)
        self.assertEqual(verdict.fields["evidenceChecked"], "%s; tests: 4 OK; checks: 2 OK" % package_path)

    def test_package_path_pass_returns_require_single_summary_and_count_only_evidence(self):
        task_id = "ctr-20260702-single-summary-count-only-return"
        package_path = "docs/team-router/packages/ctr-20260702-single-summary-count-only-return.md"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py docs/workbench.md %s" % package_path,
            "taskBriefPath": "docs/workbench.md",
            "executorReportPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: 返回模板已收紧\n"
            "evidence: %s; tests: 1 OK; checks: 0 OK\n"
            "risks: none\n"
            "next: reviewer"
        ) % (task_id, package_path)
        reviewer_result = {
            "fields": {
                "result": "pass",
                "summary": "模板审查通过",
                "findings": "none",
                "requiredChanges": "none",
                "evidenceChecked": "%s; tests: 1 OK; checks: 0 OK" % package_path,
                "risks": "none",
            },
        }
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": plan_fields["taskBriefPath"],
                "executorReportPath": package_path,
                "reviewPackagePath": package_path,
            },
        }

        messages = (
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                "thread-parent",
                role_thread_id="thread-reviewer",
                plan_fields=plan_fields,
                review_package=review_package,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                "thread-parent",
                role_thread_id="thread-verifier",
                plan_fields=plan_fields,
                review_package=review_package,
                reviewer_result=reviewer_result,
            ),
        )

        for message in messages:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("replyFields:", message)
                self.assertIn(
                    "replyPolicy: pass/done exactly one summary field; evidenceChecked format: <reviewPackagePath>; tests: N OK; checks: M OK",
                    message,
                )
                self.assertNotIn("summary: <中文 1-2 行", message)
                self.assertNotIn("replyPolicy: pass 1-2 lines", message)
                self.assertNotIn("完整日志", message)
                self.assertNotIn("full checklist", message)


    def test_read_only_role_requests_without_review_package_stay_compact(self):
        task_id = "ctr-20260703-compact-readonly-role-request"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "riskBoundary": "只读检查；不修改文件、不运行写入命令",
            "executorPrompt": "只读检查普通 reviewer/verifier 请求模板。",
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: 已完成只读检查\n"
            "evidence: focused inspection\n"
            "risks: none\n"
            "next: reviewer"
        ) % task_id

        messages = (
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "read-only",
                plan_fields["scope"],
                "thread-parent",
                role_thread_id="thread-reviewer",
                plan_fields=plan_fields,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "read-only",
                plan_fields["scope"],
                "thread-parent",
                role_thread_id="thread-verifier",
                plan_fields=plan_fields,
            ),
        )

        expectations = (
            (
                messages[0],
                "action: 只读审查执行者 callback；检查 scope/riskBoundary；返回 TEAM_ROUTER_REVIEW。",
                "reply: TEAM_ROUTER_REVIEW result,summary,findings,requiredChanges,evidenceChecked,risks,next",
            ),
            (
                messages[1],
                "action: 只读验收执行者 callback；检查 scope/riskBoundary；返回 TEAM_ROUTER_VERDICT。",
                "reply: TEAM_ROUTER_VERDICT result,summary,requiredChanges,evidenceChecked,risks,next",
            ),
        )
        for message, action_line, reply_line in expectations:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("permission: read-only", message)
                self.assertIn("riskBoundary: 只读检查；不修改文件、不运行写入命令", message)
                self.assertIn(action_line, message)
                self.assertIn(reply_line, message)
                self.assertNotIn("reviewPackagePath:", message)
                self.assertNotIn("Fresh parent facts:", message)
                self.assertNotIn("Review expectations:", message)
                self.assertNotIn("请在本线程按以下格式回复：", message)
                self.assertNotIn("result: pass | needs_rework | blocked", message)
                self.assertNotIn("summary: <中文", message)
                self.assertNotIn("evidenceChecked:", message)
                self.assertNotIn("directReturnAttempt:", message)


    def test_manager_reviewer_verifier_prompts_codify_path_handoff_contract(self):
        task_id = "ctr-20260630-role-thread-prompt-path-contract"
        role_prompts = (
            team_router.make_role_thread_prompt(
                task_id,
                "manager",
                "规划并调度一个 path handoff package。",
            ),
            team_router.make_role_thread_prompt(
                task_id,
                "reviewer",
                "审查 path handoff package。",
            ),
            team_router.make_role_thread_prompt(
                task_id,
                "verifier",
                "验收 path handoff package。",
            ),
        )
        manager_request = team_router.make_plan_request_message(
            task_id,
            "让 Manager 规划一个 PACKAGE 级别任务，并使用稳定路径交接。",
            "local-package",
        )

        for prompt in role_prompts:
            with self.subTest(role=prompt.splitlines()[2]):
                self.assertIn("roleCommunicationMode: concise-protocol-plus-paths", prompt)
                self.assertIn("taskBriefPath", prompt)
                self.assertIn("executorReportPath", prompt)
                self.assertIn("reviewPackagePath", prompt)
                self.assertIn("returnPayloadPolicy: pass/done 只写 exactly one summary field", prompt)
                self.assertIn("<reviewPackagePath>; tests: N OK; checks: M OK", prompt)
                self.assertIn("longEvidencePolicy: 长日志、完整 checklist、transcript 和完整证据写入", prompt)
                self.assertIn("reworkPayloadPolicy: fail/needs_rework/blocked", prompt)
                self.assertIn("路径只作为交接证据", prompt)
                self.assertIn("permission", prompt)
                self.assertIn("riskBoundary", prompt)

        self.assertIn("roleCommunicationMode: concise-protocol-plus-paths", manager_request)
        self.assertIn("PACKAGE 默认使用 reviewPackagePath", manager_request)
        self.assertIn("taskBriefPath: <任务 brief 的 workspace 路径>", manager_request)
        self.assertIn("executorReportPath: <执行者报告的 workspace 路径>", manager_request)
        self.assertIn("reviewPackagePath: <review package 的 workspace 路径> | inline", manager_request)

    def test_role_thread_package_bootstrap_is_pointer_only(self):
        task_id = "ctr-20260701-role-thread-bootstrap-package-only"
        message = team_router.make_role_thread_package_bootstrap_message(
            task_id,
            "verifier",
            "read-only",
            "docs/team-router/packages/ctr-20260701-role-thread-bootstrap-package-only.md",
            source_thread_id="019f18c7-86d8-7de2-9c43-c072a255ba20",
            reviewer_thread_id="019f1984-0ec5-7f41-84d4-64104e03ef36",
            reviewer_result="pass",
        )

        self.assertTrue(message.startswith("TEAM_ROUTER_VERIFY\n\n<codex_delegation>"))
        self.assertIn("<source_thread_id>019f18c7-86d8-7de2-9c43-c072a255ba20</source_thread_id>", message)
        self.assertIn("<input>role: verifier", message)
        self.assertIn("permission: read-only", message)
        self.assertIn("package: ctr-20260701-role-thread-bootstrap-package-only", message)
        self.assertIn(
            "reviewPackagePath: docs/team-router/packages/ctr-20260701-role-thread-bootstrap-package-only.md",
            message,
        )
        self.assertIn("reviewerThreadId: 019f1984-0ec5-7f41-84d4-64104e03ef36", message)
        self.assertIn("reviewerResult: pass", message)
        self.assertIn("请只读取 package path", message)
        self.assertIn("不要复制 raw callback/review/verifier evidence", message)
        self.assertIn("按 package 中的 role contract 返回标准 TEAM_ROUTER_* marker", message)
        self.assertLess(len(message), 750)
        for raw_evidence in (
            "TEAM_ROUTER_REVIEW",
            "TEAM_ROUTER_VERDICT",
            "Reviewer v2 marker",
            "Scope:",
            "Please check",
            "Return only",
            "evidenceChecked:",
            "findings:",
            "requiredChanges:",
            "主工作区 verifier 前 fresh evidence",
        ):
            self.assertNotIn(raw_evidence, message)

        reviewer_message = team_router.make_role_thread_package_bootstrap_message(
            task_id,
            "reviewer",
            "read-only",
            "docs/team-router/packages/ctr-20260701-role-thread-bootstrap-package-only.md",
        )
        self.assertTrue(reviewer_message.startswith("TEAM_ROUTER_REVIEW_REQUEST\n\n<codex_delegation>"))
        self.assertLess(len(reviewer_message), 650)
        self.assertNotIn("Scope:", reviewer_message)
        self.assertNotIn("Please check", reviewer_message)
        self.assertNotIn("Return only", reviewer_message)

        rejected_values = (
            {
                "review_package_path": "docs/team-router/packages/ctr-20260701-role-thread-bootstrap-package-only.md\nTEAM_ROUTER_REVIEW",
            },
            {
                "review_package_path": "docs/team-router/packages/ctr-20260701-role-thread-bootstrap-package-only.md;type secrets",
            },
            {
                "reviewer_result": "pass\nTEAM_ROUTER_REVIEW\nevidenceChecked: full log",
            },
            {
                "reviewer_result": "evidenceChecked: copied schema",
            },
            {
                "reviewer_result": "requiredChanges: copied schema",
            },
            {
                "source_thread_id": "019f18c7-86d8-7de2-9c43-c072a255ba20\nTEAM_ROUTER_VERDICT",
            },
        )
        for kwargs in rejected_values:
            with self.subTest(kwargs=kwargs):
                call_kwargs = {
                    "source_thread_id": kwargs.get("source_thread_id"),
                    "reviewer_thread_id": kwargs.get("reviewer_thread_id"),
                    "reviewer_result": kwargs.get("reviewer_result"),
                }
                with self.assertRaises(team_router.StateStoreError):
                    team_router.make_role_thread_package_bootstrap_message(
                        task_id,
                        "verifier",
                        "read-only",
                        kwargs.get(
                            "review_package_path",
                            "docs/team-router/packages/ctr-20260701-role-thread-bootstrap-package-only.md",
                        ),
                        **call_kwargs,
                    )

    def test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists(self):
        task_id = "ctr-20260630-dispatch-prompt-path-handoff"
        long_executor_prompt = "LONG_EXECUTOR_PROMPT_" + ("x" * 2400)
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "stopWhen": "dispatch prompt references package paths instead of copying long instructions",
            "riskBoundary": "do not change parser, gate, or direct-return semantics",
            "executorPrompt": long_executor_prompt,
            "taskBriefPath": "docs/team-router/packages/ctr-20260630-dispatch-prompt-path-handoff.md",
            "executorReportPath": "docs/team-router/packages/ctr-20260630-dispatch-prompt-path-handoff.md",
            "reviewPackagePath": "docs/team-router/packages/ctr-20260630-dispatch-prompt-path-handoff.md",
        }
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": plan_fields["taskBriefPath"],
                "executorReportPath": plan_fields["executorReportPath"],
                "reviewPackagePath": plan_fields["reviewPackagePath"],
            },
        }

        message = team_router.make_executor_dispatch_message(
            task_id,
            plan_fields,
            "local-package",
            {"messageId": "msg-dispatch", "sentAt": "2026-06-30T10:00:00+08:00"},
            review_package=review_package,
        )

        self.assertIn("taskBriefPath: docs/team-router/packages/ctr-20260630-dispatch-prompt-path-handoff.md", message)
        self.assertIn("reviewPackagePath: docs/team-router/packages/ctr-20260630-dispatch-prompt-path-handoff.md", message)
        self.assertIn("executorPrompt: <omitted; see taskBriefPath/reviewPackagePath>", message)
        self.assertNotIn(long_executor_prompt, message)

    def test_executor_dispatch_keeps_long_prompt_inline_without_task_or_review_path(self):
        task_id = "ctr-20260630-dispatch-prompt-inline-fallback"
        long_executor_prompt = "LONG_INLINE_EXECUTOR_PROMPT_" + ("y" * 2400)
        base_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "stopWhen": "inline fallback keeps complete prompt text",
            "riskBoundary": "do not change parser, gate, or direct-return semantics",
            "executorPrompt": long_executor_prompt,
        }

        scenarios = (
            (dict(base_fields, inlineFallback="true"), {"inlineFallback": True}),
            (dict(base_fields, executorReportPath="docs/team-router/packages/executor-only.md"), {"paths": {"executorReportPath": "docs/team-router/packages/executor-only.md"}}),
            (dict(base_fields), None),
        )

        for fields, review_package in scenarios:
            with self.subTest(fields=sorted(fields)):
                message = team_router.make_executor_dispatch_message(
                    task_id,
                    fields,
                    "local-package",
                    {"messageId": "msg-dispatch", "sentAt": "2026-06-30T10:05:00+08:00"},
                    review_package=review_package,
                )

                self.assertIn(long_executor_prompt, message)
                self.assertNotIn("executorPrompt: <omitted; see taskBriefPath/reviewPackagePath>", message)


    def test_path_handoff_omits_long_callback_raw_from_downstream_prompts(self):
        task_id = "ctr-20260630-compact-downstream"
        long_payload = "LONG_CALLBACK_PAYLOAD_" + ("x" * 2400)
        long_review_payload = "LONG_REVIEW_PAYLOAD_" + ("y" * 2400)
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "stopWhen": "downstream role prompts do not copy long callback/review raw text",
            "riskBoundary": "do not change parser or gate semantics",
            "executorPrompt": "Fix downstream prompt compact handoff.",
            "taskBriefPath": "docs/team-router/packages/ctr-compact-downstream.md",
            "executorReportPath": "docs/team-router/packages/ctr-compact-downstream.md",
            "reviewPackagePath": "docs/team-router/packages/ctr-compact-downstream.md",
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: compact downstream prompt fix done\n"
            "evidence: %s\n"
            "risks: none\n"
            "next: reviewer"
        ) % (task_id, long_payload)
        reviewer_result = {
            "raw": (
                "TEAM_ROUTER_REVIEW taskId=%s\n"
                "result: pass\n"
                "summary: %s\n"
                "findings: none\n"
                "requiredChanges: none\n"
                "evidenceChecked: docs/team-router/packages/ctr-compact-downstream.md\n"
                "risks: none"
            ) % (task_id, long_review_payload),
            "fields": {
                "result": "pass",
                "summary": "reviewer passed",
                "findings": "none",
                "requiredChanges": "none",
                "evidenceChecked": "docs/team-router/packages/ctr-compact-downstream.md",
                "risks": "none",
            },
        }
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": plan_fields["taskBriefPath"],
                "executorReportPath": plan_fields["executorReportPath"],
                "reviewPackagePath": plan_fields["reviewPackagePath"],
            },
        }

        downstream_messages = (
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
                review_package=review_package,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
                review_package=review_package,
                reviewer_result=reviewer_result,
            ),
            team_router.make_qa_review_request_message(
                task_id,
                callback_block,
                plan_fields["scope"],
                plan_fields=plan_fields,
                reviewer_result=reviewer_result,
            ),
        )

        for message in downstream_messages:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("roleCommunicationMode: concise-protocol-plus-paths", message)
                self.assertIn("executorReportPath: docs/team-router/packages/ctr-compact-downstream.md", message)
                self.assertIn("reviewPackagePath: docs/team-router/packages/ctr-compact-downstream.md", message)
                self.assertIn("callbackContext: compact; see executorReportPath/reviewPackagePath", message)
                self.assertIn("callbackRawLocation: executorReportPath 或 reviewPackagePath", message)
                self.assertNotIn("执行者 callback 摘要", message)
                self.assertNotIn(long_payload, message)
                self.assertNotIn(long_review_payload, message)
                self.assertNotIn("以下是执行者 callback 原文：\nTEAM_ROUTER_CALLBACK", message)

    def test_reviewer_request_uses_path_first_handoff_without_raw_callback(self):
        task_id = "ctr-20260701-role-thread-handoff-compression"
        sensitive_evidence = "SHORT_EVIDENCE_SHOULD_STAY_IN_PACKAGE_FILE"
        package_path = "docs/team-router/packages/ctr-20260701-role-thread-handoff-compression.md"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "stopWhen": "reviewer prompt is path-first",
            "riskBoundary": "do not change parser/gate/direct-return/watcher/host/prompt outside compression",
            "executorPrompt": "Compress reviewer/verifier handoff prompts.",
            "taskBriefPath": package_path,
            "executorReportPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: prompt compression implemented\n"
            "evidence: %s\n"
            "risks: none\n"
            "next: reviewer"
        ) % (task_id, sensitive_evidence)
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": package_path,
                "executorReportPath": package_path,
                "reviewPackagePath": package_path,
            },
        }

        message = team_router.make_reviewer_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            plan_fields=plan_fields,
            review_package=review_package,
        )

        self.assertIn("reviewPackagePath: %s" % package_path, message)
        self.assertIn("callbackContext: compact; see executorReportPath/reviewPackagePath", message)
        self.assertIn("callbackRawLocation: executorReportPath 或 reviewPackagePath", message)
        self.assertNotIn(sensitive_evidence, message)
        self.assertNotIn("evidence: %s" % sensitive_evidence, message)
        self.assertLess(len(message), 2200)

    def test_package_path_manager_requests_reference_callback_and_review_results_by_path(self):
        task_id = "ctr-20260703-manager-request-compression"
        package_path = "docs/team-router/packages/ctr-20260703-manager-request-compression.md"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py docs/workbench.md %s" % package_path,
            "stopWhen": "manager role requests use package pointers instead of inline role results",
            "riskBoundary": "local package only; no commit/push/PR/merge/deploy/global sync",
            "taskBriefPath": package_path,
            "executorReportPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: RAW_CALLBACK_SUMMARY_SHOULD_NOT_INLINE\n"
            "evidence: RAW_CALLBACK_EVIDENCE_SHOULD_NOT_INLINE\n"
            "risks: none\n"
            "next: reviewer"
        ) % task_id
        reviewer_raw = (
            "TEAM_ROUTER_REVIEW taskId=%s\n"
            "result: pass\n"
            "summary: RAW_REVIEW_SUMMARY_SHOULD_NOT_INLINE\n"
            "findings: none\n"
            "requiredChanges: RAW_REVIEW_REQUIRED_CHANGES_SHOULD_NOT_INLINE\n"
            "evidenceChecked: RAW_REVIEW_EVIDENCE_SHOULD_NOT_INLINE\n"
            "risks: none\n"
            "next: verifier"
        ) % task_id
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": package_path,
                "executorReportPath": package_path,
                "reviewPackagePath": package_path,
            },
        }

        reviewer_message = team_router.make_reviewer_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            "thread-parent",
            role_thread_id="thread-reviewer",
            plan_fields=plan_fields,
            review_package=review_package,
        )
        verifier_message = team_router.make_verifier_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            "thread-parent",
            role_thread_id="thread-verifier",
            plan_fields=plan_fields,
            review_package=review_package,
            reviewer_result=reviewer_raw,
        )

        expected = (
            (
                reviewer_message,
                "TEAM_ROUTER_REVIEW_REQUEST taskId=%s" % task_id,
                "role: Reviewer",
                "sourceRoleThreadId: thread-reviewer",
                "replyMarker: TEAM_ROUTER_REVIEW taskId=%s" % task_id,
                "replyFields: result,summary,findings,requiredChanges,evidenceChecked,risks,next",
                "action: review reviewPackagePath; check executorCallback",
            ),
            (
                verifier_message,
                "TEAM_ROUTER_VERIFY taskId=%s" % task_id,
                "role: Verifier",
                "sourceRoleThreadId: thread-verifier",
                "replyMarker: TEAM_ROUTER_VERDICT taskId=%s" % task_id,
                "replyFields: result,summary,requiredChanges,evidenceChecked,risks,next",
                "action: verify reviewPackagePath; check executorCallback/reviewerResult",
            ),
        )
        for message, marker, role_line, source_role_line, reply_marker, reply_fields, action_line in expected:
            with self.subTest(marker=marker):
                self.assertIn(marker, message)
                self.assertIn("permission: local-package", message)
                self.assertIn("returnThreadId: thread-parent", message)
                self.assertIn("sourceThreadId: thread-parent", message)
                self.assertIn(role_line, message)
                self.assertIn(source_role_line, message)
                self.assertIn("scope: %s" % plan_fields["scope"], message)
                self.assertIn("reviewPackagePath: %s" % package_path, message)
                self.assertIn(action_line, message)
                self.assertIn("executorCallback: see reviewPackagePath", message)
                self.assertIn(reply_marker, message)
                self.assertIn(reply_fields, message)
                self.assertNotIn("TEAM_ROUTER_CALLBACK taskId=", message)
                self.assertNotIn("RAW_CALLBACK_SUMMARY_SHOULD_NOT_INLINE", message)
                self.assertNotIn("RAW_CALLBACK_EVIDENCE_SHOULD_NOT_INLINE", message)
        self.assertIn("reviewerResult: see reviewPackagePath", verifier_message)
        self.assertNotIn("TEAM_ROUTER_REVIEW taskId=%s\nresult: pass" % task_id, verifier_message)
        self.assertNotIn("RAW_REVIEW_SUMMARY_SHOULD_NOT_INLINE", verifier_message)
        self.assertNotIn("RAW_REVIEW_REQUIRED_CHANGES_SHOULD_NOT_INLINE", verifier_message)
        self.assertNotIn("RAW_REVIEW_EVIDENCE_SHOULD_NOT_INLINE", verifier_message)

    def test_reviewer_request_with_package_paths_uses_minimal_protocol_template(self):
        task_id = "ctr-20260702-short-role-template"
        package_path = "docs/team-router/packages/ctr-20260702-short-role-template.md"
        plan_fields = {
            "scope": "docs only",
            "taskBriefPath": package_path,
            "executorReportPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: docs updated\n"
            "evidence: see package\n"
            "risks: none\n"
            "next: reviewer"
        ) % task_id
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": package_path,
                "executorReportPath": package_path,
                "reviewPackagePath": package_path,
            },
        }

        message = team_router.make_reviewer_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            "thread-parent",
            role_thread_id="thread-reviewer",
            plan_fields=plan_fields,
            review_package=review_package,
        )

        self.assertIn("returnThreadId: thread-parent", message)
        self.assertIn(
            "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
            message,
        )
        self.assertIn(
            "Then print the same full TEAM_ROUTER_* block in this thread as fallback.",
            message,
        )
        self.assertIn("replyFields: result,summary,findings,requiredChanges,evidenceChecked,risks,next", message)
        self.assertIn("reviewPackagePath: %s" % package_path, message)
        self.assertNotIn("请在本线程按以下格式回复：", message)
        self.assertNotIn("evidenceChecked:", message)
        self.assertNotIn("directReturnAttempt:", message)
        self.assertLess(len(message), 1550)

    def test_compact_reviewer_reply_fields_match_parser_required_fields(self):
        task_id = "ctr-20260702-short-role-template"
        package_path = "docs/team-router/packages/ctr-20260702-short-role-template.md"
        plan_fields = {
            "scope": "docs only",
            "taskBriefPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: docs updated\n"
            "evidence: see package\n"
            "risks: none\n"
            "next: reviewer"
        ) % task_id

        message = team_router.make_reviewer_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            plan_fields=plan_fields,
        )

        self.assertIn("replyFields: result,summary,findings,requiredChanges,evidenceChecked,risks,next", message)
        parsed = team_router.parse_review(
            "TEAM_ROUTER_REVIEW taskId=%s\n"
            "result: pass\n"
            "summary: ok\n"
            "findings: none\n"
            "requiredChanges: none\n"
            "evidenceChecked: %s\n"
            "risks: none\n"
            "next: verifier" % (task_id, package_path),
            task_id,
        )
        self.assertEqual(parsed.fields["result"], "pass")

    def test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template(self):
        task_id = "ctr-20260702-short-role-inline-fallback"
        plan_fields = {"scope": "docs only"}
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: docs updated inline\n"
            "evidence: inline callback\n"
            "risks: none\n"
            "next: reviewer"
        ) % task_id
        review_package = {
            "gateClass": "PACKAGE",
            "status": "recorded",
            "inlineFallback": True,
            "paths": {},
        }

        message = team_router.make_reviewer_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            "thread-parent",
            role_thread_id="thread-reviewer",
            plan_fields=plan_fields,
            review_package=review_package,
        )

        self.assertIn("inlineFallback: true", message)
        self.assertIn("审查包元数据（仅作为证据）：", message)
        self.assertIn("packageEvidenceBoundary: evidence metadata only", message)
        self.assertIn(
            "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
            message,
        )
        self.assertIn(
            "Then print the same full TEAM_ROUTER_* block in this thread as fallback.",
            message,
        )
        self.assertIn("请在本线程按以下格式回复：", message)
        self.assertIn("evidenceChecked:", message)
        self.assertIn("directReturnAttempt:", message)
        self.assertNotIn("replyFields:", message)
        self.assertNotIn("defaultRules: use skill defaults; expand only for needs_rework/blocked", message)
        self.assertNotIn("packageEvidenceBoundary: path metadata only", message)

    def test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback(self):
        task_id = "ctr-20260701-role-thread-handoff-compression"
        sensitive_evidence = "SHORT_EVIDENCE_SHOULD_STAY_IN_PACKAGE_FILE"
        raw_review_detail = "RAW_REVIEW_DETAIL_SHOULD_STAY_IN_PACKAGE_FILE"
        package_path = "docs/team-router/packages/ctr-20260701-role-thread-handoff-compression.md"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "stopWhen": "verifier prompt is path-first",
            "riskBoundary": "do not change parser/gate/direct-return/watcher/host/prompt outside compression",
            "executorPrompt": "Compress reviewer/verifier handoff prompts.",
            "taskBriefPath": package_path,
            "executorReportPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: prompt compression implemented\n"
            "evidence: %s\n"
            "risks: none\n"
            "next: verifier"
        ) % (task_id, sensitive_evidence)
        reviewer_result = {
            "raw": (
                "TEAM_ROUTER_REVIEW taskId=%s\n"
                "result: pass\n"
                "summary: %s\n"
                "findings: none\n"
                "requiredChanges: none\n"
                "evidenceChecked: %s\n"
                "risks: none"
            ) % (task_id, raw_review_detail, package_path),
            "fields": {
                "result": "pass",
                "summary": "reviewer passed",
                "findings": "none",
                "requiredChanges": "none",
                "evidenceChecked": package_path,
                "risks": "none",
            },
        }
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": package_path,
                "executorReportPath": package_path,
                "reviewPackagePath": package_path,
            },
        }

        message = team_router.make_verifier_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            plan_fields=plan_fields,
            review_package=review_package,
            reviewer_result=reviewer_result,
        )

        self.assertIn("reviewPackagePath: %s" % package_path, message)
        self.assertIn("result: pass", message)
        self.assertIn("requiredChanges: none", message)
        self.assertIn("callbackRawLocation: executorReportPath 或 reviewPackagePath", message)
        self.assertNotIn(sensitive_evidence, message)
        self.assertNotIn(raw_review_detail, message)
        self.assertLess(len(message), 2600)

    def test_verifier_request_with_package_paths_uses_minimal_protocol_template(self):
        task_id = "ctr-20260702-short-role-template"
        package_path = "docs/team-router/packages/ctr-20260702-short-role-template.md"
        plan_fields = {
            "scope": "docs only",
            "taskBriefPath": package_path,
            "executorReportPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: docs updated\n"
            "evidence: see package\n"
            "risks: none\n"
            "next: verifier"
        ) % task_id
        reviewer_result = {
            "fields": {
                "result": "pass",
                "summary": "reviewer passed",
                "findings": "none",
                "requiredChanges": "none",
                "evidenceChecked": package_path,
                "risks": "none",
            },
        }
        review_package = {
            "gateClass": "PACKAGE",
            "paths": {
                "taskBriefPath": package_path,
                "executorReportPath": package_path,
                "reviewPackagePath": package_path,
            },
        }

        message = team_router.make_verifier_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            "thread-parent",
            role_thread_id="thread-verifier",
            plan_fields=plan_fields,
            review_package=review_package,
            reviewer_result=reviewer_result,
        )

        self.assertIn("returnThreadId: thread-parent", message)
        self.assertIn(
            "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
            message,
        )
        self.assertIn(
            "Then print the same full TEAM_ROUTER_* block in this thread as fallback.",
            message,
        )
        self.assertIn("replyFields: result,summary,requiredChanges,evidenceChecked,risks,next", message)
        self.assertIn("reviewPackagePath: %s" % package_path, message)
        self.assertNotIn("请在本线程按以下格式回复：", message)
        self.assertNotIn("验证者检查项：", message)
        self.assertNotIn("evidenceChecked:", message)
        self.assertNotIn("directReturnAttempt:", message)
        self.assertLess(len(message), 1700)

    def test_compact_verifier_reply_fields_match_parser_required_fields(self):
        task_id = "ctr-20260702-short-role-template"
        package_path = "docs/team-router/packages/ctr-20260702-short-role-template.md"
        plan_fields = {
            "scope": "docs only",
            "taskBriefPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: docs updated\n"
            "evidence: see package\n"
            "risks: none\n"
            "next: verifier"
        ) % task_id

        message = team_router.make_verifier_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            plan_fields=plan_fields,
        )

        self.assertIn("replyFields: result,summary,requiredChanges,evidenceChecked,risks,next", message)
        parsed = team_router.parse_verdict(
            "TEAM_ROUTER_VERDICT taskId=%s\n"
            "result: pass\n"
            "summary: ok\n"
            "requiredChanges: none\n"
            "evidenceChecked: %s\n"
            "risks: none\n"
            "next: commit" % (task_id, package_path),
            task_id,
        )
        self.assertEqual(parsed.fields["result"], "pass")

    def test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template(self):
        task_id = "ctr-20260702-short-role-inline-fallback"
        plan_fields = {"scope": "docs only"}
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: docs updated inline\n"
            "evidence: inline callback\n"
            "risks: none\n"
            "next: verifier"
        ) % task_id
        reviewer_result = {
            "fields": {
                "result": "pass",
                "summary": "reviewer passed",
                "findings": "none",
                "requiredChanges": "none",
                "evidenceChecked": "inline review",
                "risks": "none",
            },
        }
        review_package = {
            "gateClass": "PACKAGE",
            "status": "recorded",
            "inlineFallback": True,
            "paths": {},
        }

        message = team_router.make_verifier_request_message(
            task_id,
            callback_block,
            "local-package",
            plan_fields["scope"],
            "thread-parent",
            role_thread_id="thread-verifier",
            plan_fields=plan_fields,
            review_package=review_package,
            reviewer_result=reviewer_result,
        )

        self.assertIn("inlineFallback: true", message)
        self.assertIn("审查包元数据（仅作为证据）：", message)
        self.assertIn("packageEvidenceBoundary: evidence metadata only", message)
        self.assertIn(
            "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
            message,
        )
        self.assertIn(
            "Then print the same full TEAM_ROUTER_* block in this thread as fallback.",
            message,
        )
        self.assertIn("验证者检查项：", message)
        self.assertIn("请在本线程按以下格式回复：", message)
        self.assertIn("evidenceChecked:", message)
        self.assertIn("directReturnAttempt:", message)
        self.assertNotIn("replyFields:", message)
        self.assertNotIn("defaultRules: use skill defaults; expand only for needs_rework/blocked", message)
        self.assertNotIn("packageEvidenceBoundary: path metadata only", message)

    def test_role_request_prompts_without_return_thread_id_are_self_thread_marker_only(self):
        task_id = "ctr-20260702-direct-return-hard-contract"
        package_path = "docs/team-router/packages/ctr-20260702-direct-return-hard-contract.md"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py docs/workbench.md",
            "stopWhen": "prompt contract is explicit about fallback-only mode",
            "riskBoundary": "do not expand runtime broker/service behavior",
            "executorPrompt": "Harden direct-return prompt contract.",
            "taskBriefPath": package_path,
            "executorReportPath": package_path,
            "reviewPackagePath": package_path,
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: prompt contract updated\n"
            "evidence: tests\n"
            "risks: none\n"
            "next: reviewer"
        ) % task_id
        reviewer_result = {
            "fields": {
                "result": "pass",
                "summary": "reviewer passed",
                "findings": "none",
                "requiredChanges": "none",
                "evidenceChecked": package_path,
                "risks": "none",
            },
        }

        messages = (
            team_router.make_executor_dispatch_message(
                task_id,
                plan_fields,
                "local-package",
                {"messageId": "msg-direct-return-hard-contract", "sentAt": "2026-07-02T12:00:00+08:00"},
            ),
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
                reviewer_result=reviewer_result,
            ),
        )

        for message in messages:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("returnContract: self-thread-marker only", message)
                self.assertNotIn(
                    "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
                    message,
                )

    def test_role_request_templates_preserve_design_gates_but_compact_result_noise(self):
        task_id = "ctr-20260629-token-economy"
        plan_fields = {
            "scope": "src/team_router.py tests/test_team_router.py",
            "stopWhen": "token economy policy is explicit",
            "riskBoundary": "不改变 gate/state/direct-return 语义",
            "executorPrompt": "实现 Team Router token economy policy。",
            "taskBriefPath": "docs/team-router/packages/ctr-token-economy-brief.md",
            "executorReportPath": "docs/team-router/packages/ctr-token-economy-executor.md",
            "reviewPackagePath": "docs/team-router/packages/ctr-token-economy-review.md",
        }
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=%s\n"
            "status: done\n"
            "final: true\n"
            "summary: 已完成 token economy policy\n"
            "evidence: tests\n"
            "risks: none\n"
            "next: verifier"
        ) % task_id
        messages = (
            team_router.make_executor_dispatch_message(
                task_id,
                plan_fields,
                "local-package",
                {"messageId": "msg-dispatch", "sentAt": "2026-06-29T10:00:00+08:00"},
            ),
            team_router.make_reviewer_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
            ),
            team_router.make_verifier_request_message(
                task_id,
                callback_block,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
            ),
            team_router.make_architect_review_request_message(
                task_id,
                plan_fields["executorPrompt"],
                plan_fields["scope"],
                return_thread_id="thread-manager",
                role_thread_id="thread-architect",
                plan_fields=plan_fields,
            ),
            team_router.make_qa_review_request_message(
                task_id,
                callback_block,
                plan_fields["scope"],
                return_thread_id="thread-manager",
                role_thread_id="thread-qa",
                plan_fields=plan_fields,
            ),
        )

        for message in messages:
            with self.subTest(marker=message.splitlines()[0]):
                self.assertIn("roleCommunicationMode: concise-protocol-plus-paths", message)
                if message.startswith(("TEAM_ROUTER_REVIEW_REQUEST", "TEAM_ROUTER_VERIFY")):
                    self.assertIn("defaultRules:mdFirstPolicy;cavemanTransportPolicy;TEAM_ROUTER_* schema commands/errors requiredChanges", message)
                    self.assertIn("taskBriefPath:", message)
                    self.assertIn("reviewPackagePath:", message)
                    self.assertNotIn("designPlanningPolicy: 保留 brainstorming/spec/plan 的完整设计判断，不为了省 token 压缩设计 gate。", message)
                    self.assertNotIn("longContextPolicy: 不要复制完整 diff、完整日志、完整背景或完整角色推理", message)
                else:
                    self.assertIn("designPlanningPolicy: 保留 brainstorming/spec/plan 的完整设计判断，不为了省 token 压缩设计 gate。", message)
                    self.assertIn("passResultPolicy: pass/done 只回传 exactly one summary field", message)
                    self.assertIn("verificationOutputPolicy: pass evidence format: <reviewPackagePath>; tests: N OK; checks: M OK", message)
                    self.assertIn("fallbackReadPolicy: direct-return manager inbox 是默认；self-thread read_thread 只作为 bounded degraded fallback。", message)
                    self.assertIn("longContextPolicy: 不要复制完整 diff、完整日志、完整背景或完整角色推理", message)

class TestTeamRouterState(unittest.TestCase):
    def test_task_dispatch_lock_is_separate_and_fails_closed_when_held(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            with team_router_state.task_dispatch_lock(root, "project-1", "task-1", acquired_at="2026-07-15T10:00:00+08:00"):
                with self.assertRaisesRegex(team_router.StateStoreError, "task dispatch lock"):
                    with team_router_state.task_dispatch_lock(root, "project-1", "task-1", acquired_at="2026-07-15T10:00:01+08:00"):
                        pass
    def test_closeout_check_reports_read_only_status_and_unauthorized_gates(self):
        global_skill = Path("C:/tmp/team-router-closeout-missing-global-skill")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "team_router_closeout_check.py"),
                "--repo-root",
                str(ROOT),
                "--global-skill",
                str(global_skill),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "read-only")
        self.assertIn("gitStatusShort", report)
        self.assertIn("diffFiles", report)
        self.assertLess(report["skill"]["entrypointBytes"], report["skill"]["hardCapBytes"])
        self.assertEqual(report["skill"]["targetBytes"], 7200)
        self.assertIn(report["skillSync"]["status"], {"match", "mismatch", "blocked"})
        self.assertFalse(report["authorization"]["commit"])
        self.assertFalse(report["authorization"]["pullRequest"])
        self.assertFalse(report["authorization"]["merge"])
        self.assertFalse(report["authorization"]["deploy"])
        self.assertFalse(report["authorization"]["push"])
        self.assertFalse(report["authorization"]["globalSync"])
        self.assertIn("does not stage, commit, push, or sync", report["readOnlyGuarantee"])

    def test_truth_check_reports_stale_claims_and_is_read_only(self):
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            stale_file = tmp_path / "stale-workbench.md"
            stale_file.write_text(
                "\n".join(
                    [
                        "# stale",
                        "## Current Task",
                        "State: active local package implementation for `ctr-20260628-team-router-optimization-1-6`",
                        "Latest `git status -s --untracked-files=all` reports:",
                        "- `M docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md`",
                        "- `M docs/workbench.md`",
                        "- `M skills/codex-team-router/SKILL.md`",
                        "- `M src/team_router.py`",
                        "- `M tests/test_team_router.py`",
                        "`skillSync.status: mismatch`",
                    ]
                ),
                encoding="utf-8",
            )
            before = {
                str(path.relative_to(global_skill)): path.read_bytes()
                for path in global_skill.rglob("*")
                if path.is_file()
            }

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_truth_check.py"),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--scan-file",
                    str(stale_file),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["mode"], "read-only")
            self.assertIn("gitStatusBranch", report)
            self.assertIn("gitStatusShort", report)
            self.assertIn("diffFiles", report)
            self.assertEqual(report["skillSync"]["status"], "match")
            self.assertFalse(report["authorization"]["commit"])
            self.assertFalse(report["authorization"]["push"])
            self.assertFalse(report["authorization"]["pullRequest"])
            self.assertFalse(report["authorization"]["merge"])
            self.assertFalse(report["authorization"]["deploy"])
            self.assertFalse(report["authorization"]["globalSync"])
            self.assertIn("does not stage, commit, push, PR, merge, deploy, or sync", report["readOnlyGuarantee"])
            claim_reasons = "\n".join(claim["reason"] for claim in report["staleClaims"])
            self.assertIn("old optimization package is not the current task", claim_reasons)
            self.assertIn("skillSync.status mismatch", claim_reasons)
            after = {
                str(path.relative_to(global_skill)): path.read_bytes()
                for path in global_skill.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_truth_check_detects_stale_current_state_when_clean_synced(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = {"skillSync": {"status": "match"}, "gitStatusShort": [], "diffFiles": []}
        text = "\n".join(
            [
                "# Workbench",
                "## Current Task",
                "- State: active local package implementation for `ctr-stale-active`.",
                "- Current next gate: reviewer/verifier focused acceptance.",
                "## Current Diff Surface",
                "- `M docs/workbench.md`",
                "## Historical Records",
                "- Previous stale package is historical only.",
            ]
        )

        claims = module.find_stale_state_claims(report, {"docs/workbench.md": text})

        reasons = "\n".join(claim["reason"] for claim in claims)
        self.assertIn("current-state claims active package while live git/skill truth is clean/synced", reasons)
        self.assertIn("current-state claims pending reviewer/verifier gate while live git/skill truth is clean/synced", reasons)
        self.assertIn("current-state claims dirty diff surface while live git/skill truth is clean/synced", reasons)

    def test_truth_check_detects_clean_claim_when_live_git_is_dirty(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = {"skillSync": {"status": "match"}, "gitStatusShort": [" M docs/workbench.md"], "diffFiles": ["docs/workbench.md"]}
        text = "\n".join(
            [
                "# Workbench",
                "## Current Task",
                "- State: clean baseline after closeout.",
                "- Fresh command truth: `git status -s --untracked-files=all` -> clean; `git diff --name-only` -> none.",
                "## Current Diff Surface",
                "Current truth is command-derived.",
            ]
        )

        claims = module.find_stale_state_claims(report, {"docs/workbench.md": text})

        reasons = "\n".join(claim["reason"] for claim in claims)
        self.assertIn("current-state claims clean diff surface while live git truth is dirty", reasons)

    def test_truth_check_allows_completed_evidence_mentions_reviewer_verifier(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = {"skillSync": {"status": "match"}, "gitStatusShort": [], "diffFiles": []}
        text = "\n".join(
            [
                "# Workbench",
                "## Current Task",
                "- State: no active repo-local package; previous package has been committed, pushed, and globally synced.",
                "- Completed package starting evidence: manager language was too quick to restart a still-active reviewer/verifier role.",
                "- Current next gate: none; no action required.",
                "## Current Diff Surface",
                "Current truth is clean.",
            ]
        )

        claims = module.find_stale_state_claims(report, {"docs/workbench.md": text})

        self.assertEqual(claims, [])

    def test_truth_check_flags_current_gate_even_when_it_mentions_historical_records(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = {"skillSync": {"status": "match"}, "gitStatusShort": [], "diffFiles": []}
        text = "\n".join(
            [
                "# Workbench",
                "## Current Task",
                "- State: clean/synced; no active package.",
                "- Current next gate: reviewer/verifier review of historical package records.",
                "## Current Diff Surface",
                "Current truth is clean.",
            ]
        )

        claims = module.find_stale_state_claims(report, {"docs/workbench.md": text})

        reasons = "\n".join(claim["reason"] for claim in claims)
        self.assertIn("current-state claims pending reviewer/verifier gate while live git/skill truth is clean/synced", reasons)

    def test_truth_check_does_not_flag_clean_synced_neutral_current_sections(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = {"skillSync": {"status": "match"}, "gitStatusShort": [], "diffFiles": []}
        text = "\n".join(
            [
                "# Workbench",
                "## Current Task",
                "- State: clean/synced; no active package.",
                "- Current next gate: none; no action required.",
                "## Current Diff Surface",
                "Current truth is clean.",
                "No current diff entries are present.",
                "## Review And Verification Gate",
                "Current gate: none; no action required.",
            ]
        )

        claims = module.find_stale_state_claims(report, {"docs/workbench.md": text})

        self.assertEqual(claims, [])

    def test_truth_check_does_not_flag_historical_package_records_as_current(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = {"skillSync": {"status": "match"}, "gitStatusShort": [], "diffFiles": []}
        text = "\n".join(
            [
                "# Package Archive",
                "## Historical Records",
                "- State: active local package implementation for `ctr-old`.",
                "- Current next gate: reviewer/verifier focused acceptance.",
                "- `M docs/workbench.md`",
                "## Integration Boundary",
                "- historical only, not current truth.",
            ]
        )

        claims = module.find_stale_state_claims(report, {"docs/team-router/packages/old.md": text})

        self.assertEqual(claims, [])

    def test_truth_check_detects_workbench_current_package_behind_latest_package(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_truth_check_under_test",
            ROOT / "scripts" / "team_router_truth_check.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = {
            "gitStatusShort": [],
            "diffFiles": [],
            "skillSync": {"status": "match"},
        }
        workbench = "\n".join((
            "# Team Router Workbench",
            "## Current Task",
            "- State: closeout recorded for `ctr-20260629-workbench-current-truth-doctor-ux`; review and verification gates accepted.",
            "- Current next gate: after this local closeout commit, open `module extraction phase 1: policy/protocol split` only on explicit dispatch.",
            "## Current Diff Surface",
            "Current truth is command-derived.",
        ))
        module_map = "\n".join((
            "# Team Router Module Map",
            "Phase 1 completed the safe opening split: protocol parsing first, then pure gate policy.",
            "The remaining safe extraction order is: watcher runtime -> status/closeout.",
        ))
        latest_package = "# Team Router Handoff Package: ctr-20260630-role-reuse-path-handoff-governance\n"

        claims = module.find_stale_state_claims(
            report,
            {
                str(ROOT / "docs" / "workbench.md"): workbench,
                str(ROOT / "docs" / "team-router" / "module-map.md"): module_map,
                str(ROOT / "docs" / "team-router" / "packages" / "ctr-20260630-role-reuse-path-handoff-governance.md"): latest_package,
            },
        )

        claim_reasons = "\n".join(claim["reason"] for claim in claims)
        self.assertIn("workbench current task is behind latest package record", claim_reasons)
        self.assertIn("workbench next gate points at completed module extraction phase", claim_reasons)

    def test_router_doctor_dirty_next_action_requires_reviewer_then_verifier(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        next_action = module._next_action("dirty", {"skillSync": {"status": "match"}})

        self.assertIn("reviewer pass", next_action)
        self.assertIn("verifier pass", next_action)
        self.assertLess(next_action.index("reviewer pass"), next_action.index("verifier pass"))

    def test_router_doctor_stale_next_action_names_truth_check_and_doctor(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        next_action = module._next_action("stale", {"skillSync": {"status": "match"}})

        self.assertIn("truth_check/doctor", next_action)
        self.assertIn("current-state text", next_action)
        self.assertIn("before claiming current truth", next_action)

    def test_router_doctor_classifies_role_thread_readiness_states(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        cases = [
            (
                {"role": "executor"},
                "missing",
                "no role thread id recorded",
            ),
            (
                {"role": "executor", "threadId": "thread-exec", "visible": False},
                "created_not_visible",
                "thread id exists but is not visible/readable",
            ),
            (
                {"role": "reviewer", "threadId": "thread-review", "readError": "not found"},
                "created_not_visible",
                "read_thread failed",
            ),
            (
                {"role": "executor", "threadId": "thread-exec", "visible": True, "turnStatus": "inProgress"},
                "active_wait",
                "role thread has an active turn",
            ),
            (
                {
                    "role": "executor",
                    "threadId": "thread-exec",
                    "visible": True,
                    "messages": [{"text": "TEAM_ROUTER_CALLBACK taskId=ctr-role-status status=done"}],
                },
                "protocol_returned",
                "expected protocol marker found",
            ),
            (
                {"role": "verifier", "threadId": "thread-verify", "visible": True, "messages": ["still working"]},
                "visible_waiting",
                "visible but no expected protocol marker",
            ),
        ]

        for snapshot, expected_status, expected_summary in cases:
            with self.subTest(snapshot=snapshot):
                result = module.classify_role_thread_status(snapshot)
                self.assertEqual(result["status"], expected_status)
                self.assertIn(expected_summary, result["summary"])

        snapshot_result = module.classify_role_thread_status_snapshot(
            {
                "roles": [
                    {
                        "role": "manager",
                        "threadId": "thread-manager",
                        "visible": True,
                        "messages": [{"text": "TEAM_ROUTER_PLAN taskId=ctr-role-status status=planned"}],
                    }
                ],
                "expectedMarkers": {"manager": "TEAM_ROUTER_PLAN"},
            }
        )
        self.assertEqual(snapshot_result["roles"][0]["expectedMarker"], "TEAM_ROUTER_PLAN")
        self.assertEqual(snapshot_result["roles"][0]["status"], "protocol_returned")

    def test_router_doctor_includes_role_thread_status_snapshot(self):
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            role_snapshot = tmp_path / "role-status.json"
            role_snapshot.write_text(
                json.dumps(
                    {
                        "roles": [
                            {"role": "executor", "threadId": "thread-exec", "visible": True, "turnStatus": "inProgress"},
                            {
                                "role": "reviewer",
                                "threadId": "thread-review",
                                "visible": True,
                                "messages": [{"text": "TEAM_ROUTER_REVIEW taskId=ctr-role-status status=pass"}],
                            },
                            {"role": "verifier"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_doctor.py"),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--role-status-json",
                    str(role_snapshot),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            statuses = {role["role"]: role["status"] for role in report["roleThreadStatus"]["roles"]}
            self.assertEqual(statuses["executor"], "active_wait")
            self.assertEqual(statuses["reviewer"], "protocol_returned")
            self.assertEqual(statuses["verifier"], "missing")
            self.assertEqual(report["roleThreadStatus"]["mode"], "read-only")
            self.assertIn("hostReadiness", report)

    def test_router_doctor_includes_manager_polling_status_decision_from_snapshot(self):
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            role_snapshot = tmp_path / "role-status.json"
            role_snapshot.write_text(
                json.dumps(
                    {
                        "roles": [],
                        "managerPolling": {
                            "ledger": {
                                "taskId": "ctr-polling-ux",
                                "status": "awaiting_callback",
                                "roleThreadStatus": "inProgress",
                                "readDiscipline": {
                                    "gateClass": "STRICT",
                                    "lastReadAt": "2026-07-02T10:00:30+08:00",
                                    "lastReportedRoleStatus": "in_progress",
                                    "nextAllowedReadAt": "2026-07-02T10:05:30+08:00",
                                    "minimumIntervalSeconds": 300,
                                    "directReturnExpected": True,
                                },
                            },
                            "wakeup": {
                                "role": "reviewer",
                                "threadId": "thread-reviewer",
                                "expectedMarker": "TEAM_ROUTER_REVIEW taskId=ctr-polling-ux",
                                "searchAnchor": {"sentAt": "2026-07-02T10:00:00+08:00"},
                                "reason": "awaiting reviewer",
                            },
                            "observedAt": "2026-07-02T10:04:00+08:00",
                            "observedStatus": "inProgress",
                            "readReason": "scheduled watcher heartbeat",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_doctor.py"),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--role-status-json",
                    str(role_snapshot),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            polling = report["managerPollingStatus"]
            self.assertEqual(polling["mode"], "read-only")
            self.assertEqual(polling["status"], "read_suppressed")
            self.assertFalse(polling["shouldRead"])
            self.assertFalse(polling["shouldReport"])
            self.assertEqual(polling["nextAllowedReadAt"], "2026-07-02T10:05:30+08:00")
            self.assertIn("without repeated status narration", polling["summary"])
            self.assertIn("managerPolling=read_suppressed", report["summary"])
            self.assertIn("no thread tools", polling["boundary"])

    def test_router_doctor_fixture_reports_manager_polling_status(self):
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            fixture = ROOT / "tests" / "fixtures" / "team_router" / "manager_polling_status_snapshot.json"
            expected = json.loads((ROOT / "tests" / "fixtures" / "team_router" / "manager_polling_status_expected_subset.json").read_text(encoding="utf-8"))

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_doctor.py"),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--role-status-json",
                    str(fixture),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            polling = report["managerPollingStatus"]
            self.assertEqual(polling["mode"], "read-only")
            self.assertEqual(polling["status"], "read_suppressed")
            self.assertFalse(polling["shouldRead"])
            self.assertFalse(polling["shouldReport"])
            self.assertEqual(polling["nextAllowedReadAt"], "2026-07-02T10:05:30+08:00")
            self.assertIn("managerPolling=read_suppressed", report["summary"])
            for key, value in expected["managerPollingStatus"].items():
                self.assertEqual(polling[key], value)
            for needle in expected["summaryContains"]:
                self.assertIn(needle, report["summary"])

    def test_host_adapter_readiness_check_accepts_callable_snapshot_without_tool_calls(self):
        with workspace_temp_dir() as tmp:
            snapshot = Path(tmp) / "host-adapter-ready.json"
            callable_tools = {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
            }
            snapshot.write_text(json.dumps({
                "source": "unit-test-host-adapter",
                "adapterCallable": True,
                "codexAppThreadToolsExposed": True,
                "callableTools": callable_tools,
                "parentThreadId": "parent-thread",
                "heartbeatSchedulerCallable": True,
                "runtimeProbe": {"status": "ready", "missing": []},
            }), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_host_adapter_readiness_check.py"),
                    "--adapter-snapshot-json",
                    str(snapshot),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["orchestrationStatus"], "adapter_smoke_ready")
            self.assertTrue(report["adapterInjection"]["pythonCallableAdapter"])
            self.assertEqual(report["adapterInjection"]["threadToolCallsExecuted"], 0)
            self.assertTrue(all(report["readiness"]["capabilities"][tool] for tool in callable_tools))
            host_snapshot = report["hostReadinessSnapshot"]
            self.assertTrue(host_snapshot["adapterCallable"])
            self.assertEqual(host_snapshot["parentThreadId"], "parent-thread")
            self.assertTrue(host_snapshot["heartbeatSchedulerCallable"])

    def test_host_adapter_readiness_check_blocks_model_side_descriptors(self):
        with workspace_temp_dir() as tmp:
            snapshot = Path(tmp) / "host-adapter-descriptors.json"
            snapshot.write_text(json.dumps({
                "source": "unit-test-model-side-descriptors",
                "adapterCallable": False,
                "codexAppThreadToolsExposed": True,
                "callableTools": {
                    "list_projects": False,
                    "create_thread": False,
                    "list_threads": False,
                    "read_thread": False,
                    "send_message_to_thread": False,
                    "set_thread_title": False,
                },
                "toolDescriptors": {
                    "read_thread": {"name": "read_thread"},
                    "send_message_to_thread": {"name": "send_message_to_thread"},
                },
                "parentThreadId": "parent-thread",
                "heartbeatSchedulerCallable": False,
                "runtimeProbe": {"status": "ready", "missing": []},
            }), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_host_adapter_readiness_check.py"),
                    "--adapter-snapshot-json",
                    str(snapshot),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["orchestrationStatus"], "host_contract_blocked")
            self.assertFalse(report["adapterInjection"]["pythonCallableAdapter"])
            self.assertEqual(report["adapterInjection"]["threadToolCallsExecuted"], 0)
            self.assertIn("callable adapter", report["doctorHostReadiness"]["missing"])
            self.assertIn("callable heartbeat scheduler", report["doctorHostReadiness"]["missing"])
            self.assertIn("model-side Codex app tool exposure is not a Python callable adapter", report["doctorHostReadiness"]["boundary"])

    def test_host_adapter_readiness_fixture_reports_ready_without_tool_calls(self):
        fixture = ROOT / "tests" / "fixtures" / "team_router" / "host_adapter_callable_ready_snapshot.json"

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "team_router_host_adapter_readiness_check.py"),
                "--adapter-snapshot-json",
                str(fixture),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["orchestrationStatus"], "adapter_smoke_ready")
        self.assertEqual(report["adapterInjection"]["threadToolCallsExecuted"], 0)
        self.assertEqual(report["adapterInjection"]["heartbeatSchedulesExecuted"], 0)
        self.assertIn("no thread tools are called", report["boundary"])

    def test_router_doctor_classifies_host_readiness_snapshot(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        blocked = module.classify_host_readiness_snapshot(
            {
                "codexAppThreadToolsExposed": True,
                "adapterCallable": False,
                "callableTools": {tool: False for tool in module.REQUIRED_THREAD_TOOLS},
                "parentThreadId": "",
                "heartbeatSchedulerCallable": False,
            }
        )

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["orchestrationStatus"], "host_contract_blocked")
        self.assertTrue(blocked["evidence"]["threadToolSurfaceExposed"])
        self.assertIn("callable adapter", blocked["missing"])
        self.assertIn("callable set_thread_title", blocked["missing"])
        self.assertIn("parent_thread_id", blocked["missing"])
        self.assertIn("callable heartbeat scheduler", blocked["missing"])
        self.assertIn("model-side Codex app tool exposure is not a Python callable adapter", blocked["boundary"])

        ready = module.classify_host_readiness_snapshot(
            {
                "adapterCallable": True,
                "callableTools": list(module.REQUIRED_THREAD_TOOLS),
                "parentThreadId": "019f0ebf-9047-71d2-86b9-efbf7bc4612d",
                "heartbeatScheduler": {"scheduleCallable": True},
                "runtimeProbe": {"status": "ready", "missing": []},
            }
        )

        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["orchestrationStatus"], "adapter_smoke_ready")
        self.assertEqual(ready["missing"], [])
        self.assertTrue(ready["capabilities"]["set_thread_title"])
        self.assertTrue(ready["capabilities"]["heartbeat_scheduler"])

    def test_router_doctor_requires_runtime_probe_for_adapter_smoke_ready(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        base_snapshot = {
            "adapterCallable": True,
            "callableTools": list(module.REQUIRED_THREAD_TOOLS),
            "parentThreadId": "parent-thread",
            "heartbeatSchedulerCallable": True,
        }

        blocked = module.classify_host_readiness_snapshot(base_snapshot)

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["orchestrationStatus"], "host_contract_blocked")
        self.assertIn("runtime readiness probe", blocked["missing"])
        self.assertFalse(blocked["evidence"]["runtimeProbeReady"])

        ready_snapshot = dict(base_snapshot)
        ready_snapshot["runtimeProbe"] = {"status": "ready", "missing": []}

        ready = module.classify_host_readiness_snapshot(ready_snapshot)

        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["orchestrationStatus"], "adapter_smoke_ready")
        self.assertEqual(ready["missing"], [])
        self.assertTrue(ready["evidence"]["runtimeProbeReady"])

    def test_router_doctor_includes_host_readiness_snapshot(self):
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            host_snapshot = tmp_path / "host-readiness.json"
            host_snapshot.write_text(
                json.dumps(
                    {
                        "codexAppThreadTools": [
                            "list_projects",
                            "create_thread",
                            "list_threads",
                            "read_thread",
                            "send_message_to_thread",
                            "set_thread_title",
                        ],
                        "adapterCallable": False,
                        "callableTools": {
                            "list_projects": False,
                            "create_thread": False,
                            "list_threads": False,
                            "read_thread": False,
                            "send_message_to_thread": False,
                            "set_thread_title": False,
                        },
                        "parentThreadId": "019f0ebf-9047-71d2-86b9-efbf7bc4612d",
                        "heartbeatSchedulerCallable": False,
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_doctor.py"),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--host-readiness-json",
                    str(host_snapshot),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["orchestrationStatus"], "host_contract_blocked")
            self.assertEqual(report["hostReadiness"]["status"], "blocked")
            self.assertTrue(report["hostReadiness"]["evidence"]["threadToolSurfaceExposed"])
            self.assertTrue(report["hostReadiness"]["evidence"]["parentThreadIdPresent"])
            self.assertIn("callable adapter", report["hostReadiness"]["missing"])
            self.assertIn("callable heartbeat scheduler", report["hostReadiness"]["missing"])
            self.assertIn("hostReadiness=blocked", report["summary"])
            self.assertIn("nextAction", report)
            self.assertNotIn("created role thread", report["summary"])
    def test_router_doctor_can_inject_host_readiness_from_broker(self):
        script = ROOT / "scripts" / "team_router_doctor.py"
        readiness = {
            "status": "ready",
            "brokerReady": True,
            "toolSmokeReady": True,
            "schedulerReady": True,
            "parentThreadId": "thread-parent",
            "projectId": "project-1",
            "capabilities": {
                "list_projects": True,
                "create_thread": True,
                "list_threads": True,
                "read_thread": True,
                "send_message_to_thread": True,
                "set_thread_title": True,
                "heartbeat_scheduler": True,
            },
            "runtimeProbe": {"status": "ready", "missing": []},
            "missing": [],
        }
        with workspace_temp_dir() as tmp, fake_broker({"/readiness": (200, readiness)}) as (base_url, _calls):
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(script),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--broker-url",
                    base_url,
                    "--session-token",
                    "session-123",
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["hostReadiness"]["status"], "ready")
        self.assertEqual(report["orchestrationStatus"], "adapter_smoke_ready")
        self.assertTrue(report["hostReadiness"]["capabilities"]["set_thread_title"])

    def test_router_doctor_rejects_host_readiness_file_and_broker_args_together(self):
        script = ROOT / "scripts" / "team_router_doctor.py"
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            host_snapshot = tmp_path / "host-readiness.json"
            host_snapshot.write_text("{}", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(script),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--host-readiness-json",
                    str(host_snapshot),
                    "--broker-url",
                    "http://127.0.0.1:1",
                    "--session-token",
                    "session-123",
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("choose either --host-readiness-json or --broker-url", result.stderr)

    def test_router_doctor_reports_plain_status_without_dispatch(self):
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            global_skill = tmp_path / "global" / "codex-team-router"
            shutil.copytree(ROOT / "skills" / "codex-team-router", global_skill)
            stale_file = tmp_path / "stale-workbench.md"
            stale_file.write_text(
                "State: active local package implementation for `ctr-20260628-team-router-optimization-1-6`\n"
                "`skillSync.status: mismatch`\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts" / "team_router_doctor.py"),
                    "--repo-root",
                    str(ROOT),
                    "--global-skill",
                    str(global_skill),
                    "--scan-file",
                    str(stale_file),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["mode"], "read-only")
            self.assertIn(report["truthStatus"], {"dirty_or_stale", "dirty", "stale"})
            self.assertIn(report["orchestrationStatus"], {"manual_only", "tool_error", "unknown"})
            self.assertIn("currentMode", report["summary"])
            self.assertIn("nextAction", report["summary"])
            self.assertIn("nextAction", report)
            self.assertIn("unauthorized", report["summary"])
            self.assertNotIn("created role thread", report["summary"])
            self.assertFalse(report["authorization"]["commit"])
            self.assertFalse(report["authorization"]["push"])
    def test_callback_unreachable_is_recoverable_not_terminal(self):
        self.assertNotIn("callback_unreachable", team_router.TERMINAL_STATUSES)
        self.assertEqual(
            team_router.manual_recovery_target("callback_unreachable"),
            "verifying",
        )
        self.assertEqual(
            team_router.manual_recovery_target("plan_unreachable"),
            "planned",
        )
        self.assertEqual(
            team_router.manual_recovery_target("review_unreachable"),
            "reviewing",
        )

    def test_rework_limit_blocks_without_incrementing(self):
        status, count = team_router.next_rework_dispatch(rework_count=3, max_rework=3)
        self.assertEqual(status, "blocked")
        self.assertEqual(count, 3)
        status, count = team_router.next_rework_dispatch(rework_count=2, max_rework=3)
        self.assertEqual(status, "dispatched")
        self.assertEqual(count, 3)


    def test_review_parser_accepts_adversarial_review_marker(self):
        text = """TEAM_ROUTER_REVIEW taskId=ctr-1
result: needs_rework
summary: risky
findings: missing direct-return fallback
requiredChanges: add reviewer gate tests
evidenceChecked: protocol snapshot
risks: none
"""

        msg = team_router.parse_review(text, "ctr-1")

        self.assertEqual(msg.fields["result"], "needs_rework")
        self.assertEqual(msg.fields["findings"], "missing direct-return fallback")
    def test_reviewer_gate_required_for_runtime_gate_reviewer_gate_and_team_router_self_changes(self):
        cases = (
            ("Team Router reviewer runtime gate rework", {"scope": "runtime gate"}),
            ("repair reviewer gate trigger policy", {"riskBoundary": "reviewer gate must run"}),
            ("Team Router self changes", {"executorPrompt": "review routing policy"}),
            ("Team Router manager orchestration policy update", {"scope": "docs"}),
            ("Team Router permission boundary change", {"scope": "src"}),
            ("ordinary task", {"requiresReviewer": "true"}),
            ("ordinary task", {"riskClass": "high"}),
        )
        for objective, fields in cases:
            with self.subTest(objective=objective, fields=fields):
                ledger = {"objective": objective, "plan": {"fields": fields}}
                self.assertTrue(team_router.reviewer_gate_required_for_ledger(ledger))

    def test_reviewer_gate_required_does_not_trigger_on_team_router_filename_only(self):
        ledger = {
            "objective": "low-risk docs-only single-file cleanup",
            "plan": {
                "fields": {
                    "scope": "src/team_router.py",
                    "riskBoundary": "low-risk docs-only single-file fix",
                    "executorPrompt": "adjust a typo in src/team_router.py",
                    "notes": "typo-only cleanup",
                }
            },
        }
        self.assertFalse(team_router.reviewer_gate_required_for_ledger(ledger))

    def test_classify_team_router_gate_fast_docs_rework(self):
        ledger = {
            "objective": "restore README BOM and keep polling wording",
            "plan": {"fields": {
                "scope": "README.md",
                "riskBoundary": "docs-only encoding rework",
                "executorPrompt": "restore UTF-8 BOM only",
                "notes": "no runtime change",
            }},
        }

        self.assertEqual(team_router.classify_team_router_gate(ledger), "FAST")
        self.assertFalse(team_router.gate_class_requires_reviewer("FAST"))

    def test_classify_team_router_gate_strict_for_router_policy(self):
        ledger = {
            "objective": "Team Router bounded polling runtime policy",
            "plan": {"fields": {
                "scope": "src/team_router.py tests/test_team_router.py",
                "riskBoundary": "manager orchestration policy",
                "executorPrompt": "change role protocol and polling rules",
                "notes": "process rules",
            }},
        }

        self.assertEqual(team_router.classify_team_router_gate(ledger), "STRICT")
        self.assertTrue(team_router.gate_class_requires_reviewer("STRICT"))

    def test_classify_team_router_gate_normal_fallback_for_plain_task(self):
        ledger = {
            "objective": "update local helper behavior",
            "plan": {"fields": {
                "scope": "src/local_helper.py",
                "riskBoundary": "ordinary implementation task",
                "executorPrompt": "adjust helper behavior",
                "notes": "single ordinary task without review-routing markers",
            }},
        }

        self.assertEqual(team_router.classify_team_router_gate(ledger), "NORMAL")
        self.assertFalse(team_router.gate_class_requires_reviewer("NORMAL"))

    def test_classify_team_router_gate_strict_for_local_package_permission(self):
        ledger = {
            "objective": "update local helper behavior",
            "plan": {"fields": {
                "acknowledgedPermission": "local-package",
                "scope": "src/local_helper.py",
                "riskBoundary": "authorized local-package workspace writes only",
                "executorPrompt": "adjust helper behavior",
                "notes": "single ordinary task without review-routing markers",
            }},
        }

        self.assertEqual(team_router.classify_team_router_gate(ledger), "STRICT")
        self.assertTrue(team_router.reviewer_gate_required_for_ledger(ledger))

    def test_classify_team_router_gate_package_for_deliberate_local_package_signal(self):
        ledger = {
            "objective": "update local helper behavior",
            "plan": {"fields": {
                "acknowledgedPermission": "local-package",
                "scope": "src/local_helper.py",
                "riskBoundary": "package gate for same task family discipline hardening",
                "executorPrompt": "bundle same task family changes",
                "notes": "package",
            }},
        }

        self.assertEqual(team_router.classify_team_router_gate(ledger), "PACKAGE")
        self.assertTrue(team_router.gate_class_requires_reviewer("PACKAGE"))

    def test_classify_team_router_gate_package_for_compounded_discipline(self):
        ledger = {
            "objective": "manager-discipline hardening package",
            "plan": {"fields": {
                "scope": "Team Router discipline package",
                "riskBoundary": "role title plus polling plus manager overreach",
                "executorPrompt": "bundle related process hardening",
                "notes": "package same task family",
            }},
        }

        self.assertEqual(team_router.classify_team_router_gate(ledger), "PACKAGE")
        self.assertTrue(team_router.gate_class_requires_reviewer("PACKAGE"))

    def test_explain_team_router_gate_names_classification_reasons(self):
        cases = (
            (
                {
                    "objective": "ordinary helper",
                    "plan": {"fields": {"acknowledgedPermission": "local-package", "scope": "src"}},
                },
                "STRICT",
                "local-package permission requires reviewer gate",
            ),
            (
                {
                    "objective": "same task family discipline hardening",
                    "plan": {"fields": {"riskBoundary": "package gate", "notes": "package"}},
                },
                "PACKAGE",
                "package term",
            ),
            (
                {
                    "objective": "Team Router manager orchestration policy",
                    "plan": {"fields": {"scope": "role protocol and safety boundary"}},
                },
                "STRICT",
                "reviewer-required term",
            ),
            (
                {
                    "objective": "restore README BOM",
                    "plan": {"fields": {"scope": "README.md", "riskBoundary": "docs-only single phrase"}},
                },
                "FAST",
                "fast docs term",
            ),
            (
                {
                    "objective": "update ordinary helper",
                    "plan": {"fields": {"scope": "src/local_helper.py", "riskBoundary": "ordinary"}},
                },
                "NORMAL",
                "normal fallback",
            ),
        )
        for ledger, expected_gate, expected_reason in cases:
            with self.subTest(expected_gate=expected_gate, expected_reason=expected_reason):
                explanation = team_router.explain_team_router_gate(ledger)
                self.assertEqual(explanation["gateClass"], expected_gate)
                self.assertEqual(team_router.classify_team_router_gate(ledger), expected_gate)
                self.assertIn(expected_reason, explanation["reasons"])

    def test_live_orchestration_readiness_reports_missing_host_contracts(self):
        scheduler = FakeHeartbeatScheduler()
        missing_adapter = team_router.assess_live_orchestration_readiness(
            thread_adapter=None,
            parent_thread_id="parent-thread",
            heartbeat_scheduler=scheduler,
        )
        self.assertEqual(missing_adapter["status"], "blocked")
        self.assertIn("callable adapter", " ".join(missing_adapter["missing"]))

        missing_parent = team_router.assess_live_orchestration_readiness(
            thread_adapter=FullThreadAdapter(),
            parent_thread_id=None,
            heartbeat_scheduler=scheduler,
        )
        self.assertEqual(missing_parent["status"], "blocked")
        self.assertIn("parent_thread_id", missing_parent["missing"])

        class AdapterWithoutTitle:
            def create_thread(self, **kwargs):
                return {}

            def send_message_to_thread(self, **kwargs):
                return {}

            def read_thread(self, **kwargs):
                return {}

        adapter_without_title = AdapterWithoutTitle()
        missing_title = team_router.assess_live_orchestration_readiness(
            thread_adapter=adapter_without_title,
            parent_thread_id="parent-thread",
            heartbeat_scheduler=scheduler,
            required_tools=("create_thread", "send_message_to_thread", "read_thread", "set_thread_title"),
        )
        self.assertEqual(missing_title["status"], "blocked")
        self.assertIn("callable set_thread_title", missing_title["missing"])

        missing_scheduler = team_router.assess_live_orchestration_readiness(
            thread_adapter=FullThreadAdapter(),
            parent_thread_id="parent-thread",
            heartbeat_scheduler=True,
        )
        self.assertEqual(missing_scheduler["status"], "blocked")
        self.assertIn("callable heartbeat scheduler", missing_scheduler["missing"])

        ready = team_router.assess_live_orchestration_readiness(
            thread_adapter=FullThreadAdapter(),
            parent_thread_id="parent-thread",
            heartbeat_scheduler=scheduler,
        )
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["missing"], [])
    def test_role_read_interval_uses_five_minute_minimum(self):
        self.assertEqual(team_router.role_read_interval_seconds("FAST"), 300)
        self.assertEqual(team_router.role_read_interval_seconds("NORMAL"), 300)
        self.assertEqual(team_router.role_read_interval_seconds("STRICT"), 300)
        self.assertEqual(team_router.role_read_interval_seconds("PACKAGE"), 300)

    def test_next_role_read_policy_uses_gate_interval_and_timezone(self):
        ledger = {
            "objective": "restore README BOM",
            "plan": {"fields": {"scope": "README.md", "riskBoundary": "docs-only encoding"}},
        }

        policy = team_router.next_role_read_policy(
            ledger,
            observed_at="2026-06-24T12:00:00+08:00",
        )

        self.assertEqual(policy["gateClass"], "FAST")
        self.assertEqual(policy["nextAllowedReadAt"], "2026-06-24T12:05:00+08:00")
        self.assertEqual(policy["minimumIntervalSeconds"], 300)
        self.assertTrue(policy["directReturnExpected"])
        self.assertTrue(policy["completionFeedbackRequired"])
        self.assertIn("observe-only", policy["convergenceMode"])

    def test_watcher_runtime_builds_facade_watcher_ledger(self):
        ledger = {
            "taskId": "ctr-20260624-120000-fast",
            "objective": "restore README BOM",
            "status": "awaiting_callback",
            "dispatches": [
                {
                    "threadId": "thread-executor",
                    "expectedCallback": "TEAM_ROUTER_CALLBACK taskId=ctr-20260624-120000-fast",
                    "searchAnchor": {
                        "messageId": "msg-dispatch",
                        "sentAt": "2026-06-24T12:00:00+08:00",
                    },
                },
            ],
            "readDiscipline": {
                "gateClass": "FAST",
                "lastReadAt": "2026-06-24T12:00:00+08:00",
                "nextAllowedReadAt": "2026-06-24T12:05:00+08:00",
                "minimumIntervalSeconds": 300,
                "directReturnExpected": True,
            },
        }

        wakeup = team_router._watch_next_wakeup(ledger)
        runtime_watcher = team_router_watcher_runtime.build_watcher_ledger(wakeup, ledger)

        self.assertEqual(runtime_watcher, team_router._watcher_ledger(ledger))
        self.assertEqual(runtime_watcher["role"], "executor")
        self.assertEqual(runtime_watcher["firstCheckAt"], "2026-06-24T12:00:30+08:00")
        self.assertEqual(runtime_watcher["nextAllowedReadAt"], "2026-06-24T12:05:00+08:00")

    def test_watcher_runtime_does_not_call_heartbeat_scheduler(self):
        runtime_source = (ROOT / "src" / "team_router_watcher_runtime.py").read_text(encoding="utf-8")
        facade_source = (ROOT / "src" / "team_router.py").read_text(encoding="utf-8")

        self.assertNotIn("heartbeat_scheduler_call", runtime_source)
        self.assertNotIn("(**payload)", runtime_source)
        self.assertIn("_heartbeat_scheduler_call(heartbeat_scheduler)(**payload)", facade_source)

    def test_missing_protocol_status_does_not_treat_active_done_phrasing_as_feedback_missing(self):
        self.assertEqual(
            team_router._missing_protocol_observed_status("not done yet, still working"),
            "active",
        )
        self.assertEqual(
            team_router._missing_protocol_observed_status("I'm done with step 1, moving on"),
            "active",
        )
        self.assertEqual(
            team_router._missing_protocol_observed_status("looks completely fine, continuing"),
            "active",
        )

    def test_missing_protocol_status_requires_structured_completion_cues(self):
        self.assertEqual(
            team_router._missing_protocol_observed_status("status: done\nfinal: true"),
            "needs_feedback",
        )
        self.assertEqual(
            team_router._missing_protocol_observed_status("completed successfully"),
            "needs_feedback",
        )

    def test_role_read_allowed_suppresses_early_fallback_reads(self):
        ledger = {
            "taskId": "ctr-20260624-120000-fast",
            "objective": "restore README BOM",
            "status": "awaiting_callback",
            "plan": {"fields": {"scope": "README.md", "riskBoundary": "docs-only encoding"}},
            "readDiscipline": {
                "gateClass": "FAST",
                "nextAllowedReadAt": "2026-06-24T12:05:00+08:00",
                "directReturnExpected": True,
            },
        }

        decision = team_router.role_read_allowed(
            ledger,
            observed_at="2026-06-24T12:04:59+08:00",
            reason="scheduled-fallback",
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["action"], "read_suppressed")
        self.assertIn("direct return", decision["reason"])

    def test_role_read_allowed_user_triggered_status_read(self):
        ledger = {
            "taskId": "ctr-20260624-120000-fast",
            "objective": "restore README BOM",
            "status": "awaiting_callback",
            "readDiscipline": {
                "gateClass": "FAST",
                "nextAllowedReadAt": "2026-06-24T12:05:00+08:00",
                "directReturnExpected": True,
            },
        }

        decision = team_router.role_read_allowed(
            ledger,
            observed_at="2026-06-24T12:00:10+08:00",
            reason="user_requested_status check",
        )

        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["action"], "read_allowed")

    def test_manager_polling_status_update_suppresses_early_read_and_repeated_active_report(self):
        ledger = {
            "taskId": "ctr-20260702-live-role-polling-ux",
            "objective": "enforce quiet manager polling",
            "status": "awaiting_callback",
            "roleThreadStatus": "inProgress",
            "readDiscipline": {
                "gateClass": "STRICT",
                "lastReadAt": "2026-07-02T10:00:30+08:00",
                "lastReportedRoleStatus": "in_progress",
                "nextAllowedReadAt": "2026-07-02T10:05:30+08:00",
                "minimumIntervalSeconds": 300,
                "directReturnExpected": True,
            },
        }
        wakeup = {
            "role": "reviewer",
            "threadId": "thread-reviewer",
            "expectedMarker": "TEAM_ROUTER_REVIEW taskId=ctr-20260702-live-role-polling-ux",
            "searchAnchor": {"sentAt": "2026-07-02T10:00:00+08:00"},
            "reason": "awaiting reviewer",
        }

        decision = team_router.manager_polling_status_update(
            ledger,
            wakeup,
            observed_at="2026-07-02T10:04:00+08:00",
            observed_status="inProgress",
            read_reason="scheduled watcher heartbeat",
        )

        self.assertFalse(decision["shouldRead"])
        self.assertFalse(decision["shouldReport"])
        self.assertEqual(decision["action"], "read_suppressed")
        self.assertEqual(decision["nextAllowedReadAt"], "2026-07-02T10:05:30+08:00")
        self.assertIn("without repeated status narration", decision["reportReason"])

    def test_manager_polling_status_update_suppresses_unchanged_active_status_after_allowed_read(self):
        ledger = {
            "taskId": "ctr-20260702-live-role-polling-ux",
            "objective": "enforce quiet manager polling",
            "status": "awaiting_callback",
            "roleThreadStatus": "inProgress",
            "readDiscipline": {
                "gateClass": "STRICT",
                "lastReadAt": "2026-07-02T10:00:30+08:00",
                "lastReportedRoleStatus": "in_progress",
                "nextAllowedReadAt": "2026-07-02T10:05:30+08:00",
                "minimumIntervalSeconds": 300,
                "directReturnExpected": True,
            },
        }
        wakeup = {
            "role": "reviewer",
            "threadId": "thread-reviewer",
            "expectedMarker": "TEAM_ROUTER_REVIEW taskId=ctr-20260702-live-role-polling-ux",
            "searchAnchor": {"sentAt": "2026-07-02T10:00:00+08:00"},
            "reason": "awaiting reviewer",
        }

        decision = team_router.manager_polling_status_update(
            ledger,
            wakeup,
            observed_at="2026-07-02T10:05:30+08:00",
            observed_status="inProgress",
            read_reason="scheduled watcher heartbeat",
        )

        self.assertTrue(decision["shouldRead"])
        self.assertFalse(decision["shouldReport"])
        self.assertEqual(decision["action"], "unchanged_active_status_suppressed")
        self.assertIn("status changes", decision["reportReason"])

    def test_manager_polling_status_update_reports_status_changes_only(self):
        ledger = {
            "taskId": "ctr-20260702-live-role-polling-ux",
            "objective": "enforce quiet manager polling",
            "status": "awaiting_callback",
            "roleThreadStatus": "running",
            "readDiscipline": {
                "gateClass": "STRICT",
                "lastReadAt": "2026-07-02T10:00:30+08:00",
                "lastReportedRoleStatus": "in_progress",
                "nextAllowedReadAt": "2026-07-02T10:05:30+08:00",
                "minimumIntervalSeconds": 300,
                "directReturnExpected": True,
            },
        }
        wakeup = {
            "role": "reviewer",
            "threadId": "thread-reviewer",
            "expectedMarker": "TEAM_ROUTER_REVIEW taskId=ctr-20260702-live-role-polling-ux",
            "searchAnchor": {"sentAt": "2026-07-02T10:00:00+08:00"},
            "reason": "awaiting reviewer",
        }

        decision = team_router.manager_polling_status_update(
            ledger,
            wakeup,
            observed_at="2026-07-02T10:05:30+08:00",
            observed_status="running",
            read_reason="scheduled watcher heartbeat",
        )

        self.assertTrue(decision["shouldRead"])
        self.assertTrue(decision["shouldReport"])
        self.assertEqual(decision["action"], "status_change_report")
        self.assertEqual(decision["previousReportedStatus"], "in_progress")
        self.assertEqual(decision["observedStatus"], "running")

    def test_role_read_allowed_does_not_bypass_on_incidental_stop_word(self):
        ledger = {
            "taskId": "ctr-20260624-120000-fast",
            "objective": "restore README BOM",
            "status": "awaiting_callback",
            "readDiscipline": {
                "gateClass": "FAST",
                "nextAllowedReadAt": "2026-06-24T12:05:00+08:00",
                "directReturnExpected": True,
            },
        }

        decision = team_router.role_read_allowed(
            ledger,
            observed_at="2026-06-24T12:00:10+08:00",
            reason="do not stop the heartbeat",
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["action"], "read_suppressed")


    def test_waiting_read_discipline_moves_next_allowed_after_single_first_check(self):
        ledger = {
            "taskId": "ctr-20260624-120000-fast",
            "objective": "restore README BOM",
            "status": "awaiting_callback",
            "roleThreadStatus": "running",
            "readDiscipline": {
                "gateClass": "FAST",
                "lastReadAt": None,
                "nextAllowedReadAt": "2026-06-24T12:05:00+08:00",
                "minimumIntervalSeconds": 300,
                "directReturnExpected": True,
            },
        }

        discipline = team_router._waiting_read_discipline(
            ledger,
            observed_at="2026-06-24T12:00:30+08:00",
        )

        self.assertEqual(discipline["lastReadAt"], "2026-06-24T12:00:30+08:00")
        self.assertEqual(discipline["nextAllowedReadAt"], "2026-06-24T12:05:30+08:00")
        self.assertEqual(discipline["minimumIntervalSeconds"], 300)
    def test_role_read_allowed_enforces_last_read_five_minute_interval(self):
        ledger = {
            "taskId": "ctr-20260624-120000-fast",
            "objective": "restore README BOM",
            "status": "awaiting_callback",
            "readDiscipline": {
                "gateClass": "FAST",
                "lastReadAt": "2026-06-24T12:00:00+08:00",
                "nextAllowedReadAt": "2026-06-24T12:00:30+08:00",
                "minimumIntervalSeconds": 300,
                "directReturnExpected": True,
            },
        }

        early = team_router.role_read_allowed(
            ledger,
            observed_at="2026-06-24T12:04:59+08:00",
            reason="scheduled-fallback",
        )
        allowed = team_router.role_read_allowed(
            ledger,
            observed_at="2026-06-24T12:05:00+08:00",
            reason="scheduled-fallback",
        )

        self.assertFalse(early["allowed"])
        self.assertEqual(early["nextAllowedReadAt"], "2026-06-24T12:05:00+08:00")
        self.assertEqual(early["minimumIntervalSeconds"], 300)
        self.assertTrue(allowed["allowed"])


    def test_convergence_prompt_disallowed_while_role_status_is_active(self):
        ledger = {
            "taskId": "ctr-20260624-120000-strict",
            "status": "awaiting_callback",
            "roleThreadStatus": "inProgress",
            "readDiscipline": {
                "gateClass": "STRICT",
                "nextAllowedReadAt": "2026-06-24T12:01:30+08:00",
                "directReturnExpected": True,
            },
        }

        decision = team_router.convergence_prompt_allowed(
            ledger,
            observed_at="2026-06-24T12:00:40+08:00",
            reason="scheduled convergence check",
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["action"], "observe_only_wait")
        self.assertEqual(decision["observedStatus"], "in_progress")

    def test_convergence_timeout_requires_observation_of_no_progress_first(self):
        ledger = {
            "taskId": "ctr-20260624-120000-strict",
            "status": "awaiting_callback",
            "roleThreadStatus": "idle",
            "readDiscipline": {
                "gateClass": "STRICT",
                "nextAllowedReadAt": "2026-06-24T12:01:30+08:00",
                "directReturnExpected": True,
            },
        }

        decision = team_router.convergence_prompt_allowed(
            ledger,
            observed_at="2026-06-24T12:05:00+08:00",
            reason="timeout fallback",
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["action"], "observe_only_read_first")

    def test_convergence_timeout_allowed_after_observation_confirms_no_progress(self):
        ledger = {
            "taskId": "ctr-20260624-120000-strict",
            "status": "awaiting_callback",
            "roleThreadStatus": "idle",
            "readDiscipline": {
                "gateClass": "STRICT",
                "nextAllowedReadAt": "2026-06-24T12:01:30+08:00",
                "directReturnExpected": True,
                "lastObservedNoProgressAt": "2026-06-24T12:04:30+08:00",
            },
        }

        decision = team_router.convergence_prompt_allowed(
            ledger,
            observed_at="2026-06-24T12:05:00+08:00",
            reason="timeout fallback",
        )

        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["action"], "convergence_allowed")
        self.assertEqual(decision["observedNoProgressAt"], "2026-06-24T12:04:30+08:00")

    def test_command_startup_retry_decision_uses_parent_probes_then_same_scope_retry(self):
        decision = team_router.command_startup_retry_decision(-1073741502, "", "")

        self.assertTrue(decision["startupFailure"])
        self.assertEqual(decision["action"], "run_parent_minimal_probes")
        self.assertIn("cmd.exe /c ver", decision["probes"])
        self.assertIn("Get-Location", decision["probes"])
        self.assertIn("git status -s --untracked-files=all", decision["probes"])

        retry = team_router.command_startup_retry_decision(-1073741502, "", "", probes_recovered=True)
        self.assertEqual(retry["action"], "retry_same_scope")
        self.assertIn("只重试同一个窄 package", retry["reason"])

        blocked = team_router.command_startup_retry_decision(-1073741502, "", "", probes_recovered=False)
        self.assertEqual(blocked["action"], "environment_blocked")
        self.assertIn("环境仍被阻断", blocked["reason"])

    def test_verifier_evidence_only_fast_path_requires_complete_evidence_and_pass_review(self):
        callback_fields = {
            "status": "done",
            "summary": "implemented",
            "evidence": "tests: ok; diff checked",
        }
        reviewer_result = {
            "fields": {
                "result": "pass",
                "requiredChanges": "none",
                "evidenceChecked": "tests",
            }
        }

        decision = team_router.verifier_evidence_only_fast_path(callback_fields, reviewer_result)
        self.assertTrue(decision["allowed"])
        self.assertIn("evidence is present", decision["reason"])
        self.assertNotIn("complete", decision["reason"].lower())

    def test_verifier_evidence_only_fast_path_rejects_required_changes_or_missing_evidence(self):
        missing = team_router.verifier_evidence_only_fast_path({"status": "done"}, None)
        self.assertFalse(missing["allowed"])
        self.assertIn("missing", missing["reason"])

        reviewer_gap = team_router.verifier_evidence_only_fast_path(
            {"status": "done", "evidence": "tests"},
            {"fields": {"result": "pass", "requiredChanges": "add more evidence"}},
        )
        self.assertFalse(reviewer_gap["allowed"])
        self.assertIn("requiredChanges", reviewer_gap["reason"])

    def test_verifier_evidence_only_fast_path_rejects_missing_reviewer_result_even_with_evidence(self):
        decision = team_router.verifier_evidence_only_fast_path(
            {"status": "done", "evidence": "tests passed"},
            None,
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "reviewer result is missing")

    def test_verifier_evidence_only_fast_path_respects_required_qa_gate(self):
        callback_fields = {"status": "done", "evidence": "tests passed"}
        reviewer_result = {"fields": {"result": "pass", "requiredChanges": "none"}}

        missing_qa = team_router.verifier_evidence_only_fast_path(
            callback_fields,
            reviewer_result,
            qa_required=True,
            qa_result=None,
        )
        self.assertFalse(missing_qa["allowed"])
        self.assertEqual(missing_qa["reason"], "QA result is missing or not pass")

        passed_qa = team_router.verifier_evidence_only_fast_path(
            callback_fields,
            reviewer_result,
            qa_required=True,
            qa_result={"fields": {"result": "pass"}},
        )
        self.assertTrue(passed_qa["allowed"])
        self.assertIn("evidence is present", passed_qa["reason"])
    def test_protocol_contract_snapshot_centralizes_roles_states_and_markers(self):
        snapshot = team_router.protocol_contract_snapshot()

        self.assertEqual(snapshot["parentSideRoles"]["parent_orchestrator"]["displayName"], "调度者")
        self.assertEqual(snapshot["parentSideRoles"]["parent_orchestrator"]["englishAlias"], "Orchestrator")
        snapshot_text = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("父线程" + "调度者", snapshot_text)
        self.assertNotIn("Parent " + "Orchestrator", snapshot_text)
        self.assertFalse(snapshot["parentSideRoles"]["state_controller"]["thread"])
        self.assertEqual(snapshot["roleThreads"]["manager"]["displayName"], "规划者")
        self.assertEqual(snapshot["roleThreads"]["reviewer"]["displayName"], "审查者")
        self.assertEqual(snapshot["roleThreads"]["reviewer"]["englishAlias"], "Reviewer")
        self.assertTrue(snapshot["roleThreads"]["reviewer"]["conditional"])
        self.assertTrue(snapshot["roleThreads"]["executor"]["thread"])
        self.assertEqual(snapshot["threadPermissions"], ["design-only", "local-package", "read-only"])
        self.assertIn("send_message_to_thread", snapshot["threadToolNames"])
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_CALLBACK"]["requiredFields"],
            ["status", "final", "summary", "evidence", "risks", "next"],
        )
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_VERDICT"]["allowedValues"]["result"],
            ["blocked", "needs_rework", "pass"],
        )
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_VERDICT"]["conditionalRequired"]["result"],
            "required unless status: accepted is present; status: accepted implies result: pass",
        )
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_REVIEW"]["requiredFields"],
            ["result", "summary", "findings", "requiredChanges", "evidenceChecked", "risks"],
        )
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_REVIEW"]["allowedValues"]["result"],
            ["blocked", "needs_rework", "pass"],
        )
        self.assertIn("awaiting_callback", snapshot["stateMachine"]["main"])
        self.assertIn("reviewing", snapshot["stateMachine"]["main"])
        self.assertEqual(snapshot["recoverableStatuses"]["callback_unreachable"], "verifying")
        self.assertEqual(snapshot["recoverableStatuses"]["review_unreachable"], "reviewing")
        self.assertEqual(snapshot["stateMachine"]["manual_recovery"]["review_unreachable"], "reviewing")



    def test_protocol_contract_snapshot_includes_manager_orchestration_policy(self):
        snapshot = team_router.protocol_contract_snapshot()
        policy = snapshot["managerOrchestrationPolicy"]
        self.assertEqual(snapshot["agentAssistPolicy"], policy["agentAssistPolicy"])

        self.assertIn("low-frequency", policy["polling"]["mode"])
        self.assertIn("event-driven", policy["polling"]["mode"])
        self.assertIn("read_thread", policy["polling"]["mode"])
        self.assertIn("5 minutes", policy["polling"]["steadyCadence"])
        self.assertIn("user-triggered status check", policy["polling"]["allowedReads"])
        self.assertIn("agreed or explicit interval", "\n".join(policy["polling"]["allowedReads"]))
        self.assertIn("known expected completion window", "\n".join(policy["polling"]["allowedReads"]))
        self.assertIn("timeout or blocker handling", policy["polling"]["allowedReads"])
        self.assertIn("bounded status reads are allowed", policy["polling"]["zeroReadBoundary"])
        self.assertIn("zero-read waiting is not required", policy["polling"]["zeroReadBoundary"])
        self.assertIn("continuous polling", policy["polling"]["forbidden"])
        self.assertIn("mid-run instruction injection", policy["polling"]["forbidden"])
        self.assertIn("status changes", policy["polling"]["userVisibleUpdates"])
        watcher = policy["watcherAutomation"]
        self.assertEqual(
            watcher["ledgerFields"],
            ("role", "threadId", "expectedMarker", "lastReadAt", "firstCheckAt", "nextAllowedReadAt", "status", "waitingReason", "nextManagerAction"),
        )
        self.assertIn("heartbeat", watcher["fallback"])
        self.assertIn("5 minutes", watcher["fallback"])
        self.assertIn("Role writing a marker is not receipt by the manager", watcher["receiptRule"])
        self.assertIn("plain user-facing language", watcher["completionReport"])
        self.assertIn("firstCheckAt", watcher["ledgerFields"])
        self.assertIn("single short observation-only check", watcher["firstCheck"])
        self.assertIn("5 minutes", watcher["firstCheck"])
        accepted_closeout = watcher["acceptedCloseout"]
        self.assertIn("stop_and_delete_heartbeat", accepted_closeout["watcherAction"])
        self.assertIn("plain language", accepted_closeout["reportAction"])
        self.assertIn("stage/commit/push/PR/publish/release were not done", accepted_closeout["notDone"])
        direct_return = policy["roleDirectReturn"]
        self.assertEqual(direct_return["defaultReturnThread"], "none without explicit parent/source thread id")
        self.assertIn("current orchestrator/parent thread", direct_return["targetThread"])
        self.assertIn("not the manager/planner role thread", direct_return["targetThread"])
        self.assertEqual(
            direct_return["requiredLedgerFields"],
            ("returnThreadId", "orchestratorThreadId", "roleThreadId"),
        )
        self.assertIn("direct-send", direct_return["delivery"])
        self.assertIn("self-thread-marker", direct_return["fallback"])
        self.assertIn("5 minutes", direct_return["fallback"])
        self.assertIn("child-thread output alone is not parent receipt", direct_return["completionReceipt"])
        self.assertIn("bare create_thread plus read_thread", direct_return["manualThreadBoundary"])
        self.assertIn("formally dispatched with returnThreadId/sourceRoleThreadId", direct_return["manualThreadBoundary"])
        self.assertIn("deliveryStatus: fallback_only", direct_return["degradedCollection"])
        self.assertIn("normal proactive return", direct_return["degradedCollection"])
        self.assertIn("taskId", direct_return["managerReceiptValidation"])
        self.assertIn("protocol-block `sourceThreadId`", direct_return["managerReceiptValidation"])
        self.assertIn("role", direct_return["managerReceiptValidation"])
        self.assertIn("sourceRoleThreadId", direct_return["managerReceiptValidation"])
        self.assertIn("pending `returnThreadId`", direct_return["managerReceiptValidation"])
        self.assertIn("marker", direct_return["managerReceiptValidation"])
        self.assertIn("orchestratorThreadId", direct_return["managerReceiptValidation"])
        self.assertIn("roleThreadId", direct_return["managerReceiptValidation"])
        self.assertIn("expected marker", direct_return["inboxValidation"])
        self.assertIn("currently awaited", direct_return["inboxValidation"])
        self.assertIn("duplicate direct callbacks are ignored", direct_return["deduplication"])
        self.assertIn("not recorded twice", direct_return["deduplication"])
        self.assertEqual(
            direct_return["markers"],
            {
                "executor": "TEAM_ROUTER_CALLBACK",
                "reviewer": "TEAM_ROUTER_REVIEW",
                "verifier": "TEAM_ROUTER_VERDICT",
                "architect": "TEAM_ROUTER_ARCHITECT_REVIEW",
                "qa": "TEAM_ROUTER_QA_REVIEW",
            },
        )
        delivery_model = policy["callbackDeliveryModel"]
        self.assertIn("direct-send", delivery_model["primaryDelivery"])
        self.assertIn("send_message_to_thread", delivery_model["primaryDelivery"])
        self.assertIn("threadId=<returnThreadId>", delivery_model["primaryDelivery"])
        self.assertNotIn("send_message_to_thread(sourceThreadId, protocolBlock)", delivery_model["primaryDelivery"])
        self.assertIn("self-thread-marker", delivery_model["fallback"])
        self.assertIn("mandatory audit and recovery path", delivery_model["fallback"])
        self.assertIn("sourceThreadId", delivery_model["requiredDispatchFields"])
        self.assertIn("sourceRoleThreadId", delivery_model["requiredDispatchFields"])
        self.assertIn("role", delivery_model["requiredDispatchFields"])
        self.assertIn("callbackMarker", delivery_model["requiredDispatchFields"])
        self.assertIn("returnThreadId", delivery_model["requiredDispatchFields"])
        self.assertIn("callbackDelivery: direct-send", delivery_model["requiredDispatchFields"])
        self.assertIn("callbackFallback: self-thread-marker", delivery_model["requiredDispatchFields"])
        self.assertIn("reviewDelivery: direct-send", delivery_model["requiredDispatchFields"])
        self.assertIn("reviewFallback: self-thread-marker", delivery_model["requiredDispatchFields"])
        self.assertIn("verdictDelivery: direct-send", delivery_model["requiredDispatchFields"])
        self.assertIn("verdictFallback: self-thread-marker", delivery_model["requiredDispatchFields"])
        self.assertIn("callbackDelivery/reviewDelivery/verdictDelivery: direct-send", delivery_model["requiredDispatchFields"])
        self.assertIn("callbackFallback/reviewFallback/verdictFallback: self-thread-marker", delivery_model["requiredDispatchFields"])
        self.assertIn("architectReviewDelivery: direct-send", delivery_model["requiredDispatchFields"])
        self.assertIn("architectReviewFallback: self-thread-marker", delivery_model["requiredDispatchFields"])
        self.assertIn("qaReviewDelivery: direct-send", delivery_model["requiredDispatchFields"])
        self.assertIn("qaReviewFallback: self-thread-marker", delivery_model["requiredDispatchFields"])
        self.assertIn("two-step bootstrap", delivery_model["roleThreadBootstrap"])
        self.assertIn("taskId", delivery_model["managerReceiptValidation"])
        self.assertIn("role", delivery_model["managerReceiptValidation"])
        self.assertIn("sourceRoleThreadId", delivery_model["managerReceiptValidation"])
        self.assertIn("same protocol block body", delivery_model["fallbackBodyInvariant"])
        self.assertIn("deliveryStatus: fallback_only", delivery_model["fallbackMetadata"])
        self.assertIn("deliveryError", delivery_model["fallbackMetadata"])
        self.assertIn("direct-send first", delivery_model["normalCadence"])
        self.assertIn("one bounded read/check", delivery_model["normalCadence"])
        self.assertIn("avoid continuous polling", delivery_model["normalCadence"])
        self.assertIn("must direct-send", delivery_model["proactiveReturnRule"])
        self.assertIn("key checks complete", delivery_model["proactiveReturnRule"])
        self.assertIn("must not rely on parent polling", delivery_model["proactiveReturnRule"])
        self.assertIn("bare create_thread plus read_thread", delivery_model["bareCreateThreadBoundary"])
        self.assertIn("manual/degraded collection only", delivery_model["bareCreateThreadBoundary"])
        self.assertIn("registered", delivery_model["bareCreateThreadBoundary"])
        self.assertIn("bounded wait/read", delivery_model["boundedControlFallback"])
        self.assertIn("scope-limited closeout", delivery_model["boundedControlFallback"])
        self.assertIn("already-confirmed facts", delivery_model["boundedControlFallback"])

        convergence = policy["convergence"]
        self.assertIn("observation-only", convergence["statusReads"])
        self.assertIn("return-verdict-now", convergence["firstResponseToStillWorking"])
        self.assertIn("idle or completed", convergence["allowedWhen"][0])
        self.assertIn("blocked or explicitly asks", convergence["allowedWhen"][1])
        self.assertIn("user explicitly asks", convergence["allowedWhen"][2])
        self.assertIn("observation-only status read confirms no recent progress", convergence["allowedWhen"][3])
        self.assertEqual(convergence["blockedWhileRoleStatus"], ("active", "inProgress", "running", "working"))
        self.assertIn("slow progress alone is not enough", convergence["retryWithFreshRoleThread"])
        startup = policy["startupFailureRecovery"]
        self.assertIn("-1073741502", startup["startupFailureSignature"])
        self.assertIn("environment/tooling startup failure", startup["startupFailureSignature"])
        self.assertIn("pause role escalation", startup["managerSequence"][0])
        self.assertIn("cmd.exe /c ver", startup["managerSequence"][1])
        self.assertIn("Get-Location", startup["managerSequence"][1])
        self.assertIn("git status", startup["managerSequence"][1])
        self.assertIn("只重试同一个窄 package", startup["managerSequence"][2])
        self.assertIn("环境阻断", startup["managerSequence"][3])
        self.assertIn("preserve the original authorized scope", startup["retryScope"])
        self.assertIn("reuse existing executor", policy["roleReuse"]["default"])
        self.assertIn("existing verifier", policy["roleReuse"]["default"])
        self.assertIn("same taskId or task family", policy["roleReuse"]["default"])
        self.assertIn("original executor", policy["roleReuse"]["reworkExecutor"])
        self.assertIn("original verifier", policy["roleReuse"]["reworkVerifier"])
        self.assertIn("isolation/audit boundary changes", policy["roleReuse"]["newThreadOnlyWhen"])
        title_policy = policy["roleTitleNormalization"]
        self.assertEqual(title_policy["format"], "角色-任务名")
        self.assertIn("immediately after creating or discovering", title_policy["requiredAfter"])
        self.assertIn("set_thread_title", title_policy["requiredAfter"])
        self.assertEqual(title_policy["appliesTo"], ("manager", "executor", "reviewer", "verifier"))
        self.assertIn("执行者-Team Router <task label>", title_policy["examples"])
        self.assertIn("审查者-Team Router <task label>", title_policy["examples"])
        self.assertIn("验证者-Team Router <task label>", title_policy["examples"])
        self.assertEqual(title_policy["parentThread"]["format"], "调度者-Team Router <task label>")
        self.assertIn("parent/current manager-dispatcher", title_policy["parentThread"]["scope"])
        self.assertIn("manager first renames", title_policy["parentThread"]["firstAction"])
        self.assertIn("before child-role dispatch", title_policy["parentThread"]["firstAction"])
        self.assertIn("requires explicit parent_thread_id", title_policy["parentThread"]["runtimeStatus"])
        self.assertIn("verdictDelivery: direct-send", policy["verifierDirectReturn"]["requiredFields"])
        self.assertIn("verdictFallback: self-thread-marker", policy["verifierDirectReturn"]["requiredFields"])
        self.assertEqual(
            policy["verifierDirectReturn"]["sendInstruction"],
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)",
        )

        evidence_only = policy["verifierEvidenceOnlyFastPath"]
        self.assertIn("non-empty evidence", evidence_only["allowedWhen"][0])
        self.assertNotIn("complete", evidence_only["allowedWhen"][0].lower())
        self.assertIn("reviewer result is pass", evidence_only["allowedWhen"][1])
        self.assertIn("requiredChanges is none", evidence_only["allowedWhen"][2])
        self.assertIn("requiredChanges is not none", evidence_only["forbiddenWhen"][0])
        self.assertIn("missing or incomplete", evidence_only["forbiddenWhen"][2])
        self.assertIn("evidence-only", evidence_only["verdictRequirements"][0])
        self.assertIn("residual risks", evidence_only["verdictRequirements"][1])
        self.assertIn("stage/commit/push/PR/release were not done", evidence_only["verdictRequirements"][2])

        agent_policy = policy["agentAssistPolicy"]
        self.assertIn("superpowers", agent_policy["purpose"])
        self.assertIn("gstack", agent_policy["purpose"])
        self.assertIn("visible role threads", agent_policy["purpose"])
        self.assertIn("native-subagent", agent_policy["visibleRoleBoundary"])
        self.assertIn("visible reviewer role conversation", agent_policy["visibleRoleBoundary"])
        self.assertIn("dispatch a role, reviewer, executor, or verifier", agent_policy["teamRouterContextDefault"])
        self.assertIn("visible Team Router role thread", agent_policy["teamRouterContextDefault"])
        self.assertIn("multi_agent/subagent", agent_policy["teamRouterContextDefault"])
        self.assertIn("explicitly asks for external subagents", agent_policy["teamRouterContextDefault"])
        process_write_boundary = agent_policy["managerModeProcessWriteBoundary"]
        self.assertIn("记录进skill", process_write_boundary["triggerExamples"])
        self.assertIn("改进skill", process_write_boundary["triggerExamples"])
        self.assertIn("superpowers修", process_write_boundary["triggerExamples"])
        self.assertIn("写进规则", process_write_boundary["triggerExamples"])
        self.assertIn("active Manager Mode", process_write_boundary["defaultHandling"])
        self.assertIn("orchestration", process_write_boundary["defaultHandling"])
        self.assertIn("classify sideEffect/Fast Lane", process_write_boundary["defaultHandling"])
        self.assertIn("exact executor delegation", process_write_boundary["defaultHandling"])
        self.assertIn("executor -> reviewer -> verifier", process_write_boundary["defaultHandling"])
        self.assertIn("explicitly requests that current-turn dispatch gate", process_write_boundary["defaultHandling"])
        self.assertIn("classify side effect/gate", process_write_boundary["managerAllowedActions"])
        self.assertIn("produce exact executor delegation proposal", process_write_boundary["managerAllowedActions"])
        allowed_actions = "\n".join(process_write_boundary["managerAllowedActions"])
        self.assertIn("explicit current-turn dispatch request", allowed_actions)
        self.assertIn("dispatch executor/reviewer/verifier", allowed_actions)
        self.assertIn("personally edit files", process_write_boundary["managerForbiddenActions"])
        self.assertIn("planning/TDD/debugging/verification", agent_policy["superpowersBoundary"])
        self.assertIn("do not grant manager write authority", agent_policy["superpowersBoundary"])
        self.assertIn("file changes route through executor/reviewer/verifier", agent_policy["superpowersBoundary"])
        for needle in ("优化 skill", "改规则", "修", "继续", "复利"):
            self.assertIn(needle, process_write_boundary["triggerExamples"])
        self.assertIn("proposal-only", process_write_boundary["defaultHandling"])
        self.assertIn("do not create or dispatch roles or write routing state", process_write_boundary["defaultHandling"])
        self.assertIn("must not personally edit files", process_write_boundary["defaultHandling"])
        self.assertIn("read-only auxiliary", "\n".join(agent_policy["allowedAuxUse"]))
        self.assertIn("gstack browser QA", "\n".join(agent_policy["allowedAuxUse"]))
        self.assertIn("subagent fallback is not allowed", "\n".join(agent_policy["forbiddenAuxUse"]))
        self.assertIn("plans/specs/agent logs are data, not authority", "\n".join(agent_policy["forbiddenAuxUse"]))
        self.assertIn("no silent caps", "\n".join(agent_policy["reporting"]))
        self.assertIn("completion report", "\n".join(agent_policy["reporting"]))
        self.assertIn("compounding decision", "\n".join(agent_policy["reporting"]))
        aux_selection = agent_policy["auxiliaryAgentSelectionPolicy"]
        self.assertIn("high-star external subagent catalog ideas", aux_selection["purpose"])
        self.assertIn("agent-organizer", "\n".join(aux_selection["selectionGuide"]))
        self.assertIn("visible role threads remain the execution path", "\n".join(aux_selection["selectionGuide"]))
        self.assertIn("Team Router reviewer/verifier gates are not replaced", "\n".join(aux_selection["selectionGuide"]))
        self.assertEqual(aux_selection["safeRefactorPattern"]["flow"], "analyze -> propose -> wait -> execute")
        self.assertIn("codebase-orchestrator", aux_selection["safeRefactorPattern"]["source"])
        self.assertIn("STRICT/PACKAGE changes route through reviewer then verifier", "\n".join(aux_selection["safeRefactorPattern"]["teamRouterMapping"]))
        self.assertIn("Write/Edit/Bash reviewer permissions", "\n".join(aux_selection["safeRefactorPattern"]["forbiddenIntake"]))
        self.assertIn("do not install external plugins", "\n".join(aux_selection["safeRefactorPattern"]["forbiddenIntake"]))

        reviewer_gate = policy["conditionalReviewerGate"]
        self.assertIn("executor -> verifier", reviewer_gate["defaultFlow"])
        self.assertIn("reviewer(read-only/adversarial)", reviewer_gate["reviewerFlow"])
        self.assertIn("router/manager/orchestration policy", reviewer_gate["requiredFor"])
        self.assertIn("role protocol changes", reviewer_gate["requiredFor"])
        self.assertIn("runtime gate or reviewer gate changes", reviewer_gate["requiredFor"])
        self.assertIn("Team Router self changes", "\n".join(reviewer_gate["requiredFor"]))
        self.assertIn("ordinary small fixes", reviewer_gate["skipWhen"])
        self.assertIn("not final acceptance", reviewer_gate["reviewerResponsibility"])
        self.assertIn("final acceptance", reviewer_gate["verifierResponsibility"])
        self.assertIn("reuse the same reviewer thread", reviewer_gate["roleReuse"])
        self.assertIn("original reviewer", reviewer_gate["roleReuse"])
        self.assertIn("send_reviewer_request_with_adapter()", reviewer_gate["runtimeImplementation"])
        self.assertIn("read_reviewer_review_update_with_adapter()", reviewer_gate["runtimeImplementation"])
        self.assertIn("capture_reviewer_review_from_read()", reviewer_gate["runtimeImplementation"])
        self.assertIn("needs_rework -> executor rework", reviewer_gate["runtimeImplementation"])
        self.assertIn("reviewer role conversation/thread", reviewer_gate["namedReviewerRequirement"])
        self.assertIn("create/register reviewer role conversation", reviewer_gate["namedReviewerRequirement"])
        self.assertIn("subagent fallback is not allowed", reviewer_gate["namedReviewerRequirement"])
        self.assertIn("reviewDelivery: direct-send", policy["reviewerDirectReturn"]["requiredFields"])
        self.assertIn("reviewFallback: self-thread-marker", policy["reviewerDirectReturn"]["requiredFields"])
        self.assertEqual(
            policy["reviewerDirectReturn"]["sendInstruction"],
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)",
        )

        fast_lane = policy["fastLane"]
        self.assertEqual(fast_lane["classes"], ("FAST", "NORMAL", "STRICT", "PACKAGE"))
        self.assertEqual(fast_lane["FAST"]["route"], "executor -> verifier")
        self.assertEqual(fast_lane["FAST"]["fallbackReadWindowSeconds"], 300)
        self.assertIn("docs/BOM", fast_lane["FAST"]["scope"])
        self.assertEqual(fast_lane["NORMAL"]["route"], "executor -> verifier")
        self.assertEqual(fast_lane["NORMAL"]["fallbackReadWindowSeconds"], 300)
        self.assertIn("small focused code/test work", fast_lane["NORMAL"]["scope"])
        self.assertEqual(fast_lane["STRICT"]["route"], "executor -> reviewer -> verifier")
        self.assertEqual(fast_lane["STRICT"]["fallbackReadWindowSeconds"], 300)
        self.assertIn("Team Router process", fast_lane["STRICT"]["scope"])
        self.assertEqual(fast_lane["PACKAGE"]["route"], "executor -> reviewer -> verifier")
        self.assertEqual(fast_lane["PACKAGE"]["fallbackReadWindowSeconds"], 300)
        self.assertIn("same task family discipline hardening", fast_lane["PACKAGE"]["scope"])
        self.assertIn("direct-return first", fast_lane["completion"])
        self.assertIn("bounded read_thread fallback", fast_lane["completion"])
        self.assertIn("300 second", fast_lane["completion"])
        self.assertIn("user-triggered status request", fast_lane["completion"])
        self.assertIn("CRLF/LF normalization", fast_lane["mechanicalFixException"])
        self.assertIn("either reviewer or verifier", fast_lane["mechanicalFixException"])
        self.assertIn("semantic/process risk", fast_lane["mechanicalFixException"])
        closeout_reporting = policy["closeoutReportingPolicy"]
        self.assertEqual(
            closeout_reporting["requiredFields"],
            (
                "implemented changes",
                "verification actually run and results",
                "blockers/exceptions",
                "remaining risks",
                "current state and next step",
                "compoundingDecision: recorded | skipped",
                "reason: ...",
            ),
        )
        self.assertIn("every task closeout", closeout_reporting["scope"])
        self.assertIn("closeout compounding decision", closeout_reporting["scope"])

        compounding = policy["compoundingDecisionPolicy"]
        self.assertEqual(compounding["closeoutFields"]["compoundingDecision"], ("recorded", "skipped"))
        self.assertIn("required explanatory text", compounding["closeoutFields"]["reason"])
        self.assertIn("default to compoundingDecision: recorded", compounding["recordDefault"])
        self.assertIn("concrete reason and evidence", compounding["recordDefault"])
        self.assertIn("manager overreach", compounding["recordWhen"])
        self.assertIn("role conflict", compounding["recordWhen"])
        self.assertIn("role-authority confusion", compounding["recordWhen"])
        self.assertIn("permission/sandbox issue", compounding["recordWhen"])
        self.assertIn("permission boundary failure", compounding["recordWhen"])
        self.assertIn("test instability", compounding["recordWhen"])
        self.assertIn("temp-file/workspace pollution", compounding["recordWhen"])
        self.assertIn("user explicitly adds a reusable process preference", compounding["recordWhen"])
        self.assertIn("manager overreach", compounding["recordedLessons"][0])
        self.assertIn("role-authority mistakes", compounding["recordedLessons"][0])
        self.assertIn("docs/compounding.md", compounding["recordedLessons"][0])
        self.assertIn("docs/evidence", compounding["recordedLessons"][0])
        self.assertIn("durable lesson writes are executor-owned and gated", compounding["recordedLessons"][1])
        self.assertIn("must not self-write the lesson", compounding["recordedLessons"][1])
        self.assertIn("pending/blocked/skipped", compounding["noDurableWriteReport"])
        self.assertIn("silently omitting", compounding["noDurableWriteReport"])
        self.assertIn("ordinary successful implementation/testing", compounding["skipWhen"])
        self.assertIn("no new reusable risk", compounding["skipWhen"])
        self.assertIn("compoundingDecision: skipped", compounding["skipReport"])
        self.assertIn("reason: ordinary successful implementation/testing", compounding["skipReport"])


    def test_protocol_contract_snapshot_includes_side_effect_taxonomy_policy(self):
        policy = team_router.protocol_contract_snapshot()["sideEffectTaxonomy"]

        self.assertEqual(
            set(policy) & {
                "READ_ONLY",
                "DISPATCH_ONLY",
                "LOCAL_CLOSEOUT",
                "WORKSPACE_WRITE",
                "HEAVY_OR_RISKY",
                "EXTERNAL_RELEASE",
            },
            {
                "READ_ONLY",
                "DISPATCH_ONLY",
                "LOCAL_CLOSEOUT",
                "WORKSPACE_WRITE",
                "HEAVY_OR_RISKY",
                "EXTERNAL_RELEASE",
            },
        )
        self.assertIn("CodeGraph query/status/explore", policy["READ_ONLY"]["description"])
        self.assertIn("read_thread low-frequency", policy["READ_ONLY"]["description"])
        self.assertIn("not implementation", policy["READ_ONLY"]["boundary"])
        self.assertIn("TEAM_ROUTER_DISPATCH", policy["DISPATCH_ONLY"]["description"])
        self.assertIn("record/capture ledger state", policy["DISPATCH_ONLY"]["description"])
        self.assertIn("routing is not implementation", policy["DISPATCH_ONLY"]["boundary"])
        self.assertIn("verifier pass", policy["LOCAL_CLOSEOUT"]["requires"])
        self.assertIn("explicit user commit request", policy["LOCAL_CLOSEOUT"]["requires"])
        self.assertIn("stage only accepted files", policy["LOCAL_CLOSEOUT"]["allowedFor"])
        self.assertIn("unrelated untracked", policy["LOCAL_CLOSEOUT"]["excludes"])
        self.assertIn("push/PR/merge/deploy", policy["LOCAL_CLOSEOUT"]["excludes"])
        self.assertIn("fixtures", policy["WORKSPACE_WRITE"]["description"])
        self.assertIn("executor", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("authorized local-package dispatch", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("explicit scope/files", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("only within that explicit scope", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("required reviewer/verifier gates", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("exact current-turn manager instruction", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("specific file edit/file-change action", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("commit/PR/publish/release", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("prompt and wait for explicit authorization", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("executor local-package authorization", policy["WORKSPACE_WRITE"]["managerFileEditAuthorization"])
        self.assertIn("current-turn explicit manager instruction", policy["WORKSPACE_WRITE"]["managerFileEditAuthorization"])
        self.assertIn("historical authorization", policy["WORKSPACE_WRITE"]["managerFileEditAuthorization"])
        self.assertIn("terse approvals", policy["WORKSPACE_WRITE"]["managerFileEditAuthorization"])
        self.assertIn("role switch alone", policy["WORKSPACE_WRITE"]["managerFileEditAuthorization"])
        self.assertIn("external API", policy["HEAVY_OR_RISKY"]["description"])
        self.assertIn("explicit separate authorization", policy["HEAVY_OR_RISKY"]["requires"])
        self.assertIn("push/PR/merge/deploy/publish/release", policy["EXTERNAL_RELEASE"]["description"])
        self.assertIn("separate publish/release authorization", policy["EXTERNAL_RELEASE"]["requires"])
        self.assertIn("authorize only a dispatch proposal", policy["terseApprovalBoundary"])
        self.assertIn("do not authorize create_thread, role messages, registry/ledger writes", policy["terseApprovalBoundary"])
        self.assertIn("explicit current-turn create/dispatch request", policy["terseApprovalBoundary"])
        self.assertIn("subagent fallback is not allowed", policy["namedReviewerRequirement"])

    def test_active_manager_dispatches_small_artifact_policy_writes(self):
        policy = team_router.protocol_contract_snapshot()["sideEffectTaxonomy"]
        regression = policy["WORKSPACE_WRITE"]["managerOverreachRegression"]
        scenarios = (
            "small artifact policy task",
            "docs policy task",
            ".gitignore policy task",
        )

        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                self.assertIn("WORKSPACE_WRITE", policy)
                self.assertIn("executor dispatch", regression)
                self.assertIn("specific manager file-edit instruction", regression)
                self.assertIn("asking for role/authorization", regression)
                self.assertIn("role switch alone is not sufficient", regression)
                self.assertIn(scenario.split()[0], regression)
                self.assertIn("active Manager Mode", regression)

    def test_protocol_contract_snapshot_includes_role_closeout_policy(self):
        policy = team_router.protocol_contract_snapshot()["roleCloseoutPolicy"]

        self.assertIn("no extra ROLE_CLOSEOUT", policy["default"])
        self.assertIn("ordinary closeout messages", policy["default"])
        self.assertIn("final protocol block is the closeout", policy["finalProtocolBlock"])
        self.assertIn("TEAM_ROUTER_CALLBACK", policy["finalProtocolBlock"])
        self.assertIn("TEAM_ROUTER_REVIEW", policy["finalProtocolBlock"])
        self.assertIn("TEAM_ROUTER_VERDICT", policy["finalProtocolBlock"])
        self.assertIn("proactively return", policy["proactiveReturn"])
        self.assertIn("key checks complete", policy["proactiveReturn"])
        self.assertIn("must not rely on parent polling", policy["proactiveReturn"])
        self.assertIn("bounded wait/read", policy["controlFallback"])
        self.assertIn("scope-limited", policy["controlFallback"])
        self.assertIn("already-confirmed facts", policy["controlFallback"])
        self.assertIn("docs/compounding.md", policy["continuousRecords"])
        self.assertIn("docs/workbench.md", policy["continuousRecords"])
        self.assertIn("separately authorized workspace-write gate", policy["continuousRecords"])
        self.assertIn("never write those files automatically", policy["continuousRecords"])
        self.assertIn("pending/blocked/skipped", policy["continuousRecords"])
        self.assertIn("compact is native operation, not chat prompt", policy["compact"])
        self.assertIn("must not send compact or ROLE_CLOSEOUT text", policy["compact"])
        self.assertIn("if no compact tool is available, do nothing", policy["noCompactTool"])
        self.assertIn("role thread is still active/inProgress and must stop", policy["exceptionsOnly"])
        self.assertIn("no final protocol block exists", "\n".join(policy["exceptionsOnly"]))
        self.assertIn("compact/archive recovery anchor", "\n".join(policy["exceptionsOnly"]))
        self.assertIn("user explicitly asks", policy["exceptionsOnly"])
        self.assertIn("clear is not a default action", policy["clearArchiveNewThread"])
        self.assertIn("task family/permission/workspace boundary changes", policy["clearArchiveNewThread"])

    def test_protocol_contract_snapshot_includes_role_handoff_review_package_policy(self):
        policy = team_router.protocol_contract_snapshot()["roleHandoffReviewPackagePolicy"]

        self.assertIn("stable file/path handoff", policy["handoff"]["preferred"])
        self.assertIn("accumulated chat history", policy["handoff"]["preferred"])
        self.assertIn("taskId", policy["handoff"]["promptShape"])
        self.assertIn("explicit scope/files", policy["handoff"]["promptShape"])
        self.assertIn("expected marker", policy["handoff"]["promptShape"])
        self.assertIn("explicit protocol return format", policy["handoff"]["promptShape"])
        self.assertIn("exact executor delegation", policy["handoff"]["writeDelegation"])
        self.assertIn("executor write only inside that explicit scope", policy["handoff"]["writeDelegation"])
        self.assertIn("never authorizes manager direct edits", policy["handoff"]["writeDelegation"])
        self.assertIn("inline protocol blocks", policy["handoff"]["smallTasks"])
        self.assertIn("Team Router self changes", policy["handoff"]["highRisk"])
        self.assertIn("reviewer-gate/process/policy changes", policy["handoff"]["highRisk"])
        self.assertIn("shared workspace/path", policy["handoff"]["highRisk"])
        self.assertIn("inline protocol block fallback", policy["handoff"]["fallback"])
        self.assertIn("role-request free-text task content defaults to Chinese", policy["handoff"]["taskContentLanguage"])
        self.assertIn("protocol markers", policy["handoff"]["taskContentLanguage"])
        self.assertIn("commands, filenames, and tool names stay English/literal", policy["handoff"]["taskContentLanguage"])
        self.assertIn("protocol field names stay parser-compatible English", policy["handoff"]["callbackLanguage"])
        self.assertIn("summary, evidence, risks, and next content", policy["handoff"]["callbackLanguage"])
        self.assertIn("TEAM_ROUTER_CALLBACK", policy["handoff"]["callbackLanguage"])
        self.assertIn("executors, reviewers, and verifiers", policy["handoff"]["callbackLanguage"])
        self.assertIn("English-only templates", policy["handoff"]["callbackLanguage"])
        self.assertEqual(
            policy["reviewPackage"]["minimumContent"],
            [
                "taskId",
                "objective",
                "scope",
                "protocol marker references",
                "touched files",
                "accepted files when different from touched files",
                "behavior changes",
                "diff summary without full diff",
                "executor callback/report summary",
                "reviewer findings and requiredChanges when present",
                "verification evidence and actual commands/results",
                "excluded unrelated changes and untracked files",
                "risks",
                "remainingTodos",
            ],
        )
        self.assertEqual(
            policy["reviewPackage"]["defaultReviewPackagePath"],
            "docs/team-router/packages/<taskId>.md",
        )
        self.assertIn("durable project evidence", policy["reviewPackage"]["gitPolicy"])
        self.assertIn("must not be added to .gitignore", policy["reviewPackage"]["gitPolicy"])
        self.assertIn("does not apply to taskBriefPath", policy["reviewPackage"]["defaultPathScope"])
        self.assertIn("does not apply to executorReportPath", policy["reviewPackage"]["defaultPathScope"])
        self.assertIn("full diff", policy["reviewPackage"]["diffPolicy"])
        self.assertIn("must not include", policy["reviewPackage"]["diffPolicy"])
        self.assertIn("free-text fields default to Chinese", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("role-request task-content language", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("callback summary/evidence/risks/next content", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("field names", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("enum values", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("English classifier signals", policy["reviewPackage"]["languagePolicy"])
        self.assertIn(
            "Task Summary / 任务摘要",
            policy["reviewPackage"]["bilingualTemplateSections"],
        )
        self.assertIn(
            "Behavior Changes / 行为变化",
            policy["reviewPackage"]["bilingualTemplateSections"],
        )
        self.assertIn(
            "Diff Summary / Diff 摘要",
            policy["reviewPackage"]["bilingualTemplateSections"],
        )
        self.assertIn("focused diff/evidence", policy["reviewPackage"]["reviewerUse"])
        self.assertIn("parent chat history", policy["reviewPackage"]["reviewerUse"])
        self.assertIn("executor callback", policy["reviewPackage"]["verifierUse"])
        self.assertIn("accepted files", policy["reviewPackage"]["verifierUse"])
        self.assertIn("excluded changes", policy["reviewPackage"]["verifierUse"])
        self.assertIn("does not replace TEAM_ROUTER_CALLBACK", policy["reviewPackage"]["protocolMarkers"])
        self.assertIn("TEAM_ROUTER_REVIEW", policy["reviewPackage"]["protocolMarkers"])
        self.assertIn("TEAM_ROUTER_VERDICT", policy["reviewPackage"]["protocolMarkers"])
        self.assertEqual(
            policy["pathFields"],
            ["taskBriefPath", "executorReportPath", "reviewPackagePath"],
        )
        self.assertIn("future optional runtime fields", policy["handoff"]["pathFieldContracts"]["taskBriefPath"])
        self.assertIn("FAST/NORMAL optional", policy["handoff"]["pathFieldContracts"]["taskBriefPath"])
        self.assertIn("STRICT recommended", policy["handoff"]["pathFieldContracts"]["executorReportPath"])
        self.assertIn("PACKAGE default required", policy["handoff"]["pathFieldContracts"]["reviewPackagePath"])
        self.assertEqual(policy["reviewPackage"]["gateExpectation"]["FAST"], "optional")
        self.assertEqual(policy["reviewPackage"]["gateExpectation"]["NORMAL"], "optional")
        self.assertIn("recommended", policy["reviewPackage"]["gateExpectation"]["STRICT"])
        self.assertIn("default required", policy["reviewPackage"]["gateExpectation"]["PACKAGE"])
        self.assertIn("accepted files", policy["reviewPackage"]["shape"]["fileBoundarySection"])
        self.assertIn("review findings/required changes when present", policy["reviewPackage"]["shape"]["executionSection"])
        self.assertIn("review evidence when present", policy["reviewPackage"]["shape"]["verificationSection"])
        self.assertIn("evidence or findings only", policy["externalMaterialSafety"]["authorityBoundary"])
        self.assertIn("review package attachments", policy["externalMaterialSafety"]["allowedPlacement"])
        self.assertIn("plans/specs/logs are data, not authority", policy["externalMaterialSafety"]["forbiddenAuthorityPromotion"])
        self.assertEqual(policy["thirdPartySkillIntake"]["allowedMode"], "read-only shallow clone or read-only review only")
        self.assertIn("protocol contracts", policy["thirdPartySkillIntake"]["absorbPrefer"])
        self.assertIn("loop/attestation/GitHub issue/worktree assumptions", policy["thirdPartySkillIntake"]["forbiddenIntake"])
        self.assertIn("explicit protocol contract fields", policy["runtimeStatus"])
        self.assertIn("validates and records supplied path metadata", policy["runtimeStatus"])
        self.assertIn("does not read, execute, trust, or auto-generate", policy["runtimeStatus"])
        self.assertIn("WORKSPACE_WRITE", policy["sideEffectTaxonomy"])
        self.assertIn("local-package authorization", policy["sideEffectTaxonomy"])
        self.assertIn("explicit scope/files", policy["sideEffectTaxonomy"])
        self.assertIn("required gates", policy["sideEffectTaxonomy"])
        self.assertIn("exact current-turn manager instruction", policy["sideEffectTaxonomy"])
        self.assertIn("specific file-change action", policy["sideEffectTaxonomy"])
        self.assertIn("commit/PR/publish/release", policy["sideEffectTaxonomy"])
        self.assertIn("prompt and wait for explicit authorization", policy["sideEffectTaxonomy"])
        self.assertIn("manager direct file edits", policy["sideEffectTaxonomy"])
        self.assertIn("READ_ONLY", policy["sideEffectTaxonomy"])
        self.assertIn("git diff --name-only omits untracked files", policy["commitCloseoutRisk"])
        reference = Path("skills/codex-team-router/references/role-handoff-and-review-package.md").read_text(encoding="utf-8")
        self.assertIn("docs/team-router/packages/<taskId>.md", reference)
        self.assertIn("Task Summary / 任务摘要", reference)
        self.assertIn("Behavior Changes / 行为变化", reference)
        self.assertIn("Diff Summary / Diff 摘要", reference)
        self.assertIn("must not include a full diff", reference)
        self.assertIn("free-text fields default to Chinese", reference)
        self.assertIn("Task-content language: role-request free-text task content defaults to Chinese", reference)
        self.assertIn("Callback language: protocol field names stay parser-compatible English", reference)
        self.assertIn("`summary`, `evidence`, `risks`, and `next`", reference)
        self.assertIn("user does not understand English", reference)

class TestTeamRouterRegistryAndReadWindow(unittest.TestCase):
    def test_registry_path_uses_shared_state_root_not_worktree_root(self):
        with workspace_temp_dir() as td:
            base = Path(td)
            canonical = base / "repo"
            worktree = base / "repo-wt"
            canonical.mkdir()
            worktree.mkdir()
            a = team_router.resolve_state_root(worktree, canonical_root=canonical)
            b = team_router.resolve_state_root(canonical, canonical_root=canonical)
            self.assertEqual(a, b)
            self.assertEqual(
                team_router.registry_path(a, "project-123"),
                canonical / ".codex-team-router" / "projects" / "project-123" / "registry.json",
            )

    def test_state_root_rejects_codex_tmp(self):
        with workspace_temp_dir() as td:
            forbidden_root = Path(td) / ".codex-tmp" / "team-router"
            project_root = Path(td) / "repo"

            with self.assertRaises(team_router.StateStoreError):
                team_router.resolve_state_root(
                    project_root,
                    explicit_state_root=forbidden_root,
                )

    def test_state_root_rejects_windows_codex_tmp(self):
        with self.assertRaises(team_router.StateStoreError):
            team_router.resolve_state_root(
                r"D:\codex\repo",
                explicit_state_root=r"D:\.codex-tmp\team-router",
            )

    def test_read_window_without_time_or_message_id_is_unreachable(self):
        messages = [{"text": "summary only"}]
        anchor = {"messageId": None, "sentAt": "2026-06-22T00:00:00+08:00"}
        self.assertFalse(team_router.read_window_covers_anchor(messages, anchor))

    def test_read_window_compares_timestamp_offsets_by_instant(self):
        messages = [{"sentAt": "2026-06-22T00:30:00+09:00"}]
        anchor = {"messageId": None, "sentAt": "2026-06-21T23:45:00+08:00"}
        self.assertTrue(team_router.read_window_covers_anchor(messages, anchor))

    def test_observation_schema_requires_bounded_fields(self):
        obs = team_router.make_observation(
            "callback_raw",
            "executor",
            "thread-1",
            "2026-06-22T00:00:00+08:00",
            "TEAM_ROUTER_CALLBACK taskId=ctr-1",
            {"status": "done"},
        )
        self.assertEqual(obs["type"], "callback_raw")
        self.assertEqual(obs["parsedFields"]["status"], "done")

    def test_observation_rejects_oversized_content(self):
        with self.assertRaises(team_router.ProtocolError):
            team_router.make_observation(
                "callback_raw",
                "executor",
                "thread-1",
                "2026-06-22T00:00:00+08:00",
                "x" * (team_router.MAX_OBSERVATION_CONTENT_CHARS + 1),
                {"status": "done"},
            )


class TestTeamRouterJsonState(unittest.TestCase):
    def test_registry_v2_preserves_legacy_roles_and_adds_manager_pools(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"

            registry = team_router.load_registry(root, project_id)
            project = registry["projects"][project_id]

            self.assertEqual(registry["version"], 2)
            self.assertEqual(project["roles"], {})
            self.assertEqual(project["managerPools"], {})

    def test_registry_round_trip_normalizes_missing_fields(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            path = team_router.registry_path(root, project_id)
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps({
                    "projects": {
                        project_id: {
                            "roles": {
                                "manager": {"threadId": "thread-1"},
                            },
                        },
                    },
                }),
                encoding="utf-8",
            )

            registry = team_router.load_registry(root, project_id)

            self.assertEqual(registry["version"], 2)
            self.assertEqual(registry["stateRoot"], str(root.resolve()))
            project = registry["projects"][project_id]
            self.assertEqual(project["projectId"], project_id)
            self.assertEqual(project["roles"]["manager"]["threadId"], "thread-1")
            self.assertEqual(project["managerPools"], {})

            saved = team_router.save_registry(root, project_id, registry)
            self.assertEqual(saved, registry)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), registry)

    def test_task_ledger_round_trip_normalizes_missing_fields(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"
            path = team_router.task_path(root, project_id, task_id)
            path.parent.mkdir(parents=True)
            path.write_text('{"objective":"inspect docs"}', encoding="utf-8")

            ledger = team_router.load_task_ledger(root, project_id, task_id)

            self.assertEqual(ledger["version"], 2)
            self.assertEqual(ledger["workflowVersion"], 1)
            self.assertEqual(ledger["taskId"], task_id)
            self.assertEqual(ledger["projectId"], project_id)
            self.assertEqual(ledger["stateRoot"], str(root.resolve()))
            self.assertEqual(ledger["objective"], "inspect docs")
            self.assertEqual(ledger["status"], "created")
            self.assertEqual(ledger["reworkCount"], 0)
            self.assertEqual(ledger["maxRework"], 3)
            self.assertEqual(ledger["dispatches"], [])
            self.assertEqual(ledger["observations"], [])

            ledger["status"] = "awaiting_callback"
            team_router.save_task_ledger(root, project_id, task_id, ledger)
            self.assertEqual(
                team_router.load_task_ledger(root, project_id, task_id)["status"],
                "awaiting_callback",
            )

    def test_missing_workflow_version_is_legacy_and_v2_is_explicit(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            legacy = team_router.new_task_ledger(
                root,
                project_id,
                "legacy-task",
                objective="legacy",
                project_local_path=root,
            )
            self.assertEqual(team_router.task_workflow_version(legacy), 1)
            self.assertEqual(legacy["workflowVersion"], 1)

    def test_version_one_nonterminal_ledger_is_not_silently_upgraded(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "legacy-awaiting-plan"
            ledger = team_router.new_task_ledger(
                root,
                project_id,
                task_id,
                objective="legacy",
                project_local_path=root,
            )
            ledger["status"] = "awaiting_plan"
            team_router.save_task_ledger(root, project_id, task_id, ledger)

            reloaded = team_router.load_task_ledger(root, project_id, task_id)

            self.assertEqual(team_router.task_workflow_version(reloaded), 1)
            self.assertEqual(reloaded["status"], "awaiting_plan")

    def test_new_v2_task_ledger_is_explicit_and_keeps_v1_constructor_unchanged(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            resolved_plan = {
                "effectiveGateClass": "NORMAL",
                "routeRoles": ["executor"],
            }
            authorization_package = {
                "packageId": "auth-1",
                "status": "active",
            }

            ledger = team_router.new_v2_task_ledger(
                root,
                project_id,
                "v2-task",
                objective="delegated v2 task",
                project_local_path=root,
                parent_thread_id="parent-1",
                resolved_plan=resolved_plan,
                task_authorization_package=authorization_package,
                created_at="2026-07-11T20:00:00+08:00",
            )

            self.assertEqual(team_router.task_workflow_version(ledger), 2)
            self.assertEqual(ledger["status"], "planned")
            self.assertEqual(ledger["maxRework"], 1)
            self.assertEqual(ledger["parentThreadId"], "parent-1")
            self.assertEqual(ledger["plan"], resolved_plan)
            self.assertEqual(ledger["taskAuthorizationPackage"], authorization_package)
            self.assertIsNone(ledger["managerAcceptance"])
            self.assertEqual(ledger["modelUpgradeCount"], 0)

            legacy = team_router.new_task_ledger(
                root,
                project_id,
                "legacy-task",
                objective="legacy",
                project_local_path=root,
            )
            self.assertEqual(team_router.task_workflow_version(legacy), 1)

    def test_missing_task_ledger_raises_state_store_error(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"

            with self.assertRaises(team_router.StateStoreError) as caught:
                team_router.load_task_ledger(root, project_id, task_id)

            self.assertIn("missing JSON file", str(caught.exception))

    def test_new_task_ledger_rejects_invalid_inputs(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"

            invalid_calls = [
                {
                    "objective": "",
                    "project_local_path": ".",
                    "max_rework": 3,
                    "message": "objective must be a non-empty string",
                },
                {
                    "objective": object(),
                    "project_local_path": ".",
                    "max_rework": 3,
                    "message": "objective must be a non-empty string",
                },
                {
                    "objective": "inspect docs",
                    "project_local_path": ".",
                    "max_rework": True,
                    "message": "maxRework must be a non-negative integer",
                },
                {
                    "objective": "inspect docs",
                    "project_local_path": ".",
                    "max_rework": -1,
                    "message": "maxRework must be a non-negative integer",
                },
            ]
            for kwargs in invalid_calls:
                message = kwargs.pop("message")
                with self.subTest(message=message):
                    with self.assertRaises(team_router.StateStoreError) as caught:
                        team_router.new_task_ledger(
                            root,
                            project_id,
                            task_id,
                            **kwargs,
                        )
                    self.assertIn(message, str(caught.exception))

    def test_bad_registry_json_raises_state_store_error(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            path = team_router.registry_path(root, project_id)
            path.parent.mkdir(parents=True)
            path.write_text("{bad json", encoding="utf-8")

            with self.assertRaises(team_router.StateStoreError) as caught:
                team_router.load_registry(root, project_id)

            self.assertIn("invalid JSON", str(caught.exception))

    def test_bad_task_ledger_json_raises_state_store_error(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"
            path = team_router.task_path(root, project_id, task_id)
            path.parent.mkdir(parents=True)
            path.write_text("{bad json", encoding="utf-8")

            with self.assertRaises(team_router.StateStoreError) as caught:
                team_router.load_task_ledger(root, project_id, task_id)

            self.assertIn("invalid JSON", str(caught.exception))

    def test_task_ledger_read_permission_error_raises_state_store_error(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"

            with mock.patch.object(Path, "open", side_effect=PermissionError("denied")):
                with self.assertRaises(team_router.StateStoreError) as caught:
                    team_router.load_task_ledger(root, project_id, task_id)

            self.assertIn("cannot read JSON file", str(caught.exception))

    def test_atomic_save_leaves_no_temp_file(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"
            ledger = team_router.new_task_ledger(
                root,
                project_id,
                task_id,
                objective="inspect docs",
                project_local_path="D:\\codex\\codex-dynamic-workflow",
            )

            team_router.save_task_ledger(root, project_id, task_id, ledger)

            path = team_router.task_path(root, project_id, task_id)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), ledger)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_two_worktrees_share_registry_via_canonical_root(self):
        with workspace_temp_dir() as td:
            base = Path(td)
            canonical = base / "repo"
            worktree = base / "repo-wt"
            canonical.mkdir()
            worktree.mkdir()
            project_id = "project-123"
            state_a = team_router.resolve_state_root(worktree, canonical_root=canonical)
            state_b = team_router.resolve_state_root(canonical, canonical_root=canonical)
            self.assertEqual(state_a, state_b)

            registry = team_router.load_registry(state_a, project_id)
            registry["projects"][project_id]["roles"]["manager"] = {
                "threadId": "thread-1",
                "title": "TeamRouter manager - repo",
            }
            team_router.save_registry(state_a, project_id, registry)

            reloaded = team_router.load_registry(state_b, project_id)
            self.assertEqual(
                reloaded["projects"][project_id]["roles"]["manager"]["threadId"],
                "thread-1",
            )


class TestTeamRouterV2DynamicDispatch(unittest.TestCase):
    def setUp(self):
        self.td = workspace_temp_dir()
        self.root = Path(self.td.name) / "state"
        self.project_id = "project-1"
        self.target = {
            "type": "project",
            "projectId": self.project_id,
            "environment": {"type": "local"},
        }

    def tearDown(self):
        self.td.cleanup()

    def _save_task(self, task_id="task-1", *, parallel_allowed=False):
        ledger = team_router.new_v2_task_ledger(
            self.root,
            self.project_id,
            task_id,
            objective="成本感知路由",
            project_local_path=self.root,
            parent_thread_id="parent-1",
            resolved_plan={
                "routeRoles": ["executor", "verifier"],
                "parallelAllowed": parallel_allowed,
                "roleRouting": {
                    "executor": {"executionClass": "standard", "requestedModel": "gpt-5.6-terra", "requestedThinking": "medium"},
                    "verifier": {"executionClass": "mechanical", "requestedModel": "gpt-5.6-luna", "requestedThinking": "medium"},
                },
            },
            task_authorization_package={"packageId": "auth-1"},
            created_at="2026-07-11T20:00:00+08:00",
        )
        return team_router.save_task_ledger(self.root, self.project_id, task_id, ledger)

    def _send(self, adapter, *, task_id="task-1", request_id="request-1", **changes):
        request = {
            "parent_thread_id": "parent-1",
            "host_id": "local",
            "target": self.target,
            "role": "executor",
            "task_id": task_id,
            "request_id": request_id,
            "title": "执行者-成本感知路由",
            "prompt": "实现已确认的成本感知路由任务",
            "requested_model": "gpt-5.6-terra",
            "requested_thinking": "medium",
            "requested_at": "2026-07-11T20:00:00+08:00",
        }
        request.update(changes)
        return team_router.send_v2_role_request_with_adapter(
            adapter,
            self.root,
            self.project_id,
            **request,
        )

    def _reserve_intent(self, task_id="task-1", request_id="request-1", *, parallel_allowed=False):
        fingerprint = team_router.target_fingerprint_for(self.target, "local")
        team_router.reserve_role_or_creation_intent(
            self.root,
            self.project_id,
            parent_thread_id="parent-1",
            host_id="local",
            target_fingerprint=fingerprint,
            role="executor",
            task_id=task_id,
            request_id=request_id,
            claimed_at="2026-07-11T20:00:00+08:00",
            parallel_allowed=parallel_allowed,
        )
        return fingerprint

    def test_v2_rejects_unknown_model_override_before_authorization(self):
        with self.assertRaisesRegex(team_router.StateStoreError, "model_override_invalid"):
            team_router.resolve_role_model(
                "standard",
                model="gpt-5.6-unknown",
                thinking="medium",
                override_reason="requested for this task",
            )

    def test_v2_rejects_unknown_thinking_override_before_authorization(self):
        with self.assertRaisesRegex(team_router.StateStoreError, "model_override_invalid"):
            team_router.resolve_role_model(
                "standard",
                model="gpt-5.6-terra",
                thinking="unknown",
                override_reason="requested for this task",
            )

    def test_v2_override_reason_does_not_bypass_exact_authorization(self):
        authorization = team_router_v2.validate_model_routing_authorization(
            {
                "authorizedBy": "explicit_cost_aware_entry",
                "allowedDefaults": ["gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high"],
            },
            route_roles=("executor",),
        )
        resolved = team_router.resolve_role_model(
            "high", model="gpt-5.6-sol", thinking="high", override_reason="audit only",
        )

        self.assertFalse(team_router_v2._role_model_is_authorized(resolved, authorization, "executor"))

    def test_v2_rejects_ordinary_model_mismatch_before_any_side_effect(self):
        adapter = FakeThreadAdapter()
        self._save_task()
        ledger_before = json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True)
        registry_before = json.dumps(team_router.load_registry(self.root, self.project_id), sort_keys=True)

        with self.assertRaisesRegex(team_router.StateStoreError, "dispatch_model_mismatch"):
            self._send(adapter, requested_model="gpt-5.6-luna", requested_thinking="medium")

        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])
        self.assertEqual(adapter.renamed, [])
        self.assertEqual(json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True), ledger_before)
        self.assertEqual(json.dumps(team_router.load_registry(self.root, self.project_id), sort_keys=True), registry_before)

    def test_v2_rejects_pending_upgrade_mismatch_without_consuming_it(self):
        adapter = FakeThreadAdapter()
        ledger = self._save_task()
        ledger.update({
            "status": "needs_rework",
            "modelUpgradeCount": 1,
            "modelUpgradePending": True,
            "pendingModelUpgrade": {
                "parentThreadId": "parent-1", "role": "executor", "requestedModel": "gpt-5.6-sol",
                "requestedThinking": "high", "upgradedFrom": "gpt-5.6-terra", "completedResults": ["parsed registry"],
                "readFiles": ["src/team_router_state.py"], "exactFailure": "callback failure", "unresolved": ["claim ordering"],
            },
        })
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)
        ledger_before = json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True)
        registry_before = json.dumps(team_router.load_registry(self.root, self.project_id), sort_keys=True)

        with self.assertRaisesRegex(team_router.StateStoreError, "dispatch_model_mismatch"):
            self._send(adapter)

        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])
        self.assertEqual(adapter.renamed, [])
        self.assertEqual(json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True), ledger_before)
        self.assertEqual(json.dumps(team_router.load_registry(self.root, self.project_id), sort_keys=True), registry_before)

    def test_v2_send_records_router_owned_prepared_dispatch_then_acknowledges(self):
        adapter = FakeThreadAdapter()
        self._save_task()

        self._send(adapter)

        dispatch = team_router.load_task_ledger(self.root, self.project_id, "task-1")["dispatches"][-1]
        self.assertEqual(dispatch["protocolVersion"], 2)
        self.assertTrue(dispatch["dispatchId"])
        self.assertEqual(dispatch["requestId"], "request-1")
        self.assertEqual(dispatch["attempt"], 1)
        self.assertEqual(dispatch["deliveryStatus"], "acknowledged")
        self.assertEqual(dispatch["resultStatus"], "pending")

    def test_v2_send_exception_marks_prepared_dispatch_outcome_unknown_without_retry(self):
        adapter = FakeThreadAdapter()
        adapter.send_error = RuntimeError("send failed")
        self._save_task()

        result = self._send(adapter)

        self.assertEqual(result["outcome"], "tool_error")
        dispatches = team_router.load_task_ledger(self.root, self.project_id, "task-1")["dispatches"]
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(dispatches[0]["deliveryStatus"], "outcome_unknown")
        self.assertEqual(adapter.sent, [])

    def test_v2_startup_recovery_marks_prepared_dispatch_outcome_unknown(self):
        ledger = self._save_task()
        ledger["dispatches"].append({
            "role": "executor", "requestId": "request-1", "protocolVersion": 2,
            "dispatchId": "dispatch-1", "attempt": 1, "deliveryStatus": "prepared", "resultStatus": "pending",
        })
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)

        recovered = team_router.recover_v2_prepared_dispatches(
            self.root, self.project_id, "task-1", recovered_at="2026-07-11T20:01:00+08:00",
        )

        self.assertEqual(recovered["dispatches"][-1]["deliveryStatus"], "outcome_unknown")

    def test_v2_dispatch_attempt_is_monotonic_per_task_and_role(self):
        self._save_task()

        for request_id in ("request-1", "request-2"):
            team_router._prepare_v2_role_dispatch(
                self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
                request_id=request_id, thread_id="thread-executor", host_id="local", target_fingerprint="target-1",
                requested_model="gpt-5.6-terra", requested_thinking="medium",
                requested_at="2026-07-11T20:00:00+08:00", creation_accepted=False, binding="reused",
                model_override_reason=None, return_thread_id=None,
            )

        dispatches = team_router.load_task_ledger(self.root, self.project_id, "task-1")["dispatches"]
        self.assertEqual([item["attempt"] for item in dispatches], [1, 2])
        self.assertNotEqual(dispatches[0]["dispatchId"], dispatches[1]["dispatchId"])

    def test_v2_guarded_prepare_rechecks_model_after_early_preflight(self):
        adapter = FakeThreadAdapter()
        self._save_task()

        def stale_binding(*args, **kwargs):
            ledger = team_router.load_task_ledger(self.root, self.project_id, "task-1")
            plan = ledger.get("resolvedPlan") or ledger["plan"]
            plan["roleRouting"]["executor"] = {
                "executionClass": "standard", "requestedModel": "gpt-5.6-luna", "requestedThinking": "medium",
            }
            team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)
            return {"outcome": "reused", "threadId": "thread-executor", "targetFingerprint": kwargs["target_fingerprint"], "creationAccepted": False}

        with mock.patch.object(team_router, "resolve_or_create_v2_role_with_adapter", stale_binding):
            with self.assertRaisesRegex(team_router.StateStoreError, "dispatch_model_mismatch"):
                self._send(adapter)
        self.assertEqual(adapter.sent, [])
        self.assertEqual(team_router.load_task_ledger(self.root, self.project_id, "task-1")["dispatches"], [])

    def test_v2_terminal_pending_upgrade_is_consumed_in_prepared_transition(self):
        adapter = FakeThreadAdapter()
        adapter.send_error = RuntimeError("send failed")
        ledger = self._save_task()
        ledger.update({
            "status": "completed", "modelUpgradeCount": 1, "modelUpgradePending": True,
            "pendingModelUpgrade": {
                "parentThreadId": "parent-1", "role": "executor", "requestedModel": "gpt-5.6-sol",
                "requestedThinking": "high", "upgradedFrom": "gpt-5.6-terra", "completedResults": ["result"],
                "readFiles": ["src/team_router.py"], "exactFailure": "failure", "unresolved": ["edge"],
            },
        })
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)

        self._send(adapter, requested_model="gpt-5.6-sol", requested_thinking="high")

        saved = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        dispatch = saved["dispatches"][-1]
        self.assertEqual(saved["status"], "awaiting_callback")
        self.assertNotIn("pendingModelUpgrade", saved)
        self.assertNotIn("modelUpgradePending", saved)
        self.assertEqual(dispatch["attempt"], 1)
        self.assertTrue(dispatch["dispatchId"])
        self.assertEqual(dispatch["upgradedFrom"], "gpt-5.6-terra")
        self.assertEqual(dispatch["carryForward"]["exactFailure"], "failure")
        self.assertEqual(dispatch["deliveryStatus"], "outcome_unknown")

    def test_v2_adapter_send_runs_between_prepared_and_ack_locks(self):
        test = self
        calls = []

        class LockAwareAdapter(FakeThreadAdapter):
            def send_message_to_thread(self, **kwargs):
                self.assertFalse(team_router_state.task_path(test.root, test.project_id, "task-1").with_suffix(".dispatch.lock").exists())
                return super().send_message_to_thread(**kwargs)

        @contextmanager
        def counting_lock(*args, **kwargs):
            calls.append(kwargs["acquired_at"])
            with team_router_state.task_dispatch_lock(*args, **kwargs):
                yield

        self._save_task()
        with mock.patch.object(team_router, "task_dispatch_lock", counting_lock):
            self._send(LockAwareAdapter())
        self.assertEqual(len(calls), 2)

    def test_v2_result_consume_is_once_and_deduplicates_receipt_evidence(self):
        self._save_task()
        prepared, _ = team_router._prepare_v2_role_dispatch(
            self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
            request_id="request-1", thread_id="thread-executor", host_id="local", target_fingerprint="target",
            requested_model="gpt-5.6-terra", requested_thinking="medium", requested_at="2026-07-11T20:00:00+08:00",
            creation_accepted=False, binding="reused", model_override_reason=None, return_thread_id="parent-1",
        )

        first, consumed = team_router._consume_v2_dispatch_result(
            self.root, self.project_id, "task-1", dispatch=prepared, channel="manager-inbox", host_message_id="msg-1",
            captured_at="2026-07-11T20:01:00+08:00",
        )
        second, repeated = team_router._consume_v2_dispatch_result(
            self.root, self.project_id, "task-1", dispatch=prepared, channel="read_thread", host_message_id="msg-2",
            captured_at="2026-07-11T20:02:00+08:00",
        )
        _, duplicate = team_router._consume_v2_dispatch_result(
            self.root, self.project_id, "task-1", dispatch=prepared, channel="manager-inbox", host_message_id="msg-1",
            captured_at="2026-07-11T20:03:00+08:00",
        )

        self.assertTrue(consumed)
        self.assertFalse(repeated)
        self.assertFalse(duplicate)
        self.assertEqual(first["dispatches"][-1]["resultStatus"], "consumed")
        self.assertEqual(len(second["dispatches"][-1]["resultReceipts"]), 2)

    def test_v2_consume_rejects_old_strict_dispatch_after_newer_pending_attempt(self):
        self._save_task()
        first, _ = team_router._prepare_v2_role_dispatch(
            self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
            request_id="request-1", thread_id="thread-executor", host_id="local", target_fingerprint="target",
            requested_model="gpt-5.6-terra", requested_thinking="medium", requested_at="2026-07-11T20:00:00+08:00",
            creation_accepted=False, binding="reused", model_override_reason=None, return_thread_id="parent-1",
        )
        team_router._prepare_v2_role_dispatch(
            self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
            request_id="request-2", thread_id="thread-executor", host_id="local", target_fingerprint="target",
            requested_model="gpt-5.6-terra", requested_thinking="medium", requested_at="2026-07-11T20:01:00+08:00",
            creation_accepted=False, binding="reused", model_override_reason=None, return_thread_id="parent-1",
        )
        before = json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True)

        with self.assertRaisesRegex(team_router.StateStoreError, "dispatch_not_current"):
            team_router._consume_v2_dispatch_result(
                self.root, self.project_id, "task-1", dispatch=first, channel="read_thread",
                host_message_id="old-result", captured_at="2026-07-11T20:02:00+08:00",
            )

        self.assertEqual(
            json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True),
            before,
        )

    def test_v2_public_capture_rejects_strict_result_after_newer_legacy_dispatch(self):
        adapter = FakeThreadAdapter()
        self._save_task()
        sent = self._send(adapter)
        dispatch = sent["ledger"]["dispatches"][-1]
        adapter.append_reply(
            dispatch["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=task-1\nsourceThreadId: parent-1\n"
            "sourceRoleThreadId: thread-executor\nrole: Executor\nprotocolVersion: 2\n"
            "dispatchId: %s\nrequestId: request-1\nattempt: 1\nstatus: done\nfinal: true\n"
            "summary: stale strict result\nevidence: focused\nrisks: none\nnext: manager"
            % dispatch["dispatchId"],
            message_id="strict-result", sent_at="2026-07-11T20:01:00+08:00",
        )
        validate = team_router._validate_self_thread_fallback_receipt

        def append_newer_legacy(*args, **kwargs):
            malformed = validate(*args, **kwargs)
            ledger = team_router.load_task_ledger(self.root, self.project_id, "task-1")
            ledger["dispatches"].append({
                "role": "executor",
                "requestId": "legacy-request",
                "threadId": "thread-legacy",
                "dispatchAccepted": True,
            })
            team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)
            return malformed

        with mock.patch.object(
            team_router,
            "_validate_self_thread_fallback_receipt",
            side_effect=append_newer_legacy,
        ):
            with self.assertRaisesRegex(team_router.StateStoreError, "dispatch_not_current"):
                team_router.capture_executor_callback_from_read(
                    self.root,
                    self.project_id,
                    "task-1",
                    adapter.messages[dispatch["threadId"]],
                    captured_at="2026-07-11T20:02:00+08:00",
                )

        saved = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        self.assertEqual(saved["dispatches"][0]["resultStatus"], "pending")
        self.assertEqual(saved["dispatches"][0].get("resultReceipts", []), [])

    def test_v2_public_capture_route_failure_is_replayable_and_preserves_claim(self):
        adapter = FakeThreadAdapter()
        self._save_task()
        sent = self._send(adapter)
        dispatch = sent["ledger"]["dispatches"][-1]
        adapter.append_reply(
            dispatch["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=task-1\nsourceThreadId: parent-1\n"
            "sourceRoleThreadId: thread-executor\nrole: Executor\nprotocolVersion: 2\n"
            "dispatchId: %s\nrequestId: request-1\nattempt: 1\nstatus: done\nfinal: true\n"
            "summary: replay after repair\nevidence: focused\nrisks: none\nnext: manager"
            % dispatch["dispatchId"],
            message_id="strict-result", sent_at="2026-07-11T20:01:00+08:00",
        )

        with mock.patch.object(
            team_router,
            "next_v2_route_after_evidence",
            side_effect=team_router.StateStoreError("route_interrupted"),
        ):
            failed = team_router.capture_executor_callback_from_read(
                self.root,
                self.project_id,
                "task-1",
                adapter.messages[dispatch["threadId"]],
                captured_at="2026-07-11T20:02:00+08:00",
            )

        self.assertEqual(failed["status"], "awaiting_callback")
        self.assertEqual(failed["dispatches"][-1]["resultStatus"], "pending")
        self.assertEqual(failed["dispatches"][-1].get("resultReceipts", []), [])
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertEqual(pool["roles"]["executor"][0]["claim"]["requestId"], "request-1")

        def repaired_route(current, evidence):
            repaired = dict(current)
            repaired["status"] = "manager_acceptance_pending"
            return repaired

        with mock.patch.object(team_router, "next_v2_route_after_evidence", side_effect=repaired_route):
            repaired = team_router.capture_executor_callback_from_read(
                self.root,
                self.project_id,
                "task-1",
                adapter.messages[dispatch["threadId"]],
                captured_at="2026-07-11T20:03:00+08:00",
            )
        self.assertEqual(repaired["dispatches"][-1]["resultStatus"], "consumed")
        self.assertEqual(len(repaired["dispatches"][-1]["resultReceipts"]), 1)
        self.assertNotIn("routingError", repaired)
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertNotIn("claim", pool["roles"]["executor"][0])

    def test_v2_fallback_rejects_two_final_blocks_in_one_message(self):
        self._save_task()
        dispatch, _ = team_router._prepare_v2_role_dispatch(
            self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
            request_id="request-1", thread_id="thread-executor", host_id="local", target_fingerprint="target",
            requested_model="gpt-5.6-terra", requested_thinking="medium", requested_at="2026-07-11T20:00:00+08:00",
            creation_accepted=False, binding="reused", model_override_reason=None, return_thread_id="parent-1",
        )
        ledger = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        ledger["dispatches"][-1].update({
            "callbackDelivery": "direct-send",
            "roleThreadId": "thread-executor",
            "returnThreadId": "parent-1",
            "orchestratorThreadId": "parent-1",
            "fallbackSearchAnchor": {"messageId": "dispatch", "sentAt": "2026-07-11T20:00:00+08:00"},
        })
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)
        block = (
            "TEAM_ROUTER_CALLBACK taskId=task-1\nsourceThreadId: parent-1\n"
            "sourceRoleThreadId: thread-executor\nrole: Executor\nprotocolVersion: 2\n"
            "dispatchId: %s\nrequestId: request-1\nattempt: 1\nstatus: done\nfinal: true\n"
            "summary: %s\nevidence: focused\nrisks: none\nnext: manager"
        )
        saved = team_router.capture_executor_callback_from_read(
            self.root, self.project_id, "task-1",
            [
                {"messageId": "dispatch", "sentAt": "2026-07-11T20:00:00+08:00", "text": "TEAM_ROUTER_DISPATCH taskId=task-1"},
                {"messageId": "reply", "sentAt": "2026-07-11T20:01:00+08:00", "sourceThreadId": "thread-executor",
                 "text": "%s\n%s" % ((block % (dispatch["dispatchId"], "first")), (block % (dispatch["dispatchId"], "second")))},
            ],
            captured_at="2026-07-11T20:02:00+08:00",
        )
        self.assertEqual(saved["status"], "malformed_callback")
        self.assertEqual(saved["dispatches"][-1]["resultStatus"], "pending")
        self.assertNotIn("first", json.dumps(saved.get("observations", [])))
        self.assertNotIn("second", json.dumps(saved.get("observations", [])))

    def test_v2_executor_self_thread_fallback_rejects_invalid_strict_correlation_without_direct_return(self):
        self._save_task()
        dispatch, _ = team_router._prepare_v2_role_dispatch(
            self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
            request_id="request-1", thread_id="thread-executor", host_id="local", target_fingerprint="target",
            requested_model="gpt-5.6-terra", requested_thinking="medium", requested_at="2026-07-11T20:00:00+08:00",
            creation_accepted=False, binding="reused", model_override_reason=None, return_thread_id=None,
        )

        saved = team_router.capture_executor_callback_from_read(
            self.root, self.project_id, "task-1",
            [
                {"messageId": "dispatch", "sentAt": "2026-07-11T20:00:00+08:00", "text": "TEAM_ROUTER_DISPATCH taskId=task-1"},
                {
                    "messageId": "reply", "sentAt": "2026-07-11T20:01:00+08:00",
                    "sourceThreadId": "thread-executor",
                    "text": (
                        "TEAM_ROUTER_CALLBACK taskId=task-1\nsourceThreadId: parent-1\n"
                        "sourceRoleThreadId: thread-executor\nrole: Executor\nprotocolVersion: 1\n"
                        "dispatchId: wrong-dispatch\nstatus: done\nfinal: true\n"
                        "summary: invalid correlation\nevidence: focused\nrisks: none\nnext: manager"
                    ),
                },
            ],
            captured_at="2026-07-11T20:02:00+08:00",
        )

        self.assertEqual(saved["status"], "malformed_callback")
        self.assertEqual(saved["dispatches"][-1]["dispatchId"], dispatch["dispatchId"])
        self.assertEqual(saved["dispatches"][-1]["resultStatus"], "pending")
        self.assertNotIn("callbackReceipt", saved)
        self.assertFalse(any(item.get("type") == "callback_raw" for item in saved.get("observations", [])))

    def test_v2_legacy_self_thread_fallback_keeps_legacy_shape_but_rejects_strict_fields(self):
        adapter = FakeThreadAdapter()
        for mixed in (False, True):
            task_id = "task-legacy-mixed" if mixed else "task-legacy-clean"
            request_id = "request-legacy-mixed" if mixed else "request-legacy-clean"
            self._save_task(task_id=task_id)
            sent = self._send(adapter, task_id=task_id, request_id=request_id)
            dispatch = sent["ledger"]["dispatches"][-1]
            ledger = team_router.load_task_ledger(self.root, self.project_id, task_id)
            for field in ("protocolVersion", "dispatchId", "attempt", "deliveryStatus", "resultStatus"):
                ledger["dispatches"][-1].pop(field, None)
            team_router.save_task_ledger(self.root, self.project_id, task_id, ledger)

            callback = (
                "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\n"
                "summary: legacy result\nevidence: focused\nrisks: none\nnext: manager"
            ) % task_id
            if mixed:
                callback += (
                    "\nprotocolVersion: 2\ndispatchId: mixed-dispatch"
                    "\nrequestId: mixed-request\nattempt: 1"
                )
            adapter.append_reply(
                dispatch["threadId"],
                callback,
                message_id="legacy-result-%s" % ("mixed" if mixed else "clean"),
                sent_at="2026-07-11T20:02:00+08:00",
            )
            saved = team_router.capture_executor_callback_from_read(
                self.root,
                self.project_id,
                task_id,
                adapter.messages[dispatch["threadId"]],
                captured_at="2026-07-11T20:03:00+08:00",
            )
            if not mixed:
                self.assertIn("callbackReceipt", saved)
                self.assertNotIn("malformedDirectReturns", saved)
                continue
            self.assertEqual(saved["status"], "malformed_callback")
            error = saved["malformedDirectReturns"][-1]["error"]
            for field in ("protocolVersion", "dispatchId", "requestId", "attempt"):
                self.assertIn("%s is not accepted for a legacy dispatch" % field, error)
            self.assertNotIn("callbackReceipt", saved)

    def test_v2_late_ack_preserves_consumed_result(self):
        self._save_task()
        prepared, _ = team_router._prepare_v2_role_dispatch(
            self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
            request_id="request-1", thread_id="thread-executor", host_id="local", target_fingerprint="target",
            requested_model="gpt-5.6-terra", requested_thinking="medium", requested_at="2026-07-11T20:00:00+08:00",
            creation_accepted=False, binding="reused", model_override_reason=None, return_thread_id="parent-1",
        )
        team_router._consume_v2_dispatch_result(self.root, self.project_id, "task-1", dispatch=prepared, channel="read_thread", host_message_id="msg-result", captured_at="2026-07-11T20:01:00+08:00")

        saved = team_router._record_v2_role_dispatch(
            self.root, self.project_id, "task-1", role="executor", request_id="request-1", thread_id="thread-executor",
            host_id="local", target_fingerprint="target", requested_model="gpt-5.6-terra", requested_thinking="medium",
            requested_at="2026-07-11T20:00:00+08:00", creation_accepted=False, binding="reused",
            send_result={"message": {"id": "msg-ack", "createdAt": "2026-07-11T20:02:00+08:00"}},
            return_thread_id="parent-1", dispatch_id=prepared["dispatchId"],
        )

        self.assertEqual(saved["dispatches"][-1]["deliveryStatus"], "acknowledged")
        self.assertEqual(saved["dispatches"][-1]["resultStatus"], "consumed")

    def test_v2_complete_override_authorizes_only_its_exact_role_pair(self):
        authorization = team_router_v2.validate_model_routing_authorization(
            {
                "authorizedBy": "complete_per_request_override",
                "allowedDefaults": [],
                "allowedOverrides": [{"role": "executor", "model": "gpt-5.6-sol", "thinking": "high"}],
            },
            route_roles=("executor",),
        )
        resolved = team_router.resolve_role_model(
            "high",
            model="gpt-5.6-sol",
            thinking="high",
            override_reason="audit only",
        )

        self.assertTrue(team_router_v2._role_model_is_authorized(resolved, authorization, "executor"))
        self.assertFalse(team_router_v2._role_model_is_authorized(resolved, authorization, "verifier"))

    def test_v2_complete_multi_role_override_authorizes_each_exact_pair(self):
        authorization = team_router_v2.validate_model_routing_authorization(
            {
                "authorizedBy": "complete_per_request_override",
                "allowedDefaults": [],
                "allowedOverrides": [
                    {"role": "executor", "model": "gpt-5.6-sol", "thinking": "high"},
                    {"role": "verifier", "model": "gpt-5.6-luna", "thinking": "medium"},
                ],
            },
            route_roles=("executor", "verifier"),
        )

        self.assertTrue(team_router_v2._role_model_is_authorized(
            team_router.resolve_role_model("high", model="gpt-5.6-sol", thinking="high", override_reason="approved"),
            authorization, "executor",
        ))
        self.assertTrue(team_router_v2._role_model_is_authorized(
            team_router.resolve_role_model("mechanical", model="gpt-5.6-luna", thinking="medium", override_reason="approved"),
            authorization, "verifier",
        ))

    def test_v2_complete_override_rejects_unknown_duplicate_and_conflicting_entries(self):
        base = {
            "authorizedBy": "complete_per_request_override",
            "allowedDefaults": [],
            "allowedOverrides": [{"role": "executor", "model": "gpt-5.6-sol", "thinking": "high"}],
        }
        invalid = (
            {**base, "unexpected": True},
            {**base, "allowedOverrides": [{"role": "unknown", "model": "gpt-5.6-sol", "thinking": "high"}]},
            {**base, "allowedOverrides": base["allowedOverrides"] * 2},
            {**base, "allowedOverrides": base["allowedOverrides"] + [{"role": "executor", "model": "gpt-5.6-terra", "thinking": "medium"}]},
        )
        for authorization in invalid:
            with self.assertRaisesRegex(team_router.StateStoreError, "model_authorization_required"):
                team_router_v2.validate_model_routing_authorization(authorization, route_roles=("executor",))

    def test_v2_upgrade_requires_complete_route_override_authorization(self):
        ledger = self._save_task()
        ledger["taskAuthorizationPackage"]["modelRoutingAuthorization"] = {
            "authorizedBy": "complete_per_request_override",
            "allowedDefaults": [],
            "allowedOverrides": [{"role": "executor", "model": "gpt-5.6-sol", "thinking": "high"}],
        }
        ledger.update({
            "status": "tool_error",
            "dispatches": [{
                "role": "executor", "requestId": "request-1", "threadId": "thread-executor",
                "requestedModel": "gpt-5.6-terra", "requestedThinking": "medium",
                "dispatchAccepted": False, "failureReason": "callback failure",
            }],
        })
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)
        before = json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True)

        with self.assertRaisesRegex(team_router.StateStoreError, "model_authorization_required"):
            team_router.record_v2_model_upgrade(
                self.root, self.project_id, "task-1", parent_thread_id="parent-1", role="executor",
                failed_request_id="request-1", execution_class="high", model="gpt-5.6-sol", thinking="high",
                override_reason="approved recovery", completed_results=["parsed registry"],
                read_files=["src/team_router_state.py"], exact_failure="callback failed",
                unresolved=["claim ordering"], requested_at="2026-07-11T21:05:00+08:00",
            )
        self.assertEqual(json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True), before)

    def test_v2_executor_uses_luna_bootstrap_then_terra_dispatch_accepted(self):
        adapter = FakeThreadAdapter()
        self._save_task()
        result = self._send(adapter)

        self.assertEqual(result["outcome"], "sent")
        self.assertEqual(adapter.created[0]["kwargs"]["model"], "gpt-5.6-luna")
        self.assertEqual(adapter.created[0]["kwargs"]["thinking"], "medium")
        self.assertIn("requestId: request-1", adapter.created[0]["kwargs"]["prompt"])
        self.assertNotIn("hostId", adapter.created[0]["kwargs"])
        self.assertEqual(adapter.sent[0]["kwargs"]["model"], "gpt-5.6-terra")
        self.assertEqual(adapter.sent[0]["kwargs"]["thinking"], "medium")
        self.assertNotIn("hostId", adapter.sent[0]["kwargs"])
        self.assertNotIn("hostId", adapter.renamed[0])

    def test_v2_send_failure_preserves_claim_while_awaiting_late_callback(self):
        adapter = FakeThreadAdapter()
        adapter.send_error = RuntimeError("model rejected")
        self._save_task()
        result = self._send(adapter)

        self.assertEqual(result["outcome"], "tool_error")
        self.assertEqual(result["reason"], "model_unavailable")
        ledger = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        self.assertEqual(ledger["status"], "awaiting_callback")
        self.assertFalse(ledger["dispatches"][-1]["dispatchAccepted"])
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertEqual(pool["roles"]["executor"][0]["claim"]["taskId"], "task-1")
        self.assertEqual(pool["roles"]["executor"][0]["claim"]["requestId"], "request-1")

    def test_v2_creation_intent_recovery_binds_one_verified_bootstrap_identity_without_create(self):
        class RecoveryAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.read_calls = []

            def list_threads(self, **kwargs):
                self.listed = dict(kwargs)
                return {"threads": [{"threadId": "thread-recovered"}]}

            def read_thread(self, **kwargs):
                self.read_calls.append(dict(kwargs))
                return super().read_thread(**kwargs)

        adapter = RecoveryAdapter()
        self._save_task()
        fingerprint = self._reserve_intent()
        adapter.messages["thread-recovered"] = [{
            "text": team_router.make_v2_role_bootstrap_prompt(
                request_id="request-1",
                project_id=self.project_id,
                parent_thread_id="parent-1",
                role="executor",
            ),
        }]

        result = team_router.recover_v2_creation_intent_with_adapter(
            adapter,
            self.root,
            self.project_id,
            parent_thread_id="parent-1",
            host_id="local",
            target_fingerprint=fingerprint,
            role="executor",
            task_id="task-1",
            request_id="request-1",
            title="执行者-成本感知路由",
            observed_at="2026-07-11T20:00:01+08:00",
        )

        self.assertEqual((result["outcome"], result["threadId"]), ("recovered", "thread-recovered"))
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.listed, {"query": "request-1"})
        self.assertEqual(adapter.read_calls, [{"threadId": "thread-recovered", "hostId": "local"}])
        self.assertEqual(adapter.renamed[-1], {
            "threadId": "thread-recovered",
            "title": "执行者-成本感知路由",
        })

    def test_target_fingerprint_for_is_canonical_and_mismatch_fails_before_pool_mutation(self):
        equivalent = {
            "environment": {"type": "local"},
            "projectId": self.project_id,
            "type": "project",
        }
        fingerprint = team_router.target_fingerprint_for(self.target, "local")
        self.assertEqual(fingerprint, team_router.target_fingerprint_for(equivalent, "local"))
        self.assertNotEqual(fingerprint, team_router.target_fingerprint_for(self.target, "remote"))
        self.assertNotEqual(
            fingerprint,
            team_router.target_fingerprint_for({**self.target, "projectId": "project-2"}, "local"),
        )
        with self.assertRaises(team_router.StateStoreError):
            team_router.target_fingerprint_for({}, "local")
        with self.assertRaises(team_router.StateStoreError):
            team_router.target_fingerprint_for(self.target, "")

        adapter = FakeThreadAdapter()
        self._save_task()
        with self.assertRaisesRegex(team_router.StateStoreError, "target_fingerprint_mismatch"):
            self._send(adapter, target_fingerprint="wrong")
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])
        self.assertEqual(team_router.load_task_ledger(self.root, self.project_id, "task-1")["status"], "planned")

    def test_v2_reused_executor_refreshes_title_and_sends_explicit_model(self):
        adapter = FakeThreadAdapter()
        self._save_task()
        first = self._send(adapter)
        thread_id = first["threadId"]
        team_router.release_role_claim(
            self.root,
            self.project_id,
            parent_thread_id="parent-1",
            role="executor",
            thread_id=thread_id,
            task_id="task-1",
            request_id="request-1",
        )
        self._save_task("task-2")
        second = team_router.load_task_ledger(self.root, self.project_id, "task-2")
        second["plan"]["roleRouting"]["executor"].update(
            requestedModel="gpt-5.6-luna", requestedThinking="medium",
        )
        team_router.save_task_ledger(self.root, self.project_id, "task-2", second)

        reused = self._send(
            adapter,
            task_id="task-2",
            request_id="request-2",
            title="执行者-复用任务",
            requested_model="gpt-5.6-luna",
            requested_thinking="medium",
        )

        self.assertEqual((reused["outcome"], reused["binding"], reused["threadId"]), ("sent", "reused", thread_id))
        self.assertEqual(len(adapter.created), 1)
        self.assertEqual(adapter.sent[-1]["kwargs"]["model"], "gpt-5.6-luna")
        self.assertEqual(adapter.sent[-1]["kwargs"]["thinking"], "medium")
        self.assertEqual(adapter.renamed[-1], {"threadId": thread_id, "title": "执行者-复用任务"})
        self.assertEqual(
            team_router.load_task_ledger(self.root, self.project_id, "task-2")["dispatches"][-1]["binding"],
            "reused",
        )

    def test_v2_parallel_allowed_reaches_role_reservation(self):
        class ParallelAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.role_counts = {}

            def create_thread(self, **kwargs):
                result = super().create_thread(**kwargs)
                thread_id = result["threadId"]
                count = self.role_counts.get(thread_id, 0) + 1
                self.role_counts[thread_id] = count
                if count > 1:
                    unique_id = "%s-%s" % (thread_id, count)
                    self.messages[unique_id] = self.messages.pop(thread_id)
                    result["threadId"] = unique_id
                return result

        adapter = ParallelAdapter()
        self._save_task("task-1")
        self._send(adapter, task_id="task-1", request_id="request-1")
        self._save_task("task-2", parallel_allowed=False)
        blocked = self._send(adapter, task_id="task-2", request_id="request-2", parallel_allowed=True)
        self._save_task("task-3", parallel_allowed=True)
        parallel = self._send(adapter, task_id="task-3", request_id="request-3", parallel_allowed=True)
        self._save_task("task-4", parallel_allowed=True)
        inherited = self._send(adapter, task_id="task-4", request_id="request-4")

        self.assertEqual(blocked["outcome"], "busy")
        self.assertEqual((parallel["outcome"], parallel["binding"]), ("sent", "new"))
        self.assertEqual(inherited["outcome"], "busy")
        self.assertEqual(len(adapter.created), 2)
        self.assertNotEqual(adapter.created[0]["result"]["threadId"], adapter.created[1]["result"]["threadId"])
        self.assertTrue(adapter.renamed[-1]["title"].endswith(" #2"))

    def test_v2_non_executor_dispatch_uses_its_own_waiting_state(self):
        adapter = FakeThreadAdapter()
        self._save_task()

        result = self._send(
            adapter,
            role="verifier",
            title="验证者-成本感知路由",
            requested_model="gpt-5.6-luna",
            requested_thinking="medium",
        )

        self.assertEqual(result["outcome"], "sent")
        self.assertEqual(team_router.load_task_ledger(self.root, self.project_id, "task-1")["status"], "verifying")

    def test_dynamic_model_create_failure_records_rejected_creation_and_cleans_intent(self):
        adapter = FakeThreadAdapter()
        adapter.create_error = RuntimeError("model rejected")
        self._save_task()

        result = self._send(adapter)

        self.assertEqual((result["outcome"], result["reason"]), ("tool_error", "model_unavailable"))
        ledger = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        self.assertFalse(ledger["dispatches"][-1]["creationAccepted"])
        self.assertFalse(ledger["dispatches"][-1]["dispatchAccepted"])
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertEqual(pool["creationIntents"], [])

    def test_create_timeout_recovers_server_created_thread_without_retrying_create(self):
        class TimeoutAfterCreateAdapter(FakeThreadAdapter):
            def create_thread(self, **kwargs):
                created = super().create_thread(**kwargs)
                self.messages[created["threadId"]].append({"text": kwargs["prompt"]})
                raise TimeoutError("create_thread timed out")

            def list_threads(self, **kwargs):
                return {"threads": [{"threadId": thread_id} for thread_id in self.messages]}

        adapter = TimeoutAfterCreateAdapter()
        self._save_task()

        result = self._send(adapter)

        self.assertEqual((result["outcome"], result["threadId"]), ("sent", "thread-executor"))
        self.assertEqual(len(adapter.created), 1)
        self.assertEqual(len(adapter.sent), 1)
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertEqual(pool["creationIntents"], [])

    def test_v2_model_upgrade_is_once_only_and_receipt_is_requested_only(self):
        ledger = self._save_task()
        ledger["taskAuthorizationPackage"]["modelRoutingAuthorization"] = {
            "authorizedBy": "explicit_cost_aware_entry",
            "allowedDefaults": [
                "gpt-5.6-luna:medium",
                "gpt-5.6-terra:medium",
                "gpt-5.6-sol:high",
            ],
        }
        ledger.update({
            "status": "tool_error",
            "dispatches": [{
                "role": "executor",
                "requestId": "request-1",
                "threadId": "thread-executor",
                "binding": "reused",
                "requestedModel": "gpt-5.6-terra",
                "requestedThinking": "medium",
                "dispatchAccepted": False,
                "failureReason": "callback failure",
            }],
        })
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)

        upgraded = team_router.record_v2_model_upgrade(
            self.root,
            self.project_id,
            "task-1",
            parent_thread_id="parent-1",
            role="executor",
            failed_request_id="request-1",
            execution_class="high",
            completed_results=["parsed existing registry"],
            read_files=["src/team_router_state.py"],
            exact_failure="Terra callback could not resolve the concurrency invariant",
            unresolved=["prove claim release ordering"],
            requested_at="2026-07-11T21:05:00+08:00",
        )

        self.assertEqual(upgraded["modelUpgradeCount"], 1)
        self.assertEqual(upgraded["status"], "needs_rework")
        self.assertEqual(upgraded["pendingModelUpgrade"]["requestedModel"], "gpt-5.6-sol")
        self.assertEqual(upgraded["pendingModelUpgrade"]["upgradedFrom"], "gpt-5.6-terra")
        receipt = team_router.build_v2_routing_receipt(upgraded)
        self.assertEqual(receipt["roles"][0]["requestedModel"], "gpt-5.6-terra")
        self.assertFalse(receipt["solUltraDispatched"])
        self.assertNotIn("actualModel", str(receipt))
        self.assertNotIn("cost", str(receipt).lower())
        self.assertNotIn("token", str(receipt).lower())

        blocked = team_router.record_v2_model_upgrade(
            self.root,
            self.project_id,
            "task-1",
            parent_thread_id="parent-1",
            role="executor",
            failed_request_id="request-1",
            execution_class="high",
            completed_results=["parsed existing registry"],
            read_files=["src/team_router_state.py"],
            exact_failure="same failure",
            unresolved=["same unresolved work"],
            requested_at="2026-07-11T21:06:00+08:00",
        )
        self.assertEqual((blocked["status"], blocked["reason"]), ("blocked", "model_upgrade_limit"))

    def test_v2_pending_model_upgrade_consumes_once_and_prefers_failed_thread(self):
        adapter = FakeThreadAdapter()
        ledger = self._save_task()
        ledger["taskAuthorizationPackage"]["modelRoutingAuthorization"] = {
            "authorizedBy": "explicit_cost_aware_entry",
            "allowedDefaults": [
                "gpt-5.6-luna:medium",
                "gpt-5.6-terra:medium",
                "gpt-5.6-sol:high",
            ],
        }
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)
        first = self._send(adapter)
        team_router.release_role_claim(
            self.root,
            self.project_id,
            parent_thread_id="parent-1",
            role="executor",
            thread_id=first["threadId"],
            task_id="task-1",
            request_id="request-1",
        )
        failed = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        failed["status"] = "tool_error"
        failed["dispatches"][-1]["failureReason"] = "callback failure"
        team_router.save_task_ledger(self.root, self.project_id, "task-1", failed)
        team_router.record_v2_model_upgrade(
            self.root,
            self.project_id,
            "task-1",
            parent_thread_id="parent-1",
            role="executor",
            failed_request_id="request-1",
            execution_class="high",
            completed_results=["parsed registry"],
            read_files=["src/team_router_state.py"],
            exact_failure="Terra could not prove the invariant",
            unresolved=["prove claim release ordering"],
            requested_at="2026-07-11T21:05:00+08:00",
        )

        consumed = self._send(
            adapter,
            request_id="request-2",
            requested_model="gpt-5.6-sol",
            requested_thinking="high",
        )

        self.assertEqual((consumed["outcome"], consumed["threadId"]), ("sent", first["threadId"]))
        self.assertEqual(adapter.sent[-1]["kwargs"]["model"], "gpt-5.6-sol")
        self.assertEqual(adapter.sent[-1]["kwargs"]["thinking"], "high")
        saved = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        self.assertEqual(saved["dispatches"][-1]["upgradedFrom"], "gpt-5.6-terra")
        self.assertNotIn("pendingModelUpgrade", saved)
        self.assertEqual(saved["modelUpgradeCount"], 1)

    def test_v2_model_upgrade_rejects_success_or_sol_ultra_before_save(self):
        ledger = self._save_task()
        ledger["taskAuthorizationPackage"]["modelRoutingAuthorization"] = {
            "authorizedBy": "explicit_cost_aware_entry",
            "allowedDefaults": [
                "gpt-5.6-luna:medium",
                "gpt-5.6-terra:medium",
                "gpt-5.6-sol:high",
            ],
        }
        ledger["dispatches"] = [{
            "role": "executor", "requestId": "request-1", "threadId": "thread-executor",
            "requestedModel": "gpt-5.6-terra", "requestedThinking": "medium", "dispatchAccepted": True,
        }]
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)
        kwargs = {
            "parent_thread_id": "parent-1", "role": "executor", "failed_request_id": "request-1",
            "execution_class": "high", "completed_results": ["parsed registry"],
            "read_files": ["src/team_router_state.py"], "exact_failure": "could not prove invariant",
            "unresolved": ["claim ordering"], "requested_at": "2026-07-11T21:05:00+08:00",
        }
        with self.assertRaisesRegex(team_router.StateStoreError, "latest request is not failed"):
            team_router.record_v2_model_upgrade(self.root, self.project_id, "task-1", **kwargs)

        failed = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        failed["dispatches"][-1].update(dispatchAccepted=False, failureReason="callback failure")
        team_router.save_task_ledger(self.root, self.project_id, "task-1", failed)
        before = json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True)
        with self.assertRaisesRegex(team_router.StateStoreError, "model_forbidden"):
            team_router.record_v2_model_upgrade(
                self.root,
                self.project_id,
                "task-1",
                model="gpt-5.6-sol",
                thinking="ultra",
                override_reason="forbidden",
                **kwargs,
            )
        after = json.dumps(team_router.load_task_ledger(self.root, self.project_id, "task-1"), sort_keys=True)
        self.assertEqual(after, before)

    def test_v2_resolved_model_override_reason_reaches_routing_receipt(self):
        adapter = FakeThreadAdapter()
        ledger = self._save_task()
        ledger["plan"] = {
            **ledger["plan"],
            "roleRouting": {
                "executor": {
                    "executionClass": "standard",
                    "requestedModel": "gpt-5.6-terra",
                    "requestedThinking": "medium",
                    "modelOverrideReason": "fixed host regression reproduction",
                },
            },
        }
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)

        self._send(adapter)
        receipt = team_router.build_v2_routing_receipt(
            team_router.load_task_ledger(self.root, self.project_id, "task-1"),
        )

        self.assertEqual(receipt["roles"][-1]["modelOverrideReason"], "fixed host regression reproduction")

    def test_v2_title_failure_releases_new_role_claim(self):
        class TitleFailureAdapter(FakeThreadAdapter):
            def set_thread_title(self, **kwargs):
                raise RuntimeError("title transport unavailable")

        adapter = TitleFailureAdapter()
        self._save_task()

        result = self._send(adapter)

        self.assertEqual((result["outcome"], result["reason"]), ("tool_error", "thread_tool_error"))
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertNotIn("claim", pool["roles"]["executor"][0])
        self.assertEqual(team_router.load_task_ledger(self.root, self.project_id, "task-1")["status"], "tool_error")

    def test_sol_ultra_is_forbidden_before_adapter_dispatch(self):
        adapter = FakeThreadAdapter()
        ledger = self._save_task()
        ledger["plan"]["roleRouting"]["executor"].update(
            requestedModel="gpt-5.6-sol", requestedThinking="ultra",
        )
        team_router.save_task_ledger(self.root, self.project_id, "task-1", ledger)

        result = self._send(
            adapter,
            requested_model=" gpt-5.6-sol ",
            requested_thinking=" ultra ",
        )

        self.assertEqual((result["outcome"], result["reason"]), ("tool_error", "model_forbidden"))
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])
        ledger = team_router.load_task_ledger(self.root, self.project_id, "task-1")
        self.assertFalse(ledger["dispatches"][-1]["dispatchAccepted"])
        self.assertEqual(ledger["dispatches"][-1]["requestedModel"], "gpt-5.6-sol")

    def test_creation_intent_recovery_zero_multiple_or_mismatched_candidates_never_create(self):
        class RecoveryAdapter(FakeThreadAdapter):
            def __init__(self, candidates, messages):
                super().__init__()
                self.candidates = candidates
                self.messages.update(messages)

            def list_threads(self, **kwargs):
                return {"threads": [{"threadId": thread_id} for thread_id in self.candidates]}

        valid = lambda request_id: team_router.make_v2_role_bootstrap_prompt(
            request_id=request_id,
            project_id=self.project_id,
            parent_thread_id="parent-1",
            role="executor",
        )
        cases = (
            ("zero", (), {}),
            ("multiple", ("thread-a", "thread-b"), {
                "thread-a": [{"text": valid("request-multiple")}],
                "thread-b": [{"text": valid("request-multiple")}],
            }),
            ("mismatch", ("thread-wrong",), {
                "thread-wrong": [{"text": valid("request-other")}],
            }),
        )
        for name, candidates, messages in cases:
            with self.subTest(name=name):
                self.root = Path(self.td.name) / ("state-" + name)
                task_id, request_id = "task-%s" % name, "request-%s" % name
                self._save_task(task_id, parallel_allowed=True)
                adapter = RecoveryAdapter(candidates, messages)
                self._reserve_intent(task_id, request_id, parallel_allowed=True)

                result = team_router.resolve_or_create_v2_role_with_adapter(
                    adapter,
                    self.root,
                    self.project_id,
                    parent_thread_id="parent-1",
                    host_id="local",
                    target=self.target,
                    role="executor",
                    task_id=task_id,
                    request_id=request_id,
                    title="执行者-恢复测试",
                    requested_at="2026-07-11T20:00:01+08:00",
                )

                self.assertEqual((result["outcome"], result["reason"]), ("creation_outcome_unknown", "creation_outcome_unknown"))
                self.assertEqual(adapter.created, [])
                ledger = team_router.load_task_ledger(self.root, self.project_id, task_id)
                self.assertEqual(ledger["status"], "creation_outcome_unknown")
                pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
                self.assertIn(request_id, [item["requestId"] for item in pool["creationIntents"]])
                self.assertTrue(any(
                    item.get("parsedFields", {}).get("reason") == "creation_outcome_unknown"
                    for item in ledger["observations"]
                ))

    def test_creation_intent_recovery_missing_thread_tools_fails_closed_without_create(self):
        adapter = FakeThreadAdapter()
        self._save_task()
        self._reserve_intent()

        result = team_router.resolve_or_create_v2_role_with_adapter(
            adapter,
            self.root,
            self.project_id,
            parent_thread_id="parent-1",
            host_id="local",
            target=self.target,
            role="executor",
            task_id="task-1",
            request_id="request-1",
            title="执行者-恢复测试",
            requested_at="2026-07-11T20:00:01+08:00",
        )

        self.assertEqual((result["outcome"], result["reason"]), ("tool_error", "thread_tool_error"))
        self.assertEqual(adapter.created, [])

    def test_v2_dispatch_has_no_native_spawn_agent_fallback(self):
        source = Path(team_router.__file__).read_text(encoding="utf-8")
        self.assertNotIn("spawn_agent", source)


class TestTeamRouterV2ManagerAcceptance(unittest.TestCase):
    def setUp(self):
        self.td = workspace_temp_dir()
        self.root = Path(self.td.name) / "state"
        self.project_id = "project-v2-acceptance"
        self.task_id = "task-v2-acceptance"
        self.parent_thread_id = "parent-v2-acceptance"

    def tearDown(self):
        self.td.cleanup()

    def _save_awaiting_acceptance(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-v2-acceptance",
            task_id=self.task_id,
            parent_thread_id=self.parent_thread_id,
            objective="implement a narrow local fix",
            scope="src/example.py only",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-11T21:00:00+08:00",
            model_routing_authorization={
                "authorizedBy": "explicit_cost_aware_entry",
                "allowedDefaults": [
                    "gpt-5.6-luna:medium",
                    "gpt-5.6-terra:medium",
                    "gpt-5.6-sol:high",
                ],
            },
        )
        plan = team_router.resolve_v2_manager_plan(
            objective=package["objective"],
            scope=package["scope"],
            permission=package["permission"],
            stop_condition=package["stopCondition"],
            requested_gate_class="NORMAL",
            authorization_package=package,
            explicit_roles=("executor",),
            requested_role_routing={"executor": {"executionClass": "standard"}},
            ledger_input={"taskId": self.task_id, "parentThreadId": self.parent_thread_id},
        )
        ledger = team_router.new_v2_task_ledger(
            self.root,
            self.project_id,
            self.task_id,
            objective=package["objective"],
            project_local_path=self.root,
            parent_thread_id=self.parent_thread_id,
            resolved_plan=plan,
            task_authorization_package=package,
            created_at="2026-07-11T21:00:00+08:00",
        )
        ledger.update({
            "status": "manager_acceptance_pending",
            "dispatches": [{
                "role": "executor",
                "requestId": "request-1",
                "threadId": "thread-executor",
                "binding": "reused",
                "requestedModel": "gpt-5.6-terra",
                "requestedThinking": "medium",
                "dispatchAccepted": True,
            }],
            "observations": [{
                "type": "callback_raw",
                "role": "executor",
                "threadId": "thread-executor",
                "parsedFields": {"status": "done", "final": "true", "summary": "focused test passed"},
            }],
        })
        return team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

    def _capture_executor_callback(self, ledger, *, risks):
        ledger = dict(ledger)
        dispatch = dict(ledger["dispatches"][-1])
        dispatch.update({
            "messageId": "msg-executor-dispatch",
            "sentAt": "2026-07-11T21:00:30+08:00",
            "searchAnchor": {"messageId": "msg-executor-dispatch", "sentAt": "2026-07-11T21:00:30+08:00"},
        })
        ledger["dispatches"] = [dispatch]
        ledger["status"] = "awaiting_callback"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        return team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-executor-dispatch", "sentAt": "2026-07-11T21:00:30+08:00", "text": "dispatch"},
                {"messageId": "msg-executor-callback", "sentAt": "2026-07-11T21:00:45+08:00", "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: focused fix done\n"
                    "evidence: 1 focused test OK\nrisks: %s\nnext: manager"
                ) % (self.task_id, risks)},
            ],
            captured_at="2026-07-11T21:01:00+08:00",
        )

    def test_v2_normal_executor_callback_manager_acceptance_can_finish(self):
        self._save_awaiting_acceptance()

        accepted = team_router.record_manager_acceptance(
            self.root,
            self.project_id,
            self.task_id,
            result="pass",
            accepted_at="2026-07-11T21:01:00+08:00",
            callback_receipt="direct-send",
            scope_checked="src/example.py",
            evidence_checked="1 focused test OK",
            risk_boundary_checked="FAST/NORMAL",
            remaining_risks="none",
        )

        self.assertEqual(accepted["status"], "done")
        self.assertEqual(accepted["managerAcceptance"]["result"], "pass")
        self.assertEqual(accepted["closeout"]["acceptedBy"], "manager")
        self.assertEqual(accepted["closeout"]["watcherAction"], "stop_and_delete_heartbeat")

    def test_v2_manager_acceptance_rework_releases_executor_claim(self):
        self._save_awaiting_acceptance()
        team_router.reserve_role_or_creation_intent(
            self.root,
            self.project_id,
            parent_thread_id=self.parent_thread_id,
            host_id="local",
            target_fingerprint="target-v2-acceptance",
            role="executor",
            task_id=self.task_id,
            request_id="request-1",
            claimed_at="2026-07-11T21:00:00+08:00",
        )
        team_router.finalize_created_role(
            self.root,
            self.project_id,
            parent_thread_id=self.parent_thread_id,
            role="executor",
            request_id="request-1",
            thread_id="thread-executor",
            title="执行者-局部修复",
            created_at="2026-07-11T21:00:01+08:00",
        )

        rework = team_router.record_manager_acceptance(
            self.root,
            self.project_id,
            self.task_id,
            result="needs_rework",
            accepted_at="2026-07-11T21:01:00+08:00",
            callback_receipt="direct-send",
            scope_checked="src/example.py",
            evidence_checked="1 focused test OK",
            risk_boundary_checked="FAST/NORMAL",
            remaining_risks="one narrow follow-up",
        )

        self.assertEqual((rework["status"], rework["reworkCount"]), ("dispatched", 1))
        self.assertEqual(rework["preferredThreadId"], "thread-executor")
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertNotIn("claim", pool["roles"]["executor"][0])

    def test_v2_callback_risk_escalation_without_candidates_waits_for_manager_routing(self):
        ledger = self._save_awaiting_acceptance()
        updated = self._capture_executor_callback(ledger, risks="strict protocol risk")

        self.assertEqual(updated["status"], "manager_routing_pending")
        self.assertEqual(updated["routingError"]["reason"], "plan_invalid")

    def test_v2_executor_callback_enters_manager_acceptance(self):
        updated = self._capture_executor_callback(self._save_awaiting_acceptance(), risks="none")

        self.assertEqual(updated["status"], "manager_acceptance_pending")
        self.assertEqual(updated["observations"][-1]["type"], "v2_route_reclassified")

    def test_v2_executor_callback_risk_escalation_uses_preserved_candidate_routing(self):
        ledger = self._save_awaiting_acceptance()
        ledger["plan"] = dict(ledger["plan"])
        ledger["plan"]["candidateRoleRouting"] = {
            "executor": {"executionClass": "standard"},
            "reviewer": {"executionClass": "high", "requestedModel": "gpt-5.6-sol", "requestedThinking": "high"},
            "verifier": {"executionClass": "mechanical", "requestedModel": "gpt-5.6-luna", "requestedThinking": "medium"},
        }
        updated = self._capture_executor_callback(ledger, risks="strict protocol risk")

        self.assertEqual(updated["status"], "reviewing")
        self.assertEqual(tuple(updated["plan"]["routeRoles"]), ("executor", "reviewer", "verifier"))

    def test_v2_callback_missing_routing_releases_final_executor_claim_without_terminal_block(self):
        ledger = self._save_awaiting_acceptance()
        team_router.reserve_role_or_creation_intent(
            self.root,
            self.project_id,
            parent_thread_id=self.parent_thread_id,
            host_id="local",
            target_fingerprint="target-v2-acceptance",
            role="executor",
            task_id=self.task_id,
            request_id="request-1",
            claimed_at="2026-07-11T21:00:00+08:00",
        )
        team_router.finalize_created_role(
            self.root,
            self.project_id,
            parent_thread_id=self.parent_thread_id,
            role="executor",
            request_id="request-1",
            thread_id="thread-executor",
            title="执行者-局部修复",
            created_at="2026-07-11T21:00:01+08:00",
        )

        updated = self._capture_executor_callback(ledger, risks="strict protocol risk")

        self.assertEqual(updated["status"], "manager_routing_pending")
        self.assertEqual(updated["routingError"]["reason"], "plan_invalid")
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertNotIn("claim", pool["roles"]["executor"][0])

    def test_v2_closeout_parity_manager_and_verifier_share_receipt_and_format_pool_only(self):
        self._save_awaiting_acceptance()
        manager_done = team_router.record_manager_acceptance(
            self.root,
            self.project_id,
            self.task_id,
            result="pass",
            accepted_at="2026-07-11T21:01:00+08:00",
            callback_receipt="direct-send",
            scope_checked="src/example.py",
            evidence_checked="1 focused test OK",
            risk_boundary_checked="FAST/NORMAL",
            remaining_risks="none",
        )

        verifier = self._save_awaiting_acceptance()
        verifier.update({
            "status": "verifying",
            "verification": {"request": {
                "role": "verifier", "threadId": "thread-verifier", "messageId": "msg-verify",
                "sentAt": "2026-07-11T21:02:00+08:00",
                "searchAnchor": {"messageId": "msg-verify", "sentAt": "2026-07-11T21:02:00+08:00"},
                "expectedCallback": "TEAM_ROUTER_VERDICT taskId=%s" % self.task_id,
            }},
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, verifier)
        verifier_done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-verify", "sentAt": "2026-07-11T21:02:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-07-11T21:03:00+08:00", "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: verifier pass\n"
                    "requiredChanges: none\nevidenceChecked: 1 focused test OK\nrisks: none"
                ) % self.task_id},
            ],
            captured_at="2026-07-11T21:04:00+08:00",
        )

        self.assertEqual(manager_done["closeout"]["routingReceipt"], verifier_done["closeout"]["routingReceipt"])
        self.assertEqual(verifier_done["closeout"]["acceptedBy"], "verifier")
        self.assertEqual(verifier_done["closeout"]["watcherAction"], "stop_and_delete_heartbeat")
        registry = {
            "projects": {
                self.project_id: {
                    "roles": {"manager": {"threadId": "legacy-manager"}},
                    "managerPools": {
                        self.parent_thread_id: {"roles": {"executor": [{"threadId": "thread-executor"}] }},
                        "other-parent": {"roles": {"executor": [{"threadId": "other-thread"}] }},
                    },
                },
            },
        }
        rendered = team_router.format_closeout_for_user(verifier_done, registry)
        self.assertIn("executor: thread-executor", rendered)
        self.assertNotIn("other-thread", rendered)
        self.assertIn("acceptedBy: verifier", rendered)
        self.assertIn("routingReceipt:", rendered)

        legacy = {
            "projectId": self.project_id,
            "taskId": "legacy-task",
            "status": "done",
            "closeout": {"summary": "legacy", "evidenceChecked": "tests", "risks": "none", "nextAction": "none"},
        }
        legacy_rendered = team_router.format_closeout_for_user(legacy, registry)
        self.assertNotIn("acceptedBy:", legacy_rendered)
        self.assertNotIn("routingReceipt:", legacy_rendered)

    def test_v2_blocked_manager_closeout_stops_heartbeat(self):
        self._save_awaiting_acceptance()
        blocked = team_router.record_manager_acceptance(
            self.root,
            self.project_id,
            self.task_id,
            result="blocked",
            accepted_at="2026-07-11T21:01:00+08:00",
            callback_receipt="direct-send",
            scope_checked="src/example.py",
            evidence_checked="1 focused test OK",
            risk_boundary_checked="FAST/NORMAL",
            remaining_risks="blocked by host",
        )
        self.assertEqual((blocked["status"], blocked["closeout"]["watcherAction"]), ("blocked", "stop_and_delete_heartbeat"))

    def test_v2_second_automatic_rework_blocks_and_stops_heartbeat(self):
        self._save_awaiting_acceptance()
        first = team_router.record_manager_acceptance(
            self.root, self.project_id, self.task_id,
            result="needs_rework", accepted_at="2026-07-11T21:01:00+08:00",
            callback_receipt="direct-send", scope_checked="src/example.py",
            evidence_checked="1 focused test OK", risk_boundary_checked="FAST/NORMAL",
            remaining_risks="one narrow follow-up",
        )
        first["status"] = "manager_acceptance_pending"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, first)

        blocked = team_router.record_manager_acceptance(
            self.root, self.project_id, self.task_id,
            result="needs_rework", accepted_at="2026-07-11T21:02:00+08:00",
            callback_receipt="direct-send", scope_checked="src/example.py",
            evidence_checked="1 focused test OK", risk_boundary_checked="FAST/NORMAL",
            remaining_risks="still unresolved",
        )

        self.assertEqual((blocked["status"], blocked["reworkCount"]), ("blocked", 1))
        self.assertEqual(blocked["closeout"]["watcherAction"], "stop_and_delete_heartbeat")

    def test_v2_verifier_rework_releases_final_verifier_claim(self):
        ledger = self._save_awaiting_acceptance()
        ledger.update({
            "status": "verifying",
            "dispatches": [
                *ledger["dispatches"],
                {
                    "role": "verifier", "requestId": "verifier-request-1", "threadId": "thread-verifier",
                    "requestedModel": "gpt-5.6-luna", "requestedThinking": "medium", "dispatchAccepted": True,
                },
            ],
            "verification": {"request": {
                "role": "verifier", "threadId": "thread-verifier", "messageId": "msg-verify",
                "sentAt": "2026-07-11T21:02:00+08:00",
                "searchAnchor": {"messageId": "msg-verify", "sentAt": "2026-07-11T21:02:00+08:00"},
            }},
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        team_router.reserve_role_or_creation_intent(
            self.root, self.project_id,
            parent_thread_id=self.parent_thread_id, host_id="local", target_fingerprint="target-v2-acceptance",
            role="verifier", task_id=self.task_id, request_id="verifier-request-1",
            claimed_at="2026-07-11T21:00:00+08:00",
        )
        team_router.finalize_created_role(
            self.root, self.project_id, parent_thread_id=self.parent_thread_id, role="verifier",
            request_id="verifier-request-1", thread_id="thread-verifier", title="验证者-局部修复",
            created_at="2026-07-11T21:00:01+08:00",
        )

        rework = team_router.capture_verifier_verdict_from_read(
            self.root, self.project_id, self.task_id,
            [
                {"messageId": "msg-verify", "sentAt": "2026-07-11T21:02:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-07-11T21:03:00+08:00", "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\nresult: needs_rework\nsummary: narrow fix needed\n"
                    "requiredChanges: add assertion\nevidenceChecked: focused test\nrisks: none"
                ) % self.task_id},
            ],
            captured_at="2026-07-11T21:04:00+08:00",
        )

        self.assertEqual((rework["status"], rework["reworkCount"], rework["preferredThreadId"]), ("dispatched", 1, "thread-verifier"))
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertNotIn("claim", pool["roles"]["verifier"][0])

    def _save_v1_mixed_verifier_history(self, *, direct_return=False):
        ledger = self._save_awaiting_acceptance()
        legacy_request = {
            "role": "verifier",
            "threadId": "thread-legacy-verifier",
            "messageId": "msg-legacy-request",
            "sentAt": "2026-07-15T10:00:00+08:00",
            "searchAnchor": {
                "messageId": "msg-legacy-request",
                "sentAt": "2026-07-15T10:00:00+08:00",
            },
        }
        if direct_return:
            legacy_request.update({
                "returnThreadId": self.parent_thread_id,
                "returnSearchAnchor": {
                    "messageId": "msg-legacy-request",
                    "sentAt": "2026-07-15T10:00:00+08:00",
                },
                "verdictDelivery": "direct-send",
            })
        ledger.update({
            "workflowVersion": 1,
            "status": "verifying",
            "dispatches": [
                *ledger["dispatches"],
                {
                    "role": "verifier",
                    "threadId": "thread-strict-verifier",
                    "roleThreadId": "thread-strict-verifier",
                    "requestId": "strict-request",
                    "protocolVersion": 2,
                    "dispatchId": "strict-dispatch",
                    "attempt": 1,
                    "dispatchAccepted": True,
                    "resultStatus": "pending",
                },
            ],
            "verification": {"request": legacy_request},
        })
        return team_router.save_task_ledger(
            self.root, self.project_id, self.task_id, ledger,
        )

    def test_v1_verifier_fallback_rejects_legacy_verdict_when_strict_dispatch_exists(self):
        self._save_v1_mixed_verifier_history()
        messages = [
            {
                "messageId": "msg-legacy-request",
                "sentAt": "2026-07-15T10:00:00+08:00",
                "text": "verify",
            },
            {
                "messageId": "msg-legacy-verdict",
                "sentAt": "2026-07-15T10:01:00+08:00",
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\n"
                    "summary: stale legacy verdict\nrequiredChanges: none\n"
                    "evidenceChecked: focused test\nrisks: none"
                ) % self.task_id,
            },
        ]

        with self.assertRaisesRegex(team_router.StateStoreError, "strict verifier dispatch"):
            team_router.capture_verifier_verdict_from_read(
                self.root,
                self.project_id,
                self.task_id,
                messages,
                captured_at="2026-07-15T10:02:00+08:00",
            )

        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(saved["status"], "verifying")
        self.assertEqual(saved["dispatches"][-1]["resultStatus"], "pending")
        self.assertNotIn("resultReceipts", saved["dispatches"][-1])

    def test_v1_verifier_direct_return_rejects_legacy_verdict_when_strict_dispatch_exists(self):
        self._save_v1_mixed_verifier_history(direct_return=True)
        messages = [{
            "messageId": "msg-legacy-verdict",
            "sentAt": "2026-07-15T10:01:00+08:00",
            "sourceThreadId": "thread-legacy-verifier",
            "text": (
                "TEAM_ROUTER_VERDICT taskId=%s\n"
                "sourceThreadId: %s\n"
                "sourceRoleThreadId: thread-legacy-verifier\n"
                "role: Verifier\nresult: pass\n"
                "summary: stale legacy verdict\nrequiredChanges: none\n"
                "evidenceChecked: focused test\nrisks: none"
            ) % (self.task_id, self.parent_thread_id),
        }]

        result = team_router._capture_verifier_verdict_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-07-15T10:02:00+08:00",
        )

        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertIsNone(result)
        self.assertEqual(saved["status"], "verifying")
        self.assertEqual(saved["dispatches"][-1]["resultStatus"], "pending")
        self.assertNotIn("resultReceipts", saved["dispatches"][-1])

    def test_v2_verifier_direct_return_rejects_newer_legacy_record_after_strict_history(self):
        ledger = self._save_awaiting_acceptance()
        strict_dispatch = {
            "role": "verifier",
            "threadId": "thread-strict-verifier",
            "roleThreadId": "thread-strict-verifier",
            "requestId": "strict-request",
            "protocolVersion": 2,
            "dispatchId": "strict-dispatch",
            "attempt": 1,
            "dispatchAccepted": True,
            "resultStatus": "pending",
        }
        legacy_dispatch = {
            "role": "verifier",
            "threadId": "thread-legacy-verifier",
            "requestId": "legacy-request",
            "returnThreadId": self.parent_thread_id,
            "verdictDelivery": "direct-send",
            "returnSearchAnchor": {
                "messageId": "msg-legacy-request",
                "sentAt": "2026-07-15T10:00:00+08:00",
            },
        }
        ledger.update({
            "status": "verifying",
            "dispatches": [
                *ledger["dispatches"],
                strict_dispatch,
                legacy_dispatch,
            ],
            "verification": {"request": legacy_dispatch},
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [{
            "messageId": "msg-legacy-verdict",
            "sentAt": "2026-07-15T10:01:00+08:00",
            "sourceThreadId": "thread-legacy-verifier",
            "text": (
                "TEAM_ROUTER_VERDICT taskId=%s\n"
                "sourceThreadId: %s\n"
                "sourceRoleThreadId: thread-legacy-verifier\n"
                "role: Verifier\nresult: pass\n"
                "summary: stale legacy verdict\nrequiredChanges: none\n"
                "evidenceChecked: focused test\nrisks: none"
            ) % (self.task_id, self.parent_thread_id),
        }]

        result = team_router._capture_verifier_verdict_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-07-15T10:02:00+08:00",
        )

        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertIsNone(result)
        self.assertEqual(saved["status"], "verifying")
        self.assertEqual(saved["dispatches"][-2]["resultStatus"], "pending")
        self.assertNotIn("resultReceipts", saved["dispatches"][-2])
        self.assertNotIn("verdict", saved["verification"])
        self.assertFalse(saved.get("closeout"))


class TestTeamRouterV2RolePool(unittest.TestCase):
    def setUp(self):
        self.td = workspace_temp_dir()
        self.root = Path(self.td.name) / "state"
        self.project_id = "project-123"
        self.base_claim = {
            "parent_thread_id": "parent-a",
            "host_id": "local",
            "target_fingerprint": "target-a",
            "role": "executor",
            "claimed_at": "2026-07-11T20:00:00+08:00",
        }

    def tearDown(self):
        self.td.cleanup()

    def _reserve(self, task_id, request_id, **changes):
        claim = {**self.base_claim, "task_id": task_id, "request_id": request_id, **changes}
        return team_router.reserve_role_or_creation_intent(self.root, self.project_id, **claim)

    def _save_v2_task(self, task_id):
        ledger = team_router.new_v2_task_ledger(
            self.root,
            self.project_id,
            task_id,
            objective="manage executor pool",
            project_local_path=self.root,
            parent_thread_id="parent-a",
            resolved_plan={"routeRoles": ["executor"]},
            task_authorization_package={"packageId": "auth-a"},
            created_at="2026-07-11T20:00:00+08:00",
        )
        return team_router.save_task_ledger(self.root, self.project_id, task_id, ledger)

    def _finalize(self, request_id, thread_id="thread-executor-a"):
        return team_router.finalize_created_role(
            self.root,
            self.project_id,
            parent_thread_id="parent-a",
            role="executor",
            request_id=request_id,
            thread_id=thread_id,
            title="执行者-任务 A",
            created_at="2026-07-11T20:00:01+08:00",
        )

    def _release(self, task_id, request_id, thread_id="thread-executor-a"):
        return team_router.release_role_claim(
            self.root,
            self.project_id,
            parent_thread_id="parent-a",
            role="executor",
            thread_id=thread_id,
            task_id=task_id,
            request_id=request_id,
        )

    def _make_idle(self, task_id="task-seed", request_id="req-seed", thread_id="thread-executor-a"):
        self._reserve(task_id, request_id)
        self._finalize(request_id, thread_id)
        self._release(task_id, request_id, thread_id)

    def test_v2_role_pool_reuses_only_same_host_target_and_role(self):
        first = self._reserve("task-a", "req-a")
        duplicate = self._reserve("task-a", "req-a")
        self.assertEqual(first["outcome"], "creation_intent")
        self.assertTrue(duplicate["existing"])
        self._finalize("req-a")
        self.assertEqual(self._release("task-a", "req-a")["outcome"], "released")

        reused = self._reserve("task-b", "req-b")
        other_parent = self._reserve("task-c", "req-c", parent_thread_id="parent-b")
        other_target = self._reserve("task-d", "req-d", target_fingerprint="target-b")
        self.assertEqual((reused["outcome"], reused["threadId"]), ("reused", "thread-executor-a"))
        self.assertEqual(other_parent["outcome"], "busy")
        self.assertEqual(other_target["outcome"], "creation_intent")

    def test_v2_role_pool_reuses_idle_role_across_manager_threads(self):
        self._make_idle()

        reused = self._reserve(
            "task-other-manager",
            "req-other-manager",
            parent_thread_id="parent-b",
        )

        self.assertEqual((reused["outcome"], reused["threadId"]), ("reused", "thread-executor-a"))
        self.assertEqual(
            team_router_state.manager_pool_lock_path(self.root, self.project_id, "parent-a"),
            team_router_state.manager_pool_lock_path(self.root, self.project_id, "parent-b"),
        )

    def test_v2_role_title_is_stable_across_objectives(self):
        first = team_router.v2_role_thread_title(self.project_id, "executor")
        second = team_router.v2_role_thread_title(self.project_id, "executor")

        self.assertEqual(first, second)
        self.assertEqual(first, "执行者-Team Router project-123")

    def test_role_claim_is_mutex_and_parallel_creation_is_explicit(self):
        self._make_idle()
        barrier, outcomes, errors = threading.Barrier(3), [], []

        def reserve(task_id, request_id):
            try:
                barrier.wait()
                outcomes.append(self._reserve(task_id, request_id))
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=reserve, args=("task-one", "req-one")),
            threading.Thread(target=reserve, args=("task-two", "req-two")),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual([item["outcome"] for item in outcomes].count("reused"), 1)
        self.assertEqual([item["outcome"] for item in outcomes].count("busy"), 1)
        self.assertEqual(
            self._reserve("task-parallel", "req-parallel", parallel_allowed=True)["outcome"],
            "creation_intent",
        )
        with team_router.manager_pool_lock(
            self.root, self.project_id, "parent-a", task_id="task-held", request_id="req-held",
            acquired_at="2026-07-11T20:00:02+08:00",
        ):
            self.assertEqual(self._reserve("task-locked", "req-locked")["outcome"], "busy")

    def test_role_claim_release_keeps_preferred_thread_id(self):
        task_id = "task-preferred"
        self._save_v2_task(task_id)
        self._reserve(task_id, "req-a")
        self._finalize("req-a")
        self.assertEqual(self._release(task_id, "req-a")["outcome"], "released")
        self.assertEqual(
            team_router.load_task_ledger(self.root, self.project_id, task_id)["preferredThreadId"],
            "thread-executor-a",
        )

    def test_v2_role_pool_prefers_requested_idle_thread_when_two_records_exist(self):
        self._reserve("task-a", "req-a")
        self._finalize("req-a", "thread-executor-a")
        self.assertEqual(
            self._reserve("task-b", "req-b", parallel_allowed=True)["outcome"],
            "creation_intent",
        )
        self._finalize("req-b", "thread-executor-b")
        self.assertEqual(self._release("task-b", "req-b", "thread-executor-b")["outcome"], "released")
        self.assertEqual(self._release("task-a", "req-a", "thread-executor-a")["outcome"], "released")

        preferred = self._reserve(
            "task-c",
            "req-c",
            preferred_thread_id="thread-executor-b",
        )

        self.assertEqual((preferred["outcome"], preferred["threadId"]), ("reused", "thread-executor-b"))

    def test_v2_role_pool_replaces_archived_or_corrupt_records(self):
        with self.assertRaises(team_router.StateStoreError):
            self._reserve("task-manager", "req-manager", role="manager")
        self._make_idle(thread_id="thread-archived")
        registry = team_router.load_registry(self.root, self.project_id)
        project = registry["projects"][self.project_id]
        pool = project["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        pool["roles"]["executor"][0]["archived"] = True
        pool["roles"]["executor"].append({
            "threadId": "thread-corrupt", "hostId": "local", "targetFingerprint": "target-a", "claim": "bad",
        })
        team_router.save_registry(self.root, self.project_id, registry)

        self.assertEqual(self._reserve("task-new", "req-new")["outcome"], "creation_intent")
        self.assertEqual(
            self._reserve("task-corrupt", "req-corrupt", parent_thread_id="parent-corrupt")["outcome"],
            "busy",
        )

    def _leak_lock(self, task_id, request_id):
        path = team_router_state.manager_pool_lock_path(self.root, self.project_id, "parent-a")
        payload = json.dumps({
            "projectId": self.project_id, "parentThreadId": "parent-a", "taskId": task_id,
            "requestId": request_id, "pid": os.getpid(), "acquiredAt": "2001-01-01T00:00:00+00:00",
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        return path

    def test_creation_intent_recovery_keeps_unknown_identity_then_cleans_terminal_task(self):
        task_id = "task-unknown"
        self._save_v2_task(task_id)
        self._reserve(task_id, "req-claimed")
        self._finalize("req-claimed")
        self._reserve(task_id, "req-unknown", parallel_allowed=True)
        pending = team_router.recover_creation_intent(
            self.root, self.project_id, parent_thread_id="parent-a", role="executor",
            request_id="req-unknown", recovered_at="2026-07-11T20:00:02+08:00",
        )
        self.assertEqual(pending["requestId"], "req-unknown")

        lock_path = self._leak_lock(task_id, "req-unknown")
        self.assertFalse(team_router.recover_manager_pool_lock(
            self.root, self.project_id, "parent-a", task_id=task_id, request_id="req-unknown",
            recovered_at="2026-07-11T20:00:02+08:00",
        ))
        ledger = team_router.load_task_ledger(self.root, self.project_id, task_id)
        ledger.update(status="tool_error", reason="creation_outcome_unknown")
        team_router.save_task_ledger(self.root, self.project_id, task_id, ledger)
        self.assertTrue(team_router.recover_manager_pool_lock(
            self.root, self.project_id, "parent-a", task_id=task_id, request_id="req-unknown",
            recovered_at="2026-07-11T20:00:03+08:00",
        ))
        self.assertFalse(lock_path.exists())
        self.assertEqual(self._release(task_id, "req-claimed")["outcome"], "released")

        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertEqual(pool["creationIntents"], [])
        self.assertNotIn("claim", pool["roles"]["executor"][0])
        self.assertIsNone(team_router.recover_creation_intent(
            self.root, self.project_id, parent_thread_id="parent-a", role="executor",
            request_id="req-unknown", recovered_at="2026-07-11T20:00:04+08:00",
        ))
        observations = team_router.load_task_ledger(self.root, self.project_id, task_id)["observations"]
        self.assertTrue(any(
            item.get("type") == "system_event"
            and item.get("parsedFields", {}).get("reason") == "creation_outcome_unknown"
            and item.get("parsedFields", {}).get("requestId") == "req-unknown"
            for item in observations
        ))

    def test_role_claim_terminal_pool_cleanup_is_public_and_refuses_nonterminal_task(self):
        task_id = "task-terminal"
        self._save_v2_task(task_id)
        self._reserve(task_id, "req-terminal")
        cleanup = lambda stamp: team_router.cleanup_terminal_manager_pool_task(
            self.root, self.project_id, parent_thread_id="parent-a", task_id=task_id, cleaned_at=stamp,
        )
        self.assertEqual(cleanup("2026-07-11T20:00:01+08:00")["outcome"], "not_terminal")
        ledger = team_router.load_task_ledger(self.root, self.project_id, task_id)
        ledger["status"] = "done"
        team_router.save_task_ledger(self.root, self.project_id, task_id, ledger)
        self.assertEqual(cleanup("2026-07-11T20:00:02+08:00")["outcome"], "cleaned")
        pool = team_router.load_registry(self.root, self.project_id)["projects"][self.project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]
        self.assertEqual(pool["creationIntents"], [])


class TestTeamRouterManagerIntegration(unittest.TestCase):
    def setUp(self):
        self.td = workspace_temp_dir()
        self.root = Path(self.td.name) / "state"
        self.project_id = "project-123"
        self.task_id = "ctr-20260622-160000-a7f3"
        self.roles = {
            "manager": {
                "threadId": "thread-manager",
                "title": "TeamRouter manager - repo",
            },
            "executor": {
                "threadId": "thread-executor",
                "title": "TeamRouter executor - repo",
            },
            "verifier": {
                "threadId": "thread-verifier",
                "title": "TeamRouter verifier - repo",
            },
        }

    def tearDown(self):
        self.td.cleanup()

    def _ready_ledger(self, max_rework=3):
        return team_router.create_team_task(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            roles=self.roles,
            observed_at="2026-06-22T20:00:00+08:00",
            max_rework=max_rework,
        )

    def _awaiting_plan_ledger(self):
        self._ready_ledger()
        return team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id="msg-plan",
        )

    def _planned_ledger(self, max_rework=3):
        self._ready_ledger(max_rework=max_rework)
        team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id="msg-plan",
        )
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=ctr-20260622-160000-a7f3\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none"},
        ]
        return team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

    def _awaiting_callback_ledger(self, max_rework=3):
        self._planned_ledger(max_rework=max_rework)
        return team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
        )

    def _verifying_ledger(self, max_rework=3):
        self._awaiting_callback_ledger(max_rework=max_rework)
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
        ]
        return team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

    def test_create_team_task_writes_registry_roles_and_task_file(self):
        ledger = self._ready_ledger()

        self.assertEqual(ledger["status"], "roles_ready")
        saved_ledger = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(saved_ledger["objective"], "inspect docs")
        registry = team_router.load_registry(self.root, self.project_id)
        project = registry["projects"][self.project_id]
        self.assertEqual(project["roles"]["manager"]["threadId"], "thread-manager")
        self.assertEqual(project["roles"]["executor"]["threadId"], "thread-executor")
        self.assertEqual(project["roles"]["verifier"]["threadId"], "thread-verifier")
        self.assertEqual(project["roles"]["manager"]["lastObservedAt"], "2026-06-22T20:00:00+08:00")

    def test_plan_request_and_plan_capture_record_anchors_and_fields(self):
        ledger = self._ready_ledger()
        message = team_router.make_plan_request_message(
            ledger["taskId"],
            ledger["objective"],
            "read-only",
        )
        self.assertIn("TEAM_ROUTER_PLAN_REQUEST taskId=ctr-20260622-160000-a7f3", message)
        self.assertIn("permission: read-only", message)
        local_message = team_router.make_plan_request_message(
            ledger["taskId"],
            ledger["objective"],
            "local-package",
        )
        self.assertIn("permission: local-package", local_message)
        self.assertIn("acknowledgedPermission: read-only | design-only | local-package | escalation-required", local_message)
        self.assertIn("相关时可填写 PACKAGE/STRICT 交接字段：", local_message)
        self.assertIn("taskBriefPath: <任务 brief 的 workspace 路径>", local_message)
        self.assertIn("executorReportPath: <执行者报告的 workspace 路径>", local_message)
        self.assertIn("reviewPackagePath: <review package 的 workspace 路径> | inline", local_message)
        self.assertIn("inlineFallback: true", local_message)

        awaiting = team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id="msg-plan",
        )
        self.assertEqual(awaiting["status"], "awaiting_plan")
        self.assertEqual(awaiting["planRequest"]["searchAnchor"]["messageId"], "msg-plan")

        planned = self._planned_ledger()
        self.assertEqual(planned["status"], "planned")
        self.assertEqual(planned["plan"]["fields"]["executorPrompt"], "inspect src")

    def test_plan_capture_marks_unreachable_when_read_window_misses_anchor(self):
        ledger = self._awaiting_plan_ledger()
        messages = [{"text": "plan without ids or timestamps"}]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "plan_unreachable")

    def test_plan_capture_keeps_waiting_when_window_covers_but_marker_missing(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-later", "sentAt": "2026-06-22T20:01:30+08:00", "text": "still planning"},
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_plan")

    def test_plan_capture_blocks_escalation_required(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: escalation-required\nscope: src\nstopWhen: done\nriskBoundary: needs write access\nexecutorPrompt: inspect src\nnotes: none" % ledger["taskId"]},
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "blocked")

    def test_plan_capture_records_workspace_path_metadata_without_reading_files(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: docs\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect docs\ntaskBriefPath: docs/brief.md\nexecutorReportPath: reports/executor.md\nreviewPackagePath: docs/review-package.md\nnotes: none" % ledger["taskId"]},
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "planned")
        package = updated["reviewPackage"]
        self.assertEqual(package["status"], "recorded")
        self.assertFalse(package["contentTrusted"])
        self.assertFalse(package["autoGenerated"])
        self.assertEqual(package["paths"]["taskBriefPath"], "docs/brief.md")
        self.assertEqual(package["paths"]["executorReportPath"], "reports/executor.md")
        self.assertEqual(package["paths"]["reviewPackagePath"], "docs/review-package.md")

    def test_plan_capture_blocks_invalid_review_package_paths(self):
        cases = (
            ("../outside.md", "inside project workspace"),
            ("https://example.test/package.md", "not a URL"),
            ("AGENTS.md", "AGENTS.md"),
            (".git/config", "git or global config"),
            ("docs/package; rm -rf .", "action or wildcard"),
            ("C:/Users/Orz/.codex/config.toml", "inside project workspace"),
        )
        for raw_path, error_part in cases:
            with self.subTest(raw_path=raw_path):
                self.tearDown()
                self.setUp()
                ledger = self._awaiting_plan_ledger()
                messages = [
                    {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
                    {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: docs\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect docs\nreviewPackagePath: %s\nnotes: none" % (ledger["taskId"], raw_path)},
                ]

                updated = team_router.capture_manager_plan_from_read(
                    self.root,
                    self.project_id,
                    ledger["taskId"],
                    messages,
                    captured_at="2026-06-22T20:01:40+08:00",
                )

                self.assertEqual(updated["status"], "blocked")
                self.assertEqual(updated["reviewPackage"]["status"], "blocked")
                self.assertIn(error_part, "\n".join(updated["reviewPackage"]["errors"]))

    def test_package_gate_requires_review_package_path_or_inline_fallback(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: local-package\nscope: same task family discipline hardening\nstopWhen: done\nriskBoundary: package gate\nexecutorPrompt: bundle same task family changes\nnotes: package" % ledger["taskId"]},
        ]

        blocked = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("requires reviewPackagePath", "\n".join(blocked["reviewPackage"]["errors"]))

        self.tearDown()
        self.setUp()
        ledger = self._awaiting_plan_ledger()
        messages[1] = {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: local-package\nscope: same task family discipline hardening\nstopWhen: done\nriskBoundary: package gate\nexecutorPrompt: bundle same task family changes\ninlineFallback: true\nnotes: package" % ledger["taskId"]}
        planned = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(planned["status"], "planned")
        self.assertEqual(planned["reviewPackage"]["gateClass"], "PACKAGE")
        self.assertTrue(planned["reviewPackage"]["inlineFallback"])

    def test_strict_gate_records_missing_paths_without_blocking(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: Team Router process policy\nstopWhen: done\nriskBoundary: role protocol change\nexecutorPrompt: inspect policy\nnotes: none" % ledger["taskId"]},
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "planned")
        self.assertEqual(updated["reviewPackage"]["gateClass"], "STRICT")
        self.assertEqual(updated["reviewPackage"]["paths"], {})
        self.assertEqual(updated["reviewPackage"]["errors"], [])

    def _high_risk_awaiting_callback_ledger(self):
        ledger = self._awaiting_callback_ledger()
        ledger["objective"] = "update role protocol and orchestration policy"
        ledger["plan"]["fields"]["scope"] = "role protocol and orchestration policy"
        return team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

    def test_executor_dispatch_records_attempt_and_recovery_anchor(self):
        ledger = self._planned_ledger()
        message = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"},
        )
        self.assertIn("callbackMode: self-thread-marker", message)
        self.assertIn("callbackMarker: TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", message)
        anchor_line = next(line for line in message.splitlines() if line.startswith("searchAnchor: "))
        self.assertEqual(anchor_line, "searchAnchor: {\"messageId\": \"msg-dispatch\", \"sentAt\": \"2026-06-22T20:02:00+08:00\"}")
        anchor_json = anchor_line.removeprefix("searchAnchor: ")
        self.assertEqual(json.loads(anchor_json), {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"})

        updated = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
        )
        self.assertEqual(updated["status"], "awaiting_callback")
        self.assertEqual(updated["dispatches"][-1]["attempt"], 1)
        registry = team_router.load_registry(self.root, self.project_id)
        read_request = team_router.recovery_read_request(updated, registry, "executor")
        self.assertEqual(read_request["threadId"], "thread-executor")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-dispatch")

    def test_executor_dispatch_records_heartbeat_watcher_metadata(self):
        ledger = self._planned_ledger()

        updated = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
        )

        watcher = updated["watcher"]
        self.assertEqual(watcher["role"], "executor")
        self.assertEqual(watcher["threadId"], "thread-executor")
        self.assertEqual(watcher["expectedMarker"], "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3")
        self.assertEqual(watcher["lastReadAt"], "2026-06-22T20:02:00+08:00")
        self.assertEqual(watcher["nextAllowedReadAt"], "2026-06-22T20:07:00+08:00")
        self.assertEqual(watcher["minimumIntervalSeconds"], 300)
        self.assertEqual(watcher["status"], "running")
        self.assertEqual(watcher["nextManagerAction"], "watch_team_task_with_adapter")
        self.assertEqual(watcher["actionOnWake"], "read_thread")
        self.assertEqual(watcher["firstCheckAction"], "read_thread")
        self.assertEqual(watcher["firstCheckReason"], "initial short follow-up after dispatch")
        self.assertEqual(watcher["firstCheckAt"], "2026-06-22T20:02:30+08:00")

    def test_executor_dispatch_supports_direct_return_delivery_metadata(self):
        ledger = self._planned_ledger()

        message = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"},
            return_thread_id="parent-manager-thread",
            role_thread_id="thread-executor",
        )

        self.assertIn("sourceThreadId: parent-manager-thread", message)
        self.assertIn("sourceRoleThreadId: thread-executor", message)
        self.assertIn("role: Executor", message)
        self.assertIn("returnThreadId: parent-manager-thread", message)
        self.assertIn("orchestratorThreadId: parent-manager-thread", message)
        self.assertIn("roleThreadId: thread-executor", message)
        self.assertIn("callbackDelivery: direct-send", message)
        self.assertIn("callbackFallback: self-thread-marker", message)
        self.assertIn(
            "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
            message,
        )
        self.assertIn(
            "Then print the same full TEAM_ROUTER_* block in this thread as fallback.",
            message,
        )
        self.assertIn("直接回传校验字段：taskId, role, sourceThreadId, sourceRoleThreadId。", message)
        self.assertIn(
            "直接回传 fallback metadata：deliveryStatus: fallback_only; deliveryError: <仅 direct-send 失败时填写短错误>。",
            message,
        )
        self.assertIn("deliveryStatus: fallback_only", message)
        self.assertIn("deliveryError", message)
        self.assertNotIn("short error only when direct-send failed", message)
        self.assertIn("callbackMarker: TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", message)

        updated = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        latest = updated["dispatches"][-1]
        self.assertEqual(latest["returnThreadId"], "parent-manager-thread")
        self.assertEqual(latest["orchestratorThreadId"], "parent-manager-thread")
        self.assertEqual(latest["roleThreadId"], "thread-executor")
        self.assertEqual(latest["callbackDelivery"], "direct-send")
        self.assertEqual(latest["callbackFallback"], "self-thread-marker")
        self.assertEqual(latest["fallbackSearchAnchor"], latest["searchAnchor"])
        self.assertEqual(
            latest["returnSearchAnchor"],
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )

    def test_malformed_direct_return_records_wrong_protocol_fields_and_keeps_fallback(self):
        self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        messages = [{
            "messageId": "msg-direct-bad",
            "sentAt": "2026-06-22T20:03:00+08:00",
            "sourceThreadId": "thread-executor",
            "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none\nsourceThreadId: wrong-parent\nrole: verifier\nsourceRoleThreadId: wrong-role-thread",
        }]

        result = team_router._capture_executor_callback_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:03:30+08:00",
        )

        self.assertIsNone(result)
        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(saved["status"], "awaiting_callback")
        malformed = saved["malformedDirectReturns"][-1]
        self.assertEqual(malformed["recovery"], "self-thread-marker fallback")
        self.assertEqual(malformed["sourceThreadId"], "thread-executor")
        self.assertEqual(malformed["protocolSourceThreadId"], "wrong-parent")
        self.assertEqual(malformed["protocolRole"], "verifier")
        self.assertEqual(malformed["protocolSourceRoleThreadId"], "wrong-role-thread")
        self.assertIn("TEAM_ROUTER_CALLBACK.sourceThreadId", malformed["error"])
        self.assertIn("TEAM_ROUTER_CALLBACK.role", malformed["error"])
        self.assertIn("TEAM_ROUTER_CALLBACK.sourceRoleThreadId", malformed["error"])

    def test_malformed_direct_return_records_missing_protocol_fields_and_keeps_fallback(self):
        self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        messages = [{
            "messageId": "msg-direct-missing",
            "sentAt": "2026-06-22T20:03:00+08:00",
            "sourceThreadId": "thread-executor",
            "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none",
        }]

        result = team_router._capture_executor_callback_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:03:30+08:00",
        )

        self.assertIsNone(result)
        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(saved["status"], "awaiting_callback")
        malformed = saved["malformedDirectReturns"][-1]
        self.assertEqual(malformed["protocolSourceThreadId"], "")
        self.assertEqual(malformed["protocolRole"], "")
        self.assertEqual(malformed["protocolSourceRoleThreadId"], "")
        self.assertIn("TEAM_ROUTER_CALLBACK.sourceThreadId is required", malformed["error"])
        self.assertIn("TEAM_ROUTER_CALLBACK.role is required", malformed["error"])
        self.assertIn("TEAM_ROUTER_CALLBACK.sourceRoleThreadId is required", malformed["error"])
    def test_send_executor_dispatch_with_adapter_includes_startup_failure_recovery_policy(self):
        adapter = FakeThreadAdapter()
        self._planned_ledger()

        team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="local-package",
            sent_at="2026-06-22T20:02:00+08:00",
        )

        prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("-1073741502", prompt)
        self.assertIn("cmd.exe /c ver", prompt)
        self.assertIn("Get-Location", prompt)
        self.assertIn("git status -s --untracked-files=all", prompt)
        self.assertIn("不当作任务代码失败", prompt)
        self.assertIn("只重试同一个窄 package", prompt)
        self.assertIn("不得把范围扩大到原始窄 package 之外", prompt)
        self.assertNotIn("retry the same narrow package only", prompt)
        self.assertNotIn("environment is blocked", prompt)

    def test_executor_dispatch_search_anchor_serializes_null_message_id(self):
        ledger = self._planned_ledger()

        message = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )

        anchor_line = next(line for line in message.splitlines() if line.startswith("searchAnchor: "))
        self.assertEqual(anchor_line, "searchAnchor: {\"messageId\": null, \"sentAt\": \"2026-06-22T20:02:00+08:00\"}")

    def test_role_prompts_include_risk_boundary_and_review_package_metadata(self):
        ledger = self._planned_ledger()
        plan_fields = dict(ledger["plan"]["fields"])
        plan_fields.update({
            "scope": "same task family discipline hardening",
            "stopWhen": "reviewer and verifier pass",
            "riskBoundary": "workspace writes only; no external release",
            "executorPrompt": "fix package gate",
            "taskBriefPath": "docs/brief.md",
            "executorReportPath": "reports/executor.md",
            "reviewPackagePath": "inline",
            "inlineFallback": "true",
        })
        review_package = {
            "gateClass": "PACKAGE",
            "status": "recorded",
            "inlineFallback": True,
            "paths": {
                "taskBriefPath": "docs/brief.md",
                "executorReportPath": "reports/executor.md",
            },
            "raw": {"reviewPackagePath": "inline"},
            "contentTrusted": False,
            "autoGenerated": False,
        }
        callback = "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: ok\nevidence: package\nrisks: none\nnext: reviewer" % ledger["taskId"]
        messages = (
            team_router.make_executor_dispatch_message(
                ledger["taskId"],
                plan_fields,
                "local-package",
                {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"},
                review_package=review_package,
            ),
            team_router.make_reviewer_request_message(
                ledger["taskId"],
                callback,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
                review_package=review_package,
            ),
            team_router.make_verifier_request_message(
                ledger["taskId"],
                callback,
                "local-package",
                plan_fields["scope"],
                plan_fields=plan_fields,
                review_package=review_package,
            ),
        )
        for message in messages:
            self.assertIn("riskBoundary: workspace writes only; no external release", message)
            self.assertIn("packageEvidenceBoundary:", message)
            if message.startswith(("TEAM_ROUTER_REVIEW_REQUEST", "TEAM_ROUTER_VERIFY")):
                self.assertIn("defaultRules:mdFirstPolicy;cavemanTransportPolicy;TEAM_ROUTER_* schema commands/errors requiredChanges", message)
                self.assertNotIn("审查包元数据（仅作为证据）：", message)
                self.assertNotIn("运行时边界：Team Router runtime 不得读取、执行、信任或自动生成", message)
            else:
                self.assertIn("审查包元数据（仅作为证据）：", message)
                self.assertIn("运行时边界：Team Router runtime 不得读取、执行、信任或自动生成", message)
            self.assertIn("gateClass: PACKAGE", message)
            self.assertIn("metadataStatus: recorded", message)
            self.assertIn("inlineFallback: true", message)
            self.assertIn("taskBriefPath: docs/brief.md", message)
            self.assertIn("executorReportPath: reports/executor.md", message)
            self.assertIn("reviewPackagePath: inline", message)

    def test_callback_capture_uses_dispatch_anchor_from_ledger(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["type"], "callback_raw")
        self.assertEqual(updated["observations"][-1]["threadId"], "thread-executor")

    def test_callback_capture_accepts_same_timestamp_response_for_time_only_anchor(self):
        ledger = self._planned_ledger()
        dispatch_prompt = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )
        ledger = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "type": "userMessage",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": dispatch_prompt,
            },
            {
                "type": "agentMessage",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: same second\nevidence: tests\nrisks: none\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "same second")

    def test_callback_capture_falls_back_to_timestamp_when_send_message_id_missing_from_read(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {
                "type": "userMessage",
                "messageId": "item-dispatch",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_DISPATCH taskId=ctr-20260622-160000-a7f3",
            },
            {
                "type": "agentMessage",
                "messageId": "item-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: id mismatch\nevidence: live thread\nrisks: none\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "id mismatch")

    def test_callback_capture_uses_timestamp_when_read_thread_is_newest_first(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {
                "type": "agentMessage",
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: newest first\nevidence: live thread\nrisks: none\nnext: none",
            },
            {
                "type": "userMessage",
                "messageId": "msg-dispatch",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_DISPATCH taskId=ctr-20260622-160000-a7f3",
            },
            {
                "type": "agentMessage",
                "messageId": "msg-before-dispatch",
                "sentAt": "2026-06-22T20:01:30+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: stale\nevidence: old\nrisks: stale\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "newest first")

    def test_callback_capture_preserves_multiline_summary(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: first line\nsecond line\nthird line\nevidence: tests\nrisks: none\nnext: none"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(
            updated["observations"][-1]["parsedFields"]["summary"],
            "first line\nsecond line\nthird line",
        )

    def test_callback_capture_marks_unreachable_when_read_window_misses_anchor(self):
        ledger = self._awaiting_callback_ledger()
        messages = [{"text": "summary without ids or timestamps"}]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "callback_unreachable")

    def test_callback_capture_keeps_waiting_when_window_covers_but_marker_missing(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-later", "sentAt": "2026-06-22T20:03:00+08:00", "text": "still working"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_callback")

    def test_watch_executor_completion_without_callback_marker_needs_feedback_not_verifier(self):
        adapter = FakeThreadAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        adapter.append_reply(
            "thread-executor",
            "done, completed successfully",
            message_id="msg-done-no-marker",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["status"], "needs_feedback")
        self.assertEqual(update["ledger"]["roleThreadStatus"], "needs_feedback")
        self.assertIn("TEAM_ROUTER_CALLBACK", update["ledger"]["missingFeedback"]["expectedCallback"])
        self.assertEqual(update["nextWakeup"]["role"], "executor")
        self.assertEqual(update["watcher"]["threadId"], "thread-executor")
        self.assertIn("TEAM_ROUTER_CALLBACK", update["watcher"]["expectedMarker"])
        self.assertIn("structured TEAM_ROUTER_CALLBACK", update["nextWakeup"]["reason"])
        self.assertEqual(adapter.sent, [])

    def test_watch_executor_completion_with_callback_marker_advances_to_verifier_request(self):
        adapter = FakeThreadAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        adapter.append_reply(
            "thread-executor",
            "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: completed\nevidence: tests\nrisks: none\nnext: verifier",
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertIn("TEAM_ROUTER_VERIFY taskId=ctr-20260622-160000-a7f3", adapter.sent[-1]["kwargs"]["prompt"])

    def test_watch_executor_still_working_keeps_observe_only_convergence_decision(self):
        adapter = FakeThreadAdapter()
        scheduler = FakeHeartbeatScheduler()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        adapter.append_reply(
            "thread-executor",
            "still working",
            message_id="msg-later",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
            heartbeat_scheduler=scheduler,
        )

        self.assertEqual(update["status"], "awaiting_callback")
        self.assertEqual(update["ledger"]["roleThreadStatus"], "active")
        self.assertEqual(update["watcher"]["status"], "active")
        self.assertEqual(update["watcher"]["firstCheckAt"], "2026-06-22T20:02:30+08:00")
        self.assertEqual(update["watcher"]["nextAllowedReadAt"], "2026-06-22T20:09:00+08:00")
        self.assertEqual(update["convergenceDecision"]["action"], "observe_only_wait")
        self.assertFalse(update["convergenceDecision"]["allowed"])
        self.assertEqual(adapter.sent, [])
        self.assertEqual(len(scheduler.scheduled), 1)
        self.assertEqual(update["heartbeatSchedule"]["runAt"], "2026-06-22T20:09:00+08:00")
        self.assertEqual(scheduler.scheduled[0]["runAt"], "2026-06-22T20:09:00+08:00")
        self.assertEqual(scheduler.scheduled[0]["callback"], "watch_team_task_with_adapter")
        self.assertEqual(scheduler.scheduled[0]["role"], "executor")
        self.assertEqual(scheduler.scheduled[0]["watchArgs"]["read_reason"], "scheduled watcher heartbeat")

    def test_watch_rejects_non_callable_heartbeat_scheduler_when_waiting(self):
        adapter = FakeThreadAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        adapter.append_reply(
            "thread-executor",
            "still working",
            message_id="msg-later",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.watch_team_task_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                observed_at="2026-06-22T20:04:00+08:00",
                heartbeat_scheduler=True,
            )

        self.assertIn("heartbeat scheduler", str(ctx.exception))

    def test_watch_terminal_status_does_not_schedule_heartbeat(self):
        adapter = FakeThreadAdapter()
        scheduler = FakeHeartbeatScheduler()
        ledger = self._awaiting_callback_ledger()
        ledger["status"] = "done"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
            heartbeat_scheduler=scheduler,
        )

        self.assertEqual(update["action"], "watch_no_action")
        self.assertEqual(scheduler.scheduled, [])
        self.assertNotIn("heartbeatSchedule", update)
    def test_waiting_executor_update_before_timeout_does_not_allow_convergence_without_observation(self):
        ledger = self._awaiting_callback_ledger()

        update = team_router._adapter_task_update(
            "watch_waiting_executor",
            self.root,
            self.project_id,
            ledger,
            observed_at="2026-06-22T20:02:10+08:00",
        )

        self.assertEqual(update["readDiscipline"]["nextAllowedReadAt"], "2026-06-22T20:07:10+08:00")
        self.assertEqual(update["convergenceDecision"]["action"], "observe_only_wait")
        self.assertFalse(update["convergenceDecision"]["allowed"])
        self.assertEqual(update["convergenceDecision"]["readDecision"]["action"], "read_suppressed")

    def test_waiting_executor_update_exposes_heartbeat_watcher_metadata(self):
        ledger = self._awaiting_callback_ledger()

        update = team_router._adapter_task_update(
            "watch_waiting_executor",
            self.root,
            self.project_id,
            ledger,
            observed_at="2026-06-22T20:02:10+08:00",
        )

        watcher = update["watcher"]
        self.assertEqual(watcher["role"], "executor")
        self.assertEqual(watcher["threadId"], "thread-executor")
        self.assertEqual(watcher["expectedMarker"], "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3")
        self.assertEqual(watcher["lastReadAt"], "2026-06-22T20:02:10+08:00")
        self.assertEqual(watcher["nextAllowedReadAt"], "2026-06-22T20:07:10+08:00")
        self.assertEqual(watcher["nextManagerAction"], "watch_team_task_with_adapter")
        self.assertEqual(watcher["actionOnWake"], "read_thread")
        self.assertEqual(watcher["firstCheckAt"], "2026-06-22T20:02:30+08:00")
        self.assertEqual(watcher["firstCheckAction"], "read_thread")
        self.assertIn("nextAllowedReadAt: 2026-06-22T20:07:00+08:00", update["userOutput"])
        self.assertIn("expectedMarker: TEAM_ROUTER_CALLBACK", update["userOutput"])

    def test_watch_executor_public_helper_suppresses_repeated_reads_before_next_allowed(self):
        class CountingAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.read_count = 0

            def read_thread(self, **kwargs):
                self.read_count += 1
                return super().read_thread(**kwargs)

        adapter = CountingAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        adapter.append_reply(
            "thread-executor",
            "still working",
            message_id="msg-later",
            sent_at="2026-06-22T20:02:20+08:00",
        )

        first = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:02:30+08:00",
        )
        second = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:03:00+08:00",
        )

        self.assertEqual(first["action"], "watch_read_executor_callback")
        self.assertEqual(second["action"], "watch_read_suppressed")
        self.assertEqual(second["readDecision"]["action"], "read_suppressed")
        self.assertEqual(second["readDecision"]["nextAllowedReadAt"], "2026-06-22T20:07:30+08:00")
        self.assertEqual(adapter.read_count, 1)

    def test_watch_executor_public_helper_user_status_bypasses_read_throttle(self):
        class CountingAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.read_count = 0

            def read_thread(self, **kwargs):
                self.read_count += 1
                return super().read_thread(**kwargs)

        adapter = CountingAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply("thread-executor", "dispatch", message_id="msg-dispatch", sent_at="2026-06-22T20:02:00+08:00")
        adapter.append_reply("thread-executor", "still working", message_id="msg-later", sent_at="2026-06-22T20:02:20+08:00")
        team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:02:30+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:03:00+08:00",
            read_reason="user-triggered status check",
        )

        self.assertEqual(update["action"], "watch_read_executor_callback")
        self.assertEqual(adapter.read_count, 2)
    def test_watch_executor_first_check_with_valid_marker_advances_immediately(self):
        adapter = FakeThreadAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        adapter.append_reply(
            "thread-executor",
"TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: immediate\nevidence: tests\nrisks: none\nnext: verifier",
            message_id="msg-callback-fast",
            sent_at="2026-06-22T20:02:20+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:02:30+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")

    def test_watch_executor_first_check_without_marker_becomes_needs_feedback(self):
        adapter = FakeThreadAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        adapter.append_reply(
            "thread-executor",
            "completed quickly",
            message_id="msg-complete-no-marker-fast",
            sent_at="2026-06-22T20:02:20+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:02:30+08:00",
        )

        self.assertEqual(update["status"], "needs_feedback")
        self.assertEqual(update["nextWakeup"]["role"], "executor")
        self.assertIn("TEAM_ROUTER_CALLBACK", update["watcher"]["expectedMarker"])

    def test_watch_executor_idle_after_observation_allows_timeout_convergence(self):
        adapter = FakeThreadAdapter()
        self._awaiting_callback_ledger()
        adapter.append_reply(
            "thread-executor",
            "dispatch",
            message_id="msg-dispatch",
            sent_at="2026-06-22T20:02:00+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(update["status"], "awaiting_callback")
        self.assertEqual(update["ledger"]["roleThreadStatus"], "idle")
        self.assertEqual(update["convergenceDecision"]["action"], "convergence_allowed")
        self.assertTrue(update["convergenceDecision"]["allowed"])
        self.assertEqual(
            update["convergenceDecision"].get("observedNoProgressAt"),
            "2026-06-22T20:08:00+08:00",
        )

    def test_waiting_executor_idle_without_no_progress_confirmation_does_not_allow_convergence(self):
        ledger = self._awaiting_callback_ledger()
        ledger["roleThreadStatus"] = "idle"
        ledger["readDiscipline"] = dict(ledger["readDiscipline"])
        ledger["readDiscipline"].pop("lastObservedNoProgressAt", None)

        update = team_router._adapter_task_update(
            "watch_waiting_executor",
            self.root,
            self.project_id,
            ledger,
            observed_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(update["convergenceDecision"]["action"], "observe_only_read_first")
        self.assertFalse(update["convergenceDecision"]["allowed"])
        self.assertIn("observation-only read", update["convergenceDecision"]["reason"])

    def test_high_risk_executor_callback_enters_reviewer_gate_instead_of_verifier(self):
        ledger = self._high_risk_awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: protocol changed\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "reviewing")
        self.assertIsNone(updated["verification"])

    def test_low_risk_executor_callback_still_enters_verifier_gate(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: verifier"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")

    def test_fast_executor_callback_skips_reviewer_and_records_gate_class(self):
        ledger = self._awaiting_callback_ledger()
        ledger["objective"] = "restore README BOM"
        ledger["plan"]["fields"]["scope"] = "README.md"
        ledger["plan"]["fields"]["riskBoundary"] = "docs-only encoding rework"
        ledger["plan"]["fields"]["executorPrompt"] = "restore UTF-8 BOM only"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: bom restored\nevidence: tests\nrisks: none\nnext: verifier"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["gateClass"], "FAST")
        self.assertIsNone(updated["review"])

    def test_strict_executor_callback_enters_reviewer_and_records_gate_class(self):
        ledger = self._high_risk_awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: protocol changed\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "reviewing")
        self.assertEqual(updated["gateClass"], "STRICT")
        self.assertIsNone(updated["verification"])

    def test_watch_sends_reviewer_request_for_high_risk_callback(self):
        adapter = FakeThreadAdapter()
        ledger = self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        adapter.messages.setdefault("thread-executor", []).append({
            "messageId": "msg-dispatch",
            "sentAt": "2026-06-22T20:02:00+08:00",
            "text": "TEAM_ROUTER_DISPATCH taskId=%s" % self.task_id,
        })
        adapter.append_reply(
            ledger["dispatches"][-1]["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
            return_thread_id="parent-manager-thread",
        )

        self.assertEqual(update["action"], "watch_sent_reviewer_request")
        self.assertEqual(update["status"], "reviewing")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-reviewer")
        prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("reviewDelivery: direct-send", prompt)
        self.assertIn("reviewFallback: self-thread-marker", prompt)
        self.assertNotIn("verdictDelivery: direct-send", prompt)
        self.assertEqual(update["nextWakeup"]["role"], "reviewer")
        self.assertEqual(update["nextWakeup"]["reason"], "awaiting TEAM_ROUTER_REVIEW")
        self.assertEqual(
            update["nextWakeup"]["searchAnchor"],
            update["ledger"]["review"]["request"]["fallbackSearchAnchor"],
        )

    def test_review_unreachable_next_wakeup_points_to_reviewer_fallback_anchor(self):
        self._high_risk_awaiting_callback_ledger()
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id},
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            callback_messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        reviewing = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        reviewing["status"] = "review_unreachable"
        reviewing = team_router.save_task_ledger(self.root, self.project_id, self.task_id, reviewing)

        wakeup = team_router._watch_next_wakeup(reviewing)

        self.assertIsNotNone(wakeup)
        self.assertEqual(wakeup["role"], "reviewer")
        self.assertEqual(wakeup["reason"], "awaiting TEAM_ROUTER_REVIEW")
        self.assertEqual(wakeup["searchAnchor"], reviewing["review"]["request"]["fallbackSearchAnchor"])

    def test_watch_reviewer_request_inherits_return_thread_id_after_executor_fallback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        ledger["objective"] = "Team Router reviewer runtime gate rework"
        ledger["plan"]["fields"]["scope"] = "role protocol and orchestration policy"
        ledger["plan"]["fields"]["riskBoundary"] = "runtime gate change"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        ledger = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:02:30+08:00",
        )
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % ledger["taskId"],
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_reviewer_request")
        self.assertIn("returnThreadId: parent-manager-thread", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertEqual(update["ledger"]["review"]["request"]["returnThreadId"], "parent-manager-thread")
        self.assertEqual(update["nextWakeup"]["role"], "reviewer")

    def test_watch_verifier_request_inherits_return_thread_id_after_executor_fallback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        ledger = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: verifier" % ledger["taskId"],
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertIn("returnThreadId: parent-manager-thread", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertEqual(update["ledger"]["verification"]["request"]["returnThreadId"], "parent-manager-thread")

    def test_watch_verifier_request_inherits_return_thread_id_after_reviewer_fallback(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id},
            ],
            captured_at="2026-06-22T20:04:00+08:00",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:04:30+08:00",
        )
        team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["thread-reviewer"] = [
            {"messageId": "msg-review", "sentAt": "2026-06-22T20:05:00+08:00", "text": "review request"},
            {
                "messageId": "msg-review-pass",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": "TEAM_ROUTER_REVIEW taskId=%s\nresult: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none" % self.task_id,
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertIn("returnThreadId: parent-manager-thread", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertEqual(update["ledger"]["verification"]["request"]["returnThreadId"], "parent-manager-thread")

    def test_watch_captures_reviewer_direct_return_and_sends_verifier(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("pass"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["result"], "pass")
        self.assertEqual(update["ledger"]["review"]["result"]["receipt"]["source"], "manager-inbox/direct-send")
        self.assertEqual(update["ledger"]["review"]["result"]["receipt"]["channel"], "manager-inbox")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-verifier")
        self.assertIn("TEAM_ROUTER_VERIFY taskId=%s" % self.task_id, adapter.sent[-1]["kwargs"]["prompt"])

    def test_capture_reviewer_direct_return_from_manager_inbox_records_receipt(self):
        self._record_reviewer_direct_return_request()
        messages = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "sourceThreadId": "thread-reviewer",
                "text": (
                    "TEAM_ROUTER_REVIEW taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: thread-reviewer\n"
                    "role: Reviewer\n"
                    "result: pass\n"
                    "summary: direct review\n"
                    "findings: none\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        updated = team_router._capture_reviewer_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        result = updated["review"]["result"]
        self.assertEqual(result["fields"]["summary"], "direct review")
        self.assertEqual(result["receipt"]["source"], "manager-inbox/direct-send")
        self.assertEqual(result["receipt"]["channel"], "manager-inbox")
        self.assertEqual(result["receipt"]["returnThreadId"], "parent-manager-thread")

    def test_capture_verifier_direct_return_from_manager_inbox_is_idempotent(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        messages = [
            {
                "messageId": "msg-verdict-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "sourceThreadId": "thread-verifier",
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: thread-verifier\n"
                    "role: Verifier\n"
                    "result: pass\n"
                    "summary: direct closeout\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        first = team_router._capture_verifier_verdict_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        second = team_router._capture_verifier_verdict_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(first["status"], "done")
        self.assertIsNone(second)
        verdict = first["verification"]["verdict"]
        self.assertEqual(verdict["fields"]["summary"], "direct closeout")
        self.assertEqual(verdict["receipt"]["source"], "manager-inbox/direct-send")
        self.assertEqual(verdict["receipt"]["channel"], "manager-inbox")
        self.assertEqual(first["closeout"]["status"], "accepted")
        self.assertEqual(first["closeout"]["summary"], "direct closeout")
        self.assertEqual(first["closeout"]["receiptSource"], "manager-inbox/direct-send")
        self.assertEqual(first["closeout"]["receiptChannel"], "manager-inbox")
        registry = team_router.load_registry(self.root, self.project_id)
        closeout = team_router.format_closeout_for_user(first, registry)
        self.assertIn("receiptSource: manager-inbox/direct-send", closeout)
        self.assertIn("receiptChannel: manager-inbox", closeout)

    def test_watch_reviewer_direct_return_validates_protocol_source_role_thread_id(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper(
                    "pass",
                    source_thread_id="thread-reviewer",
                    source_role_thread_id="wrong-reviewer-thread",
                ),
            },
        ]
        adapter.messages["thread-reviewer"] = [
            {"messageId": "msg-review", "sentAt": "2026-06-22T20:05:00+08:00", "text": "review request"},
            {
                "messageId": "msg-review-fallback",
                "sentAt": "2026-06-22T20:06:30+08:00",
                "text": (
                    "TEAM_ROUTER_REVIEW taskId=%s\n"
                    "result: pass\n"
                    "summary: fallback review\n"
                    "findings: fallback evidence\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: reviewer self-thread\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["summary"], "fallback review")
        self.assertEqual(
            update["ledger"]["review"]["result"]["receipt"]["source"],
            "self-thread-fallback/read_thread",
        )
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["taskId"], self.task_id)
        self.assertEqual(telemetry[0]["role"], "reviewer")
        self.assertEqual(telemetry[0]["sourceThreadId"], "thread-reviewer")
        self.assertEqual(telemetry[0]["roleThreadId"], "thread-reviewer")
        self.assertEqual(telemetry[0]["returnThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["orchestratorThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["expectedMarker"], "TEAM_ROUTER_REVIEW taskId=%s" % self.task_id)
        self.assertEqual(telemetry[0]["messageId"], "msg-review-return")
        self.assertEqual(telemetry[0]["sentAt"], "2026-06-22T20:06:00+08:00")
        self.assertEqual(telemetry[0]["capturedAt"], "2026-06-22T20:07:00+08:00")
        self.assertIn("sourceRoleThreadId", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["recovery"], "self-thread-marker fallback")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-verifier")


    def test_watch_ignores_reviewer_direct_return_with_wrong_source_thread_id(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("pass", source_thread_id="thread-other-reviewer"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "review_unreachable")
        self.assertEqual(adapter.sent, [])
        self.assertNotIn("result", update["ledger"]["review"])
        self.assertIsNone(update["ledger"]["verification"])

    def test_watch_ignores_reviewer_direct_return_with_wrong_task_id(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("pass", task_id="ctr-20260622-wrong-task"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "review_unreachable")
        self.assertEqual(adapter.sent, [])
        self.assertNotIn("result", update["ledger"]["review"])
        self.assertIsNone(update["ledger"]["verification"])

    def test_watch_reads_reviewer_direct_return_needs_rework_without_verifier(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("needs_rework"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "needs_rework")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["result"], "needs_rework")
        self.assertEqual(adapter.sent, [])
        self.assertIsNone(update["ledger"]["verification"])

    def test_watch_reads_reviewer_direct_return_blocked_without_verifier(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("blocked"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "blocked")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["result"], "blocked")
        self.assertEqual(adapter.sent, [])
        self.assertIsNone(update["ledger"]["verification"])

    def _record_reviewer_direct_return_request(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id},
            ],
            captured_at="2026-06-22T20:04:00+08:00",
        )
        reviewing = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        request = reviewing["review"]["request"]
        self.assertEqual(request["reviewDelivery"], "direct-send")
        self.assertEqual(request["reviewFallback"], "self-thread-marker")
        self.assertNotIn("verdictDelivery", request)
        self.assertNotIn("verdictFallback", request)
        return adapter

    def _reviewer_direct_return_wrapper(self,
                                        result,
                                        task_id=None,
                                        source_thread_id="thread-reviewer",
                                        source_role_thread_id=None,
                                        role="Reviewer",
                                        protocol_source_thread_id="parent-manager-thread"):
        review_task_id = task_id or self.task_id
        review_source_role_thread_id = source_role_thread_id or source_thread_id
        return (
            "<codex_delegation>\n"
            "  <source_thread_id>%s</source_thread_id>\n"
            "  <input>TEAM_ROUTER_REVIEW taskId=%s\n"
            "sourceThreadId: %s\n"
            "role: %s\n"
            "sourceRoleThreadId: %s\n"
            "result: %s\n"
            "summary: review result\n"
            "findings: focused check\n"
            "requiredChanges: none\n"
            "evidenceChecked: tests\n"
            "risks: none</input>\n"
            "</codex_delegation>"
        ) % (source_thread_id, review_task_id, protocol_source_thread_id, role, review_source_role_thread_id, result)

    def test_watch_reviewer_direct_return_rejects_wrong_protocol_source_thread_id(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper(
                    "pass",
                    source_thread_id="thread-reviewer",
                    source_role_thread_id="thread-reviewer",
                    protocol_source_thread_id="wrong-parent-thread",
                ),
            },
        ]
        adapter.messages["thread-reviewer"] = [
            {"messageId": "msg-review", "sentAt": "2026-06-22T20:05:00+08:00", "text": "review request"},
            {
                "messageId": "msg-review-fallback",
                "sentAt": "2026-06-22T20:06:30+08:00",
                "text": (
                    "TEAM_ROUTER_REVIEW taskId=%s\n"
                    "result: pass\n"
                    "summary: fallback review\n"
                    "findings: fallback evidence\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: reviewer self-thread\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["summary"], "fallback review")
        self.assertEqual(
            update["ledger"]["review"]["result"]["receipt"]["source"],
            "self-thread-fallback/read_thread",
        )
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertIn("sourceThreadId", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["returnThreadId"], "parent-manager-thread")

    def test_reviewer_pass_sends_verifier_request_and_needs_rework_or_blocked_stops(self):
        ledger = self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]
        reviewing = team_router.capture_executor_callback_from_read(
            self.root, self.project_id, self.task_id, callback_messages, captured_at="2026-06-22T20:04:00+08:00"
        )
        self.assertEqual(reviewing["status"], "reviewing")
        reviewing = team_router.record_reviewer_request_sent(
            self.root, self.project_id, self.task_id, reviewer_thread_id="thread-reviewer", sent_at="2026-06-22T20:05:00+08:00", message_id="msg-review"
        )
        review_request = reviewing["review"]["request"]
        pass_messages = [
            {"messageId": review_request["messageId"], "sentAt": review_request["sentAt"], "text": "review"},
            {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]
        passed = team_router.capture_reviewer_review_from_read(
            self.root, self.project_id, self.task_id, pass_messages, captured_at="2026-06-22T20:07:00+08:00"
        )
        self.assertEqual(passed["status"], "verifying")
        self.assertEqual(passed["review"]["result"]["fields"]["result"], "pass")

        self.tearDown(); self.setUp()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(self.root, self.project_id, {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}}, "2026-06-22T20:02:30+08:00")
        team_router.capture_executor_callback_from_read(self.root, self.project_id, self.task_id, callback_messages, captured_at="2026-06-22T20:04:00+08:00")
        team_router.record_reviewer_request_sent(self.root, self.project_id, self.task_id, reviewer_thread_id="thread-reviewer", sent_at="2026-06-22T20:05:00+08:00", message_id="msg-review")
        rework = team_router.capture_reviewer_review_from_read(
            self.root, self.project_id, self.task_id, [pass_messages[0], {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: gap\nfindings: missing test\nrequiredChanges: add test\nevidenceChecked: tests\nrisks: none"}], captured_at="2026-06-22T20:07:00+08:00"
        )
        self.assertEqual(rework["status"], "needs_rework")

        self.tearDown(); self.setUp()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(self.root, self.project_id, {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}}, "2026-06-22T20:02:30+08:00")
        team_router.capture_executor_callback_from_read(self.root, self.project_id, self.task_id, callback_messages, captured_at="2026-06-22T20:04:00+08:00")
        team_router.record_reviewer_request_sent(self.root, self.project_id, self.task_id, reviewer_thread_id="thread-reviewer", sent_at="2026-06-22T20:05:00+08:00", message_id="msg-review")
        blocked = team_router.capture_reviewer_review_from_read(
            self.root, self.project_id, self.task_id, [pass_messages[0], {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: blocked\nsummary: blocked\nfindings: unsafe\nrequiredChanges: redesign\nevidenceChecked: tests\nrisks: high"}], captured_at="2026-06-22T20:07:00+08:00"
        )
        self.assertEqual(blocked["status"], "blocked")

    def test_plain_local_package_callback_routes_to_reviewer_before_verifier(self):
        adapter = FakeThreadAdapter()
        ledger = self._awaiting_callback_ledger()
        ledger["objective"] = "update local helper behavior"
        ledger["plan"]["fields"].update({
            "acknowledgedPermission": "local-package",
            "scope": "src/local_helper.py",
            "riskBoundary": "ordinary implementation task",
            "executorPrompt": "adjust helper behavior",
            "notes": "single ordinary task without review-routing markers",
        })
        ledger["dispatches"][-1]["permission"] = "local-package"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: helper updated\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "reviewing")
        self.assertEqual(updated["gateClass"], "STRICT")
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_verifier_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="local-package",
                sent_at="2026-06-22T20:05:00+08:00",
            )
        self.assertIn("not ready for verifier", str(ctx.exception))

        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:04:30+08:00",
        )
        reviewing = team_router.send_reviewer_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="local-package",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        self.assertEqual(reviewing["status"], "reviewing")
        self.assertEqual(reviewing["review"]["request"]["threadId"], "thread-reviewer")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-reviewer")
        self.assertIn("permission: local-package", adapter.sent[-1]["kwargs"]["prompt"])

    def test_read_only_plain_low_risk_callback_still_routes_to_verifier(self):
        ledger = self._awaiting_callback_ledger()
        ledger["objective"] = "update local helper behavior"
        ledger["plan"]["fields"].update({
            "acknowledgedPermission": "read-only",
            "scope": "src/local_helper.py",
            "riskBoundary": "ordinary read-only inspection",
            "executorPrompt": "inspect helper behavior",
            "notes": "single ordinary task without review-routing markers",
        })
        ledger["dispatches"][-1]["permission"] = "read-only"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: inspected\nevidence: tests\nrisks: none\nnext: verifier"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["gateClass"], "NORMAL")

        adapter = FakeThreadAdapter()
        team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        verifier_prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("riskBoundary: ordinary read-only inspection", verifier_prompt)
        self.assertNotIn("Review package metadata", verifier_prompt)
        self.assertNotIn("reviewPackagePath:", verifier_prompt)
        self.assertNotIn("inlineFallback:", verifier_prompt)
        self.assertNotIn("审查者结果上下文：", verifier_prompt)

    def test_reviewer_request_rejects_fast_gate_callback(self):
        adapter = FakeThreadAdapter()
        ledger = self._awaiting_callback_ledger()
        ledger["objective"] = "restore README BOM"
        ledger["plan"]["fields"]["scope"] = "README.md"
        ledger["plan"]["fields"]["riskBoundary"] = "docs-only encoding rework"
        ledger["plan"]["fields"]["executorPrompt"] = "restore UTF-8 BOM only"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: bom restored\nevidence: tests\nrisks: none\nnext: verifier"},
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_reviewer_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:05:00+08:00",
            )

        self.assertIn("reviewer gate is not required", str(ctx.exception))
        self.assertIn("FAST", str(ctx.exception))

    def test_reviewer_gate_without_role_thread_requires_role_conversation_not_subagent(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]
        team_router.capture_executor_callback_from_read(self.root, self.project_id, self.task_id, messages, captured_at="2026-06-22T20:04:00+08:00")

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_reviewer_request_with_adapter(
                self.root, self.project_id, self.task_id, thread_adapter=adapter, permission="read-only", sent_at="2026-06-22T20:05:00+08:00"
            )
        self.assertIn("reviewer role conversation", str(ctx.exception))
        self.assertIn("subagent fallback is not allowed", str(ctx.exception))

    def test_verifier_request_includes_reviewer_result_context_for_reviewer_gated_flow(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            callback_messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        reviewing = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
        )
        review_request = reviewing["review"]["request"]
        review_messages = [
            {"messageId": review_request["messageId"], "sentAt": review_request["sentAt"], "text": "review"},
            {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nfindings: none\nrequiredChanges: confirm regression tests\nevidenceChecked: tests\nrisks: none"},
        ]
        passed = team_router.capture_reviewer_review_from_read(
            self.root,
            self.project_id,
            self.task_id,
            review_messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(passed["status"], "verifying")

        team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:08:00+08:00",
        )

        verifier_prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("审查者结果上下文：", verifier_prompt)
        self.assertIn("验证者返回 pass 前，必须确认 reviewer requiredChanges 已满足。", verifier_prompt)
        self.assertIn("TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3", verifier_prompt)
        self.assertIn("requiredChanges: confirm regression tests", verifier_prompt)


    def test_send_verifier_request_with_adapter_without_reviewer_result_does_not_offer_evidence_only_fast_path(self):
        adapter = FakeThreadAdapter()
        self._verifying_ledger()

        team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        verifier_prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertNotIn("本次验证可考虑 evidence-only fast path。", verifier_prompt)
        self.assertNotIn("不重新运行命令，也不扩大检查范围", verifier_prompt)

    def test_send_verifier_request_with_adapter_offers_evidence_only_fast_path_after_clean_reviewer_pass(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests passed\nrisks: none\nnext: reviewer"},
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            callback_messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        reviewing = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
        )
        review_request = reviewing["review"]["request"]
        team_router.capture_reviewer_review_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": review_request["messageId"], "sentAt": review_request["sentAt"], "text": "review"},
                {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )

        team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="local-package",
            sent_at="2026-06-22T20:08:00+08:00",
        )

        verifier_prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("本次验证可考虑 evidence-only fast path。", verifier_prompt)
        self.assertIn("如果执行者 evidence 加 reviewer result 已足够覆盖授权范围", verifier_prompt)
        self.assertIn("不重新运行命令，也不扩大检查范围", verifier_prompt)
        self.assertNotIn("Evidence-only fast path is allowed for this verification.", verifier_prompt)

    def test_verifier_request_mentions_evidence_only_fast_path_when_reviewer_passes_cleanly(self):
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\n"
            "status: done\n"
            "final: true\n"
            "summary: implemented\n"
            "evidence: tests passed\n"
            "risks: none\n"
            "next: verifier"
        )
        reviewer_result = {
            "fields": {
                "result": "pass",
                "summary": "ok",
                "findings": "none",
                "requiredChanges": "none",
                "evidenceChecked": "tests",
                "risks": "none",
            }
        }

        verifier_prompt = team_router.make_verifier_request_message(
            "ctr-20260622-160000-a7f3",
            callback_block,
            "local-package",
            "narrow Team Router stability fix",
            reviewer_result=reviewer_result,
        )

        self.assertIn("本次验证可考虑 evidence-only fast path。", verifier_prompt)
        self.assertIn("如果执行者 evidence 加 reviewer result 已足够覆盖授权范围", verifier_prompt)
        self.assertIn("不重新运行命令，也不扩大检查范围", verifier_prompt)
        self.assertNotIn("Evidence-only fast path is allowed for this verification.", verifier_prompt)
        self.assertIn("stage/commit/push/PR/release 未执行", verifier_prompt)

    def test_verifier_request_without_reviewer_result_does_not_offer_evidence_only_fast_path(self):
        callback_block = (
            "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\n"
            "status: done\n"
            "final: true\n"
            "summary: implemented\n"
            "evidence: tests passed\n"
            "risks: none\n"
            "next: verifier"
        )

        verifier_prompt = team_router.make_verifier_request_message(
            "ctr-20260622-160000-a7f3",
            callback_block,
            "local-package",
            "narrow Team Router stability fix",
            reviewer_result=None,
        )

        self.assertNotIn("本次验证可考虑 evidence-only fast path。", verifier_prompt)
        self.assertNotIn("不重新运行命令，也不扩大检查范围", verifier_prompt)
    def test_verifier_accepted_closeout_adds_auto_stop_and_plain_language_metadata(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        accepted = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
{"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: accepted fast\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(accepted["status"], "done")
        self.assertEqual(accepted["closeout"]["status"], "accepted")
        self.assertEqual(accepted["closeout"]["watcherAction"], "stop_and_delete_heartbeat")
        self.assertIn("plain language", accepted["closeout"]["reportAction"])
        self.assertIn("stage/commit/push/PR/publish/release were not done", accepted["closeout"]["notDone"])
        self.assertEqual(accepted["closeout"]["receiptSource"], "self-thread-fallback/read_thread")
        self.assertEqual(accepted["closeout"]["receiptChannel"], "read_thread")
        self.assertNotIn("watcher", accepted)
        registry = team_router.load_registry(self.root, self.project_id)
        closeout = team_router.format_closeout_for_user(accepted, registry)
        self.assertIn("heartbeatAction: stop_and_delete_heartbeat", closeout)
        self.assertIn("plainLanguageReport: required", closeout)
        self.assertIn("notDone: stage/commit/push/PR/publish/release were not done", closeout)
        self.assertIn("receiptSource: self-thread-fallback/read_thread", closeout)
        self.assertIn("receiptChannel: read_thread", closeout)

    def test_verifier_needs_rework_does_not_produce_accepted_closeout_action(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        needs_rework = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
{"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: more work\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(needs_rework["status"], "needs_rework")
        self.assertNotIn("watcherAction", needs_rework["closeout"])

    def test_verifier_pass_writes_verification_and_closeout(self):
        ledger = self._verifying_ledger()
        verify_message = team_router.make_verifier_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
        )
        self.assertIn("TEAM_ROUTER_VERIFY taskId=ctr-20260622-160000-a7f3", verify_message)

        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        registry = team_router.load_registry(self.root, self.project_id)
        read_request = team_router.recovery_read_request(requested, registry, "verifier")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-verify")

        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]
        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["verification"]["verdict"]["fields"]["result"], "pass")
        self.assertEqual(updated["closeout"]["status"], "accepted")
        self.assertEqual(updated["closeout"]["remainingTodos"], "none")

    def test_verifier_request_supports_direct_return_delivery_metadata(self):
        ledger = self._verifying_ledger()

        verify_message = team_router.make_verifier_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
            return_thread_id="parent-manager-thread",
            role_thread_id="thread-verifier",
        )

        self.assertIn("sourceThreadId: parent-manager-thread", verify_message)
        self.assertIn("sourceRoleThreadId: thread-verifier", verify_message)
        self.assertIn("role: Verifier", verify_message)
        self.assertIn("returnThreadId: parent-manager-thread", verify_message)
        self.assertIn("orchestratorThreadId: parent-manager-thread", verify_message)
        self.assertIn("roleThreadId: thread-verifier", verify_message)
        self.assertIn("verdictDelivery: direct-send", verify_message)
        self.assertIn("verdictFallback: self-thread-marker", verify_message)
        self.assertIn(
            "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
            verify_message,
        )
        self.assertIn(
            "Then print the same full TEAM_ROUTER_* block in this thread as fallback.",
            verify_message,
        )
        self.assertIn("returnContract: hard-direct-return", verify_message)
        self.assertIn("直接回传校验字段：taskId, role, sourceThreadId, sourceRoleThreadId。", verify_message)
        self.assertIn(
            "直接回传 fallback metadata：deliveryStatus: fallback_only; deliveryError: <仅 direct-send 失败时填写短错误>。",
            verify_message,
        )
        self.assertIn("deliveryStatus: fallback_only", verify_message)
        self.assertIn("deliveryError", verify_message)
        self.assertNotIn("short error only when direct-send failed", verify_message)
        self.assertIn("callbackMarker: TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3", verify_message)

        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        request = requested["verification"]["request"]
        self.assertEqual(request["returnThreadId"], "parent-manager-thread")
        self.assertEqual(request["orchestratorThreadId"], "parent-manager-thread")
        self.assertEqual(request["roleThreadId"], "thread-verifier")
        self.assertEqual(request["verdictDelivery"], "direct-send")
        self.assertEqual(request["verdictFallback"], "self-thread-marker")
        self.assertEqual(request["fallbackSearchAnchor"], request["searchAnchor"])
        self.assertEqual(requested["status"], "verifying")

    def test_reviewer_request_supports_direct_return_delivery_metadata(self):
        ledger = self._verifying_ledger()

        review_message = team_router.make_reviewer_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
            return_thread_id="parent-manager-thread",
            role_thread_id="thread-reviewer",
        )

        self.assertIn("sourceThreadId: parent-manager-thread", review_message)
        self.assertIn("sourceRoleThreadId: thread-reviewer", review_message)
        self.assertIn("role: Reviewer", review_message)
        self.assertIn("returnThreadId: parent-manager-thread", review_message)
        self.assertIn("orchestratorThreadId: parent-manager-thread", review_message)
        self.assertIn("roleThreadId: thread-reviewer", review_message)
        self.assertIn("reviewDelivery: direct-send", review_message)
        self.assertIn("reviewFallback: self-thread-marker", review_message)
        self.assertIn(
            "MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)",
            review_message,
        )
        self.assertIn(
            "Then print the same full TEAM_ROUTER_* block in this thread as fallback.",
            review_message,
        )
        self.assertIn("returnContract: hard-direct-return", review_message)
        self.assertIn("直接回传校验字段：taskId, role, sourceThreadId, sourceRoleThreadId。", review_message)
        self.assertIn(
            "直接回传 fallback metadata：deliveryStatus: fallback_only; deliveryError: <仅 direct-send 失败时填写短错误>。",
            review_message,
        )
        self.assertIn("deliveryStatus: fallback_only", review_message)
        self.assertIn("deliveryError", review_message)
        self.assertNotIn("short error only when direct-send failed", review_message)
        self.assertIn("reviewMarker: TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3", review_message)
        self.assertIn("callbackMarker: TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3", review_message)
        self.assertIn("reviewerMode: read-only/adversarial", review_message)

        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {
                "reviewer": {
                    "threadId": "thread-reviewer",
                    "title": "审查者-test",
                }
            },
            "2026-06-22T20:04:30+08:00",
        )
        requested = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        request = requested["review"]["request"]
        self.assertEqual(request["returnThreadId"], "parent-manager-thread")
        self.assertEqual(request["orchestratorThreadId"], "parent-manager-thread")
        self.assertEqual(request["roleThreadId"], "thread-reviewer")
        self.assertEqual(request["reviewDelivery"], "direct-send")
        self.assertEqual(request["reviewFallback"], "self-thread-marker")
        self.assertEqual(request["fallbackSearchAnchor"], request["searchAnchor"])
        self.assertEqual(requested["status"], "reviewing")

        registry = team_router.load_registry(self.root, self.project_id)
        read_request = team_router.recovery_read_request(requested, registry, "reviewer")
        self.assertEqual(read_request["threadId"], "thread-reviewer")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-review")
        self.assertEqual(read_request["expectedCallback"], "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3")

    def test_verifier_capture_accepts_same_timestamp_response_for_time_only_anchor(self):
        ledger = self._verifying_ledger()
        verify_prompt = team_router.make_verifier_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
        )
        ledger = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "type": "userMessage",
                "sentAt": "2026-06-22T20:05:00+08:00",
                "text": verify_prompt,
            },
            {
                "type": "agentMessage",
                "sentAt": "2026-06-22T20:05:00+08:00",
                "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: same second\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none",
            },
        ]

        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["closeout"]["summary"], "same second")

    def test_verifier_needs_rework_respects_max_rework(self):
        ledger = self._verifying_ledger(max_rework=0)
        team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
        ]

        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "blocked")
        self.assertEqual(updated["closeout"]["status"], "blocked")
        self.assertEqual(updated["closeout"]["nextAction"], "fix docs")
        self.assertEqual(updated["closeout"]["remainingTodos"], "fix docs")

    def test_terminal_task_cannot_be_redispatched(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )

        with self.assertRaises(team_router.StateStoreError):
            team_router.record_executor_dispatch_sent(
                self.root,
                self.project_id,
                ledger["taskId"],
                executor_thread_id="thread-executor",
                sent_at="2026-06-22T20:08:00+08:00",
                message_id="msg-again",
            )

        saved = team_router.load_task_ledger(self.root, self.project_id, ledger["taskId"])
        self.assertEqual(saved["status"], "done")
        self.assertEqual(len(saved["dispatches"]), 1)

    def test_done_verifier_capture_is_idempotent(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        observation_count = len(done["observations"])

        repeated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(repeated["status"], "done")
        self.assertEqual(len(repeated["observations"]), observation_count)
        self.assertEqual(repeated["closeout"]["capturedAt"], "2026-06-22T20:07:00+08:00")

    def test_blocked_terminal_task_rejects_guarded_manager_executor_verifier_actions(self):
        plan_ledger = self._awaiting_plan_ledger()
        plan_ledger["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, plan_ledger["taskId"], plan_ledger)
        with self.assertRaises(team_router.StateStoreError):
            team_router.record_plan_request_sent(
                self.root,
                self.project_id,
                plan_ledger["taskId"],
                manager_thread_id="thread-manager",
                sent_at="2026-06-22T20:09:00+08:00",
                message_id="msg-plan-again",
            )
        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_manager_plan_from_read(
                self.root,
                self.project_id,
                plan_ledger["taskId"],
                [{"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"}],
                captured_at="2026-06-22T20:09:00+08:00",
            )

        self.tearDown()
        self.setUp()
        callback_ledger = self._awaiting_callback_ledger()
        callback_ledger["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, callback_ledger["taskId"], callback_ledger)
        with self.assertRaises(team_router.StateStoreError):
            team_router.record_executor_dispatch_sent(
                self.root,
                self.project_id,
                callback_ledger["taskId"],
                executor_thread_id="thread-executor",
                sent_at="2026-06-22T20:09:00+08:00",
                message_id="msg-dispatch-again",
            )
        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_executor_callback_from_read(
                self.root,
                self.project_id,
                callback_ledger["taskId"],
                [{"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"}],
                captured_at="2026-06-22T20:09:00+08:00",
            )

        self.tearDown()
        self.setUp()
        verifier_ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            verifier_ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        verifier_ledger = team_router.load_task_ledger(self.root, self.project_id, verifier_ledger["taskId"])
        verifier_ledger["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, verifier_ledger["taskId"], verifier_ledger)
        with self.assertRaises(team_router.StateStoreError):
            team_router.record_verifier_request_sent(
                self.root,
                self.project_id,
                verifier_ledger["taskId"],
                verifier_thread_id="thread-verifier",
                sent_at="2026-06-22T20:09:00+08:00",
                message_id="msg-verify-again",
            )
        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_verifier_verdict_from_read(
                self.root,
                self.project_id,
                verifier_ledger["taskId"],
                [{"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"}],
                captured_at="2026-06-22T20:09:00+08:00",
            )

    def test_escalation_required_blocks_executor_dispatch(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: escalation-required\nscope: src\nstopWhen: done\nriskBoundary: needs write access\nexecutorPrompt: inspect src\nnotes: none" % ledger["taskId"]},
        ]
        blocked = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        with self.assertRaises(team_router.StateStoreError):
            team_router.record_executor_dispatch_sent(
                self.root,
                self.project_id,
                ledger["taskId"],
                executor_thread_id="thread-executor",
                sent_at="2026-06-22T20:02:00+08:00",
                message_id="msg-dispatch",
            )
        self.assertEqual(blocked["dispatches"], [])

    def test_sent_at_fallback_ignores_anchor_message_template(self):
        self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_DISPATCH taskId=ctr-20260622-160000-a7f3\nTEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done | blocked\nfinal: true\nsummary: <3-7 lines>\nevidence: <evidence>\nrisks: <risks>\nnext: <next>",
            },
            {
                "sentAt": "2026-06-22T20:02:30+08:00",
                "text": "still working",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_callback")

    def test_plan_sent_at_fallback_ignores_request_template(self):
        ledger = self._ready_ledger()
        team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:01:00+08:00",
                "text": team_router.make_plan_request_message(ledger["taskId"], ledger["objective"], "read-only"),
            },
            {
                "sentAt": "2026-06-22T20:01:30+08:00",
                "text": "still planning",
            },
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_plan")

    def test_verifier_sent_at_fallback_ignores_request_template(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:05:00+08:00",
                "text": team_router.make_verifier_request_message(
                    ledger["taskId"],
                    ledger["observations"][-1]["content"],
                    "read-only",
                    "src",
                ),
            },
            {
                "sentAt": "2026-06-22T20:05:30+08:00",
                "text": "still verifying",
            },
        ]

        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:06:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")

    def test_same_timestamp_callback_without_message_id_is_captured(self):
        self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: same timestamp\nevidence: tests\nrisks: none\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "same timestamp")

    def test_rework_redispatch_can_finish_with_fresh_closeout(self):
        ledger = self._verifying_ledger(max_rework=2)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        needs_rework = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["closeout"]["status"], "needs_rework")

        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:08:00+08:00",
            message_id="msg-rework",
        )
        verifying = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-rework", "sentAt": "2026-06-22T20:08:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback-2", "sentAt": "2026-06-22T20:09:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: fixed\nevidence: tests\nrisks: none\nnext: none"},
            ],
            captured_at="2026-06-22T20:09:30+08:00",
        )
        self.assertEqual(verifying["status"], "verifying")
        self.assertIsNone(verifying["closeout"])
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:10:00+08:00",
            message_id="msg-verify-2",
        )

        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify-2", "sentAt": "2026-06-22T20:10:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict-2", "sentAt": "2026-06-22T20:11:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok after rework\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:11:30+08:00",
        )

        self.assertEqual(done["status"], "done")
        self.assertEqual(done["closeout"]["status"], "accepted")
        self.assertEqual(done["closeout"]["summary"], "ok after rework")

    def test_manager_capture_requires_plan_request_anchor(self):
        ledger = self._ready_ledger()
        ledger["planRequest"] = None
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=ctr-20260622-160000-a7f3\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none"},
        ]

        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_manager_plan_from_read(
                self.root,
                self.project_id,
                self.task_id,
                messages,
                captured_at="2026-06-22T20:01:40+08:00",
            )

    def test_verifier_capture_requires_verification_request_anchor(self):
        ledger = self._verifying_ledger()
        ledger["verification"] = None
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]

        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_verifier_verdict_from_read(
                self.root,
                self.project_id,
                self.task_id,
                messages,
                captured_at="2026-06-22T20:07:00+08:00",
            )

    def test_confirm_rework_dispatch_increments_rework_count(self):
        ledger = self._verifying_ledger(max_rework=2)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
        ]
        needs_rework = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["status"], "needs_rework")

        dispatched = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:08:00+08:00",
            message_id="msg-rework",
        )

        self.assertEqual(dispatched["status"], "awaiting_callback")
        self.assertEqual(dispatched["reworkCount"], 1)
        self.assertEqual(dispatched["dispatches"][-1]["attempt"], 2)
        self.assertIsNone(dispatched["closeout"])

    def test_old_task_ledger_normalizes_plan_fields(self):
        path = team_router.task_path(self.root, self.project_id, self.task_id)
        path.parent.mkdir(parents=True)
        path.write_text('{"objective":"inspect docs"}', encoding="utf-8")

        ledger = team_router.load_task_ledger(self.root, self.project_id, self.task_id)

        self.assertIn("planRequest", ledger)
        self.assertIsNone(ledger["planRequest"])
        self.assertIn("plan", ledger)
        self.assertIsNone(ledger["plan"])
    def test_task_ledger_normalizes_architecture_and_qa_review_fields(self):
        path = team_router.task_path(self.root, self.project_id, self.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "taskId": self.task_id,
            "projectId": self.project_id,
            "status": "awaiting_architect_review",
            "architectureReview": {"request": {"threadId": "thread-architect"}},
            "qaReview": {"request": {"threadId": "thread-qa"}},
        }), encoding="utf-8")

        ledger = team_router.load_task_ledger(self.root, self.project_id, self.task_id)

        self.assertEqual(ledger["architectureReview"]["request"]["threadId"], "thread-architect")
        self.assertEqual(ledger["qaReview"]["request"]["threadId"], "thread-qa")

    def test_architect_review_request_prompt_contains_direct_return_contract(self):
        message = team_router.make_architect_review_request_message(
            task_id=self.task_id,
            objective="change state-machine protocol",
            scope="Team Router state machine",
            return_thread_id="parent-manager-thread",
            role_thread_id="thread-architect",
            plan_fields={"riskBoundary": "direct-return"},
        )

        for needle in (
            "TEAM_ROUTER_ARCHITECT_REVIEW",
            "sourceThreadId: parent-manager-thread",
            "sourceRoleThreadId: thread-architect",
            "role: Architect",
            "skillProfileUsed: architect-default",
            "architectureImpact:",
            "compatibilityNotes:",
            "alternatives:",
            "migrationRisks:",
            "architectReviewDelivery: direct-send",
            "architectReviewFallback: self-thread-marker",
            "send_message_to_thread(threadId=<returnThreadId>",
            "manual orchestration fallback",
        ):
            self.assertIn(needle, message)

    def test_qa_review_request_prompt_contains_direct_return_contract(self):
        message = team_router.make_qa_review_request_message(
            task_id=self.task_id,
            executor_callback=(
                "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\n"
                "summary: ok\nevidence: tests\nrisks: none\nnext: qa" % self.task_id
            ),
            scope="Team Router verifier gating",
            return_thread_id="parent-manager-thread",
            role_thread_id="thread-qa",
            plan_fields={"riskBoundary": "regression"},
            reviewer_result={"fields": {"result": "pass", "summary": "ok"}},
        )

        for needle in (
            "TEAM_ROUTER_QA_REVIEW",
            "sourceThreadId: parent-manager-thread",
            "sourceRoleThreadId: thread-qa",
            "role: QA",
            "skillProfileUsed: qa-default",
            "coverageGaps:",
            "verificationPlan:",
            "regressionRisks:",
            "qaReviewDelivery: direct-send",
            "qaReviewFallback: self-thread-marker",
            "send_message_to_thread(threadId=<returnThreadId>",
            "manual orchestration fallback",
        ):
            self.assertIn(needle, message)

    def test_send_architect_review_request_records_direct_return_metadata(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        ledger["objective"] = "change shared protocol contract"
        ledger["plan"]["fields"].update({
            "scope": "src/team_router.py",
            "riskBoundary": "state-machine direct-return behavior",
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"architect": {"threadId": "thread-architect", "title": "架构师-test"}},
            "2026-06-22T20:02:30+08:00",
        )

        updated = team_router.send_architect_review_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
            return_thread_id="parent-manager-thread",
        )

        request = updated["architectureReview"]["request"]
        self.assertEqual(updated["status"], "awaiting_architect_review")
        self.assertEqual(request["role"], "architect")
        self.assertEqual(request["threadId"], "thread-architect")
        self.assertEqual(request["roleThreadId"], "thread-architect")
        self.assertEqual(request["sourceRoleThreadId"], "thread-architect")
        self.assertEqual(request["returnThreadId"], "parent-manager-thread")
        self.assertEqual(request["orchestratorThreadId"], "parent-manager-thread")
        self.assertEqual(request["expectedMarker"], "TEAM_ROUTER_ARCHITECT_REVIEW")
        self.assertEqual(request["expectedCallback"], "TEAM_ROUTER_ARCHITECT_REVIEW taskId=%s" % self.task_id)
        self.assertEqual(request["architectReviewDelivery"], "direct-send")
        self.assertEqual(request["architectReviewFallback"], "self-thread-marker")
        self.assertEqual(request["fallbackSearchAnchor"], request["searchAnchor"])
        self.assertEqual(request["returnSearchAnchor"]["sentAt"], request["sentAt"])
        self.assertEqual(updated["watcher"]["role"], "architect")
        self.assertEqual(updated["watcher"]["expectedMarker"], "TEAM_ROUTER_ARCHITECT_REVIEW taskId=%s" % self.task_id)
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-architect")
        self.assertIn("callbackMode: direct-return runtime", adapter.sent[-1]["kwargs"]["prompt"])

    def test_send_qa_review_request_records_direct_return_metadata(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        ledger["objective"] = "high regression risk with test matrix needed"
        ledger["plan"]["fields"].update({
            "scope": "src/team_router.py",
            "riskBoundary": "regression verification plan",
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"qa": {"threadId": "thread-qa", "title": "QA-test"}},
            "2026-06-22T20:04:30+08:00",
        )

        updated = team_router.send_qa_review_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
            return_thread_id="parent-manager-thread",
        )

        request = updated["qaReview"]["request"]
        self.assertEqual(updated["status"], "awaiting_qa_review")
        self.assertEqual(request["role"], "qa")
        self.assertEqual(request["threadId"], "thread-qa")
        self.assertEqual(request["sourceRoleThreadId"], "thread-qa")
        self.assertEqual(request["returnThreadId"], "parent-manager-thread")
        self.assertEqual(request["expectedMarker"], "TEAM_ROUTER_QA_REVIEW")
        self.assertEqual(request["qaReviewDelivery"], "direct-send")
        self.assertEqual(request["qaReviewFallback"], "self-thread-marker")
        self.assertEqual(updated["watcher"]["role"], "qa")
        self.assertIn("callbackMode: direct-return runtime", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertIn("以下是执行者 callback 原文：", adapter.sent[-1]["kwargs"]["prompt"])

    def _awaiting_architect_review_ledger(self, *, return_thread_id="parent-manager-thread", max_rework=3):
        ledger = self._planned_ledger(max_rework=max_rework)
        ledger["objective"] = "change shared protocol contract"
        ledger["plan"]["fields"].update({
            "scope": "src/team_router.py",
            "riskBoundary": "state-machine direct-return behavior",
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        return team_router.record_architect_review_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            architect_thread_id="thread-architect",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-architect-request",
            return_thread_id=return_thread_id,
        )

    def _awaiting_qa_review_ledger(self, *, return_thread_id="parent-manager-thread", max_rework=3):
        ledger = self._verifying_ledger(max_rework=max_rework)
        ledger["objective"] = "high regression risk with test matrix needed"
        ledger["plan"]["fields"].update({
            "scope": "src/team_router.py",
            "riskBoundary": "regression verification plan",
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        return team_router.record_qa_review_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            qa_thread_id="thread-qa",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-qa-request",
            return_thread_id=return_thread_id,
        )

    def _architect_review_block(self, result="pass", *, source_thread_id="parent-manager-thread", source_role_thread_id="thread-architect"):
        return """TEAM_ROUTER_ARCHITECT_REVIEW taskId=%s
result: %s
sourceThreadId: %s
sourceRoleThreadId: %s
role: Architect
summary: architecture checked
findings: none
requiredChanges: none
evidenceChecked: spec and plan
risks: none
skillProfileUsed: architect-default
architectureImpact: shared state machine
compatibilityNotes: compatible
alternatives: none
migrationRisks: low
""" % (self.task_id, result, source_thread_id, source_role_thread_id)

    def _qa_review_block(self, result="pass", *, source_thread_id="parent-manager-thread", source_role_thread_id="thread-qa"):
        return """TEAM_ROUTER_QA_REVIEW taskId=%s
result: %s
sourceThreadId: %s
sourceRoleThreadId: %s
role: QA
summary: qa checked
findings: none
requiredChanges: none
evidenceChecked: focused tests
risks: none
skillProfileUsed: qa-default
coverageGaps: direct-return stale cases
verificationPlan: py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v
regressionRisks: watcher transitions
""" % (self.task_id, result, source_thread_id, source_role_thread_id)

    def _direct_return_message(self, role_thread_id, text, *, message_id="msg-direct-return"):
        return {
            "messageId": message_id,
            "sentAt": "2026-06-22T20:06:00+08:00",
            "sourceThreadId": role_thread_id,
            "text": text,
        }

    def test_direct_return_record_and_capture_allowed_support_architect_and_qa(self):
        architect = self._awaiting_architect_review_ledger()
        self.assertEqual(
            team_router._direct_return_record(architect, "architect")["threadId"],
            "thread-architect",
        )
        self.assertTrue(team_router._direct_return_capture_allowed({"status": "awaiting_architect_review"}, "architect"))
        self.assertTrue(team_router._direct_return_capture_allowed({"status": "architect_review_unreachable"}, "architect"))
        self.assertFalse(team_router._direct_return_capture_allowed({"status": "awaiting_qa_review"}, "architect"))

        self.tearDown(); self.setUp()
        qa = self._awaiting_qa_review_ledger()
        self.assertEqual(
            team_router._direct_return_record(qa, "qa")["threadId"],
            "thread-qa",
        )
        self.assertTrue(team_router._direct_return_capture_allowed({"status": "awaiting_qa_review"}, "qa"))
        self.assertTrue(team_router._direct_return_capture_allowed({"status": "qa_review_unreachable"}, "qa"))
        self.assertFalse(team_router._direct_return_capture_allowed({"status": "planned"}, "qa"))

    def test_architect_pass_direct_return_records_result_and_returns_to_planned_without_dispatch(self):
        self._awaiting_architect_review_ledger()
        updated = team_router._capture_architect_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-architect", self._architect_review_block("pass"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "planned")
        self.assertEqual(updated["architectureReview"]["result"]["fields"]["result"], "pass")
        self.assertEqual(updated["dispatches"], [])
        self.assertEqual(updated["architectureReview"]["result"]["receipt"]["channel"], "manager-inbox")

    def test_architect_needs_rework_records_result_without_executor_rework_increment(self):
        self._awaiting_architect_review_ledger(max_rework=2)
        updated = team_router._capture_architect_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-architect", self._architect_review_block("needs_rework"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "architect_rework_pending")
        self.assertEqual(updated["reworkCount"], 0)
        self.assertEqual(updated["architectureReview"]["result"]["fields"]["architectureImpact"], "shared state machine")

    def test_architect_blocked_records_result_and_blocks_task(self):
        self._awaiting_architect_review_ledger()
        updated = team_router._capture_architect_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-architect", self._architect_review_block("blocked"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "blocked")
        self.assertEqual(updated["architectureReview"]["result"]["fields"]["result"], "blocked")

    def test_qa_pass_direct_return_records_result_and_returns_to_verifying(self):
        self._awaiting_qa_review_ledger()
        updated = team_router._capture_qa_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-qa", self._qa_review_block("pass"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["qaReview"]["result"]["fields"]["result"], "pass")
        self.assertEqual(updated["qaReview"]["result"]["receipt"]["channel"], "manager-inbox")

    def test_architect_required_executor_dispatch_rejects_before_architect_pass_without_send_or_rewrite(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        ledger["objective"] = "change shared protocol contract"
        ledger["plan"]["fields"].update({
            "scope": "src/team_router.py",
            "riskBoundary": "state-machine direct-return behavior",
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        before = team_router.load_task_ledger(self.root, self.project_id, self.task_id)

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_executor_dispatch_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:07:00+08:00",
                return_thread_id="parent-manager-thread",
            )

        self.assertIn("architect gate", str(ctx.exception))
        self.assertEqual(adapter.sent, [])
        after = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(after, before)

    def test_architect_pass_allows_required_executor_dispatch(self):
        adapter = FakeThreadAdapter()
        self._awaiting_architect_review_ledger()
        team_router._capture_architect_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-architect", self._architect_review_block("pass"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        updated = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:07:00+08:00",
            return_thread_id="parent-manager-thread",
        )

        self.assertEqual(updated["status"], "awaiting_callback")
        self.assertEqual(updated["dispatches"][-1]["threadId"], "thread-executor")
        self.assertEqual(len(adapter.sent), 1)

    def test_non_architect_executor_dispatch_remains_unchanged(self):
        adapter = FakeThreadAdapter()
        self._planned_ledger()

        updated = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_callback")
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-executor")

    def test_qa_required_verifier_request_rejects_before_qa_pass_without_send_or_rewrite(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        ledger["objective"] = "high regression risk with test strategy needed"
        ledger["plan"]["fields"].update({
            "scope": "src/team_router.py",
            "riskBoundary": "regression verification plan",
        })
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        before = team_router.load_task_ledger(self.root, self.project_id, self.task_id)

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_verifier_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:07:00+08:00",
                return_thread_id="parent-manager-thread",
            )

        self.assertIn("QA gate", str(ctx.exception))
        self.assertEqual(adapter.sent, [])
        after = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(after, before)

    def test_reviewer_pass_alone_does_not_bypass_required_qa_gate(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        ledger["objective"] = "high regression risk with test strategy needed"
        ledger["plan"]["fields"].update({
            "scope": "src/team_router.py",
            "riskBoundary": "regression verification plan",
        })
        ledger["review"] = {
            "result": {
                "fields": {
                    "result": "pass",
                    "summary": "reviewer passed",
                    "findings": "none",
                    "requiredChanges": "none",
                    "evidenceChecked": "tests",
                    "risks": "none",
                }
            }
        }
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_verifier_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:07:00+08:00",
                return_thread_id="parent-manager-thread",
            )

        self.assertIn("QA gate", str(ctx.exception))
        self.assertEqual(adapter.sent, [])

    def test_qa_pass_allows_required_verifier_request_and_includes_qa_context(self):
        adapter = FakeThreadAdapter()
        self._awaiting_qa_review_ledger()
        team_router._capture_qa_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-qa", self._qa_review_block("pass"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        updated = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:07:00+08:00",
            return_thread_id="parent-manager-thread",
        )

        self.assertEqual(updated["status"], "verifying")
        verifier_prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("QA review context:", verifier_prompt)
        self.assertIn("result: pass", verifier_prompt)
        self.assertIn("summary: qa checked", verifier_prompt)
        self.assertIn("coverageGaps: direct-return stale cases", verifier_prompt)
        self.assertIn("verificationPlan: py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v", verifier_prompt)
        self.assertIn("regressionRisks: watcher transitions", verifier_prompt)
        self.assertIn("evidenceChecked: focused tests", verifier_prompt)
        self.assertIn("risks: none", verifier_prompt)
    def test_qa_needs_rework_uses_existing_executor_rework_path_once(self):
        self._awaiting_qa_review_ledger(max_rework=2)
        updated = team_router._capture_qa_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-qa", self._qa_review_block("needs_rework"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "dispatched")
        self.assertEqual(updated["reworkCount"], 1)
        self.assertEqual(updated["qaReview"]["result"]["fields"]["coverageGaps"], "direct-return stale cases")

    def test_qa_blocked_records_result_and_blocks_task(self):
        self._awaiting_qa_review_ledger()
        updated = team_router._capture_qa_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-qa", self._qa_review_block("blocked"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "blocked")
        self.assertEqual(updated["qaReview"]["result"]["fields"]["result"], "blocked")

    def test_wrong_role_thread_direct_return_is_quarantined_without_state_advance(self):
        self._awaiting_architect_review_ledger()
        updated = team_router._capture_architect_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [
                self._direct_return_message(
                    "thread-architect",
                    self._architect_review_block("pass", source_role_thread_id="thread-other"),
                )
            ],
            captured_at="2026-06-22T20:06:30+08:00",
        )
        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)

        self.assertIsNone(updated)
        self.assertEqual(saved["status"], "awaiting_architect_review")
        self.assertEqual(saved["malformedDirectReturns"][-1]["role"], "architect")

    def test_stale_architect_direct_return_does_not_mutate_ledger(self):
        ledger = self._awaiting_architect_review_ledger()
        ledger["status"] = "planned"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

        updated = team_router._capture_architect_review_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            [self._direct_return_message("thread-architect", self._architect_review_block("pass"))],
            captured_at="2026-06-22T20:06:30+08:00",
        )
        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)

        self.assertIsNone(updated)
        self.assertEqual(saved["status"], "planned")
        self.assertNotIn("result", saved["architectureReview"])

    def _fallback_messages(self, request_message_id, text, *, source_thread_id):
        return [
            {"messageId": request_message_id, "sentAt": "2026-06-22T20:05:00+08:00", "text": "request"},
            {"messageId": "msg-fallback", "sentAt": "2026-06-22T20:06:00+08:00", "sourceThreadId": source_thread_id, "text": text},
        ]

    def test_architect_fallback_rejects_wrong_source_role_thread_without_state_advance(self):
        self._awaiting_architect_review_ledger(return_thread_id=None)
        updated = team_router.capture_architect_review_from_read(
            self.root,
            self.project_id,
            self.task_id,
            self._fallback_messages(
                "msg-architect-request",
                self._architect_review_block("pass", source_role_thread_id="thread-other"),
                source_thread_id="thread-architect",
            ),
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_architect_review")
        self.assertNotIn("result", updated["architectureReview"])
        self.assertEqual(updated["malformedDirectReturns"][-1]["role"], "architect")
        self.assertIn("sourceRoleThreadId", updated["malformedDirectReturns"][-1]["error"])

    def test_qa_fallback_rejects_wrong_source_thread_target_without_state_advance(self):
        self._awaiting_qa_review_ledger(return_thread_id=None)
        updated = team_router.capture_qa_review_from_read(
            self.root,
            self.project_id,
            self.task_id,
            self._fallback_messages(
                "msg-qa-request",
                self._qa_review_block("pass"),
                source_thread_id="thread-other",
            ),
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_qa_review")
        self.assertNotIn("result", updated["qaReview"])
        self.assertEqual(updated["malformedDirectReturns"][-1]["role"], "qa")
        self.assertIn("message sourceThreadId", updated["malformedDirectReturns"][-1]["error"])

    def test_architect_fallback_rejects_wrong_source_thread_id_field_without_state_advance(self):
        self._awaiting_architect_review_ledger(return_thread_id="parent-manager-thread")
        updated = team_router.capture_architect_review_from_read(
            self.root,
            self.project_id,
            self.task_id,
            self._fallback_messages(
                "msg-architect-request",
                self._architect_review_block("pass", source_thread_id="wrong-parent-thread"),
                source_thread_id="thread-architect",
            ),
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_architect_review")
        self.assertNotIn("result", updated["architectureReview"])
        self.assertEqual(updated["malformedDirectReturns"][-1]["role"], "architect")
        self.assertIn("sourceThreadId", updated["malformedDirectReturns"][-1]["error"])

    def test_stale_architect_fallback_does_not_mutate_ledger(self):
        ledger = self._awaiting_architect_review_ledger(return_thread_id=None)
        ledger["status"] = "planned"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

        updated = team_router.capture_architect_review_from_read(
            self.root,
            self.project_id,
            self.task_id,
            self._fallback_messages(
                "msg-architect-request",
                self._architect_review_block("pass"),
                source_thread_id="thread-architect",
            ),
            captured_at="2026-06-22T20:06:30+08:00",
        )

        self.assertEqual(updated["status"], "planned")
        self.assertNotIn("result", updated["architectureReview"])

    def test_watch_next_wakeup_has_no_execution_side_effect_code(self):
        source = (ROOT / "src" / "team_router.py").read_text(encoding="utf-8")
        start = source.index("def _watch_next_wakeup")
        end = source.index("def _watcher_read_allowed", start)
        body = source[start:end]
        for forbidden in (
            "thread_adapter",
            "turn_limit",
            "state_root",
            "project_id",
            "task_id",
            "observed_at",
            "finish(",
            "_capture_architect_review_from_manager_inbox",
            "read_architect_review_update_with_adapter",
        ):
            self.assertNotIn(forbidden, body)
    def test_architect_and_qa_fallback_capture_mark_unreachable_when_read_window_misses_anchor(self):
        architect = self._awaiting_architect_review_ledger(return_thread_id=None)
        updated_architect = team_router.capture_architect_review_from_read(
            self.root,
            self.project_id,
            architect["taskId"],
            [{"messageId": "msg-unrelated", "sentAt": "2026-06-22T20:06:00+08:00", "text": self._architect_review_block("pass")}],
            captured_at="2026-06-22T20:06:30+08:00",
        )
        self.assertEqual(updated_architect["status"], "architect_review_unreachable")

        self.tearDown(); self.setUp()
        qa = self._awaiting_qa_review_ledger(return_thread_id=None)
        updated_qa = team_router.capture_qa_review_from_read(
            self.root,
            self.project_id,
            qa["taskId"],
            [{"messageId": "msg-unrelated", "sentAt": "2026-06-22T20:06:00+08:00", "text": self._qa_review_block("pass")}],
            captured_at="2026-06-22T20:06:30+08:00",
        )
        self.assertEqual(updated_qa["status"], "qa_review_unreachable")

    def test_watch_prefers_manager_inbox_direct_return_before_self_thread_fallback(self):
        adapter = FakeThreadAdapter()
        self._awaiting_architect_review_ledger()
        adapter.messages["parent-manager-thread"] = [
            self._direct_return_message("thread-architect", self._architect_review_block("pass"))
        ]
        adapter.messages["thread-architect"] = [
            {"messageId": "msg-architect-request", "sentAt": "2026-06-22T20:05:00+08:00", "text": "request"},
            {"messageId": "msg-fallback", "sentAt": "2026-06-22T20:06:00+08:00", "text": self._architect_review_block("needs_rework")},
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:06:30+08:00",
            return_thread_id="parent-manager-thread",
        )

        self.assertEqual(update["ledger"]["status"], "planned")
        self.assertEqual(update["ledger"]["architectureReview"]["result"]["fields"]["result"], "pass")

    def test_architect_and_qa_review_requests_reject_when_gate_not_required_before_sending(self):
        adapter = FakeThreadAdapter()
        self._planned_ledger()
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_architect_review_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:05:00+08:00",
                return_thread_id="parent-manager-thread",
            )
        self.assertIn("architect gate is not required", str(ctx.exception))
        self.assertEqual(adapter.sent, [])

        self.tearDown(); self.setUp()
        adapter = FakeThreadAdapter()
        self._verifying_ledger()
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_qa_review_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:05:00+08:00",
                return_thread_id="parent-manager-thread",
            )
        self.assertIn("QA gate is not required", str(ctx.exception))
        self.assertEqual(adapter.sent, [])

    def test_architect_request_without_return_thread_is_manual_fallback_not_direct_return(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        ledger["objective"] = "change shared protocol contract"
        ledger["plan"]["fields"]["riskBoundary"] = "state-machine direct-return behavior"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"architect": {"threadId": "thread-architect", "title": "架构师-test"}},
            "2026-06-22T20:02:30+08:00",
        )

        updated = team_router.send_architect_review_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        request = updated["architectureReview"]["request"]
        self.assertIsNone(request["returnThreadId"])
        self.assertIsNone(request["orchestratorThreadId"])
        self.assertEqual(request["architectReviewDelivery"], "fallback_only")
        self.assertEqual(request["callbackMode"], "manual orchestration fallback")
        self.assertEqual(request["deliveryStatus"], "fallback_only")
        self.assertIn("returnThreadId unavailable", request["deliveryError"])
        self.assertIn("callbackMode: manual orchestration fallback", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertNotIn("architectReviewDelivery: direct-send", adapter.sent[-1]["kwargs"]["prompt"])

    def test_architect_review_request_rejects_wrong_nonterminal_states_without_rewind(self):
        rejected_statuses = (
            "awaiting_callback",
            "reviewing",
            "verifying",
            "awaiting_qa_review",
            "awaiting_architect_review",
        )
        for status in rejected_statuses:
            with self.subTest(status=status):
                self.tearDown(); self.setUp()
                adapter = FakeThreadAdapter()
                ledger = self._planned_ledger()
                ledger["objective"] = "change shared protocol contract"
                ledger["status"] = status
                ledger["plan"]["fields"].update({
                    "scope": "src/team_router.py",
                    "riskBoundary": "state-machine direct-return behavior",
                })
                ledger["architectureReview"] = None
                team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

                with self.assertRaises(team_router.StateStoreError) as ctx:
                    team_router.send_architect_review_request_with_adapter(
                        self.root,
                        self.project_id,
                        self.task_id,
                        thread_adapter=adapter,
                        permission="read-only",
                        sent_at="2026-06-22T20:05:00+08:00",
                        return_thread_id="parent-manager-thread",
                    )

                self.assertIn("architect review request is only allowed", str(ctx.exception))
                self.assertIn("current: %s" % status, str(ctx.exception))
                self.assertEqual(adapter.sent, [])
                saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
                self.assertEqual(saved["status"], status)
                self.assertIsNone(saved["architectureReview"])

    def test_qa_review_request_rejects_stale_callback_from_wrong_current_states(self):
        rejected_statuses = (
            "planned",
            "awaiting_callback",
            "reviewing",
            "architect_rework_pending",
            "awaiting_architect_review",
            "awaiting_qa_review",
        )
        for status in rejected_statuses:
            with self.subTest(status=status):
                self.tearDown(); self.setUp()
                adapter = FakeThreadAdapter()
                ledger = self._verifying_ledger()
                self.assertIsNotNone(team_router._latest_executor_callback_observation(ledger))
                ledger["objective"] = "high regression risk with test matrix needed"
                ledger["status"] = status
                ledger["plan"]["fields"].update({
                    "scope": "src/team_router.py",
                    "riskBoundary": "regression verification plan",
                })
                ledger["qaReview"] = None
                team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

                with self.assertRaises(team_router.StateStoreError) as ctx:
                    team_router.send_qa_review_request_with_adapter(
                        self.root,
                        self.project_id,
                        self.task_id,
                        thread_adapter=adapter,
                        permission="read-only",
                        sent_at="2026-06-22T20:05:00+08:00",
                        return_thread_id="parent-manager-thread",
                    )

                self.assertIn("QA review request is only allowed", str(ctx.exception))
                self.assertIn("current: %s" % status, str(ctx.exception))
                self.assertEqual(adapter.sent, [])
                saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
                self.assertEqual(saved["status"], status)
                self.assertIsNone(saved["qaReview"])
    def test_recovery_read_request_uses_registry_thread_when_ledger_lacks_thread_id(self):
        ledger = self._ready_ledger()
        ledger["planRequest"] = {
            "searchAnchor": {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00"},
            "expectedCallback": "TEAM_ROUTER_PLAN taskId=ctr-20260622-160000-a7f3",
        }
        registry = team_router.load_registry(self.root, self.project_id)

        read_request = team_router.recovery_read_request(ledger, registry, "manager")

        self.assertEqual(read_request["threadId"], "thread-manager")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-plan")

    def test_thread_send_anchor_normalizes_common_tool_shapes(self):
        direct = team_router.thread_send_anchor(
            {"messageId": "msg-direct", "sentAt": "2026-06-22T20:01:00+08:00"},
            fallback_sent_at="fallback",
        )
        nested = team_router.thread_send_anchor(
            {"message": {"id": "msg-nested", "createdAt": "2026-06-22T20:02:00+08:00"}},
            fallback_sent_at="fallback",
        )
        fallback = team_router.thread_send_anchor({}, fallback_sent_at="2026-06-22T20:03:00+08:00")

        self.assertEqual(direct, {"messageId": "msg-direct", "sentAt": "2026-06-22T20:01:00+08:00"})
        self.assertEqual(nested, {"messageId": "msg-nested", "sentAt": "2026-06-22T20:02:00+08:00"})
        self.assertEqual(fallback, {"messageId": None, "sentAt": "2026-06-22T20:03:00+08:00"})

    def test_create_thread_result_schema_accepts_common_thread_id_shapes(self):
        cases = [
            ({"threadId": "thread-a"}, "thread-a"),
            ({"thread_id": "thread-b"}, "thread-b"),
            ({"id": "thread-c"}, "thread-c"),
            ({"thread": {"id": "thread-d"}}, "thread-d"),
            ({"data": {"threadId": "thread-e"}}, "thread-e"),
            ({"result": {"thread_id": "thread-f"}}, "thread-f"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(team_router._thread_id_from_create_result(raw, "executor"), expected)

    def test_create_thread_result_schema_rejects_missing_thread_id(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router._thread_id_from_create_result({"thread": {"title": "Executor"}}, "executor")

        self.assertIn("create_thread result missing thread id", str(ctx.exception))

    def test_read_thread_result_schema_rejects_missing_messages_array(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.normalize_thread_read_messages({"thread": {"title": "Executor"}})

        self.assertIn("messages array", str(ctx.exception))

    def test_thread_adapter_capability_probe_reports_missing_tools(self):
        class MissingTitleAdapter(FakeThreadAdapter):
            set_thread_title = None

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.probe_thread_adapter_capabilities(MissingTitleAdapter())
        self.assertIn("list_projects", str(ctx.exception))
        self.assertIn("list_threads", str(ctx.exception))
        self.assertIn("set_thread_title", str(ctx.exception))
        self.assertNotIn("host adapter wrapper", str(ctx.exception))

        capabilities = team_router.probe_thread_adapter_capabilities(FullThreadAdapter())
        self.assertTrue(capabilities["create_thread"])
        self.assertTrue(capabilities["list_projects"])
        self.assertTrue(capabilities["list_threads"])
        self.assertTrue(capabilities["set_thread_title"])

    def test_parent_entry_guard_blocks_adapter_runner_without_callable_tools(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.parent_entry_guard(
                FakeThreadAdapter(),
                parent_thread_id="parent-manager-thread",
                heartbeat_scheduler=FakeHeartbeatScheduler(),
            )

        self.assertIn("adapter-created path unavailable", str(ctx.exception))
        self.assertIn("manual/pre-created continuation", str(ctx.exception))
        self.assertIn("callable list_projects", str(ctx.exception))

    def test_parent_entry_guard_allows_manual_precreated_when_adapter_unusable(self):
        entry = team_router.parent_entry_guard(
            FakeThreadAdapter(),
            precreated_roles=self.roles,
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=FakeHeartbeatScheduler(),
        )

        self.assertEqual(entry["path"], "manual-precreated")
        self.assertFalse(entry["adapterUsable"])
        self.assertIn("list_projects", entry["reason"])
        self.assertEqual(entry["readiness"]["status"], "blocked")
        self.assertIn("callable list_projects", entry["readiness"]["missing"])

    def test_parent_entry_guard_rejects_manual_precreated_without_thread_ids(self):
        invalid_roles = {
            "manager": {"title": "TeamRouter manager"},
            "executor": {"threadId": "thread-executor"},
            "verifier": {"threadId": "thread-verifier"},
        }

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.parent_entry_guard(precreated_roles=invalid_roles)

        self.assertIn("roles.manager.threadId", str(ctx.exception))

    def test_parent_entry_guard_accepts_full_callable_adapter_path(self):
        entry = team_router.parent_entry_guard(
            FullThreadAdapter(),
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=FakeHeartbeatScheduler(),
        )

        self.assertEqual(entry["path"], "adapter-created")
        self.assertTrue(entry["adapterUsable"])
        self.assertTrue(entry["capabilities"]["send_message_to_thread"])
        self.assertTrue(entry["capabilities"]["heartbeat_scheduler"])
        self.assertEqual(entry["readiness"]["status"], "ready")

    def test_parent_entry_guard_blocks_missing_parent_thread_id(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.parent_entry_guard(
                FullThreadAdapter(),
                heartbeat_scheduler=FakeHeartbeatScheduler(),
            )

        self.assertIn("adapter-created path unavailable", str(ctx.exception))
        self.assertIn("parent_thread_id", str(ctx.exception))

    def test_parent_entry_guard_blocks_non_callable_heartbeat_scheduler(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.parent_entry_guard(
                FullThreadAdapter(),
                parent_thread_id="parent-manager-thread",
                heartbeat_scheduler=True,
            )

        self.assertIn("adapter-created path unavailable", str(ctx.exception))
        self.assertIn("callable heartbeat scheduler", str(ctx.exception))

    def test_thread_adapter_capability_probe_rejects_model_tool_descriptors(self):
        descriptor_adapter = {
            tool_name: "codex_app.%s" % tool_name
            for tool_name in team_router.THREAD_TOOL_NAMES
        }

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.probe_thread_adapter_capabilities(descriptor_adapter)

        self.assertIn("in-process Python callables", str(ctx.exception))
        self.assertIn("model-side Codex app tool descriptors need a host adapter wrapper", str(ctx.exception))
        self.assertIn("list_projects", str(ctx.exception))

    def test_normalize_thread_read_messages_accepts_lists_nested_messages_and_turns(self):
        raw_list = team_router.normalize_thread_read_messages([
            {"id": "m1", "createdAt": "2026-06-22T20:01:00+08:00", "content": "hello"},
        ])
        nested = team_router.normalize_thread_read_messages({
            "thread": {"messages": [
                {"message_id": "m2", "timestamp": "2026-06-22T20:02:00+08:00", "summary": "nested"},
            ]},
        })
        turns = team_router.normalize_thread_read_messages({
            "turns": [
                {"id": "turn-1", "createdAt": "2026-06-22T20:03:00+08:00", "summary": "turn summary"},
            ],
        })

        self.assertEqual(raw_list[0]["messageId"], "m1")
        self.assertEqual(raw_list[0]["text"], "hello")
        self.assertEqual(nested[0]["messageId"], "m2")
        self.assertEqual(nested[0]["text"], "nested")
        self.assertEqual(turns[0]["messageId"], "turn-1")
        self.assertEqual(turns[0]["text"], "turn summary")

    def test_normalize_thread_read_messages_unwraps_result_and_content_blocks(self):
        messages = team_router.normalize_thread_read_messages({
            "result": {
                "messages": [
                    {
                        "id": "m1",
                        "createdAt": "2026-06-22T20:03:00+08:00",
                        "content": [
                            {"type": "text", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3"},
                            {"type": "text", "text": "status: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
                        ],
                    },
                ],
            },
        })

        self.assertEqual(messages[0]["messageId"], "m1")
        self.assertIn("TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", messages[0]["text"])
        self.assertIn("summary: ok", messages[0]["text"])

    def test_normalize_thread_read_messages_prefers_content_blocks_over_summary(self):
        messages = team_router.normalize_thread_read_messages({
            "messages": [
                {
                    "id": "m1",
                    "summary": "model summary without protocol marker",
                    "content": [
                        {"type": "text", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3"},
                        {"type": "text", "text": "status: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
                    ],
                },
            ],
        })

        self.assertIn("TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", messages[0]["text"])
        self.assertIn("summary: ok", messages[0]["text"])
        self.assertNotEqual(messages[0]["text"], "model summary without protocol marker")

    def test_normalize_thread_read_messages_flattens_codex_turn_items(self):
        messages = team_router.normalize_thread_read_messages({
            "turns": [
                {
                    "id": "turn-1",
                    "startedAt": "2026-06-22T20:03:00+08:00",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "item-user",
                            "content": [{"type": "text", "text": "request"}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "item-agent",
                            "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none",
                        },
                    ],
                },
            ],
        })

        self.assertEqual([msg["messageId"] for msg in messages], ["item-user", "item-agent"])
        self.assertEqual(messages[0]["sentAt"], "2026-06-22T20:03:00+08:00")
        self.assertIn("TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", messages[1]["text"])
        self.assertIn("summary: ok", messages[1]["text"])

    def test_normalize_thread_read_messages_accepts_live_codex_numeric_turn_timestamps(self):
        messages = team_router.normalize_thread_read_messages({
            "schemaVersion": 1,
            "thread": {"id": "thread-live", "status": {"type": "idle"}},
            "turns": [
                {
                    "id": "turn-live",
                    "startedAt": 1767225600,
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "item-user",
                            "content": [{"type": "text", "text": "TEAM_ROUTER_VERDICT request"}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "item-agent",
                            "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: live smoke\nevidenceChecked: thread tools\nrisks: none",
                        },
                    ],
                },
            ],
        })

        self.assertEqual(messages[0]["sentAt"], 1767225600)
        self.assertEqual(messages[1]["sentAt"], 1767225600)
        anchor = {"messageId": None, "sentAt": "2026-01-01T00:00:00+00:00"}
        self.assertTrue(team_router.read_window_covers_anchor(messages, anchor))
        filtered = team_router._messages_after_anchor(messages, anchor)
        self.assertEqual([msg["messageId"] for msg in filtered], ["item-agent"])

    def test_live_manager_inbox_direct_return_fixture_normalizes_source_thread(self):
        path = ROOT / "tests" / "fixtures" / "team_router" / "live_manager_inbox_direct_return.json"
        raw = json.loads(path.read_text(encoding="utf-8"))

        messages = team_router.normalize_thread_read_messages(raw)
        marker_messages = [
            msg for msg in messages
            if "TEAM_ROUTER_CALLBACK taskId=ctr-live-direct-fixture-1" in msg["text"]
        ]

        self.assertTrue(marker_messages)
        self.assertEqual(marker_messages[-1]["messageId"], "item-direct-callback")
        self.assertEqual(marker_messages[-1]["sentAt"], 1767225660)
        self.assertEqual(marker_messages[-1]["sourceThreadId"], "thread-executor-fixture")
        self.assertEqual(marker_messages[-1]["delegatedText"], marker_messages[-1]["text"])

    def test_live_read_thread_fixture_matches_normalizer_contract(self):
        path = ROOT / "tests" / "fixtures" / "team_router" / "live_read_thread_verdict.json"
        raw = json.loads(path.read_text(encoding="utf-8"))

        messages = team_router.normalize_thread_read_messages(raw)
        marker_messages = [
            msg for msg in messages
            if "TEAM_ROUTER_VERDICT taskId=ctr-live-smoke-fixture-1" in msg["text"]
        ]

        self.assertTrue(marker_messages)
        self.assertEqual(marker_messages[-1]["messageId"], "item-verdict")
        self.assertEqual(marker_messages[-1]["sentAt"], 1767225600)

    def test_adapter_send_wrappers_do_not_send_for_terminal_or_max_rework(self):
        adapter = FakeThreadAdapter()
        blocked = self._awaiting_plan_ledger()
        blocked["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, blocked)

        with self.assertRaises(team_router.StateStoreError):
            team_router.send_manager_plan_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:09:00+08:00",
            )
        self.assertEqual(adapter.sent, [])

        self.tearDown()
        self.setUp()
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger(max_rework=0)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        needs_rework = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["status"], "blocked")

        with self.assertRaises(team_router.StateStoreError):
            team_router.send_executor_dispatch_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:08:00+08:00",
            )
        self.assertEqual(adapter.sent, [])

    def test_create_role_threads_normalizes_created_titles_immediately(self):
        class NestedTitleAdapter(FakeThreadAdapter):
            def create_thread(self, **kwargs):
                prompt = kwargs["prompt"]
                role = "role"
                for line in prompt.splitlines():
                    match = re.match(r"^\s*role\s*:\s*(manager|executor|reviewer|verifier|architect|qa)\s*$", line, re.IGNORECASE)
                    if match:
                        role = match.group(1).lower()
                        break
                else:
                    for candidate in ("manager", "executor", "verifier", "reviewer"):
                        if candidate in prompt:
                            role = candidate
                            break
                thread_id = "thread-%s" % role
                self.messages[thread_id] = []
                return {"thread": {"id": thread_id, "title": "Nested %s title" % role}}

        adapter = NestedTitleAdapter()
        roles = team_router.create_role_threads_with_adapter(
            adapter,
            project_id=self.project_id,
            objective="Team Router title hardening",
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
            role_names=["manager", "executor", "reviewer", "verifier"],
        )

        self.assertEqual(roles["manager"]["title"], "规划者-Team Router title hardening")
        self.assertEqual(roles["executor"]["title"], "执行者-Team Router title hardening")
        self.assertEqual(roles["reviewer"]["title"], "审查者-Team Router title hardening")
        self.assertEqual(roles["verifier"]["title"], "验证者-Team Router title hardening")
        self.assertEqual(
            adapter.renamed,
            [
                {"threadId": "thread-executor", "title": "执行者-Team Router title hardening"},
                {"threadId": "thread-manager", "title": "规划者-Team Router title hardening"},
                {"threadId": "thread-reviewer", "title": "审查者-Team Router title hardening"},
                {"threadId": "thread-verifier", "title": "验证者-Team Router title hardening"},
            ],
        )

    def test_create_role_threads_with_adapter_blocks_create_when_discovery_finds_reusable_role(self):
        class DiscoveryBeforeCreateAdapter(FakeThreadAdapter):
            def list_threads(self, **kwargs):
                return {
                    "threads": [
                        {
                            "threadId": "live-executor",
                            "title": "TeamRouter executor - project-123",
                        },
                    ],
                }

            def create_thread(self, **kwargs):
                raise AssertionError("create_thread should not run before reusable role discovery")

        adapter = DiscoveryBeforeCreateAdapter()

        with self.assertRaisesRegex(
            team_router.StateStoreError,
            "role discovery must happen before create_thread",
        ) as caught:
            team_router.create_role_threads_with_adapter(
                adapter,
                project_id=self.project_id,
                objective="inspect docs",
                target={"type": "projectless"},
                observed_at="2026-06-22T20:00:00+08:00",
                role_names=["executor"],
            )

        self.assertIn("executor=live-executor", str(caught.exception))
        self.assertEqual(adapter.created, [])

    def test_reviewer_role_is_first_class_but_not_default_created(self):
        default_adapter = FakeThreadAdapter()
        default_roles = team_router.create_role_threads_with_adapter(
            default_adapter,
            project_id=self.project_id,
            objective="inspect docs",
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )
        self.assertEqual(sorted(default_roles), ["executor", "manager", "verifier"])
        self.assertNotIn("reviewer", default_roles)

        reviewer_adapter = FakeThreadAdapter()
        reviewer_roles = team_router.create_role_threads_with_adapter(
            reviewer_adapter,
            project_id=self.project_id,
            objective="inspect router protocol",
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
            role_names=["reviewer"],
        )
        self.assertEqual(sorted(reviewer_roles), ["reviewer"])
        self.assertEqual(reviewer_roles["reviewer"]["threadId"], "thread-reviewer")
        self.assertEqual(reviewer_roles["reviewer"]["title"], "审查者-inspect router protocol")
        self.assertIn(
            {"threadId": "thread-reviewer", "title": "审查者-inspect router protocol"},
            reviewer_adapter.renamed,
        )
        self.assertTrue(team_router.role_thread_title(self.project_id, "reviewer", "协议审查").startswith("审查者-"))

    def test_role_thread_title_supports_chinese_visible_task_titles_and_legacy_default(self):
        self.assertEqual(
            team_router.role_thread_title(
                self.project_id,
                "manager",
                "Team Router 自动化入口与待办提醒",
            ),
            "规划者-Team Router 自动化入口与待办提醒",
        )
        self.assertEqual(
            team_router.role_thread_title(
                self.project_id,
                "executor",
                "  Team   Router   自动化入口与待办提醒  ",
            ),
            "执行者-Team Router 自动化入口与待办提醒",
        )
        self.assertEqual(
            team_router.role_thread_title(self.project_id, "verifier"),
            "TeamRouter verifier - project-123",
        )

    def test_orchestrate_team_task_requires_parent_current_thread_rename_before_role_dispatch(self):
        class ParentAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.thread_list = [
                    {"threadId": "live-manager", "title": "Old manager title", "role": "manager", "projectId": "project-123"},
                    {"threadId": "live-executor", "title": "TeamRouter executor - project-123"},
                    {"threadId": "live-verifier", "title": "TeamRouter verifier - project-123"},
                ]

            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-123", "target": {"type": "project", "projectId": "project-123"}}]}

            def list_threads(self, **kwargs):
                return {"threads": list(self.thread_list)}

        adapter = ParentAdapter()
        scheduler = FakeHeartbeatScheduler()

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="role lifecycle fixes",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=scheduler,
        )

        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(adapter.renamed[0], {"threadId": "parent-manager-thread", "title": "调度者-Team Router role lifecycle fixes"})
        self.assertIn(
            {"threadId": "live-executor", "title": "执行者-role lifecycle fixes"},
            adapter.renamed[1:],
        )
        self.assertEqual(adapter.created, [])
        self.assertEqual(len(scheduler.scheduled), 1)
        self.assertEqual(update["heartbeatSchedule"]["runAt"], update["watcher"]["firstCheckAt"])
        self.assertEqual(scheduler.scheduled[0]["runAt"], update["watcher"]["firstCheckAt"])
        self.assertEqual(scheduler.scheduled[0]["managerAction"], "watch_team_task_with_adapter")
        self.assertEqual(scheduler.scheduled[0]["role"], update["watcher"]["role"])
        self.assertEqual(scheduler.scheduled[0]["threadId"], update["watcher"]["threadId"])
        self.assertEqual(scheduler.scheduled[0]["watchArgs"]["task_id"], self.task_id)
        self.assertEqual(scheduler.scheduled[0]["watchArgs"]["permission"], "read-only")

    def test_orchestrate_team_task_accepts_live_host_context(self):
        class ParentAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.thread_list = [
                    {"threadId": "live-manager", "title": "Old manager title", "role": "manager", "projectId": "project-123"},
                    {"threadId": "live-executor", "title": "TeamRouter executor - project-123"},
                    {"threadId": "live-verifier", "title": "TeamRouter verifier - project-123"},
                ]

            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-123", "target": {"type": "project", "projectId": "project-123"}}]}

            def list_threads(self, **kwargs):
                return {"threads": list(self.thread_list)}

        adapter = ParentAdapter()
        scheduler = FakeHeartbeatScheduler()
        host_context = team_router.make_live_orchestration_host_context(
            adapter,
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=scheduler,
            codex_project_id="project-123",
        )

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="role lifecycle fixes",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            host_context=host_context,
        )

        self.assertEqual(host_context.readiness["status"], "ready")
        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(update["codexProjectId"], "project-123")
        self.assertEqual(adapter.renamed[0], {"threadId": "parent-manager-thread", "title": "调度者-Team Router role lifecycle fixes"})
        self.assertEqual(adapter.created, [])
        self.assertEqual(len(scheduler.scheduled), 1)
        self.assertEqual(update["heartbeatSchedule"]["runAt"], update["watcher"]["firstCheckAt"])
        self.assertEqual(scheduler.scheduled[0]["runAt"], update["watcher"]["firstCheckAt"])
        self.assertEqual(scheduler.scheduled[0]["watchArgs"]["task_id"], self.task_id)

    def test_watcher_runtime_materializes_scheduler_payload_kwargs(self):
        adapter = FakeThreadAdapter()
        scheduler = FakeHeartbeatScheduler()
        update = {
            "status": "awaiting_callback",
            "watcher": {
                "role": "executor",
                "threadId": "thread-executor",
                "expectedMarker": "TEAM_ROUTER_CALLBACK taskId=task-1",
                "firstCheckAt": "2026-07-01T10:00:30+08:00",
                "nextAllowedReadAt": "2026-07-01T10:05:00+08:00",
                "lastReadAt": None,
            },
        }
        payload = team_router_watcher_runtime.build_watcher_heartbeat_payload(
            update,
            state_root=self.root,
            project_id=self.project_id,
            task_id="task-1",
            permission="read-only",
            return_thread_id="parent-thread",
        )

        kwargs = team_router.materialize_watcher_call_kwargs(
            payload,
            thread_adapter=adapter,
            heartbeat_scheduler=scheduler,
            turn_limit=3,
        )

        self.assertEqual(kwargs["state_root"], str(Path(self.root)))
        self.assertEqual(kwargs["project_id"], self.project_id)
        self.assertEqual(kwargs["task_id"], "task-1")
        self.assertEqual(kwargs["permission"], "read-only")
        self.assertEqual(kwargs["return_thread_id"], "parent-thread")
        self.assertEqual(kwargs["read_reason"], "scheduled watcher heartbeat")
        self.assertEqual(kwargs["observed_at"], payload["runAt"])
        self.assertIs(kwargs["thread_adapter"], adapter)
        self.assertIs(kwargs["heartbeat_scheduler"], scheduler)
        self.assertEqual(kwargs["turn_limit"], 3)

    def test_watcher_runtime_rejects_non_watcher_scheduler_payload(self):
        with self.assertRaises(team_router.ProtocolError) as ctx:
            team_router.materialize_watcher_call_kwargs(
                {"callback": "other_callback", "kwargs": {}},
                thread_adapter=FakeThreadAdapter(),
            )

        self.assertIn("watch_team_task_with_adapter", str(ctx.exception))
    def test_live_host_context_blocks_missing_parent_thread_id_without_side_effects(self):
        adapter = FullThreadAdapter()
        scheduler = FakeHeartbeatScheduler()

        with self.assertRaises(team_router.StateStoreError) as caught:
            team_router.make_live_orchestration_host_context(
                adapter,
                parent_thread_id=None,
                heartbeat_scheduler=scheduler,
            )

        self.assertIn("parent_thread_id", str(caught.exception))
        self.assertEqual(adapter.renamed, [])
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])
        self.assertEqual(scheduler.scheduled, [])

    def test_live_host_context_blocks_non_callable_scheduler_without_side_effects(self):
        adapter = FullThreadAdapter()

        with self.assertRaises(team_router.StateStoreError) as caught:
            team_router.make_live_orchestration_host_context(
                adapter,
                parent_thread_id="parent-manager-thread",
                heartbeat_scheduler=True,
            )

        self.assertIn("callable heartbeat scheduler", str(caught.exception))
        self.assertEqual(adapter.renamed, [])
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])

    def test_orchestrate_team_task_rejects_host_context_conflicts_before_side_effects(self):
        adapter = FullThreadAdapter()
        scheduler = FakeHeartbeatScheduler()
        host_context = team_router.make_live_orchestration_host_context(
            adapter,
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=scheduler,
        )

        with self.assertRaises(team_router.StateStoreError) as caught:
            team_router.orchestrate_team_task_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                objective="role lifecycle fixes",
                project_local_path="D:\\codex\\codex-dynamic-workflow",
                thread_adapter=adapter,
                permission="read-only",
                observed_at="2026-06-22T20:00:00+08:00",
                parent_thread_id="other-parent-thread",
                heartbeat_scheduler=scheduler,
                host_context=host_context,
            )

        self.assertIn("host_context conflicts with explicit parent_thread_id", str(caught.exception))
        self.assertEqual(adapter.renamed, [])
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])
        self.assertEqual(scheduler.scheduled, [])

    def test_orchestrate_team_task_blocks_when_parent_thread_id_is_unavailable(self):
        adapter = FullThreadAdapter()

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="role lifecycle fixes",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            heartbeat_scheduler=FakeHeartbeatScheduler(),
        )

        self.assertEqual(update["status"], "tool_error")
        self.assertEqual(update["action"], "tool_error_parent_title_unavailable")
        self.assertIn("current thread id", update["userOutput"])
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])

    def test_orchestrate_team_task_blocks_when_heartbeat_scheduler_is_not_callable(self):
        adapter = FullThreadAdapter()

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="role lifecycle fixes",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=True,
        )

        self.assertEqual(update["status"], "tool_error")
        self.assertEqual(update["action"], "tool_error_live_orchestration_unavailable")
        self.assertIn("callable heartbeat scheduler", update["userOutput"])
        self.assertEqual(adapter.renamed, [])
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.sent, [])

    def test_start_team_task_with_adapter_replaces_broken_registry_role_without_duplicate_active_roles(self):
        class ReplacementAdapter(FakeThreadAdapter):
            def create_thread(self, **kwargs):
                result = super().create_thread(**kwargs)
                if result["threadId"] == "thread-executor":
                    result = dict(result, threadId="thread-executor-replacement")
                    self.created[-1]["result"] = result
                    self.messages[result["threadId"]] = []
                return result

        adapter = ReplacementAdapter()
        existing_roles = {
            "manager": self.roles["manager"],
            "executor": dict(self.roles["executor"], status="broken"),
            "verifier": self.roles["verifier"],
        }
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            existing_roles,
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="role lifecycle fixes",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        created_prompts = [record["kwargs"]["prompt"] for record in adapter.created]
        self.assertEqual(len(created_prompts), 1)
        self.assertIn("role: executor", created_prompts[0])
        registry = team_router.load_registry(self.root, self.project_id)
        project_roles = registry["projects"][self.project_id]["roles"]
        self.assertEqual(project_roles["manager"]["threadId"], "thread-manager")
        self.assertEqual(project_roles["executor"]["threadId"], "thread-executor-replacement")
        self.assertEqual(project_roles["executor"]["replacesThreadId"], "thread-executor")
        self.assertIn("broken", project_roles["executor"]["replacementReason"])
        self.assertEqual(project_roles["verifier"]["threadId"], "thread-verifier")

    def test_start_team_task_with_adapter_reuses_existing_registry_roles(self):
        adapter = FakeThreadAdapter()
        existing_roles = {
            role: dict(record, createdAt="2026-06-22T19:00:00+08:00")
            for role, record in self.roles.items()
        }
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            existing_roles,
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.created, [])
        registry = team_router.load_registry(self.root, self.project_id)
        for role in ("manager", "executor", "verifier"):
            self.assertEqual(
                registry["projects"][self.project_id]["roles"][role]["threadId"],
                self.roles[role]["threadId"],
            )

    def test_start_team_task_with_adapter_reuses_registry_without_target_lookup(self):
        adapter = FakeThreadAdapter()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            self.roles,
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.created, [])

    def test_start_team_task_with_adapter_creates_only_missing_registry_roles(self):
        adapter = FakeThreadAdapter()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"manager": self.roles["manager"]},
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        created_prompts = [record["kwargs"]["prompt"] for record in adapter.created]
        self.assertEqual(len(created_prompts), 2)
        self.assertFalse(any("role: manager" in prompt for prompt in created_prompts))
        self.assertTrue(any("role: executor" in prompt for prompt in created_prompts))
        self.assertTrue(any("role: verifier" in prompt for prompt in created_prompts))
        registry = team_router.load_registry(self.root, self.project_id)
        project_roles = registry["projects"][self.project_id]["roles"]
        self.assertEqual(project_roles["manager"]["threadId"], "thread-manager")
        self.assertEqual(project_roles["executor"]["threadId"], "thread-executor")
        self.assertEqual(project_roles["verifier"]["threadId"], "thread-verifier")

    def test_start_team_task_with_adapter_ignores_archived_discovered_role_threads(self):
        class DiscoveryAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.thread_list = [
                    {
                        "threadId": "archived-executor",
                        "title": "TeamRouter executor - project-123",
                        "status": "archived",
                    },
                    {
                        "threadId": "live-manager",
                        "title": "TeamRouter manager - project-123",
                    },
                ]

            def list_threads(self, **kwargs):
                return {"threads": list(self.thread_list)}

        adapter = DiscoveryAdapter()

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        created_prompts = [record["kwargs"]["prompt"] for record in adapter.created]
        self.assertTrue(any("role: executor" in prompt for prompt in created_prompts))
        registry = team_router.load_registry(self.root, self.project_id)
        executor = registry["projects"][self.project_id]["roles"]["executor"]
        self.assertEqual(executor["threadId"], "thread-executor")
        self.assertNotEqual(executor["threadId"], "archived-executor")

    def test_send_executor_dispatch_with_adapter_replaces_archived_registry_role(self):
        class ReplacementAdapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-123", "target": {"type": "projectless"}}]}

        adapter = ReplacementAdapter()
        self._planned_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"executor": {"threadId": "archived-executor", "title": "执行者-old", "status": "archived"}},
            "2026-06-22T19:59:00+08:00",
        )

        updated = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:02:00+08:00",
        )

        self.assertEqual(updated["dispatches"][-1]["threadId"], "thread-executor")
        self.assertNotEqual(updated["dispatches"][-1]["threadId"], "archived-executor")
        registry = team_router.load_registry(self.root, self.project_id)
        executor = registry["projects"][self.project_id]["roles"]["executor"]
        self.assertEqual(executor["replacesThreadId"], "archived-executor")
        self.assertIn("archived", executor["replacementReason"])
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-executor")

    def test_reviewer_and_verifier_requests_replace_unavailable_registry_roles(self):
        class ReplacementAdapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-123", "target": {"type": "projectless"}}]}

        adapter = ReplacementAdapter()
        self._high_risk_awaiting_callback_ledger()
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            callback_messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "archived-reviewer", "title": "审查者-old", "status": "archived"}},
            "2026-06-22T20:04:30+08:00",
        )

        reviewed = team_router.send_reviewer_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        self.assertEqual(reviewed["review"]["request"]["threadId"], "thread-reviewer")
        registry = team_router.load_registry(self.root, self.project_id)
        reviewer = registry["projects"][self.project_id]["roles"]["reviewer"]
        self.assertEqual(reviewer["replacesThreadId"], "archived-reviewer")
        self.assertIn("archived", reviewer["replacementReason"])
        review_request = reviewed["review"]["request"]

        reviewed = team_router.capture_reviewer_review_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": review_request["messageId"], "sentAt": review_request["sentAt"], "text": "review"},
                {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(reviewed["status"], "verifying")
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"verifier": {"threadId": "broken-verifier", "title": "验证者-old", "status": "broken"}},
            "2026-06-22T20:07:30+08:00",
        )
        verified = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(verified["verification"]["request"]["threadId"], "thread-verifier")
        registry = team_router.load_registry(self.root, self.project_id)
        verifier = registry["projects"][self.project_id]["roles"]["verifier"]
        self.assertEqual(verifier["replacesThreadId"], "broken-verifier")
        self.assertIn("broken", verifier["replacementReason"])
    def test_start_team_task_with_adapter_discovers_existing_role_threads(self):
        class DiscoveryAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed = 0
                self.renamed = []
                self.thread_list = [
                    {
                        "threadId": "live-manager",
                        "title": "Old manager title",
                        "role": "manager",
                        "projectId": "project-123",
                    },
                    {
                        "threadId": "live-executor",
                        "title": "TeamRouter executor - project-123",
                    },
                ]

            def list_threads(self, **kwargs):
                self.listed += 1
                return {"threads": list(self.thread_list)}

            def set_thread_title(self, **kwargs):
                self.renamed.append(dict(kwargs))
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        adapter = DiscoveryAdapter()

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.listed, 1)
        self.assertEqual(len(adapter.created), 1)
        self.assertIn("role: verifier", adapter.created[0]["kwargs"]["prompt"])
        registry = team_router.load_registry(self.root, self.project_id)
        project_roles = registry["projects"][self.project_id]["roles"]
        self.assertEqual(project_roles["manager"]["threadId"], "live-manager")
        self.assertEqual(project_roles["executor"]["threadId"], "live-executor")
        self.assertEqual(project_roles["verifier"]["threadId"], "thread-verifier")
        self.assertIn(
            {"threadId": "live-manager", "title": "规划者-inspect docs"},
            adapter.renamed,
        )
        self.assertIn(
            {"threadId": "live-executor", "title": "执行者-inspect docs"},
            adapter.renamed,
        )
        self.assertIn(
            {"threadId": "thread-verifier", "title": "验证者-inspect docs"},
            adapter.renamed,
        )

    def test_start_team_task_with_adapter_ignores_ambiguous_bound_registry_roles(self):
        class DuplicateManagerAdapter(FakeThreadAdapter):
            def list_threads(self, **kwargs):
                return {
                    "threads": [
                        {"threadId": "manager-a", "title": "TeamRouter manager - project-123"},
                        {"threadId": "manager-b", "title": "TeamRouter manager - project-123"},
                    ],
                }

        adapter = DuplicateManagerAdapter()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"manager": self.roles["manager"]},
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(len(adapter.created), 2)
        registry = team_router.load_registry(self.root, self.project_id)
        self.assertEqual(
            registry["projects"][self.project_id]["roles"]["manager"]["threadId"],
            "thread-manager",
        )

    def test_start_team_task_with_adapter_does_not_bind_bare_role_from_other_project(self):
        class ForeignRoleAdapter(FakeThreadAdapter):
            def list_threads(self, **kwargs):
                return {
                    "threads": [
                        {
                            "threadId": "foreign-manager",
                            "title": "Other project manager",
                            "role": "manager",
                        },
                    ],
                }

        adapter = ForeignRoleAdapter()

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        registry = team_router.load_registry(self.root, self.project_id)
        self.assertEqual(
            registry["projects"][self.project_id]["roles"]["manager"]["threadId"],
            "thread-manager",
        )

    def test_start_team_task_with_adapter_blocks_ambiguous_discovered_role_threads(self):
        class AmbiguousAdapter(FakeThreadAdapter):
            def list_threads(self, **kwargs):
                return {
                    "threads": [
                        {"threadId": "manager-a", "title": "TeamRouter manager - project-123"},
                        {"threadId": "manager-b", "title": "TeamRouter manager - project-123"},
                    ],
                }

        with self.assertRaises(team_router.StateStoreError):
            team_router.start_team_task_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                objective="inspect docs",
                project_local_path="D:\\codex\\codex-dynamic-workflow",
                thread_adapter=AmbiguousAdapter(),
                target={"type": "projectless"},
                observed_at="2026-06-22T20:00:00+08:00",
            )

    def test_start_team_task_with_adapter_resolves_target_from_list_projects(self):
        class ProjectListAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed_projects = 0

            def list_projects(self, **kwargs):
                self.listed_projects += 1
                return {
                    "projects": [
                        {
                            "projectId": "project-123",
                            "target": {
                                "type": "worktree",
                                "path": "D:\\codex\\codex-dynamic-workflow",
                            },
                        },
                    ],
                }

        adapter = ProjectListAdapter()

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.listed_projects, 1)
        for record in adapter.created:
            self.assertEqual(
                record["kwargs"]["target"],
                {"type": "worktree", "path": "D:\\codex\\codex-dynamic-workflow"},
            )

    def test_orchestrate_team_task_with_adapter_discovers_reuses_and_advances(self):
        class ParentAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed_projects = 0
                self.listed_threads = 0
                self.renamed = []
                self.thread_list = [
                    {
                        "threadId": "live-manager",
                        "title": "Old manager title",
                        "role": "manager",
                        "projectId": "project-123",
                    },
                    {
                        "threadId": "live-executor",
                        "title": "TeamRouter executor - project-123",
                    },
                    {
                        "threadId": "live-verifier",
                        "title": "TeamRouter verifier - project-123",
                    },
                ]

            def list_projects(self, **kwargs):
                self.listed_projects += 1
                return {
                    "projects": [
                        {
                            "projectId": "project-123",
                            "target": {
                                "type": "project",
                                "projectId": "project-123",
                                "environment": {"type": "local"},
                            },
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                self.listed_threads += 1
                return {"threads": list(self.thread_list)}

            def set_thread_title(self, **kwargs):
                self.renamed.append(dict(kwargs))
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        adapter = ParentAdapter()

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=FakeHeartbeatScheduler(),
        )

        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(update["ledger"]["status"], "awaiting_plan")
        self.assertEqual(adapter.listed_projects, 1)
        self.assertEqual(adapter.listed_threads, 1)
        self.assertEqual(adapter.created, [])
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "live-manager")
        self.assertEqual(
            adapter.renamed,
            [
                {"threadId": "parent-manager-thread", "title": "调度者-Team Router inspect docs"},
                {"threadId": "live-executor", "title": "执行者-inspect docs"},
                {"threadId": "live-manager", "title": "规划者-inspect docs"},
                {"threadId": "live-verifier", "title": "验证者-inspect docs"},
            ],
        )
        self.assertEqual(update["projectTarget"]["environment"], {"type": "local"})
        registry = team_router.load_registry(self.root, self.project_id)
        project_roles = registry["projects"][self.project_id]["roles"]
        self.assertEqual(project_roles["manager"]["threadId"], "live-manager")
        self.assertEqual(project_roles["executor"]["threadId"], "live-executor")
        self.assertEqual(project_roles["verifier"]["threadId"], "live-verifier")

    def test_orchestrate_team_task_with_adapter_can_resolve_path_codex_project_id(self):
        class PathProjectAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed_projects = 0
                self.listed_threads = 0

            def list_projects(self, **kwargs):
                self.listed_projects += 1
                return {
                    "projects": [
                        {
                            "projectId": "D:\\codex\\codex-dynamic-workflow",
                            "target": {
                                "type": "project",
                                "projectId": "D:\\codex\\codex-dynamic-workflow",
                                "environment": {"type": "local"},
                            },
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                self.listed_threads += 1
                return {
                    "threads": [
                        {"threadId": "live-manager", "title": "TeamRouter manager - project-123"},
                        {"threadId": "live-executor", "title": "TeamRouter executor - project-123"},
                        {"threadId": "live-verifier", "title": "TeamRouter verifier - project-123"},
                    ],
                }

            def set_thread_title(self, **kwargs):
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        adapter = PathProjectAdapter()

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            codex_project_id="D:\\codex\\codex-dynamic-workflow",
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=FakeHeartbeatScheduler(),
        )

        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(update["ledger"]["projectId"], "project-123")
        self.assertEqual(update["codexProjectId"], "D:\\codex\\codex-dynamic-workflow")
        self.assertEqual(update["projectTarget"]["projectId"], "D:\\codex\\codex-dynamic-workflow")
        self.assertEqual(adapter.listed_projects, 1)
        self.assertEqual(adapter.listed_threads, 1)
        self.assertEqual(adapter.created, [])

    def test_orchestrate_team_task_with_adapter_accepts_codex_desktop_project_shape(self):
        class CodexDesktopProjectAdapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "projects": [
                        {
                            "projectId": "D:\\codex\\codex-dynamic-workflow",
                            "projectKind": "local",
                            "label": "codex-dynamic-workflow",
                            "path": "D:\\codex\\codex-dynamic-workflow",
                            "hostId": "local",
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "threads": [
                        {"id": "live-manager", "title": "TeamRouter manager - project-123"},
                        {"id": "live-executor", "title": "TeamRouter executor - project-123"},
                        {"id": "live-verifier", "title": "TeamRouter verifier - project-123"},
                    ],
                }

            def set_thread_title(self, **kwargs):
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=CodexDesktopProjectAdapter(),
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            codex_project_id="D:\\codex\\codex-dynamic-workflow",
            parent_thread_id="parent-manager-thread",
            heartbeat_scheduler=FakeHeartbeatScheduler(),
        )

        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(update["projectTarget"], {
            "type": "project",
            "projectId": "D:\\codex\\codex-dynamic-workflow",
            "environment": {"type": "local"},
        })

    def test_orchestrate_team_task_with_adapter_reaches_closeout_with_codex_desktop_shapes(self):
        class CodexDesktopE2EAdapter(FakeThreadAdapter):
            def __init__(self, task_id):
                super().__init__()
                self.task_id = task_id
                self.created = []
                self.reads = []
                self.renamed = []
                self.messages = {
                    "thread-manager": [],
                    "thread-executor": [],
                    "thread-verifier": [],
                }
                self.reply_specs = {
                    "thread-manager": (
                        "msg-live-plan",
                        "2026-06-23T11:40:30+08:00",
                        "assistant",
                        "TEAM_ROUTER_PLAN taskId=%s\n"
                        "status: planned\n"
                        "acknowledgedPermission: read-only\n"
                        "scope: src/team_router.py tests/test_team_router.py\n"
                        "stopWhen: closeout\n"
                        "riskBoundary: read only\n"
                        "executorPrompt: inspect adapter orchestration\n"
                        "notes: desktop e2e" % task_id,
                    ),
                    "thread-executor": (
                        "msg-live-callback",
                        "2026-06-23T11:41:30+08:00",
                        "assistant",
                        "TEAM_ROUTER_CALLBACK taskId=%s\n"
                        "status: done\n"
                        "final: true\n"
                        "summary: first line\n"
                        "second line\n"
                        "evidence: codex desktop shape\n"
                        "risks: none\n"
                        "next: verifier" % task_id,
                    ),
                    "thread-verifier": (
                        "msg-live-verdict",
                        "2026-06-23T11:42:30+08:00",
                        "assistant",
                        "TEAM_ROUTER_VERDICT taskId=%s\n"
                        "result: pass\n"
                        "summary: verified closeout\n"
                        "requiredChanges: none\n"
                        "evidenceChecked: codex desktop shape\n"
                        "risks: none" % task_id,
                    ),
                }

            def create_thread(self, **kwargs):
                raise AssertionError("pre-created role threads should be reused")

            def list_projects(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "projects": [
                        {
                            "projectId": "D:\\codex\\codex-dynamic-workflow",
                            "projectKind": "local",
                            "label": "codex-dynamic-workflow",
                            "path": "D:\\codex\\codex-dynamic-workflow",
                            "hostId": "local",
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "threads": [
                        {"id": "thread-manager", "title": "规划者-inspect docs"},
                        {"id": "thread-executor", "title": "执行者-inspect docs"},
                        {"id": "thread-verifier", "title": "验证者-inspect docs"},
                    ],
                }

            def set_thread_title(self, **kwargs):
                self.renamed.append(dict(kwargs))
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

            def send_message_to_thread(self, **kwargs):
                thread_id = kwargs["threadId"]
                self.sent.append({"kwargs": kwargs, "result": {"threadId": thread_id}})
                self.messages[thread_id].append({
                    "id": "user-%02d" % len(self.sent),
                    "sentAt": {
                        "thread-manager": "2026-06-23T11:40:00+08:00",
                        "thread-executor": "2026-06-23T11:41:00+08:00",
                        "thread-verifier": "2026-06-23T11:42:00+08:00",
                    }[thread_id],
                    "role": "user",
                    "content": [{"type": "text", "text": kwargs["prompt"]}],
                })
                reply_id, sent_at, role, text = self.reply_specs[thread_id]
                self.messages[thread_id].append({
                    "id": reply_id,
                    "sentAt": sent_at,
                    "role": role,
                    "content": [{"type": "text", "text": text}],
                })
                return {"threadId": thread_id}

            def read_thread(self, **kwargs):
                thread_id = kwargs["threadId"]
                self.reads.append(dict(kwargs))
                return {
                    "schemaVersion": 1,
                    "page": {"order": "newest_first"},
                    "thread": {"id": thread_id},
                    "turns": [
                        {
                            "id": "turn-%s" % thread_id,
                            "startedAt": "2026-06-23T11:40:00+08:00",
                            "items": list(reversed(self.messages[thread_id])),
                        },
                    ],
                }

        adapter = CodexDesktopE2EAdapter(self.task_id)
        observed_at = [
            "2026-06-23T11:40:00+08:00",
            "2026-06-23T11:41:00+08:00",
            "2026-06-23T11:42:00+08:00",
            "2026-06-23T11:43:00+08:00",
        ]

        updates = [
            team_router.orchestrate_team_task_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                objective="inspect docs",
                project_local_path="D:\\codex\\codex-dynamic-workflow",
                thread_adapter=adapter,
                permission="read-only",
                observed_at=timestamp,
                codex_project_id="D:\\codex\\codex-dynamic-workflow",
                parent_thread_id="parent-manager-thread",
                heartbeat_scheduler=FakeHeartbeatScheduler(),
            )
            for timestamp in observed_at
        ]

        self.assertEqual(
            [(update["action"], update["status"]) for update in updates],
            [
                ("sent_manager_plan_request", "awaiting_plan"),
                ("sent_executor_dispatch", "awaiting_callback"),
                ("sent_verifier_request", "verifying"),
                ("read_verifier_verdict", "done"),
            ],
        )
        self.assertEqual(adapter.created, [])
        self.assertEqual([record["kwargs"]["threadId"] for record in adapter.sent], [
            "thread-manager",
            "thread-executor",
            "thread-verifier",
        ])
        self.assertEqual([record["threadId"] for record in adapter.reads], [
            "thread-manager",
            "thread-executor",
            "thread-verifier",
        ])
        self.assertEqual(adapter.renamed, [{"threadId": "parent-manager-thread", "title": "调度者-Team Router inspect docs"}])
        self.assertTrue(updates[-1]["userOutput"].startswith("Team Router Closeout"))
        self.assertEqual(
            updates[-1]["ledger"]["observations"][-2]["parsedFields"]["summary"],
            "first line\nsecond line",
        )
        self.assertEqual(updates[-1]["codexProjectId"], "D:\\codex\\codex-dynamic-workflow")

    def test_verifier_request_uses_recent_executor_callback_observation(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        ledger["observations"].append(team_router.make_observation(
            "system_event",
            "system",
            "thread-system",
            "2026-06-22T20:04:30+08:00",
            "manual note after executor callback",
            {"status": "not-callback"},
        ))
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

        updated = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-verifier")
        prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("executorCallback: compact; raw omitted", prompt)
        self.assertIn("callbackSummary: ok", prompt)
        self.assertNotIn("manual note after executor callback", prompt)

    def test_fake_thread_adapter_runs_manager_executor_verifier_smoke(self):
        adapter = FakeThreadAdapter()
        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )
        self.assertEqual(ledger["status"], "roles_ready")

        awaiting_plan = team_router.send_manager_plan_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = awaiting_plan["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        planned = team_router.read_manager_plan_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:01:40+08:00",
        )
        self.assertEqual(planned["status"], "planned")

        awaiting_callback = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        executor_thread = awaiting_callback["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: ok\nevidence: fake adapter\nrisks: none\nnext: none" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        verifying = team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(verifying["status"], "verifying")

        verifying = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        verifier_thread = verifying["verification"]["request"]["threadId"]
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict",
            sent_at="2026-06-22T20:06:00+08:00",
        )
        done = team_router.read_verifier_verdict_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(done["status"], "done")
        self.assertEqual(done["closeout"]["summary"], "ok")
        self.assertEqual(len(adapter.created), 3)
        self.assertEqual(len(adapter.sent), 3)

    def test_run_team_task_with_adapter_orchestrates_until_external_waits(self):
        adapter = FakeThreadAdapter()

        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        self.assertEqual(first["action"], "sent_manager_plan_request")
        self.assertEqual(first["ledger"]["status"], "awaiting_plan")
        self.assertTrue(first["userOutput"].startswith("Team Router Handoff"))
        self.assertEqual(len(adapter.created), 3)
        self.assertEqual(len(adapter.sent), 1)

        manager_thread = first["ledger"]["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        second = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        self.assertEqual(second["action"], "sent_executor_dispatch")
        self.assertEqual(second["ledger"]["status"], "awaiting_callback")
        self.assertEqual(len(adapter.sent), 2)
        dispatch = second["ledger"]["dispatches"][-1]
        self.assertNotIn("returnThreadId", dispatch)
        self.assertNotIn("callbackDelivery", dispatch)
        self.assertNotIn("returnThreadId:", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertNotIn("callbackDelivery: direct-send", adapter.sent[-1]["kwargs"]["prompt"])

        executor_thread = second["ledger"]["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: line one\nline two\nevidence: fake adapter\nrisks: none\nnext: verifier" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        third = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(third["action"], "sent_verifier_request")
        self.assertEqual(third["ledger"]["status"], "verifying")
        self.assertEqual(
            third["ledger"]["observations"][-1]["parsedFields"]["summary"],
            "line one\nline two",
        )
        self.assertEqual(len(adapter.sent), 3)
        verifier_request = third["ledger"]["verification"]["request"]
        self.assertNotIn("returnThreadId", verifier_request)
        self.assertNotIn("verdictDelivery", verifier_request)
        self.assertNotIn("returnThreadId:", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertNotIn("verdictDelivery: direct-send", adapter.sent[-1]["kwargs"]["prompt"])

        verifier_thread = third["ledger"]["verification"]["request"]["threadId"]
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        fourth = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:06:00+08:00",
        )
        self.assertEqual(fourth["action"], "read_verifier_verdict")
        self.assertEqual(fourth["ledger"]["status"], "done")
        self.assertTrue(fourth["userOutput"].startswith("Team Router Closeout"))

    def test_run_team_task_with_adapter_recovers_from_needs_feedback_when_marker_later_arrives(self):
        adapter = FakeThreadAdapter()

        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = first["ledger"]["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )

        second = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        executor_thread = second["ledger"]["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "completed successfully",
            message_id="msg-done-no-marker",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        third = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(third["action"], "read_executor_callback")
        self.assertEqual(third["ledger"]["status"], "needs_feedback")
        self.assertIn("TEAM_ROUTER_CALLBACK", third["ledger"]["missingFeedback"]["expectedCallback"])

        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: recovered\nevidence: callback marker\nrisks: none\nnext: verifier" % self.task_id,
            message_id="msg-callback-after-needs-feedback",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        fourth = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:06:00+08:00",
        )

        self.assertEqual(fourth["action"], "sent_verifier_request")
        self.assertEqual(fourth["ledger"]["status"], "verifying")
        self.assertEqual(
            fourth["ledger"]["observations"][-1]["parsedFields"]["summary"],
            "recovered",
        )

    def test_run_team_task_with_adapter_routes_high_risk_callback_through_reviewer_pass(self):
        adapter = FakeThreadAdapter()
        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = first["ledger"]["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: Team Router reviewer runtime gate\nstopWhen: done\nriskBoundary: runtime gate and reviewer gate change\nexecutorPrompt: inspect Team Router self changes\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        second = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:02:30+08:00",
        )
        executor_thread = second["ledger"]["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: runtime gate fixed\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        third = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(third["action"], "sent_reviewer_request")
        self.assertEqual(third["ledger"]["status"], "reviewing")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-reviewer")
        self.assertIn("TEAM_ROUTER_REVIEW_REQUEST taskId=%s" % self.task_id, adapter.sent[-1]["kwargs"]["prompt"])

        adapter.append_reply(
            "thread-reviewer",
            "TEAM_ROUTER_REVIEW taskId=%s\nresult: pass\nsummary: reviewer passed\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none" % self.task_id,
            message_id="msg-review-pass",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        fourth = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:06:00+08:00",
        )

        self.assertEqual(fourth["action"], "sent_verifier_request")
        self.assertEqual(fourth["ledger"]["status"], "verifying")
        self.assertEqual(fourth["ledger"]["review"]["result"]["fields"]["result"], "pass")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-verifier")

    def test_run_team_task_with_adapter_stops_for_reviewer_needs_rework(self):
        adapter = FakeThreadAdapter()
        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        adapter.append_reply(
            first["ledger"]["planRequest"]["threadId"],
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: Team Router reviewer gate\nstopWhen: done\nriskBoundary: runtime gate change\nexecutorPrompt: inspect Team Router self changes\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        second = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:02:30+08:00",
        )
        adapter.append_reply(
            second["ledger"]["dispatches"][-1]["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: runtime gate fixed\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        third = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(third["action"], "sent_reviewer_request")
        adapter.append_reply(
            "thread-reviewer",
            "TEAM_ROUTER_REVIEW taskId=%s\nresult: needs_rework\nsummary: gap remains\nfindings: trigger missing\nrequiredChanges: expand reviewer gate trigger tests\nevidenceChecked: tests\nrisks: none" % self.task_id,
            message_id="msg-review-rework",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        fourth = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:06:00+08:00",
        )

        self.assertEqual(fourth["action"], "needs_rework_pending")
        self.assertEqual(fourth["ledger"]["status"], "needs_rework")
        self.assertEqual(fourth["ledger"]["review"]["result"]["fields"]["result"], "needs_rework")
    def test_watch_team_task_reads_executor_callback_and_sends_verifier(self):
        adapter = FakeThreadAdapter()
        awaiting = self._awaiting_callback_ledger()
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: callback ready\n"
                    "evidence: fake adapter\n"
                    "risks: none\n"
                    "next: verifier" % awaiting["taskId"]
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["type"], "callback_raw")
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "thread-verifier")
        self.assertIn("TEAM_ROUTER_VERIFY taskId=%s" % self.task_id, adapter.sent[0]["kwargs"]["prompt"])
        self.assertEqual(update["nextWakeup"]["role"], "verifier")
        self.assertEqual(update["nextWakeup"]["reason"], "awaiting TEAM_ROUTER_VERDICT")
        self.assertIn("host watcher", update["automationBoundary"])

    def test_watch_team_task_prefers_manager_inbox_direct_return_callback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: thread-executor\n"
                    "role: Executor\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: direct return callback\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["parsedFields"]["summary"], "direct return callback")
        self.assertEqual(update["ledger"]["observations"][-1]["receipt"]["source"], "manager-inbox/direct-send")
        self.assertEqual(update["ledger"]["observations"][-1]["receipt"]["channel"], "manager-inbox")
        self.assertEqual(update["ledger"]["callbackReceipt"]["source"], "manager-inbox/direct-send")
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "thread-verifier")

    def test_executor_direct_return_duplicate_callback_is_idempotent(self):
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        messages = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "sourceThreadId": "thread-executor",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: thread-executor\n"
                    "role: Executor\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: direct return callback\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier" % self.task_id
                ),
            },
        ]

        first = team_router._capture_executor_callback_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        second = team_router._capture_executor_callback_from_manager_inbox(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:05:00+08:00",
        )

        self.assertEqual(first["status"], "verifying")
        self.assertIsNone(second)
        saved = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(len(saved["observations"]), 1)
        self.assertFalse(saved.get("malformedDirectReturns"))

    def test_watch_team_task_ignores_malformed_manager_inbox_callback_and_uses_self_thread_fallback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: maybe\n"
                    "final: true\n"
                    "summary: malformed direct return\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:30+08:00",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: fallback callback\n"
                    "evidence: executor self-thread\n"
                    "risks: none\n"
                    "next: verifier" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["parsedFields"]["summary"], "fallback callback")
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["taskId"], self.task_id)
        self.assertEqual(telemetry[0]["role"], "executor")
        self.assertEqual(telemetry[0]["sourceThreadId"], "thread-executor")
        self.assertEqual(telemetry[0]["roleThreadId"], "thread-executor")
        self.assertEqual(telemetry[0]["returnThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["orchestratorThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["expectedMarker"], "TEAM_ROUTER_CALLBACK taskId=%s" % self.task_id)
        self.assertEqual(telemetry[0]["messageId"], "msg-manager-callback")
        self.assertEqual(telemetry[0]["sentAt"], "2026-06-22T20:03:00+08:00")
        self.assertEqual(telemetry[0]["capturedAt"], "2026-06-22T20:04:00+08:00")
        self.assertIn("must be one of", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["recovery"], "self-thread-marker fallback")
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "thread-verifier")

    def test_watch_executor_direct_return_rejects_wrong_protocol_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "sourceThreadId: wrong-parent-thread\n"
                    "sourceRoleThreadId: thread-executor\n"
                    "role: Executor\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: manager inbox\n"
                    "evidence: direct return\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:30+08:00",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: fallback callback\n"
                    "evidence: executor self-thread\n"
                    "risks: none\n"
                    "next: verifier" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["parsedFields"]["summary"], "fallback callback")
        self.assertEqual(update["ledger"]["observations"][-1]["receipt"]["source"], "self-thread-fallback/read_thread")
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertIn("sourceThreadId", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["protocolSourceThreadId"], "wrong-parent-thread")
        self.assertEqual(telemetry[0]["protocolRole"], "Executor")
        self.assertEqual(telemetry[0]["protocolSourceRoleThreadId"], "thread-executor")
        self.assertEqual(telemetry[0]["recovery"], "self-thread-marker fallback")

    def test_watch_executor_direct_return_rejects_wrong_protocol_role(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: thread-executor\n"
                    "role: Verifier\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: manager inbox\n"
                    "evidence: direct return\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:30+08:00",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: fallback callback\n"
                    "evidence: executor self-thread\n"
                    "risks: none\n"
                    "next: verifier" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["parsedFields"]["summary"], "fallback callback")
        self.assertEqual(update["ledger"]["observations"][-1]["receipt"]["source"], "self-thread-fallback/read_thread")
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["protocolSourceThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["protocolRole"], "Verifier")
        self.assertEqual(telemetry[0]["protocolSourceRoleThreadId"], "thread-executor")
        self.assertIn("TEAM_ROUTER_CALLBACK.role", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["recovery"], "self-thread-marker fallback")

    def test_watch_executor_direct_return_rejects_wrong_protocol_source_role_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: wrong-executor-thread\n"
                    "role: Executor\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: manager inbox\n"
                    "evidence: direct return\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:30+08:00",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: fallback callback\n"
                    "evidence: executor self-thread\n"
                    "risks: none\n"
                    "next: verifier" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["parsedFields"]["summary"], "fallback callback")
        self.assertEqual(update["ledger"]["observations"][-1]["receipt"]["source"], "self-thread-fallback/read_thread")
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["protocolSourceThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["protocolRole"], "Executor")
        self.assertEqual(telemetry[0]["protocolSourceRoleThreadId"], "wrong-executor-thread")
        self.assertIn("TEAM_ROUTER_CALLBACK.sourceRoleThreadId", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["recovery"], "self-thread-marker fallback")


    def test_watch_team_task_ignores_manager_inbox_callback_with_wrong_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>wrong-executor-thread</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: wrong source\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_executor_callback")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertEqual(update["ledger"]["observations"], [])
        self.assertFalse(update["ledger"].get("malformedDirectReturns"))
        self.assertEqual(adapter.sent, [])

    def test_watch_team_task_ignores_manager_inbox_callback_with_wrong_task_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=ctr-wrong-task\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: wrong task\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>"
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_executor_callback")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertEqual(update["ledger"]["observations"], [])
        self.assertEqual(adapter.sent, [])

    def test_executor_role_fallback_read_uses_fallback_search_anchor(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        awaiting = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        awaiting["dispatches"][-1]["searchAnchor"] = {"messageId": "manager-direct-callback"}
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, awaiting)
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: fallback callback\nevidence: executor self-thread\nrisks: none\nnext: verifier\ndirectReturnAttempt: sent\ndirectReturnTarget: parent-manager-thread" % self.task_id,
            },
        ]

        update = team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["observations"][-1]["parsedFields"]["summary"], "fallback callback")
        self.assertEqual(update["observations"][-1]["parsedFields"]["directReturnAttempt"], "sent")
        self.assertEqual(update["callbackReceipt"]["source"], "self-thread-fallback/read_thread")
        self.assertEqual(update["callbackReceipt"]["channel"], "read_thread")

    def test_watch_team_task_reads_verifier_pass_and_returns_closeout(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {
                "messageId": "msg-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: watcher closeout\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: fake adapter\n"
                    "risks: none" % requested["taskId"]
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "done")
        self.assertIsNone(update["nextWakeup"])
        self.assertIn("Team Router Closeout", update["userOutput"])
        self.assertIn("summary: watcher closeout", update["userOutput"])
        self.assertIn("remainingTodos: none", update["userOutput"])
        self.assertIn("compoundingDecision: skipped", update["userOutput"])
        self.assertIn("reason: ordinary successful implementation/testing with no new reusable risk", update["userOutput"])
        self.assertEqual(len(adapter.sent), 0)

    def test_verifier_role_fallback_read_uses_fallback_search_anchor(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        requested["verification"]["request"]["searchAnchor"] = {"messageId": "manager-direct-verdict"}
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, requested)
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {
                "messageId": "msg-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: fallback closeout\nrequiredChanges: none\nevidenceChecked: verifier self-thread\nrisks: none\ndirectReturnAttempt: unavailable\ndirectReturnTarget: parent-manager-thread" % self.task_id,
            },
        ]

        update = team_router.read_verifier_verdict_update_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["ledger"]["status"], "done")
        self.assertIn("summary: fallback closeout", update["userOutput"])
        self.assertEqual(update["ledger"]["verification"]["verdict"]["fields"]["directReturnAttempt"], "unavailable")
        self.assertEqual(update["ledger"]["verification"]["verdict"]["receipt"]["source"], "self-thread-fallback/read_thread")
        self.assertEqual(update["ledger"]["verification"]["verdict"]["receipt"]["channel"], "read_thread")

    def test_watch_verifier_direct_return_rejects_wrong_protocol_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
        )
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: verifier" % self.task_id,
            },
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            callback_messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-verdict-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-verifier</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=%s\n"
                    "sourceThreadId: wrong-parent-thread\n"
                    "sourceRoleThreadId: thread-verifier\n"
                    "role: Verifier\n"
                    "result: pass\n"
                    "summary: manager inbox verdict\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: direct return\n"
                    "risks: none</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {
                "messageId": "msg-verdict",
                "sentAt": "2026-06-22T20:06:30+08:00",
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: fallback verdict\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: verifier self-thread\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "done")
        self.assertEqual(update["ledger"]["verification"]["verdict"]["fields"]["summary"], "fallback verdict")
        self.assertEqual(update["ledger"]["verification"]["verdict"]["receipt"]["source"], "self-thread-fallback/read_thread")
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertIn("sourceThreadId", telemetry[0]["error"])

    def test_watch_team_task_prefers_manager_inbox_direct_return_verdict(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-verifier</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: thread-verifier\n"
                    "role: Verifier\n"
                    "result: pass\n"
                    "summary: direct return closeout\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "done")
        self.assertIn("summary: direct return closeout", update["userOutput"])
        self.assertIn("remainingTodos: none", update["userOutput"])
        self.assertIn("compoundingDecision: skipped", update["userOutput"])
        self.assertIn("reason: ordinary successful implementation/testing with no new reusable risk", update["userOutput"])
        self.assertEqual(update["ledger"]["verification"]["verdict"]["receipt"]["source"], "manager-inbox/direct-send")
        self.assertEqual(update["ledger"]["verification"]["verdict"]["receipt"]["channel"], "manager-inbox")
        self.assertEqual(len(adapter.sent), 0)

    def test_watch_team_task_ignores_malformed_manager_inbox_verdict_and_uses_self_thread_fallback(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-verifier</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: accepted\n"
                    "summary: malformed direct return\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {
                "messageId": "msg-verdict",
                "sentAt": "2026-06-22T20:06:30+08:00",
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: fallback closeout\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: verifier self-thread\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "done")
        self.assertIn("summary: fallback closeout", update["userOutput"])
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["taskId"], self.task_id)
        self.assertEqual(telemetry[0]["role"], "verifier")
        self.assertEqual(telemetry[0]["sourceThreadId"], "thread-verifier")
        self.assertEqual(telemetry[0]["roleThreadId"], "thread-verifier")
        self.assertEqual(telemetry[0]["returnThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["orchestratorThreadId"], "parent-manager-thread")
        self.assertEqual(telemetry[0]["expectedMarker"], "TEAM_ROUTER_VERDICT taskId=%s" % self.task_id)
        self.assertEqual(telemetry[0]["messageId"], "msg-manager-verdict")
        self.assertEqual(telemetry[0]["sentAt"], "2026-06-22T20:06:00+08:00")
        self.assertEqual(telemetry[0]["capturedAt"], "2026-06-22T20:07:00+08:00")
        self.assertIn("must be one of", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["recovery"], "self-thread-marker fallback")
        self.assertEqual(len(adapter.sent), 0)

    def test_watch_team_task_ignores_manager_inbox_verdict_with_wrong_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>wrong-verifier-thread</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: wrong source\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertIsNone(update["ledger"]["closeout"])
        self.assertFalse(update["ledger"].get("malformedDirectReturns"))
        self.assertEqual(len(adapter.sent), 0)

    def test_watch_team_task_ignores_manager_inbox_verdict_with_wrong_task_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-verifier</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=ctr-wrong-task\n"
                    "result: pass\n"
                    "summary: wrong task\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none</input>\n"
                    "</codex_delegation>"
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertIsNone(update["ledger"]["closeout"])
        self.assertEqual(len(adapter.sent), 0)

    def test_fallback_self_thread_does_not_redispatch_after_direct_return_callback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "sourceThreadId: parent-manager-thread\n"
                    "sourceRoleThreadId: thread-executor\n"
                    "role: Executor\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: direct return callback\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        first = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(first["action"], "watch_sent_verifier_request")
        self.assertEqual(len(first["ledger"]["observations"]), 1)
        self.assertEqual(len(adapter.sent), 1)

        adapter.messages["parent-manager-thread"] = []
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:04:00+08:00", "text": "verify"},
        ]
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: direct return callback\nevidence: manager inbox\nrisks: none\nnext: verifier" % self.task_id,
            },
        ]

        second = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:05:00+08:00",
        )

        self.assertEqual(second["action"], "watch_read_verifier_verdict")
        self.assertEqual(len(second["ledger"]["observations"]), 1)
        self.assertEqual(len(adapter.sent), 1)

    def test_run_team_task_with_adapter_waits_for_rework_confirmation(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        adapter = FakeThreadAdapter()

        update = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(update["action"], "needs_rework_pending")
        self.assertEqual(update["ledger"]["status"], "needs_rework")
        self.assertEqual(adapter.sent, [])

    def test_run_team_task_with_adapter_dispatches_rework_when_confirmed(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        adapter = FakeThreadAdapter()

        update = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:08:00+08:00",
            confirm_rework=True,
        )

        self.assertEqual(update["action"], "sent_executor_dispatch")
        self.assertEqual(update["ledger"]["status"], "awaiting_callback")
        self.assertEqual(update["ledger"]["reworkCount"], 1)
        self.assertEqual(len(adapter.sent), 1)

    def test_run_team_task_with_adapter_retries_plan_unreachable_reads(self):
        adapter = FakeThreadAdapter()
        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = first["ledger"]["planRequest"]["threadId"]
        original_messages = list(adapter.messages[manager_thread])
        adapter.messages[manager_thread] = [{"text": "summary-only window"}]

        unreachable = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        self.assertEqual(unreachable["ledger"]["status"], "plan_unreachable")

        adapter.messages[manager_thread] = original_messages
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        retried = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(retried["action"], "sent_executor_dispatch")
        self.assertEqual(retried["ledger"]["status"], "awaiting_callback")

    def test_manual_precreated_flow_uses_direct_send_read_and_capture_helpers(self):
        adapter = FakeThreadAdapter()
        ledger = self._ready_ledger()

        manager_prompt = team_router.make_plan_request_message(
            ledger["taskId"],
            ledger["objective"],
            "read-only",
        )
        manager_send = adapter.send_message_to_thread(
            threadId="thread-manager",
            prompt=manager_prompt,
        )
        manager_anchor = team_router.thread_send_anchor(
            manager_send,
            fallback_sent_at="2026-06-22T20:01:00+08:00",
        )
        awaiting_plan = team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            manager_thread_id="thread-manager",
            sent_at=manager_anchor["sentAt"],
            message_id=manager_anchor["messageId"],
        )
        adapter.append_reply(
            awaiting_plan["planRequest"]["threadId"],
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        planned = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            self.task_id,
            team_router.normalize_thread_read_messages(
                adapter.read_thread(threadId="thread-manager")
            ),
            captured_at="2026-06-22T20:01:40+08:00",
        )
        self.assertEqual(planned["status"], "planned")

        executor_prompt = team_router.make_executor_dispatch_message(
            self.task_id,
            planned["plan"]["fields"],
            "read-only",
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )
        executor_send = adapter.send_message_to_thread(
            threadId="thread-executor",
            prompt=executor_prompt,
        )
        executor_anchor = team_router.thread_send_anchor(
            executor_send,
            fallback_sent_at="2026-06-22T20:02:00+08:00",
        )
        awaiting_callback = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at=executor_anchor["sentAt"],
            message_id=executor_anchor["messageId"],
        )
        adapter.append_reply(
            awaiting_callback["dispatches"][-1]["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: first line\nsecond line\nevidence: direct tools\nrisks: none\nnext: verifier" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        verifying = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            team_router.normalize_thread_read_messages(
                adapter.read_thread(threadId="thread-executor")
            ),
            captured_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(
            verifying["observations"][-1]["parsedFields"]["summary"],
            "first line\nsecond line",
        )

        verifier_prompt = team_router.make_verifier_request_message(
            self.task_id,
            verifying["observations"][-1]["content"],
            "read-only",
            verifying["plan"]["fields"]["scope"],
        )
        verifier_send = adapter.send_message_to_thread(
            threadId="thread-verifier",
            prompt=verifier_prompt,
        )
        verifier_anchor = team_router.thread_send_anchor(
            verifier_send,
            fallback_sent_at="2026-06-22T20:05:00+08:00",
        )
        verifying = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            verifier_thread_id="thread-verifier",
            sent_at=verifier_anchor["sentAt"],
            message_id=verifier_anchor["messageId"],
        )
        adapter.append_reply(
            verifying["verification"]["request"]["threadId"],
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: direct tools\nrisks: none" % self.task_id,
            message_id="msg-verdict",
            sent_at="2026-06-22T20:06:00+08:00",
        )
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            self.task_id,
            team_router.normalize_thread_read_messages(
                adapter.read_thread(threadId="thread-verifier")
            ),
            captured_at="2026-06-22T20:07:00+08:00",
        )
        registry = team_router.load_registry(self.root, self.project_id)

        self.assertEqual(done["status"], "done")
        self.assertEqual(len(adapter.sent), 3)
        self.assertIn("Team Router Closeout", team_router.format_task_update_for_user(done, registry))

    def test_fake_thread_adapter_runs_rework_cycle_smoke(self):
        adapter = FakeThreadAdapter()
        team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )
        awaiting_plan = team_router.send_manager_plan_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = awaiting_plan["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        team_router.read_manager_plan_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        first_dispatch = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        executor_thread = first_dispatch["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: first attempt\nevidence: fake adapter\nrisks: none\nnext: verifier" % self.task_id,
            message_id="msg-callback-1",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        first_verify = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        verifier_thread = first_verify["verification"]["request"]["threadId"]
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: needs_rework\nsummary: missing evidence\nrequiredChanges: add evidence\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict-1",
            sent_at="2026-06-22T20:06:00+08:00",
        )
        needs_rework = team_router.read_verifier_verdict_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["status"], "needs_rework")

        second_dispatch = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:08:00+08:00",
        )
        self.assertEqual(second_dispatch["reworkCount"], 1)
        self.assertIsNone(second_dispatch["closeout"])
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: second attempt\nevidence: added evidence\nrisks: none\nnext: none" % self.task_id,
            message_id="msg-callback-2",
            sent_at="2026-06-22T20:09:00+08:00",
        )
        team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:10:00+08:00",
        )
        second_verify = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:11:00+08:00",
        )
        self.assertEqual(second_verify["verification"]["request"]["threadId"], verifier_thread)
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict-2",
            sent_at="2026-06-22T20:12:00+08:00",
        )
        done = team_router.read_verifier_verdict_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:13:00+08:00",
        )

        self.assertEqual(done["status"], "done")
        self.assertEqual(done["reworkCount"], 1)
        self.assertEqual(len(done["dispatches"]), 2)
        self.assertEqual(len(adapter.sent), 5)

    def test_closeout_and_handoff_user_formats_include_threads_and_anchors(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        registry = team_router.load_registry(self.root, self.project_id)

        closeout = team_router.format_closeout_for_user(done, registry)
        handoff = team_router.format_handoff_for_user(done, registry)

        self.assertIn("taskId: ctr-20260622-160000-a7f3", closeout)
        self.assertIn("status: done", closeout)
        self.assertIn("manager: thread-manager", closeout)
        self.assertIn("summary: ok", closeout)
        self.assertIn("remainingTodos: none", closeout)
        self.assertIn("receiptSource: self-thread-fallback/read_thread", closeout)
        self.assertIn("receiptChannel: read_thread", closeout)
        self.assertIn("compoundingDecision: skipped", closeout)
        self.assertIn("reason: ordinary successful implementation/testing with no new reusable risk", closeout)
        legacy_done = dict(done)
        legacy_done["closeout"] = dict(done["closeout"])
        legacy_done["closeout"].pop("compoundingDecision")
        legacy_done["closeout"].pop("reason")
        legacy_closeout = team_router.format_closeout_for_user(legacy_done, registry)

        self.assertIn("compoundingDecision: skipped", legacy_closeout)
        self.assertIn("reason: ordinary successful implementation/testing with no new reusable risk", legacy_closeout)
        self.assertIn("read_thread anchors", handoff)
        self.assertIn("msg-verify", handoff)
        self.assertIn("verification", handoff)
        self.assertIn("remainingTodos: none", handoff)
        self.assertNotIn("compoundingDecision:", handoff)
        self.assertNotIn("reason: ", handoff)

    def test_handoff_includes_manager_polling_status_summary(self):
        ledger = self._awaiting_callback_ledger()
        ledger["managerPollingStatus"] = {
            "mode": "read-only",
            "status": "read_suppressed",
            "shouldRead": False,
            "shouldReport": False,
            "nextAllowedReadAt": "2026-07-02T10:05:30+08:00",
            "summary": "manager polling read suppressed until 2026-07-02T10:05:30+08:00",
        }
        registry = team_router.load_registry(self.root, self.project_id)

        handoff = team_router.format_handoff_for_user(ledger, registry)

        self.assertIn("managerPolling:", handoff)
        self.assertIn("  status: read_suppressed", handoff)
        self.assertIn("  shouldRead: False", handoff)
        self.assertIn("  shouldReport: False", handoff)
        self.assertIn("  nextAllowedReadAt: 2026-07-02T10:05:30+08:00", handoff)
        self.assertIn("manager polling read suppressed", handoff)

    def test_closeout_includes_manager_polling_status_summary(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        done["managerPollingStatus"] = {
            "mode": "read-only",
            "status": "unchanged_active_status_suppressed",
            "shouldRead": True,
            "shouldReport": False,
            "summary": "manager polling observed unchanged active status",
        }
        registry = team_router.load_registry(self.root, self.project_id)

        closeout = team_router.format_closeout_for_user(done, registry)

        self.assertIn("managerPolling:", closeout)
        self.assertIn("  status: unchanged_active_status_suppressed", closeout)
        self.assertIn("  shouldRead: True", closeout)
        self.assertIn("  shouldReport: False", closeout)
        self.assertIn("manager polling observed unchanged active status", closeout)

    def test_format_task_update_for_user_uses_closeout_only_for_terminal_closeout(self):
        awaiting = self._awaiting_callback_ledger()
        registry = team_router.load_registry(self.root, self.project_id)

        handoff = team_router.format_task_update_for_user(awaiting, registry)

        self.assertIn("Team Router Handoff", handoff)
        self.assertIn("read_thread anchors", handoff)
        self.assertIn("executor.dispatch[1]", handoff)
        self.assertIn("manager watcher:", handoff)
        self.assertIn("nextManagerAction: watch_team_task_with_adapter", handoff)
        self.assertIn("actionOnWake: read_thread", handoff)

        done = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            awaiting["taskId"],
            [
                {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
            ],
            captured_at="2026-06-22T20:04:00+08:00",
        )
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            done["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            done["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: complete\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )

        closeout = team_router.format_task_update_for_user(done, registry)

        self.assertIn("Team Router Closeout", closeout)
        self.assertIn("summary: complete", closeout)
        self.assertIn("remainingTodos: none", closeout)
        self.assertIn("evidenceChecked: tests", closeout)
        self.assertIn("risks: none", closeout)
        self.assertIn("nextAction: none", closeout)
        self.assertIn("plainLanguageReport: required", closeout)
        self.assertIn("notDone: stage/commit/push/PR/publish/release were not done", closeout)
        self.assertIn("compoundingDecision: skipped", closeout)
        self.assertIn("reason: ordinary successful implementation/testing with no new reusable risk", closeout)
        self.assertNotIn("read_thread anchors", closeout)
        self.assertNotIn("TEAM_ROUTER_VERDICT", closeout)

    def test_read_verifier_verdict_update_with_adapter_returns_user_output(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: adapter done\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none"},
        ]

        update = team_router.read_verifier_verdict_update_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["ledger"]["status"], "done")
        self.assertIn("Team Router Closeout", update["userOutput"])
        self.assertIn("summary: adapter done", update["userOutput"])
        self.assertIn("remainingTodos: none", update["userOutput"])
        self.assertIn("compoundingDecision: skipped", update["userOutput"])
        self.assertIn("reason: ordinary successful implementation/testing with no new reusable risk", update["userOutput"])


class TestTeamRouterSkillDoc(unittest.TestCase):
    REQUIRED_SKILL_REFERENCE_FILES = (
        "manager-mode.md",
        "manager-quick-card.md",
        "manager-polling-cadence.md",
        "side-effect-taxonomy.md",
        "role-handoff-and-review-package.md",
        "agent-assist-policy.md",
        "direct-return.md",
        "reviewer-gate.md",
        "conditional-roles.md",
        "role-closeout.md",
        "adapter-runtime.md",
        "manual-orchestration.md",
        "testing-and-quality-gates.md",
    )

    def _skill_path(self):
        return ROOT / "skills" / "codex-team-router" / "SKILL.md"

    def _skill_references_dir(self):
        return ROOT / "skills" / "codex-team-router" / "references"

    def _skill_contract_text(self):
        parts = [self._skill_path().read_text(encoding="utf-8")]
        for filename in self.REQUIRED_SKILL_REFERENCE_FILES:
            parts.append((self._skill_references_dir() / filename).read_text(encoding="utf-8"))
        return "\n\n".join(parts)

    def _section(self, text, heading):
        start = text.index(heading)
        candidates = [
            text.find("\n## ", start + len(heading)),
            text.find("\n### ", start + len(heading)),
        ]
        ends = [candidate for candidate in candidates if candidate != -1]
        if not ends:
            return text[start:]
        return text[start:min(ends)]

    def test_skill_entrypoint_uses_progressive_disclosure_references(self):
        skill_path = self._skill_path()
        references_dir = self._skill_references_dir()
        skill_text = skill_path.read_text(encoding="utf-8-sig")

        self.assertLess(len(skill_path.read_bytes()), 7200)
        self.assertTrue(references_dir.is_dir())
        self.assertIn("Codex 8KB cap", skill_text)
        self.assertIn("references/", skill_text)
        self.assertIn("part of the Team Router contract", skill_text)
        self.assertIn("list_projects -> set_thread_title -> create_thread -> send_message_to_thread -> read_thread", skill_text)
        self.assertIn("Archived role/thread is unavailable for reuse, period", skill_text)
        self.assertIn("non-archived visible role", skill_text)
        self.assertIn("replacement reason", skill_text)
        self.assertIn("no unarchive exception", skill_text)
        self.assertIn("Manager intake separates read-only, dispatch, workspace write, local closeout, and external release gates", skill_text)
        self.assertIn("ambiguous follow-ups never skip the next gate", skill_text)
        self.assertIn("Daily Manager shortcut: `references/manager-quick-card.md`", skill_text)
        self.assertNotIn("reuse it only after it is unarchived", skill_text)
        self.assertNotIn("reuse only after it is unarchived", skill_text)
        for filename in self.REQUIRED_SKILL_REFERENCE_FILES:
            self.assertTrue((references_dir / filename).is_file(), filename)
            self.assertIn("references/%s" % filename, skill_text)

    def test_skill_entrypoint_contains_explicit_path_field_contract(self):
        text = self._skill_path().read_text(encoding="utf-8-sig")
        for needle in (
            "explicit protocol fields",
            "FAST/NORMAL optional",
            "STRICT recommended",
            "PACKAGE default required unless explicit inline fallback is marked",
            "Runtime validates/records supplied path metadata, but does not read, execute, trust, or auto-generate package files.",
        ):
            self.assertIn(needle, text)
        self.assertNotIn(
            "list_projects -> create_thread -> send_message_to_thread -> read_thread",
            text,
        )

    def test_skill_doc_contains_required_boundaries(self):
        text = self._skill_contract_text()
        for needle in (
            "TEAM_ROUTER_PLAN",
            "TEAM_ROUTER_CALLBACK",
            "TEAM_ROUTER_VERDICT",
            "stateRoot",
            "callback_unreachable",
            "planRequest",
            "searchAnchor",
            "recovery_read_request",
            "registry role persistence",
            "read-only/design-only 不是沙箱",
            "local-package",
            "required gates",
            "remainingTodos",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("不支持 `workspace-write`", text)

    def test_skill_doc_documents_cost_aware_v2_routing_contract(self):
        skill = self._skill_path().read_text(encoding="utf-8")
        contract = self._skill_contract_text()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        runbook = (
            ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        ).read_text(encoding="utf-8")
        module_map = (ROOT / "docs" / "team-router" / "module-map.md").read_text(
            encoding="utf-8"
        )

        for needle in (
            "Version 2 Manager direct is decided before ledger, title, heartbeat, or thread operations.",
            "A standard Manager entry does not select a concrete role model.",
            "Explicit cost-aware model entry authorizes Luna Medium, Terra Medium, and Sol High role routing.",
            "Visible Codex role threads only; never fall back to native spawn_agent.",
            "Luna Medium / Terra Medium / Sol High",
            "Sol Ultra is forbidden for role dispatch.",
            "FAST/NORMAL delegated work ends with Manager acceptance; STRICT/PACKAGE requires Reviewer then Verifier.",
        ):
            self.assertIn(needle, skill)

        for needle in (
            "Version 2 has no child Manager role; the parent Manager owns the plan.",
            "Bare Manager Mode is proposal-only.",
            "creation_outcome_unknown",
            "never automatically call create_thread again",
            "canonical JSON",
            "parallelAllowed",
            "Terra Medium is normal execution",
            "Sol High is complex review or the single evidence-preserving upgrade",
            "one automatic model upgrade",
            "hard stop after the second attempt",
            "routingReceipt",
            "requestedModel is not actualModel or billing evidence",
            "repo/global mismatch before sync is expected",
            "Task 10 is a separate explicit global-sync gate",
            "Version 1 compatibility",
        ):
            self.assertIn(needle, contract)

        for text in (readme, runbook):
            self.assertIn("你作为管理者，完成 <目标>", text)
            self.assertIn("按 Luna Medium、Terra Medium、Sol High 成本感知路由完成 <目标>", text)
        self.assertIn("team_router_v2.py", module_map)
        self.assertIn("manager-owned role pools", module_map)

    def test_workbench_tracks_current_task_without_stale_diff_surface(self):
        text = (ROOT / "docs" / "workbench.md").read_text(encoding="utf-8")

        self.assertIn("## Current Task", text)
        self.assertRegex(text, r"(?m)^## Current Diff Surface$")
        self.assertRegex(text, r"(?m)^## Review And Verification Gate$")
        self.assertNotRegex(text, r"(?m)[^\n]## (Current Diff Surface|Review And Verification Gate)$")
        current_task_section = text.split("## Current Task", 1)[1].split("## Current Diff Surface", 1)[0]
        current_diff_section = text.split("## Current Diff Surface", 1)[1].split("## Verification Record", 1)[0]
        historical_section = text.split("## Historical Records", 1)[1].split("## Integration Boundary", 1)[0]
        review_gate_section = text.split("\n## Review And Verification Gate\n", 1)[1]

        for needle in (
            "State: no task-specific state is asserted here",
            "Objective: derive current truth from fresh commands",
            "Current next gate: none",
            "Current truth is command-derived",
            "This file intentionally does not list a live diff surface",
            "scripts/team_router_truth_check.py",
            "scripts/team_router_doctor.py",
            "Current Task / Current Diff Surface style sections",
            "historical package archives are not treated as live truth",
            "Historical Records",
            "completed historical package",
            "not current git truth",
            "Implementation: moved `_latest_executor_callback_observation()`",
            "Previous `ctr-20260630-ledger-transition-state-extraction`",
            "_has_observation_content()",
            "_search_anchor()",
        ):
            self.assertIn(needle, text)
        for stale in (

            "closeout authorization remains pending",
            "no closeout side effect is authorized yet",
            "Current gate: closeout authorization",
        ):
            self.assertNotIn(stale, current_task_section)
        self.assertNotIn("`r`n", text)
        self.assertNotIn("\t", text)
        self.assertNotIn("\b", text)
        self.assertNotIn("`M docs/workbench.md`", current_diff_section)
        self.assertNotIn("closeout authorization remains pending", review_gate_section)
        self.assertIn("Current gate: none", review_gate_section)
        self.assertIn("Commit, push, PR, merge, deploy", review_gate_section)
        self.assertNotIn("none; await the next explicit package dispatch", current_task_section)
        self.assertNotIn("verifier re-check is the current gate", current_task_section)
        self.assertNotIn("active repo-local package `ctr-20260702-single-summary-count-only-return`", current_task_section)
        self.assertNotIn("Current package objective: tighten package-path pass/done return templates", current_task_section)
        self.assertNotIn("Current package starting evidence: compact reviewer/verifier prompts already used package paths", current_task_section)
        self.assertNotIn("Current package boundary", current_task_section)
        self.assertNotIn("Current next gate: local commit closeout for `ctr-20260702-single-summary-count-only-return`", current_task_section)
        self.assertNotIn("ctr-20260702-compact-role-return-payload`", review_gate_section)
        self.assertNotIn("ctr-20260702-direct-return-hard-contract", review_gate_section)
        self.assertNotIn("ctr-20260702-short-role-request-template", review_gate_section)
        self.assertNotIn("ctr-20260702-host-adapter-readiness-check", review_gate_section)
        self.assertNotIn("Current gate: none after local closeout", review_gate_section)
        self.assertIn("Historical Records", text)
        self.assertIn("Older entries are history only", historical_section)
        self.assertIn("ctr-20260628-team-router-optimization-1-6", historical_section)
        for stale_current in (
            "active local package implementation for `ctr-20260628-team-router-optimization-1-6`",
            "active local package implementation for `ctr-20260628-host-adapter-heartbeat-smoke`",
            "host adapter readiness and heartbeat scheduler contract",
            "P2-5 is the current workbench/package-state refresh",
            "Latest `git diff --name-only` reports the same five tracked files",
            "`skillSync.status: mismatch`",
            "active local package implementation for `ctr-20260629-workbench-current-truth-doctor-ux`",
            "active while this local package is awaiting reviewer/verifier gates",
            "module extraction phase 1: policy/protocol split",
            "repo clean before `ctr-20260628-team-router-optimization-local-package` dispatch",
            "wait for a new explicit dispatch or user authorization",
            "No current diff surface is expected in idle state",
            "accepted local-package `ctr-20260630-watcher-status-extraction`",
            "explicit commit authorization for this watcher/status package",
            "send this status/closeout package to verifier after reviewer pass",
            "verifier role-thread gate is pending",
            "send to verifier, then stop",
            "explicit commit authorization for this status/closeout package",
            "closeout recorded for `ctr-20260630-status-closeout-extraction`",
            "local commit was explicitly authorized and completed",
            "none for repo-local status/closeout extraction",
            "send this status-tools package to reviewer, then verifier",
            "repo-local package `ctr-20260630-status-tools-extraction` is locally committed",
            "send this status-tools package to verifier after reviewer re-review pass",
            "send this status-tools package to verifier only",
            "is not yet granted",
            "Commit remains unauthorized until the user explicitly authorizes it",
            "send this dispatch-prompt path-handoff package to reviewer, then verifier",
            "reviewer re-review is pending",
            "Reviewer and verifier gates remain pending",
            "send this dispatch-prompt path-handoff package to verifier final check only",
            "verifier final check remains pending",
            "active local package implementation for `ctr-20260630-dispatch-prompt-path-handoff`",
            "request explicit commit authorization for `ctr-20260630-dispatch-prompt-path-handoff`",
            "Next gated step: request explicit local commit authorization",
            "repo-local dispatch-prompt path-handoff package is locally committed",
            "no repo-local role-thread gate remains",
            "Next external gated step after local commit",
            "Current gate: local commit closeout for `ctr-20260702-md-first-caveman-transport`",
            "Current gate: reviewer for `ctr-20260702-single-summary-count-only-return`",
            "active local package `ctr-20260703-manager-request-compression`",
            "Current next gate: reviewer for `ctr-20260703-manager-request-compression`",
        ):
            self.assertNotIn(stale_current, current_task_section + current_diff_section)
        self.assertNotIn("send this status-tools package to reviewer, then verifier", review_gate_section)
        self.assertNotIn("repo-local package `ctr-20260630-status-tools-extraction` is locally committed", review_gate_section)
        self.assertNotIn("status-tools extraction requires reviewer, then verifier", review_gate_section)
        self.assertNotIn("send this status-tools package to verifier only", review_gate_section)
        self.assertNotIn("is not yet granted", review_gate_section)
        self.assertNotIn("Commit remains unauthorized until the user explicitly authorizes it", review_gate_section)
        self.assertNotIn("verifier is the only remaining role gate before closeout", review_gate_section)

        for stale_current_claim in (
            "[ahead 1]",
            "ahead of `origin/master` by 1",
            "previous helper-test commit `c9d41b3` is local-only",
            r"C:\\Users\\Orz\\.codex\\skills\\codex-team-router",
            "implementation in progress in isolated worktree",
            "thread tools unavailable",
            "reviewer re-review is next",
            "send this dispatch-prompt path-handoff package back to reviewer re-review",
        ):
            self.assertNotIn(stale_current_claim, text)

    def test_runbook_documents_manager_polling_snapshot_fixture(self):
        text = (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(encoding="utf-8")

        for needle in (
            "managerPolling",
            "tests/fixtures/team_router/manager_polling_status_snapshot.json",
            "tests/fixtures/team_router/manager_polling_status_expected_subset.json",
            "--role-status-json",
            "evidence-only",
            "does not call live thread tools",
            "stable reproducible fields",
            "managerPollingStatus.status",
            "Do not compare the full JSON report",
        ):
            self.assertIn(needle, text)

    def test_runbook_documents_host_adapter_readiness_check(self):
        text = (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(encoding="utf-8")

        for needle in (
            "scripts\\team_router_host_adapter_readiness_check.py",
            "tests/fixtures/team_router/host_adapter_callable_ready_snapshot.json",
            "tests/fixtures/team_router/host_adapter_model_descriptors_blocked_snapshot.json",
            "Python-callable injection shape",
            "without calling live thread tools",
            "adapterInjection.threadToolCallsExecuted: 0",
            "tool descriptors are not Python callables",
        ):
            self.assertIn(needle, text)

    def test_watcher_status_package_records_fallback_only_role_delivery(self):
        package = (ROOT / "docs" / "team-router" / "packages" / "ctr-20260630-watcher-status-extraction.md").read_text(encoding="utf-8")

        for needle in (
            "multi_agent/subagent outputs are auxiliary evidence only",
            "deliveryStatus: fallback_only",
            "receiptSource: self-thread-fallback/read_thread",
            "not normal proactive return",
            "direct-send was not observed",
            "Closeout correction reviewer direct-send observed",
            "Closeout correction reviewer deliveryStatus: direct_send",
            "Closeout correction reviewer deliveryError: none",
            "Closeout correction verifier direct-send observed",
            "Closeout correction verifier deliveryStatus: direct_send",
            "Closeout correction verifier deliveryError: none",
            "Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de`",
            "Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60`",
        ):
            self.assertIn(needle, package)

    def test_status_closeout_package_records_extraction_boundary(self):
        package = (ROOT / "docs" / "team-router" / "packages" / "ctr-20260630-status-closeout-extraction.md").read_text(encoding="utf-8")

        for needle in (
            "ctr-20260630-status-closeout-extraction",
            "src/team_router_status.py",
            "format_closeout_for_user",
            "format_handoff_for_user",
            "format_task_update_for_user",
            "watcher_builder",
            "does not import `team_router`",
            "truth_check/doctor/closeout scripts remain read-only evidence tools",
            "real live host integration remains an external host package gate",
            "Commit: authorized by the user and completed as a local commit",
            "TEAM_ROUTER_VERDICT result: pass",
            "No further repo-local status/closeout action remains",
        ):
            self.assertIn(needle, package)

    def test_status_tools_package_records_extraction_boundary(self):
        package = (ROOT / "docs" / "team-router" / "packages" / "ctr-20260630-status-tools-extraction.md").read_text(encoding="utf-8")

        self.assertNotIn("\t", package)
        self.assertNotIn("\b", package)

        for needle in (
            "ctr-20260630-status-tools-extraction",
            "src/team_router_status_tools.py",
            "build_truth_report",
            "build_closeout_report",
            "truth_status",
            "next_action",
            "scripts/team_router_truth_check.py",
            "scripts/team_router_closeout_check.py",
            "scripts/team_router_doctor.py",
            "read-only status tools",
            "does not import `team_router`",
            "does not call thread tools",
            "real live host integration remains an external host package gate",
            "Commit: authorized for local closeout",
        ):
            self.assertIn(needle, package)

    def test_dispatch_prompt_path_handoff_package_records_boundary(self):
        package = (ROOT / "docs" / "team-router" / "packages" / "ctr-20260630-dispatch-prompt-path-handoff.md").read_text(encoding="utf-8")

        self.assertNotIn("\t", package)
        self.assertNotIn("\b", package)

        for needle in (
            "ctr-20260630-dispatch-prompt-path-handoff",
            "baseline: committed status-tools package `4dd5a95`",
            "executorPrompt: <omitted; see taskBriefPath/reviewPackagePath>",
            "stable path handoff",
            "Short executor prompts, no-path inline fallback, `inlineFallback: true`, and executorReportPath-only handoff remain inline",
            "does not generate package files automatically",
            "parser/gate/direct-return semantics",
            "Real live host integration: external host package gate",
            "Commit: authorized by the user and completed as local closeout",
            "reviewer re-review returned `pass` by direct-send with `requiredChanges: none`",
            "Verifier: pass by direct-send; requiredChanges none",
        ):
            self.assertIn(needle, package)

        self.assertNotIn("implements a live host adapter", package)
        self.assertNotIn("production scheduler", package)
        self.assertNotIn("re-review pending", package)
        self.assertNotIn("Reviewer and verifier gates remain pending", package)
        self.assertNotIn("Verifier: final check pending", package)
        self.assertNotIn("Commit: not authorized", package)


    def test_role_thread_readiness_package_tracks_reviewer_pass_before_verifier(self):
        package = (ROOT / "docs" / "team-router" / "packages" / "ctr-20260628-role-thread-readiness-status.md").read_text(encoding="utf-8")

        for needle in (
            "reviewer re-review returned `pass`",
            "verifier re-check returned `pass`",
            "Ask for the next explicit gate",
            "Global skill sync",
            "status: match",
        ):
            self.assertIn(needle, package)
        for stale in (
            "Reviewer re-review: pending",
            "Send the current diff to reviewer re-review",
            "If reviewer passes",
            "Send the package to verifier in read-only mode",
            "global sync remains a separate gate",
            "local closeout/commit, global skill sync, or stop",
        ):
            self.assertNotIn(stale, package)

    def test_module_map_documents_phase1_protocol_policy_split(self):
        text = (ROOT / "docs" / "team-router" / "module-map.md").read_text(encoding="utf-8")

        for needle in (
            "conservative phase 1 split",
            "Public imports continue through `src/team_router.py`",
            "protocol parsing",
            "gate policy",
            "facade and contract snapshot",
            "registry/ledger state",
            "adapter runtime",
            "direct return",
            "watcher/heartbeat",
            "closeout/status",
            "read-only status tools",
            "dispatch prompt path-handoff compaction",
            "reviewer/verifier package-handoff prompt compression",
            "latest executor callback observation helper cut",
            "Role prompt transport still lives here",
            "raw callback or reviewer evidence",
            "overlong `executorPrompt` text",
            "does not change parser/gate/direct-return semantics",
            "docs/skill contract tests",
            "`team_router_protocol.py`",
            "Python standard library only",
            "must not import `team_router` or `team_router_policy`",
            "`team_router_policy.py`",
            "`team_router_runtime.py`",
            "`team_router_direct_return.py`",
            "`team_router_host_runtime.py`",
            "`team_router_watcher_runtime.py`",
            "`team_router_status.py`",
            "`team_router_status_tools.py`",
            "closeout and handoff text helpers",
            "watcher_builder",
            "truth_check/doctor/closeout scripts are thin read-only evidence wrappers",
            "build_truth_report",
            "build_closeout_report",
            "truth_status",
            "next_action",
            "does not import `team_router`",
            "`team_router_protocol.ProtocolError` only",
            "`team_router_protocol`, `team_router_state.StateStoreError`",
            "`protocol_contract_snapshot()`",
            "Deferred Future Modules",
            "Phase 2b2 extracted pure direct-return contract helpers",
            "Phase 2b4 extracted watcher timing/read discipline/heartbeat payload helpers",
            "Phase 2b5 extracted closeout/handoff text helpers",
            "Phase 2b6 extracted read-only status tool helpers",
            "capture/watch/state-save orchestration",
            "remaining safe extraction order is: additional registry/ledger state transitions",
            "_latest_executor_callback_observation()",
            "First tests to move",
            "Acceptance gate",
        ):
            self.assertIn(needle, text)

    def test_quality_gates_name_truth_and_doctor_read_only_tools(self):
        text = (ROOT / "skills" / "codex-team-router" / "references" / "testing-and-quality-gates.md").read_text(encoding="utf-8")

        for needle in (
            "scripts/team_router_truth_check.py",
            "scripts/team_router_doctor.py",
            "must not stage, commit, push, PR, merge, deploy, or sync",
            "refresh workbench/package current-state text from truth_check/doctor evidence before claiming current truth",
            "Current Task / Current Diff Surface / current-state sections",
            "do not replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`",
        ):
            self.assertIn(needle, text)
        self.assertLess(len(self._skill_path().read_bytes()), 7200)

    def test_role_communication_economy_policy_keeps_gates_but_limits_chat(self):
        snapshot = team_router.protocol_contract_snapshot()
        economy = snapshot["roleHandoffReviewPackagePolicy"]["roleCommunicationEconomy"]
        text = self._skill_contract_text()

        self.assertEqual(
            economy["accuracyBoundary"],
            "do not remove executor/reviewer/verifier gates to save tokens",
        )
        self.assertEqual(economy["defaultMode"], "protocol block plus stable path references")
        self.assertEqual(
            economy["designPlanningPolicy"],
            "preserve full brainstorming/spec/plan reasoning; do not compress design gates to save tokens",
        )
        self.assertEqual(
            economy["passResultPolicy"],
            "compact parent callback/verdict on pass/done with exactly one summary field; expand findings/evidence only for needs_rework/fail/blocked",
        )
        self.assertEqual(
            economy["verificationOutputPolicy"],
            "passing returns use count-only evidence format: <reviewPackagePath>; tests: N OK; checks: M OK; paste failure details or rerun verbose only on failure",
        )
        self.assertEqual(
            economy["threadPollingPolicy"],
            "manager inbox direct-return first; self-thread read_thread is bounded degraded fallback only",
        )
        self.assertIn("delta-only follow-up", economy["followUpPolicy"])
        self.assertIn("do not restate background", economy["followUpPolicy"])
        self.assertEqual(
            economy["longContextPolicy"],
            "move long context, diff evidence, logs, and detailed reports into taskBriefPath, executorReportPath, or reviewPackagePath",
        )
        self.assertEqual(
            economy["managerCloseoutPolicy"],
            "manager closeout reports acceptedBy, changed, verified, remainingRisk, nextGate, and compoundingDecision without copying full role reasoning",
        )
        self.assertEqual(
            economy["budgetHintsTokens"],
            {
                "dispatch": "300-500",
                "executorCallback": "500-800",
                "architect": "400-700",
                "reviewer": "400-700",
                "qa": "400-700",
                "verifier": "300-600",
            },
        )
        for needle in (
            "Role Communication Economy",
            "do not remove executor/reviewer/verifier gates to save tokens",
            "protocol block plus stable path references",
            "delta-only follow-up",
            "taskBriefPath",
            "executorReportPath",
            "reviewPackagePath",
            "acceptedBy, changed, verified, remainingRisk, nextGate, and compoundingDecision",
            "preserve full brainstorming/spec/plan reasoning",
            "pass/done",
            "passing tests report command, suite count, and OK",
            "manager inbox direct-return first",
        ):
            self.assertIn(needle, text)

    def test_quality_gates_document_role_thread_status_snapshots(self):
        text = (ROOT / "skills" / "codex-team-router" / "references" / "testing-and-quality-gates.md").read_text(encoding="utf-8")

        for needle in (
            "--host-readiness-json",
            "hostReadiness",
            "missing",
            "created_not_visible",
            "visible_waiting",
            "active_wait",
            "protocol_returned",
            "caller-supplied role-thread snapshot",
            "does not create, read, poll, send, stage, commit, push, PR, merge, deploy, or sync",
        ):
            self.assertIn(needle, text)

    def test_quality_gates_document_host_readiness_snapshots(self):
        text = (ROOT / "skills" / "codex-team-router" / "references" / "testing-and-quality-gates.md").read_text(encoding="utf-8")

        for needle in (
            "--host-readiness-json",
            "hostReadiness",
            "host_contract_blocked",
            "adapter_smoke_ready",
            "callable adapter",
            "parent_thread_id",
            "callable heartbeat scheduler",
            "model-side Codex app tool exposure is not a Python callable adapter",
            "evidence-only host adapter readiness snapshot",
        ):
            self.assertIn(needle, text)
    def test_thread_tool_absence_is_tool_error_or_manual_only_not_role_dispatch(self):
        text = self._skill_contract_text()

        for needle in (
            "When required thread tools are not exposed in the current host",
            "`tool_error` / `manual orchestration only`",
            "must not claim that visible role threads were created, dispatched, reused, watched, or completed",
            "copy-paste executor/reviewer/verifier prompts are handoff text, not live Team Router dispatch evidence",
        ):
            self.assertIn(needle, text)

        self.assertNotIn(
            "If required tools are missing, continue by describing created role threads",
            text,
        )

    def test_workbench_tracks_live_capability_state_without_tool_surface_drift(self):
        workbench = (ROOT / "docs" / "workbench.md").read_text(encoding="utf-8")
        package = (
            ROOT
            / "docs"
            / "team-router"
            / "packages"
            / "ctr-20260628-live-capability-state-fix.md"
        ).read_text(encoding="utf-8")
        combined = workbench + "\n" + package

        for needle in (
            "tool surface available",
            "callable adapter unavailable",
            "live orchestration not ready",
            "list_projects/create_thread/read_thread/send_message_to_thread/list_threads/set_thread_title",
            "Python callable adapter",
            "parent_thread_id",
            "scheduler/heartbeat",
        ):
            self.assertIn(needle, combined)

        self.assertNotIn("thread tools unavailable", workbench)
        self.assertNotIn("thread tools unavailable", package)

    def test_role_requests_require_direct_send_and_bounded_waiting_contract(self):
        contract = self._skill_contract_text()
        workbench = (ROOT / "docs" / "workbench.md").read_text(encoding="utf-8")
        package = (
            ROOT
            / "docs"
            / "team-router"
            / "packages"
            / "ctr-20260628-role-request-direct-send-and-waiting-fix.md"
        ).read_text(encoding="utf-8")
        combined = contract + "\n" + workbench + "\n" + package

        for needle in (
            "callbackDelivery: direct-send",
            "callbackFallback: self-thread-marker",
            "reviewDelivery: direct-send",
            "reviewFallback: self-thread-marker",
            "verdictDelivery: direct-send",
            "verdictFallback: self-thread-marker",
            "protocol direct-send is allowed and is not a workspace/file write",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)",
            "then output the same protocol block body as the self-thread-marker fallback",
            "one short observation-only first check, then stop proactive reads until firstCheckAt or nextAllowedReadAt",
            "inProgress is not polling permission",
            "CONTROL after bounded wait/read is not permission for immediate continuous read_thread polling",
            "wait for direct-send, user-triggered status/stop/immediate, firstCheckAt, nextAllowedReadAt, known expected completion window, or timeout/blocker handling",
        ):
            self.assertIn(needle, combined)

    def test_anchor_and_closeout_freshness_after_verifier_pass(self):
        contract = self._skill_contract_text()
        workbench = (ROOT / "docs" / "workbench.md").read_text(encoding="utf-8")
        role_package = (
            ROOT
            / "docs"
            / "team-router"
            / "packages"
            / "ctr-20260628-role-request-direct-send-and-waiting-fix.md"
        ).read_text(encoding="utf-8")
        cleanup_package = (
            ROOT
            / "docs"
            / "team-router"
            / "packages"
            / "ctr-20260628-anchor-and-closeout-freshness-fix.md"
        ).read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"(?<!t)hreadId=(?:<|&lt;|&amp;lt;)", contract))
        self.assertNotIn("\\threadId=<returnThreadId>", contract)
        self.assertIn("`threadId=<returnThreadId>`", contract)
        self.assertIn("ctr-20260628-anchor-and-closeout-freshness-fix", cleanup_package)
        self.assertIn("verifier accepted/pass", workbench)
        self.assertIn("verifier accepted/pass", role_package)
        self.assertIn("remainingTodos: none for this local package", role_package)
        for stale in (
            "then verifier acceptance",
            "verifier acceptance remains the external gate",
        ):
            self.assertNotIn(stale, workbench)
            self.assertNotIn(stale, role_package)
            self.assertNotIn(stale, cleanup_package)
    def test_skill_doc_contains_parent_thread_operating_flow(self):
        text = self._skill_contract_text()
        for needle in (
            "## Parent Thread Entry Flow",
            "list_projects -> set_thread_title -> create_thread -> send_message_to_thread -> read_thread",
            "parent_thread_id",
            "before child-role dispatch",
            "parent_entry_guard()",
            "protocol_contract_snapshot()",
            "orchestrate_team_task_with_adapter()",
            "run_team_task_with_adapter()",
            "watch_team_task_with_adapter()",
            "start_team_task_with_adapter()",
            "send_manager_plan_request_with_adapter()",
            "read_manager_plan_with_adapter()",
            "send_executor_dispatch_with_adapter()",
            "read_executor_callback_with_adapter()",
            "send_verifier_request_with_adapter()",
            "read_verifier_verdict_update_with_adapter()",
            "emit `update[\"userOutput\"]`",
            "callbackDelivery: direct-send",
            "callbackFallback: self-thread-marker",
            "reviewDelivery: direct-send",
            "reviewFallback: self-thread-marker",
            "verdictDelivery: direct-send",
            "verdictFallback: self-thread-marker",
            "callbackMarker: TEAM_ROUTER_CALLBACK taskId=<taskId>",
            "callbackMarker: TEAM_ROUTER_REVIEW taskId=<taskId>",
            "callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>",
            "returnThreadId",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)",
            "watcher/scheduler polling is the fallback",
            "self-thread-marker writes only to the role thread",
            "does not automatically appear in the manager/main thread",
            "explicit result collection read/check",
            "one deliberate collection check",
        ):
            self.assertIn(needle, text)
        skill_entrypoint = self._skill_path().read_text(encoding="utf-8-sig")
        self.assertNotIn("send_message_to_thread(sourceThreadId, protocolBlock)", skill_entrypoint)
        direct_return_reference = (
            self._skill_references_dir() / "direct-return.md"
        ).read_text(encoding="utf-8")
        legacy_section = direct_return_reference.split("Compatibility anchor: legacy shorthand", 1)[1]
        self.assertIn("send_message_to_thread(sourceThreadId, protocolBlock)", legacy_section)

    def test_team_router_docs_describe_active_role_return(self):
        docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md",
                ROOT / "skills" / "codex-team-router" / "references" / "manager-mode.md",
                ROOT / "skills" / "codex-team-router" / "references" / "manual-orchestration.md",
                ROOT / "skills" / "codex-team-router" / "references" / "testing-and-quality-gates.md",
            )
        )
        for needle in (
            "direct-send + self-thread-marker fallback",
            "Bare `create_thread` plus `read_thread` is not formal role dispatch or direct-return completion",
            "A manager-read child-thread result is degraded/manual collection",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)",
            "sourceRoleThreadId",
            "role",
            "taskId",
            "two-step bootstrap",
            "deliveryStatus: fallback_only",
            "deliveryError",
            "receiptSource: <manager-inbox/direct-send or self-thread-fallback/read_thread>",
            "receiptChannel: <manager-inbox or read_thread>",
            "same protocol block body",
            "bounded result-collection read/check",
            "continuous polling is not the default",
            "After bounded wait/read with no final protocol block",
            "scope-limited closeout from already-confirmed facts",
        ):
            self.assertIn(needle, docs)
        self.assertNotIn("after it writes the marker in its own thread", docs)

        runbook = (
            ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "first call `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)` with the final protocol block, then output the same protocol block body in the role thread as self-thread-marker fallback",
            runbook,
        )
        runbook_main = runbook.split("Compatibility anchor:", 1)[0]
        runbook_compatibility = runbook.split("Compatibility anchor:", 1)[1]
        self.assertNotIn("send_message_to_thread(sourceThreadId, protocolBlock)", runbook_main)
        self.assertNotIn(
            "first call `send_message_to_thread(sourceThreadId, protocolBlock)`",
            runbook_main,
        )
        self.assertIn("send_message_to_thread(sourceThreadId, protocolBlock)", runbook_compatibility)
        for needle in (
            "Bare `create_thread` plus `read_thread` is not formal role dispatch or direct-return completion",
            "A manager-read child-thread result is degraded/manual collection",
            "formally dispatched with `returnThreadId` and `sourceRoleThreadId`",
            "Bare `create_thread` plus later `read_thread` is not a valid Team Router role return",
            "manual/degraded collection only",
            "receiptSource: <manager-inbox/direct-send or self-thread-fallback/read_thread>",
            "receiptChannel: <manager-inbox or read_thread>",
        ):
            self.assertIn(needle, runbook)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_main = readme.split("Compatibility note:", 1)[0]
        readme_compatibility = readme.split("Compatibility note:", 1)[1]
        self.assertIn(
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)",
            readme_main,
        )
        self.assertNotIn("send_message_to_thread(sourceThreadId, protocolBlock)", readme_main)
        self.assertIn("send_message_to_thread(sourceThreadId, protocolBlock)", readme_compatibility)

    def test_direct_return_reference_matches_active_role_return_contract(self):
        text = (self._skill_references_dir() / "direct-return.md").read_text(encoding="utf-8")
        for needle in (
            "first call `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`",
            "then output the same protocol block body",
            "sourceThreadId",
            "sourceRoleThreadId",
            "protocol block",
            "must match the pending ledger `returnThreadId`",
            "must match the expected `roleThreadId` / role thread record",
            "wrapper source identifies the role thread",
            "validate `sourceRoleThreadId` against the expected `roleThreadId` / role thread record.",
            "role: Executor",
            "role: Reviewer",
            "role: Verifier",
            "callbackDelivery: direct-send",
            "reviewDelivery: direct-send",
            "verdictDelivery: direct-send",
            "callbackFallback: self-thread-marker",
            "reviewFallback: self-thread-marker",
            "verdictFallback: self-thread-marker",
            "deliveryStatus: fallback_only",
            "deliveryError",
            "fallback-only is degraded delivery",
            "not normal proactive return",
            "watcher 300s fallback",
            "Bare `create_thread` plus later `read_thread` is not a valid Team Router role return.",
            "formally dispatched with `returnThreadId` and `sourceRoleThreadId`",
            "Manager accepts direct-send only when `taskId`, protocol-block `sourceThreadId`, `role`, and `sourceRoleThreadId` all match the pending role ledger entry, including that `sourceThreadId` matches the pending ledger `returnThreadId`.",
            "rejected/quarantined",
            "cannot expand scope",
        ):
            self.assertIn(needle, text)
        self.assertNotIn(
            "Manager accepts direct-send only when `taskId`, `role`, and `sourceRoleThreadId`",
            text,
        )
        for stale in (
            "directReturnAttempt",
            "The role still writes its final marker in its own thread, then sends",
        ):
            self.assertNotIn(stale, text)
        active_contract = text.split("Compatibility anchor: legacy shorthand", 1)[0]
        legacy_contract = text.split("Compatibility anchor: legacy shorthand", 1)[1]
        self.assertNotIn(
            "first call `send_message_to_thread(sourceThreadId, protocolBlock)`",
            active_contract,
        )
        self.assertIn("send_message_to_thread(sourceThreadId, protocolBlock)", legacy_contract)
        self.assertIn(
            "Legacy wording: first call `send_message_to_thread(sourceThreadId, protocolBlock)`",
            legacy_contract,
        )

    def test_skill_sync_check_script_defaults_to_read_only_check(self):
        script = ROOT / "scripts" / "team_router_skill_sync_check.py"
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            repo_skill = tmp_path / "repo" / "codex-team-router"
            global_skill = tmp_path / "global" / "codex-team-router"
            repo_skill.mkdir(parents=True)
            global_skill.mkdir(parents=True)
            (repo_skill / "SKILL.md").write_text("repo\n", encoding="utf-8")
            (global_skill / "SKILL.md").write_text("global\n", encoding="utf-8")

            before = (global_skill / "SKILL.md").read_text(encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repo-skill",
                    str(repo_skill),
                    "--global-skill",
                    str(global_skill),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("mode: check-only", result.stdout)
            self.assertIn("status: mismatch", result.stdout)
            self.assertIn("SKILL.md", result.stdout)
            self.assertEqual((global_skill / "SKILL.md").read_text(encoding="utf-8"), before)

    def test_skill_sync_check_script_reports_match_without_writes(self):
        script = ROOT / "scripts" / "team_router_skill_sync_check.py"
        with workspace_temp_dir() as tmp:
            tmp_path = Path(tmp)
            repo_skill = tmp_path / "repo" / "codex-team-router"
            global_skill = tmp_path / "global" / "codex-team-router"
            repo_skill.mkdir(parents=True)
            global_skill.mkdir(parents=True)
            (repo_skill / "SKILL.md").write_text("same\n", encoding="utf-8")
            (global_skill / "SKILL.md").write_text("same\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repo-skill",
                    str(repo_skill),
                    "--global-skill",
                    str(global_skill),
                    "--check",
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("mode: check-only", result.stdout)
            self.assertIn("status: match", result.stdout)
    def test_skill_doc_contains_chinese_role_model(self):
        text = self._skill_contract_text()
        for needle in (
            "## Role Model",
            "调度者 (Orchestrator)",
            "工具宿主边界 (Adapter Host Boundary)",
            "状态控制器 (State Controller)",
            "规划者 (Manager)",
            "执行者 (Executor)",
            "验证者 (Verifier)",
            "只有规划者、执行者、验证者是长期 role thread",
            "父线程侧状态控制器 (Parent-Side State Controller)",
            "Visible Codex desktop thread titles use `角色-任务名`",
            "`调度者-Team Router",
            "`执行者-Team Router 管理者模式触发词修复`",
            "`验证者-Team Router 管理者模式触发词修复`",
            "set_thread_title",
            "Skill/rule/process writes route executor -> reviewer -> verifier",
            "Superpowers grants no manager write authority",
            "Title changes require explicit current-turn authorization",
            "before creating, dispatching, or normalizing child role threads",
            "explicit role-intent phrases",
            "“你是管理者”",
            "“你作为管理者”",
            "“团队管理者”",
            "“进入 Manager Mode”",
            "`act as team manager`",
            "裸 `manager` 不触发 Manager Mode",
            "`manager thread`",
            "`manager parser`",
            "`manager integration`",
            "continues an already-active Manager Mode task with terse follow-ups",
            "Manager Mode is sticky for the current task",
            "A terse follow-up or implementation command such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` is not execution or dispatch authorization",
            "`先修`",
            "`开始修`",
            "`修这个`",
            "`开始处理`",
            "`先处理`",
            "`按刚才说的修`",
            "propose rule updates",
            "classifying sideEffectTaxonomy/Fast Lane",
            "exact executor delegation",
            "executor write authority stays inside the delegated explicit scope",
            "Manager Mode 禁止亲自修改文件、跑测试、执行实现命令、push、PR 或 merge",
            "If implementation is requested during active Manager Mode",
            "Do not personally edit files or run project commands from Manager Mode",
            "除非用户明确说“切回执行者”",
            "“你亲自改代码”",
            "current-turn user authorization for manager file edits",
        ):
            self.assertIn(needle, text)
        manager_mode = self._section(text, "### Manager Mode Hard Rule")
        self.assertNotIn(
            "`manager`, or `team manager`, the assistant enters Manager Mode",
            manager_mode,
        )
        self.assertNotIn("“" + "直接" + "改”", manager_mode)
        self.assertNotIn("你" + "来执行", manager_mode)
        self.assertNotIn("while the user is still addressing" + " the agent as manager", manager_mode)
        self.assertNotIn("update the rules", manager_mode)
        for needle in (
            "skill/process requests such as `记录进skill`",
            "`优化 skill`",
            "`改规则`",
            "`修`",
            "`继续`",
            "`复利`",
            "Superpowers can guide planning/TDD/debugging/verification",
            "does not grant manager write authority",
            "File changes must route through executor/reviewer/verifier",
            "delegation must include `taskId`, objective, scope/files",
            "route executor -> reviewer -> verifier",
        ):
            self.assertIn(needle, manager_mode)

    def test_skill_doc_separates_adapter_created_and_precreated_role_paths(self):
        text = self._skill_contract_text()

        adapter_created = self._section(text, "### Adapter-created roles path")
        pre_created = self._section(text, "### Pre-created roles path")
        adapter_continuation = self._section(text, "### Adapter continuation")
        manual_continuation = self._section(text, "### Manual/pre-created continuation")

        self.assertIn("start_team_task_with_adapter()", adapter_created)
        self.assertIn("Do not pre-call `create_thread`", adapter_created)
        self.assertIn("create_team_task()", pre_created)
        self.assertIn(
            "Do not call `start_team_task_with_adapter()` after manually creating role threads",
            pre_created,
        )
        for needle in (
            "send_manager_plan_request_with_adapter()",
            "read_manager_plan_with_adapter()",
            "send_executor_dispatch_with_adapter()",
            "read_executor_callback_with_adapter()",
            "send_verifier_request_with_adapter()",
            "read_verifier_verdict_update_with_adapter()",
        ):
            self.assertIn(needle, adapter_continuation)
        for needle in (
            "send_message_to_thread",
            "read_thread",
            "thread_send_anchor()",
            "normalize_thread_read_messages()",
            "record_plan_request_sent()",
            "capture_manager_plan_from_read()",
            "record_executor_dispatch_sent()",
            "capture_executor_callback_from_read()",
            "record_verifier_request_sent()",
            "capture_verifier_verdict_from_read()",
            "format_task_update_for_user()",
        ):
            self.assertIn(needle, manual_continuation)
        self.assertNotIn("send_manager_plan_request_with_adapter()", manual_continuation)
        self.assertNotIn("read_verifier_verdict_update_with_adapter()", manual_continuation)
        self.assertIn("does not continue through `orchestrate_team_task_with_adapter()`", manual_continuation)
        self.assertIn("not an end-to-end adapter-runner entrypoint", manual_continuation)

    def test_live_orchestration_runbook_exists(self):
        path = ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        text = path.read_text(encoding="utf-8")
        for needle in (
            "# Codex Team Router Live Orchestration Runbook",
            "create_thread",
            "send_message_to_thread",
            "read_thread",
            "parent_entry_guard()",
            "orchestrate_team_task_with_adapter()",
            "run_team_task_with_adapter()",
            "watch_team_task_with_adapter()",
            "read_verifier_verdict_update_with_adapter()",
            "tests/fixtures/team_router/live_read_thread_verdict.json",
            "tests/fixtures/team_router/live_manager_inbox_direct_return.json",
            "tests/fixtures/team_router/three_role_visible_smoke_scenarios.json",
            "Emit `update[\"userOutput\"]` exactly",
            "Team Router Closeout",
            "Team Router Handoff",
            "direct-send-callback-success",
            "direct-send-missed-self-thread-fallback",
            "verifier-needs-rework",
            "verifier-blocked-closeout",
            "remainingTodos",
            "callbackDelivery: direct-send",
            "callbackFallback: self-thread-marker",
            "reviewDelivery: direct-send",
            "reviewFallback: self-thread-marker",
            "verdictDelivery: direct-send",
            "verdictFallback: self-thread-marker",
            "callbackMarker: TEAM_ROUTER_CALLBACK taskId=<taskId>",
            "callbackMarker: TEAM_ROUTER_REVIEW taskId=<taskId>",
            "callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>",
            "returnThreadId",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)",
            "Watcher polling is the fallback path",
            "self-thread-marker writes only to the role thread",
            "does not automatically appear in the manager/main thread",
            "explicit result collection read/check",
            "one deliberate collection check",
            "调度者 (Orchestrator)",
            "规划者 (Manager)",
            "执行者 (Executor)",
            "验证者 (Verifier)",
            "Visible Codex desktop thread titles use `角色-任务名`",
            "`调度者-Team Router",
            "`执行者-Team Router 管理者模式触发词修复`",
            "`验证者-Team Router 管理者模式触发词修复`",
            "set_thread_title",
            "explicit role-intent phrases",
            "“你是管理者”",
            "“你作为管理者”",
            "“团队管理者”",
            "“进入 Manager Mode”",
            "`act as team manager`",
            "裸 `manager` 不触发 Manager Mode",
            "`manager thread`",
            "`manager parser`",
            "`manager integration`",
            "Manager Mode is sticky for the current task",
            "A terse follow-up or implementation command such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` is not execution or dispatch authorization",
            "`先修`",
            "`开始修`",
            "`修这个`",
            "`开始处理`",
            "`先处理`",
            "`按刚才说的修`",
            "propose rule updates",
            "Do not personally edit files or run project commands from Manager Mode",
            "“你亲自改代码”",
            "Manager file edits require explicit current-turn user authorization",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("“" + "直接" + "改”", text)
        self.assertNotIn("你" + "来执行", text)
        self.assertNotIn("while the user is still addressing" + " the agent as manager", text)

    def test_readme_and_runbook_document_skill_progressive_disclosure(self):
        paths = (
            ROOT / "README.md",
            ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for needle in (
                    "Progressive disclosure invariant",
                    "SKILL.md",
                    "Codex 8KB cap",
                    "references/",
                    "Team Router contract",
                ):
                    self.assertIn(needle, text)
        self.assertNotIn("update the rules", text)

    def test_side_effect_taxonomy_docs_cover_manager_action_boundaries(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "sideEffectTaxonomy",
                    "READ_ONLY",
                    "DISPATCH_ONLY",
                    "LOCAL_CLOSEOUT",
                    "WORKSPACE_WRITE",
                    "HEAVY_OR_RISKY",
                    "EXTERNAL_RELEASE",
                    "`可以`",
                    "`修`",
                    "`继续`",
                    "`开始修`",
                    "`先修`",
                    "`修这个`",
                    "`do it`",
                    "verifier pass",
                    "explicit user commit request",
                    "push/PR/merge/deploy",
                    "subagent fallback is not allowed",
                ):
                    self.assertIn(needle, text)
                for alternatives in (
                    ("authorize only a dispatch proposal", "只授权派工方案"),
                    ("not implementation authorization", "不是 implementation authorization", "not actual `DISPATCH_ONLY` or implementation", "不授权实际 `DISPATCH_ONLY` 或 implementation"),
                    ("explicit `local-package` executor delegation", "明确 `local-package` executor delegation", "explicitly grants an authorized `local-package` scope"),
                    ("explicitly switches roles", "明确说“切回执行者”"),
                    ("manager file edits", "manager file-edit authorization"),
                    ("current-turn user authorization", "current turn", "当轮明确授权"),
                    ("stage only accepted files", "stage 已验收文件"),
                    ("unrelated untracked", "无关 untracked"),
                    ("separate publish/release authorization", "独立 publish/release 授权"),
                    ("explicit separate authorization", "单独明确授权"),
                ):
                    self.assertTrue(
                        any(needle in text for needle in alternatives),
                        "%s missing one of %r" % (name, alternatives),
                    )

    def test_role_handoff_and_review_package_policy_docs_cover_stable_packages(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                common_needles = (
                    "roleHandoffPolicy",
                    "reviewPackagePolicy",
                    "stable file/path handoff",
                    "accumulated chat history",
                    "taskBriefPath",
                    "executorReportPath",
                    "reviewPackagePath",
                    "taskId",
                    "objective",
                    "scope",
                    "diff summary",
                    "executor callback/report",
                    "TEAM_ROUTER_CALLBACK",
                    "TEAM_ROUTER_REVIEW",
                    "TEAM_ROUTER_VERDICT",
                    "WORKSPACE_WRITE",
                    "executor",
                    "git diff --name-only",
                    "untracked files",
                )
                for needle in common_needles:
                    self.assertIn(needle, text)
                if name in ("README.md", "codex-team-router skill contract"):
                    for needle in (
                        "explicit protocol fields",
                        "FAST/NORMAL optional",
                        "STRICT recommended",
                        "PACKAGE default required unless explicit inline fallback is marked",
                    ):
                        self.assertIn(needle, text)
                self.assertNotIn("Writing workspace package artifacts is `WORKSPACE_WRITE` and should be executor work in active Manager Mode unless there is an explicit role switch", text)
                self.assertNotIn("写 workspace package artifacts 属于 `WORKSPACE_WRITE`，active Manager Mode 下应由 executor 做，除非明确角色切换", text)
                common_alternatives = (
                    ("stable facts by file/path", "stable file/path handoff"),
                    ("inline protocol block fallback", "inline protocol blocks"),
                    ("does not replace", "不替代"),
                    ("supplements evidence", "补充证据"),
                    ("validates and records supplied path metadata", "验证并记录这些 path metadata"),
                    ("stage new reference files explicitly", "显式 stage 新 reference files"),
                    ("role threads can access the same workspace/path", "shared workspace/path is accessible", "可访问同一 workspace/path"),
                    ("Writing workspace package artifacts", "写 workspace package artifacts"),
                    ("explicit current-turn user authorization for manager file edits", "authorizes manager file edits in the current turn", "当轮明确授权 manager file edits"),
                    ("READ_ONLY", "DISPATCH_ONLY"),
                    ("touched/accepted files", "touched files"),
                    ("test/verification evidence", "verification evidence and actual commands/results"),
                    ("reviewer requiredChanges", "reviewer findings and `requiredChanges`"),
                    ("excluded unrelated untracked", "excluded unrelated changes and untracked files"),
                    ("risks/remainingTodos", "remainingTodos"),
                )
                for alternatives in common_alternatives:
                    self.assertTrue(
                        any(needle in text for needle in alternatives),
                        "%s missing one of %r" % (name, alternatives),
                    )
                if name in ("README.md", "codex-team-router skill contract"):
                    for alternatives in (
                        ("FAST/NORMAL optional", "FAST / NORMAL optional"),
                        ("STRICT recommended", "`STRICT` recommended"),
                        ("PACKAGE default required unless explicit inline fallback is marked", "`PACKAGE` default required unless explicit inline fallback is marked"),
                    ):
                        self.assertTrue(
                            any(needle in text for needle in alternatives),
                            "%s missing one of %r" % (name, alternatives),
                        )

    def test_live_orchestration_runbook_separates_adapter_created_and_precreated_role_paths(self):
        path = ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        text = path.read_text(encoding="utf-8")

        adapter_created = self._section(text, "### Adapter-created roles path")
        pre_created = self._section(text, "### Pre-created roles path")
        adapter_continuation = self._section(text, "### Adapter continuation")
        manual_continuation = self._section(text, "### Manual/pre-created continuation")

        self.assertIn("start_team_task_with_adapter()", adapter_created)
        self.assertIn("Do not pre-call `create_thread`", adapter_created)
        self.assertIn("create_team_task()", pre_created)
        self.assertIn(
            "Do not call `start_team_task_with_adapter()` after manually creating role threads",
            pre_created,
        )
        for needle in (
            "send_message_to_thread",
            "read_thread",
            "record_plan_request_sent()",
            "capture_manager_plan_from_read()",
            "record_executor_dispatch_sent()",
            "capture_executor_callback_from_read()",
            "record_verifier_request_sent()",
            "capture_verifier_verdict_from_read()",
        ):
            self.assertIn(needle, manual_continuation)
        self.assertIn("read_verifier_verdict_update_with_adapter()", adapter_continuation)
        self.assertNotIn("send_manager_plan_request_with_adapter()", manual_continuation)
        self.assertIn("does not continue through `orchestrate_team_task_with_adapter()`", manual_continuation)
        self.assertIn("not an end-to-end adapter-runner entrypoint", manual_continuation)

    def test_conditional_roles_reference_documents_architect_qa_contract(self):
        reference = self._skill_references_dir() / "conditional-roles.md"
        self.assertTrue(reference.exists())
        text = reference.read_text(encoding="utf-8")

        for heading in (
            "## Architect",
            "## QA",
            "## Boundaries",
            "## Markers",
            "## Rework",
            "## Direct Return",
            "## Testing",
        ):
            self.assertIn(heading, text)
        for needle in (
            "CORE_ROLE_NAMES remains unchanged",
            "no runtime skill loading",
            "no custom role registry",
            "QA does not replace verifier",
            "architect/QA do not replace reviewer",
            "TEAM_ROUTER_ARCHITECT_REVIEW",
            "TEAM_ROUTER_QA_REVIEW",
            "sourceThreadId",
            "sourceRoleThreadId",
            "role",
            "skillProfileUsed",
            "architectureReview.request",
            "qaReview.request",
            "architect-default",
            "qa-default",
        ):
            self.assertIn(needle, text)

    def test_skill_entrypoint_mentions_conditional_roles_reference_under_size_cap(self):
        skill_path = self._skill_path()
        text = skill_path.read_text(encoding="utf-8-sig")

        self.assertIn("architect", text)
        self.assertIn("qa", text)
        self.assertIn("references/conditional-roles.md", text)
        self.assertLess(skill_path.stat().st_size, 8192)

    def test_conditional_roles_cross_links_update_existing_references(self):
        references = {
            "direct-return.md": (
                "architect -> TEAM_ROUTER_ARCHITECT_REVIEW",
                "qa -> TEAM_ROUTER_QA_REVIEW",
                "architectureReview.request",
                "qaReview.request",
                "sourceRoleThreadId",
            ),
            "reviewer-gate.md": (
                "architect/QA do not replace reviewer",
                "reviewer remains separate from architect/QA",
                "QA does not replace verifier",
            ),
            "manager-polling-cadence.md": (
                "architectureReview.request",
                "qaReview.request",
                "TEAM_ROUTER_ARCHITECT_REVIEW",
                "TEAM_ROUTER_QA_REVIEW",
                "architect_review_unreachable",
                "qa_review_unreachable",
            ),
            "testing-and-quality-gates.md": (
                "architect_only",
                "qa_only",
                "architect_reviewer_no_qa",
                "architect_reviewer_qa",
                "qa_needs_rework",
                "architect_blocked",
                "qa_blocked",
            ),
        }
        for filename, needles in references.items():
            with self.subTest(filename=filename):
                text = (self._skill_references_dir() / filename).read_text(encoding="utf-8")
                self.assertIn("references/conditional-roles.md", text)
                for needle in needles:
                    self.assertIn(needle, text)

    def test_architect_qa_visible_smoke_fixture_covers_required_paths(self):
        path = ROOT / "tests" / "fixtures" / "team_router" / "architect_qa_visible_smoke_scenarios.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        scenarios = {scenario["name"]: scenario for scenario in raw["scenarios"]}

        self.assertEqual(raw["markers"]["architect"], "TEAM_ROUTER_ARCHITECT_REVIEW")
        self.assertEqual(raw["markers"]["qa"], "TEAM_ROUTER_QA_REVIEW")
        self.assertEqual(
            set(scenarios),
            {
                "architect_only",
                "qa_only",
                "architect_reviewer_no_qa",
                "architect_reviewer_qa",
                "qa_needs_rework",
                "architect_blocked",
                "qa_blocked",
            },
        )
        self.assertEqual(scenarios["architect_only"]["roleFlow"], ["architect", "executor", "verifier"])
        self.assertEqual(scenarios["qa_only"]["roleFlow"], ["executor", "qa", "verifier"])
        self.assertEqual(scenarios["architect_reviewer_no_qa"]["roleFlow"], ["architect", "executor", "reviewer", "verifier"])
        self.assertEqual(scenarios["architect_reviewer_qa"]["roleFlow"], ["architect", "executor", "reviewer", "qa", "verifier"])
        self.assertEqual(scenarios["qa_needs_rework"]["roleFlow"], ["executor", "qa", "executor", "qa", "verifier"])
        self.assertEqual(scenarios["architect_blocked"]["expectedStatus"], "blocked")
        self.assertEqual(scenarios["qa_blocked"]["expectedStatus"], "blocked")
        self.assertIn("QA pass is verifier input, not final acceptance", raw["notes"])
        self.assertIn("reviewer remains separate from architect and qa", raw["notes"])
    def test_three_role_visible_smoke_fixture_covers_required_paths(self):
        path = ROOT / "tests" / "fixtures" / "team_router" / "three_role_visible_smoke_scenarios.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        names = {scenario["name"] for scenario in raw["scenarios"]}

        self.assertEqual(raw["roles"]["manager"], "规划者")
        self.assertIn("调度者", raw["parentSideConcepts"])
        self.assertNotIn("父线程" + "调度者", raw["parentSideConcepts"])
        self.assertEqual(
            names,
            {
                "direct-send-callback-success",
                "direct-send-missed-self-thread-fallback",
                "verifier-needs-rework",
                "verifier-blocked-closeout",
            },
        )
        direct = next(s for s in raw["scenarios"] if s["name"] == "direct-send-callback-success")
        self.assertIn("returnThreadId", direct["requiredLedgerFields"])
        self.assertIn("fallbackSearchAnchor", direct["requiredLedgerFields"])

    def test_readme_documents_team_router_quick_start_and_boundaries(self):
        path = ROOT / "README.md"
        text = path.read_text(encoding="utf-8")
        for needle in (
            "## Team Router 快速使用",
            "`codex-team-router`",
            "`dynamic-workflow`",
            "read-only/design-only",
            "`local-package`",
            "workspace-write scope",
            "不授权 manager 直接改文件",
            "调度者",
            "规划者",
            "执行者",
            "验证者",
            "审查者",
            "TEAM_ROUTER_REVIEW",
            "reviewDelivery: direct-send",
            "reviewFallback: self-thread-marker",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)",
            "parent_entry_guard()",
            "protocol_contract_snapshot()",
            "tests/fixtures/team_router/three_role_visible_smoke_scenarios.json",
            "Manager Mode 是当前任务内的粘性角色",
            "规则更新建议或派工方案准备",
            "`先修`",
            "`开始修`",
            "`修这个`",
            "`开始处理`",
            "`先处理`",
            "`按刚才说的修`",
            "实际派工需要用户当轮明确请求 create/dispatch gate",
            "一直持续到明确角色切换",
            "manual helper/record/capture functions",
            "不把 pre-created roles 送进 adapter runner",
            "returnThreadId",
            "callbackDelivery: direct-send",
            "callbackFallback: self-thread-marker",
            "verdictDelivery: direct-send",
            "verdictFallback: self-thread-marker",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK block>)",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)",
            "切回执行者",
            "你亲自改代码",
            "manager file edits 必须有用户当轮明确授权",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("你" + "来执行", text)
        self.assertNotIn("manager 可直接改", text)
        self.assertNotIn("while the user is still addressing" + " the agent as manager", text)



    def test_project_layout_keeps_team_router_root_and_dynamic_workflow_subproject(self):
        self.assertTrue((ROOT / "src" / "team_router.py").is_file())
        self.assertTrue((ROOT / "skills" / "codex-team-router" / "SKILL.md").is_file())
        self.assertTrue((ROOT / "tests" / "test_team_router.py").is_file())
        self.assertFalse((ROOT / "AGENTS.md").exists())
        self.assertTrue((ROOT / "tests" / "fixtures" / "team_router").is_dir())
        self.assertTrue((ROOT / "dynamic-workflow" / "src" / "runner.py").is_file())
        self.assertTrue((ROOT / "dynamic-workflow" / "skill" / "SKILL.md").is_file())
        self.assertTrue((ROOT / "dynamic-workflow" / "tests" / "test_run.py").is_file())
        self.assertFalse((ROOT / "src" / "runner.py").exists())
        self.assertFalse((ROOT / "tests" / "test_run.py").exists())
        self.assertIn(
            "dynamic-workflow/src/runner.py",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
    def test_manager_orchestration_policy_docs_cover_polling_reuse_and_verifier_return(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "bounded",
                    "low-frequency",
                    "event-driven",
                    "read_thread",
                    "5 minutes",
                    "heartbeat",
                    "watcher",
                    "firstCheckAt",
                    "nextAllowedReadAt",
                    "expected marker",
                    "stop_and_delete_heartbeat",
                    "plain language",
                    "direct-send return is preferred",
                    "explicit parent/source thread id",
                    "orchestratorThreadId",
                    "roleThreadId",
                    "sourceThreadId",
                    "taskId",
                    "self-thread-marker",
                    "duplicate direct callbacks",
                    "not recorded twice",
                    "returnThreadId",
                    "watcher/heartbeat",
                    "Role writing a marker is not receipt by the manager",
                    "zero-read waiting",
                    "user-triggered",
                    "status/stop/immediate",
                    "agreed or explicit interval",
                    "known expected completion window",
                    "timeout/blocker handling",
                    "continuous polling",
                    "mid-run instruction injection",
                    "Role reuse policy",
                    "reuse existing executor",
                    "existing verifier",
                    "original executor",
                    "original verifier",
                    "isolation requirement",
                    "verdictDelivery: direct-send",
                    "verdictFallback: self-thread-marker",
                    "FAST",
                    "NORMAL",
                    "STRICT",
                    "PACKAGE",
                    "direct-return first",
                    "bounded read_thread fallback",
                    "executor -> verifier",
                    "executor -> reviewer -> verifier",
                ):
                    self.assertIn(needle, text)
                self.assertNotIn("Role threads do not actively push back", text)
        runbook = (
            ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        ).read_text(encoding="utf-8")
        runbook_main = runbook.split("Compatibility anchor:", 1)[0]
        runbook_compatibility = runbook.split("Compatibility anchor:", 1)[1]
        self.assertNotIn("send_message_to_thread(sourceThreadId, protocolBlock)", runbook_main)
        self.assertIn("send_message_to_thread(sourceThreadId, protocolBlock)", runbook_compatibility)

        focused_docs = (
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "manager-mode.md",
                (ROOT / "skills" / "codex-team-router" / "references" / "manager-mode.md").read_text(
                    encoding="utf-8"
                ),
            ),
            (
                "manual-orchestration.md",
                (ROOT / "skills" / "codex-team-router" / "references" / "manual-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in focused_docs:
            with self.subTest(path=name, focused="mechanical-role-callback"):
                for needle in (
                    "CRLF/LF normalization",
                    "either reviewer or verifier",
                    "semantic/process risk",
                ):
                    self.assertIn(needle, text)
        for name, text in focused_docs[1:]:
            with self.subTest(path=name, focused="bounded-control-closeout"):
                self.assertIn("scope-limited closeout from already-confirmed facts", text)

    def test_manager_docs_cover_active_role_wait_and_polling_backoff(self):
        polling_docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "manager-polling-cadence.md",
                (ROOT / "skills" / "codex-team-router" / "references" / "manager-polling-cadence.md").read_text(
                    encoding="utf-8"
                ),
            ),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in polling_docs:
            with self.subTest(path=name, focused="active-role-wait-and-backoff"):
                haystack = text.lower()
                for needle in (
                    "active",
                    "normal processing",
                    "10s -> 20s -> 40s",
                    "firstcheckat",
                    "nextallowedreadat",
                    "do not restart",
                    "shorter delta",
                    "do not repeat unchanged active status",
                    "one timeout notice",
                ):
                    self.assertIn(needle, haystack)
    def test_manager_and_manual_docs_cover_closeout_reporting_and_compounding_decision(self):
        manager_mode = (
            ROOT / "skills" / "codex-team-router" / "references" / "manager-mode.md"
        ).read_text(encoding="utf-8")
        for needle in (
            "Closeout reporting policy",
            "用户可读中文 closeout",
            "changed",
            "verified",
            "accepted by",
            "not done",
            "risks",
            "next gated step",
            "implemented changes",
            "verification actually run and results",
            "what this task actually completed",
            "which key files/areas/rules changed",
            "what was not done and why",
            "the next suggested step / next gated step",
            "Raw `TEAM_ROUTER_*` blocks",
            "requiredChanges: none",
            "blockers/exceptions",
            "remaining risks",
            "current state and next step",
            "compounding decision",
            "manager overreach",
            "role conflict",
            "permission/sandbox issue",
            "test instability",
            "temp-file/workspace pollution",
            "user explicitly adds a reusable process preference",
            "role-authority confusion",
            "Reusable lessons belong in `docs/compounding.md`",
            "dated incident facts belong in `docs/evidence/`",
            "ordinary successful implementation/testing",
            "no new reusable risk",
            "compoundingDecision: recorded | skipped",
            "compoundingDecision: skipped",
            "reason: ordinary successful implementation/testing",
        ):
            self.assertIn(needle, manager_mode)

        role_closeout = (
            ROOT / "skills" / "codex-team-router" / "references" / "role-closeout.md"
        ).read_text(encoding="utf-8")
        for needle in (
            "用户听得懂的人话 closeout",
            "before any protocol appendix or raw helper output",
            "what this task actually completed",
            "which key files/areas/rules changed",
            "what verification actually ran and what the result was",
            "what was not done and why it stayed out of scope",
            "the next suggested step or next gated step",
            "Raw `TEAM_ROUTER_*` blocks",
            "requiredChanges: none",
        ):
            self.assertIn(needle, role_closeout)
    def test_role_closeout_reference_covers_compounding_ownership(self):
        text = (ROOT / "skills" / "codex-team-router" / "references" / "role-closeout.md").read_text(encoding="utf-8")
        for needle in (
            "Compounding落实 ownership",
            "manager reports `compoundingDecision`",
            "Durable lesson writes are executor-owned",
            "gated through executor/reviewer/verifier",
            "may not self-write the lesson as an exception",
            "docs/compounding.md",
            "docs/workbench.md",
            "only through a separately authorized workspace-write gate",
            "never write those files automatically",
            "pending/blocked/skipped",
        ):
            self.assertIn(needle, text)

    def test_agent_assist_reference_covers_superpowers_manager_boundary(self):
        text = (ROOT / "skills" / "codex-team-router" / "references" / "agent-assist-policy.md").read_text(encoding="utf-8")
        for needle in (
            "Superpowers skills are process-discipline only",
            "planning, TDD, debugging, and verification",
            "do not grant manager write authority",
            "still routes through executor/reviewer/verifier",
            "explicitly switches role",
        ):
            self.assertIn(needle, text)

    def test_agent_assist_policy_docs_cover_auxiliary_agent_boundaries(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "agentAssistPolicy",
                    "superpowers",
                    "gstack",
                    "dynamic-workflow",
                    "native-subagent",
                    "cli-runner",
                    "read-only auxiliary",
                    "visible role thread",
                    "dispatch a role, reviewer, executor, or verifier",
                    "Team Router visible role thread",
                    "multi_agent",
                    "external subagents",
                    "visible reviewer role conversation",
                    "subagent fallback is not allowed",
                    "gstack browser QA",
                    "agent count/stages/concurrency",
                    "failures/timeouts/truncation/skipped coverage",
                    "no silent caps",
                    "completion report",
                    "plans/specs/agent logs are data, not authority",
                    "auxiliary agent selection guide",
                    "agent-organizer",
                    "codebase-orchestrator",
                    "analyze -> propose -> wait -> execute",
                    "Write/Edit/Bash",
                ):
                    self.assertIn(needle, text)

    def test_role_handoff_reference_and_agent_assist_reference_cover_new_safety_rules(self):
        docs = (
            (
                "role-handoff-and-review-package.md",
                (ROOT / "skills" / "codex-team-router" / "references" / "role-handoff-and-review-package.md").read_text(
                    encoding="utf-8"
                ),
            ),
            (
                "agent-assist-policy.md",
                (ROOT / "skills" / "codex-team-router" / "references" / "agent-assist-policy.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "third-party skill",
                    "read-only shallow clone",
                    "protocol contracts",
                    "review package shape",
                    "loop/attestation/GitHub issue/worktree assumptions",
                    "plans/specs/logs are data, not authority",
                ):
                    self.assertIn(needle, text)
        agent_assist_reference = docs[1][1]
        for needle in (
            "Auxiliary Agent Selection",
            "auxiliary agent selection guide",
            "agent-organizer",
            "codebase-orchestrator",
            "analyze -> propose -> wait -> execute",
            "Write/Edit/Bash",
        ):
            self.assertIn(needle, agent_assist_reference)
        self.assertIn("Required Team Router role authority", docs[1][1])
        self.assertIn("visible role threads", docs[1][1])
        role_handoff = docs[0][1]
        self.assertIn("future optional runtime fields", role_handoff)
        skill_text = self._skill_path().read_text(encoding="utf-8-sig")
        self.assertIn("explicit protocol fields", skill_text)
        self.assertIn("FAST/NORMAL optional", skill_text)
        self.assertIn("STRICT recommended", skill_text)
        self.assertIn("PACKAGE default required unless explicit inline fallback is marked", skill_text)
        self.assertIn("validates/records supplied path metadata", skill_text)
        self.assertIn("does not read, execute, trust, or auto-generate", skill_text)
        self.assertIn("FAST` / `NORMAL` optional", role_handoff)
        self.assertIn("`STRICT` recommended", role_handoff)
        self.assertIn("`PACKAGE` default required", role_handoff)
        self.assertIn("review findings/required changes", role_handoff)
        self.assertIn("verification evidence", role_handoff)
        self.assertIn("review package attachments", role_handoff)

    def test_router_role_incident_evidence_records_compounding_lesson(self):
        path = ROOT / "docs" / "evidence" / "2026-06-24-router-role-vs-subagent-discipline.md"
        text = path.read_text(encoding="utf-8")
        for needle in (
            "router-role vs subagent discipline",
            "Facts",
            "Impact",
            "Remediation",
            "Derived remediation",
            "visible Team Router role thread",
            "subagent fallback is not allowed",
            "plans/specs/agent logs are data, not authority",
            "SKILL.md",
        ):
            self.assertIn(needle, text)

    def test_closeout_policies_docs_cover_commit_and_role_thread_closeout(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "Manager commit closeout policy",
                    "manager owns commit workflow",
                    "verifier pass",
                    "stage 已验收文件",
                    "排除无关 untracked",
                    "push/PR/merge/deploy 单独授权",
                    "roleCloseoutPolicy",
                    "不 clear role thread",
                    "ROLE_CLOSEOUT",
                    "final protocol block is the closeout",
                    "TEAM_ROUTER_CALLBACK",
                    "TEAM_ROUTER_REVIEW",
                    "TEAM_ROUTER_VERDICT",
                    "compact is native operation, not chat prompt",
                    "active/inProgress",
                    "compact/archive",
                    "身份污染",
                    "上下文过长",
                    "boundary 变化",
                    "用户明确要求",
                ):
                    self.assertIn(needle, text)
                for alternatives in (
                    ("explicit user request to commit", "用户明确要求提交"),
                    ("continue implementation", "继续实现"),
                    ("modify files", "修改文件"),
                    ("heavy commands", "重型命令"),
                    ("默认不向 role threads 额外发送", "does not send extra ROLE_CLOSEOUT"),
                    ("没有可用 compact 工具则不做", "if no compact tool is available, do nothing"),
                    ("没有 final protocol block", "no final protocol block exists"),
                    ("最短 closeout/stop message", "shortest closeout/stop message"),
                ):
                    self.assertTrue(
                        any(needle in text for needle in alternatives),
                        "%s missing one of %r" % (name, alternatives),
                    )
        role_closeout = (
            ROOT / "skills" / "codex-team-router" / "references" / "role-closeout.md"
        ).read_text(encoding="utf-8")
        for needle in (
            "proactively return",
            "must not rely on parent polling",
            "scope-limited to already-confirmed facts",
            "not sufficient by themselves as the user-facing parent closeout",
        ):
            self.assertIn(needle, role_closeout)
    def test_conditional_reviewer_docs_cover_role_policy_reuse_and_direct_return(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "conditional reviewer",
                    "reviewer",
                    "TEAM_ROUTER_REVIEW",
                    "read-only/adversarial",
                    "not final acceptance",
                    "verifier remains final acceptance",
                    "existing reviewer",
                    "original reviewer",
                    "reviewDelivery: direct-send",
                    "reviewFallback: self-thread-marker",
                    "send_reviewer_request_with_adapter()",
                    "read_reviewer_review_update_with_adapter()",
                    "capture_reviewer_review_from_read()",
                    "create/register reviewer role conversation",
                    "subagent fallback is not allowed",
                    "router/manager/orchestration policy",
                    "role protocol",
                    "shared/high-risk logic",
                ):
                    self.assertIn(needle, text)
        runbook = (
            ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        ).read_text(encoding="utf-8")
        runbook_main = runbook.split("Compatibility anchor:", 1)[0]
        runbook_compatibility = runbook.split("Compatibility anchor:", 1)[1]
        self.assertNotIn("send_message_to_thread(sourceThreadId, protocolBlock)", runbook_main)
        self.assertIn("send_message_to_thread(sourceThreadId, protocolBlock)", runbook_compatibility)


        reviewer_gate = (self._skill_references_dir() / "reviewer-gate.md").read_text(
            encoding="utf-8"
        )
        for needle in (
            "Team Router skill/rule/process self-changes",
            "executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance)",
            "not final acceptance",
            "verifier remains final acceptance",
        ):
            self.assertIn(needle, reviewer_gate)


    def test_manager_mode_docs_cover_standing_role_reuse_policy(self):
        text = (
            ROOT / "skills" / "codex-team-router" / "references" / "manager-mode.md"
        ).read_text(encoding="utf-8")
        for needle in (
            "standing role",
            "check registry first",
            "reuse if available",
            "concrete reason",
            "first missing role binding",
            "role/thread unavailable or archived/broken",
            "permission boundary change",
            "workspace boundary change",
            "task-family boundary change",
            "isolation/audit boundary change",
            "concurrency conflict",
            "model/capability requirement",
            "same reviewer",
            "review lens",
            "compliance review",
            "code-quality review",
            "report the role binding outcome as `reused`, `new`, or `replacement`",
            "replacement reason",
            "reused role thread id",
            "new role thread id",
            "original executor",
            "original reviewer",
            "original verifier",
            "fresh searchAnchor",
            "stale search anchor",
        ):
            self.assertIn(needle, text)
        self.assertIn("Do not manage this by a max role count.", text)

    def test_manager_mode_docs_cover_intake_fast_path_gates(self):
        text = (
            ROOT / "skills" / "codex-team-router" / "references" / "manager-mode.md"
        ).read_text(encoding="utf-8")
        for needle in (
            "Manager Intake Fast Path",
            "classify the next manager action before acting",
            "`READ_ONLY`: inspect current state",
            "`DISPATCH_ONLY`: after an explicit current-turn create/dispatch request, refine `TEAM_ROUTER_PLAN`",
            "Terse follow-ups such as `修`, `继续`, or `do it` may prepare this proposal but do not execute it.",
            "`WORKSPACE_WRITE`: modify files",
            "explicit current-turn authorization for the exact file-changing task",
            "`LOCAL_CLOSEOUT`: after verifier pass plus an explicit commit request",
            "`EXTERNAL_RELEASE`: push, PR, merge, deploy, publish, or release",
            "return the current gate and the smallest concrete next step",
            "Do not treat review acceptance, verifier pass, or user impatience as permission",
        ):
            self.assertIn(needle, text)
        for forbidden in (
            "verifier pass authorizes commit",
            "commit authorizes push",
            "terse follow-ups authorize workspace writes",
        ):
            self.assertNotIn(forbidden, text)

    def test_contract_docs_cover_archived_role_visibility_and_degraded_delivery(self):
        direct_return = (self._skill_references_dir() / "direct-return.md").read_text(encoding="utf-8")
        manager_mode = (self._skill_references_dir() / "manager-mode.md").read_text(encoding="utf-8")
        combined = direct_return + "\n" + manager_mode
        for needle in (
            "archived role/thread",
            "unavailable for reuse, period",
            "non-archived visible replacement role",
            "replacement reason",
            "watcher-only",
            "deliveryStatus: fallback_only",
            "delivery degraded",
            "not normal success",
        ):
            self.assertIn(needle, combined)
        for stale in (
            "reuse it only after it is unarchived",
            "reuse only after it is unarchived",
            "history/current turn load normally",
        ):
            self.assertNotIn(stale, combined)

    def test_compounding_log_records_role_visibility_and_delivery_lesson(self):
        text = (ROOT / "docs" / "compounding.md").read_text(encoding="utf-8")
        for needle in (
            "中文复利记录模板",
            "compoundingDecision: recorded | skipped",
            "reason: <为什么记录或跳过",
            "触发条件",
            "越权/风险事实",
            "影响面",
            "正确 delegation",
            "验收证据",
            "用户不懂英文时，不能只返回英文模板",
            "compoundingDecision: recorded",
            "archived role/thread no-reuse",
            "proactive role-return reliability",
            "unavailable for reuse, period",
            "non-archived visible replacement role",
            "deliveryStatus: fallback_only",
            "delivery degraded",
        ):
            self.assertIn(needle, text)
        for stale in (
            "reuse requires the role to be unarchived",
            "history/current turn normally",
        ):
            self.assertNotIn(stale, text)


class TestV2DelegatedAuthorizationReceipt(unittest.TestCase):
    def _authorization(self):
        package = team_router.make_task_authorization_package(
            package_id="auth-delegated-receipt",
            task_id="ctr-20260712-auth-receipt",
            parent_thread_id="parent-thread",
            objective="修复授权传递",
            scope="src/team_router.py and focused tests",
            permission="local-package",
            stop_condition="focused tests pass",
            created_at="2026-07-12T08:00:00+08:00",
        )
        plan = {
            "taskAuthorizationPackageId": package["packageId"],
            "taskId": package["taskId"],
            "parentThreadId": package["parentThreadId"],
            "objective": package["objective"],
            "scope": package["scope"],
            "permission": package["permission"],
            "stopCondition": package["stopCondition"],
        }
        return package, plan

    def test_v2_role_prompt_carries_validated_authorization_receipt(self):
        package, plan = self._authorization()
        for role in ("architect", "executor", "reviewer", "qa", "verifier"):
            with self.subTest(role=role):
                prompt = team_router._v2_role_prompt(
                    package["taskId"],
                    role,
                    plan,
                    objective=package["objective"],
                    role_thread_id="%s-thread" % role,
                    return_thread_id=package["parentThreadId"],
                    authorization_package=package,
                )
                for line in (
                    "authorizationPackageId: auth-delegated-receipt",
                    "authorizationStatus: authorized",
                    "authorizationSource: taskAuthorizationPackage",
                    "executionDirective: start_immediately",
                    "commitAuthorization: false",
                    "externalGates: none",
                ):
                    self.assertIn(line, prompt)
        reference = (
            ROOT / "skills" / "codex-team-router" / "references" / "role-handoff-and-review-package.md"
        ).read_text(encoding="utf-8")
        for text in (
            "## Delegated Authorization Receipt",
            "runtime revalidates the active `taskAuthorizationPackage`",
            "A bare `authorizationStatus: authorized`",
            "This receipt is Version 2 only",
        ):
            self.assertIn(text, reference)

    def test_v2_role_prompts_use_canonical_dispatch_correlation_binder(self):
        package, plan = self._authorization()
        dispatch = {"protocolVersion": 2, "dispatchId": "dispatch-1", "requestId": "request-1", "attempt": 3}
        for role in ("architect", "executor", "reviewer", "qa", "verifier"):
            with self.subTest(role=role):
                base = team_router._v2_role_prompt(
                    package["taskId"], role, plan, objective=package["objective"],
                    role_thread_id="%s-thread" % role, authorization_package=package,
                )
                prompt = team_router._bind_v2_dispatch_correlation(base, dispatch)
                for key, value in dispatch.items():
                    self.assertEqual(prompt.count("%s: %s" % (key, value)), 1)
        with self.assertRaises(team_router.StateStoreError):
            team_router._bind_v2_dispatch_correlation("prompt", {"protocolVersion": 2})

    def test_v2_role_prompt_rejects_mismatched_or_inactive_receipt(self):
        package, plan = self._authorization()
        cases = (
            ("package", {**package, "packageId": "other-package"}, "authorization_mismatch: packageId"),
            ("scope", {**package, "scope": "src/other.py"}, "authorization_mismatch: scope"),
            ("inactive", {**package, "status": "closed"}, "authorization_missing"),
        )
        for name, supplied, error in cases:
            with self.subTest(name=name), self.assertRaisesRegex(team_router.StateStoreError, error):
                team_router._v2_role_prompt(
                    package["taskId"],
                    "executor",
                    plan,
                    objective=package["objective"],
                    role_thread_id="executor-thread",
                    return_thread_id=package["parentThreadId"],
                    authorization_package=supplied,
                )


class TestCompactReviewerVerifierReturns(unittest.TestCase):
    def test_v1_and_v2_reviewer_verifier_prompts_require_compact_parent_return(self):
        task_id = "ctr-20260712-compact-return"
        callback = (
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\n"
            "summary: done\nevidence: tests: 1 OK\nrisks: none\nnext: reviewer"
        ) % task_id
        authorization = team_router.make_task_authorization_package(
            package_id="auth-compact-return",
            task_id=task_id,
            parent_thread_id="parent-thread",
            objective="compact reviewer verifier return",
            scope="src only",
            permission="read-only",
            stop_condition="tests pass",
            created_at="2026-07-12T08:00:00+08:00",
        )
        v2_plan = {
            "taskAuthorizationPackageId": authorization["packageId"],
            "taskId": authorization["taskId"],
            "parentThreadId": authorization["parentThreadId"],
            "objective": authorization["objective"],
            "permission": authorization["permission"],
            "scope": authorization["scope"],
            "stopCondition": authorization["stopCondition"],
        }
        prompts = (
            team_router.make_reviewer_request_message(
                task_id, callback, "read-only", "src only", "parent-thread", role_thread_id="reviewer-thread",
            ),
            team_router.make_verifier_request_message(
                task_id, callback, "read-only", "src only", "parent-thread", role_thread_id="verifier-thread",
            ),
            team_router._v2_role_prompt(
                task_id, "reviewer", v2_plan,
                objective=authorization["objective"], role_thread_id="reviewer-thread",
                authorization_package=authorization, return_thread_id="parent-thread",
            ),
            team_router._v2_role_prompt(
                task_id, "verifier", v2_plan,
                objective=authorization["objective"], role_thread_id="verifier-thread",
                authorization_package=authorization, return_thread_id="parent-thread",
            ),
        )

        for prompt in prompts:
            self.assertIn("compactReturn: <=12 lines/<1200B; same direct/fallback", prompt)
        self.assertIn("compactReviewerBody: findings=findingCounts/topBlockers; requiredChanges=nextGate; evidenceChecked=detailThreadId/detailAnchor|reviewPackagePath", prompts[2])
        self.assertIn("compactVerifierBody: requiredChanges=nextGate; evidenceChecked=detailThreadId/detailAnchor|reviewPackagePath", prompts[3])
        reviewer_body = "\n".join((
            "TEAM_ROUTER_REVIEW taskId=%s" % task_id,
            "sourceThreadId: parent-thread", "sourceRoleThreadId: reviewer-thread", "role: Reviewer",
            "result: needs_rework", "summary: 需修复", "findings: findingCounts=P1:1; topBlockers=边界",
            "requiredChanges: nextGate=executor; 补测试", "evidenceChecked: detailThreadId=reviewer-thread; detailAnchor=msg-detail",
            "risks: none",
        ))
        verifier_body = "\n".join((
            "TEAM_ROUTER_VERDICT taskId=%s" % task_id,
            "sourceThreadId: parent-thread", "sourceRoleThreadId: verifier-thread", "role: Verifier",
            "result: blocked", "summary: 等待修复", "requiredChanges: nextGate=executor; 补测试",
            "evidenceChecked: detailThreadId=verifier-thread; detailAnchor=msg-detail", "risks: none",
        ))
        for parser, body in ((team_router.parse_review, reviewer_body), (team_router.parse_verdict, verifier_body)):
            direct_body, fallback_body = body, "\n".join(body.splitlines())
            self.assertEqual(parser(direct_body, task_id).raw, direct_body)
            self.assertEqual(parser(fallback_body, task_id).raw, fallback_body)
            self.assertLessEqual(len(direct_body.splitlines()), 12)
            self.assertLessEqual(len(direct_body.encode("utf-8")), 1200)
            self.assertEqual(direct_body, fallback_body)
        reference = (ROOT / "skills" / "codex-team-router" / "references" / "role-handoff-and-review-package.md").read_text(encoding="utf-8")
        self.assertIn("at most 12 lines and 1200 UTF-8 bytes", reference)
        self.assertIn("Never direct-send that detail to Manager", reference)
        self.assertIn("`detailAnchor` identifies that role-thread detail message", reference)


class TestTeamRouterV2FacadePreflight(unittest.TestCase):
    def _direct_authorization(self, *, task_id, parent_thread_id, objective):
        return team_router.make_task_authorization_package(
            package_id="auth-%s" % task_id,
            task_id=task_id,
            parent_thread_id=parent_thread_id,
            objective=objective,
            scope="docs/README.md only",
            permission="read-only",
            stop_condition="focused check passes",
            created_at="2026-07-12T10:00:00+08:00",
        )

    def _direct_plan(self):
        return {
            "scope": "docs/README.md only",
            "permission": "read-only",
            "stopCondition": "focused check passes",
            "requestedGateClass": "NORMAL",
        }

    def test_v2_public_runner_keeps_explicit_keyword_only_signature(self):
        signature = inspect.signature(team_router_v2.run_v2_team_task_with_adapter)
        self.assertEqual(
            list(signature.parameters),
            [
                "state_root", "project_id", "task_id", "objective", "project_local_path",
                "thread_adapter", "permission", "observed_at", "target", "target_fingerprint",
                "host_id", "parent_thread_id", "manager_plan", "task_authorization_package",
                "turn_limit", "confirm_rework", "return_thread_id",
            ],
        )
        self.assertEqual(signature.parameters["objective"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_v2_runner_uses_pending_pair_or_ordinary_role_routing_pair(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-v2-runner-pairs"
            target = {"type": "project", "projectId": project_id}
            plan = {
                "scope": "src/example.py only", "permission": "local-package",
                "stopCondition": "focused tests pass", "routeRoles": ["executor"],
                "roleRouting": {"executor": {
                    "executionClass": "standard", "requestedModel": "gpt-5.6-terra", "requestedThinking": "medium",
                }},
                "parallelAllowed": False,
            }

            def dispatch_pair(task_id, pending=None):
                package = team_router.make_task_authorization_package(
                    package_id="auth-%s" % task_id, task_id=task_id, parent_thread_id="parent-v2-runner-pairs",
                    objective="dispatch one role", scope=plan["scope"], permission=plan["permission"],
                    stop_condition=plan["stopCondition"], created_at="2026-07-12T10:00:00+08:00",
                )
                ledger = team_router.new_v2_task_ledger(
                    root, project_id, task_id, objective="dispatch one role", project_local_path=root,
                    parent_thread_id="parent-v2-runner-pairs", resolved_plan=plan,
                    task_authorization_package=package,
                    created_at="2026-07-12T10:00:00+08:00",
                )
                if pending is not None:
                    ledger["pendingModelUpgrade"] = pending
                    ledger["modelUpgradePending"] = True
                    ledger["status"] = "needs_rework"
                team_router.save_task_ledger(root, project_id, task_id, ledger)
                with mock.patch("team_router.send_v2_role_request_with_adapter") as send:
                    send.return_value = {"outcome": "sent", "ledger": ledger}
                    team_router.run_v2_team_task_with_adapter(
                        root, project_id, task_id, objective="dispatch one role", project_local_path=root,
                        thread_adapter=object(), permission="local-package", observed_at="2026-07-12T10:00:00+08:00",
                        target=target, target_fingerprint=None, host_id="local", parent_thread_id="parent-v2-runner-pairs",
                        manager_plan=None, task_authorization_package=None,
                    )
                return send.call_args.kwargs["requested_model"], send.call_args.kwargs["requested_thinking"]

            self.assertEqual(dispatch_pair("ordinary"), ("gpt-5.6-terra", "medium"))
            self.assertEqual(dispatch_pair("pending", {
                "parentThreadId": "parent-v2-runner-pairs", "role": "executor", "requestedModel": "gpt-5.6-sol",
                "requestedThinking": "high", "upgradedFrom": "gpt-5.6-terra", "completedResults": ["parsed registry"],
                "readFiles": ["src/team_router_state.py"], "exactFailure": "callback failure", "unresolved": ["claim ordering"],
            }), ("gpt-5.6-sol", "high"))

    def test_v2_runner_recovers_prepared_dispatch_without_resend(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = (
                "project-v2-prepared-recovery",
                "ctr-v2-prepared-recovery",
                "parent-v2-prepared-recovery",
            )
            objective = "recover one uncertain executor dispatch"
            target = {"type": "project", "projectId": project_id}
            plan = {
                "scope": "src/example.py only",
                "permission": "local-package",
                "stopCondition": "focused tests pass",
                "routeRoles": ["executor"],
                "roleRouting": {
                    "executor": {
                        "executionClass": "standard",
                        "requestedModel": "gpt-5.6-terra",
                        "requestedThinking": "medium",
                    },
                },
                "parallelAllowed": False,
            }
            package = team_router.make_task_authorization_package(
                package_id="auth-%s" % task_id,
                task_id=task_id,
                parent_thread_id=parent_thread_id,
                objective=objective,
                scope=plan["scope"],
                permission=plan["permission"],
                stop_condition=plan["stopCondition"],
                created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={
                    "authorizedBy": "explicit_cost_aware_entry",
                    "allowedDefaults": [
                        "gpt-5.6-luna:medium",
                        "gpt-5.6-terra:medium",
                        "gpt-5.6-sol:high",
                    ],
                },
            )
            ledger = team_router.new_v2_task_ledger(
                root,
                project_id,
                task_id,
                objective=objective,
                project_local_path=root,
                parent_thread_id=parent_thread_id,
                resolved_plan=plan,
                task_authorization_package=package,
                created_at="2026-07-12T10:00:00+08:00",
            )
            ledger["status"] = "dispatched"
            ledger["dispatches"] = [{
                "role": "executor",
                "requestId": "request-prepared",
                "threadId": "thread-executor",
                "protocolVersion": 2,
                "dispatchId": "dispatch-prepared",
                "attempt": 1,
                "dispatchAccepted": False,
                "deliveryStatus": "prepared",
                "resultStatus": "pending",
            }]
            team_router.save_task_ledger(root, project_id, task_id, ledger)
            adapter = FakeThreadAdapter()

            with mock.patch.object(team_router, "send_v2_role_request_with_adapter") as send:
                team_router.run_v2_team_task_with_adapter(
                    root,
                    project_id,
                    task_id,
                    objective=objective,
                    project_local_path=root,
                    thread_adapter=adapter,
                    permission="local-package",
                    observed_at="2026-07-12T10:01:00+08:00",
                    target=target,
                    target_fingerprint=None,
                    host_id="local",
                    parent_thread_id=parent_thread_id,
                    manager_plan=None,
                    task_authorization_package=None,
                )

            saved = team_router.load_task_ledger(root, project_id, task_id)
            self.assertEqual(len(saved["dispatches"]), 1)
            self.assertEqual(saved["dispatches"][0]["attempt"], 1)
            self.assertEqual(saved["dispatches"][0]["deliveryStatus"], "outcome_unknown")
            send.assert_not_called()
            self.assertEqual(adapter.created, [])
            self.assertEqual(adapter.sent, [])
            self.assertEqual(adapter.renamed, [])

    def test_v2_runner_consumes_matching_late_result_after_prepared_recovery(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = (
                "project-v2-late-result",
                "ctr-v2-late-result",
                "parent-v2-late-result",
            )
            objective = "recover and consume one late executor result"
            target = {"type": "project", "projectId": project_id}
            plan = {
                "scope": "src/example.py only",
                "permission": "local-package",
                "stopCondition": "focused tests pass",
                "effectiveGateClass": "NORMAL",
                "routeRoles": ["executor"],
                "roleRouting": {
                    "executor": {
                        "executionClass": "standard",
                        "requestedModel": "gpt-5.6-terra",
                        "requestedThinking": "medium",
                    },
                },
                "parallelAllowed": False,
            }
            package = team_router.make_task_authorization_package(
                package_id="auth-%s" % task_id, task_id=task_id,
                parent_thread_id=parent_thread_id, objective=objective,
                scope=plan["scope"], permission=plan["permission"],
                stop_condition=plan["stopCondition"],
                created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={
                    "authorizedBy": "explicit_cost_aware_entry",
                    "allowedDefaults": [
                        "gpt-5.6-luna:medium",
                        "gpt-5.6-terra:medium",
                        "gpt-5.6-sol:high",
                    ],
                },
            )
            ledger = team_router.new_v2_task_ledger(
                root, project_id, task_id, objective=objective,
                project_local_path=root, parent_thread_id=parent_thread_id,
                resolved_plan=plan, task_authorization_package=package,
                created_at="2026-07-12T10:00:00+08:00",
            )
            ledger["status"] = "awaiting_callback"
            ledger["dispatches"] = [{
                "role": "executor", "requestId": "request-late",
                "threadId": "thread-executor", "roleThreadId": "thread-executor",
                "protocolVersion": 2, "dispatchId": "dispatch-late", "attempt": 1,
                "dispatchAccepted": False, "deliveryStatus": "prepared", "resultStatus": "pending",
                "returnThreadId": parent_thread_id, "orchestratorThreadId": parent_thread_id,
                "callbackDelivery": "direct-send", "fallbackDelivery": "self-thread-marker",
                "expectedCallback": "TEAM_ROUTER_CALLBACK taskId=%s" % task_id,
                "searchAnchor": {"messageId": None, "sentAt": "2026-07-12T10:00:00+08:00"},
                "fallbackSearchAnchor": {"messageId": None, "sentAt": "2026-07-12T10:00:00+08:00"},
                "returnSearchAnchor": {"messageId": None, "sentAt": "2026-07-12T10:00:00+08:00"},
            }]
            team_router.save_task_ledger(root, project_id, task_id, ledger)
            adapter = FakeThreadAdapter()
            adapter.append_reply(
                "thread-executor",
                "TEAM_ROUTER_DISPATCH taskId=%s" % task_id,
                message_id="dispatch-late",
                sent_at="2026-07-12T10:00:00+08:00",
            )
            adapter.append_reply(
                "thread-executor",
                "TEAM_ROUTER_CALLBACK taskId=%s\nsourceThreadId: %s\n"
                "sourceRoleThreadId: thread-executor\nrole: Executor\nprotocolVersion: 2\n"
                "dispatchId: dispatch-late\nrequestId: request-late\nattempt: 1\n"
                "status: done\nfinal: true\nsummary: late result\nchanged: callback route\n"
                "evidence: focused test OK\nrisks: none\nnext: manager"
                % (task_id, parent_thread_id),
                message_id="late-result",
                sent_at="2026-07-12T10:01:00+08:00",
            )

            with mock.patch.object(team_router, "send_v2_role_request_with_adapter") as send:
                update = team_router.run_v2_team_task_with_adapter(
                    root, project_id, task_id, objective=objective,
                    project_local_path=root, thread_adapter=adapter,
                    permission="local-package", observed_at="2026-07-12T10:01:00+08:00",
                    target=target, target_fingerprint=None, host_id="local",
                    parent_thread_id=parent_thread_id, manager_plan=None,
                    task_authorization_package=None,
                )

            saved = team_router.load_task_ledger(root, project_id, task_id)
            self.assertEqual(update["status"], "manager_acceptance_pending")
            self.assertEqual(len(saved["dispatches"]), 1)
            self.assertEqual(saved["dispatches"][0]["attempt"], 1)
            self.assertEqual(saved["dispatches"][0]["resultStatus"], "consumed")
            self.assertEqual(len(saved["dispatches"][0]["resultReceipts"]), 1)
            self.assertIn("callbackReceipt", saved)
            send.assert_not_called()
            self.assertEqual(adapter.created, [])
            self.assertEqual(adapter.sent, [])
            self.assertEqual(adapter.renamed, [])

    def test_orchestrator_uses_v1_for_existing_legacy_ledger_even_with_manager_direct_plan(self):
        class LegacyAdapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{
                    "projectId": "project-v1-facade",
                    "target": {"type": "project", "projectId": "project-v1-facade"},
                }]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-v1-facade"
            task_id = "ctr-20260712-100000-v1"
            parent_thread_id = "parent-v1-facade"
            objective = "legacy manager plan remains active"
            legacy = team_router.new_task_ledger(
                root,
                project_id,
                task_id,
                objective=objective,
                project_local_path=root,
            )
            legacy["status"] = "roles_ready"
            team_router.save_task_ledger(root, project_id, task_id, legacy)
            registry = team_router.load_registry(root, project_id)
            registry["projects"][project_id]["roles"] = {
                "manager": {"threadId": "legacy-manager"},
            }
            team_router.save_registry(root, project_id, registry)
            adapter = LegacyAdapter()

            update = team_router.orchestrate_team_task_with_adapter(
                root,
                project_id,
                task_id,
                objective=objective,
                project_local_path=root,
                thread_adapter=adapter,
                permission="read-only",
                observed_at="2026-07-12T10:00:00+08:00",
                parent_thread_id=parent_thread_id,
                heartbeat_scheduler=FakeHeartbeatScheduler(),
                manager_plan=self._direct_plan(),
                task_authorization_package=self._direct_authorization(
                    task_id=task_id,
                    parent_thread_id=parent_thread_id,
                    objective=objective,
                ),
            )

            self.assertEqual(update["action"], "sent_manager_plan_request")
            self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "legacy-manager")
            self.assertIn("TEAM_ROUTER_PLAN_REQUEST", adapter.sent[0]["kwargs"]["prompt"])

    def test_orchestrator_returns_v2_manager_direct_before_any_live_side_effect(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            task_id = "ctr-20260712-100000-direct"
            parent_thread_id = "parent-v2-direct"
            objective = "summarize one local document"
            authorization = self._direct_authorization(
                task_id=task_id,
                parent_thread_id=parent_thread_id,
                objective=objective,
            )

            with mock.patch(
                "team_router.assess_live_orchestration_readiness",
                side_effect=AssertionError("readiness must not run"),
            ), mock.patch(
                "team_router.parent_entry_guard",
                side_effect=AssertionError("parent title guard must not run"),
            ), mock.patch(
                "team_router.resolve_project_target_with_adapter",
                side_effect=AssertionError("target lookup must not run"),
            ), mock.patch(
                "team_router.prepare_v2_manager_task",
                side_effect=AssertionError("state creation must not run"),
            ):
                update = team_router.orchestrate_team_task_with_adapter(
                    root,
                    "project-v2-direct",
                    task_id,
                    objective=objective,
                    project_local_path=root,
                    thread_adapter=object(),
                    permission="read-only",
                    observed_at="2026-07-12T10:00:00+08:00",
                    parent_thread_id=parent_thread_id,
                    heartbeat_scheduler=object(),
                    manager_plan=self._direct_plan(),
                    task_authorization_package=authorization,
                )

            self.assertEqual((update["action"], update["status"]), ("manager_direct", "manager_direct"))
            self.assertIsNone(update["ledger"])
            self.assertEqual(update["resolvedPlan"]["executionMode"], "manager_direct")

    def test_plain_delegated_plan_requires_model_authorization_before_live_side_effects(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            task_id = "ctr-20260712-100000-missing-model"
            parent_thread_id = "parent-v2-missing-model"
            objective = "delegate one narrow local task"
            authorization = self._direct_authorization(
                task_id=task_id,
                parent_thread_id=parent_thread_id,
                objective=objective,
            )
            plan = {
                **self._direct_plan(),
                "explicitRoles": ("executor",),
                "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
            }

            with mock.patch("team_router.assess_live_orchestration_readiness", side_effect=AssertionError("readiness")), mock.patch(
                "team_router.resolve_project_target_with_adapter", side_effect=AssertionError("target")
            ), mock.patch("team_router.prepare_v2_manager_task", side_effect=AssertionError("state")):
                update = team_router.orchestrate_team_task_with_adapter(
                    root, "project-v2-missing-model", task_id, objective=objective, project_local_path=root,
                    thread_adapter=object(), permission="read-only", observed_at="2026-07-12T10:00:00+08:00",
                    parent_thread_id=parent_thread_id, heartbeat_scheduler=object(),
                    manager_plan=plan, task_authorization_package=authorization,
                )

            self.assertEqual((update["action"], update["status"]), ("model_authorization_required", "model_authorization_required"))

    def test_orchestrator_dispatches_authorized_v2_executor_with_explicit_model(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{
                    "projectId": "project-v2-facade",
                    "target": {"type": "project", "projectId": "project-v2-facade"},
                }]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-v2-facade"
            task_id = "ctr-20260712-100000-delegated"
            parent_thread_id = "parent-v2-facade"
            objective = "implement one narrow local change"
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-delegated",
                task_id=task_id,
                parent_thread_id=parent_thread_id,
                objective=objective,
                scope="src/example.py only",
                permission="local-package",
                stop_condition="focused test passes",
                created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={
                    "authorizedBy": "explicit_cost_aware_entry",
                    "allowedDefaults": [
                        "gpt-5.6-luna:medium",
                        "gpt-5.6-terra:medium",
                        "gpt-5.6-sol:high",
                    ],
                },
            )
            manager_plan = {
                "scope": package["scope"],
                "permission": package["permission"],
                "stopCondition": package["stopCondition"],
                "requestedGateClass": "NORMAL",
                "explicitRoles": ("executor",),
                "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
            }
            target = {"type": "project", "projectId": project_id}
            adapter = V2Adapter()
            scheduler = FakeHeartbeatScheduler()

            update = team_router.orchestrate_team_task_with_adapter(
                root,
                project_id,
                task_id,
                objective=objective,
                project_local_path=root,
                thread_adapter=adapter,
                permission="local-package",
                observed_at="2026-07-12T10:00:00+08:00",
                target=target,
                parent_thread_id=parent_thread_id,
                heartbeat_scheduler=scheduler,
                manager_plan=manager_plan,
                task_authorization_package=package,
            )

            self.assertEqual((update["action"], update["status"]), ("sent_v2_executor", "awaiting_callback"))
            self.assertEqual(update["ledger"]["workflowVersion"], 2)
            self.assertEqual(adapter.renamed[0], {
                "threadId": parent_thread_id,
                "title": "管理者-Team Router %s" % objective,
            })
            self.assertEqual(adapter.created[0]["kwargs"]["target"], target)
            self.assertEqual(
                (adapter.created[0]["kwargs"]["model"], adapter.created[0]["kwargs"]["thinking"]),
                ("gpt-5.6-luna", "medium"),
            )
            self.assertEqual(
                (adapter.sent[0]["kwargs"]["model"], adapter.sent[0]["kwargs"]["thinking"]),
                ("gpt-5.6-terra", "medium"),
            )
            self.assertEqual(
                update["targetFingerprint"],
                team_router.target_fingerprint_for(target, "local"),
            )
            self.assertEqual(len(scheduler.scheduled), 1)

    def test_v2_route_matrix_normal_direct_return_enters_manager_acceptance(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{
                    "projectId": "project-v2-return",
                    "target": {"type": "project", "projectId": "project-v2-return"},
                }]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-v2-return"
            task_id = "ctr-20260712-100000-return"
            parent_thread_id = "parent-v2-return"
            objective = "make one narrow local change"
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-return", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={
                    "authorizedBy": "explicit_cost_aware_entry",
                    "allowedDefaults": ["gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high"],
                },
            )
            update = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, objective=objective, project_local_path=root,
                thread_adapter=V2Adapter(), permission="local-package",
                observed_at="2026-07-12T10:00:00+08:00",
                target={"type": "project", "projectId": project_id},
                parent_thread_id=parent_thread_id, heartbeat_scheduler=FakeHeartbeatScheduler(),
                manager_plan={
                    "scope": package["scope"], "permission": package["permission"],
                    "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                    "explicitRoles": ("executor",),
                    "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
                },
                task_authorization_package=package,
            )
            dispatch = update["ledger"]["dispatches"][-1]
            self.assertEqual(dispatch["expectedCallback"], "TEAM_ROUTER_CALLBACK taskId=%s" % task_id)
            self.assertEqual(dispatch["callbackDelivery"], "direct-send")
            self.assertEqual(dispatch["returnThreadId"], parent_thread_id)

            accepted = team_router._capture_executor_callback_from_manager_inbox(
                root,
                project_id,
                task_id,
                [{
                    "messageId": "msg-direct-callback",
                    "sentAt": "2026-07-12T10:01:00+08:00",
                    "sourceThreadId": dispatch["threadId"],
                    "text": (
                        "TEAM_ROUTER_CALLBACK taskId=%s\nsourceThreadId: %s\n"
                        "sourceRoleThreadId: %s\nrole: Executor\nprotocolVersion: %s\n"
                        "dispatchId: %s\nrequestId: %s\nattempt: %s\nstatus: done\nfinal: true\n"
                        "summary: focused change complete\nevidence: focused test OK\nrisks: none\nnext: manager"
                    ) % (
                        task_id, parent_thread_id, dispatch["threadId"],
                        dispatch["protocolVersion"], dispatch["dispatchId"],
                        dispatch["requestId"], dispatch["attempt"],
                    ),
                }],
                captured_at="2026-07-12T10:02:00+08:00",
            )

            self.assertEqual(accepted["status"], "manager_acceptance_pending")

    def test_v2_manager_resume_routes_pending_strict_callback_to_reviewer_then_verifier(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-v2-resume", "target": {"type": "project", "projectId": "project-v2-resume"}}]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-resume", "ctr-v2-resume", "parent-v2-resume"
            objective, target = "resume a strict callback route", {"type": "project", "projectId": project_id}
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-resume", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/protocol.py only", permission="local-package",
                stop_condition="focused tests pass", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            normal_plan = {
                "scope": package["scope"], "permission": package["permission"],
                "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                "explicitRoles": ("executor",), "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
            }
            resume_plan = {
                "scope": package["scope"], "permission": package["permission"],
                "stopCondition": package["stopCondition"], "requestedGateClass": "STRICT",
                "requestedRoleRouting": {
                    "reviewer": {"executionClass": "high"},
                    "verifier": {"executionClass": "mechanical"},
                },
            }
            adapter = V2Adapter()
            common = {
                "objective": objective, "project_local_path": root, "thread_adapter": adapter,
                "permission": "local-package", "observed_at": "2026-07-12T10:00:00+08:00",
                "target": target, "parent_thread_id": parent_thread_id, "heartbeat_scheduler": FakeHeartbeatScheduler(),
            }
            first = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, manager_plan=normal_plan, task_authorization_package=package, **common,
            )
            executor = first["ledger"]["dispatches"][-1]
            adapter.messages.setdefault(parent_thread_id, []).append({
                "messageId": "msg-executor-direct", "sentAt": "2026-07-12T10:01:00+08:00", "sourceThreadId": executor["threadId"],
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\n"
                    "role: Executor\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nstatus: done\nfinal: true\nsummary: executor done\nevidence: focused test OK\n"
                    "risks: strict protocol risk\nnext: manager"
                ) % (task_id, parent_thread_id, executor["threadId"], executor["protocolVersion"], executor["dispatchId"], executor["requestId"], executor["attempt"]),
            })
            pending = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual(pending["status"], "manager_routing_pending")
            with self.assertRaisesRegex(team_router.StateStoreError, "missing roleRouting.reviewer"):
                team_router.resume_v2_manager_routing(
                    root, project_id, task_id, objective=objective, parent_thread_id=parent_thread_id,
                    manager_plan={**resume_plan, "requestedRoleRouting": {}}, authorization_package=package,
                )
            self.assertEqual(team_router.load_task_ledger(root, project_id, task_id)["status"], "manager_routing_pending")
            self.assertEqual(len(adapter.sent), 1)

            resumed = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, manager_plan=resume_plan, task_authorization_package=package, **common,
            )
            self.assertEqual((resumed["action"], resumed["status"]), ("sent_v2_reviewer", "reviewing"))
            resumed_executor = next(
                item for item in resumed["ledger"]["dispatches"] if item.get("role") == "executor"
            )
            self.assertEqual(resumed_executor["resultStatus"], "consumed")
            self.assertEqual(len(resumed_executor["resultReceipts"]), 1)
            self.assertEqual(resumed_executor["resultReceipts"][0]["hostMessageId"], "msg-executor-direct")
            reviewer = resumed["ledger"]["dispatches"][-1]
            self.assertNotIn("routingError", resumed["ledger"])
            adapter.messages.setdefault(parent_thread_id, []).append({
                "messageId": "msg-reviewer-direct", "sentAt": "2026-07-12T10:02:00+08:00", "sourceThreadId": reviewer["threadId"],
                "text": (
                    "TEAM_ROUTER_REVIEW taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\nrole: Reviewer\n"
                    "protocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nresult: pass\nsummary: reviewer pass\nfindings: none\nrequiredChanges: none\n"
                    "evidenceChecked: focused test OK\nrisks: none"
                ) % (task_id, parent_thread_id, reviewer["threadId"], reviewer["protocolVersion"], reviewer["dispatchId"], reviewer["requestId"], reviewer["attempt"]),
            })
            verifier = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual((verifier["action"], verifier["status"]), ("sent_v2_verifier", "verifying"))

    def test_v2_route_matrix_strict_dispatches_reviewer_then_verifier(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{
                    "projectId": "project-v2-strict",
                    "target": {"type": "project", "projectId": "project-v2-strict"},
                }]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id = "project-v2-strict"
            task_id = "ctr-20260712-100000-strict"
            parent_thread_id = "parent-v2-strict"
            objective = "review a strict protocol change"
            target = {"type": "project", "projectId": project_id}
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-strict", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/protocol.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={
                    "authorizedBy": "explicit_cost_aware_entry",
                    "allowedDefaults": ["gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high"],
                },
            )
            plan = {
                "scope": package["scope"], "permission": package["permission"],
                "stopCondition": package["stopCondition"], "requestedGateClass": "STRICT",
                "requestedRoleRouting": {
                    "executor": {"executionClass": "standard"},
                    "reviewer": {"executionClass": "high"},
                    "verifier": {"executionClass": "mechanical"},
                },
            }
            adapter = V2Adapter()
            common = {
                "objective": objective, "project_local_path": root, "thread_adapter": adapter,
                "permission": "local-package", "observed_at": "2026-07-12T10:00:00+08:00",
                "target": target, "parent_thread_id": parent_thread_id,
                "heartbeat_scheduler": FakeHeartbeatScheduler(),
            }
            first = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, manager_plan=plan,
                task_authorization_package=package, **common,
            )
            executor = first["ledger"]["dispatches"][-1]
            adapter.messages.setdefault(parent_thread_id, []).append({
                "messageId": "msg-executor-direct", "sentAt": "2026-07-12T10:01:00+08:00",
                "sourceThreadId": executor["threadId"],
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\n"
                    "role: Executor\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nstatus: done\nfinal: true\nsummary: executor done\n"
                    "evidence: focused test OK\nrisks: none\nnext: reviewer"
                ) % (task_id, parent_thread_id, executor["threadId"], executor["protocolVersion"], executor["dispatchId"], executor["requestId"], executor["attempt"]),
            })
            second = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual((second["action"], second["status"]), ("sent_v2_reviewer", "reviewing"))
            reviewer = second["ledger"]["dispatches"][-1]
            self.assertEqual(
                (adapter.sent[-1]["kwargs"]["model"], adapter.sent[-1]["kwargs"]["thinking"]),
                ("gpt-5.6-sol", "high"),
            )
            adapter.messages.setdefault(parent_thread_id, []).append({
                "messageId": "msg-reviewer-direct", "sentAt": "2026-07-12T10:02:00+08:00",
                "sourceThreadId": reviewer["threadId"],
                "text": (
                    "TEAM_ROUTER_REVIEW taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\n"
                    "role: Reviewer\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nresult: pass\nsummary: reviewer pass\nfindings: none\n"
                    "requiredChanges: none\nevidenceChecked: focused test OK\nrisks: none"
                ) % (task_id, parent_thread_id, reviewer["threadId"], reviewer["protocolVersion"], reviewer["dispatchId"], reviewer["requestId"], reviewer["attempt"]),
            })
            third = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual((third["action"], third["status"]), ("sent_v2_verifier", "verifying"))
            verifier = third["ledger"]["dispatches"][-1]
            self.assertEqual(
                (adapter.sent[-1]["kwargs"]["model"], adapter.sent[-1]["kwargs"]["thinking"]),
                ("gpt-5.6-luna", "medium"),
            )
            adapter.messages.setdefault(parent_thread_id, []).append({
                "messageId": "msg-verifier-direct", "sentAt": "2026-07-12T10:03:00+08:00",
                "sourceThreadId": verifier["threadId"],
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\n"
                    "role: Verifier\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nresult: pass\nsummary: verifier pass\nrequiredChanges: none\n"
                    "evidenceChecked: focused test OK\nrisks: none"
                ) % (task_id, parent_thread_id, verifier["threadId"], verifier["protocolVersion"], verifier["dispatchId"], verifier["requestId"], verifier["attempt"]),
            })
            complete = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)

            self.assertEqual((complete["action"], complete["status"]), ("v2_terminal_closeout", "done"))
            self.assertEqual(len(adapter.sent), 3)

    def test_v2_route_matrix_architect_and_qa_preserves_all_required_roles(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-v2-full", "target": {"type": "project", "projectId": "project-v2-full"}}]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-full", "ctr-20260712-100000-full", "parent-v2-full"
            objective, target = "complete an independently reviewed protocol change", {"type": "project", "projectId": project_id}
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-full", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/protocol.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            plan = {
                "scope": package["scope"], "permission": package["permission"],
                "stopCondition": package["stopCondition"], "requestedGateClass": "STRICT",
                "explicitRoles": ("architect", "qa"),
                "requestedRoleRouting": {
                    "architect": {"executionClass": "high"}, "executor": {"executionClass": "standard"},
                    "reviewer": {"executionClass": "high"}, "qa": {"executionClass": "standard"},
                    "verifier": {"executionClass": "mechanical"},
                },
            }
            adapter = V2Adapter()
            common = {
                "objective": objective, "project_local_path": root, "thread_adapter": adapter,
                "permission": "local-package", "observed_at": "2026-07-12T10:00:00+08:00",
                "target": target, "parent_thread_id": parent_thread_id,
                "heartbeat_scheduler": FakeHeartbeatScheduler(),
            }

            def reply(record, marker, body, message_id):
                adapter.messages.setdefault(parent_thread_id, []).append({
                    "messageId": message_id, "sentAt": "2026-07-12T10:01:00+08:00",
                    "sourceThreadId": record["threadId"],
                    "text": "%s taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\nrole: %s\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\n%s" % (
                        marker, task_id, parent_thread_id, record["threadId"],
                        team_router.ROLE_ALIASES[record["role"]], record["protocolVersion"],
                        record["dispatchId"], record["requestId"], record["attempt"], body,
                    ),
                })

            first = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, manager_plan=plan, task_authorization_package=package, **common)
            reply(first["ledger"]["dispatches"][-1], "TEAM_ROUTER_ARCHITECT_REVIEW", "result: pass\nsummary: architecture pass\nfindings: none\nrequiredChanges: none\nevidenceChecked: design checked\nrisks: none\nskillProfileUsed: architect-default\narchitectureImpact: none\ncompatibilityNotes: compatible\nalternatives: none\nmigrationRisks: none", "architect")
            second = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual(second["action"], "sent_v2_executor")
            reply(second["ledger"]["dispatches"][-1], "TEAM_ROUTER_CALLBACK", "status: done\nfinal: true\nsummary: executor pass\nevidence: focused test OK\nrisks: none\nnext: reviewer", "executor")
            third = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual(third["action"], "sent_v2_reviewer")
            reply(third["ledger"]["dispatches"][-1], "TEAM_ROUTER_REVIEW", "result: pass\nsummary: reviewer pass\nfindings: none\nrequiredChanges: none\nevidenceChecked: review checked\nrisks: none", "reviewer")
            fourth = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual((fourth["action"], fourth["status"]), ("sent_v2_qa", "awaiting_qa_review"))
            reply(fourth["ledger"]["dispatches"][-1], "TEAM_ROUTER_QA_REVIEW", "result: pass\nsummary: QA pass\nfindings: none\nrequiredChanges: none\nevidenceChecked: QA checked\nrisks: none\nskillProfileUsed: qa-default\ncoverageGaps: none\nverificationPlan: focused check\nregressionRisks: none", "qa")
            fifth = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)
            self.assertEqual((fifth["action"], fifth["status"]), ("sent_v2_verifier", "verifying"))
            reply(fifth["ledger"]["dispatches"][-1], "TEAM_ROUTER_VERDICT", "result: pass\nsummary: verifier pass\nrequiredChanges: none\nevidenceChecked: verifier checked\nrisks: none", "verifier")
            complete = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)

            self.assertEqual(complete["status"], "done")
            self.assertEqual([item["kwargs"]["model"] for item in adapter.sent], [
                "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
            ])

    def test_v2_target_fingerprint_mismatch_prevents_title_pool_and_thread_creation(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": []}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            task_id, parent_thread_id, objective = "ctr-20260712-100000-fingerprint", "parent-v2-fingerprint", "change one local file"
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-fingerprint", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            adapter, scheduler = V2Adapter(), FakeHeartbeatScheduler()
            update = team_router.orchestrate_team_task_with_adapter(
                root, "project-v2-fingerprint", task_id, objective=objective, project_local_path=root,
                thread_adapter=adapter, permission="local-package", observed_at="2026-07-12T10:00:00+08:00",
                target={"type": "project", "projectId": "project-v2-fingerprint"},
                target_fingerprint="not-the-canonical-fingerprint", host_id="local",
                parent_thread_id=parent_thread_id, heartbeat_scheduler=scheduler,
                manager_plan={
                    "scope": package["scope"], "permission": package["permission"],
                    "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                    "explicitRoles": ("executor",),
                    "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
                },
                task_authorization_package=package,
            )

            self.assertEqual((update["action"], update["status"]), ("target_fingerprint_invalid", "tool_error"))
            self.assertEqual((adapter.renamed, adapter.created, adapter.sent, scheduler.scheduled), ([], [], [], []))
            self.assertFalse(team_router.task_path(root, "project-v2-fingerprint", task_id).exists())

    def test_sticky_continuation_rejects_parent_scope_external_gate_and_terminal_before_live_calls(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-sticky", "ctr-20260712-100000-sticky", "parent-v2-sticky"
            objective = "continue one narrow delegated task"
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-sticky", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            plan = {
                "scope": package["scope"], "permission": package["permission"],
                "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                "explicitRoles": ("executor",),
                "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
            }
            resolved = team_router.resolve_v2_manager_plan(
                objective=objective, scope=package["scope"], permission=package["permission"],
                stop_condition=package["stopCondition"], requested_gate_class="NORMAL",
                authorization_package=package, explicit_roles=("executor",),
                requested_role_routing=plan["requestedRoleRouting"],
                ledger_input={"taskId": task_id, "parentThreadId": parent_thread_id},
            )
            ledger = team_router.new_v2_task_ledger(
                root, project_id, task_id, objective=objective, project_local_path=root,
                parent_thread_id=parent_thread_id, resolved_plan=resolved,
                task_authorization_package=package, created_at="2026-07-12T10:00:00+08:00",
            )
            team_router.save_task_ledger(root, project_id, task_id, ledger)

            def invoke(*, parent=parent_thread_id, supplied_plan=plan, supplied_objective=objective):
                with mock.patch("team_router.assess_live_orchestration_readiness", side_effect=AssertionError("readiness")):
                    return team_router.orchestrate_team_task_with_adapter(
                        root, project_id, task_id, objective=supplied_objective, project_local_path=root,
                        thread_adapter=object(), permission="local-package", observed_at="2026-07-12T10:00:00+08:00",
                        parent_thread_id=parent, heartbeat_scheduler=object(), manager_plan=supplied_plan,
                        task_authorization_package=package,
                    )

            self.assertEqual(invoke(parent="other-parent")["action"], "authorization_mismatch")
            self.assertEqual(invoke(supplied_objective="expanded delegated task")["action"], "authorization_mismatch")
            self.assertEqual(invoke(supplied_plan={**plan, "scope": "src/expanded.py"})["action"], "authorization_mismatch")
            self.assertEqual(invoke(supplied_plan={**plan, "externalGates": ("commit",)})["action"], "authorization_mismatch")
            terminal = team_router.load_task_ledger(root, project_id, task_id)
            terminal["status"] = "done"
            team_router.save_task_ledger(root, project_id, task_id, terminal)
            self.assertEqual(invoke()["action"], "authorization_expired")

    def test_manager_acceptance_is_parent_local_and_never_schedules_role_polling(self):
        update = {
            "status": "manager_acceptance_pending",
            "watcher": {
                "role": "executor", "threadId": "thread-executor",
                "firstCheckAt": "2026-07-12T10:00:30+08:00",
                "nextAllowedReadAt": "2026-07-12T10:05:00+08:00", "lastReadAt": None,
            },
        }

        payload = team_router_watcher_runtime.build_watcher_heartbeat_payload(
            update,
            state_root="C:/tmp/team-router-manager-acceptance", project_id="project-v2-acceptance",
            task_id="ctr-20260712-100000-acceptance", permission="local-package",
        )

        self.assertIsNone(payload)

    def test_v2_self_thread_fallback_uses_dispatch_thread_without_legacy_role_registry(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-v2-fallback", "target": {"type": "project", "projectId": "project-v2-fallback"}}]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-fallback", "ctr-20260712-100000-fallback", "parent-v2-fallback"
            objective, target = "finish one local task", {"type": "project", "projectId": project_id}
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-fallback", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            adapter = V2Adapter()
            common = {
                "objective": objective, "project_local_path": root, "thread_adapter": adapter,
                "permission": "local-package", "observed_at": "2026-07-12T10:00:00+08:00",
                "target": target, "parent_thread_id": parent_thread_id,
                "heartbeat_scheduler": FakeHeartbeatScheduler(),
            }
            first = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, manager_plan={
                    "scope": package["scope"], "permission": package["permission"],
                    "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                    "explicitRoles": ("executor",),
                    "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
                }, task_authorization_package=package, **common,
            )
            executor = first["ledger"]["dispatches"][-1]
            adapter.append_reply(
                executor["threadId"],
                "TEAM_ROUTER_CALLBACK taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\nrole: Executor\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nstatus: done\nfinal: true\nsummary: fallback pass\nevidence: focused test OK\nrisks: none\nnext: manager" % (
                    task_id, parent_thread_id, executor["threadId"],
                    executor["protocolVersion"], executor["dispatchId"],
                    executor["requestId"], executor["attempt"],
                ),
                message_id="msg-self-thread", sent_at="2026-07-12T10:01:00+08:00",
            )
            registry = team_router.load_registry(root, project_id)
            self.assertEqual(registry["projects"][project_id]["roles"], {})

            second = team_router.orchestrate_team_task_with_adapter(root, project_id, task_id, **common)

            self.assertEqual((second["action"], second["status"]), ("manager_acceptance_pending", "manager_acceptance_pending"))
            accepted = team_router.record_manager_acceptance(
                root,
                project_id,
                task_id,
                result="pass",
                accepted_at="2026-07-12T10:02:00+08:00",
                callback_receipt="manager checked fallback receipt",
                scope_checked="scope unchanged",
                evidence_checked="focused test OK",
                risk_boundary_checked="NORMAL",
                remaining_risks="none",
            )

            self.assertEqual(accepted["closeout"]["receiptSource"], "self-thread-fallback/read_thread")
            self.assertEqual(accepted["closeout"]["receiptChannel"], "read_thread")
            self.assertEqual(accepted["closeout"]["receiptRoleThreadId"], executor["threadId"])
            self.assertEqual(accepted["closeout"]["returnThreadId"], parent_thread_id)
            self.assertEqual(accepted["closeout"]["deliveryStatus"], "fallback_only")
            self.assertTrue(accepted["closeout"]["deliveryDegraded"])
            closeout = team_router.format_closeout_for_user(
                accepted,
                team_router.load_registry(root, project_id),
            )
            self.assertIn("deliveryStatus: fallback_only", closeout)
            self.assertIn("delivery: degraded", closeout)

    def test_v2_verifier_fallback_closeout_preserves_delivery_provenance(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-verifier-closeout", "ctr-20260712-100000-verifier-closeout", "parent-v2-verifier-closeout"
            objective = "verify a fallback closeout"
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-verifier-closeout", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            plan = team_router.resolve_v2_manager_plan(
                objective=objective, scope=package["scope"], permission=package["permission"],
                stop_condition=package["stopCondition"], requested_gate_class="STRICT",
                authorization_package=package,
                requested_role_routing={
                    "executor": {"executionClass": "standard"},
                    "reviewer": {"executionClass": "high"},
                    "verifier": {"executionClass": "mechanical"},
                }, ledger_input={"taskId": task_id, "parentThreadId": parent_thread_id},
            )
            ledger = team_router.new_v2_task_ledger(
                root, project_id, task_id, objective=objective, project_local_path=root,
                parent_thread_id=parent_thread_id, resolved_plan=plan,
                task_authorization_package=package, created_at="2026-07-12T10:00:00+08:00",
            )
            receipt = {
                "source": "self-thread-fallback/read_thread",
                "channel": "read_thread",
                "roleThreadId": "thread-v2-verifier",
                "returnThreadId": parent_thread_id,
                "orchestratorThreadId": parent_thread_id,
            }
            ledger.update({
                "status": "done",
                "verification": {"verdict": {"receipt": receipt}},
                "observations": [{
                    "type": "callback_raw", "role": "executor",
                    "parsedFields": {"status": "done", "final": "true", "summary": "executor completed"},
                }],
            })

            closeout = team_router._make_closeout(
                ledger,
                {"result": "pass", "summary": "verifier passed", "requiredChanges": "none", "evidenceChecked": "focused test OK", "risks": "none"},
                "2026-07-12T10:02:00+08:00",
            )

            self.assertEqual(closeout["receiptSource"], "self-thread-fallback/read_thread")
            self.assertEqual(closeout["receiptChannel"], "read_thread")
            self.assertEqual(closeout["receiptRoleThreadId"], "thread-v2-verifier")
            self.assertEqual(closeout["returnThreadId"], parent_thread_id)
            self.assertEqual(closeout["deliveryStatus"], "fallback_only")
            self.assertTrue(closeout["deliveryDegraded"])

    def test_v2_watcher_heartbeat_uses_manager_pool_dispatch_and_stops_at_manager_acceptance(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-v2-watch", "target": {"type": "project", "projectId": "project-v2-watch"}}]}

            def list_threads(self, **kwargs):
                return {"threads": []}

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-watch", "ctr-20260712-100000-watch", "parent-v2-watch"
            objective, target = "finish one watched local task", {"type": "project", "projectId": project_id}
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-watch", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            adapter = V2Adapter()
            first = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, objective=objective, project_local_path=root,
                thread_adapter=adapter, permission="local-package", observed_at="2026-07-12T10:00:00+08:00",
                target=target, parent_thread_id=parent_thread_id, heartbeat_scheduler=FakeHeartbeatScheduler(),
                manager_plan={
                    "scope": package["scope"], "permission": package["permission"],
                    "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                    "explicitRoles": ("executor",),
                    "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
                }, task_authorization_package=package,
            )
            executor = first["ledger"]["dispatches"][-1]
            adapter.append_reply(
                executor["threadId"],
                "TEAM_ROUTER_CALLBACK taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\nrole: Executor\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nstatus: done\nfinal: true\nsummary: watcher fallback pass\nevidence: focused test OK\nrisks: none\nnext: manager" % (
                    task_id, parent_thread_id, executor["threadId"],
                    executor["protocolVersion"], executor["dispatchId"],
                    executor["requestId"], executor["attempt"],
                ),
                message_id="msg-watch-fallback", sent_at="2026-07-12T10:01:00+08:00",
            )
            self.assertEqual(team_router.load_registry(root, project_id)["projects"][project_id]["roles"], {})
            scheduler = FakeHeartbeatScheduler()

            update = team_router.watch_team_task_with_adapter(
                root, project_id, task_id, thread_adapter=adapter, permission="local-package",
                observed_at="2026-07-12T10:01:30+08:00", heartbeat_scheduler=scheduler,
            )

            self.assertEqual((update["action"], update["status"]), ("manager_acceptance_pending", "manager_acceptance_pending"))
            self.assertIsNone(update["nextWakeup"])
            self.assertEqual(scheduler.scheduled, [])

    def test_v2_watcher_cadence_stays_gated_while_direct_facade_checks_immediately(self):
        class CountingV2Adapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.read_count = 0

            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-v2-cadence", "target": {"type": "project", "projectId": "project-v2-cadence"}}]}

            def list_threads(self, **kwargs):
                return {"threads": []}

            def send_message_to_thread(self, **kwargs):
                result = super().send_message_to_thread(**kwargs)
                sent_at = "2026-07-12T10:00:00+08:00"
                self.messages[kwargs["threadId"]][-1]["sentAt"] = sent_at
                result["message"]["createdAt"] = sent_at
                return result

            def read_thread(self, **kwargs):
                self.read_count += 1
                return super().read_thread(**kwargs)

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-cadence", "ctr-20260712-100000-cadence", "parent-v2-cadence"
            objective, target = "check one explicit callback", {"type": "project", "projectId": project_id}
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-cadence", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            plan = {
                "scope": package["scope"], "permission": package["permission"],
                "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                "explicitRoles": ("executor",),
                "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
            }
            adapter = CountingV2Adapter()
            common = {
                "objective": objective, "project_local_path": root, "thread_adapter": adapter,
                "permission": "local-package", "target": target, "parent_thread_id": parent_thread_id,
                "heartbeat_scheduler": FakeHeartbeatScheduler(),
            }
            first = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, observed_at="2026-07-12T10:00:00+08:00",
                manager_plan=plan, task_authorization_package=package, **common,
            )
            executor = first["ledger"]["dispatches"][-1]
            self.assertEqual(first["ledger"]["readDiscipline"]["nextAllowedReadAt"], "2026-07-12T10:05:00+08:00")
            decision = team_router._watcher_read_allowed(
                first["ledger"], observed_at="2026-07-12T10:00:10+08:00", read_reason="scheduled watcher heartbeat",
            )
            self.assertFalse(decision["allowed"], decision)
            adapter.messages[parent_thread_id] = [{
                "messageId": "msg-cadence-direct", "sentAt": "2026-07-12T10:00:05+08:00",
                "sourceThreadId": executor["threadId"],
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\n"
                    "role: Executor\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\nstatus: done\nfinal: true\nsummary: direct check pass\n"
                    "evidence: focused test OK\nrisks: none\nnext: manager"
                ) % (task_id, parent_thread_id, executor["threadId"], executor["protocolVersion"], executor["dispatchId"], executor["requestId"], executor["attempt"]),
            }]

            early = team_router.watch_team_task_with_adapter(
                root, project_id, task_id, thread_adapter=adapter, permission="local-package",
                observed_at="2026-07-12T10:00:10+08:00", heartbeat_scheduler=FakeHeartbeatScheduler(),
            )

            self.assertEqual(early["action"], "watch_read_suppressed", early)
            self.assertEqual(adapter.read_count, 0)
            direct = team_router.orchestrate_team_task_with_adapter(
                root, project_id, task_id, observed_at="2026-07-12T10:00:10+08:00", **common,
            )
            self.assertEqual((direct["action"], direct["status"]), ("manager_acceptance_pending", "manager_acceptance_pending"))
            self.assertGreater(adapter.read_count, 0)

    def test_v2_route_matrix_explicit_architect_and_qa_singleton_paths(self):
        class V2Adapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": []}

            def list_threads(self, **kwargs):
                return {"threads": []}

        def make_package(*, task_id, parent_thread_id, objective):
            return team_router.make_task_authorization_package(
                package_id="auth-%s" % task_id, task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )

        def direct_reply(adapter, *, task_id, parent_thread_id, dispatch, marker, fields, message_id):
            adapter.messages.setdefault(parent_thread_id, []).append({
                "messageId": message_id, "sentAt": "2026-07-12T10:01:00+08:00",
                "sourceThreadId": dispatch["threadId"],
                "text": "%s taskId=%s\nsourceThreadId: %s\nsourceRoleThreadId: %s\nrole: %s\nprotocolVersion: %s\ndispatchId: %s\nrequestId: %s\nattempt: %s\n%s" % (
                    marker, task_id, parent_thread_id, dispatch["threadId"],
                    team_router.ROLE_ALIASES[dispatch["role"]], dispatch["protocolVersion"],
                    dispatch["dispatchId"], dispatch["requestId"], dispatch["attempt"], fields,
                ),
            })

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            architect_project, architect_task, architect_parent = "project-v2-architect", "ctr-20260712-100000-architect", "parent-v2-architect"
            architect_objective = "apply one explicit architecture review"
            architect_package = make_package(
                task_id=architect_task, parent_thread_id=architect_parent, objective=architect_objective,
            )
            architect_adapter = V2Adapter()
            architect_common = {
                "objective": architect_objective, "project_local_path": root, "thread_adapter": architect_adapter,
                "permission": "local-package", "observed_at": "2026-07-12T10:00:00+08:00",
                "target": {"type": "project", "projectId": architect_project},
                "parent_thread_id": architect_parent, "heartbeat_scheduler": FakeHeartbeatScheduler(),
            }
            architect_plan = {
                "scope": architect_package["scope"], "permission": architect_package["permission"],
                "stopCondition": architect_package["stopCondition"], "requestedGateClass": "NORMAL",
                "explicitRoles": ("architect",),
                "requestedRoleRouting": {
                    "architect": {"executionClass": "high"}, "executor": {"executionClass": "standard"},
                },
            }
            architect_first = team_router.orchestrate_team_task_with_adapter(
                root, architect_project, architect_task, manager_plan=architect_plan,
                task_authorization_package=architect_package, **architect_common,
            )
            self.assertEqual((architect_first["action"], architect_first["status"]), ("sent_v2_architect", "awaiting_architect_review"))
            direct_reply(
                architect_adapter, task_id=architect_task, parent_thread_id=architect_parent,
                dispatch=architect_first["ledger"]["dispatches"][-1], marker="TEAM_ROUTER_ARCHITECT_REVIEW",
                fields="result: pass\nsummary: architecture pass\nfindings: none\nrequiredChanges: none\nevidenceChecked: design checked\nrisks: none\nskillProfileUsed: architect-default\narchitectureImpact: none\ncompatibilityNotes: compatible\nalternatives: none\nmigrationRisks: none",
                message_id="msg-architect-singleton",
            )
            architect_second = team_router.orchestrate_team_task_with_adapter(
                root, architect_project, architect_task, **architect_common,
            )
            self.assertEqual((architect_second["action"], architect_second["status"]), ("sent_v2_executor", "awaiting_callback"))
            direct_reply(
                architect_adapter, task_id=architect_task, parent_thread_id=architect_parent,
                dispatch=architect_second["ledger"]["dispatches"][-1], marker="TEAM_ROUTER_CALLBACK",
                fields="status: done\nfinal: true\nsummary: executor pass\nevidence: focused test OK\nrisks: none\nnext: manager",
                message_id="msg-architect-executor",
            )
            architect_third = team_router.orchestrate_team_task_with_adapter(
                root, architect_project, architect_task, **architect_common,
            )
            self.assertEqual((architect_third["action"], architect_third["status"]), ("manager_acceptance_pending", "manager_acceptance_pending"))
            self.assertEqual([item["role"] for item in architect_third["ledger"]["dispatches"]], ["architect", "executor"])

            qa_project, qa_task, qa_parent = "project-v2-qa", "ctr-20260712-100000-qa", "parent-v2-qa"
            qa_objective = "apply one explicit QA review"
            qa_package = make_package(task_id=qa_task, parent_thread_id=qa_parent, objective=qa_objective)
            qa_adapter = V2Adapter()
            qa_common = {
                "objective": qa_objective, "project_local_path": root, "thread_adapter": qa_adapter,
                "permission": "local-package", "observed_at": "2026-07-12T10:00:00+08:00",
                "target": {"type": "project", "projectId": qa_project},
                "parent_thread_id": qa_parent, "heartbeat_scheduler": FakeHeartbeatScheduler(),
            }
            qa_plan = {
                "scope": qa_package["scope"], "permission": qa_package["permission"],
                "stopCondition": qa_package["stopCondition"], "requestedGateClass": "NORMAL",
                "explicitRoles": ("qa",),
                "requestedRoleRouting": {
                    "executor": {"executionClass": "standard"}, "qa": {"executionClass": "standard"},
                    "verifier": {"executionClass": "mechanical"},
                },
            }
            qa_first = team_router.orchestrate_team_task_with_adapter(
                root, qa_project, qa_task, manager_plan=qa_plan, task_authorization_package=qa_package, **qa_common,
            )
            self.assertEqual((qa_first["action"], qa_first["status"]), ("sent_v2_executor", "awaiting_callback"))
            direct_reply(
                qa_adapter, task_id=qa_task, parent_thread_id=qa_parent,
                dispatch=qa_first["ledger"]["dispatches"][-1], marker="TEAM_ROUTER_CALLBACK",
                fields="status: done\nfinal: true\nsummary: executor pass\nevidence: focused test OK\nrisks: none\nnext: QA",
                message_id="msg-qa-executor",
            )
            qa_second = team_router.orchestrate_team_task_with_adapter(root, qa_project, qa_task, **qa_common)
            self.assertEqual((qa_second["action"], qa_second["status"]), ("sent_v2_qa", "awaiting_qa_review"))
            direct_reply(
                qa_adapter, task_id=qa_task, parent_thread_id=qa_parent,
                dispatch=qa_second["ledger"]["dispatches"][-1], marker="TEAM_ROUTER_QA_REVIEW",
                fields="result: pass\nsummary: QA pass\nfindings: none\nrequiredChanges: none\nevidenceChecked: QA checked\nrisks: none\nskillProfileUsed: qa-default\ncoverageGaps: none\nverificationPlan: focused test\nregressionRisks: none",
                message_id="msg-qa-singleton",
            )
            qa_third = team_router.orchestrate_team_task_with_adapter(root, qa_project, qa_task, **qa_common)
            self.assertEqual((qa_third["action"], qa_third["status"]), ("sent_v2_verifier", "verifying"))
            direct_reply(
                qa_adapter, task_id=qa_task, parent_thread_id=qa_parent,
                dispatch=qa_third["ledger"]["dispatches"][-1], marker="TEAM_ROUTER_VERDICT",
                fields="result: pass\nsummary: verifier pass\nrequiredChanges: none\nevidenceChecked: focused test OK\nrisks: none",
                message_id="msg-qa-verifier",
            )
            qa_complete = team_router.orchestrate_team_task_with_adapter(root, qa_project, qa_task, **qa_common)
            self.assertEqual((qa_complete["action"], qa_complete["status"]), ("v2_terminal_closeout", "done"))
            self.assertEqual([item["role"] for item in qa_complete["ledger"]["dispatches"]], ["executor", "qa", "verifier"])

    def test_v2_parallel_allowed_reaches_facade_reservation_and_shared_write_conflict_blocks_it(self):
        class ParallelAdapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {"projects": [{"projectId": "project-v2-parallel", "target": {"type": "project", "projectId": "project-v2-parallel"}}]}

            def list_threads(self, **kwargs):
                return {"threads": []}

            def create_thread(self, **kwargs):
                record = super().create_thread(**kwargs)
                old_thread_id = record["threadId"]
                thread_id = "%s-%d" % (old_thread_id, len(self.created))
                self.messages[thread_id] = self.messages.pop(old_thread_id)
                result = {**record, "threadId": thread_id}
                self.created[-1]["result"] = result
                return result

        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, parent_thread_id = "project-v2-parallel", "parent-v2-parallel"
            objective, target = "run independent local checks", {"type": "project", "projectId": project_id}
            adapter = ParallelAdapter()

            def run(task_id, *, conflicts=()):
                package = team_router.make_task_authorization_package(
                    package_id="auth-%s" % task_id, task_id=task_id, parent_thread_id=parent_thread_id,
                    objective=objective, scope="src/example.py only", permission="local-package",
                    stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                    model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                        "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                    ]},
                )
                return team_router.orchestrate_team_task_with_adapter(
                    root, project_id, task_id, objective=objective, project_local_path=root,
                    thread_adapter=adapter, permission="local-package", observed_at="2026-07-12T10:00:00+08:00",
                    target=target, parent_thread_id=parent_thread_id, heartbeat_scheduler=FakeHeartbeatScheduler(),
                    manager_plan={
                        "scope": package["scope"], "permission": package["permission"],
                        "stopCondition": package["stopCondition"], "requestedGateClass": "NORMAL",
                        "requiresParallelism": True, "parallelConflicts": conflicts,
                        "requestedRoleRouting": {"executor": {"executionClass": "standard"}},
                    }, task_authorization_package=package,
                )

            first = run("ctr-20260712-100000-parallel-a")
            second = run("ctr-20260712-100000-parallel-b")
            blocked = run("ctr-20260712-100000-parallel-c", conflicts=("shared-write",))
            pool = team_router.load_registry(root, project_id)["projects"][project_id]["managerPools"][team_router_state.PROJECT_ROLE_POOL_KEY]

            self.assertTrue(first["ledger"]["plan"]["parallelAllowed"])
            self.assertTrue(second["ledger"]["plan"]["parallelAllowed"])
            self.assertEqual(len(pool["roles"]["executor"]), 2)
            self.assertEqual((blocked["action"], blocked["ledger"]["plan"]["parallelAllowed"]), ("v2_busy", False))
            self.assertEqual(len(adapter.created), 2)

    def test_v2_reviewer_rework_consumes_the_single_global_budget(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-rework", "ctr-20260712-100000-rework", "parent-v2-rework"
            objective = "review one strict local change"
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-rework", task_id=task_id, parent_thread_id=parent_thread_id,
                objective=objective, scope="src/example.py only", permission="local-package",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
                model_routing_authorization={"authorizedBy": "explicit_cost_aware_entry", "allowedDefaults": [
                    "gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high",
                ]},
            )
            plan = team_router.resolve_v2_manager_plan(
                objective=objective, scope=package["scope"], permission=package["permission"],
                stop_condition=package["stopCondition"], requested_gate_class="STRICT",
                authorization_package=package,
                requested_role_routing={
                    "executor": {"executionClass": "standard"}, "reviewer": {"executionClass": "high"},
                    "verifier": {"executionClass": "mechanical"},
                }, ledger_input={"taskId": task_id, "parentThreadId": parent_thread_id},
            )
            ledger = team_router.new_v2_task_ledger(
                root, project_id, task_id, objective=objective, project_local_path=root,
                parent_thread_id=parent_thread_id, resolved_plan=plan,
                task_authorization_package=package, created_at="2026-07-12T10:00:00+08:00",
            )
            ledger.update({
                "status": "reviewing",
                "review": {"request": {"role": "reviewer", "threadId": "thread-reviewer"}},
            })
            message = team_router.parse_review(
                "TEAM_ROUTER_REVIEW taskId=%s\nresult: needs_rework\nsummary: fix required\n"
                "findings: one issue\nrequiredChanges: add a check\nevidenceChecked: focused test\nrisks: none" % task_id,
                task_id,
            )

            first = team_router._apply_reviewer_review_message(
                ledger, dict(ledger["review"]), ledger["review"]["request"], message,
                captured_at="2026-07-12T10:01:00+08:00",
            )
            second_input = dict(first)
            second_input["status"] = "reviewing"
            second = team_router._apply_reviewer_review_message(
                second_input, dict(second_input["review"]), second_input["review"]["request"], message,
                captured_at="2026-07-12T10:02:00+08:00",
            )

            self.assertEqual((first["status"], first["reworkCount"]), ("dispatched", 1))
            self.assertEqual((second["status"], second["reworkCount"]), ("blocked", 1))

    def test_v2_executor_self_thread_fallback_rejects_missing_direct_return_identity(self):
        with workspace_temp_dir() as td:
            root = Path(td) / "state"
            project_id, task_id, parent_thread_id = "project-v2-malformed", "ctr-20260712-100000-malformed", "parent-v2-malformed"
            package = team_router.make_task_authorization_package(
                package_id="auth-v2-malformed", task_id=task_id, parent_thread_id=parent_thread_id,
                objective="validate a fallback callback", scope="src/example.py only", permission="read-only",
                stop_condition="focused test passes", created_at="2026-07-12T10:00:00+08:00",
            )
            ledger = team_router.new_v2_task_ledger(
                root, project_id, task_id, objective=package["objective"], project_local_path=root,
                parent_thread_id=parent_thread_id,
                resolved_plan={
                    "scope": package["scope"], "permission": package["permission"],
                    "stopCondition": package["stopCondition"], "routeRoles": ["executor"],
                    "roleRouting": {"executor": {"executionClass": "standard", "requestedModel": "gpt-5.6-terra", "requestedThinking": "medium"}},
                }, task_authorization_package=package, created_at="2026-07-12T10:00:00+08:00",
            )
            ledger.update({
                "status": "awaiting_callback",
                "dispatches": [{
                    "role": "executor", "threadId": "thread-executor", "roleThreadId": "thread-executor",
                    "returnThreadId": parent_thread_id, "callbackDelivery": "direct-send",
                    "messageId": "msg-dispatch", "sentAt": "2026-07-12T10:00:00+08:00",
                    "searchAnchor": {"messageId": "msg-dispatch", "sentAt": "2026-07-12T10:00:00+08:00"},
                    "fallbackSearchAnchor": {"messageId": "msg-dispatch", "sentAt": "2026-07-12T10:00:00+08:00"},
                }],
            })
            team_router.save_task_ledger(root, project_id, task_id, ledger)

            captured = team_router.capture_executor_callback_from_read(
                root, project_id, task_id,
                [
                    {"messageId": "msg-dispatch", "sentAt": "2026-07-12T10:00:00+08:00", "text": "dispatch"},
                    {"messageId": "msg-fallback", "sentAt": "2026-07-12T10:01:00+08:00", "text": (
                        "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: missing identity\n"
                        "evidence: focused test\nrisks: none\nnext: manager"
                    ) % task_id},
                ], captured_at="2026-07-12T10:02:00+08:00",
            )

            self.assertEqual(captured["status"], "malformed_callback")
            self.assertTrue(captured["malformedDirectReturns"])


if __name__ == "__main__":
    unittest.main()
