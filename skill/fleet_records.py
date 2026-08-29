"""Structured Agent Fleet records and strict validators."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

FINDING_CATEGORIES = frozenset(
    {
        "correctness",
        "regression",
        "tests",
        "api-compatibility",
        "security",
        "concurrency-lifecycle",
        "platform",
        "performance",
        "scope-effects",
        "architecture",
        "operations",
        "data-state",
        "research-evidence",
        "other",
    }
)
SEVERITIES = frozenset({"P1", "P2", "P3"})
CONFIDENCE = frozenset({"high", "medium", "low"})
MAX_ITEMS = 128
MAX_FINDINGS_PER_RECORD = 16
MAX_TEXT = 8_000


class FleetRecordError(RuntimeError):
    """A fleet agent record is malformed, stale, effectful, or inconsistent."""


def _closed(value: Any, *, where: str, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetRecordError(f"{where} must be an object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise FleetRecordError(
            f"{where} keys mismatch: missing={missing} unknown={unknown}"
        )
    return value


def _text(value: Any, *, where: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise FleetRecordError(f"{where} must be a string")
    result = value.strip()
    if not result or "\x00" in result or len(result) > maximum:
        raise FleetRecordError(f"{where} must be a bounded non-empty string")
    return result


def _strings(
    value: Any,
    *,
    where: str,
    minimum: int = 0,
    maximum: int = MAX_ITEMS,
) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise FleetRecordError(
            f"{where} must contain {minimum}..{maximum} strings"
        )
    return [_text(item, where=f"{where}[{index}]") for index, item in enumerate(value)]


def _identity(
    raw: Mapping[str, Any],
    *,
    candidate_revision: str,
    agent: Mapping[str, Any],
    phase: str,
) -> None:
    expected = {
        "candidate_revision": candidate_revision,
        "agent_id": agent["agent_id"],
        "role_id": agent["role_id"],
        "phase": phase,
    }
    for key, value in expected.items():
        if raw.get(key) != value:
            raise FleetRecordError(
                f"record {key} mismatch: expected={value!r} actual={raw.get(key)!r}"
            )
    if raw.get("effects") != []:
        raise FleetRecordError("fleet agent effects must be exactly []")


def finding_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string", "enum": sorted(FINDING_CATEGORIES)},
            "severity": {"type": "string", "enum": sorted(SEVERITIES)},
            "summary": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": sorted(CONFIDENCE)},
        },
        "required": [
            "category",
            "severity",
            "summary",
            "evidence",
            "locations",
            "confidence",
        ],
    }


def discovery_schema(*, candidate_revision: str, agent: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_revision": {"type": "string", "enum": [candidate_revision]},
            "agent_id": {"type": "string", "enum": [agent["agent_id"]]},
            "role_id": {"type": "string", "enum": [agent["role_id"]]},
            "phase": {"type": "string", "enum": ["discovery"]},
            "verdict": {"type": "string", "enum": ["accept", "findings", "unknown"]},
            "findings": {
                "type": "array",
                "maxItems": MAX_FINDINGS_PER_RECORD,
                "items": finding_schema(),
            },
            "unknown": {"type": "array", "items": {"type": "string"}},
            "effects": {"type": "array", "maxItems": 0},
        },
        "required": [
            "candidate_revision",
            "agent_id",
            "role_id",
            "phase",
            "verdict",
            "findings",
            "unknown",
            "effects",
        ],
    }


def challenge_schema(*, candidate_revision: str, agent: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_revision": {"type": "string", "enum": [candidate_revision]},
            "agent_id": {"type": "string", "enum": [agent["agent_id"]]},
            "role_id": {"type": "string", "enum": [agent["role_id"]]},
            "phase": {"type": "string", "enum": ["challenge"]},
            "assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "finding_id": {"type": "string"},
                        "outcome": {
                            "type": "string",
                            "enum": ["support", "refute", "unresolved"],
                        },
                        "evidence": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["finding_id", "outcome", "evidence"],
                },
            },
            "new_findings": {
                "type": "array",
                "maxItems": MAX_FINDINGS_PER_RECORD,
                "items": finding_schema(),
            },
            "unknown": {"type": "array", "items": {"type": "string"}},
            "effects": {"type": "array", "maxItems": 0},
        },
        "required": [
            "candidate_revision",
            "agent_id",
            "role_id",
            "phase",
            "assessments",
            "new_findings",
            "unknown",
            "effects",
        ],
    }


def reproduction_schema(*, candidate_revision: str, agent: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_revision": {"type": "string", "enum": [candidate_revision]},
            "agent_id": {"type": "string", "enum": [agent["agent_id"]]},
            "role_id": {"type": "string", "enum": [agent["role_id"]]},
            "phase": {"type": "string", "enum": ["reproduction"]},
            "reproductions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "finding_id": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["reproduced", "refuted", "inconclusive"],
                        },
                        "steps": {"type": "array", "items": {"type": "string"}},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["finding_id", "status", "steps", "evidence"],
                },
            },
            "new_findings": {
                "type": "array",
                "maxItems": MAX_FINDINGS_PER_RECORD,
                "items": finding_schema(),
            },
            "unknown": {"type": "array", "items": {"type": "string"}},
            "effects": {"type": "array", "maxItems": 0},
        },
        "required": [
            "candidate_revision",
            "agent_id",
            "role_id",
            "phase",
            "reproductions",
            "new_findings",
            "unknown",
            "effects",
        ],
    }


def arbiter_schema(*, candidate_revision: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_revision": {"type": "string", "enum": [candidate_revision]},
            "verdict": {"type": "string", "enum": ["ship", "fix-first", "rethink"]},
            "accepted_findings": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "effects": {"type": "array", "maxItems": 0},
        },
        "required": [
            "candidate_revision",
            "verdict",
            "accepted_findings",
            "rationale",
            "evidence",
            "effects",
        ],
    }


def _finding(value: Any, *, where: str) -> dict[str, Any]:
    record = _closed(
        value,
        where=where,
        keys=frozenset(
            {"category", "severity", "summary", "evidence", "locations", "confidence"}
        ),
    )
    if record["category"] not in FINDING_CATEGORIES:
        raise FleetRecordError(f"{where}.category is invalid")
    if record["severity"] not in SEVERITIES:
        raise FleetRecordError(f"{where}.severity is invalid")
    if record["confidence"] not in CONFIDENCE:
        raise FleetRecordError(f"{where}.confidence is invalid")
    return {
        "category": record["category"],
        "severity": record["severity"],
        "summary": _text(record["summary"], where=f"{where}.summary"),
        "evidence": _strings(
            record["evidence"], where=f"{where}.evidence", minimum=1
        ),
        "locations": _strings(record["locations"], where=f"{where}.locations", maximum=32),
        "confidence": record["confidence"],
    }


def validate_discovery_record(
    raw: Any,
    *,
    candidate_revision: str,
    agent: Mapping[str, Any],
) -> dict[str, Any]:
    keys = frozenset(
        {
            "candidate_revision",
            "agent_id",
            "role_id",
            "phase",
            "verdict",
            "findings",
            "unknown",
            "effects",
        }
    )
    record = _closed(raw, where="discovery record", keys=keys)
    _identity(record, candidate_revision=candidate_revision, agent=agent, phase="discovery")
    verdict = record["verdict"]
    if verdict not in {"accept", "findings", "unknown"}:
        raise FleetRecordError("discovery verdict is invalid")
    findings_raw = record["findings"]
    if (
        not isinstance(findings_raw, list)
        or len(findings_raw) > MAX_FINDINGS_PER_RECORD
    ):
        raise FleetRecordError("discovery findings must be a bounded array")
    findings = [
        _finding(item, where=f"discovery findings[{index}]")
        for index, item in enumerate(findings_raw)
    ]
    unknown = _strings(record["unknown"], where="discovery unknown")
    if verdict == "accept" and (findings or unknown):
        raise FleetRecordError("accept requires empty findings and unknown")
    if verdict == "findings" and not findings:
        raise FleetRecordError("findings verdict requires at least one finding")
    if verdict == "unknown" and not unknown:
        raise FleetRecordError("unknown verdict requires at least one unknown")
    return {
        "candidate_revision": candidate_revision,
        "agent_id": agent["agent_id"],
        "role_id": agent["role_id"],
        "phase": "discovery",
        "verdict": verdict,
        "findings": findings,
        "unknown": unknown,
        "effects": [],
    }


def validate_challenge_record(
    raw: Any,
    *,
    candidate_revision: str,
    agent: Mapping[str, Any],
    finding_ids: Sequence[str],
) -> dict[str, Any]:
    keys = frozenset(
        {
            "candidate_revision",
            "agent_id",
            "role_id",
            "phase",
            "assessments",
            "new_findings",
            "unknown",
            "effects",
        }
    )
    record = _closed(raw, where="challenge record", keys=keys)
    _identity(record, candidate_revision=candidate_revision, agent=agent, phase="challenge")
    allowed = set(finding_ids)
    raw_assessments = record["assessments"]
    if not isinstance(raw_assessments, list) or len(raw_assessments) > MAX_ITEMS:
        raise FleetRecordError("challenge assessments must be a bounded array")
    assessments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_assessments):
        assessment = _closed(
            item,
            where=f"challenge assessments[{index}]",
            keys=frozenset({"finding_id", "outcome", "evidence"}),
        )
        finding_id = _text(
            assessment["finding_id"], where=f"challenge assessments[{index}].finding_id", maximum=96
        )
        if finding_id not in allowed:
            raise FleetRecordError(f"challenge references unknown finding {finding_id!r}")
        if finding_id in seen:
            raise FleetRecordError("challenge may assess each finding at most once")
        seen.add(finding_id)
        outcome = assessment["outcome"]
        if outcome not in {"support", "refute", "unresolved"}:
            raise FleetRecordError("challenge outcome is invalid")
        assessments.append(
            {
                "finding_id": finding_id,
                "outcome": outcome,
                "evidence": _strings(
                    assessment["evidence"],
                    where=f"challenge assessments[{index}].evidence",
                    minimum=1,
                ),
            }
        )
    missing = sorted(allowed - seen)
    if missing:
        raise FleetRecordError(
            f"challenge must assess every assigned finding exactly once: {missing}"
        )
    raw_new = record["new_findings"]
    if (
        not isinstance(raw_new, list)
        or len(raw_new) > MAX_FINDINGS_PER_RECORD
    ):
        raise FleetRecordError("challenge new_findings must be a bounded array")
    return {
        "candidate_revision": candidate_revision,
        "agent_id": agent["agent_id"],
        "role_id": agent["role_id"],
        "phase": "challenge",
        "assessments": assessments,
        "new_findings": [
            _finding(item, where=f"challenge new_findings[{index}]")
            for index, item in enumerate(raw_new)
        ],
        "unknown": _strings(record["unknown"], where="challenge unknown"),
        "effects": [],
    }


def validate_reproduction_record(
    raw: Any,
    *,
    candidate_revision: str,
    agent: Mapping[str, Any],
    finding_ids: Sequence[str],
) -> dict[str, Any]:
    keys = frozenset(
        {
            "candidate_revision",
            "agent_id",
            "role_id",
            "phase",
            "reproductions",
            "new_findings",
            "unknown",
            "effects",
        }
    )
    record = _closed(raw, where="reproduction record", keys=keys)
    _identity(record, candidate_revision=candidate_revision, agent=agent, phase="reproduction")
    allowed = set(finding_ids)
    raw_items = record["reproductions"]
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS:
        raise FleetRecordError("reproductions must be a bounded array")
    reproductions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items):
        reproduction = _closed(
            item,
            where=f"reproductions[{index}]",
            keys=frozenset({"finding_id", "status", "steps", "evidence"}),
        )
        finding_id = _text(
            reproduction["finding_id"], where=f"reproductions[{index}].finding_id", maximum=96
        )
        if finding_id not in allowed:
            raise FleetRecordError(f"reproduction references unknown finding {finding_id!r}")
        if finding_id in seen:
            raise FleetRecordError("reproduction may assess each finding at most once")
        seen.add(finding_id)
        status = reproduction["status"]
        if status not in {"reproduced", "refuted", "inconclusive"}:
            raise FleetRecordError("reproduction status is invalid")
        steps = _strings(reproduction["steps"], where=f"reproductions[{index}].steps")
        evidence = _strings(
            reproduction["evidence"],
            where=f"reproductions[{index}].evidence",
            minimum=1,
        )
        if status == "reproduced" and not steps:
            raise FleetRecordError("reproduced finding requires reproduction steps")
        reproductions.append(
            {
                "finding_id": finding_id,
                "status": status,
                "steps": steps,
                "evidence": evidence,
            }
        )
    missing = sorted(allowed - seen)
    if missing:
        raise FleetRecordError(
            f"reproduction must assess every assigned finding exactly once: {missing}"
        )
    raw_new = record["new_findings"]
    if (
        not isinstance(raw_new, list)
        or len(raw_new) > MAX_FINDINGS_PER_RECORD
    ):
        raise FleetRecordError("reproduction new_findings must be a bounded array")
    return {
        "candidate_revision": candidate_revision,
        "agent_id": agent["agent_id"],
        "role_id": agent["role_id"],
        "phase": "reproduction",
        "reproductions": reproductions,
        "new_findings": [
            _finding(item, where=f"reproduction new_findings[{index}]")
            for index, item in enumerate(raw_new)
        ],
        "unknown": _strings(record["unknown"], where="reproduction unknown"),
        "effects": [],
    }


def validate_arbiter_record(
    raw: Any,
    *,
    candidate_revision: str,
    valid_finding_ids: Sequence[str],
    severity_by_id: Mapping[str, str],
) -> dict[str, Any]:
    record = _closed(
        raw,
        where="Sol arbitration record",
        keys=frozenset(
            {
                "candidate_revision",
                "verdict",
                "accepted_findings",
                "rationale",
                "evidence",
                "effects",
            }
        ),
    )
    if record["candidate_revision"] != candidate_revision:
        raise FleetRecordError("Sol arbitration candidate revision is stale")
    if record["effects"] != []:
        raise FleetRecordError("Sol arbitration effects must be exactly []")
    verdict = record["verdict"]
    if verdict not in {"ship", "fix-first", "rethink"}:
        raise FleetRecordError("Sol arbitration verdict is invalid")
    accepted = _strings(
        record["accepted_findings"],
        where="Sol arbitration accepted_findings",
        maximum=MAX_ITEMS,
    )
    if len(set(accepted)) != len(accepted):
        raise FleetRecordError("accepted_findings must be unique")
    valid = set(valid_finding_ids)
    if not set(accepted) <= valid:
        raise FleetRecordError("Sol arbitration references an unknown finding")
    blocking = [item for item in accepted if severity_by_id.get(item) in {"P1", "P2"}]
    if verdict == "ship" and blocking:
        raise FleetRecordError("ship cannot accept a P1/P2 finding")
    if verdict == "fix-first" and not blocking:
        raise FleetRecordError("fix-first requires an accepted P1/P2 finding")
    return {
        "candidate_revision": candidate_revision,
        "verdict": verdict,
        "accepted_findings": accepted,
        "rationale": _text(record["rationale"], where="Sol arbitration rationale"),
        "evidence": _strings(
            record["evidence"], where="Sol arbitration evidence", minimum=1
        ),
        "effects": [],
    }
