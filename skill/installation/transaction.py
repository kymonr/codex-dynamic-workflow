"""Discover and recover one in-progress installation transaction."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .contract import (
    InstallManagerError,
    canonical_json_bytes,
    sha256_bytes,
    validate_install_record,
)
from .filesystem import (
    assert_safe_regular_file,
    atomic_write_bytes,
    atomic_write_json,
    current_regular_digest,
    manifest_path,
    read_active_transaction,
    read_manifest,
    read_record,
    safe_target,
)


def load_active_transaction(
    state_root: Path,
    codex_home: Path,
) -> tuple[dict[str, Any], Path, dict[str, Any]] | None:
    """Load and cross-check the fixed transaction pointer and its record."""

    pointer = read_active_transaction(state_root)
    if pointer is None:
        return None
    record_path, raw_record = read_record(state_root, pointer["record"])
    record = validate_install_record(
        raw_record,
        codex_home=str(codex_home),
        label="active installation transaction record",
    )
    if record["install_id"] != pointer["install_id"]:
        raise InstallManagerError(
            "active installation transaction pointer/record identity mismatch"
        )
    return pointer, record_path, record


def inspect_target_sides(
    record: dict[str, Any],
    codex_home: Path,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Classify each transaction target as its exact before or after side."""

    sides: dict[str, str] = {}
    issues: list[dict[str, Any]] = []
    for change in record["changes"]:
        target = change["target"]
        before = change["before"]
        after = change["after"]
        try:
            current = current_regular_digest(codex_home, target)
        except InstallManagerError as exc:
            issues.append(
                {
                    "target": target,
                    "status": "unsafe",
                    "detail": str(exc),
                }
            )
            continue
        exists = current is not None
        current_sha = current[0] if current is not None else None
        matches_before = exists == before["exists"] and (
            not exists or current_sha == before["sha256"]
        )
        matches_after = exists == after["exists"] and (
            not exists or current_sha == after["sha256"]
        )
        if matches_after:
            sides[target] = "after"
        elif matches_before:
            sides[target] = "before"
        else:
            issues.append(
                {
                    "target": target,
                    "status": "neither_before_nor_after",
                    "current_sha256": current_sha,
                    "before_sha256": before["sha256"],
                    "after_sha256": after["sha256"],
                }
            )
    return sides, issues


def require_target_sides(
    record: dict[str, Any],
    codex_home: Path,
) -> dict[str, str]:
    sides, issues = inspect_target_sides(record, codex_home)
    if issues:
        targets = ", ".join(issue["target"] for issue in issues)
        raise InstallManagerError(
            "installation transaction targets are not recoverable: " + targets
        )
    return sides


def _published_previous_manifest(
    record: dict[str, Any],
    *,
    preserve_rollback: bool,
) -> dict[str, Any] | None:
    previous = record["previous_manifest"]
    if previous is None:
        return None
    published = copy.deepcopy(previous)
    if not preserve_rollback:
        published["history_record"] = None
    return published


def _same_manifest(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def manifest_side(
    record: dict[str, Any],
    codex_home: Path,
    *,
    preserve_rollback: bool,
) -> str:
    """Return whether the active manifest is on the before or after side."""

    current = read_manifest(codex_home)
    previous = _published_previous_manifest(
        record,
        preserve_rollback=preserve_rollback,
    )
    if current is None:
        if previous is None:
            return "before"
        raise InstallManagerError(
            "active manifest is missing while the transaction expects a previous install"
        )
    if previous is not None and _same_manifest(current, previous):
        return "before"
    if (
        current["install_id"] == record["install_id"]
        and current["skill_version"] == record["skill_version"]
        and current["payload_digest"] == record["payload_digest"]
        and current["applied_plan_digest"] == record["plan_digest"]
    ):
        return "after"
    raise InstallManagerError(
        "active manifest is neither the transaction before nor after state"
    )


def restore_targets_before(
    record: dict[str, Any],
    *,
    record_path: Path,
    state_root: Path,
    codex_home: Path,
    sides: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Restore every after-side target to its exact before state."""

    history = record_path.parent
    restored: list[str] = []
    removed: list[str] = []
    for change in reversed(record["changes"]):
        target = change["target"]
        if sides[target] == "before":
            continue
        target_path = safe_target(
            codex_home, target, label="managed installation target"
        )
        before = change["before"]
        if before["exists"]:
            backup = safe_target(
                history,
                before["backup"],
                label="installation backup file",
            )
            assert_safe_regular_file(
                backup, root=state_root, label="installation backup file"
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
                root=codex_home,
                label="managed rollback target",
            )
            restored.append(target)
        else:
            current = current_regular_digest(codex_home, target)
            if current is not None:
                assert_safe_regular_file(
                    target_path,
                    root=codex_home,
                    label="managed rollback target",
                )
                try:
                    target_path.unlink()
                except OSError as exc:
                    raise InstallManagerError(
                        f"cannot remove created target during recovery {target_path}: {exc}"
                    ) from exc
            removed.append(target)
    return restored, removed


def publish_previous_manifest(
    record: dict[str, Any],
    *,
    codex_home: Path,
    preserve_rollback: bool,
) -> tuple[str | None, str | None]:
    """Idempotently restore or remove the manifest preceding the transaction."""

    side = manifest_side(
        record,
        codex_home,
        preserve_rollback=preserve_rollback,
    )
    previous = _published_previous_manifest(
        record,
        preserve_rollback=preserve_rollback,
    )
    if side == "after":
        active_path = manifest_path(codex_home)
        if previous is None:
            assert_safe_regular_file(
                active_path,
                root=codex_home,
                label="active installation manifest",
            )
            try:
                active_path.unlink()
            except OSError as exc:
                raise InstallManagerError(
                    f"cannot remove active installation manifest {active_path}: {exc}"
                ) from exc
        else:
            atomic_write_json(
                active_path,
                previous,
                root=codex_home,
                label="active installation manifest",
            )
    if previous is None:
        return None, None
    return previous["install_id"], previous["skill_version"]
