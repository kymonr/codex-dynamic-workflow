"""Isolated Worktree Writer v2 host runtime.

The runtime is deliberately separate from Workflow IR: neither Auto Planner nor
Bounded Loop can activate it. One explicit package and one fixed host writer route
create one detached worktree, one writer attempt, host reconciliation and
validation, and one fresh read-only Sol review. It never applies the candidate to
the canonical checkout and never commits, pushes, merges, releases, or deploys.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from skill import platform_paths
    from skill import runner as legacy
    from skill.runtime.limits import RuntimeLimits, enforce_file_limit, enforce_run_limit
    from skill.runtime.state_store import RunStateStore, atomic_write_json, now_iso
    from skill.writer_contract import (
        WriterContractError,
        WriterPackage,
        canonical_digest,
        canonical_json_bytes,
        load_package,
        package_contract,
    )
    from skill.writer_effects import (
        WriterEffectError,
        assert_no_link_components,
        canonical_directory,
        compare_snapshots,
        paths_overlap,
        reconcile_candidate,
        repository_root,
        repository_snapshot,
        run_git,
        sha256_bytes,
        sha256_file,
        validate_base,
    )
    from skill.writer_process import (
        REVIEWER_ROUTE,
        WRITER_ROUTE,
        WriterProcessError,
        probe_codex_capabilities,
        run_codex_attempt,
        validate_writer_package,
        writer_output_schema,
        writer_binding_record,
    )
    from skill.writer_review import (
        REVIEWER_AGENT_TYPE,
        WriterReviewError,
        build_review_prompt,
        review_schema,
        terminal_state_for_verdict,
        validate_review_record,
    )
except ModuleNotFoundError:
    import platform_paths
    import runner as legacy
    from runtime.limits import RuntimeLimits, enforce_file_limit, enforce_run_limit
    from runtime.state_store import RunStateStore, atomic_write_json, now_iso
    from writer_contract import (
        WriterContractError,
        WriterPackage,
        canonical_digest,
        canonical_json_bytes,
        load_package,
        package_contract,
    )
    from writer_effects import (
        WriterEffectError,
        assert_no_link_components,
        canonical_directory,
        compare_snapshots,
        paths_overlap,
        reconcile_candidate,
        repository_root,
        repository_snapshot,
        run_git,
        sha256_bytes,
        sha256_file,
        validate_base,
    )
    from writer_process import (
        REVIEWER_ROUTE,
        WRITER_ROUTE,
        WriterProcessError,
        probe_codex_capabilities,
        run_codex_attempt,
        validate_writer_package,
        writer_output_schema,
        writer_binding_record,
    )
    from writer_review import (
        REVIEWER_AGENT_TYPE,
        WriterReviewError,
        build_review_prompt,
        review_schema,
        terminal_state_for_verdict,
        validate_review_record,
    )

WRITER_RUNTIME_VERSION = 2
WRITER_RUNTIME_NAME = "worktree-writer-v2"
WRITER_ACK = "--ack-isolated-worktree-write"
WRITER_RUNS_SUBDIR = "writers"
LOCKS_SUBDIR = ".locks"
TERMINAL_STATES = frozenset(
    {
        "ship_candidate",
        "fix_first",
        "rethink",
        "validation_failed",
        "effect_violation",
        "attention_required",
        "cancelled",
    }
)
SUCCESSFUL_CANDIDATE_STATES = frozenset({"ship_candidate", "fix_first", "rethink"})
MAX_WRITER_TIMEOUT_SECONDS = 7_200
MAX_REVIEWER_TIMEOUT_SECONDS = 7_200
WRITER_LIMITS = RuntimeLimits(
    max_result_bytes=2 * 1024 * 1024,
    max_log_bytes=8 * 1024 * 1024,
    max_run_artifact_bytes=64 * 1024 * 1024,
    max_upstream_inline_bytes=16 * 1024,
    max_event_bytes=256 * 1024,
)

ProcessAdapter = Callable[..., dict[str, Any]]


class WriterRuntimeError(RuntimeError):
    """The writer host runtime cannot continue without violating its contract."""


class WriterValidationError(WriterRuntimeError):
    """A fixed host validation command failed or changed the candidate."""


class WriterAttentionRequired(WriterRuntimeError):
    """The preserved isolated worktree requires explicit human reconciliation."""


def _timestamp_slug() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def _atomic_bytes(path: Path, payload: bytes, *, maximum: int, label: str) -> None:
    if len(payload) > maximum:
        raise WriterRuntimeError(f"{label} exceeds {maximum} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _atomic_json(path: Path, value: Any, *, maximum: int = 8 * 1024 * 1024) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    _atomic_bytes(path, payload, maximum=maximum, label=path.name)


def _runs_root() -> Path:
    return Path(platform_paths.default_runs_root()) / WRITER_RUNS_SUBDIR


def _worktree_root() -> Path:
    return Path(platform_paths.default_worktree_root())


def _lock_path(worktree_root: Path, canonical_repository: Path) -> Path:
    identity = hashlib.sha256(str(canonical_repository).casefold().encode("utf-8")).hexdigest()
    return worktree_root / LOCKS_SUBDIR / f"{identity}.lock.json"


def _validate_root_layout(
    *,
    canonical_repository: Path,
    runs_root: Path,
    worktree_root: Path,
    codex_home: Path,
) -> None:
    for path, label in (
        (runs_root, "writer runs root"),
        (worktree_root, "writer worktree root"),
        (codex_home, "Codex home"),
    ):
        assert_no_link_components(path, label=label)
    if not worktree_root.is_dir():
        raise WriterRuntimeError(
            f"DYNWF_WORKTREE_ROOT must already exist for zero-write planning: {worktree_root}"
        )
    pairs = [
        (canonical_repository, runs_root, "canonical repository", "runs root"),
        (canonical_repository, worktree_root, "canonical repository", "worktree root"),
        (canonical_repository, codex_home, "canonical repository", "Codex home"),
        (runs_root, worktree_root, "runs root", "worktree root"),
        (runs_root, codex_home, "runs root", "Codex home"),
        (worktree_root, codex_home, "worktree root", "Codex home"),
    ]
    for first, second, first_label, second_label in pairs:
        if paths_overlap(first.resolve(strict=False), second.resolve(strict=False)):
            raise WriterRuntimeError(f"{first_label} overlaps {second_label}")


def _codex_preflight() -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    try:
        prefix, identity = legacy.resolve_codex_prefix()
        capabilities = probe_codex_capabilities(prefix)
    except (legacy.WorkflowError, WriterProcessError) as exc:
        raise WriterRuntimeError(str(exc)) from exc
    return prefix, identity, capabilities


def plan_writer(
    *,
    package_path: str | Path,
    repository: str | Path,
    expected_package_digest: str,
) -> dict[str, Any]:
    """Zero-model, zero-write package/repository/capability preview."""

    package = load_package(package_path)
    if package.digest != expected_package_digest:
        raise WriterRuntimeError(
            f"package digest mismatch: expected={expected_package_digest} actual={package.digest}"
        )
    try:
        validate_writer_package(package)
    except WriterProcessError as exc:
        raise WriterRuntimeError(str(exc)) from exc
    binding_record = writer_binding_record()
    canonical = repository_root(repository)
    codex_home = legacy.resolve_codex_home().resolve()
    runs_root = _runs_root().expanduser().resolve(strict=False)
    worktree_root = _worktree_root().expanduser().resolve(strict=True)
    _validate_root_layout(
        canonical_repository=canonical,
        runs_root=runs_root,
        worktree_root=worktree_root,
        codex_home=codex_home,
    )
    base_snapshot = validate_base(canonical, package)
    codex_prefix, codex_identity, capabilities = _codex_preflight()
    lock_path = _lock_path(worktree_root, canonical)
    if lock_path.exists() or lock_path.is_symlink():
        raise WriterRuntimeError(
            f"writer lock already exists; inspect or clean it explicitly: {lock_path}"
        )
    return {
        "operation": "writer-plan",
        "runtime_version": WRITER_RUNTIME_VERSION,
        "model_calls": 0,
        "writes": [],
        "run_directory_created": False,
        "worktree_created": False,
        "canonical_repository_modified": False,
        "package": package.value,
        "package_digest": package.digest,
        "package_contract": package_contract(),
        "writer_binding": binding_record,
        "base_identity": base_snapshot,
        "canonical_repository": str(canonical),
        "runs_root": str(runs_root),
        "worktree_root": str(worktree_root),
        "writer_lock": str(lock_path),
        "writer_lock_available": True,
        "codex_prefix": list(codex_prefix),
        "codex_identity": codex_identity,
        "codex_capabilities": capabilities,
        "writer_route": {
            "role": WRITER_ROUTE.role,
            "model": WRITER_ROUTE.model,
            "effort": WRITER_ROUTE.effort,
            "tier": WRITER_ROUTE.tier,
            "sandbox": WRITER_ROUTE.sandbox,
            "attempts": 1,
            "retry": 0,
            "upgrade": None,
        },
        "reviewer_route": {
            "agent_type": REVIEWER_AGENT_TYPE,
            "role": REVIEWER_ROUTE.role,
            "model": REVIEWER_ROUTE.model,
            "effort": REVIEWER_ROUTE.effort,
            "sandbox": REVIEWER_ROUTE.sandbox,
            "fresh": True,
            "attempts": 1,
            "retry": 0,
            "upgrade": None,
        },
        "automatic_apply": False,
        "automatic_git_write": False,
        "automatic_retry": False,
    }


def _create_unique_path(root: Path, prefix: str) -> Path:
    for _ in range(20):
        candidate = root / f"{prefix}-{_timestamp_slug()}-{uuid.uuid4().hex[:12]}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise WriterRuntimeError(f"cannot allocate a unique path below {root}")


def _create_lock(
    path: Path,
    *,
    run_id: str,
    package: WriterPackage,
    writer_binding: Mapping[str, Any],
    repository: Path,
    worktree_path: Path,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "lock_version": 2,
        "status": "active",
        "run_id": run_id,
        "pid": os.getpid(),
        "package_version": package.version,
        "package_digest": package.digest,
        "writer_binding": dict(writer_binding),
        "repository": str(repository),
        "repository_full_name": package.repository_full_name,
        "created_at": now_iso(),
        "worktree_path": str(worktree_path),
    }
    payload = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise WriterRuntimeError(f"writer lock already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            path.unlink()
        raise
    return record


def _load_json_file(path: Path, *, label: str) -> Any:
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
            raise WriterRuntimeError(f"{label} is not strict UTF-8 JSON")
        return json.loads(raw.decode("utf-8", errors="strict"))
    except WriterRuntimeError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WriterRuntimeError(f"cannot load {label}: {exc}") from exc


def _lock_record(path: Path) -> dict[str, Any]:
    value = _load_json_file(path, label="writer lock")
    required = {
        "lock_version", "status", "run_id", "pid", "package_version",
        "package_digest", "writer_binding", "repository",
        "repository_full_name", "created_at", "worktree_path",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("lock_version") != 2:
        raise WriterRuntimeError("writer lock has an invalid shape")
    return value


__all__ = [name for name in globals() if not name.startswith("__")]
