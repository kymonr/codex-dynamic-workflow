# Team Router Host RPC Broker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repo-local support for a future Codex Desktop/plugin localhost RPC broker without implementing the Desktop/plugin broker.

**Architecture:** Build a small Python broker boundary: a localhost RPC client, a `CodexAppThreadAdapter` exposing existing Team Router callable methods, conservative readiness helpers, and a scheduler wake wrapper. All repo-local behavior uses fake localhost broker tests; real Desktop/plugin authority remains a later feasibility gate.

**Tech Stack:** Python standard library only: `urllib.request`, `json`, `uuid`, `dataclasses`, `http.server`, `threading`, `unittest`. Existing modules under `src/`. Existing `tests/test_team_router.py`.

## Global Constraints

- No Codex Desktop/plugin broker implementation in this repo.
- No fake claim that model-side Codex app tool descriptors are Python callables.
- No production daemon or long-running scheduler implementation.
- No native `multi_agent_v1` replacement for visible Team Router role threads.
- Broker client may call only `127.0.0.1` or `localhost` by default.
- Broker thread-tool methods are allowlisted only: `list_projects`, `create_thread`, `list_threads`, `read_thread`, `send_message_to_thread`, `set_thread_title`.
- Scheduler callback allowlist is only `watch_team_task_with_adapter`.
- Missing broker, parent thread id, callable evidence, tool smoke, or scheduler smoke means `manual_only` or `host_contract_blocked`, not automatic orchestration.
- Preserve watcher timing: `FIRST_ROLE_CHECK_DELAY_SECONDS = 30`, `MIN_ROLE_POLL_INTERVAL_SECONDS = 300`.
- Preserve direct-send first and bounded `read_thread` fallback only.
- No push, PR, remote merge, deploy, release, global skill sync, or external app/plugin state changes in repo-local packages.

---

## File Structure

- Create `src/team_router_broker_adapter.py`: broker config, localhost RPC client, thread adapter wrapper, readiness helpers, and later scheduler wrapper.
- Modify `src/team_router.py`: re-export stable broker adapter symbols after tests pass.
- Modify `tests/test_team_router.py`: fake broker tests for client, adapter, readiness, scheduler, facade exports.
- Create `scripts/team_router_broker_feasibility_check.py`: read-only checker for externally supplied broker URL/token.
- Optional docs after real external evidence: `docs/team-router/packages/ctr-20260701-host-rpc-broker-feasibility.md`.

---

### Task 1: Add Localhost Broker RPC Client Primitives

