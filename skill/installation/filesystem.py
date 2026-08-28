"""Path-safe source discovery, target access, and atomic installation writes."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from skill.platform_paths import default_codex_home, default_state_root
    from skill.runtime.path_safety import (
        UnsafeRunPathError,
        assert_safe_descendant,
        assert_safe_run_tree,
        canonical_runtime_path,
        is_reparse,
        lexists,
    )
except ModuleNotFoundError:
    from platform_paths import default_codex_home, default_state_root
    from runtime.path_safety import (
        UnsafeRunPathError,
        assert_safe_descendant,
        assert_safe_run_tree,
        canonical_runtime_path,
        is_reparse,
        lexists,
    )

from .contract import (
    ACTIVE_TRANSACTION_RELATIVE,
    AGENTS_TARGET,
    COMMIT_RE,
    EXCLUDED_DIR_NAMES,
    EXCLUDED_FILE_NAMES,
    EXCLUDED_SUFFIXES,
    INSTALL_HISTORY_DIRNAME,
    MANIFEST_FILENAME,
    SKILL_TARGET,
    InstallManagerError,
    backup_relative,
    sha256_bytes,
    strict_json_loads,
    validate_active_transaction,
    validate_manifest,
)


def safe_root(path: Path, *, label: str, must_exist: bool) -> Path:
    try:
        root = canonical_runtime_path(path, label=label)
    except UnsafeRunPathError as exc:
        raise InstallManagerError(str(exc)) from exc
    if must_exist:
        if not root.is_dir() or is_reparse(root):
            raise InstallManagerError(f"{label} is not a safe directory: {root}")
    elif lexists(root) and (not root.is_dir() or is_reparse(root)):
        raise InstallManagerError(f"{label} is not a safe directory: {root}")
    return root


def resolve_codex_home(value: Path | str | None) -> Path:
    return safe_root(
        default_codex_home() if value is None else Path(value),
        label="Codex home",
        must_exist=False,
    )


def resolve_state_root(value: Path | str | None) -> Path:
    return safe_root(
        default_state_root() if value is None else Path(value),
        label="Dynamic Workflow state root",
        must_exist=False,
    )


def safe_target(root: Path, target: str, *, label: str) -> Path:
    relative = PurePosixPath(target)
    if (
        not isinstance(target, str)
        or not target
        or "\\" in target
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != target
    ):
        raise InstallManagerError(f"{label} is not a safe relative path: {target!r}")
    candidate = root.joinpath(*relative.parts)
    try:
        assert_safe_descendant(root, candidate, label=label)
        return canonical_runtime_path(candidate, label=label)
    except UnsafeRunPathError as exc:
        raise InstallManagerError(str(exc)) from exc


def target_identity(root: Path, target: str) -> str:
    path = safe_target(root, target, label="managed installation target")
    return os.path.normcase(os.path.normpath(str(path)))


def assert_safe_regular_file(path: Path, *, root: Path, label: str) -> None:
    try:
        assert_safe_descendant(root, path, label=label)
    except UnsafeRunPathError as exc:
        raise InstallManagerError(str(exc)) from exc
    if not lexists(path):
        raise InstallManagerError(f"{label} does not exist: {path}")
    if is_reparse(path):
        raise InstallManagerError(
            f"{label} is a symlink, junction, or reparse point: {path}"
        )
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise InstallManagerError(f"cannot inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise InstallManagerError(f"{label} is not a regular file: {path}")


def walk_regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name.casefold())
        except OSError as exc:
            raise InstallManagerError(
                f"cannot inspect source directory {directory}: {exc}"
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            if is_reparse(path):
                raise InstallManagerError(
                    "installation tree contains a symlink, junction, or reparse "
                    f"point: {path}"
                )
            if entry.is_dir(follow_symlinks=False):
                if entry.name not in EXCLUDED_DIR_NAMES:
                    pending.append(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise InstallManagerError(
                    f"installation tree entry is not a regular file: {path}"
                )
            if entry.name in EXCLUDED_FILE_NAMES or path.suffix in EXCLUDED_SUFFIXES:
                continue
            files.append(path)
    return sorted(files, key=lambda path: path.as_posix().casefold())


def source_root(path: Path | str) -> Path:
    root = safe_root(Path(path), label="installation source root", must_exist=True)
    required = (
        root / "skill" / "SKILL.md",
        root / "skill" / "VERSION",
        root / "config" / "agents",
        root / "integration" / "AGENTS.dynamic-workflow.md",
    )
    if not required[0].is_file():
        raise InstallManagerError(f"source root is missing skill/SKILL.md: {root}")
    if not required[1].is_file():
        raise InstallManagerError(f"source root is missing skill/VERSION: {root}")
    if not required[2].is_dir():
        raise InstallManagerError(f"source root is missing config/agents: {root}")
    if not required[3].is_file():
        raise InstallManagerError(
            f"source root is missing integration/AGENTS.dynamic-workflow.md: {root}"
        )
    for item in required:
        if is_reparse(item):
            raise InstallManagerError(f"source contract path is a reparse point: {item}")
    return root


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise InstallManagerError(f"cannot read file {path}: {exc}") from exc
    return digest.hexdigest(), size


def payload_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    skill_root = root / "skill"
    for source in walk_regular_files(skill_root):
        relative = source.relative_to(skill_root)
        target = SKILL_TARGET.joinpath(*relative.parts).as_posix()
        digest, size = sha256_file(source)
        entries.append(
            {
                "kind": "skill",
                "source": source.relative_to(root).as_posix(),
                "target": target,
                "sha256": digest,
                "bytes": size,
            }
        )

    agent_root = root / "config" / "agents"
    for source in walk_regular_files(agent_root):
        if source.parent != agent_root or source.suffix != ".toml":
            continue
        target = AGENTS_TARGET.joinpath(source.name).as_posix()
        digest, size = sha256_file(source)
        entries.append(
            {
                "kind": "agent",
                "source": source.relative_to(root).as_posix(),
                "target": target,
                "sha256": digest,
                "bytes": size,
            }
        )

    if not entries:
        raise InstallManagerError("installation source contains no managed files")
    seen: set[str] = set()
    for entry in entries:
        key = entry["target"].casefold()
        if key in seen:
            raise InstallManagerError(f"duplicate installation target: {entry['target']}")
        seen.add(key)
    return sorted(entries, key=lambda entry: entry["target"].casefold())


def git_identity(root: Path) -> dict[str, Any]:
    def run(*arguments: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *arguments],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=5,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError, UnicodeError):
            return None

    head = run("rev-parse", "HEAD")
    commit: str | None = None
    if head is not None and head.returncode == 0:
        candidate = head.stdout.strip().lower()
        if COMMIT_RE.fullmatch(candidate):
            commit = candidate
    status = run("status", "--porcelain=v1", "--untracked-files=normal")
    dirty: bool | None = None
    if status is not None and status.returncode == 0:
        dirty = bool(status.stdout)
    return {"commit": commit, "dirty": dirty}


def manifest_path(codex_home: Path) -> Path:
    return safe_target(
        codex_home,
        SKILL_TARGET.joinpath(MANIFEST_FILENAME).as_posix(),
        label="active installation manifest",
    )


def read_manifest(codex_home: Path) -> dict[str, Any] | None:
    path = manifest_path(codex_home)
    if not lexists(path):
        return None
    assert_safe_regular_file(path, root=codex_home, label="active installation manifest")
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallManagerError(
            f"cannot read active installation manifest {path}: {exc}"
        ) from exc
    return validate_manifest(
        strict_json_loads(payload, label="active installation manifest"),
        label="active installation manifest",
    )


def read_record(state_root: Path, relative: str) -> tuple[Path, dict[str, Any]]:
    path = safe_target(state_root, relative, label="installation history record")
    assert_safe_regular_file(path, root=state_root, label="installation history record")
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallManagerError(
            f"cannot read installation history record {path}: {exc}"
        ) from exc
    value = strict_json_loads(payload, label="installation history record")
    if not isinstance(value, dict):
        raise InstallManagerError("installation history record must be an object")
    return path, value


def atomic_write_bytes(path: Path, payload: bytes, *, root: Path, label: str) -> None:
    try:
        assert_safe_descendant(root, path, label=label)
    except UnsafeRunPathError as exc:
        raise InstallManagerError(str(exc)) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        assert_safe_descendant(root, path.parent, label=f"{label} parent")
        assert_safe_descendant(root, path, label=label)
    except UnsafeRunPathError as exc:
        raise InstallManagerError(str(exc)) from exc
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        assert_safe_descendant(root, temporary, label=f"{label} temporary")
    except UnsafeRunPathError as exc:
        raise InstallManagerError(str(exc)) from exc
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        os.set_inheritable(descriptor, False)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            assert_safe_descendant(root, path, label=label)
        except UnsafeRunPathError as exc:
            raise InstallManagerError(str(exc)) from exc
        os.replace(temporary, path)
    except InstallManagerError:
        raise
    except OSError as exc:
        raise InstallManagerError(f"cannot write {label} {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_json(path: Path, value: Any, *, root: Path, label: str) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    atomic_write_bytes(path, payload, root=root, label=label)


def active_transaction_path(state_root: Path) -> Path:
    return safe_target(
        state_root,
        ACTIVE_TRANSACTION_RELATIVE.as_posix(),
        label="active installation transaction",
    )


def read_active_transaction(state_root: Path) -> dict[str, Any] | None:
    path = active_transaction_path(state_root)
    if not lexists(path):
        return None
    assert_safe_regular_file(
        path, root=state_root, label="active installation transaction"
    )
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallManagerError(
            f"cannot read active installation transaction {path}: {exc}"
        ) from exc
    return validate_active_transaction(
        strict_json_loads(payload, label="active installation transaction")
    )


def write_active_transaction(
    state_root: Path,
    value: dict[str, Any],
) -> Path:
    normalized = validate_active_transaction(value)
    path = active_transaction_path(state_root)
    atomic_write_json(
        path,
        normalized,
        root=state_root,
        label="active installation transaction",
    )
    return path


def remove_active_transaction(
    state_root: Path,
    *,
    expected: dict[str, Any],
) -> None:
    current = read_active_transaction(state_root)
    if current is None:
        raise InstallManagerError("active installation transaction is missing")
    if current != validate_active_transaction(expected):
        raise InstallManagerError("active installation transaction changed")
    path = active_transaction_path(state_root)
    try:
        path.unlink()
    except OSError as exc:
        raise InstallManagerError(
            f"cannot remove active installation transaction {path}: {exc}"
        ) from exc


def current_regular_digest(codex_home: Path, target: str) -> tuple[str, int] | None:
    path = safe_target(codex_home, target, label="managed installation target")
    if not lexists(path):
        return None
    assert_safe_regular_file(path, root=codex_home, label="managed installation target")
    return sha256_file(path)


def history_dir(state_root: Path, install_id: str) -> Path:
    return safe_target(
        state_root,
        PurePosixPath(INSTALL_HISTORY_DIRNAME, install_id).as_posix(),
        label="installation history directory",
    )


def copy_backup(
    target_path: Path,
    *,
    target: str,
    codex_home: Path,
    history: Path,
    state_root: Path,
    expected_sha256: str,
) -> str:
    assert_safe_regular_file(target_path, root=codex_home, label="backup source")
    try:
        payload = target_path.read_bytes()
    except OSError as exc:
        raise InstallManagerError(f"cannot read backup source {target_path}: {exc}") from exc
    actual = sha256_bytes(payload)
    if actual != expected_sha256:
        raise InstallManagerError(
            f"backup source changed after planning: {target}; "
            f"expected={expected_sha256} actual={actual}"
        )
    relative = backup_relative(target)
    backup = safe_target(history, relative, label="installation backup file")
    atomic_write_bytes(backup, payload, root=state_root, label="installation backup file")
    return relative


def remove_history_record_tree(state_root: Path, relative: str | None) -> str | None:
    """Remove one no-longer-addressable rollback snapshot after state publication."""

    if relative is None:
        return None
    record = safe_target(state_root, relative, label="obsolete installation history record")
    history = record.parent
    installations = safe_target(
        state_root,
        INSTALL_HISTORY_DIRNAME,
        label="installation history root",
    )
    if history.parent != installations:
        raise InstallManagerError("obsolete installation history path has invalid shape")
    if not lexists(history):
        return None
    try:
        assert_safe_run_tree(history)
        shutil.rmtree(history)
    except (UnsafeRunPathError, OSError) as exc:
        raise InstallManagerError(
            f"cannot remove obsolete installation history {history}: {exc}"
        ) from exc
    return str(history)


def scan_unmanaged_skill_files(
    codex_home: Path,
    managed_targets: set[str],
) -> list[str]:
    skill_root = safe_target(
        codex_home, SKILL_TARGET.as_posix(), label="installed skill root"
    )
    if not lexists(skill_root):
        return []
    if not skill_root.is_dir() or is_reparse(skill_root):
        raise InstallManagerError(
            f"installed skill root is not a safe directory: {skill_root}"
        )
    unmanaged: list[str] = []
    for path in walk_regular_files(skill_root):
        relative = path.relative_to(codex_home).as_posix()
        if relative not in managed_targets:
            unmanaged.append(relative)
    return sorted(unmanaged, key=str.casefold)
