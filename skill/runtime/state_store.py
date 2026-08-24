"""Checkpoint and append-only event journal for resumable workflow runs."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .limits import ArtifactLimitError, directory_size, enforce_projected_write
from .path_safety import assert_safe_descendant

CHECKPOINT_VERSION = 1
EVENT_VERSION = 1
STABLE_SPEC_KEYS = (
    "version",
    "name",
    "workdir",
    "max_concurrency",
    "soft_timeout_seconds",
    "hard_timeout_seconds",
    "limits",
    "tasks",
)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def stable_spec_payload(spec: dict[str, Any]) -> dict[str, Any]:
    return {key: spec[key] for key in STABLE_SPEC_KEYS if key in spec}


def spec_digest(spec: dict[str, Any]) -> str:
    encoded = json.dumps(
        stable_spec_payload(spec),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RunStateStore:
    def __init__(
        self,
        run_dir: Path,
        *,
        max_event_bytes: int,
        max_run_artifact_bytes: int | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.events_path = run_dir / "events.jsonl"
        self.checkpoint_path = run_dir / "checkpoint.json"
        self.max_event_bytes = max_event_bytes
        self.max_run_artifact_bytes = max_run_artifact_bytes
        self.sequence = self._existing_sequence()

    def _existing_sequence(self) -> int:
        assert_safe_descendant(
            self.run_dir, self.checkpoint_path, label="checkpoint read"
        )
        assert_safe_descendant(
            self.run_dir, self.events_path, label="event journal read"
        )
        if self.checkpoint_path.is_file():
            try:
                checkpoint = json.loads(
                    self.checkpoint_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                checkpoint = None
            if isinstance(checkpoint, dict):
                sequence = checkpoint.get("event_sequence")
                if (
                    not isinstance(sequence, bool)
                    and isinstance(sequence, int)
                    and sequence >= 0
                ):
                    return sequence
        if not self.events_path.is_file():
            return 0
        sequence = 0
        try:
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if (
                    isinstance(event, dict)
                    and not isinstance(event.get("sequence"), bool)
                    and isinstance(event.get("sequence"), int)
                ):
                    sequence = max(sequence, event["sequence"])
        except (OSError, json.JSONDecodeError):
            return sequence
        return sequence

    def append_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type must be a non-empty string")
        assert_safe_descendant(
            self.run_dir, self.events_path, label="event journal append"
        )
        previous_sequence = self.sequence
        original_size = (
            self.events_path.stat().st_size if self.events_path.is_file() else 0
        )
        self.sequence += 1
        event = {
            "event_version": EVENT_VERSION,
            "sequence": self.sequence,
            "at": now_iso(),
            "type": event_type,
            "payload": payload,
        }
        encoded = (
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
        try:
            if len(encoded) > self.max_event_bytes:
                raise ValueError(
                    f"event exceeds max_event_bytes={self.max_event_bytes}: "
                    f"{len(encoded)}"
                )
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            assert_safe_descendant(
                self.run_dir, self.events_path, label="event journal append"
            )
            if self.max_run_artifact_bytes is not None:
                enforce_projected_write(
                    self.run_dir,
                    self.events_path,
                    len(encoded),
                    self.max_run_artifact_bytes,
                    "event journal append",
                    temporary_copy=False,
                )
            with self.events_path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            return event
        except BaseException:
            self.sequence = previous_sequence
            try:
                if self.events_path.is_file():
                    with self.events_path.open("r+b") as handle:
                        handle.truncate(original_size)
                    if original_size == 0:
                        self.events_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def validate_journal(
        self, *, expected_sequence: int | None = None
    ) -> list[dict[str, Any]]:
        """Strictly validate the append-only journal and its checkpoint tail."""

        assert_safe_descendant(
            self.run_dir, self.events_path, label="event journal validation"
        )
        if not self.events_path.is_file():
            if expected_sequence in (None, 0):
                return []
            raise ValueError("event journal is missing")
        try:
            raw = self.events_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"cannot read event journal: {exc}") from exc
        if raw and not raw.endswith(b"\n"):
            raise ValueError("event journal has a partial final record")
        events: list[dict[str, Any]] = []
        for expected, line in enumerate(raw.splitlines(), start=1):
            if len(line) + 1 > self.max_event_bytes:
                raise ValueError(
                    f"event journal record {expected} exceeds max_event_bytes"
                )
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"event journal record {expected} is malformed: {exc}"
                ) from exc
            if not isinstance(event, dict):
                raise ValueError(f"event journal record {expected} must be an object")
            if event.get("event_version") != EVENT_VERSION:
                raise ValueError(f"event journal record {expected} version is invalid")
            sequence = event.get("sequence")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence != expected
            ):
                raise ValueError(
                    f"event journal sequence is not continuous at record {expected}"
                )
            if not isinstance(event.get("type"), str) or not event["type"]:
                raise ValueError(f"event journal record {expected} type is invalid")
            if not isinstance(event.get("payload"), dict):
                raise ValueError(f"event journal record {expected} payload is invalid")
            if not isinstance(event.get("at"), str) or not event["at"]:
                raise ValueError(f"event journal record {expected} timestamp is invalid")
            events.append(event)
        if expected_sequence is not None and len(events) != expected_sequence:
            raise ValueError(
                "event journal tail disagrees with checkpoint: "
                f"journal={len(events)} checkpoint={expected_sequence}"
            )
        return events

    def write_checkpoint(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert_safe_descendant(
            self.run_dir, self.checkpoint_path, label="checkpoint write"
        )
        checkpoint = {
            **payload,
            "checkpoint_version": CHECKPOINT_VERSION,
            "event_sequence": self.sequence,
            "updated_at": now_iso(),
        }
        encoded = json.dumps(
            checkpoint, ensure_ascii=False, indent=2
        ).encode("utf-8")
        if self.max_run_artifact_bytes is not None:
            enforce_projected_write(
                self.run_dir,
                self.checkpoint_path,
                len(encoded),
                self.max_run_artifact_bytes,
                "checkpoint write",
            )
        temporary = self.checkpoint_path.with_suffix(
            self.checkpoint_path.suffix + ".tmp"
        )
        assert_safe_descendant(
            self.run_dir, temporary, label="checkpoint temporary write"
        )
        temporary.write_bytes(encoded)
        os.replace(temporary, self.checkpoint_path)
        return checkpoint

    def load_checkpoint(self) -> dict[str, Any]:
        assert_safe_descendant(
            self.run_dir, self.checkpoint_path, label="checkpoint read"
        )
        try:
            checkpoint = json.loads(
                self.checkpoint_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load checkpoint: {exc}") from exc
        if not isinstance(checkpoint, dict):
            raise ValueError("checkpoint must be an object")
        if checkpoint.get("checkpoint_version") != CHECKPOINT_VERSION:
            raise ValueError("unsupported checkpoint version")
        sequence = checkpoint.get("event_sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("checkpoint event_sequence is invalid")
        return checkpoint
