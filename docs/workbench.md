# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: repo-local package `ctr-20260630-status-tools-extraction` is locally committed; status tools extraction starts from committed status/closeout package `d66b77d`.
- Current package objective: extract read-only truth_check/doctor/closeout shared helpers into `src/team_router_status_tools.py` while keeping `scripts/team_router_truth_check.py`, `scripts/team_router_doctor.py`, and `scripts/team_router_closeout_check.py` as read-only CLI/evidence wrappers.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live host adapter implementation, no production scheduler/daemon, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync in this package. Repo/global skill comparison remains `status: match` unless this package explicitly edits skill files.
- Current next gate: none inside repo-local status-tools extraction; real live host integration remains an external host package gate.

## Current Diff Surface

Current truth is command-derived. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

This file intentionally does not list a live diff surface. The status-tools package files are recorded in the review package, and the exact current surface must be taken from fresh commands before any new claim.

`scripts/team_router_truth_check.py` is the stale-current-state gate for workbench/package text. It should focus on Current Task / Current Diff Surface style sections so historical package archives are not treated as live truth. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must remain read-only/evidence-only.

## Verification Record

Active package verification:

- Implementation: added `src/team_router_status_tools.py` for shared read-only status tool helpers: git/skill comparison, stale-current-state scanning, truth report building, closeout report building, and doctor truth/next-action classification.
- Script wrappers: `scripts/team_router_truth_check.py` now imports `build_truth_report` and `find_stale_state_claims`; `scripts/team_router_closeout_check.py` imports `build_closeout_report as build_report`; `scripts/team_router_doctor.py` imports `truth_status` and `next_action` while retaining doctor-specific host readiness and role-thread snapshot logic.
- Boundary: `src/team_router_status_tools.py` does not import `team_router`, does not call thread tools, does not mutate Team Router state, and does not stage, commit, push, PR, merge, deploy, publish, or sync. Real live host integration remains an external host package gate.
- RED implementation test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-red'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_status_tools_module_extracts_read_only_script_helpers -v` -> failed before implementation because `team_router_status_tools` was missing.
- GREEN implementation test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-green2'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_status_tools_module_extracts_read_only_script_helpers -v` -> Ran 1 test OK.
- Focused status tool regression: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-focused2'; py -B -m unittest tests.test_team_router -k truth_check -k router_doctor -k closeout_check -v` -> Ran 13 tests OK.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-compile2'; py -B -m py_compile src\team_router_status_tools.py scripts\team_router_truth_check.py scripts\team_router_doctor.py scripts\team_router_closeout_check.py tests\test_team_router.py` -> OK.
- RED docs tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-doc-red'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_tools_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> failed before docs update because workbench/module-map/package did not record this package.
- Focused docs/module tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-doc-green2'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_tools_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> Ran 3 tests OK.
- Focused extraction/doc regression: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-focused3'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_status_tools_module_extracts_read_only_script_helpers tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_tools_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> Ran 4 tests OK.
- Full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-full'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 344 tests OK.
- Truth check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-truth'; py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty surface includes tracked module-map/workbench/status scripts/tests plus untracked package doc and `src/team_router_status_tools.py`.
- Doctor/closeout checks: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-doctor'; py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`; `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-closeout'; py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`, entrypoint `underTarget: true`.
- Whitespace/status: `git diff --check` -> exit 0 with CRLF/LF warnings only; `git status -sb --untracked-files=all` -> `## master...origin/master [ahead 4]` plus this package diff/untracked files.
- Reviewer result: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: needs_rework`; `deliveryStatus: direct_send`; required fixing TAB/BS control-character pollution in active verification command records.
- Reviewer-required fix: restored verification command records to literal text, added workbench/package assertions rejecting TAB and BS controls, and reran focused docs/module tests -> Ran 3 tests OK; explicit control-char check reports TAB=False and BS=False for workbench and package docs.
- Reviewer re-review result: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: pass`; `deliveryStatus: direct_send`; `requiredChanges: none`.
- Verifier result: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: needs_rework`; `deliveryStatus: direct_send`; required fixing stale review-gate wording that still routed back to reviewer after reviewer re-review pass.
- Verifier-required fix: the review-gate section now states reviewer re-review has passed and verifier is the only remaining role gate before closeout; workbench tests reject stale reviewer-next wording in that section. Focused docs/module tests -> Ran 3 tests OK; truth_check -> `staleClaims: []`, `skillSync.status: match`; control-char check remains TAB=False and BS=False.
- Verifier re-check result: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: pass`; `deliveryStatus: direct_send`; `requiredChanges: none`.
- Remaining verification: post-commit truth/closeout checks only; explicit commit authorization was used for this repo-local closeout.

Previous package verification:

- Previous `ctr-20260630-status-closeout-extraction` passed reviewer and verifier, then was explicitly authorized and committed as `d66b77d`; its closeout/status helper extraction is now historical baseline only.
- Previous `ctr-20260630-watcher-status-extraction` was explicitly authorized and committed as `dcff722`; its watcher runtime extraction is historical baseline only.

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
- Stale-current-state detection and doctor nextAction in this package are evidence-only UX; they do not modify dispatch, watcher cadence, registry, ledger, protocol parsing, host integration, or production scheduling.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- `scripts/team_router_doctor.py` still owns doctor-specific host readiness and role-thread snapshot classification; only shared read-only truth/next-action helpers moved in this package.
- Real host integration is still external: no live host adapter implementation, no production scheduler/daemon, and no callable host readiness snapshot is supplied by this repo package.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: repo-local status-tools extraction is locally committed; no repo-local role-thread gate remains.
- Next external gated step after local commit: real live host integration remains blocked until an external host supplies callable adapter/scheduler evidence.