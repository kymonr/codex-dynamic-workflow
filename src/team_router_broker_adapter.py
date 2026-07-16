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
BROKER_CORE_THREAD_TOOL_METHODS = tuple(
    method_name for method_name in BROKER_THREAD_TOOL_METHODS
    if method_name != "set_thread_title"
)
BROKER_ALLOWED_PATHS = tuple("/thread-tools/%s" % name for name in BROKER_THREAD_TOOL_METHODS) + (
    "/readiness",
    "/scheduler/wake",
)
BROKER_SCHEDULER_CALLBACKS = ("watch_team_task_with_adapter",)
BROKER_ALLOWED_HOSTS = ("127.0.0.1", "localhost")


class BrokerProtocolError(StateStoreError):
    """Broker responded, but violated Team Router broker contract."""


class BrokerTransportError(StateStoreError):
    """Broker could not be reached or returned HTTP failure."""


@dataclass(frozen=True)
class BrokerConfig:
    base_url: str
    session_token: str
    timeout_ms: int = 10000
    allowed_hosts: tuple[str, ...] = BROKER_ALLOWED_HOSTS


def _base_url(config: BrokerConfig) -> str:
    if not isinstance(config.base_url, str) or not config.base_url.strip():
        raise BrokerProtocolError("localhost broker URL must be a non-empty string")
    parsed = urlparse(config.base_url)
    if parsed.scheme not in {"http", "https"}:
        raise BrokerProtocolError("localhost broker URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise BrokerProtocolError("localhost broker URL must not contain user info")
    if parsed.hostname not in BROKER_ALLOWED_HOSTS:
        raise BrokerProtocolError("localhost broker URL must target 127.0.0.1 or localhost")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise BrokerProtocolError("localhost broker URL must not contain path, query, or fragment")
    try:
        parsed.port
    except ValueError as exc:
        raise BrokerProtocolError("localhost broker URL has invalid port") from exc
    return config.base_url.rstrip("/")


def validate_broker_config(config: BrokerConfig) -> None:
    if not isinstance(config.session_token, str) or not config.session_token.strip():
        raise BrokerProtocolError("broker session token must be non-empty")
    if isinstance(config.timeout_ms, bool) or not isinstance(config.timeout_ms, int) or config.timeout_ms <= 0:
        raise BrokerProtocolError("broker timeout_ms must be a positive integer")
    _base_url(config)


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


def _sanitize_broker_value(value: Any, session_token: str) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).replace("_", "").replace("-", "").lower()
            if any(term in normalized_key for term in ("token", "secret", "password", "cookie", "authorization")):
                continue
            sanitized[str(key)] = _sanitize_broker_value(item, session_token)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_broker_value(item, session_token) for item in value]
    if isinstance(value, str):
        return _redact_session_token(value, session_token)
    return value


def _redact_session_token(text: str, session_token: str) -> str:
    return text.replace(session_token, "[redacted]") if session_token else text


def broker_request(
    config: BrokerConfig,
    path: str,
    payload: Mapping[str, Any] | None = None,
    *,
    method: str = "POST",
) -> dict[str, Any]:
    _validate_path(path)
    validate_broker_config(config)
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
        request = Request(
            url,
            method="GET",
            headers={
                "X-Request-Id": str(request_payload["requestId"]),
                "X-Session-Token": str(request_payload["sessionToken"]),
                "X-Timeout-Ms": str(request_payload["timeoutMs"]),
            },
        )
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
        reason = _redact_session_token(str(exc.reason), config.session_token)
        raise BrokerTransportError("broker transport error: %s" % reason) from exc
    decoded = _decode_response(response_body)
    response_request_id = decoded.get("requestId")
    if response_request_id is None and isinstance(decoded.get("result"), Mapping):
        response_request_id = decoded["result"].get("requestId")
    if response_request_id is not None and str(response_request_id) != str(request_payload["requestId"]):
        raise BrokerProtocolError("broker response requestId mismatch")
    if decoded.get("ok") is False:
        error = decoded.get("error") if isinstance(decoded.get("error"), Mapping) else {}
        message = error.get("message") if isinstance(error.get("message"), str) else "broker returned error"
        raise BrokerProtocolError(_redact_session_token(message, config.session_token))
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


def _broker_identity_evidence(readiness: Mapping[str, Any]) -> dict[str, bool]:
    capabilities = _mapping_or_empty(readiness.get("capabilities"))
    return {
        "trustedSenderProvenance": (
            readiness.get("trustedSenderProvenance") is True
            or capabilities.get("trusted_sender_provenance") is True
        ),
        "trustedExecutionDomain": (
            readiness.get("trustedExecutionDomain") is True
            or capabilities.get("trusted_execution_domain") is True
        ),
    }


