# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: closeout recorded for `ctr-20260630-status-closeout-extraction`; reviewer and verifier role-thread gates passed by direct-send, and the local commit was explicitly authorized and completed for this package; status/closeout extraction starts from committed watcher runtime `dcff722`.
- Last package objective: extract closeout/handoff text helpers into `src/team_router_status.py` while preserving facade compatibility and existing manager handoff/closeout output.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live host adapter implementation, no production scheduler/daemon, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync in this package. Repo/global skill comparison remains `status: match` unless this package explicitly edits skill files.
- Current next gate: none for repo-local status/closeout extraction; wait for the next explicit repo-local package. Real live host integration remains an external host package gate.

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

- Implementation: added `src/team_router_status.py` for closeout and handoff text helpers, role-thread lines, anchor rendering, compounding defaults, and task-update formatting.
- Facade compatibility: `src/team_router.py` imports status helpers and keeps `format_handoff_for_user` / `format_task_update_for_user` wrappers that pass `_watcher_ledger` as `watcher_builder`, preserving manager watcher lines when a ledger lacks a precomputed `watcher` field.
- Boundary: truth_check/doctor/closeout scripts remain read-only evidence tools; real live host integration remains an external host package gate.
- RED implementation tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-red'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_facade_delegates_to_extracted_status_symbols tests.test_team_router.TestTeamRouterManagerIntegration.test_format_task_update_for_user_uses_closeout_only_for_terminal_closeout -v` -> failed before implementation because `team_router_status` was missing.
- GREEN implementation tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-green'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_facade_delegates_to_extracted_status_symbols tests.test_team_router.TestTeamRouterManagerIntegration.test_format_task_update_for_user_uses_closeout_only_for_terminal_closeout -v` -> Ran 2 tests OK.
- RED docs tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-doc-red'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_closeout_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> failed before docs update because workbench/module-map/package did not record this package.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-compile'; py -B -m py_compile src\team_router.py src\team_router_status.py tests\test_team_router.py` -> OK.
- Focused closeout/status regression: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-focused2'; py -B -m unittest tests.test_team_router -k closeout -k handoff -k format_task_update -v` -> Ran 19 tests OK.
- Focused docs/module/status tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-doc-green'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_closeout_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> Ran 3 tests OK.
- Full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-full'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 342 tests OK.
- Truth check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-truth'; py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty surface includes tracked module-map/workbench/team_router/tests plus untracked package doc and `src/team_router_status.py`.
- Doctor/closeout checks: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`, nextAction says reviewer then verifier before closeout; `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`, entrypoint `underTarget: true`.
- Whitespace/status: `git diff --check` -> exit 0 with CRLF/LF warnings only; `git status -sb --untracked-files=all` -> `## master...origin/master [ahead 3]` plus this package diff/untracked files.
- Reviewer rework: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `needs_rework`; required fixing `docs/workbench.md` heading pollution where `## Current Diff Surface` and `## Review And Verification Gate` were glued to the previous list item.
- Reviewer-required title cleanup: restored those headings to standalone lines and added workbench assertions that both headings must match `^## ...$` and must not appear as glued `...## ...` text.
- Reviewer-required focused test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-extraction-rework-doc'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 1 test OK.
- Reviewer re-review result: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: pass`; `deliveryStatus: direct_send`; `requiredChanges: none`; remaining gate is verifier.
- Verifier final result: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: pass`; `deliveryStatus: direct_send`; `requiredChanges: none`; remaining gate is explicit commit authorization.

Previous package verification:
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

- `src/team_router_status.py` currently extracts closeout/handoff text helpers only. Moving truth_check/doctor/closeout script internals remains out of this package.
- `format_handoff_for_user` depends on a facade-supplied `watcher_builder` to preserve watcher metadata without importing `team_router` from the status module.
- Real host integration is still external: no live host adapter implementation, no production scheduler/daemon, and no callable host readiness snapshot is supplied by this repo package.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: status/closeout text helper extraction passed reviewer and verifier; local closeout and local commit are recorded.
- Next gated step: none for this repo-local status/closeout package. Real live host integration remains blocked until an external host supplies callable adapter/scheduler evidence.
