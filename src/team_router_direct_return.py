# -*- coding: utf-8 -*-
"""Pure direct-return contract helpers for Team Router."""
from __future__ import annotations

from typing import Any, Mapping

from team_router_protocol import (
    ProtocolError,
    ProtocolMessage,
    _iter_marker_blocks,
    parse_callback,
    parse_message,
    parse_plan,
    parse_review,
    parse_verdict,
)


DIRECT_RETURN_MAX_UTF8_BYTES = 1200
from team_router_state import StateStoreError


def _message_text(message: Mapping[str, Any]) -> str:
    for key in ("text", "content", "summary"):
        value = message.get(key)
        if isinstance(value, str):
            return value
    return ""


def _has_strict_role_dispatch(ledger: Mapping[str, Any], role: str) -> bool:
    dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
    return any(
        isinstance(record, Mapping)
        and record.get("role") == role
        and record.get("protocolVersion") == 2
        for record in dispatches
    )


def _direct_return_record(ledger: Mapping[str, Any],
                          role: str) -> Mapping[str, Any] | None:
    if (
        role == "verifier"
        and ledger.get("workflowVersion") != 2
        and _has_strict_role_dispatch(ledger, role)
    ):
        return None
    if ledger.get("workflowVersion") == 2:
        dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
        strict_verifier_history = role == "verifier" and _has_strict_role_dispatch(ledger, role)
        for record in reversed(dispatches):
            if not isinstance(record, Mapping) or record.get("role") != role:
                continue
            if strict_verifier_history and record.get("protocolVersion") != 2:
                return None
            if not record.get("returnThreadId"):
                return None
            if not any(
                record.get(field) == "direct-send"
                for field in ("callbackDelivery", "reviewDelivery", "architectReviewDelivery", "qaReviewDelivery", "verdictDelivery")
            ):
                return None
            return record
        return None
    if role == "executor":
        dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
        record = dispatches[-1] if dispatches and isinstance(dispatches[-1], Mapping) else None
        if not isinstance(record, Mapping):
            return None
        if not record.get("returnThreadId") or record.get("callbackDelivery") != "direct-send":
            return None
        return record
    if role == "reviewer":
        review = ledger.get("review") if isinstance(ledger.get("review"), Mapping) else None
        request = review.get("request") if isinstance(review, Mapping) else None
        if not isinstance(request, Mapping):
            return None
        if not request.get("returnThreadId") or request.get("reviewDelivery") != "direct-send":
            return None
        return request
    if role == "architect":
        review = ledger.get("architectureReview") if isinstance(ledger.get("architectureReview"), Mapping) else None
        request = review.get("request") if isinstance(review, Mapping) else None
        if not isinstance(request, Mapping):
            return None
        if not request.get("returnThreadId") or request.get("architectReviewDelivery") != "direct-send":
            return None
        return request
    if role == "qa":
        review = ledger.get("qaReview") if isinstance(ledger.get("qaReview"), Mapping) else None
        request = review.get("request") if isinstance(review, Mapping) else None
        if not isinstance(request, Mapping):
            return None
        if not request.get("returnThreadId") or request.get("qaReviewDelivery") != "direct-send":
            return None
        return request
    if role == "verifier":
        verification = ledger.get("verification") if isinstance(ledger.get("verification"), Mapping) else None
        request = verification.get("request") if isinstance(verification, Mapping) else None
        if not isinstance(request, Mapping):
            return None
        if not request.get("returnThreadId") or request.get("verdictDelivery") != "direct-send":
            return None
        return request
    raise StateStoreError("invalid direct-return role: %s" % role)


def _direct_return_capture_allowed_for_status(status: str,
                                             role: str,
                                             *,
                                             needs_feedback_role: str | None = None) -> bool:
    if role == "executor":
        return status in {"awaiting_callback", "callback_unreachable"} or needs_feedback_role == "executor"
    if role == "reviewer":
        return status in {"reviewing", "review_unreachable"} or needs_feedback_role == "reviewer"
    if role == "architect":
        return status in {"awaiting_architect_review", "architect_review_unreachable"} or needs_feedback_role == "architect"
    if role == "qa":
        return status in {"awaiting_qa_review", "qa_review_unreachable"} or needs_feedback_role == "qa"
    if role == "verifier":
        return status in {"verifying", "callback_unreachable"} or needs_feedback_role == "verifier"
    raise StateStoreError("invalid direct-return role: %s" % role)


def _direct_return_candidate_messages(messages: list[Mapping[str, Any]],
                                      source_thread_id: str | None) -> list[Mapping[str, Any]]:
    if source_thread_id is None:
        return list(messages)
    out: list[Mapping[str, Any]] = []
    for message in messages:
        if message.get("sourceThreadId") != source_thread_id:
            continue
        out.append(message)
    return out