def fetch_broker_readiness(config: BrokerConfig) -> dict[str, Any]:
    readiness = _sanitize_broker_value(
        broker_request(config, "/readiness", method="GET"),
        config.session_token,
    )
    if not isinstance(readiness.get("runtimeProbe"), Mapping):
        raise BrokerProtocolError("broker readiness requires runtimeProbe")
    return readiness



def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def broker_host_readiness_snapshot(readiness: Mapping[str, Any]) -> dict[str, Any]:
    """Map broker /readiness evidence into scripts/team_router_doctor.py snapshot shape."""
    capabilities = _mapping_or_empty(readiness.get("capabilities"))
    callable_tools = {
        method_name: capabilities.get(method_name) is True
        for method_name in BROKER_THREAD_TOOL_METHODS
    }
    runtime_probe = readiness.get("runtimeProbe")
    if not isinstance(runtime_probe, Mapping):
        runtime_probe = {"status": "blocked", "missing": ["runtime readiness probe"]}
    broker_missing = _list_or_empty(readiness.get("missing"))
    broker_ready = readiness.get("status") == "ready" and readiness.get("brokerReady") is True and not broker_missing
    if not broker_ready:
        probe_missing = _list_or_empty(runtime_probe.get("missing"))
        if "broker readiness" not in probe_missing:
            probe_missing.append("broker readiness")
        runtime_probe = {"status": "blocked", "missing": probe_missing}
    parent_thread_id = readiness.get("parentThreadId")
    scheduler_ready = broker_ready and (
        readiness.get("schedulerReady") is True
        or capabilities.get("heartbeat_scheduler") is True
    )
    return {
        "source": "broker-readiness",
        "brokerReady": broker_ready,
        "brokerStatus": readiness.get("status"),
        "brokerMissing": broker_missing,
        "projectId": readiness.get("projectId") if isinstance(readiness.get("projectId"), str) else None,
        "codexAppThreadToolsExposed": readiness.get("toolSmokeReady") is True or any(callable_tools.values()),
        "adapterCallable": True,
        "callableTools": callable_tools,
        "parentThreadId": parent_thread_id.strip() if isinstance(parent_thread_id, str) else "",
        "heartbeatSchedulerCallable": scheduler_ready,
        **_broker_identity_evidence(readiness),
        "runtimeProbe": dict(runtime_probe),
    }

def broker_host_context_kwargs(config: BrokerConfig) -> dict[str, Any]:
    readiness = fetch_broker_readiness(config)
    if readiness.get("status") != "ready":
        raise BrokerProtocolError("broker readiness is not ready: %s" % readiness.get("missing", []))
    if not _runtime_probe_ready(readiness):
        raise BrokerProtocolError("broker readiness runtimeProbe is not ready")
    identity_evidence = _broker_identity_evidence(readiness)
    if not all(identity_evidence.values()):
        raise BrokerProtocolError("broker readiness lacks trusted sender/domain evidence")
    parent_thread_id = readiness.get("parentThreadId")
    if not isinstance(parent_thread_id, str) or not parent_thread_id.strip():
        raise BrokerProtocolError("broker readiness requires parentThreadId")
    host_snapshot = broker_host_readiness_snapshot(readiness)
    if host_snapshot.get("brokerReady") is not True:
        raise BrokerProtocolError("broker readiness is not ready")
    callable_tools = _mapping_or_empty(host_snapshot.get("callableTools"))
    missing_core_tools = [
        method_name for method_name in BROKER_CORE_THREAD_TOOL_METHODS
        if callable_tools.get(method_name) is not True
    ]
    if missing_core_tools:
        raise BrokerProtocolError(
            "broker readiness lacks "
            + ", ".join("callable %s" % method_name for method_name in missing_core_tools)
        )
    scheduler = (
        BrokerHeartbeatScheduler(config)
        if host_snapshot.get("heartbeatSchedulerCallable") is True
        else None
    )
    project_id = readiness.get("projectId")
    return {
        "thread_adapter": CodexAppThreadAdapter(config, identity_evidence=identity_evidence),
        "heartbeat_scheduler": scheduler,
        "parent_thread_id": parent_thread_id.strip(),
        "codex_project_id": project_id if isinstance(project_id, str) and project_id.strip() else None,
        "readiness": readiness,
        "host_readiness_snapshot": host_snapshot,
    }


class BrokerHeartbeatScheduler:
    """Callable heartbeat scheduler facade backed by broker /scheduler/wake."""

    def __init__(self, config: BrokerConfig):
        self.config = config

    def schedule(self, **kwargs: Any) -> dict[str, Any]:
        return broker_request(self.config, "/scheduler/wake", kwargs)


class CodexAppThreadAdapter:
    """Python-callable adapter backed by a localhost Codex Desktop/plugin broker."""

    def __init__(self, config: BrokerConfig,
                 identity_evidence: Mapping[str, Any] | None = None):
        self.config = config
        self.team_router_identity_evidence = dict(identity_evidence or {})

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
