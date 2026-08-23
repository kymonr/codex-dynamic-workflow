"""Run-scoped, immutable human decision records for Workflow IR v3.

A gate decision is data only.  It cannot expand scope, grant credentials, or
authorize external, destructive, Git, publication, or deployment effects.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Iterable, Mapping

from .limits import RuntimeLimits, enforce_projected_write, enforce_run_limit
from .state_store import now_iso

GATE_VERSION = 1
GATE_STATUSES = {"waiting", "decided"}
DECISION_SOURCES = {"user", "host"}
NODE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
OPTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
IDENTITY_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_PROMPT_CHARS = 4000
MAX_OPTIONS = 8
MAX_ACTOR_CHARS = 128
MAX_NOTE_CHARS = 2000
RECORD_KEYS = {
    "gate_version",
    "node_id",
    "prompt",
    "options",
    "status",
    "input_identity",
    "decision",
    "actor",
    "source",
    "note",
    "opened_at",
    "updated_at",
}


class HumanGateError(RuntimeError):
    """A human gate record is invalid, stale, or immutable."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def compute_gate_input_identity(
    node_id: str,
    prompt: str,
    options: Iterable[str],
    dependencies: Iterable[Mapping[str, Any]],
) -> str:
    """Bind a decision to the exact gate contract and accepted inputs."""

    payload = {
        "node_id": node_id,
        "prompt": prompt,
        "options": list(options),
        "dependencies": list(dependencies),
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _validate_node_id(value: Any) -> str:
    if not isinstance(value, str) or not NODE_ID_RE.fullmatch(value):
        raise HumanGateError("gate node_id is invalid")
    return value


def _validate_prompt(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanGateError("gate prompt must be non-empty")
    prompt = value.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HumanGateError(
            f"gate prompt exceeds {MAX_PROMPT_CHARS} characters"
        )
    return prompt


def _validate_options(value: Any) -> list[str]:
    if not isinstance(value, list) or not 2 <= len(value) <= MAX_OPTIONS:
        raise HumanGateError(
            f"gate options must contain 2..{MAX_OPTIONS} strings"
        )
    options: list[str] = []
    folded: set[str] = set()
    for option in value:
        if not isinstance(option, str) or not OPTION_RE.fullmatch(option):
            raise HumanGateError(
                "gate options must match [A-Za-z0-9][A-Za-z0-9_-]{0,31}"
            )
        key = option.casefold()
        if key in folded:
            raise HumanGateError("gate options must be case-insensitively unique")
        folded.add(key)
        options.append(option)
    return options


def _validate_identity(value: Any) -> str:
    if not isinstance(value, str) or not IDENTITY_RE.fullmatch(value):
        raise HumanGateError("gate input_identity must be a lowercase SHA-256")
    return value


def _validate_actor(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanGateError("gate actor must be non-empty")
    actor = value.strip()
    if len(actor) > MAX_ACTOR_CHARS:
        raise HumanGateError(
            f"gate actor exceeds {MAX_ACTOR_CHARS} characters"
        )
    return actor


def _validate_note(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HumanGateError("gate note must be a string or null")
    if len(value) > MAX_NOTE_CHARS:
        raise HumanGateError(f"gate note exceeds {MAX_NOTE_CHARS} characters")
    return value


def validate_gate_record(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HumanGateError("gate record must be an object")
    unknown = sorted(set(raw) - RECORD_KEYS)
    missing = sorted(RECORD_KEYS - set(raw))
    if unknown:
        raise HumanGateError(f"gate record has unknown keys: {unknown}")
    if missing:
        raise HumanGateError(f"gate record is missing keys: {missing}")
    if raw.get("gate_version") != GATE_VERSION:
        raise HumanGateError("unsupported gate record version")

    node_id = _validate_node_id(raw.get("node_id"))
    prompt = _validate_prompt(raw.get("prompt"))
    options = _validate_options(raw.get("options"))
    status = raw.get("status")
    if status not in GATE_STATUSES:
        raise HumanGateError("gate status must be waiting or decided")
    input_identity = _validate_identity(raw.get("input_identity"))
    opened_at = raw.get("opened_at")
    updated_at = raw.get("updated_at")
    if not isinstance(opened_at, str) or not opened_at:
        raise HumanGateError("gate opened_at must be non-empty")
    if not isinstance(updated_at, str) or not updated_at:
        raise HumanGateError("gate updated_at must be non-empty")

    decision = raw.get("decision")
    actor = raw.get("actor")
    source = raw.get("source")
    note = _validate_note(raw.get("note"))
    if status == "waiting":
        if any(value is not None for value in (decision, actor, source, note)):
            raise HumanGateError(
                "waiting gate cannot carry decision, actor, source, or note"
            )
    else:
        if decision not in options:
            raise HumanGateError("gate decision is not one of the allowed options")
        actor = _validate_actor(actor)
        if source not in DECISION_SOURCES:
            raise HumanGateError("gate source must be user or host")

    return {
        "gate_version": GATE_VERSION,
        "node_id": node_id,
        "prompt": prompt,
        "options": options,
        "status": status,
        "input_identity": input_identity,
        "decision": decision,
        "actor": actor,
        "source": source,
        "note": note,
        "opened_at": opened_at,
        "updated_at": updated_at,
    }


class HumanGateStore:
    """Persist exact gate records below one Workflow IR run directory."""

    def __init__(self, run_dir: Path, limits: RuntimeLimits) -> None:
        self.run_dir = run_dir.resolve()
        self.root = self.run_dir / "human-gates"
        self.limits = limits

    def path_for(self, node_id: str) -> Path:
        node_id = _validate_node_id(node_id)
        path = (self.root / f"{node_id}.json").resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise HumanGateError("gate path escapes the run-scoped gate root")
        return path

    def _write(self, record: Mapping[str, Any]) -> dict[str, Any]:
        normalized = validate_gate_record(dict(record))
        path = self.path_for(normalized["node_id"])
        payload = json.dumps(
            normalized, ensure_ascii=False, indent=2, allow_nan=False
        ).encode("utf-8")
        enforce_projected_write(
            self.run_dir,
            path,
            len(payload),
            self.limits.max_run_artifact_bytes,
            "human gate record write",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise HumanGateError("human-gates directory cannot be a symlink")
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        enforce_run_limit(self.run_dir, self.limits.max_run_artifact_bytes)
        return normalized

    def load(self, node_id: str) -> dict[str, Any]:
        path = self.path_for(node_id)
        if not path.is_file() or path.is_symlink():
            raise HumanGateError(f"gate record does not exist or is unsafe: {node_id}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HumanGateError(f"cannot read gate record {node_id}: {exc}") from exc
        record = validate_gate_record(raw)
        if record["node_id"] != node_id:
            raise HumanGateError("gate record node_id does not match its path")
        return record

    def open_gate(
        self,
        node_id: str,
        *,
        prompt: str,
        options: list[str],
        input_identity: str,
    ) -> dict[str, Any]:
        node_id = _validate_node_id(node_id)
        prompt = _validate_prompt(prompt)
        options = _validate_options(options)
        input_identity = _validate_identity(input_identity)
        path = self.path_for(node_id)
        if path.exists():
            record = self.load(node_id)
            expected = (prompt, options, input_identity)
            observed = (
                record["prompt"],
                record["options"],
                record["input_identity"],
            )
            if observed != expected:
                raise HumanGateError(
                    "existing gate record is bound to different inputs or options"
                )
            return record
        timestamp = now_iso()
        return self._write(
            {
                "gate_version": GATE_VERSION,
                "node_id": node_id,
                "prompt": prompt,
                "options": options,
                "status": "waiting",
                "input_identity": input_identity,
                "decision": None,
                "actor": None,
                "source": None,
                "note": None,
                "opened_at": timestamp,
                "updated_at": timestamp,
            }
        )

    def decide(
        self,
        node_id: str,
        *,
        decision: str,
        actor: str,
        source: str,
        expected_input_identity: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        record = self.load(node_id)
        expected_input_identity = _validate_identity(expected_input_identity)
        if record["input_identity"] != expected_input_identity:
            raise HumanGateError(
                "gate decision input identity does not match the waiting record"
            )
        if decision not in record["options"]:
            raise HumanGateError("gate decision is not an allowed option")
        actor = _validate_actor(actor)
        if source not in DECISION_SOURCES:
            raise HumanGateError("gate source must be user or host")
        note = _validate_note(note)

        requested = {
            "decision": decision,
            "actor": actor,
            "source": source,
            "note": note,
        }
        if record["status"] == "decided":
            existing = {key: record[key] for key in requested}
            if existing == requested:
                return record
            raise HumanGateError("terminal gate decisions are immutable")

        decided = dict(record)
        decided.update(requested)
        decided["status"] = "decided"
        decided["updated_at"] = now_iso()
        return self._write(decided)

    def list_records(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        if not self.root.is_dir() or self.root.is_symlink():
            raise HumanGateError("human-gates path is not a safe directory")
        records = []
        for path in sorted(self.root.glob("*.json")):
            records.append(self.load(path.stem))
        return records