**Files:**
- Create: `src/team_router_broker_adapter.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Produces: `BrokerConfig(base_url: str, session_token: str, timeout_ms: int = 10000, allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost"))`
- Produces: `BrokerProtocolError(StateStoreError)`
- Produces: `BrokerTransportError(StateStoreError)`
- Produces: `BROKER_THREAD_TOOL_METHODS: tuple[str, ...]`
- Produces: `broker_request(config: BrokerConfig, path: str, payload: Mapping[str, Any] | None = None, *, method: str = "POST") -> dict[str, Any]`

- [ ] **Step 1: Add fake broker test helpers**

Add imports to `tests/test_team_router.py`:

```python
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
```

Add near `FakeThreadAdapter`:

```python
class _FakeBrokerHandler(BaseHTTPRequestHandler):
    routes = {}
    calls = []

    def log_message(self, format, *args):
        return

    def _write_json(self, status, response):
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body)
        self.__class__.calls.append({"method": "POST", "path": self.path, "payload": payload})
        status, response = self.__class__.routes.get(self.path, (404, {"ok": False, "error": {"message": self.path}}))
        self._write_json(status, response)

    def do_GET(self):
        self.__class__.calls.append({"method": "GET", "path": self.path, "payload": None})
        status, response = self.__class__.routes.get(self.path, (404, {"ok": False, "error": {"message": self.path}}))
        self._write_json(status, response)


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
        server.server_close()
        thread.join(timeout=2)
```

- [ ] **Step 2: Add failing client tests**

Add new class:

```python
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
        self.assertEqual(calls[0]["path"], "/thread-tools/list_projects")
        self.assertEqual(calls[0]["payload"]["sessionToken"], "session-123")
        self.assertIn("requestId", calls[0]["payload"])

    def test_broker_request_rejects_non_localhost_base_url(self):
        import team_router_broker_adapter

        config = team_router_broker_adapter.BrokerConfig(
            base_url="https://example.com:443",
            session_token="session-123",
        )
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router_broker_adapter.broker_request(config, "/thread-tools/list_projects", {})

        self.assertIn("localhost broker", str(ctx.exception))

    def test_broker_request_rejects_unknown_thread_tool_path(self):
        import team_router_broker_adapter

        with fake_broker({}) as (base_url, _calls):
            config = team_router_broker_adapter.BrokerConfig(base_url=base_url, session_token="session-123")
            with self.assertRaises(team_router.StateStoreError) as ctx:
                team_router_broker_adapter.broker_request(config, "/thread-tools/delete_thread", {})

        self.assertIn("broker method not allowed", str(ctx.exception))
```

- [ ] **Step 3: Run RED**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_request_posts_json_with_session_token_and_request_id tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_request_rejects_non_localhost_base_url tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_request_rejects_unknown_thread_tool_path -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'team_router_broker_adapter'`.

- [ ] **Step 4: Implement module**

Create `src/team_router_broker_adapter.py`:

```python
# -*- coding: utf-8 -*-
"""Localhost RPC adapter boundary for future Codex Desktop broker integration."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from team_router_state import StateStoreError

BROKER_THREAD_TOOL_METHODS = (
    "list_projects",
    "create_thread",
    "list_threads",
    "read_thread",
    "send_message_to_thread",
    "set_thread_title",
)
BROKER_ALLOWED_PATHS = tuple("/thread-tools/%s" % name for name in BROKER_THREAD_TOOL_METHODS)


class BrokerProtocolError(StateStoreError):
    """Broker responded, but violated Team Router broker contract."""


class BrokerTransportError(StateStoreError):
    """Broker could not be reached or returned HTTP failure."""


@dataclass(frozen=True)
class BrokerConfig:
    base_url: str
    session_token: str
    timeout_ms: int = 10000
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")


def _base_url(config: BrokerConfig) -> str:
    parsed = urlparse(config.base_url)
    if parsed.scheme not in {"http", "https"}:
        raise BrokerProtocolError("localhost broker URL must use http or https")
    if parsed.hostname not in config.allowed_hosts:
        raise BrokerProtocolError("localhost broker URL must target 127.0.0.1 or localhost")
    return config.base_url.rstrip("/")


def _validate_path(path: str) -> None:
    if path not in BROKER_ALLOWED_PATHS:
        raise BrokerProtocolError("broker method not allowed: %s" % path)


def _decode_response(raw: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerProtocolError("broker response must be JSON") from exc
    if not isinstance(decoded, dict):
        raise BrokerProtocolError("broker response must be a JSON object")
    return decoded


def broker_request(config: BrokerConfig,
                   path: str,
                   payload: Mapping[str, Any] | None = None,
                   *,
                   method: str = "POST") -> dict[str, Any]:
    _validate_path(path)
    url = _base_url(config) + path
    request_payload = dict(payload or {})
    request_payload.setdefault("requestId", str(uuid4()))
    request_payload.setdefault("sessionToken", config.session_token)
    request_payload.setdefault("timeoutMs", config.timeout_ms)
    timeout_seconds = max(config.timeout_ms, 1) / 1000
    if method == "GET":
        request = Request(url, method="GET")
    elif method == "POST":
        encoded = json.dumps(request_payload).encode("utf-8")
        request = Request(url, data=encoded, method="POST", headers={"Content-Type": "application/json"})
    else:
        raise BrokerProtocolError("broker HTTP method not allowed: %s" % method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read()
    except HTTPError as exc:
        raise BrokerTransportError("broker HTTP error: %s" % exc.code) from exc
    except URLError as exc:
        raise BrokerTransportError("broker transport error: %s" % exc.reason) from exc
    decoded = _decode_response(response_body)
    if decoded.get("ok") is False:
        error = decoded.get("error") if isinstance(decoded.get("error"), Mapping) else {}
        message = error.get("message") if isinstance(error.get("message"), str) else "broker returned error"
        raise BrokerProtocolError(message)
    result = decoded.get("result", decoded)
    if not isinstance(result, dict):
        raise BrokerProtocolError("broker result must be a JSON object")
    return dict(result)
```

- [ ] **Step 5: Run GREEN**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_request_posts_json_with_session_token_and_request_id tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_request_rejects_non_localhost_base_url tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_request_rejects_unknown_thread_tool_path -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\team_router_broker_adapter.py tests\test_team_router.py
git commit -m "feat: add host broker rpc client"
```

---

### Task 2: Expose CodexAppThreadAdapter Against Fake Broker

**Files:**
- Modify: `src/team_router_broker_adapter.py`
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `BrokerConfig`, `broker_request(...)`
- Produces: `class CodexAppThreadAdapter`
- Produces callable methods: `list_projects`, `create_thread`, `list_threads`, `read_thread`, `send_message_to_thread`, `set_thread_title`
- Produces facade export: `team_router.CodexAppThreadAdapter`

- [ ] **Step 1: Write failing adapter tests**

Add to `TestTeamRouterBrokerAdapter`:

```python
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
```

- [ ] **Step 2: Run RED**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_codex_app_thread_adapter_exposes_required_callable_tools tests.test_team_router.TestTeamRouterBrokerAdapter.test_codex_app_thread_adapter_is_usable_by_runtime_capability_probe -v
```

Expected: FAIL with `AttributeError: module 'team_router_broker_adapter' has no attribute 'CodexAppThreadAdapter'`.

- [ ] **Step 3: Implement adapter**

Append to `src/team_router_broker_adapter.py`:

```python
class CodexAppThreadAdapter:
    """Python-callable adapter backed by a localhost Codex Desktop/plugin broker."""

    def __init__(self, config: BrokerConfig):
        self.config = config

    def _thread_tool(self, method_name: str, **kwargs: Any) -> dict[str, Any]:
        if method_name not in BROKER_THREAD_TOOL_METHODS:
            raise BrokerProtocolError("broker method not allowed: %s" % method_name)
        return broker_request(self.config, "/thread-tools/%s" % method_name, kwargs)

    def list_projects(self, **kwargs: Any) -> dict[str, Any]:
        return self._thread_tool("list_projects", **kwargs)

    def create_thread(self, **kwargs: Any) -> dict[str, Any]:
        return self._thread_tool("create_thread", **kwargs)

    def list_threads(self, **kwargs: Any) -> dict[str, Any]:
        return self._thread_tool("list_threads", **kwargs)

    def read_thread(self, **kwargs: Any) -> dict[str, Any]:
        return self._thread_tool("read_thread", **kwargs)

    def send_message_to_thread(self, **kwargs: Any) -> dict[str, Any]:
        return self._thread_tool("send_message_to_thread", **kwargs)

    def set_thread_title(self, **kwargs: Any) -> dict[str, Any]:
        return self._thread_tool("set_thread_title", **kwargs)
```

- [ ] **Step 4: Re-export through facade**

In `src/team_router.py`, add near extracted runtime imports:

```python
from team_router_broker_adapter import (
    BrokerConfig,
    BrokerProtocolError,
    BrokerTransportError,
    CodexAppThreadAdapter,
)
```

Add to `TestTeamRouterProtocol`:

```python
    def test_facade_reexports_broker_adapter_symbols(self):
        import team_router_broker_adapter

        for name in (
            "BrokerConfig",
            "BrokerProtocolError",
            "BrokerTransportError",
            "CodexAppThreadAdapter",
        ):
            self.assertIs(getattr(team_router, name), getattr(team_router_broker_adapter, name))
```

- [ ] **Step 5: Run GREEN**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_codex_app_thread_adapter_exposes_required_callable_tools tests.test_team_router.TestTeamRouterBrokerAdapter.test_codex_app_thread_adapter_is_usable_by_runtime_capability_probe tests.test_team_router.TestTeamRouterProtocol.test_facade_reexports_broker_adapter_symbols -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\team_router_broker_adapter.py src\team_router.py tests\test_team_router.py
git commit -m "feat: expose codex app broker thread adapter"
```

---

### Task 3: Normalize Broker Readiness Into Host Context Evidence

**Files:**
- Modify: `src/team_router_broker_adapter.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `BrokerConfig`, `CodexAppThreadAdapter`, `broker_request(...)`
- Produces: `fetch_broker_readiness(config: BrokerConfig) -> dict[str, Any]`
- Produces: `broker_host_context_kwargs(config: BrokerConfig) -> dict[str, Any]`

- [ ] **Step 1: Write failing readiness tests**

Add to `TestTeamRouterBrokerAdapter`:

```python
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
        self.assertEqual(kwargs["parent_thread_id"], "thread-parent")
        self.assertEqual(kwargs["codex_project_id"], "project-1")

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
```

- [ ] **Step 2: Run RED**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_fetch_broker_readiness_requires_runtime_probe_ready tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_returns_adapter_parent_and_project tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_blocks_without_ready_runtime_probe -v
```

Expected: FAIL: missing readiness helpers.

- [ ] **Step 3: Implement readiness helpers**

Extend `BROKER_ALLOWED_PATHS` in `src/team_router_broker_adapter.py` to include readiness before adding helpers:

```python
BROKER_ALLOWED_PATHS = tuple("/thread-tools/%s" % name for name in BROKER_THREAD_TOOL_METHODS) + (
    "/readiness",
)
```

Append to `src/team_router_broker_adapter.py`:

```python

def _runtime_probe_ready(readiness: Mapping[str, Any]) -> bool:
    probe = readiness.get("runtimeProbe")
    if not isinstance(probe, Mapping):
        return False
    missing = probe.get("missing")
    return probe.get("status") == "ready" and isinstance(missing, list) and not missing


def fetch_broker_readiness(config: BrokerConfig) -> dict[str, Any]:
    readiness = broker_request(config, "/readiness", method="GET")
    if not isinstance(readiness.get("runtimeProbe"), Mapping):
        raise BrokerProtocolError("broker readiness requires runtimeProbe")
    return readiness


def broker_host_context_kwargs(config: BrokerConfig) -> dict[str, Any]:
    readiness = fetch_broker_readiness(config)
    if readiness.get("status") != "ready":
        raise BrokerProtocolError("broker readiness is not ready: %s" % readiness.get("missing", []))
    if not _runtime_probe_ready(readiness):
        raise BrokerProtocolError("broker readiness runtimeProbe is not ready")
    parent_thread_id = readiness.get("parentThreadId")
    if not isinstance(parent_thread_id, str) or not parent_thread_id.strip():
        raise BrokerProtocolError("broker readiness requires parentThreadId")
    project_id = readiness.get("projectId")
    return {
        "thread_adapter": CodexAppThreadAdapter(config),
        "parent_thread_id": parent_thread_id.strip(),
        "codex_project_id": project_id if isinstance(project_id, str) and project_id.strip() else None,
        "readiness": readiness,
    }
```

- [ ] **Step 4: Run GREEN**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_fetch_broker_readiness_requires_runtime_probe_ready tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_returns_adapter_parent_and_project tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_blocks_without_ready_runtime_probe -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\team_router_broker_adapter.py tests\test_team_router.py
git commit -m "feat: normalize broker readiness evidence"
```

---

### Task 4: Lock Scheduler Wake Contract Without A Daemon

**Files:**
- Modify: `src/team_router_broker_adapter.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `BrokerConfig`, `broker_request(...)`
- Consumes: `team_router.materialize_watcher_call_kwargs(payload, *, thread_adapter, observed_at=None, heartbeat_scheduler=None, turn_limit=None)`
- Produces: `class BrokerHeartbeatScheduler`
- Produces: tests proving callback allowlist and materialization path.

- [ ] **Step 1: Write scheduler allowlist tests**

Add to `TestTeamRouterBrokerAdapter`:

```python
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
```

- [ ] **Step 2: Write materialization integration test**

Add to `TestTeamRouterBrokerAdapter`:

```python
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
```

- [ ] **Step 3: Run RED scheduler tests**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_heartbeat_scheduler_posts_only_allowed_watcher_callback tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_heartbeat_scheduler_rejects_arbitrary_callback tests.test_team_router.TestTeamRouterBrokerAdapter.test_scheduler_payload_materializes_with_broker_scheduler -v
```

Expected: FAIL because `BrokerHeartbeatScheduler` does not exist yet.

- [ ] **Step 4: Implement scheduler wrapper**

Extend `BROKER_ALLOWED_PATHS` and add the scheduler callback allowlist in `src/team_router_broker_adapter.py` before adding the scheduler wrapper:

```python
BROKER_ALLOWED_PATHS = tuple("/thread-tools/%s" % name for name in BROKER_THREAD_TOOL_METHODS) + (
    "/readiness",
    "/scheduler/wake",
)
BROKER_SCHEDULER_CALLBACKS = ("watch_team_task_with_adapter",)
```

Append to `src/team_router_broker_adapter.py`:

```python
class BrokerHeartbeatScheduler:
    """Callable heartbeat scheduler facade backed by broker /scheduler/wake."""

    def __init__(self, config: BrokerConfig):
        self.config = config

    def schedule(self, **kwargs: Any) -> dict[str, Any]:
        callback = kwargs.get("callback") or kwargs.get("managerAction")
        if callback not in BROKER_SCHEDULER_CALLBACKS:
            raise BrokerProtocolError("scheduler callback not allowed: %s" % callback)
        return broker_request(self.config, "/scheduler/wake", kwargs)
```

- [ ] **Step 5: Run GREEN scheduler tests**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_heartbeat_scheduler_posts_only_allowed_watcher_callback tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_heartbeat_scheduler_rejects_arbitrary_callback tests.test_team_router.TestTeamRouterBrokerAdapter.test_scheduler_payload_materializes_with_broker_scheduler -v
```

Expected: PASS.

- [ ] **Step 6: Run cadence regression tests**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_waiting_read_discipline_moves_next_allowed_after_single_first_check tests.test_team_router.TestTeamRouterState.test_role_read_interval_uses_five_minute_minimum tests.test_team_router.TestTeamRouterState.test_watcher_runtime_builds_facade_watcher_ledger -v
```

Expected: PASS. Do not change cadence constants.

- [ ] **Step 7: Commit**

```powershell
git add src\team_router_broker_adapter.py tests\test_team_router.py
git commit -m "test: lock broker scheduler wake contract"
```

---

### Task 5: Add Read-Only Broker Feasibility Check Script

**Files:**
- Create: `scripts/team_router_broker_feasibility_check.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `BrokerConfig`, `fetch_broker_readiness(config)`
- Produces CLI: `py -B scripts\team_router_broker_feasibility_check.py --broker-url <url> --session-token <token> --json`
- Produces blocked output when broker URL/token absent.

- [ ] **Step 1: Write CLI tests**

Add a new class near `TestTeamRouterBrokerAdapter`:

```python
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
```

- [ ] **Step 2: Run RED**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerFeasibilityScript.test_broker_feasibility_check_blocks_without_broker_arguments tests.test_team_router.TestTeamRouterBrokerFeasibilityScript.test_broker_feasibility_check_reports_ready_readiness -v
```

Expected: FAIL because script missing.

- [ ] **Step 3: Implement script**

Create `scripts/team_router_broker_feasibility_check.py`:

```python
# -*- coding: utf-8 -*-
"""Read-only feasibility check for a Team Router Codex Desktop broker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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
    parser.add_argument("--json", action="store_true")
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
```

- [ ] **Step 4: Run GREEN**

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterBrokerFeasibilityScript.test_broker_feasibility_check_blocks_without_broker_arguments tests.test_team_router.TestTeamRouterBrokerFeasibilityScript.test_broker_feasibility_check_reports_ready_readiness -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts\team_router_broker_feasibility_check.py tests\test_team_router.py
git commit -m "test: add broker feasibility check"
```

---

### Task 6: Full Repo-Local Verification And Blocker Closeout

**Files:**
- Modify only if needed: `docs/team-router/module-map.md`
- Create only if real external broker evidence exists: `docs/team-router/packages/ctr-20260701-host-rpc-broker-feasibility.md`

**Interfaces:**
- Consumes: all previous task changes
- Produces: verified repo-local broker adapter contract package
- Produces: no claim of real Desktop/plugin automatic orchestration unless external broker evidence exists

- [ ] **Step 1: Run compile check**

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-rpc-broker'; $env:TMP='C:\tmp'; $env:TEMP='C:\tmp'; py -B -m py_compile src\team_router.py src\team_router_broker_adapter.py src\team_router_host_runtime.py src\team_router_runtime.py src\team_router_watcher_runtime.py scripts\team_router_broker_feasibility_check.py tests\test_team_router.py
```

Expected: exit 0.

- [ ] **Step 2: Run broker-focused tests**

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-rpc-broker'; $env:TMP='C:\tmp'; $env:TEMP='C:\tmp'; py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter tests.test_team_router.TestTeamRouterBrokerFeasibilityScript -v
```

Expected: all broker adapter and feasibility script tests PASS.

- [ ] **Step 3: Run scheduler and readiness regression tests**

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-rpc-broker'; $env:TMP='C:\tmp'; $env:TEMP='C:\tmp'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_requires_runtime_probe_for_adapter_smoke_ready tests.test_team_router.TestTeamRouterState.test_waiting_read_discipline_moves_next_allowed_after_single_first_check tests.test_team_router.TestTeamRouterState.test_role_read_interval_uses_five_minute_minimum tests.test_team_router.TestTeamRouterState.test_watcher_runtime_builds_facade_watcher_ledger -v
```

Expected: PASS.

- [ ] **Step 4: Run full Team Router test file**

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-rpc-broker'; $env:TMP='C:\tmp'; $env:TEMP='C:\tmp'; py -B -m unittest discover -s tests -p test_team_router.py -v
```

Expected: full suite PASS.

- [ ] **Step 5: Run truth, doctor, and default feasibility checks**

```powershell
py -B scripts\team_router_truth_check.py --json
py -B scripts\team_router_doctor.py --json
py -B scripts\team_router_broker_feasibility_check.py --json
```

Expected:

```text
team_router_truth_check.py exit 0
team_router_doctor.py exit 0
team_router_broker_feasibility_check.py exit 2 by design when broker arguments are absent
truth_check staleClaims: []
doctor without host readiness snapshot: orchestrationStatus manual_only, hostReadiness.status not_supplied
broker feasibility without broker arguments: status blocked, missing broker-url/session-token, no Desktop/plugin mutation authorization
```

- [ ] **Step 6: Run whitespace and status checks**

```powershell
git diff --check
git status -sb --untracked-files=all
```

Expected: whitespace check exit 0. Status shows only intentional files changed by this implementation package before final commit.

- [ ] **Step 7: Commit final docs only if changed**

If Task 6 changes docs, run:

```powershell
git add docs\team-router\module-map.md docs\team-router\packages\ctr-20260701-host-rpc-broker-feasibility.md
git commit -m "docs: record host rpc broker feasibility"
```

If no files changed in Task 6, skip commit and record `no commit` in closeout.

## Self-Review Notes

Spec coverage:

- Desktop/plugin authority domain required: Task 5 feasibility check and Task 6 blocker closeout.
- Localhost RPC broker preferred bridge: Tasks 1-3.
- Exact RPC request/response shape: Tasks 1-3 tests; Task 1 is thread-tools only, Task 3 adds readiness, Task 4 adds scheduler wake.
- Parent thread id lifecycle and invalidation: Task 3 readiness and host context kwargs; external lifecycle remains Desktop/plugin feasibility requirement.
- Scheduler responsibilities without daemon: Task 4.
- Readiness JSON including `runtimeProbe`: Task 3 and Task 6.
- Security controls: Task 1 localhost restriction and method allowlist, Task 4 callback allowlist, Task 5 read-only authorization report.
- No live automatic orchestration claim: Task 5 default blocked feasibility and Task 6 doctor/truth checks.

Known boundary:

- This plan cannot prove Desktop/plugin can call Codex app tools. It prepares repo-local adapter contracts and a read-only feasibility checker only. Real broker authority must be proven outside this repo before any automatic orchestration claim.

Type consistency:

- `BrokerConfig`, `CodexAppThreadAdapter`, `fetch_broker_readiness`, and `broker_host_context_kwargs` are introduced before readiness tasks use them; `BrokerHeartbeatScheduler` is introduced in Task 4 before scheduler checks use it.
- `watch_team_task_with_adapter` is the only scheduler callback allowed.
- Thread tool names match existing `THREAD_TOOL_NAMES`.

## Execution Choice

Plan complete. Execute later with one of two modes:

1. Subagent-Driven: fresh worker per task, review between tasks.
2. Inline Execution: execute tasks in this session with checkpoints.
