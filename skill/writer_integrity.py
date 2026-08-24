"""Deep, read-only integrity validation for Worktree Writer v1 evidence."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from skill.runtime.state_store import RunStateStore
    from skill.writer_contract import (
        WriterPackage,
        canonical_digest,
        load_json_strict,
        normalize_repo_path,
        validate_package,
    )
    from skill.writer_git_state import (
        WriterEffectError,
        _is_reparse,
        assert_no_link_components,
        compare_snapshots,
        repository_root,
        repository_snapshot,
        sha256_bytes,
        sha256_file,
    )
    from skill.writer_candidate_effects import reconcile_candidate
    from skill.writer_process import REVIEWER_ROUTE, WRITER_ROUTE
    from skill.writer_review import (
        REVIEWER_AGENT_TYPE,
        terminal_state_for_verdict,
        validate_review_record,
    )
except ModuleNotFoundError:
    from runtime.state_store import RunStateStore
    from writer_contract import (
        WriterPackage,
        canonical_digest,
        load_json_strict,
        normalize_repo_path,
        validate_package,
    )
    from writer_git_state import (
        WriterEffectError,
        _is_reparse,
        assert_no_link_components,
        compare_snapshots,
        repository_root,
        repository_snapshot,
        sha256_bytes,
        sha256_file,
    )
    from writer_candidate_effects import reconcile_candidate
    from writer_process import REVIEWER_ROUTE, WRITER_ROUTE
    from writer_review import (
        REVIEWER_AGENT_TYPE,
        terminal_state_for_verdict,
        validate_review_record,
    )

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
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

CHECKPOINT_KEYS = frozenset(
    {
        "runtime",
        "runtime_version",
        "run_id",
        "state",
        "terminal",
        "phase",
        "created_at",
        "finished_at",
        "package_digest",
        "canonical_repository",
        "worktree_path",
        "lock_path",
        "base_snapshot",
        "canonical_post_create_snapshot",
        "worktree_initial_snapshot",
        "writer",
        "effect_manifest",
        "verification_results",
        "candidate",
        "reviewer",
        "error",
        "cleanup",
        "active_process_pid",
        "checkpoint_version",
        "event_sequence",
        "updated_at",
    }
)
CANDIDATE_CHECKPOINT_KEYS = frozenset(
    {
        "candidate_revision",
        "candidate_package_path",
        "candidate_package_sha256",
        "patch_path",
        "patch_sha256",
        "manifest_digest",
    }
)
CANDIDATE_PACKAGE_KEYS = frozenset(
    {
        "candidate_package_version",
        "package_digest",
        "package_name",
        "objective",
        "repository_full_name",
        "base",
        "worktree",
        "authority",
        "effect_manifest",
        "patch",
        "files",
        "verification",
        "writer",
        "limitations",
        "unknown",
        "candidate_revision",
        "revision_basis_digest",
    }
)
CANDIDATE_FILE_KEYS = frozenset(
    {"path", "stored_path", "bytes", "sha256", "mode", "action"}
)
EFFECT_MANIFEST_KEYS = frozenset(
    {
        "manifest_version",
        "package_digest",
        "base_head",
        "base_tree",
        "worktree_head",
        "worktree_tree",
        "files",
        "changed_paths",
        "patch_bytes",
        "patch_sha256",
        "total_candidate_bytes",
        "unauthorized_effects",
        "manifest_digest",
    }
)
EFFECT_FILE_KEYS = frozenset(
    {
        "path",
        "action",
        "mode",
        "bytes",
        "sha256",
        "base_sha256",
        "mtime_ns",
    }
)
PROCESS_CORE_KEYS = frozenset(
    {
        "status",
        "role",
        "model",
        "effort",
        "tier",
        "requested_sandbox",
        "observed_sandbox",
        "attempt_count",
        "retry",
        "upgrade",
        "nested_agents",
        "codex_identity",
        "output",
    }
)
PROCESS_ALLOWED_KEYS = PROCESS_CORE_KEYS | frozenset(
    {
        "exit_code",
        "duration_s",
        "pid",
        "command",
        "paths",
        "bytes",
    }
)
VALIDATION_RESULT_KEYS = frozenset(
    {
        "id",
        "argv",
        "shell",
        "cwd",
        "exit_code",
        "timed_out",
        "duration_s",
        "stdout",
        "stderr",
        "passed",
    }
)
STREAM_KEYS = frozenset({"path", "bytes", "sha256"})
LOCK_KEYS = frozenset(
    {
        "lock_version",
        "status",
        "run_id",
        "pid",
        "package_digest",
        "repository",
        "repository_full_name",
        "created_at",
        "worktree_path",
    }
)


class WriterIntegrityError(RuntimeError):
    """Persisted writer evidence is malformed, stale, or tampered."""


def _closed(value: Any, *, where: str, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WriterIntegrityError(f"{where} must be an object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise WriterIntegrityError(
            f"{where} keys mismatch: missing={missing} unknown={unknown}"
        )
    return value


def _bounded_text(value: Any, *, where: str, maximum: int = 16_000) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or len(value) > maximum
    ):
        raise WriterIntegrityError(f"{where} must be a bounded non-empty string")
    return value


def _integer(value: Any, *, where: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise WriterIntegrityError(f"{where} must be an integer >= {minimum}")
    return value


def _hex64(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
        raise WriterIntegrityError(f"{where} must be 64 lowercase hex")
    return value


def _strict_regular_file(path: Path, *, label: str, maximum: int | None = None) -> Path:
    try:
        assert_no_link_components(path, label=label)
        resolved = path.resolve(strict=True)
        assert_no_link_components(resolved, label=label)
    except (OSError, RuntimeError, WriterEffectError) as exc:
        raise WriterIntegrityError(f"invalid {label}: {exc}") from exc
    if resolved.is_symlink() or _is_reparse(resolved) or not resolved.is_file():
        raise WriterIntegrityError(f"{label} must be a regular non-link file")
    size = resolved.stat().st_size
    if maximum is not None and size > maximum:
        raise WriterIntegrityError(f"{label} exceeds {maximum} bytes")
    return resolved


def _evidence_file(
    root: Path,
    raw: Any,
    *,
    expected_relative: str,
    label: str,
    maximum: int | None = None,
) -> Path:
    if not isinstance(raw, str) or not raw:
        raise WriterIntegrityError(f"{label} path must be a non-empty string")
    declared = Path(raw).expanduser()
    if not declared.is_absolute():
        raise WriterIntegrityError(f"{label} path must be absolute")
    expected = root / Path(*expected_relative.split("/"))
    actual = _strict_regular_file(declared, label=label, maximum=maximum)
    expected_actual = _strict_regular_file(
        expected, label=f"expected {label}", maximum=maximum
    )
    if actual != expected_actual:
        raise WriterIntegrityError(
            f"{label} path mismatch: expected={expected_actual} actual={actual}"
        )
    if not actual.is_relative_to(root):
        raise WriterIntegrityError(f"{label} escapes the writer run directory")
    return actual


def strict_run_manifest(run_dir: Path) -> list[dict[str, Any]]:
    """Return a no-follow manifest and reject every link/reparse/other entry."""

    records: list[dict[str, Any]] = []
    stack = [run_dir]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise WriterIntegrityError(f"cannot enumerate writer run evidence: {exc}") from exc
        for path in children:
            relative = path.relative_to(run_dir).as_posix()
            try:
                if path.is_symlink() or _is_reparse(path):
                    raise WriterIntegrityError(
                        f"writer run evidence contains symlink/reparse point: {relative}"
                    )
                metadata = path.lstat()
            except OSError as exc:
                raise WriterIntegrityError(
                    f"cannot inspect writer evidence {relative}: {exc}"
                ) from exc
            if path.is_dir():
                records.append({"path": relative, "type": "directory"})
                stack.append(path)
            elif path.is_file():
                records.append(
                    {
                        "path": relative,
                        "type": "file",
                        "bytes": metadata.st_size,
                        "sha256": sha256_file(path),
                        "mtime_ns": metadata.st_mtime_ns,
                    }
                )
            else:
                raise WriterIntegrityError(
                    f"writer run evidence contains unsupported file type: {relative}"
                )
    records.sort(key=lambda item: item["path"].casefold())
    return records


def run_fingerprint(run_dir: Path) -> str:
    return canonical_digest(strict_run_manifest(run_dir))


def _strict_json(path: Path, *, label: str, maximum: int = 8 * 1024 * 1024) -> Any:
    try:
        return load_json_strict(path, maximum_bytes=maximum)
    except Exception as exc:
        raise WriterIntegrityError(f"cannot load {label}: {exc}") from exc


def _validate_process(
    value: Any,
    *,
    where: str,
    expected_role: str,
    expected_model: str,
    expected_effort: str,
    expected_tier: str | None,
    expected_sandbox: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WriterIntegrityError(f"{where} must be an object")
    unknown = sorted(set(value) - PROCESS_ALLOWED_KEYS)
    if unknown:
        raise WriterIntegrityError(f"{where} has unknown keys: {unknown}")
    process = value
    if not PROCESS_CORE_KEYS <= set(process):
        raise WriterIntegrityError(
            f"{where} is missing core fields: {sorted(PROCESS_CORE_KEYS - set(process))}"
        )
    expected = {
        "status": "succeeded",
        "role": expected_role,
        "model": expected_model,
        "effort": expected_effort,
        "tier": expected_tier,
        "requested_sandbox": expected_sandbox,
        "attempt_count": 1,
        "retry": 0,
        "upgrade": None,
        "nested_agents": 0,
    }
    for key, expected_value in expected.items():
        if process.get(key) != expected_value:
            raise WriterIntegrityError(
                f"{where}.{key} mismatch: expected={expected_value!r} actual={process.get(key)!r}"
            )
    if not isinstance(process.get("codex_identity"), dict):
        raise WriterIntegrityError(f"{where}.codex_identity must be an object")
    return process


def _validate_effect_manifest(
    value: Any,
    *,
    package: WriterPackage,
) -> dict[str, Any]:
    manifest = _closed(value, where="effect manifest", keys=EFFECT_MANIFEST_KEYS)
    if manifest["manifest_version"] != 1:
        raise WriterIntegrityError("effect manifest version is invalid")
    for key, expected in (
        ("package_digest", package.digest),
        ("base_head", package.expected_head_sha),
        ("base_tree", package.expected_tree_sha),
        ("worktree_head", package.expected_head_sha),
        ("worktree_tree", package.expected_tree_sha),
    ):
        if manifest[key] != expected:
            raise WriterIntegrityError(f"effect manifest {key} mismatch")
    if manifest["unauthorized_effects"] != []:
        raise WriterIntegrityError("effect manifest contains unauthorized effects")
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise WriterIntegrityError("effect manifest files must be non-empty")
    observed_paths: list[str] = []
    total = 0
    for index, item in enumerate(files):
        record = _closed(
            item, where=f"effect manifest files[{index}]", keys=EFFECT_FILE_KEYS
        )
        path = normalize_repo_path(record["path"], where=f"effect file {index} path")
        if path not in package.owned_targets:
            raise WriterIntegrityError(f"effect file is not owned: {path}")
        if record["action"] not in package.allowed_actions:
            raise WriterIntegrityError(f"effect action is not authorized: {path}")
        if record["mode"] not in {"100644", "100755"}:
            raise WriterIntegrityError(f"effect mode is invalid: {path}")
        size = _integer(record["bytes"], where=f"effect file {path} bytes")
        _hex64(record["sha256"], where=f"effect file {path} sha256")
        base_sha = record["base_sha256"]
        if base_sha is not None:
            _hex64(base_sha, where=f"effect file {path} base_sha256")
        _integer(record["mtime_ns"], where=f"effect file {path} mtime_ns")
        observed_paths.append(path)
        total += size
    if len({path.casefold() for path in observed_paths}) != len(observed_paths):
        raise WriterIntegrityError("effect manifest paths are not case-insensitively unique")
    if manifest["changed_paths"] != observed_paths:
        raise WriterIntegrityError("effect manifest changed_paths do not match files")
    if manifest["total_candidate_bytes"] != total:
        raise WriterIntegrityError("effect manifest total_candidate_bytes mismatch")
    _integer(manifest["patch_bytes"], where="effect manifest patch_bytes")
    _hex64(manifest["patch_sha256"], where="effect manifest patch_sha256")
    supplied_digest = manifest["manifest_digest"]
    _hex64(supplied_digest, where="effect manifest digest")
    basis = dict(manifest)
    basis.pop("manifest_digest")
    if canonical_digest(basis) != supplied_digest:
        raise WriterIntegrityError("effect manifest digest mismatch")
    return manifest


def _validate_stream(
    root: Path, value: Any, *, command_id: str, stream: str
) -> None:
    record = _closed(
        value,
        where=f"validation {command_id} {stream}",
        keys=STREAM_KEYS,
    )
    expected_relative = f"validation/{command_id}.{stream}.txt"
    path = _evidence_file(
        root,
        record["path"],
        expected_relative=expected_relative,
        label=f"validation {command_id} {stream}",
        maximum=8 * 1024 * 1024,
    )
    size = _integer(record["bytes"], where=f"validation {command_id} {stream} bytes")
    digest = _hex64(
        record["sha256"], where=f"validation {command_id} {stream} sha256"
    )
    if path.stat().st_size != size or sha256_file(path) != digest:
        raise WriterIntegrityError(
            f"validation {command_id} {stream} evidence mismatch"
        )


def _validate_validations(
    root: Path,
    values: Any,
    *,
    package: WriterPackage,
    worktree_path: str,
    require_all_passed: bool,
) -> list[dict[str, Any]]:
    if not isinstance(values, list) or len(values) > len(package.verification["commands"]):
        raise WriterIntegrityError("verification results must be a bounded prefix")
    declared = {item["id"]: item for item in package.verification["commands"]}
    observed: list[dict[str, Any]] = []
    observed_ids: list[str] = []
    for index, value in enumerate(values):
        result = _closed(
            value,
            where=f"verification result[{index}]",
            keys=VALIDATION_RESULT_KEYS,
        )
        command_id = _bounded_text(result["id"], where=f"verification result[{index}].id")
        command = declared.get(command_id)
        if command is None:
            raise WriterIntegrityError(f"unknown verification result id: {command_id}")
        if result["argv"] != [sys.executable, *command["argv"][1:]] and not (
            command["argv"][0].casefold() == "pytest"
            and result["argv"] == [sys.executable, "-m", "pytest", *command["argv"][1:]]
        ):
            raise WriterIntegrityError(f"verification {command_id} argv mismatch")
        if result["shell"] is not False or result["cwd"] != worktree_path:
            raise WriterIntegrityError(f"verification {command_id} execution boundary mismatch")
        exit_code = result["exit_code"]
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise WriterIntegrityError(f"verification {command_id} exit_code is invalid")
        if result["timed_out"] is not False:
            raise WriterIntegrityError(f"verification {command_id} timed_out must be false")
        if not isinstance(result["passed"], bool) or result["passed"] != (exit_code == 0):
            raise WriterIntegrityError(f"verification {command_id} passed flag mismatch")
        if isinstance(result["duration_s"], bool) or not isinstance(
            result["duration_s"], (int, float)
        ) or result["duration_s"] < 0:
            raise WriterIntegrityError(f"verification {command_id} duration is invalid")
        _validate_stream(root, result["stdout"], command_id=command_id, stream="stdout")
        _validate_stream(root, result["stderr"], command_id=command_id, stream="stderr")
        observed.append(result)
        observed_ids.append(command_id)
    if observed_ids != [item["id"] for item in package.verification["commands"][: len(observed_ids)]]:
        raise WriterIntegrityError("verification results are not the declared command prefix")
    if require_all_passed:
        required = set(package.verification["required_verification_ids"])
        passed = {item["id"] for item in observed if item["passed"]}
        if not required <= passed:
            raise WriterIntegrityError(
                f"required verification evidence is incomplete: {sorted(required - passed)}"
            )
    return observed


def _validate_candidate(
    root: Path,
    checkpoint_candidate: Any,
    *,
    package: WriterPackage,
    effect_manifest: Mapping[str, Any],
    writer: Mapping[str, Any],
    verification_results: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], Path, Path]:
    candidate = _closed(
        checkpoint_candidate,
        where="candidate checkpoint",
        keys=CANDIDATE_CHECKPOINT_KEYS,
    )
    revision = _bounded_text(
        candidate["candidate_revision"], where="candidate revision", maximum=80
    )
    if not revision.startswith("sha256:"):
        raise WriterIntegrityError("candidate revision must use sha256")
    _hex64(revision.split(":", 1)[1], where="candidate revision digest")
    package_path = _evidence_file(
        root,
        candidate["candidate_package_path"],
        expected_relative="candidate-package.json",
        label="candidate package",
        maximum=16 * 1024 * 1024,
    )
    patch_path = _evidence_file(
        root,
        candidate["patch_path"],
        expected_relative="candidate.patch",
        label="candidate patch",
        maximum=package.limits["max_patch_bytes"],
    )
    if sha256_file(package_path) != _hex64(
        candidate["candidate_package_sha256"],
        where="candidate package sha256",
    ):
        raise WriterIntegrityError("candidate package digest mismatch")
    if sha256_file(patch_path) != _hex64(
        candidate["patch_sha256"], where="candidate patch sha256"
    ):
        raise WriterIntegrityError("candidate patch digest mismatch")
    if candidate["manifest_digest"] != effect_manifest["manifest_digest"]:
        raise WriterIntegrityError("candidate checkpoint manifest digest mismatch")

    value = _closed(
        _strict_json(package_path, label="candidate package", maximum=16 * 1024 * 1024),
        where="candidate package",
        keys=CANDIDATE_PACKAGE_KEYS,
    )
    if value["candidate_package_version"] != 1:
        raise WriterIntegrityError("candidate package version is invalid")
    basis = dict(value)
    recorded_revision = basis.pop("candidate_revision")
    recorded_basis_digest = basis.pop("revision_basis_digest")
    computed = canonical_digest(basis)
    if recorded_basis_digest != computed or recorded_revision != f"sha256:{computed}":
        raise WriterIntegrityError("candidate revision binding is invalid")
    if revision != recorded_revision:
        raise WriterIntegrityError("candidate checkpoint revision mismatch")
    for key, expected in (
        ("package_digest", package.digest),
        ("package_name", package.name),
        ("objective", package.objective),
        ("repository_full_name", package.repository_full_name),
    ):
        if value[key] != expected:
            raise WriterIntegrityError(f"candidate package {key} mismatch")
    if value["authority"] != package.value["authority"]:
        raise WriterIntegrityError("candidate package authority mismatch")
    if value["effect_manifest"] != effect_manifest:
        raise WriterIntegrityError("candidate package effect manifest mismatch")
    patch_record = _closed(value["patch"], where="candidate patch record", keys=frozenset({"path", "bytes", "sha256"}))
    if patch_record["path"] != "candidate.patch":
        raise WriterIntegrityError("candidate patch path is invalid")
    if patch_record["bytes"] != patch_path.stat().st_size or patch_record["sha256"] != sha256_file(patch_path):
        raise WriterIntegrityError("candidate patch record mismatch")
    if effect_manifest["patch_bytes"] != patch_path.stat().st_size or effect_manifest["patch_sha256"] != sha256_file(patch_path):
        raise WriterIntegrityError("effect manifest patch identity mismatch")
    try:
        patch_path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WriterIntegrityError("candidate patch is not UTF-8") from exc

    files = value["files"]
    if not isinstance(files, list) or len(files) != len(effect_manifest["files"]):
        raise WriterIntegrityError("candidate package file count mismatch")
    effect_by_path = {item["path"]: item for item in effect_manifest["files"]}
    observed_paths: list[str] = []
    for index, item in enumerate(files):
        record = _closed(
            item,
            where=f"candidate package files[{index}]",
            keys=CANDIDATE_FILE_KEYS,
        )
        path = normalize_repo_path(record["path"], where=f"candidate file {index} path")
        expected_stored = f"candidate-files/{path}"
        if record["stored_path"] != expected_stored:
            raise WriterIntegrityError(f"candidate file stored_path mismatch: {path}")
        stored = _strict_regular_file(
            root / Path(*expected_stored.split("/")),
            label=f"captured candidate file {path}",
            maximum=package.limits["max_total_candidate_bytes"],
        )
        effect = effect_by_path.get(path)
        if effect is None:
            raise WriterIntegrityError(f"candidate file lacks effect record: {path}")
        for key in ("bytes", "sha256", "mode", "action"):
            if record[key] != effect[key]:
                raise WriterIntegrityError(f"candidate file {path} {key} mismatch")
        if stored.stat().st_size != record["bytes"] or sha256_file(stored) != record["sha256"]:
            raise WriterIntegrityError(f"captured candidate file mismatch: {path}")
        try:
            payload = stored.read_bytes()
            payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WriterIntegrityError(f"captured candidate file is not UTF-8: {path}") from exc
        if b"\x00" in payload:
            raise WriterIntegrityError(f"captured candidate file contains NUL: {path}")
        observed_paths.append(path)
    if observed_paths != effect_manifest["changed_paths"]:
        raise WriterIntegrityError("candidate package file order/path mismatch")
    if value["verification"] != list(verification_results):
        raise WriterIntegrityError("candidate package verification evidence mismatch")
    expected_writer = {
        "role": writer.get("role"),
        "model": writer.get("model"),
        "effort": writer.get("effort"),
        "tier": writer.get("tier"),
        "attempt_count": writer.get("attempt_count"),
        "retry": writer.get("retry"),
        "upgrade": writer.get("upgrade"),
        "nested_agents": writer.get("nested_agents"),
        "requested_sandbox": writer.get("requested_sandbox"),
        "observed_sandbox": writer.get("observed_sandbox", "unknown"),
        "codex_identity": writer.get("codex_identity"),
    }
    if value["writer"] != expected_writer:
        raise WriterIntegrityError("candidate package writer identity mismatch")
    if not isinstance(value["limitations"], list) or not isinstance(value["unknown"], list):
        raise WriterIntegrityError("candidate package limitations/unknown are invalid")
    return value, package_path, patch_path


def _validate_lock(
    root: Path,
    checkpoint: Mapping[str, Any],
    *,
    package: WriterPackage,
    cleaned: bool,
) -> None:
    run_copy = _strict_regular_file(root / "writer-lock.json", label="writer lock copy", maximum=64 * 1024)
    copy_value = _closed(
        _strict_json(run_copy, label="writer lock copy", maximum=64 * 1024),
        where="writer lock copy",
        keys=LOCK_KEYS,
    )
    if copy_value["lock_version"] != 1 or copy_value["status"] != "active":
        raise WriterIntegrityError("writer lock copy identity is invalid")
    expected = {
        "run_id": checkpoint["run_id"],
        "package_digest": package.digest,
        "repository": checkpoint["canonical_repository"],
        "repository_full_name": package.repository_full_name,
        "worktree_path": checkpoint["worktree_path"],
    }
    for key, value in expected.items():
        if copy_value[key] != value:
            raise WriterIntegrityError(f"writer lock copy {key} mismatch")
    lock_path_raw = checkpoint["lock_path"]
    if not isinstance(lock_path_raw, str) or not Path(lock_path_raw).is_absolute():
        raise WriterIntegrityError("writer lock path is invalid")
    lock_path = Path(lock_path_raw)
    if cleaned:
        if lock_path.exists() or lock_path.is_symlink():
            raise WriterIntegrityError("cleaned writer run still has an external lock")
        return
    external = _strict_regular_file(lock_path, label="active external writer lock", maximum=64 * 1024)
    external_value = _closed(
        _strict_json(external, label="active external writer lock", maximum=64 * 1024),
        where="active external writer lock",
        keys=LOCK_KEYS,
    )
    if external_value != copy_value:
        raise WriterIntegrityError("external writer lock differs from run evidence")


def _validate_events(
    events: Sequence[Mapping[str, Any]], checkpoint: Mapping[str, Any]
) -> None:
    run_id = checkpoint["run_id"]
    terminal = checkpoint["terminal"]
    state = checkpoint["state"]
    terminal_type = (
        "writer.run.completed"
        if state in SUCCESSFUL_CANDIDATE_STATES
        else "writer.run.attention_required"
    )
    terminal_events = [event for event in events if event.get("type") in {"writer.run.completed", "writer.run.attention_required"}]
    if terminal:
        if len(terminal_events) != 1:
            raise WriterIntegrityError("writer journal must contain exactly one terminal event")
        event = terminal_events[0]
        expected_payload = {"run_id": run_id, "state": state, "error": checkpoint["error"]}
        if event.get("type") != terminal_type or event.get("payload") != expected_payload:
            raise WriterIntegrityError("writer terminal event does not match checkpoint")
        cleaned = checkpoint["cleanup"]["cleaned"]
        if cleaned:
            if events[-1].get("type") != "writer.worktree.cleaned":
                raise WriterIntegrityError("cleaned run journal lacks final cleanup event")
        elif events[-1] is not event:
            raise WriterIntegrityError("writer terminal event must be the final event before cleanup")
    elif terminal_events:
        raise WriterIntegrityError("nonterminal checkpoint contains a terminal event")


def validate_run_integrity(
    root: Path,
    *,
    max_event_bytes: int,
    max_run_artifact_bytes: int,
) -> dict[str, Any]:
    before_manifest = strict_run_manifest(root)
    before = canonical_digest(before_manifest)
    checkpoint_path = _strict_regular_file(root / "checkpoint.json", label="writer checkpoint", maximum=16 * 1024 * 1024)
    summary_path = _strict_regular_file(root / "summary.json", label="writer summary", maximum=16 * 1024 * 1024)
    checkpoint = _closed(
        _strict_json(checkpoint_path, label="writer checkpoint", maximum=16 * 1024 * 1024),
        where="writer checkpoint",
        keys=CHECKPOINT_KEYS,
    )
    summary = _strict_json(summary_path, label="writer summary", maximum=16 * 1024 * 1024)
    if checkpoint["runtime"] != "worktree-writer-v1" or checkpoint["runtime_version"] != 1:
        raise WriterIntegrityError("writer runtime identity is invalid")
    _bounded_text(checkpoint["run_id"], where="writer run_id", maximum=200)
    package_digest = _hex64(checkpoint["package_digest"], where="writer package digest")
    sequence = _integer(checkpoint["event_sequence"], where="event_sequence", minimum=1)
    if checkpoint["checkpoint_version"] != 1:
        raise WriterIntegrityError("writer checkpoint version is invalid")
    state = checkpoint["state"]
    terminal = checkpoint["terminal"]
    if not isinstance(terminal, bool):
        raise WriterIntegrityError("writer terminal flag is invalid")
    if terminal != (state in TERMINAL_STATES):
        raise WriterIntegrityError("writer terminal flag/state mismatch")
    if terminal and checkpoint["phase"] != "terminal":
        raise WriterIntegrityError("terminal writer phase is invalid")
    if terminal and not isinstance(checkpoint["finished_at"], str):
        raise WriterIntegrityError("terminal writer finished_at is missing")
    cleanup = _closed(
        checkpoint["cleanup"],
        where="writer cleanup state",
        keys=frozenset({"cleaned", "cleaned_at"}),
    )
    if not isinstance(cleanup["cleaned"], bool):
        raise WriterIntegrityError("writer cleanup cleaned flag is invalid")
    if cleanup["cleaned"] != (cleanup["cleaned_at"] is not None):
        raise WriterIntegrityError("writer cleanup timestamp/flag mismatch")
    if summary != {
        key: checkpoint.get(key)
        for key in (
            "runtime", "runtime_version", "run_id", "state", "terminal", "phase",
            "created_at", "finished_at", "package_digest", "canonical_repository",
            "worktree_path", "lock_path", "writer", "effect_manifest",
            "verification_results", "candidate", "reviewer", "error", "cleanup",
        )
    }:
        raise WriterIntegrityError("writer summary does not match checkpoint")

    package_path = _strict_regular_file(
        root / "writer-package.resolved.json",
        label="resolved writer package",
        maximum=1024 * 1024,
    )
    package = validate_package(_strict_json(package_path, label="resolved writer package", maximum=1024 * 1024))
    if package.digest != package_digest:
        raise WriterIntegrityError("resolved writer package digest mismatch")
    authorization = _strict_json(
        _strict_regular_file(root / "writer-authorization.json", label="writer authorization", maximum=1024 * 1024),
        label="writer authorization",
        maximum=1024 * 1024,
    )
    if not isinstance(authorization, dict):
        raise WriterIntegrityError("writer authorization must be an object")
    expected_authorization = {
        "authorization_version": 1,
        "package_digest": package.digest,
        "expected_head_sha": package.expected_head_sha,
        "ack_isolated_worktree_write": True,
        "owned_targets": list(package.owned_targets),
        "allowed_actions": sorted(package.allowed_actions),
        "automatic_apply": False,
        "automatic_git_write": False,
    }
    if authorization != expected_authorization:
        raise WriterIntegrityError("writer authorization binding mismatch")
    base_identity = _strict_json(
        _strict_regular_file(root / "base-identity.json", label="base identity", maximum=16 * 1024 * 1024),
        label="base identity",
        maximum=16 * 1024 * 1024,
    )
    if base_identity != checkpoint["base_snapshot"]:
        raise WriterIntegrityError("base identity evidence mismatch")
    if base_identity.get("head") != package.expected_head_sha or base_identity.get("tree") != package.expected_tree_sha:
        raise WriterIntegrityError("base identity does not match package")

    store = RunStateStore(
        root,
        max_event_bytes=max_event_bytes,
        max_run_artifact_bytes=max_run_artifact_bytes,
    )
    try:
        events = store.validate_journal(expected_sequence=sequence)
    except Exception as exc:
        raise WriterIntegrityError(f"writer journal integrity failed: {exc}") from exc
    _validate_events(events, checkpoint)

    writer = checkpoint["writer"]
    if writer is not None:
        writer = _validate_process(
            writer,
            where="writer process",
            expected_role=WRITER_ROUTE.role,
            expected_model=WRITER_ROUTE.model,
            expected_effort=WRITER_ROUTE.effort,
            expected_tier=WRITER_ROUTE.tier,
            expected_sandbox=WRITER_ROUTE.sandbox,
        )
    effect_manifest = checkpoint["effect_manifest"]
    if effect_manifest is not None:
        effect_manifest = _validate_effect_manifest(effect_manifest, package=package)
        manifest_file = _strict_json(
            _strict_regular_file(root / "post-effect-manifest.json", label="post-effect manifest", maximum=16 * 1024 * 1024),
            label="post-effect manifest",
            maximum=16 * 1024 * 1024,
        )
        if manifest_file != effect_manifest:
            raise WriterIntegrityError("post-effect manifest file mismatch")
    verification_results = _validate_validations(
        root,
        checkpoint["verification_results"],
        package=package,
        worktree_path=checkpoint["worktree_path"],
        require_all_passed=checkpoint["candidate"] is not None,
    )
    if checkpoint["candidate"] is not None:
        validation_file = _strict_json(
            _strict_regular_file(root / "verification-results.json", label="verification results", maximum=16 * 1024 * 1024),
            label="verification results",
            maximum=16 * 1024 * 1024,
        )
        if validation_file != verification_results:
            raise WriterIntegrityError("verification results file mismatch")
        if writer is None or effect_manifest is None:
            raise WriterIntegrityError("captured candidate lacks writer/effect evidence")
        candidate_package, candidate_package_path, patch_path = _validate_candidate(
            root,
            checkpoint["candidate"],
            package=package,
            effect_manifest=effect_manifest,
            writer=writer,
            verification_results=verification_results,
        )
    else:
        candidate_package = None
        candidate_package_path = None
        patch_path = None

    reviewer = checkpoint["reviewer"]
    if state in SUCCESSFUL_CANDIDATE_STATES:
        if reviewer is None or candidate_package is None:
            raise WriterIntegrityError("successful candidate state lacks reviewer/candidate evidence")
        reviewer = _validate_process(
            reviewer,
            where="reviewer process",
            expected_role=REVIEWER_ROUTE.role,
            expected_model=REVIEWER_ROUTE.model,
            expected_effort=REVIEWER_ROUTE.effort,
            expected_tier=REVIEWER_ROUTE.tier,
            expected_sandbox=REVIEWER_ROUTE.sandbox,
        )
        review_record_path = _strict_regular_file(
            root / "review-record.json",
            label="review record",
            maximum=2 * 1024 * 1024,
        )
        review_record = validate_review_record(
            _strict_json(review_record_path, label="review record", maximum=2 * 1024 * 1024),
            candidate_revision=candidate_package["candidate_revision"],
        )
        if reviewer["output"] != review_record:
            raise WriterIntegrityError("checkpoint reviewer output mismatch")
        if terminal_state_for_verdict(review_record["VERDICT"]) != state:
            raise WriterIntegrityError("review verdict does not match terminal state")
    elif reviewer is not None:
        raise WriterIntegrityError("non-candidate terminal state unexpectedly has a reviewer")

    _validate_lock(
        root,
        checkpoint,
        package=package,
        cleaned=cleanup["cleaned"],
    )
    canonical = repository_root(checkpoint["canonical_repository"])
    if str(canonical) != checkpoint["canonical_repository"]:
        raise WriterIntegrityError("canonical repository path is not canonical")
    expected_canonical = checkpoint["canonical_post_create_snapshot"] or checkpoint["base_snapshot"]
    if not isinstance(expected_canonical, dict):
        raise WriterIntegrityError("writer checkpoint lacks canonical snapshot evidence")
    current_canonical = repository_snapshot(canonical)
    differences = compare_snapshots(
        expected_canonical,
        current_canonical,
        allow_worktree_registry_change=cleanup["cleaned"],
    )
    if differences:
        raise WriterIntegrityError(f"canonical repository drifted: {differences}")
    worktree_path = checkpoint["worktree_path"]
    if not isinstance(worktree_path, str) or not Path(worktree_path).is_absolute():
        raise WriterIntegrityError("isolated worktree path is invalid")
    worktree = Path(worktree_path)
    if cleanup["cleaned"]:
        if worktree.exists() or worktree.is_symlink():
            raise WriterIntegrityError("cleaned isolated worktree still exists")
    else:
        try:
            live_worktree = repository_root(worktree)
        except WriterEffectError as exc:
            raise WriterIntegrityError(f"isolated worktree identity is invalid: {exc}") from exc
        if str(live_worktree) != worktree_path:
            raise WriterIntegrityError("isolated worktree path is not canonical")
        initial = checkpoint["worktree_initial_snapshot"]
        if not isinstance(initial, dict):
            raise WriterIntegrityError("writer checkpoint lacks initial worktree identity")
        current_worktree = repository_snapshot(live_worktree)
        protected = {
            "head", "tree", "refs_sha256", "config_sha256", "index",
            "objects_manifest_digest", "head_file", "packed_refs",
        }
        drift = [key for key in sorted(protected) if initial.get(key) != current_worktree.get(key)]
        if drift:
            raise WriterIntegrityError(f"isolated worktree Git metadata drifted: {drift}")
        if effect_manifest is not None:
            try:
                live_manifest = reconcile_candidate(live_worktree, package)["manifest"]
            except WriterEffectError as exc:
                raise WriterIntegrityError(f"live candidate reconciliation failed: {exc}") from exc
            if live_manifest["manifest_digest"] != effect_manifest["manifest_digest"]:
                raise WriterIntegrityError("live candidate changed after capture/review")

    after_manifest = strict_run_manifest(root)
    after = canonical_digest(after_manifest)
    if before != after:
        raise WriterIntegrityError("writer integrity query modified the run directory")
    return {
        "checkpoint": checkpoint,
        "summary": summary,
        "events": events,
        "package": package,
        "candidate_package": candidate_package,
        "candidate_package_path": candidate_package_path,
        "patch_path": patch_path,
        "run_fingerprint": before,
        "run_manifest": before_manifest,
    }
