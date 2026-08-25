"""Run-scoped, atomic human decision records for Workflow IR v3.

A gate decision is data only. ``actor`` and ``source`` are audit metadata, not
an authenticated identity or authorization grant. A decision cannot expand
scope, grant credentials, or authorize external, destructive, Git,
publication, or deployment effects.
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
from .path_safety import is_reparse as _is_reparse
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
MAX_RECORD_BYTES = 64 * 1024
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
DECISION_RECORD_KEYS = {
    "gate_version",
    "node_id",
    "input_identity",
    "decision",
    "actor",
    "source",
    "note",
    "decided_at",
}


class HumanGateError(RuntimeError):
    """A human gate record is invalid, stale, unsafe, or immutable."""


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


def validate_gate_decision_record(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HumanGateError("gate decision record must be an object")
    unknown = sorted(set(raw) - DECISION_RECORD_KEYS)
    missing = sorted(DECISION_RECORD_KEYS - set(raw))
    if unknown:
        raise HumanGateError(
            f"gate decision record has unknown keys: {unknown}"
        )
    if missing:
        raise HumanGateError(
            f"gate decision record is missing keys: {missing}"
        )
    if raw.get("gate_version") != GATE_VERSION:
        raise HumanGateError("unsupported gate decision record version")
    node_id = _validate_node_id(raw.get("node_id"))
    input_identity = _validate_identity(raw.get("input_identity"))
    decision = raw.get("decision")
    if not isinstance(decision, str) or not OPTION_RE.fullmatch(decision):
        raise HumanGateError("gate decision value is invalid")
    actor = _validate_actor(raw.get("actor"))
    source = raw.get("source")
    if source not in DECISION_SOURCES:
        raise HumanGateError("gate source must be user or host")
    note = _validate_note(raw.get("note"))
    decided_at = raw.get("decided_at")
    if not isinstance(decided_at, str) or not decided_at:
        raise HumanGateError("gate decided_at must be non-empty")
    return {
        "gate_version": GATE_VERSION,
        "node_id": node_id,
        "input_identity": input_identity,
        "decision": decision,
        "actor": actor,
        "source": source,
        "note": note,
        "decided_at": decided_at,
    }


class HumanGateStore:
    """Persist exact gate contracts and decisions below one run directory."""

    def __init__(self, run_dir: Path, limits: RuntimeLimits) -> None:
        self.run_dir = Path(os.path.abspath(os.fspath(run_dir)))
        self.root = self.run_dir / "human-gates"
        self.limits = limits

    def _assert_safe_root(self) -> None:
        if not self.run_dir.is_dir() or _is_reparse(self.run_dir):
            raise HumanGateError("run directory is not a safe directory")
        if self.root.exists() or self.root.is_symlink():
            if not self.root.is_dir() or _is_reparse(self.root):
                raise HumanGateError(
                    "human-gates path cannot be a symlink, junction, or file"
                )

    def _ensure_root(self) -> None:
        self._assert_safe_root()
        self.root.mkdir(parents=False, exist_ok=True)
        self._assert_safe_root()

    def path_for(self, node_id: str) -> Path:
        node_id = _validate_node_id(node_id)
        self._assert_safe_root()
        return self.root / f"{node_id}.json"

    def decision_path_for(self, node_id: str) -> Path:
        node_id = _validate_node_id(node_id)
        self._assert_safe_root()
        return self.root / f"{node_id}.decision.json"

    def _exclusive_write(
        self, path: Path, record: Mapping[str, Any], label: str
    ) -> None:
        payload = json.dumps(
            dict(record), ensure_ascii=False, indent=2, allow_nan=False
        ).encode("utf-8")
        if len(payload) > MAX_RECORD_BYTES:
            raise HumanGateError(
                f"{label} exceeds {MAX_RECORD_BYTES} bytes"
            )
        self._ensure_root()
        enforce_projected_write(
            self.run_dir,
            path,
            len(payload),
            self.limits.max_run_artifact_bytes,
            label,
            temporary_copy=False,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        binary_flag = getattr(os, "O_BINARY", 0)
        temporary = path.with_name(
            f".{path.name}.{secrets.token_hex(8)}.tmp"
        )
        descriptor = os.open(temporary, flags | binary_flag, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            # Publish a fully written inode under the terminal path. Hard-link
            # creation is exclusive: an existing decision is never replaced.
            os.link(temporary, path)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
        enforce_run_limit(self.run_dir, self.limits.max_run_artifact_bytes)

    def _read_json(self, path: Path, label: str) -> Any:
        if not path.is_file() or _is_reparse(path):
            raise HumanGateError(f"{label} does not exist or is unsafe")
        try:
            size = path.stat().st_size
            if size > MAX_RECORD_BYTES:
                raise HumanGateError(
                    f"{label} exceeds {MAX_RECORD_BYTES} bytes"
                )
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HumanGateError(f"cannot read {label}: {exc}") from exc

    def load(self, node_id: str) -> dict[str, Any]:
        node_id = _validate_node_id(node_id)
        contract_path = self.path_for(node_id)
        contract = validate_gate_record(
            self._read_json(contract_path, f"gate contract {node_id}")
        )
        if contract["node_id"] != node_id:
            raise HumanGateError("gate contract node_id does not match its path")
        if contract["status"] != "waiting":
            raise HumanGateError(
                "gate contract is immutable and must remain in waiting form"
            )

        decision_path = self.decision_path_for(node_id)
        if not decision_path.exists() and not decision_path.is_symlink():
            return contract
        decision = validate_gate_decision_record(
            self._read_json(decision_path, f"gate decision {node_id}")
        )
        if decision["node_id"] != node_id:
            raise HumanGateError("gate decision node_id does not match its path")
        if decision["input_identity"] != contract["input_identity"]:
            raise HumanGateError("gate decision identity does not match contract")
        if decision["decision"] not in contract["options"]:
            raise HumanGateError("gate decision is not an allowed option")

        merged = dict(contract)
        merged.update(
            {
                "status": "decided",
                "decision": decision["decision"],
                "actor": decision["actor"],
                "source": decision["source"],
                "note": decision["note"],
                "updated_at": decision["decided_at"],
            }
        )
        return validate_gate_record(merged)

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
        timestamp = now_iso()
        waiting = {
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
        path = self.path_for(node_id)
        try:
            self._exclusive_write(path, waiting, "human gate contract write")
        except FileExistsError:
            record = self.load(node_id)
            expected = (prompt, options, input_identity)
            observed = (
                record["prompt"],
                record["options"],
                record["input_identity"],
            )
            if observed != expected:
                raise HumanGateError(
                    "existing gate contract is bound to different inputs or options"
                )
            return record
        return validate_gate_record(waiting)

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

        decision_record = {
            "gate_version": GATE_VERSION,
            "node_id": node_id,
            "input_identity": expected_input_identity,
            **requested,
            "decided_at": now_iso(),
        }
        decision_path = self.decision_path_for(node_id)
        try:
            self._exclusive_write(
                decision_path,
                validate_gate_decision_record(decision_record),
                "human gate decision write",
            )
        except FileExistsError:
            existing_record = self.load(node_id)
            existing = {key: existing_record[key] for key in requested}
            if existing == requested:
                return existing_record
            raise HumanGateError("terminal gate decisions are immutable")
        return self.load(node_id)

    def list_records(self) -> list[dict[str, Any]]:
        self._assert_safe_root()
        if not self.root.exists():
            return []
        records = []
        for path in sorted(self.root.glob("*.json")):
            if path.name.endswith(".decision.json"):
                continue
            records.append(self.load(path.stem))
        return records
