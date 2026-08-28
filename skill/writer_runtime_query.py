"""Read-only Worktree Writer v2 status/export and explicit cleanup."""

try:
    from skill.writer_runtime_base import *
    from skill.writer_runtime_candidate import *
    from skill.writer_integrity import WriterIntegrityError, validate_run_integrity
except ModuleNotFoundError:
    from writer_runtime_base import *
    from writer_runtime_candidate import *
    from writer_integrity import WriterIntegrityError, validate_run_integrity


def status_writer(run_dir: str | Path) -> dict[str, Any]:
    root = canonical_directory(run_dir, label="writer run directory")
    try:
        integrity = validate_run_integrity(
            root,
            max_event_bytes=WRITER_LIMITS.max_event_bytes,
            max_run_artifact_bytes=WRITER_LIMITS.max_run_artifact_bytes,
        )
    except (
        WriterIntegrityError,
        WriterContractError,
        WriterEffectError,
        WriterReviewError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise WriterRuntimeError(str(exc)) from exc
    checkpoint = integrity["checkpoint"]
    return {
        "operation": "writer-status",
        "model_calls": 0,
        "writes": [],
        "run_dir": str(root),
        "run_fingerprint": integrity["run_fingerprint"],
        "event_sequence": checkpoint["event_sequence"],
        "events": len(integrity["events"]),
        "summary": integrity["summary"],
        "integrity": "match",
    }


def export_writer(run_dir: str | Path) -> dict[str, Any]:
    root = canonical_directory(run_dir, label="writer run directory")
    before = None
    try:
        integrity = validate_run_integrity(
            root,
            max_event_bytes=WRITER_LIMITS.max_event_bytes,
            max_run_artifact_bytes=WRITER_LIMITS.max_run_artifact_bytes,
        )
        before = integrity["run_fingerprint"]
        package = integrity["candidate_package"]
        patch_path = integrity["patch_path"]
        if package is None or patch_path is None:
            raise WriterIntegrityError("writer run has no captured candidate")
        patch = patch_path.read_text(encoding="utf-8", errors="strict")
        files = []
        for item in package["files"]:
            stored = root / Path(*item["stored_path"].split("/"))
            payload = stored.read_bytes()
            files.append(
                {
                    "path": item["path"],
                    "bytes": len(payload),
                    "sha256": sha256_bytes(payload),
                    "content_base64": base64.b64encode(payload).decode("ascii"),
                }
            )
        after = validate_run_integrity(
            root,
            max_event_bytes=WRITER_LIMITS.max_event_bytes,
            max_run_artifact_bytes=WRITER_LIMITS.max_run_artifact_bytes,
        )["run_fingerprint"]
        if before != after:
            raise WriterIntegrityError("writer-export modified the run directory")
    except (
        WriterIntegrityError,
        WriterContractError,
        WriterEffectError,
        WriterReviewError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise WriterRuntimeError(str(exc)) from exc
    return {
        "operation": "writer-export",
        "model_calls": 0,
        "writes": [],
        "candidate_package": package,
        "patch": patch,
        "files": files,
        "run_fingerprint": before,
    }


def cleanup_writer(
    *,
    run_dir: str | Path,
    expected_run_id: str,
    expected_package_digest: str,
    ack_delete_isolated_worktree: bool,
) -> dict[str, Any]:
    if not ack_delete_isolated_worktree:
        raise WriterRuntimeError(
            "writer-cleanup requires --ack-delete-isolated-worktree"
        )
    status = status_writer(run_dir)
    root = Path(status["run_dir"])
    checkpoint = _load_json_file(root / "checkpoint.json", label="writer checkpoint")
    if checkpoint.get("run_id") != expected_run_id:
        raise WriterRuntimeError("writer cleanup run identity mismatch")
    if checkpoint.get("package_digest") != expected_package_digest:
        raise WriterRuntimeError("writer cleanup package digest mismatch")
    if checkpoint.get("state") not in TERMINAL_STATES or not checkpoint.get("terminal"):
        raise WriterRuntimeError("writer cleanup requires a terminal run")
    if checkpoint.get("active_process_pid") is not None:
        raise WriterRuntimeError("writer cleanup refuses an active process")
    if checkpoint.get("candidate") is None:
        raise WriterRuntimeError("writer cleanup requires captured candidate evidence")
    canonical = repository_root(checkpoint["canonical_repository"])
    current = repository_snapshot(canonical)
    expected = checkpoint.get("canonical_post_create_snapshot")
    if not isinstance(expected, dict):
        raise WriterRuntimeError("writer cleanup lacks canonical identity evidence")
    _canonical_core_unchanged(expected, current)
    worktree = Path(checkpoint["worktree_path"]).resolve(strict=True)
    lock_path = Path(checkpoint["lock_path"])
    lock = _lock_record(lock_path)
    if (
        lock["run_id"] != expected_run_id
        or lock["package_digest"] != expected_package_digest
        or lock["writer_profile"] != checkpoint["writer_profile"]
        or Path(lock["worktree_path"]).resolve(strict=True) != worktree
        or Path(lock["repository"]).resolve(strict=True) != canonical
    ):
        raise WriterRuntimeError("writer cleanup lock/worktree identity mismatch")
    run_git(canonical, ["worktree", "remove", "--force", str(worktree)])
    if worktree.exists():
        raise WriterRuntimeError("Git reported cleanup success but worktree still exists")
    lock_path.unlink()
    store = RunStateStore(
        root,
        max_event_bytes=WRITER_LIMITS.max_event_bytes,
        max_run_artifact_bytes=WRITER_LIMITS.max_run_artifact_bytes,
    )
    checkpoint["cleanup"] = {"cleaned": True, "cleaned_at": now_iso()}
    store.append_event(
        "writer.worktree.cleaned",
        {"run_id": expected_run_id, "worktree_path": str(worktree)},
    )
    store.write_checkpoint(checkpoint)
    atomic_write_json(root / "summary.json", _public_summary(checkpoint))
    # Cleanup is the only intentional query-side write. Revalidate retained
    # evidence and the now-absent worktree/lock before returning.
    status_writer(root)
    return {
        "operation": "writer-cleanup",
        "model_calls": 0,
        "run_id": expected_run_id,
        "package_digest": expected_package_digest,
        "worktree_deleted": True,
        "lock_deleted": True,
        "run_evidence_deleted": False,
    }


__all__ = ["status_writer", "export_writer", "cleanup_writer"]
