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