def _direct_return_protocol_message(messages: list[Mapping[str, Any]],
                                    *,
                                    marker: str,
                                    task_id: str,
                                    source_thread_id: str | None) -> tuple[ProtocolMessage | None, dict[str, Any] | None, Mapping[str, Any] | None]:
    candidates = _direct_return_candidate_messages(messages, source_thread_id)
    last_message = candidates[-1] if candidates and isinstance(candidates[-1], Mapping) else None
    for message in reversed(candidates):
        text = _message_text(message)
        if not text:
            continue
        try:
            marker_blocks = [block for block in _iter_marker_blocks(text) if block.marker == marker]
        except ProtocolError as exc:
            malformed = {
                "messageId": message.get("messageId") if isinstance(message, Mapping) else None,
                "sentAt": message.get("sentAt") if isinstance(message, Mapping) else None,
                "sourceThreadId": message.get("sourceThreadId") if isinstance(message, Mapping) else None,
                "error": str(exc),
            }
            return None, malformed, message
        if not marker_blocks:
            continue
        if len(marker_blocks) > 1:
            malformed = {
                "messageId": message.get("messageId") if isinstance(message, Mapping) else None,
                "sentAt": message.get("sentAt") if isinstance(message, Mapping) else None,
                "sourceThreadId": message.get("sourceThreadId") if isinstance(message, Mapping) else None,
                "error": "%s has multiple final markers in one message" % marker,
            }
            return None, malformed, message
        marker_block = marker_blocks[-1]
        if marker_block.task_id != task_id:
            malformed = {
                "messageId": message.get("messageId") if isinstance(message, Mapping) else None,
                "sentAt": message.get("sentAt") if isinstance(message, Mapping) else None,
                "sourceThreadId": message.get("sourceThreadId") if isinstance(message, Mapping) else None,
                "error": "%s.taskId must be %r, got %r" % (marker, task_id, marker_block.task_id),
            }
            return None, malformed, message
        try:
            if marker == "TEAM_ROUTER_VERDICT":
                parsed = parse_verdict(marker_block.raw, task_id)
            elif marker == "TEAM_ROUTER_REVIEW":
                parsed = parse_review(marker_block.raw, task_id)
            elif marker == "TEAM_ROUTER_CALLBACK":
                parsed = parse_callback(marker_block.raw, task_id)
            elif marker == "TEAM_ROUTER_PLAN":
                parsed = parse_plan(marker_block.raw, task_id)
            else:
                parsed = parse_message(marker_block.raw, marker, task_id)
            return parsed, None, message
        except ProtocolError as exc:
            if str(exc).startswith("missing "):
                return None, None, message
            malformed = {
                "messageId": message.get("messageId") if isinstance(message, Mapping) else None,
                "sentAt": message.get("sentAt") if isinstance(message, Mapping) else None,
                "sourceThreadId": message.get("sourceThreadId") if isinstance(message, Mapping) else None,
                "error": str(exc),
            }
            return None, malformed, message
    return None, None, last_message


def _normalize_direct_return_role(role: Any, *, expected_role: str) -> str:
    value = str(role or expected_role).strip().lower()
    return value or expected_role


