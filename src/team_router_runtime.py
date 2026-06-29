# -*- coding: utf-8 -*-
"""Thread-adapter and read-normalization runtime helpers for Team Router."""
from __future__ import annotations

import html
import re
from typing import Any, Mapping

from team_router_state import StateStoreError, _required_str


CODEX_DELEGATION_RE = re.compile(
    r"<codex_delegation>\s*"
    r"<source_thread_id>(?P<source>.*?)</source_thread_id>\s*"
    r"<input>(?P<input>.*?)</input>\s*"
    r"</codex_delegation>",
    re.DOTALL,
)


def _adapter_method(thread_adapter: Any, method_name: str) -> Any:
    if isinstance(thread_adapter, Mapping):
        return thread_adapter.get(method_name)
    return getattr(thread_adapter, method_name, None)


def _adapter_call(thread_adapter: Any, method_name: str, **kwargs: Any) -> Any:
    method = _adapter_method(thread_adapter, method_name)
    if not callable(method):
        raise StateStoreError("thread adapter missing callable: %s" % method_name)
    return method(**kwargs)


def _optional_adapter_call(thread_adapter: Any, method_name: str, **kwargs: Any) -> Any:
    method = _adapter_method(thread_adapter, method_name)
    if not callable(method):
        return None
    return method(**kwargs)


def _optional_nonempty_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _first_str(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _optional_nonempty_str(mapping.get(key))
        if value is not None:
            return value
    return None


def _optional_timestamp_value(value: Any) -> str | int | float | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _first_timestamp(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str | int | float | None:
    for key in keys:
        value = _optional_timestamp_value(mapping.get(key))
        if value is not None:
            return value
    return None


def _candidate_mappings(result: Any) -> list[Mapping[str, Any]]:
    if not isinstance(result, Mapping):
        return []
    candidates: list[Mapping[str, Any]] = [result]
    for key in ("message", "data", "result", "thread"):
        nested = result.get(key)
        if isinstance(nested, Mapping):
            candidates.append(nested)
    return candidates


def thread_send_anchor(send_result: Any, *, fallback_sent_at: str) -> dict[str, Any]:
    sent_at_fallback = _required_str(fallback_sent_at, "fallbackSentAt")
    message_id: str | None = None
    sent_at: str | None = None
    for candidate in _candidate_mappings(send_result):
        if message_id is None:
            message_id = _first_str(candidate, ("messageId", "message_id", "id"))
        if sent_at is None:
            sent_at = _first_str(candidate, (
                "sentAt", "sent_at", "createdAt", "created_at", "timestamp",
            ))
    return {"messageId": message_id, "sentAt": sent_at or sent_at_fallback}


def _content_blocks_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    if isinstance(value, Mapping):
        text = value.get("text") or value.get("content")
        if isinstance(text, str):
            return text
    return ""


def _unwrap_codex_delegation_text(text: str) -> tuple[str | None, str]:
    if not isinstance(text, str):
        return None, ""
    match = CODEX_DELEGATION_RE.search(text)
    if not match:
        return None, text
    source_thread_id = match.group("source").strip() or None
    inner_text = html.unescape(match.group("input")).strip()
    return source_thread_id, inner_text


def _normalize_thread_message(message: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(message)
    message_id = _first_str(message, ("messageId", "message_id", "id", "turnId"))
    sent_at = _first_timestamp(message, (
        "sentAt", "sent_at", "createdAt", "created_at", "timestamp",
    ))
    text = _first_str(message, ("text",)) or ""
    if not text:
        for key in ("content", "output", "response"):
            text = _content_blocks_text(message.get(key))
            if text:
                break
    if not text:
        text = _first_str(message, ("summary",)) or ""
    source_thread_id = _first_str(message, ("sourceThreadId", "source_thread_id"))
    delegated_source_thread_id, delegated_text = _unwrap_codex_delegation_text(text)
    if delegated_source_thread_id is not None:
        source_thread_id = delegated_source_thread_id
        normalized["delegatedText"] = delegated_text
        text = delegated_text
    normalized["messageId"] = message_id
    if sent_at is not None:
        normalized["sentAt"] = sent_at
    if source_thread_id is not None:
        normalized["sourceThreadId"] = source_thread_id
    normalized["text"] = text
    return normalized


def _read_messages_from_mapping(read_result: Mapping[str, Any]) -> Any:
    for key in ("messages", "turns", "items"):
        value = read_result.get(key)
        if value is not None:
            return value
    for key in ("thread", "data", "result"):
        nested = read_result.get(key)
        if isinstance(nested, Mapping):
            value = _read_messages_from_mapping(nested)
            if value is not None:
                return value
    return None


def _turn_item_messages(turns: list[Any]) -> list[dict[str, Any]] | None:
    out: list[dict[str, Any]] = []
    saw_turn_items = False
    for turn_index, turn in enumerate(turns):
        if not isinstance(turn, Mapping):
            return None
        items = turn.get("items")
        if not isinstance(items, list):
            continue
        saw_turn_items = True
        turn_time = _first_timestamp(turn, (
            "sentAt", "sent_at", "createdAt", "created_at",
            "startedAt", "started_at", "timestamp",
        ))
        for item_index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise StateStoreError(
                    "read_thread turn %d item %d must be a JSON object"
                    % (turn_index, item_index)
                )
            message = dict(item)
            if turn_time is not None and _first_timestamp(message, (
                "sentAt", "sent_at", "createdAt", "created_at", "timestamp",
            )) is None:
                message["sentAt"] = turn_time
            out.append(message)
    return out if saw_turn_items else None


def normalize_thread_read_messages(read_result: Any) -> list[dict[str, Any]]:
    if isinstance(read_result, list):
        raw_messages = _turn_item_messages(read_result) or read_result
    elif isinstance(read_result, Mapping):
        raw_messages = _read_messages_from_mapping(read_result)
        if isinstance(raw_messages, list):
            raw_messages = _turn_item_messages(raw_messages) or raw_messages
    else:
        raise StateStoreError("read_thread result must be a JSON object or array")
    if not isinstance(raw_messages, list):
        raise StateStoreError("read_thread result does not contain a messages array")
    out: list[dict[str, Any]] = []
    for index, message in enumerate(raw_messages):
        if not isinstance(message, Mapping):
            raise StateStoreError("read_thread message %d must be a JSON object" % index)
        out.append(_normalize_thread_message(message))
    return out


def _thread_id_from_create_result(create_result: Any, role: str) -> str:
    for candidate in _candidate_mappings(create_result):
        thread_id = _first_str(candidate, ("threadId", "thread_id", "id"))
        if thread_id is not None:
            return thread_id
    raise StateStoreError("create_thread result missing thread id for role: %s" % role)
