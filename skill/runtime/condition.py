"""Bounded, declarative condition evaluation for Workflow IR v3.

Conditions are JSON data.  This module never evaluates Python, JavaScript,
shell, regular expressions, templates, or user-provided selector languages.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping

CONDITION_STATES = {"true", "false", "unknown"}
CONDITION_OPERATORS = {
    "exists",
    "not_exists",
    "is_null",
    "not_null",
    "eq",
    "ne",
    "in",
    "not_in",
    "contains",
    "lt",
    "lte",
    "gt",
    "gte",
}
VALUELESS_OPERATORS = {"exists", "not_exists", "is_null", "not_null"}
VALUE_OPERATORS = CONDITION_OPERATORS - VALUELESS_OPERATORS
NODE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_POINTER_CHARS = 512
MAX_POINTER_SEGMENTS = 32
MAX_CONTAINER_ITEMS = 1024
_MISSING = object()


class ConditionValidationError(ValueError):
    """A condition declaration is outside the trusted contract."""


def _validate_json_value(value: Any, where: str, *, depth: int = 0) -> None:
    if depth > 32:
        raise ConditionValidationError(f"{where} exceeds 32 levels")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConditionValidationError(f"{where} must be finite JSON")
        return
    if isinstance(value, list):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise ConditionValidationError(
                f"{where} exceeds {MAX_CONTAINER_ITEMS} items"
            )
        for index, item in enumerate(value):
            _validate_json_value(item, f"{where}[{index}]", depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_CONTAINER_ITEMS:
            raise ConditionValidationError(
                f"{where} exceeds {MAX_CONTAINER_ITEMS} properties"
            )
        for key, item in value.items():
            if not isinstance(key, str):
                raise ConditionValidationError(f"{where} keys must be strings")
            _validate_json_value(item, f"{where}.{key}", depth=depth + 1)
        return
    raise ConditionValidationError(f"{where} must be JSON data")


def _validate_pointer(pointer: Any, where: str) -> str:
    if not isinstance(pointer, str):
        raise ConditionValidationError(f"{where} must be a string")
    if len(pointer) > MAX_POINTER_CHARS:
        raise ConditionValidationError(
            f"{where} exceeds {MAX_POINTER_CHARS} characters"
        )
    if pointer and not pointer.startswith("/"):
        raise ConditionValidationError(
            f"{where} must be empty or start with '/'"
        )
    segments = pointer.split("/")[1:] if pointer else []
    if len(segments) > MAX_POINTER_SEGMENTS:
        raise ConditionValidationError(
            f"{where} exceeds {MAX_POINTER_SEGMENTS} segments"
        )
    for segment in segments:
        index = 0
        while index < len(segment):
            if segment[index] != "~":
                index += 1
                continue
            if index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"}:
                raise ConditionValidationError(
                    f"{where} contains an invalid JSON Pointer escape"
                )
            index += 2
    return pointer


def validate_condition(raw: Any, where: str = "condition") -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConditionValidationError(f"{where} must be an object")
    allowed = {"source", "pointer", "operator", "value"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConditionValidationError(f"{where} has unknown keys: {unknown}")

    source = raw.get("source")
    if not isinstance(source, str) or not NODE_ID_RE.fullmatch(source):
        raise ConditionValidationError(f"{where}.source is invalid")
    pointer = _validate_pointer(raw.get("pointer", ""), f"{where}.pointer")
    operator = raw.get("operator")
    if operator not in CONDITION_OPERATORS:
        raise ConditionValidationError(
            f"{where}.operator must be one of {sorted(CONDITION_OPERATORS)}"
        )

    has_value = "value" in raw
    if operator in VALUELESS_OPERATORS and has_value:
        raise ConditionValidationError(
            f"{where}.value is not allowed for operator {operator}"
        )
    if operator in VALUE_OPERATORS and not has_value:
        raise ConditionValidationError(
            f"{where}.value is required for operator {operator}"
        )

    normalized = {
        "source": source,
        "pointer": pointer,
        "operator": operator,
    }
    if has_value:
        value = raw["value"]
        _validate_json_value(value, f"{where}.value")
        if operator in {"in", "not_in"} and not isinstance(value, list):
            raise ConditionValidationError(
                f"{where}.value must be an array for operator {operator}"
            )
        if operator in {"lt", "lte", "gt", "gte"} and not _is_number(value):
            raise ConditionValidationError(
                f"{where}.value must be a finite number for operator {operator}"
            )
        normalized["value"] = value
    return normalized


def _decode_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    """Resolve one already-validated JSON Pointer without coercion."""

    if not pointer:
        return True, document
    current = document
    for raw_segment in pointer.split("/")[1:]:
        segment = _decode_pointer_segment(raw_segment)
        if isinstance(current, dict):
            if segment not in current:
                return False, _MISSING
            current = current[segment]
            continue
        if isinstance(current, list):
            if not segment.isdigit():
                return False, _MISSING
            index = int(segment)
            if index >= len(current):
                return False, _MISSING
            current = current[index]
            continue
        return False, _MISSING
    return True, current


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )


def _json_equal(left: Any, right: Any) -> bool:
    if _is_number(left) and _is_number(right):
        return left == right
    if type(left) is not type(right):
        return False
    return left == right


def _actual_type(value: Any, *, found: bool) -> str:
    if not found:
        return "missing"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if _is_number(value):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _result(
    condition: Mapping[str, Any],
    state: str,
    reason: str,
    *,
    found: bool,
    actual: Any = _MISSING,
) -> dict[str, Any]:
    if state not in CONDITION_STATES:
        raise RuntimeError(f"invalid condition state: {state}")
    evidence = [
        f"source={condition['source']}",
        f"pointer={condition['pointer'] or '<root>'}",
        f"operator={condition['operator']}",
        f"actual_type={_actual_type(actual, found=found)}",
    ]
    return {
        "state": state,
        "reason": reason,
        "source": condition["source"],
        "pointer": condition["pointer"],
        "operator": condition["operator"],
        "evidence": evidence,
    }


def evaluate_condition(
    raw_condition: Mapping[str, Any],
    sources: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate a validated condition against exact node-id sources."""

    condition = validate_condition(dict(raw_condition))
    source_id = condition["source"]
    if source_id not in sources:
        return _result(
            condition,
            "unknown",
            "declared source result is unavailable",
            found=False,
        )
    found, actual = resolve_json_pointer(sources[source_id], condition["pointer"])
    operator = condition["operator"]

    if operator == "exists":
        return _result(
            condition,
            "true" if found else "false",
            "JSON Pointer existence evaluated",
            found=found,
            actual=actual,
        )
    if operator == "not_exists":
        return _result(
            condition,
            "false" if found else "true",
            "JSON Pointer non-existence evaluated",
            found=found,
            actual=actual,
        )
    if not found:
        return _result(
            condition,
            "unknown",
            "JSON Pointer did not resolve",
            found=False,
        )
    if operator == "is_null":
        return _result(
            condition,
            "true" if actual is None else "false",
            "null comparison evaluated",
            found=True,
            actual=actual,
        )
    if operator == "not_null":
        return _result(
            condition,
            "false" if actual is None else "true",
            "non-null comparison evaluated",
            found=True,
            actual=actual,
        )

    expected = condition["value"]
    if operator == "eq":
        outcome = _json_equal(actual, expected)
    elif operator == "ne":
        outcome = not _json_equal(actual, expected)
    elif operator in {"in", "not_in"}:
        outcome = any(_json_equal(actual, item) for item in expected)
        if operator == "not_in":
            outcome = not outcome
    elif operator == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            outcome = expected in actual
        elif isinstance(actual, list):
            outcome = any(_json_equal(item, expected) for item in actual)
        elif isinstance(actual, dict) and isinstance(expected, str):
            outcome = expected in actual
        else:
            return _result(
                condition,
                "unknown",
                "contains operands are not compatible",
                found=True,
                actual=actual,
            )
    elif operator in {"lt", "lte", "gt", "gte"}:
        if not _is_number(actual):
            return _result(
                condition,
                "unknown",
                "numeric comparison received a non-number",
                found=True,
                actual=actual,
            )
        outcome = {
            "lt": actual < expected,
            "lte": actual <= expected,
            "gt": actual > expected,
            "gte": actual >= expected,
        }[operator]
    else:  # guarded by validate_condition
        raise RuntimeError(f"unhandled condition operator: {operator}")

    return _result(
        condition,
        "true" if outcome else "false",
        "bounded comparison evaluated",
        found=True,
        actual=actual,
    )


def canonical_condition_json(condition: Mapping[str, Any]) -> str:
    return json.dumps(
        validate_condition(dict(condition)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
