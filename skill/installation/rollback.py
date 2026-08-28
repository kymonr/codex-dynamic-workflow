"""Rollback or recover the single active installation transaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from skill.runtime.path_safety import UnsafeRunPathError
    from skill.runtime.run_lease import RunLease, RunLeaseError
except ModuleNotFoundError:
    from runtime.path_safety import UnsafeRunPathError
    from runtime.run_lease import RunLease, RunLeaseError

from .contract import (
    INSTALL_ID_RE,
    InstallManagerError,
    new_active_transaction,
    now_iso,
    validate_history_record,
)
from .filesystem import (
    atomic_write_json,
    manifest_path,
    read_manifest,
    read_record,
    remove_active_transaction,
    remove_history_record_tree,
    resolve_codex_home,
    resolve_state_root,
    write_active_transaction,
)
from .status import install_status
from .transaction import (
    load_active_transaction,
    publish_previous_manifest,
    require_target_sides,
    restore_targets_before,
)


def _finish_record_and_cleanup(
    *,
    pointer: dict[str, Any],
    record_path: Path,
    record: dict[str, Any],
    state: Path,
) -> tuple[str | None, list[str]]:
    record["state"] = "rolled_back"
    record["rolled_back_at"] = now_iso()
    atomic_write_json(
        record_path,
        record,
        root=state,
        label="installation history record",
    )
    remove_active_transaction(state, expected=pointer)
    cleanup_warnings: list[str] = []
    removed_history: str | None = None
    try:
        removed_history = remove_history_record_tree(
            state, pointer["record"]
        )
    except InstallManagerError as exc:
        cleanup_warnings.append(str(exc))
    return removed_history, cleanup_warnings


def _recover_apply(
    *,
    pointer: dict[str, Any],
    record_path: Path,
    record: dict[str, Any],
    codex: Path,
    state: Path,
) -> dict[str, Any]:
    if record["state"] not in {"prepared", "applied", "rolling_back"}:
        raise InstallManagerError(
            "incomplete apply record state is not recoverable: "
            f"{record['state']}"
        )
    sides = require_target_sides(record, codex)
    if record["state"] != "rolling_back":
        record["state"] = "rolling_back"
        atomic_write_json(
            record_path,
            record,
            root=state,
            label="installation history record",
        )
    restored, removed = restore_targets_before(
        record,
        record_path=record_path,
        state_root=state,
        codex_home=codex,
        sides=sides,
    )
    active_install_id, active_skill_version = publish_previous_manifest(
        record,
        codex_home=codex,
        preserve_rollback=True,
    )
    removed_history, cleanup_warnings = _finish_record_and_cleanup(
        pointer=pointer,
        record_path=record_path,
        record=record,
        state=state,
    )
    return {
        "operation": "install-rollback",
        "state": "apply_recovered",
        "recovered_install_id": pointer["install_id"],
        "recovered_skill_version": record["skill_version"],
        "active_install_id": active_install_id,
        "active_skill_version": active_skill_version,
        "rollback_available": False,
        "restored": sorted(restored, key=str.casefold),
        "removed": sorted(removed, key=str.casefold),
        "removed_history": removed_history,
        "cleanup_warnings": cleanup_warnings,
        "model_calls": 0,
        "writes": [
            *restored,
            *removed,
            str(manifest_path(codex)),
            str(record_path),
        ],
    }


def _complete_rollback(
    *,
    pointer: dict[str, Any],
    record_path: Path,
    record: dict[str, Any],
    codex: Path,
    state: Path,
) -> dict[str, Any]:
    if record["state"] == "rolled_back":
        active_install_id, active_skill_version = publish_previous_manifest(
            record,
            codex_home=codex,
            preserve_rollback=False,
        )
        removed_history, cleanup_warnings = _finish_record_and_cleanup(
            pointer=pointer,
            record_path=record_path,
            record=record,
            state=state,
        )
        return {
            "operation": "install-rollback",
            "state": "rolled_back",
            "rolled_back_install_id": pointer["install_id"],
            "rolled_back_skill_version": record["skill_version"],
            "active_install_id": active_install_id,
            "active_skill_version": active_skill_version,
            "rollback_available": False,
            "restored": [],
            "removed": [],
            "removed_history": removed_history,
            "cleanup_warnings": cleanup_warnings,
            "model_calls": 0,
            "writes": [str(manifest_path(codex)), str(record_path)],
        }

    if record["state"] not in {"applied", "prepared", "rolling_back"}:
        raise InstallManagerError(
            "installation history state is not rollback-ready: "
            f"{record['state']}"
        )
    sides = require_target_sides(record, codex)
    if record["state"] != "rolling_back":
        record["state"] = "rolling_back"
        atomic_write_json(
            record_path,
            record,
            root=state,
            label="installation history record",
        )
    restored, removed = restore_targets_before(
        record,
        record_path=record_path,
        state_root=state,
        codex_home=codex,
        sides=sides,
    )
    active_install_id, active_skill_version = publish_previous_manifest(
        record,
        codex_home=codex,
        preserve_rollback=False,
    )
    removed_history, cleanup_warnings = _finish_record_and_cleanup(
        pointer=pointer,
        record_path=record_path,
        record=record,
        state=state,
    )
    return {
        "operation": "install-rollback",
        "state": "rolled_back",
        "rolled_back_install_id": pointer["install_id"],
        "rolled_back_skill_version": record["skill_version"],
        "active_install_id": active_install_id,
        "active_skill_version": active_skill_version,
        "rollback_available": False,
        "restored": sorted(restored, key=str.casefold),
        "removed": sorted(removed, key=str.casefold),
        "removed_history": removed_history,
        "cleanup_warnings": cleanup_warnings,
        "model_calls": 0,
        "writes": [
            *restored,
            *removed,
            str(manifest_path(codex)),
            str(record_path),
        ],
    }


def rollback_install(
    *,
    expected_install_id: str,
    ack_rollback: bool,
    codex_home: Path | str | None = None,
    state_root: Path | str | None = None,
) -> dict[str, Any]:
    """Restore the exact target state immediately preceding one transaction."""
    if not ack_rollback:
        raise InstallManagerError("install-rollback requires --ack-rollback")
    if not INSTALL_ID_RE.fullmatch(expected_install_id):
        raise InstallManagerError("expected install id is invalid")
    codex = resolve_codex_home(codex_home)
    state = resolve_state_root(state_root)

    try:
        with RunLease(state / "install-manager"):
            pending = load_active_transaction(state, codex)
            if pending is not None:
                pointer, record_path, record = pending
                if pointer["install_id"] != expected_install_id:
                    raise InstallManagerError(
                        "active transaction id changed; rerun install-status"
                    )
                if pointer["operation"] == "apply":
                    return _recover_apply(
                        pointer=pointer,
                        record_path=record_path,
                        record=record,
                        codex=codex,
                        state=state,
                    )
                return _complete_rollback(
                    pointer=pointer,
                    record_path=record_path,
                    record=record,
                    codex=codex,
                    state=state,
                )

            manifest = read_manifest(codex)
            if manifest is None:
                raise InstallManagerError(
                    "there is no active installation to roll back"
                )
            if manifest["install_id"] != expected_install_id:
                raise InstallManagerError(
                    "active install id changed; rerun install-status before rollback"
                )
            if manifest["history_record"] is None:
                raise InstallManagerError(
                    "the active installation has no previous rollback snapshot"
                )
            status = install_status(codex_home=codex, state_root=state)
            record_path, record = read_record(
                state, manifest["history_record"]
            )
            record = validate_history_record(
                record,
                manifest=manifest,
                codex_home=str(codex),
            )
            if (
                record["state"] in {"applied", "prepared"}
                and status["state"]
                not in {"clean", "clean_with_unmanaged_files"}
            ):
                raise InstallManagerError(
                    f"active installation is not clean: {status['state']}"
                )

            pointer = new_active_transaction(
                operation="rollback",
                install_id=manifest["install_id"],
            )
            write_active_transaction(state, pointer)
            return _complete_rollback(
                pointer=pointer,
                record_path=record_path,
                record=record,
                codex=codex,
                state=state,
            )
    except (RunLeaseError, UnsafeRunPathError, OSError) as exc:
        raise InstallManagerError(str(exc)) from exc
