# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: active local-package `ctr-20260630-host-adapter-scheduler`; reviewer/verifier accepted and local commit is authorized.
- Last package objective: explicitly check the host adapter/scheduler gate before watcher/status extraction, without fabricating callable host support from model-side Codex app tool descriptors.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live orchestration, no fake host adapter/scheduler implementation, no watcher/status extraction, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync in this package. Repo/global skill comparison remains `status: match` because this package did not edit the skill files.
- Current next gate: repository-side host readiness and scheduler guards are already covered; real live host integration still requires an external host package that supplies callable Python adapter/scheduler evidence. The next repo-local module package can continue with watcher/status extraction.

## Current Diff Surface

Current truth is command-derived. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

This file intentionally does not list a live diff surface. The closeout package files are recorded in the review package, and the exact current surface must be taken from fresh commands before any new claim.

`scripts/team_router_truth_check.py` is the stale-current-state gate for workbench/package text. It should focus on Current Task / Current Diff Surface style sections so historical package archives are not treated as live truth. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must remain read-only/evidence-only.

## Verification Record

Active package verification:

- Host package intake: `git status -sb --untracked-files=all` ran before docs update; branch/ahead state is intentionally not copied here because fresh git status is the source of truth.
- Current truth check before docs update: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; `gitStatusShort: []`.
- Doctor check before docs update: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: clean_synced`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction: no action required unless the manager opens a new package`.
- Focused host context tests: `py -B -m unittest tests.test_team_router -k "host_context" -v` -> Ran 4 tests OK.
- Focused host adapter/scheduler tests: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_thread_adapter_capability_probe_reports_missing_tools tests.test_team_router.TestTeamRouterManagerIntegration.test_thread_adapter_capability_probe_rejects_model_tool_descriptors tests.test_team_router.TestTeamRouterManagerIntegration.test_parent_entry_guard_blocks_adapter_runner_without_callable_tools tests.test_team_router.TestTeamRouterManagerIntegration.test_parent_entry_guard_accepts_full_callable_adapter_path tests.test_team_router.TestTeamRouterManagerIntegration.test_orchestrate_team_task_requires_parent_current_thread_rename_before_role_dispatch tests.test_team_router.TestTeamRouterManagerIntegration.test_orchestrate_team_task_blocks_when_parent_thread_id_is_unavailable tests.test_team_router.TestTeamRouterManagerIntegration.test_orchestrate_team_task_blocks_when_heartbeat_scheduler_is_not_callable -v` -> Ran 7 tests OK.
- Corrected verification note: an earlier focused command used the wrong unittest class path (`TestTeamRouterProtocol`) and failed with `AttributeError`; the corrected `TestTeamRouterManagerIntegration` command above passed.

- Docs gate after test expectation update: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_thread_tool_absence_is_tool_error_or_manual_only_not_role_dispatch tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_host_readiness_snapshots -v` -> Ran 3 tests OK.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 337 tests OK.
- Truth check after docs/test update: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty files are `docs/workbench.md`, `tests/test_team_router.py`, and this package record.
- Doctor check after docs/test update: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; entrypoint `underTarget: true`.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.

- Reviewer role thread `019f17f2-2fea-7b02-b1a0-f96dec82c453` returned `TEAM_ROUTER_REVIEW result: pass`, `requiredChanges: none`.
- Verifier role thread `019f17f5-f216-7802-bb8a-e74f63c2c800` returned `TEAM_ROUTER_VERDICT result: pass`, `requiredChanges: none`.

Previous package verification:

- RED focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterState.test_truth_check_detects_workbench_current_package_behind_latest_package -v` -> failed before implementation because downstream prompts copied raw callback/review payloads and `find_stale_state_claims(...)` returned no workbench/package-lag claim.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterState.test_truth_check_detects_workbench_current_package_behind_latest_package -v` -> Ran 2 tests OK.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-prompt-compact'; py -B -m py_compile src\team_router.py scripts\team_router_truth_check.py tests\test_team_router.py` -> OK.
- Initial truth check while package is dirty: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty files are this package's runtime/test/docs edits.
- Initial doctor check while package is dirty: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `hostReadiness.summary: no host readiness snapshot supplied; manual orchestration only`.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 337 tests OK.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty files are this package's runtime/test/docs edits before commit.
- Doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; entrypoint `underTarget: true`.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-role-thread-readiness-status` completed read-only role-thread status UX in `scripts/team_router_doctor.py`; it added `--role-status-json` and `roleThreadStatus` from supplied snapshots only.
- Previous `ctr-20260628-live-capability-state-fix` clarified exposed app tools versus missing Python callable adapter/runtime orchestration. That remains the baseline boundary for this package.
- Previous `ctr-20260628-trust-and-modularity` is a completed historical package covering the current-state truth checker, module split plan, and initial doctor/status UX. Its recorded diff surface, verifier evidence, and sync state are not current git truth.
- Previous `ctr-20260628-team-router-optimization-1-6` is a completed historical package. Its recorded dirty surface, skill sync result, reviewer evidence, and P2 step labels are not current git truth.
- Previous `ctr-20260628-team-router-optimization-local-package` records are historical baseline only; they are not the current active package.
- Previous `ctr-20260628-anchor-and-closeout-freshness-fix` records: verifier accepted/pass; prior local closeout/commit language is historical and no longer the Current Task.
- Previous `ctr-20260628-role-request-direct-send-and-waiting-fix` records are accepted/pass at reviewer and verifier gates.
- Previous `ctr-20260628-workbench-tool-error-governance` records described a no-tools governance state. That wording is historical and must not be copied into the current state now that the Codex app thread tool surface is exposed.
- Older ahead/behind, stale current diff surface, isolated-worktree status, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, the truth/doctor scripts, and latest role-thread marker evidence.

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library.
- Runtime/docs/tests changes require an active package plus reviewer/verifier gates.
- Workbench current state must not claim old completed tasks as active work.
- Stale-current-state detection and doctor nextAction in this package are evidence-only UX; they do not modify dispatch, watcher cadence, registry, ledger, or protocol parsing.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- The stale-current-state detector remains section-scoped. It should catch manager-facing current-state drift, workbench package-date lag, and completed phase references without treating historical package archives as live truth.
- Prompt compaction only activates when path fields exist. Inline-only fallback keeps raw callback/review context so manual flows do not lose evidence.
- `scripts/team_router_doctor.py` remains evidence-only; `nextAction` is guidance, not protocol acceptance.
- Real host adapter/scheduler integration is not implemented inside this repo. Current doctor evidence reports no supplied callable host readiness snapshot and `orchestrationStatus: manual_only`; model-side app tool descriptors remain non-callable for Python helpers until a host wrapper supplies real callables.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: explicit host adapter/scheduler package confirms repository-side guards are already in place and focused tests pass; current package docs are being refreshed.
- Next gated step: continue watcher/status module extraction as the next repo-local package, while real live host integration remains blocked until an external host supplies callable adapter/scheduler evidence. Push, PR, merge, deploy, publish/release, and global skill sync remain out of scope.
