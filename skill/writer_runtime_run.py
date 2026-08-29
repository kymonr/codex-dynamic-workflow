"""Worktree Writer v2 execution lifecycle."""

try:
    from skill.writer_runtime_base import *
    from skill.writer_runtime_candidate import *
except ModuleNotFoundError:
    from writer_runtime_base import *
    from writer_runtime_candidate import *


def run_writer(
    *,
    package_path: str | Path,
    repository: str | Path,
    expected_package_digest: str,
    expected_head_sha: str,
    ack_isolated_worktree_write: bool,
    requested_run_dir: str | None = None,
    process_adapter: ProcessAdapter = run_codex_attempt,
) -> dict[str, Any]:
    if not ack_isolated_worktree_write:
        raise WriterRuntimeError(
            "writer-run requires --ack-isolated-worktree-write"
        )
    plan = plan_writer(
        package_path=package_path,
        repository=repository,
        expected_package_digest=expected_package_digest,
    )
    package = WriterPackage(plan["package"], plan["package_digest"])
    binding_record = dict(plan["writer_binding"])
    if writer_binding_record() != binding_record:
        raise WriterRuntimeError("fixed writer binding record is inconsistent")
    writer_route = WRITER_ROUTE
    if expected_head_sha != package.expected_head_sha:
        raise WriterRuntimeError("expected-head-sha does not match the package")
    canonical = Path(plan["canonical_repository"])
    runs_root = Path(plan["runs_root"])
    worktree_root = Path(plan["worktree_root"])
    runs_root.mkdir(parents=True, exist_ok=True)
    worktree_root.mkdir(parents=True, exist_ok=True)
    run_id = f"{package.name}-{_timestamp_slug()}-{uuid.uuid4().hex[:12]}"
    if requested_run_dir:
        run_dir = Path(requested_run_dir).expanduser().resolve(strict=False)
        if not run_dir.is_relative_to(runs_root.resolve(strict=False)):
            raise WriterRuntimeError(f"requested run directory must be below {runs_root}")
    else:
        run_dir = runs_root / run_id
    if run_dir.exists() or run_dir.is_symlink():
        raise WriterRuntimeError(f"writer run directory already exists: {run_dir}")
    worktree_path = _create_unique_path(worktree_root, package.name)
    lock_path = Path(plan["writer_lock"])
    lock_record = _create_lock(
        lock_path,
        run_id=run_id,
        package=package,
        writer_binding=binding_record,
        repository=canonical,
        worktree_path=worktree_path,
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    state: dict[str, Any] = {
        "runtime": WRITER_RUNTIME_NAME,
        "runtime_version": WRITER_RUNTIME_VERSION,
        "run_id": run_id,
        "state": "running",
        "terminal": False,
        "phase": "created",
        "created_at": now_iso(),
        "finished_at": None,
        "package_digest": package.digest,
        "writer_binding": binding_record,
        "canonical_repository": str(canonical),
        "worktree_path": str(worktree_path),
        "lock_path": str(lock_path),
        "base_snapshot": plan["base_identity"],
        "canonical_post_create_snapshot": None,
        "worktree_initial_snapshot": None,
        "writer": None,
        "effect_manifest": None,
        "verification_results": [],
        "candidate": None,
        "reviewer": None,
        "error": None,
        "cleanup": {"cleaned": False, "cleaned_at": None},
        "active_process_pid": None,
    }
    journal = WriterRunJournal(run_dir, state)
    try:
        _atomic_json(run_dir / "writer-package.resolved.json", package.value)
        _atomic_json(
            run_dir / "writer-authorization.json",
            {
                "authorization_version": 2,
                "package_version": package.version,
                "package_digest": package.digest,
                "writer_binding": binding_record,
                "expected_head_sha": expected_head_sha,
                "ack_isolated_worktree_write": True,
                "owned_targets": list(package.owned_targets),
                "allowed_actions": sorted(package.allowed_actions),
                "automatic_apply": False,
                "automatic_git_write": False,
            },
        )
        _atomic_json(run_dir / "base-identity.json", plan["base_identity"])
        _atomic_json(run_dir / "writer-lock.json", lock_record)
        journal.event("writer.run.created", {"run_id": run_id, "package_digest": package.digest})
        journal.event(
            "writer.authorization.recorded",
            {
                "package_digest": package.digest,
                "writer_binding": binding_record,
                "owned_targets": list(package.owned_targets),
            },
        )

        run_git(canonical, ["worktree", "add", "--detach", str(worktree_path), package.expected_head_sha])
        worktree_path = canonical_directory(worktree_path, label="isolated worktree")
        worktree_initial = repository_snapshot(worktree_path)
        if (
            worktree_initial["head"] != package.expected_head_sha
            or worktree_initial["tree"] != package.expected_tree_sha
            or worktree_initial["status_bytes"] != 0
        ):
            raise WriterEffectError("new detached worktree identity is invalid")
        canonical_post_create = repository_snapshot(canonical)
        _canonical_core_unchanged(plan["base_identity"], canonical_post_create)
        state["canonical_post_create_snapshot"] = canonical_post_create
        state["worktree_initial_snapshot"] = worktree_initial
        _atomic_json(run_dir / "worktree-identity.json", worktree_initial)
        journal.event(
            "writer.worktree.created",
            {
                "worktree": str(worktree_path),
                "head": worktree_initial["head"],
                "tree": worktree_initial["tree"],
            },
        )

        state["phase"] = "writer"
        journal.event(
            "writer.agent.started",
            {
                "writer_binding": binding_record,
                "role": writer_route.role,
                "model": writer_route.model,
                "attempt": 1,
            },
        )
        writer_entry = process_adapter(
            attempt_dir=(
                run_dir / "tasks" / "writer" / f"attempt-01-{writer_route.role}"
            ),
            cwd=worktree_path,
            prompt=_writer_prompt(package, binding_record),
            schema=writer_output_schema(),
            route=writer_route,
            timeout_seconds=MAX_WRITER_TIMEOUT_SECONDS,
            codex_prefix=plan["codex_prefix"],
            codex_identity=plan["codex_identity"],
        )
        writer_output = _validate_writer_output(writer_entry.get("output"), package)
        writer_entry = dict(writer_entry)
        writer_entry["output"] = writer_output
        state["writer"] = writer_entry
        state["active_process_pid"] = None
        journal.event(
            "writer.agent.completed",
            {
                "status": writer_output["status"],
                "attempt_count": writer_entry.get("attempt_count"),
                "retry": writer_entry.get("retry"),
                "upgrade": writer_entry.get("upgrade"),
            },
        )

        state["phase"] = "reconciliation"
        worktree_post_writer = repository_snapshot(worktree_path)
        _worktree_metadata_unchanged(worktree_initial, worktree_post_writer)
        canonical_post_writer = repository_snapshot(canonical)
        _canonical_core_unchanged(canonical_post_create, canonical_post_writer)
        candidate = reconcile_candidate(worktree_path, package)
        manifest = candidate["manifest"]
        reported = sorted(
            writer_output["reported_effects"],
            key=lambda item: (item["path"].casefold(), item["action"]),
        )
        observed = sorted(
            [
                {"path": item["path"], "action": item["action"]}
                for item in manifest["files"]
            ],
            key=lambda item: (item["path"].casefold(), item["action"]),
        )
        state["effect_manifest"] = manifest
        _atomic_json(run_dir / "pre-effect-manifest.json", worktree_initial)
        _atomic_json(run_dir / "post-effect-manifest.json", manifest)
        journal.event(
            "writer.effects.reconciled",
            {
                "changed_paths": manifest["changed_paths"],
                "patch_sha256": manifest["patch_sha256"],
                "reported_effects_match": reported == observed,
            },
        )
        if writer_output["status"] == "needs_escalation":
            raise WriterAttentionRequired("writer requested capability escalation")

        state["phase"] = "validation"
        validation_dir = run_dir / "validation"
        temp_root = run_dir / "validation-temp"
        results: list[dict[str, Any]] = []
        current_candidate = candidate
        for command in package.verification["commands"]:
            journal.event("writer.validation.started", {"id": command["id"]})
            result = _run_validation_command(
                command=command,
                worktree=worktree_path,
                output_dir=validation_dir,
                temp_root=temp_root,
            )
            after_candidate = reconcile_candidate(worktree_path, package)
            if after_candidate["manifest"]["manifest_digest"] != manifest["manifest_digest"]:
                raise WriterEffectError(
                    f"validation {command['id']} changed the candidate"
                )
            _worktree_metadata_unchanged(
                worktree_initial, repository_snapshot(worktree_path)
            )
            _canonical_core_unchanged(
                canonical_post_create, repository_snapshot(canonical)
            )
            results.append(result)
            state["verification_results"] = results
            journal.event(
                "writer.validation.completed",
                {"id": command["id"], "exit_code": result["exit_code"], "passed": result["passed"]},
            )
            if not result["passed"]:
                raise WriterValidationError(
                    f"validation {command['id']} exited {result['exit_code']}"
                )
            current_candidate = after_candidate
        required = set(package.verification["required_verification_ids"])
        passed = {result["id"] for result in results if result["passed"]}
        if not required <= passed:
            raise WriterValidationError(
                f"required validation ids are incomplete: missing={sorted(required - passed)}"
            )
        _atomic_json(run_dir / "verification-results.json", results)

        state["phase"] = "candidate_capture"
        patch_path = run_dir / "candidate.patch"
        _atomic_bytes(
            patch_path,
            current_candidate["patch"],
            maximum=package.limits["max_patch_bytes"],
            label="candidate patch",
        )
        stored_files = _write_candidate_files(
            worktree=worktree_path,
            candidate_root=run_dir / "candidate-files",
            manifest=manifest,
        )
        material = _candidate_material(
            package=package,
            base_snapshot=plan["base_identity"],
            worktree_identity=worktree_initial,
            effect_manifest=manifest,
            patch_path=patch_path,
            stored_files=stored_files,
            verification_results=results,
            writer_entry=writer_entry,
            writer_binding=binding_record,
        )
        material_digest = canonical_digest(material)
        candidate_package = {
            **material,
            "candidate_revision": f"sha256:{material_digest}",
            "revision_basis_digest": material_digest,
        }
        candidate_package_path = run_dir / "candidate-package.json"
        _atomic_json(candidate_package_path, candidate_package)
        state["candidate"] = {
            "candidate_revision": candidate_package["candidate_revision"],
            "candidate_package_path": str(candidate_package_path),
            "candidate_package_sha256": sha256_file(candidate_package_path),
            "patch_path": str(patch_path),
            "patch_sha256": sha256_file(patch_path),
            "manifest_digest": manifest["manifest_digest"],
        }
        journal.event(
            "writer.candidate.captured",
            {
                "candidate_revision": candidate_package["candidate_revision"],
                "patch_sha256": state["candidate"]["patch_sha256"],
            },
        )

        state["phase"] = "review"
        reviewer_workspace = run_dir / "reviewer-workspace"
        reviewer_workspace.mkdir(parents=True, exist_ok=False)
        patch_text = current_candidate["patch"].decode("utf-8", errors="strict")
        frozen_manifest_digest = reconcile_candidate(worktree_path, package)["manifest"]["manifest_digest"]
        journal.event(
            "writer.review.started",
            {
                "candidate_revision": candidate_package["candidate_revision"],
                "agent_type": REVIEWER_AGENT_TYPE,
                "attempt": 1,
            },
        )
        reviewer_entry = process_adapter(
            attempt_dir=run_dir / "tasks" / "reviewer" / "attempt-01-sol",
            cwd=reviewer_workspace,
            prompt=build_review_prompt(
                candidate_package=candidate_package,
                patch_text=patch_text,
            ),
            schema=review_schema(candidate_package["candidate_revision"]),
            route=REVIEWER_ROUTE,
            timeout_seconds=MAX_REVIEWER_TIMEOUT_SECONDS,
            codex_prefix=plan["codex_prefix"],
            codex_identity=plan["codex_identity"],
        )
        review_record = validate_review_record(
            reviewer_entry.get("output"),
            candidate_revision=candidate_package["candidate_revision"],
        )
        if any(reviewer_workspace.iterdir()):
            raise WriterEffectError("read-only reviewer created workspace effects")
        if reconcile_candidate(worktree_path, package)["manifest"]["manifest_digest"] != frozen_manifest_digest:
            raise WriterEffectError("candidate changed during independent review")
        _worktree_metadata_unchanged(worktree_initial, repository_snapshot(worktree_path))
        _canonical_core_unchanged(canonical_post_create, repository_snapshot(canonical))
        if sha256_file(candidate_package_path) != state["candidate"]["candidate_package_sha256"]:
            raise WriterEffectError("candidate package changed during independent review")
        if sha256_file(patch_path) != state["candidate"]["patch_sha256"]:
            raise WriterEffectError("candidate patch changed during independent review")
        reviewer_entry = dict(reviewer_entry)
        reviewer_entry["output"] = review_record
        state["reviewer"] = reviewer_entry
        _atomic_json(run_dir / "review-record.json", review_record)
        journal.event(
            "writer.review.completed",
            {
                "candidate_revision": candidate_package["candidate_revision"],
                "verdict": review_record["VERDICT"],
                "effects": [],
            },
        )
        return journal.terminal(terminal_state_for_verdict(review_record["VERDICT"]))
    except WriterValidationError as exc:
        return journal.terminal("validation_failed", error=str(exc))
    except WriterEffectError as exc:
        return journal.terminal("effect_violation", error=str(exc))
    except (WriterAttentionRequired, WriterProcessError, WriterReviewError) as exc:
        return journal.terminal("attention_required", error=str(exc))
    except BaseException as exc:
        # Preserve all evidence and the isolated worktree.  Do not retry or clean.
        with contextlib.suppress(Exception):
            return journal.terminal(
                "attention_required",
                error=f"{type(exc).__name__}: {exc}",
            )
        raise


__all__ = ["run_writer"]
