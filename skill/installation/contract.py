"""Versioned metadata contracts for one-step personal installation rollback."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import secrets
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

try:
    from skill.versioning import VersionError, parse_version
except ModuleNotFoundError:
    from versioning import VersionError, parse_version

INSTALL_CONTRACT_VERSION = 1
MANIFEST_FILENAME = ".dynamic-workflow-install.json"
INSTALL_HISTORY_DIRNAME = "installations"
SKILL_TARGET = PurePosixPath("skills/dynamic-workflow")
AGENTS_TARGET = PurePosixPath("agents")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
INSTALL_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-[0-9a-f]{8}$")
EXCLUDED_DIR_NAMES = {"__pycache__"}
EXCLUDED_FILE_NAMES = {MANIFEST_FILENAME, ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
ACTIVE_TRANSACTION_RELATIVE = PurePosixPath(
    "install-manager", "active-transaction.json"
)
TRANSACTION_OPERATIONS = {"apply", "rollback"}


class InstallManagerError(RuntimeError):
    """The requested installation operation cannot continue safely."""


def validate_skill_version(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise InstallManagerError(f"{label} must be a string")
    try:
        parse_version(value, label=label)
    except VersionError as exc:
        raise InstallManagerError(str(exc)) from exc
    return value


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InstallManagerError(f"cannot encode installation metadata: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_json_loads(payload: str, *, label: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InstallManagerError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise InstallManagerError(f"{label} contains non-finite number {value}")

    try:
        return json.loads(
            payload,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except InstallManagerError:
        raise
    except json.JSONDecodeError as exc:
        raise InstallManagerError(f"{label} is not valid JSON: {exc}") from exc


def canonical_posix_relative(value: Any, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InstallManagerError(f"{label} is not a canonical POSIX relative path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != value
    ):
        raise InstallManagerError(f"{label} is not a canonical POSIX relative path")
    return relative


def safe_relative_target_contract(
    target: str,
    label: str,
) -> PurePosixPath:
    relative = canonical_posix_relative(target, label=f"{label}.target")
    is_skill = (
        tuple(SKILL_TARGET.parts)
        == tuple(relative.parts[: len(SKILL_TARGET.parts)])
        and len(relative.parts) > len(SKILL_TARGET.parts)
    )
    is_agent = (
        relative.parts[:1] == tuple(AGENTS_TARGET.parts)
        and len(relative.parts) == 2
        and relative.suffix == ".toml"
    )
    if not (is_skill or is_agent):
        raise InstallManagerError(
            f"{label}.target is outside managed roots: {target!r}"
        )
    return relative


def validate_managed_files(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise InstallManagerError(f"{label}.managed_files must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        where = f"{label}.managed_files[{index}]"
        if not isinstance(item, dict):
            raise InstallManagerError(f"{where} must be an object")
        required = {"kind", "source", "target", "sha256", "bytes"}
        if set(item) != required:
            raise InstallManagerError(
                f"{where} keys must be exactly {sorted(required)!r}"
            )
        kind = item.get("kind")
        source = item.get("source")
        target = item.get("target")
        digest = item.get("sha256")
        size = item.get("bytes")
        if kind not in {"skill", "agent"}:
            raise InstallManagerError(f"{where}.kind is invalid")
        source_path = canonical_posix_relative(source, label=f"{where}.source")
        target_path = safe_relative_target_contract(target, where)
        if kind == "skill":
            if source_path.parts[:1] != ("skill",) or len(source_path.parts) < 2:
                raise InstallManagerError(f"{where}.source is not a Skill path")
            if tuple(target_path.parts[: len(SKILL_TARGET.parts)]) != tuple(
                SKILL_TARGET.parts
            ):
                raise InstallManagerError(f"{where}.target/kind mismatch")
        else:
            if (
                source_path.parts[:2] != ("config", "agents")
                or len(source_path.parts) != 3
                or source_path.suffix != ".toml"
            ):
                raise InstallManagerError(f"{where}.source is not an agent path")
            if target_path.parts[:1] != tuple(AGENTS_TARGET.parts):
                raise InstallManagerError(f"{where}.target/kind mismatch")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise InstallManagerError(f"{where}.sha256 is invalid")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise InstallManagerError(f"{where}.bytes is invalid")
        key = target.casefold()
        if key in seen:
            raise InstallManagerError(f"{label} contains duplicate target {target!r}")
        seen.add(key)
        result.append(dict(item))
    return result


def _validate_history_reference(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    history_path = canonical_posix_relative(
        value, label=f"{label}.history_record"
    )
    if (
        len(history_path.parts) != 3
        or history_path.parts[0] != INSTALL_HISTORY_DIRNAME
        or not INSTALL_ID_RE.fullmatch(history_path.parts[1])
        or history_path.name != "record.json"
    ):
        raise InstallManagerError(f"{label}.history_record shape is invalid")
    return value


def validate_manifest(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InstallManagerError(f"{label} must be an object")
    required = {
        "version",
        "install_id",
        "installed_at",
        "skill_version",
        "source_root",
        "source_commit",
        "source_dirty",
        "payload_digest",
        "applied_plan_digest",
        "history_record",
        "managed_files",
    }
    if set(value) != required:
        raise InstallManagerError(f"{label} keys must be exactly {sorted(required)!r}")
    if value.get("version") != INSTALL_CONTRACT_VERSION:
        raise InstallManagerError(f"{label}.version is unsupported")
    install_id = value.get("install_id")
    if not isinstance(install_id, str) or not INSTALL_ID_RE.fullmatch(install_id):
        raise InstallManagerError(f"{label}.install_id is invalid")
    if not isinstance(value.get("installed_at"), str) or not value["installed_at"]:
        raise InstallManagerError(f"{label}.installed_at is invalid")
    validate_skill_version(value.get("skill_version"), label=f"{label}.skill_version")
    if not isinstance(value.get("source_root"), str) or not value["source_root"]:
        raise InstallManagerError(f"{label}.source_root is invalid")
    commit = value.get("source_commit")
    if commit is not None and (
        not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit)
    ):
        raise InstallManagerError(f"{label}.source_commit is invalid")
    dirty = value.get("source_dirty")
    if dirty is not None and not isinstance(dirty, bool):
        raise InstallManagerError(f"{label}.source_dirty is invalid")
    for key in ("payload_digest", "applied_plan_digest"):
        digest = value.get(key)
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise InstallManagerError(f"{label}.{key} is invalid")
    _validate_history_reference(value.get("history_record"), label=label)
    normalized = dict(value)
    normalized["managed_files"] = validate_managed_files(
        value.get("managed_files"), label=label
    )
    return normalized


def validate_install_record(
    record: Any,
    *,
    codex_home: str,
    label: str = "installation history record",
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise InstallManagerError(f"{label} must be an object")
    required = {
        "version", "install_id", "skill_version", "state",
        "prepared_at", "applied_at", "rolled_back_at",
        "plan_digest", "payload_digest", "codex_home",
        "previous_manifest", "changes",
    }
    if set(record) != required:
        raise InstallManagerError(
            f"{label} keys must be exactly {sorted(required)!r}"
        )
    if record.get("version") != INSTALL_CONTRACT_VERSION:
        raise InstallManagerError(f"{label} version is unsupported")
    install_id = record.get("install_id")
    if not isinstance(install_id, str) or not INSTALL_ID_RE.fullmatch(install_id):
        raise InstallManagerError(f"{label} install id is invalid")
    validate_skill_version(
        record.get("skill_version"), label=f"{label}.skill_version"
    )
    if record.get("state") not in {
        "prepared", "applied", "rolling_back", "rolled_back"
    }:
        raise InstallManagerError(f"{label} state is invalid")
    if not isinstance(record.get("prepared_at"), str) or not record["prepared_at"]:
        raise InstallManagerError(f"{label}.prepared_at is invalid")
    for key in ("applied_at", "rolled_back_at"):
        value = record.get(key)
        if value is not None and (not isinstance(value, str) or not value):
            raise InstallManagerError(f"{label}.{key} is invalid")
    for key in ("plan_digest", "payload_digest"):
        value = record.get(key)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            raise InstallManagerError(f"{label}.{key} is invalid")
    if record.get("codex_home") != codex_home:
        raise InstallManagerError(f"{label} Codex home mismatch")
    previous = record.get("previous_manifest")
    normalized_previous = None
    if previous is not None:
        normalized_previous = validate_manifest(
            previous, label="previous installation manifest"
        )
    changes_value = record.get("changes")
    if not isinstance(changes_value, list):
        raise InstallManagerError(f"{label}.changes must be a list")
    changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(changes_value):
        change = change_contract(value, index=index)
        key = change["target"].casefold()
        if key in seen:
            raise InstallManagerError(
                f"{label} contains duplicate target {change['target']!r}"
            )
        seen.add(key)
        changes.append(change)
    normalized = dict(record)
    normalized["previous_manifest"] = normalized_previous
    normalized["changes"] = changes
    return normalized


def validate_history_record(
    record: dict[str, Any],
    *,
    manifest: dict[str, Any],
    codex_home: str,
) -> dict[str, Any]:
    normalized = validate_install_record(
        record,
        codex_home=codex_home,
        label="installation history record",
    )
    if normalized["install_id"] != manifest["install_id"]:
        raise InstallManagerError("installation history record identity mismatch")
    if normalized["skill_version"] != manifest["skill_version"]:
        raise InstallManagerError(
            "installation history record skill version mismatch"
        )
    if normalized["plan_digest"] != manifest["applied_plan_digest"]:
        raise InstallManagerError(
            "installation history record plan digest mismatch"
        )
    if normalized["payload_digest"] != manifest["payload_digest"]:
        raise InstallManagerError(
            "installation history record payload digest mismatch"
        )
    return normalized

def change_contract(change: Any, *, index: int) -> dict[str, Any]:
    where = f"installation history record changes[{index}]"
    if not isinstance(change, dict):
        raise InstallManagerError(f"{where} must be an object")
    required = {"target", "action", "before", "after"}
    if set(change) != required:
        raise InstallManagerError(f"{where} keys must be exactly {sorted(required)!r}")
    target = change.get("target")
    if not isinstance(target, str):
        raise InstallManagerError(f"{where}.target is invalid")
    safe_relative_target_contract(target, where)
    action = change.get("action")
    if action not in {
        "create",
        "replace_managed",
        "replace_unmanaged",
        "delete_stale_managed",
    }:
        raise InstallManagerError(f"{where}.action is invalid")
    before = change.get("before")
    after = change.get("after")
    if not isinstance(before, dict) or set(before) != {
        "exists",
        "sha256",
        "backup",
    }:
        raise InstallManagerError(f"{where}.before is invalid")
    if not isinstance(after, dict) or set(after) != {"exists", "sha256"}:
        raise InstallManagerError(f"{where}.after is invalid")
    if not isinstance(before["exists"], bool) or not isinstance(after["exists"], bool):
        raise InstallManagerError(f"{where} existence flags are invalid")
    if before["exists"]:
        if not isinstance(before["sha256"], str) or not SHA256_RE.fullmatch(
            before["sha256"]
        ):
            raise InstallManagerError(f"{where}.before.sha256 is invalid")
        expected_backup = backup_relative(target)
        if before["backup"] != expected_backup:
            raise InstallManagerError(f"{where}.before.backup is invalid")
        canonical_posix_relative(
            before["backup"], label=f"{where}.before.backup"
        )
    elif before["sha256"] is not None or before["backup"] is not None:
        raise InstallManagerError(f"{where}.before absent contract is invalid")
    if after["exists"]:
        if not isinstance(after["sha256"], str) or not SHA256_RE.fullmatch(
            after["sha256"]
        ):
            raise InstallManagerError(f"{where}.after.sha256 is invalid")
    elif after["sha256"] is not None:
        raise InstallManagerError(f"{where}.after absent contract is invalid")
    if action == "create" and (before["exists"] or not after["exists"]):
        raise InstallManagerError(f"{where} create sides are invalid")
    if action == "delete_stale_managed" and (
        not before["exists"] or after["exists"]
    ):
        raise InstallManagerError(f"{where} delete sides are invalid")
    if action in {"replace_managed", "replace_unmanaged"} and (
        not before["exists"] or not after["exists"]
    ):
        raise InstallManagerError(f"{where} replace sides are invalid")
    return dict(change)


def validate_expected_digest(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise InstallManagerError(f"{label} must be a lowercase SHA-256 digest")


def new_install_id(plan_digest: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{plan_digest[:12]}-{secrets.token_hex(4)}"


def record_relative(install_id: str) -> str:
    return PurePosixPath(INSTALL_HISTORY_DIRNAME, install_id, "record.json").as_posix()


def validate_active_transaction(
    value: Any,
    *,
    label: str = "active installation transaction",
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InstallManagerError(f"{label} must be an object")
    required = {"version", "operation", "install_id", "record"}
    if set(value) != required:
        raise InstallManagerError(f"{label} keys must be exactly {sorted(required)!r}")
    if value.get("version") != INSTALL_CONTRACT_VERSION:
        raise InstallManagerError(f"{label}.version is unsupported")
    operation = value.get("operation")
    if operation not in TRANSACTION_OPERATIONS:
        raise InstallManagerError(f"{label}.operation is invalid")
    install_id = value.get("install_id")
    if not isinstance(install_id, str) or not INSTALL_ID_RE.fullmatch(install_id):
        raise InstallManagerError(f"{label}.install_id is invalid")
    if value.get("record") != record_relative(install_id):
        raise InstallManagerError(f"{label}.record is invalid")
    return dict(value)


def new_active_transaction(*, operation: str, install_id: str) -> dict[str, Any]:
    return validate_active_transaction(
        {
            "version": INSTALL_CONTRACT_VERSION,
            "operation": operation,
            "install_id": install_id,
            "record": record_relative(install_id),
        }
    )


def backup_relative(target: str) -> str:
    return PurePosixPath("before").joinpath(*PurePosixPath(target).parts).as_posix()


def payload_digest(entries: Iterable[Mapping[str, Any]]) -> str:
    value = {
        "version": INSTALL_CONTRACT_VERSION,
        "managed_files": [
            {
                "kind": entry["kind"],
                "source": entry["source"],
                "target": entry["target"],
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
            }
            for entry in entries
        ],
    }
    return sha256_bytes(canonical_json_bytes(value))
