"""Read-only personal installation identity and drift status."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import InstallManagerError, validate_history_record
from .filesystem import (
    current_regular_digest,
    read_manifest,
    read_record,
    resolve_codex_home,
    resolve_state_root,
    scan_unmanaged_skill_files,
)


def install_status(
    *,
    codex_home: Path | str | None = None,
    state_root: Path | str | None = None,
) -> dict[str, Any]:
    """Report installed identity and target drift without writing."""

    codex = resolve_codex_home(codex_home)
    state = resolve_state_root(state_root)
    manifest = read_manifest(codex)
    if manifest is None:
        return {
            "operation": "install-status",
            "state": "not_installed",
            "codex_home": str(codex),
            "state_root": str(state),
            "install_id": None,
            "skill_version": None,
            "rollback_available": False,
            "managed_files": [],
            "drift": [],
            "unmanaged_skill_files": [],
            "model_calls": 0,
            "writes": [],
        }

    drift: list[dict[str, Any]] = []
    file_status: list[dict[str, Any]] = []
    managed_targets = {entry["target"] for entry in manifest["managed_files"]}
    for entry in manifest["managed_files"]:
        current = current_regular_digest(codex, entry["target"])
        if current is None:
            status = "missing"
            current_sha = None
        else:
            current_sha = current[0]
            status = "clean" if current_sha == entry["sha256"] else "modified"
        if status != "clean":
            drift.append(
                {
                    "target": entry["target"],
                    "status": status,
                    "expected_sha256": entry["sha256"],
                    "current_sha256": current_sha,
                }
            )
        file_status.append(
            {
                "target": entry["target"],
                "status": status,
                "expected_sha256": entry["sha256"],
                "current_sha256": current_sha,
            }
        )

    record_error: str | None = None
    record_state: str | None = None
    previous_install_id: str | None = None
    previous_skill_version: str | None = None
    rollback_available = manifest["history_record"] is not None
    if manifest["history_record"] is not None:
        try:
            _, record = read_record(state, manifest["history_record"])
            validate_history_record(
                record, manifest=manifest, codex_home=str(codex)
            )
            record_state = record["state"]
            previous = record.get("previous_manifest")
            if previous is not None:
                previous_install_id = previous["install_id"]
                previous_skill_version = previous["skill_version"]
            if record_state not in {"applied", "prepared", "rolling_back"}:
                record_error = f"active installation history state is {record_state!r}"
        except InstallManagerError as exc:
            record_error = str(exc)
            rollback_available = False

    unmanaged = scan_unmanaged_skill_files(codex, managed_targets)
    if drift:
        state_name = (
            "rollback_incomplete" if record_state == "rolling_back" else "drifted"
        )
    elif record_error is not None:
        state_name = "metadata_error"
    elif unmanaged:
        state_name = "clean_with_unmanaged_files"
    else:
        state_name = "clean"
    return {
        "operation": "install-status",
        "state": state_name,
        "codex_home": str(codex),
        "state_root": str(state),
        "install_id": manifest["install_id"],
        "skill_version": manifest["skill_version"],
        "installed_at": manifest["installed_at"],
        "source_root": manifest["source_root"],
        "source_commit": manifest["source_commit"],
        "source_dirty": manifest["source_dirty"],
        "payload_digest": manifest["payload_digest"],
        "history_record": manifest["history_record"],
        "history_state": record_state,
        "history_error": record_error,
        "rollback_available": rollback_available,
        "previous_install_id": previous_install_id,
        "previous_skill_version": previous_skill_version,
        "managed_files": file_status,
        "drift": drift,
        "unmanaged_skill_files": unmanaged,
        "model_calls": 0,
        "writes": [],
    }