def _validate_direct_return_receipt(msg: ProtocolMessage,
                                    manager_message: Mapping[str, Any] | None,
                                    *,
                                    task_id: str,
                                    expected_role: str,
                                    expected_role_thread_id: str,
                                    expected_return_thread_id: str | None = None,
                                    expected_dispatch: Mapping[str, Any] | None = None,
                                    require_protocol_identity: bool = True,
                                    require_host_agent_message: bool = False) -> dict[str, Any] | None:
    message = manager_message if isinstance(manager_message, Mapping) else {}
    role_value = str(msg.fields.get("role") or "").strip()
    source_role_thread_id = str(msg.fields.get("sourceRoleThreadId") or "").strip()
    protocol_source_thread_id = str(msg.fields.get("sourceThreadId") or "").strip()
    host_source_thread_id = str(message.get("sourceThreadId") or "").strip()
    delegated_source_thread_id = str(message.get("delegatedSourceThreadId") or "").strip()
    expected_return = str(expected_return_thread_id or "").strip()
    errors: list[str] = []
    if len(msg.raw.encode("utf-8")) > DIRECT_RETURN_MAX_UTF8_BYTES:
        errors.append("%s result exceeds 1200 UTF-8 bytes" % msg.marker)
    if (
        host_source_thread_id
        and delegated_source_thread_id
        and host_source_thread_id != delegated_source_thread_id
    ):
        errors.append("wrapper source conflicts with Host source")
    if require_host_agent_message:
        if message.get("type") != "agentMessage":
            errors.append("Host agentMessage provenance is required")
        if not str(message.get("messageId") or "").strip():
            errors.append("Host item id is required")
        if not host_source_thread_id:
            errors.append("Host sourceThreadId is required")
        elif host_source_thread_id != expected_role_thread_id:
            errors.append(
                "Host sourceThreadId must be %r, got %r"
                % (expected_role_thread_id, host_source_thread_id)
            )
    if msg.task_id != task_id:
        errors.append("%s.taskId must be %r, got %r" % (msg.marker, task_id, msg.task_id))
    if require_protocol_identity and expected_return:
        if not protocol_source_thread_id:
            errors.append("%s.sourceThreadId is required" % msg.marker)
        elif protocol_source_thread_id != expected_return:
            errors.append(
                "%s.sourceThreadId must be %r, got %r"
                % (msg.marker, expected_return, protocol_source_thread_id)
            )
    if require_protocol_identity and not role_value:
        errors.append("%s.role is required" % msg.marker)
    elif require_protocol_identity and _normalize_direct_return_role(role_value, expected_role=expected_role) != expected_role:
        errors.append(
            "%s.role must be %r, got %r"
            % (msg.marker, expected_role, role_value)
        )
    if require_protocol_identity and not source_role_thread_id:
        errors.append("%s.sourceRoleThreadId is required" % msg.marker)
    elif require_protocol_identity and source_role_thread_id != expected_role_thread_id:
        errors.append(
            "%s.sourceRoleThreadId must be %r, got %r"
            % (msg.marker, expected_role_thread_id, source_role_thread_id)
            )
    if isinstance(expected_dispatch, Mapping) and expected_dispatch.get("protocolVersion") == 2:
        for field, expected in (
            ("protocolVersion", "2"),
            ("dispatchId", expected_dispatch.get("dispatchId")),
            ("requestId", expected_dispatch.get("requestId")),
            ("attempt", expected_dispatch.get("attempt")),
        ):
            actual = str(msg.fields.get(field) or "").strip()
            if not actual:
                errors.append("%s.%s is required" % (msg.marker, field))
            elif field == "attempt" and (not actual.isdigit() or int(actual) <= 0):
                errors.append("%s.attempt must be a positive integer" % msg.marker)
            elif str(expected) != actual:
                errors.append("%s.%s must be %r, got %r" % (msg.marker, field, expected, actual))
    elif isinstance(expected_dispatch, Mapping):
        for field in ("protocolVersion", "dispatchId", "requestId", "attempt"):
            if str(msg.fields.get(field) or "").strip():
                errors.append("%s.%s is not accepted for a legacy dispatch" % (msg.marker, field))
    if not errors:
        return None
    return {
        "messageId": message.get("messageId"),
        "sentAt": message.get("sentAt"),
        "sourceThreadId": message.get("sourceThreadId"),
        "protocolSourceThreadId": protocol_source_thread_id,
        "protocolRole": role_value,
        "protocolSourceRoleThreadId": source_role_thread_id,
        "error": "; ".join(errors),
    }


def _validate_self_thread_fallback_receipt(msg: ProtocolMessage,
                                           fallback_message: Mapping[str, Any] | None,
                                           *,
                                           task_id: str,
                                           expected_role: str,
                                           expected_role_thread_id: str,
                                           expected_return_thread_id: str | None = None,
                                           expected_dispatch: Mapping[str, Any] | None = None,
                                           require_protocol_identity: bool = True) -> dict[str, Any] | None:
    malformed = _validate_direct_return_receipt(
        msg,
        fallback_message,
        task_id=task_id,
        expected_role=expected_role,
        expected_role_thread_id=expected_role_thread_id,
        expected_return_thread_id=expected_return_thread_id,
        expected_dispatch=expected_dispatch,
        require_protocol_identity=require_protocol_identity,
    )
    message = fallback_message if isinstance(fallback_message, Mapping) else {}
    message_source_thread_id = str(message.get("sourceThreadId") or "").strip()
    fallback_errors: list[str] = []
    if message.get("type") != "agentMessage":
        fallback_errors.append("self-thread receipt requires Host agentMessage")
    if not str(message.get("messageId") or "").strip():
        fallback_errors.append("self-thread receipt Host item id is required")
    if message_source_thread_id and message_source_thread_id != expected_role_thread_id:
        fallback_errors.append(
            "message sourceThreadId must be %r, got %r"
            % (expected_role_thread_id, message_source_thread_id)
        )
    if fallback_errors:
        error = "; ".join(fallback_errors)
        if malformed is not None:
            malformed = dict(malformed)
            existing = str(malformed.get("error") or "")
            malformed["error"] = "%s; %s" % (existing, error) if existing else error
            return malformed
        return {
            "messageId": message.get("messageId"),
            "sentAt": message.get("sentAt"),
            "sourceThreadId": message.get("sourceThreadId"),
            "protocolSourceThreadId": str(msg.fields.get("sourceThreadId") or "").strip(),
            "protocolRole": str(msg.fields.get("role") or "").strip(),
            "protocolSourceRoleThreadId": str(msg.fields.get("sourceRoleThreadId") or "").strip(),
            "error": error,
        }
    return malformed


def _receipt_metadata(record: Mapping[str, Any],
                      *,
                      source: str,
                      channel: str) -> dict[str, Any]:
    return {
        "source": source,
        "channel": channel,
        "roleThreadId": record.get("threadId"),
        "returnThreadId": record.get("returnThreadId"),
        "orchestratorThreadId": record.get("orchestratorThreadId") or record.get("returnThreadId"),
    }
