# Team Router Review Package: ctr-20260630-host-adapter-scheduler

## Package Metadata

- taskId: `ctr-20260630-host-adapter-scheduler`
- permission: `local-package`
- objective: explicitly check the host adapter/scheduler gate before watcher/status extraction, and determine whether the repo still needs host runtime changes or only an external host package with callable evidence.
- scope: `src/team_router_host_runtime.py`, `src/team_router.py`, `scripts/team_router_doctor.py`, `tests/test_team_router.py`, `docs/workbench.md`, this package file.
- outOfScope: fake host adapter implementation, live daemon, production scheduler, watcher/status module extraction, push, PR, merge, deploy, publish/release, global skill sync.

## Findings

- `src/team_router_host_runtime.py` already owns callable host readiness checks: callable adapter, callable thread tools, explicit `parent_thread_id`, and callable heartbeat scheduler or `.schedule(**kwargs)`.
- `src/team_router.py` already blocks adapter-created orchestration unless readiness is complete. Missing `parent_thread_id` returns `tool_error_parent_title_unavailable`; missing callable scheduler/tools returns `tool_error_live_orchestration_unavailable`.
- `watch_team_task_with_adapter()` remains a host-scheduled callback target. It computes and attaches heartbeat schedule metadata, but it does not install or run a daemon by itself.
- `scripts/team_router_doctor.py --host-readiness-json <path>` remains evidence-only. It reports `manual_only` without a snapshot, `host_contract_blocked` with incomplete callable evidence, and `adapter_smoke_ready` only when supplied evidence proves the callable contract.
- Model-side Codex app tool descriptors are still not Python callables. A real host package must supply an in-process wrapper exposing `list_projects`, `create_thread`, `list_threads`, `read_thread`, `send_message_to_thread`, `set_thread_title`, `parent_thread_id`, and a callable heartbeat scheduler.

## Changes

- `docs/workbench.md`: current state moved from the previous prompt-compaction package to this explicit host adapter/scheduler package, and next gate clarified as watcher/status module extraction for repo-local work.
- `docs/team-router/packages/ctr-20260630-host-adapter-scheduler.md`: added this package record.
- No runtime code changes were needed; existing guards already cover the requested host adapter/scheduler boundary. `tests/test_team_router.py` workbench expectations were updated to this current package.

## Verification

- `git status -sb --untracked-files=all` ran before docs update; branch/ahead state is intentionally not copied here because fresh git status is the source of truth.
- `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; `gitStatusShort: []` before docs update.
- `py -B scripts\team_router_doctor.py --json` -> `truthStatus: clean_synced`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction: no action required unless the manager opens a new package` before docs update.
- `py -B -m unittest tests.test_team_router -k "host_context" -v` -> Ran 4 tests OK.
- `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_thread_adapter_capability_probe_reports_missing_tools tests.test_team_router.TestTeamRouterManagerIntegration.test_thread_adapter_capability_probe_rejects_model_tool_descriptors tests.test_team_router.TestTeamRouterManagerIntegration.test_parent_entry_guard_blocks_adapter_runner_without_callable_tools tests.test_team_router.TestTeamRouterManagerIntegration.test_parent_entry_guard_accepts_full_callable_adapter_path tests.test_team_router.TestTeamRouterManagerIntegration.test_orchestrate_team_task_requires_parent_current_thread_rename_before_role_dispatch tests.test_team_router.TestTeamRouterManagerIntegration.test_orchestrate_team_task_blocks_when_parent_thread_id_is_unavailable tests.test_team_router.TestTeamRouterManagerIntegration.test_orchestrate_team_task_blocks_when_heartbeat_scheduler_is_not_callable -v` -> Ran 7 tests OK.
- An earlier focused command used the wrong class path (`TestTeamRouterProtocol`) and failed with `AttributeError`; the corrected `TestTeamRouterManagerIntegration` command passed.

- Docs gate after test expectation update: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_thread_tool_absence_is_tool_error_or_manual_only_not_role_dispatch tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_host_readiness_snapshots -v` -> Ran 3 tests OK.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 337 tests OK.
- Truth check after docs/test update: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty files are `docs/workbench.md`, `tests/test_team_router.py`, and this package record.
- Doctor check after docs/test update: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; entrypoint `underTarget: true`.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.

- Reviewer role thread `019f17f2-2fea-7b02-b1a0-f96dec82c453` returned `TEAM_ROUTER_REVIEW result: pass`, `requiredChanges: none`.
- Verifier role thread `019f17f5-f216-7802-bb8a-e74f63c2c800` returned `TEAM_ROUTER_VERDICT result: pass`, `requiredChanges: none`.

## Not Done

- No live Codex host adapter was implemented inside this repo.
- No heartbeat daemon or production scheduler was installed.
- No watcher/status module extraction was started in this package.
- No push, PR, merge, deploy, publish/release, or global skill sync. Local commit is authorized after reviewer/verifier pass.

## Risks

- `adapter_smoke_ready` remains snapshot-driven. It is only as strong as the external host evidence supplied to doctor.
- A future host package must prove callable wrapper behavior in-process; model-side tool availability alone is insufficient.
- The next repo-local work should avoid re-opening host runtime unless a real host readiness snapshot exposes a specific failing contract.

## Review And Verification Gate

- Reviewer focus: confirm this package does not claim live orchestration readiness without external callable host evidence.
- Verifier focus: confirm focused tests cover non-callable descriptors, missing `parent_thread_id`, missing heartbeat scheduler, and successful callable adapter/scheduler scheduling path.
- Current manager conclusion: host adapter/scheduler gate has been explicitly checked and verifier accepted it; repo-local next gate may proceed to watcher/status extraction after local commit.