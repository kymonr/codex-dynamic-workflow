"""Read-only installation planning bound to source and current target state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from skill.versioning import VersionError, read_skill_version
except ModuleNotFoundError:
    from versioning import VersionError, read_skill_version

from .contract import (
    INSTALL_CONTRACT_VERSION,
    InstallManagerError,
    canonical_json_bytes,
    payload_digest,
    sha256_bytes,
)
from .filesystem import (
    current_regular_digest,
    git_identity,
    manifest_path,
    payload_entries,
    read_active_transaction,
    read_manifest,
    resolve_codex_home,
    resolve_state_root,
    source_root as resolve_source_root,
    target_identity,
)


def _prior_files(
    manifest: dict[str, Any] | None,
    codex_home: Path,
) -> dict[str, dict[str, Any]]:
    if manifest is None:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in manifest["managed_files"]:
        identity = target_identity(codex_home, entry["target"])
        if identity in result:
            raise InstallManagerError(
                "active manifest contains colliding target identities: "
                f"{result[identity]['target']} and {entry['target']}"
            )
        result[identity] = entry
    return result


def plan_install(
    source_root: Path | str,
    *,
    codex_home: Path | str | None = None,
    state_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build a zero-write installation plan bound to exact current state."""

    source = resolve_source_root(source_root)
    codex = resolve_codex_home(codex_home)
    state = resolve_state_root(state_root)
    try:
        skill_version = read_skill_version(source)
    except VersionError as exc:
        raise InstallManagerError(str(exc)) from exc
    payload = payload_entries(source)
    identity = git_identity(source)
    previous = read_manifest(codex)
    active_transaction = read_active_transaction(state)
    prior = _prior_files(previous, codex)
    blocked: list[dict[str, str]] = []
    planned_files: list[dict[str, Any]] = []

    if active_transaction is not None:
        blocked.append(
            {
                "code": "active_install_transaction",
                "target": active_transaction["record"],
                "detail": (
                    "an incomplete installation transaction must be recovered "
                    "with install-rollback before planning a new apply"
                ),
            }
        )

    payload_by_identity: dict[str, dict[str, Any]] = {}
    for entry in payload:
        item_identity = target_identity(codex, entry["target"])
        if item_identity in payload_by_identity:
            raise InstallManagerError(
                "installation payload contains colliding target identities: "
                f"{payload_by_identity[item_identity]['target']} and {entry['target']}"
            )
        payload_by_identity[item_identity] = entry

    for entry in payload:
        target = entry["target"]
        item_identity = target_identity(codex, target)
        current = current_regular_digest(codex, target)
        prior_entry = prior.get(item_identity)
        current_sha = current[0] if current is not None else None
        if prior_entry is not None and prior_entry["target"] != target:
            action = "blocked_target_identity_collision"
            blocked.append(
                {
                    "code": "target_identity_collision",
                    "target": target,
                    "detail": (
                        "new and previous targets resolve to the same filesystem "
                        f"identity: {prior_entry['target']} vs {target}"
                    ),
                }
            )
        elif prior_entry is not None:
            if current is None:
                action = "blocked_managed_missing"
                blocked.append(
                    {
                        "code": "managed_target_missing",
                        "target": target,
                        "detail": "active manifest expects the target but it is absent",
                    }
                )
            elif current_sha != prior_entry["sha256"]:
                action = "blocked_managed_drift"
                blocked.append(
                    {
                        "code": "managed_target_drift",
                        "target": target,
                        "detail": "target differs from the active manifest",
                    }
                )
            elif current_sha == entry["sha256"]:
                action = "unchanged"
            else:
                action = "replace_managed"
        elif current is None:
            action = "create"
        elif current_sha == entry["sha256"]:
            action = "adopt_existing"
        else:
            action = "replace_unmanaged"
        planned = dict(entry)
        planned.update(
            {
                "action": action,
                "current_sha256": current_sha,
                "previous_sha256": (
                    prior_entry["sha256"] if prior_entry else None
                ),
            }
        )
        planned_files.append(planned)

    stale_files: list[dict[str, Any]] = []
    for item_identity in sorted(
        set(prior) - set(payload_by_identity),
        key=str.casefold,
    ):
        prior_entry = prior[item_identity]
        target = prior_entry["target"]
        current = current_regular_digest(codex, target)
        current_sha = current[0] if current is not None else None
        if current is None:
            action = "blocked_stale_missing"
            blocked.append(
                {
                    "code": "stale_managed_target_missing",
                    "target": target,
                    "detail": (
                        "active manifest expects a stale target but it is absent"
                    ),
                }
            )
        elif current_sha != prior_entry["sha256"]:
            action = "blocked_stale_drift"
            blocked.append(
                {
                    "code": "stale_managed_target_drift",
                    "target": target,
                    "detail": (
                        "stale managed target differs from the active manifest"
                    ),
                }
            )
        else:
            action = "delete_stale_managed"
        stale_files.append(
            {
                "kind": prior_entry["kind"],
                "source": prior_entry["source"],
                "target": target,
                "sha256": prior_entry["sha256"],
                "bytes": prior_entry["bytes"],
                "action": action,
                "current_sha256": current_sha,
            }
        )

    content_digest = payload_digest(payload)
    plan_contract = {
        "version": INSTALL_CONTRACT_VERSION,
        "skill_version": skill_version,
        "source_root": str(source),
        "codex_home": str(codex),
        "state_root": str(state),
        "source_commit": identity["commit"],
        "source_dirty": identity["dirty"],
        "payload_digest": content_digest,
        "previous_install_id": previous["install_id"] if previous else None,
        "previous_skill_version": (
            previous["skill_version"] if previous else None
        ),
        "active_transaction": active_transaction,
        "managed_files": planned_files,
        "stale_files": stale_files,
        "blocked": blocked,
    }
    plan_digest = sha256_bytes(canonical_json_bytes(plan_contract))
    changes = [
        entry
        for entry in [*planned_files, *stale_files]
        if entry["action"]
        in {
            "create",
            "replace_managed",
            "replace_unmanaged",
            "delete_stale_managed",
        }
    ]
    return {
        "operation": "install-plan",
        **plan_contract,
        "plan_digest": plan_digest,
        "ready": not blocked,
        "change_count": len(changes),
        "manifest_path": str(manifest_path(codex)),
        "manual_integration": {
            "required": True,
            "source": str(
                source / "integration" / "AGENTS.dynamic-workflow.md"
            ),
            "target": "workspace AGENTS.md",
            "reason": (
                "workspace rules must be merged manually and never overwritten"
            ),
        },
        "model_calls": 0,
        "writes": [],
    }
