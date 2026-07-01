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
BROKER_ALLOWED_PATHS = tuple("/thread-tools/%s" % name for name in BROKER_THREAD_TOOL_METHODS) + (
    "/readiness",
    "/scheduler/wake",
)
BROKER_SCHEDULER_CALLBACKS = ("watch_team_task_with_adapter",)


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


def _validate_scheduler_payload(payload: Mapping[str, Any]) -> None:
    callbacks = [payload.get(name) for name in ("callback", "managerAction") if payload.get(name) is not None]
    if not callbacks:
        raise BrokerProtocolError("scheduler callback not allowed: None")
    for callback in callbacks:
        if callback not in BROKER_SCHEDULER_CALLBACKS:
            raise BrokerProtocolError("scheduler callback not allowed: %s" % callback)


def _decode_response(raw: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerProtocolError("broker response must be JSON") from exc
    if not isinstance(decoded, dict):
        raise BrokerProtocolError("broker response must be a JSON object")
    return decoded


def broker_request(
    config: BrokerConfig,
    path: str,
    payload: Mapping[str, Any] | None = None,
    *,
    method: str = "POST",
) -> dict[str, Any]:
    _validate_path(path)
    url = _base_url(config) + path
    request_payload = dict(payload or {})
    if path == "/scheduler/wake":
        _validate_scheduler_payload(request_payload)
    request_payload.setdefault("requestId", str(uuid4()))
    request_payload.setdefault("sessionToken", config.session_token)
    request_payload.setdefault("timeoutMs", config.timeout_ms)
    timeout_seconds = max(config.timeout_ms, 1) / 1000
    if method == "GET":
        if path != "/readiness":
            raise BrokerProtocolError("broker HTTP method not allowed for %s: %s" % (path, method))
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
        exc.close()
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
        "heartbeat_scheduler": BrokerHeartbeatScheduler(config),
        "parent_thread_id": parent_thread_id.strip(),
        "codex_project_id": project_id if isinstance(project_id, str) and project_id.strip() else None,
        "readiness": readiness,
    }


class BrokerHeartbeatScheduler:
    """Callable heartbeat scheduler facade backed by broker /scheduler/wake."""

    def __init__(self, config: BrokerConfig):
        self.config = config

    def schedule(self, **kwargs: Any) -> dict[str, Any]:
        return broker_request(self.config, "/scheduler/wake", kwargs)


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
