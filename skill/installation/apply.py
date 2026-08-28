"""Apply one exact personal installation plan."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

try:
    from skill.runtime.path_safety import UnsafeRunPathError, assert_safe_descendant, lexists
    from skill.runtime.run_lease import RunLease, RunLeaseError
except ModuleNotFoundError:
    from runtime.path_safety import UnsafeRunPathError, assert_safe_descendant, lexists
    from runtime.run_lease import RunLease, RunLeaseError

from .contract import (
    INSTALL_CONTRACT_VERSION,
    InstallManagerError,
    new_install_id,
    now_iso,
    record_relative,
    sha256_bytes,
    validate_expected_digest,
)
from .filesystem import (
    assert_safe_regular_file,
    atomic_write_bytes,
    atomic_write_json,
    copy_backup,
    current_regular_digest,
    history_dir,
    manifest_path,
    read_manifest,
    resolve_codex_home,
    resolve_state_root,
    safe_target,
    sha256_file,
)
from .planner import plan_install


def apply_install(
    source_root: Path | str,
    *,
    expected_plan_digest: str,
    ack_install: bool,
    codex_home: Path | str | None = None,
    state_root: Path | str | None = None,
) -> dict[str, Any]:
    """Apply one exact plan and publish an active manifest last."""

    if not ack_install:
        raise InstallManagerError("install-apply requires --ack-install")
    validate_expected_digest(expected_plan_digest, label="expected plan digest")
    codex = resolve_codex_home(codex_home)
    state = resolve_state_root(state_root)

    try:
        with RunLease(state / "install-manager"):
            plan = plan_install(
                source_root,
                codex_home=codex,
                state_root=state,
            )
            if plan["plan_digest"] != expected_plan_digest:
                raise InstallManagerError(
                    "installation plan changed; rerun install-plan and use its exact digest"
                )
            if not plan["ready"]:
                codes = ", ".join(item["code"] for item in plan["blocked"])
                raise InstallManagerError(f"installation plan is blocked: {codes}")

            previous = read_manifest(codex)
            same_identity = bool(
                previous
                and previous["payload_digest"] == plan["payload_digest"]
                and previous["source_commit"] == plan["source_commit"]
                and previous["source_dirty"] == plan["source_dirty"]
                and plan["change_count"] == 0
            )
            if same_identity:
                return {
                    "operation": "install-apply",
                    "state": "already_current",
                    "install_id": previous["install_id"],
                    "plan_digest": plan["plan_digest"],
                    "payload_digest": plan["payload_digest"],
                    "model_calls": 0,
                    "writes": [],
                }

            install_id = new_install_id(plan["plan_digest"])
            history = history_dir(state, install_id)
            if lexists(history):
                raise InstallManagerError(f"installation history already exists: {history}")
            history.mkdir(parents=True, exist_ok=False)
            try:
                assert_safe_descendant(
                    state, history, label="installation history directory"
                )
            except UnsafeRunPathError as exc:
                raise InstallManagerError(str(exc)) from exc

            changes: list[dict[str, Any]] = []
            source = Path(plan["source_root"])
            for entry in [*plan["managed_files"], *plan["stale_files"]]:
                action = entry["action"]
                if action not in {
                    "create",
                    "replace_managed",
                    "replace_unmanaged",
                    "delete_stale_managed",
                }:
                    continue
                target = entry["target"]
                target_path = safe_target(
                    codex, target, label="managed installation target"
                )
                before_exists = lexists(target_path)
                if action == "create" and before_exists:
                    raise InstallManagerError(
                        f"create target appeared after planning: {target}"
                    )
                if action != "create" and not before_exists:
                    raise InstallManagerError(
                        f"managed target disappeared after planning: {target}"
                    )
                before: dict[str, Any] = {
                    "exists": before_exists,
                    "sha256": None,
                    "backup": None,
                }
                if before_exists:
                    assert_safe_regular_file(
                        target_path,
                        root=codex,
                        label="managed installation target",
                    )
                    current_sha, _ = sha256_file(target_path)
                    expected_current = entry["current_sha256"]
                    if current_sha != expected_current:
                        raise InstallManagerError(
                            f"managed target changed after planning: {target}"
                        )
                    before["sha256"] = current_sha
                    before["backup"] = copy_backup(
                        target_path,
                        target=target,
                        codex_home=codex,
                        history=history,
                        state_root=state,
                        expected_sha256=current_sha,
                    )
                changes.append(
                    {
                        "target": target,
                        "action": action,
                        "before": before,
                        "after": {
                            "exists": action != "delete_stale_managed",
                            "sha256": (
                                None
                                if action == "delete_stale_managed"
                                else entry["sha256"]
                            ),
                        },
                    }
                )

            record_relative_path = record_relative(install_id)
            record_path = safe_target(
                state,
                record_relative_path,
                label="installation history record",
            )
            record = {
                "version": INSTALL_CONTRACT_VERSION,
                "install_id": install_id,
                "state": "prepared",
                "prepared_at": now_iso(),
                "applied_at": None,
                "rolled_back_at": None,
                "plan_digest": plan["plan_digest"],
                "payload_digest": plan["payload_digest"],
                "codex_home": str(codex),
                "previous_manifest": previous,
                "changes": changes,
            }
            atomic_write_json(
                record_path,
                record,
                root=state,
                label="installation history record",
            )

            for entry in plan["managed_files"]:
                if entry["action"] not in {
                    "create",
                    "replace_managed",
                    "replace_unmanaged",
                }:
                    continue
                source_path = source.joinpath(*PurePosixPath(entry["source"]).parts)
                assert_safe_regular_file(
                    source_path, root=source, label="installation source file"
                )
                try:
                    payload = source_path.read_bytes()
                except OSError as exc:
                    raise InstallManagerError(
                        f"cannot read installation source file {source_path}: {exc}"
                    ) from exc
                if sha256_bytes(payload) != entry["sha256"]:
                    raise InstallManagerError(
                        f"installation source changed after planning: {entry['source']}"
                    )
                atomic_write_bytes(
                    safe_target(
                        codex,
                        entry["target"],
                        label="managed installation target",
                    ),
                    payload,
                    root=codex,
                    label="managed installation target",
                )

            for entry in plan["stale_files"]:
                if entry["action"] != "delete_stale_managed":
                    continue
                target_path = safe_target(
                    codex,
                    entry["target"],
                    label="stale managed installation target",
                )
                if not lexists(target_path):
                    raise InstallManagerError(
                        "stale managed target disappeared after planning: "
                        f"{entry['target']}"
                    )
                assert_safe_regular_file(
                    target_path,
                    root=codex,
                    label="stale managed installation target",
                )
                current_sha, _ = sha256_file(target_path)
                if current_sha != entry["current_sha256"]:
                    raise InstallManagerError(
                        f"stale managed target changed after planning: {entry['target']}"
                    )
                try:
                    target_path.unlink()
                except OSError as exc:
                    raise InstallManagerError(
                        f"cannot delete stale managed target {target_path}: {exc}"
                    ) from exc

            for entry in plan["managed_files"]:
                current = current_regular_digest(codex, entry["target"])
                if current is None or current[0] != entry["sha256"]:
                    raise InstallManagerError(
                        "managed target verification failed before manifest publish: "
                        f"{entry['target']}"
                    )
            for entry in plan["stale_files"]:
                if (
                    entry["action"] == "delete_stale_managed"
                    and current_regular_digest(codex, entry["target"]) is not None
                ):
                    raise InstallManagerError(
                        "stale managed target still exists before manifest publish: "
                        f"{entry['target']}"
                    )

            managed_files = [
                {
                    "kind": entry["kind"],
                    "source": entry["source"],
                    "target": entry["target"],
                    "sha256": entry["sha256"],
                    "bytes": entry["bytes"],
                }
                for entry in plan["managed_files"]
            ]
            manifest = {
                "version": INSTALL_CONTRACT_VERSION,
                "install_id": install_id,
                "installed_at": now_iso(),
                "source_root": plan["source_root"],
                "source_commit": plan["source_commit"],
                "source_dirty": plan["source_dirty"],
                "payload_digest": plan["payload_digest"],
                "applied_plan_digest": plan["plan_digest"],
                "history_record": record_relative_path,
                "managed_files": managed_files,
            }
            active_manifest_path = manifest_path(codex)
            atomic_write_json(
                active_manifest_path,
                manifest,
                root=codex,
                label="active installation manifest",
            )
            record["state"] = "applied"
            record["applied_at"] = now_iso()
            atomic_write_json(
                record_path,
                record,
                root=state,
                label="installation history record",
            )
            writes = [change["target"] for change in changes]
            writes.extend([str(active_manifest_path), str(record_path)])
            return {
                "operation": "install-apply",
                "state": "applied",
                "install_id": install_id,
                "previous_install_id": previous["install_id"] if previous else None,
                "plan_digest": plan["plan_digest"],
                "payload_digest": plan["payload_digest"],
                "source_commit": plan["source_commit"],
                "source_dirty": plan["source_dirty"],
                "manifest_path": str(active_manifest_path),
                "history_record": str(record_path),
                "change_count": len(changes),
                "manual_integration": plan["manual_integration"],
                "model_calls": 0,
                "writes": writes,
            }
    except (RunLeaseError, UnsafeRunPathError) as exc:
        raise InstallManagerError(str(exc)) from exc
