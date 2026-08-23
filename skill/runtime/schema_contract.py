"""Shared JSON-schema compilation and local validation.

Provider-facing structured output schemas often require every object property to
be listed in ``required``.  The user-facing contract still needs true optional
fields.  Optional fields are therefore compiled as required nullable provider
fields and normalized back to absence when the provider returns ``null``.
"""

from __future__ import annotations

import copy
from typing import Any


def _allows_null(schema: dict[str, Any]) -> bool:
    expected = schema.get("type")
    if expected == "null":
        return True
    if isinstance(expected, list) and "null" in expected:
        return True
    alternatives = schema.get("anyOf")
    return isinstance(alternatives, list) and any(
        isinstance(child, dict) and _allows_null(child) for child in alternatives
    )


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    if _allows_null(schema):
        return schema
    return {"anyOf": [schema, {"type": "null"}]}


def compile_provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Compile a user schema into a strict provider schema.

    Empty schemas stay empty for backwards compatibility.  Object properties
    preserve their original optionality through nullable provider fields.
    """

    compiled = copy.deepcopy(schema)

    def visit(node: Any) -> Any:
        if not isinstance(node, dict) or not node:
            return node

        properties = node.get("properties")
        if isinstance(properties, dict):
            original_required = set(node.get("required", []))
            compiled_properties: dict[str, Any] = {}
            for key, child in properties.items():
                compiled_child = visit(child)
                if key not in original_required and isinstance(compiled_child, dict):
                    compiled_child = _nullable(compiled_child)
                compiled_properties[key] = compiled_child
            node["properties"] = compiled_properties
            node["additionalProperties"] = False
            node["required"] = list(compiled_properties)

        items = node.get("items")
        if isinstance(items, dict):
            node["items"] = visit(items)

        alternatives = node.get("anyOf")
        if isinstance(alternatives, list):
            node["anyOf"] = [visit(child) for child in alternatives]
        return node

    return visit(compiled)


def build_envelope_schema(result_schema: dict[str, Any] | None) -> dict[str, Any]:
    result = {"type": "string"} if result_schema is None else result_schema
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "workflow_status": {
                "type": "string",
                "enum": ["ok", "needs_escalation"],
            },
            "reason": {"type": "string"},
            "result": compile_provider_schema(result),
        },
        "required": ["workflow_status", "reason", "result"],
    }


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def validate_instance(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    problems: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path} 不在 enum 中")
        return problems

    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected] if expected else []
    if expected_types and not any(
        _json_type_matches(value, item) for item in expected_types
    ):
        problems.append(f"{path} 类型不符合 {expected!r}")
        return problems

    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list) and alternatives:
        if not any(
            not validate_instance(value, alternative, path)
            for alternative in alternatives
            if isinstance(alternative, dict)
        ):
            problems.append(f"{path} 不符合任何 anyOf 分支")
            return problems

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = [key for key in required if key not in value]
            if missing:
                problems.append(f"{path} 缺少 required 字段: {missing}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    problems.extend(
                        validate_instance(value[key], child_schema, f"{path}.{key}")
                    )
            if schema.get("additionalProperties") is False:
                extras = sorted(set(value) - set(properties))
                if extras:
                    problems.append(f"{path} 含额外字段: {extras}")

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            problems.extend(validate_instance(item, schema["items"], f"{path}[{index}]"))
    return problems


def normalize_provider_result(value: Any, schema: dict[str, Any]) -> Any:
    """Restore user-facing optional-field semantics after provider validation."""

    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        for alternative in alternatives:
            if isinstance(alternative, dict) and not validate_instance(value, alternative):
                return normalize_provider_result(value, alternative)
        return value

    if isinstance(value, dict) and isinstance(schema.get("properties"), dict):
        required = set(schema.get("required", []))
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            child_schema = schema["properties"].get(key)
            if (
                key not in required
                and item is None
                and isinstance(child_schema, dict)
                and not _allows_null(child_schema)
            ):
                continue
            normalized[key] = (
                normalize_provider_result(item, child_schema)
                if isinstance(child_schema, dict)
                else item
            )
        return normalized

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [normalize_provider_result(item, schema["items"]) for item in value]
    return value
