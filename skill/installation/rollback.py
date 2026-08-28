"""Rollback the active personal installation by one exact history record."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from skill.runtime.path_safety import UnsafeRunPathError, lexists
    from skill.runtime.run_lease import RunLease, RunLeaseError
except ModuleNotFoundError:
    from runtime.path_safety import UnsafeRunPathError, lexists
    from runtime.run_lease import RunLease, RunLeaseError

from .contract import (
    INSTALL_ID_RE,
    InstallManagerError,
    change_contract,
    now_iso,
    sha256_bytes,
    validate_history_record,
    validate_manifest,
)
from .filesystem import (
    assert_safe_regular_file,
    atomic_write_bytes,
    atomic_write_json,
    manifest_path,
    read_manifest,
    read_record,
    resolve_codex_home,
    resolve_state_root,
    safe_target,
    sha256_file,
)
from .status import install_status


def rollback_install(
    *,
    expected_install_id: str,
    ack_rollback: bool,
    codex_home: Path | str | None = None,
    state_root: Path | str | None = None,
) -> dict[str, Any]:
    """Restore the exact pre-install target state for the active installation."""

    if not ack_rollback:
        raise InstallManagerError("install-rollback requires --ack-rollback")
    if not INSTALL_ID_RE.fullmatch(expected_install_id):
        raise InstallManagerError("expected install id is invalid")
    codex = resolve_codex_home(codex_home)
    state = resolve_state_root(state_root)

    try:
        with RunLease(state / "install-manager"):
            manifest = read_manifest(codex)
            if manifest is None:
                raise InstallManagerError("there is no active installation to roll back")
            if manifest["install_id"] != expected_install_id:
                raise InstallManagerError(
                    "active install id changed; rerun install-status before rollback"
                )
            status = install_status(codex_home=codex, state_root=state)
            record_path, record = read_record(state, manifest["history_record"])
            validate_history_record(
                record, manifest=manifest, codex_home=str(codex)
            )
            record_state = record["state"]
            if record_state not in {"applied", "prepared", "rolling_back"}:
                raise InstallManagerError(
                    f"installation history state is not rollback-ready: {record_state}"
                )
            if (
                record_state in {"applied", "prepared"}
                and status["state"] not in {"clean", "clean_with_unmanaged_files"}
            ):
                raise InstallManagerError(
                    f"active installation is not clean: {status['state']}"
                )

            raw_changes = record["changes"]
            changes = [
                change_contract(change, index=index)
                for index, change in enumerate(raw_changes)
            ]
            history = record_path.parent
            current_sides: dict[str, str] = {}
            seen_targets: set[str] = set()
            for change in changes:
                target = change["target"]
                key = target.casefold()
                if key in seen_targets:
                    raise InstallManagerError(
                        f"installation history contains duplicate target: {target}"
                    )
                seen_targets.add(key)
                target_path = safe_target(
                    codex, target, label="managed installation target"
                )
                before = change["before"]
                after = change["after"]
                exists = lexists(target_path)
                current_sha: str | None = None
                if exists:
                    assert_safe_regular_file(
                        target_path,
                        root=codex,
                        label="managed installation target",
                    )
                    current_sha, _ = sha256_file(target_path)
                matches_after = exists == after["exists"] and (
                    not exists or current_sha == after["sha256"]
                )
                matches_before = exists == before["exists"] and (
                    not exists or current_sha == before["sha256"]
                )
                if matches_after:
                    current_sides[target] = "after"
                elif record_state == "rolling_back" and matches_before:
                    current_sides[target] = "before"
                else:
                    raise InstallManagerError(
                        f"managed target changed before rollback: {target}"
                    )

            record["state"] = "rolling_back"
            atomic_write_json(
                record_path,
                record,
                root=state,
                label="installation history record",
            )

            restored: list[str] = []
            removed: list[str] = []
            for change in reversed(changes):
                target = change["target"]
                if current_sides[target] == "before":
                    continue
                target_path = safe_target(
                    codex, target, label="managed installation target"
                )
                before = change["before"]
                if before["exists"]:
                    backup = safe_target(
                        history,
                        before["backup"],
                        label="installation backup file",
                    )
                    assert_safe_regular_file(
                        backup, root=state, label="installation backup file"
                    )
                    try:
                        payload = backup.read_bytes()
                    except OSError as exc:
                        raise InstallManagerError(
                            f"cannot read installation backup {backup}: {exc}"
                        ) from exc
                    if sha256_bytes(payload) != before["sha256"]:
                        raise InstallManagerError(
                            f"installation backup digest mismatch: {target}"
                        )
                    atomic_write_bytes(
                        target_path,
                        payload,
                        root=codex,
                        label="managed rollback target",
                    )
                    restored.append(target)
                else:
                    if lexists(target_path):
                        assert_safe_regular_file(
                            target_path,
                            root=codex,
                            label="managed rollback target",
                        )
                        try:
                            target_path.unlink()
                        except OSError as exc:
                            raise InstallManagerError(
                                "cannot remove created target during rollback "
                                f"{target_path}: {exc}"
                            ) from exc
                    removed.append(target)

            previous = record.get("previous_manifest")
            active_manifest_path = manifest_path(codex)
            if previous is None:
                if lexists(active_manifest_path):
                    assert_safe_regular_file(
                        active_manifest_path,
                        root=codex,
                        label="active installation manifest",
                    )
                    active_manifest_path.unlink()
                active_install_id = None
            else:
                previous_manifest = validate_manifest(
                    previous, label="previous installation manifest"
                )
                atomic_write_json(
                    active_manifest_path,
                    previous_manifest,
                    root=codex,
                    label="active installation manifest",
                )
                active_install_id = previous_manifest["install_id"]

            record["state"] = "rolled_back"
            record["rolled_back_at"] = now_iso()
            atomic_write_json(
                record_path,
                record,
                root=state,
                label="installation history record",
            )
            return {
                "operation": "install-rollback",
                "state": "rolled_back",
                "rolled_back_install_id": expected_install_id,
                "active_install_id": active_install_id,
                "restored": sorted(restored, key=str.casefold),
                "removed": sorted(removed, key=str.casefold),
                "history_record": str(record_path),
                "model_calls": 0,
                "writes": [
                    *restored,
                    *removed,
                    str(active_manifest_path),
                    str(record_path),
                ],
            }
    except (RunLeaseError, UnsafeRunPathError, OSError) as exc:
        raise InstallManagerError(str(exc)) from exc
