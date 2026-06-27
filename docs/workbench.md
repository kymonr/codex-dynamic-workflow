# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- Objective: Optimize the Team Router skill as manager-facing process guidance: make Manager Mode intake gates explicit and keep parent-thread title normalization from repeating on every orchestration turn.
- State: local implementation complete and verified. `SKILL.md` now has a short Manager Intake anchor under the 8KB cap; `references/manager-mode.md` contains the detailed `READ_ONLY` / `DISPATCH_ONLY` / `WORKSPACE_WRITE` / `LOCAL_CLOSEOUT` / `EXTERNAL_RELEASE` fast path; `orchestrate_team_task_with_adapter()` now renames the parent/current thread once before first child-role dispatch instead of every loop; full Team Router tests pass.
- Git baseline at this turn: `git status -s` already showed modified Team Router lifecycle files before the intake optimization.
- Last refreshed: 2026-06-28 Manager Intake Fast Path optimization complete; repo/global skill files synced for `SKILL.md` and `references/manager-mode.md`.
- Not done: commit, push, PR, merge, publish, release.

## Current Diff Surface

Current package diff includes the pre-existing role-lifecycle surface plus this Manager Intake optimization and test alignment:

- `src/team_router.py`
- `tests/test_team_router.py`
- `docs/workbench.md`
- `docs/compounding.md`
- `docs/runbooks/codex-team-router-live-orchestration.md`
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/adapter-runtime.md`
- `skills/codex-team-router/references/direct-return.md`
- `skills/codex-team-router/references/manager-mode.md`
- `skills/codex-team-router/references/manager-polling-cadence.md`

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library. It records registry/ledger state, builds prompts, parses role protocol blocks, and exposes adapter-aware helper functions.
- Real live orchestration still depends on a parent host adapter that can provide callable Codex thread tools such as `list_projects`, `create_thread`, `send_message_to_thread`, `read_thread`, and `set_thread_title`, plus the current parent thread id for `parent_thread_id`.
- Adapter-created orchestration returns `tool_error` before first child-role dispatch when the parent/current thread id is unavailable, rather than pretending the parent rename happened.
- Parent/current thread title normalization now happens only when the task ledger does not exist yet, so watcher/read/closeout loops do not repeatedly rename the parent thread.
- Watcher/heartbeat behavior still depends on a host scheduler or automation loop calling `watch_team_task_with_adapter()` at `firstCheckAt` / `nextAllowedReadAt`. After the single short first check, the helper moves the next proactive read to at least 300 seconds after that read; it does not install or run the scheduler by itself.
- If the parent host cannot pass callable thread tools into Python, use the manual/pre-created continuation path and feed actual send/read observations back into the helpers.

## Verification Record

Current verification:

- `skills/codex-team-router/SKILL.md` size check: 7533 bytes, under the 8192-byte entrypoint cap.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_skill_entrypoint_uses_progressive_disclosure_references tests.test_team_router.TestTeamRouterSkillDoc.test_manager_mode_docs_cover_intake_fast_path_gates tests.test_team_router.TestTeamRouterSkillDoc.test_contract_docs_cover_archived_role_visibility_and_degraded_delivery -v`: pass, 3 tests.
- `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_waiting_executor_update_before_timeout_does_not_allow_convergence_without_observation tests.test_team_router.TestTeamRouterManagerIntegration.test_orchestrate_team_task_with_adapter_reaches_closeout_with_codex_desktop_shapes -v`: pass, 2 tests.
- `py -m py_compile src\team_router.py tests\test_team_router.py`: pass.
- `git diff --check`: pass; CRLF warnings only for existing modified files.
- `py -m unittest tests.test_team_router -v`: pass, 237 tests.
- Repo/global installed skill sync: SHA256 matched for repo and installed `SKILL.md`; SHA256 matched for repo/global `references/manager-mode.md`.

## Review And Verification Gate

- Local verification: passed.
- Reviewer/verifier role-thread gates: not run in this turn; no live thread-tool role orchestration was available in this workspace session.

## Next Gate

- Commit only after explicit commit authorization.
- Push, PR, merge, publish, and release require separate explicit authorization.