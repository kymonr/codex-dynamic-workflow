# Team Router Review Package: ctr-20260630-status-closeout-extraction

## Package Metadata

- taskId: `ctr-20260630-status-closeout-extraction`
- permission: `local-package`
- objective: extract closeout/handoff text helpers into `src/team_router_status.py` after the watcher runtime split while preserving public facade compatibility.
- scope: `src/team_router.py`, `src/team_router_status.py`, `tests/test_team_router.py`, `docs/workbench.md`, `docs/team-router/module-map.md`, this package file.
- outOfScope: truth_check/doctor/closeout script internals, real host adapter implementation, production scheduler/daemon, push, PR, merge, deploy, publish/release, global skill sync.

## Current Intent

- Move closeout and handoff formatting helpers out of `src/team_router.py`.
- Keep `src/team_router.py` as the public facade and compatibility import surface.
- Preserve `format_closeout_for_user`, `format_handoff_for_user`, and `format_task_update_for_user` behavior.
- Use `watcher_builder` from the facade so `format_handoff_for_user` still includes manager watcher details when the ledger has no precomputed `watcher` field.
- Keep `src/team_router_status.py` deterministic: it does not import `team_router` and does not call Codex thread tools.

## Implemented Changes

- Added `src/team_router_status.py` for role-thread lines, read anchor lines, closeout compounding defaults, `format_closeout_for_user`, `format_handoff_for_user`, and `format_task_update_for_user`.
- Updated `src/team_router.py` to import status helpers and keep thin wrappers for `format_handoff_for_user` / `format_task_update_for_user` that pass `_watcher_ledger` as `watcher_builder`.
- Updated module-map expectations so status/closeout text helpers are implemented while truth_check/doctor/closeout scripts remain read-only evidence tools.

## Verification Evidence

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

## Boundary

- truth_check/doctor/closeout scripts remain read-only evidence tools in this package.
- real live host integration remains an external host package gate.
- No production scheduler/daemon was added.
- Commit: authorized by the user and completed as a local commit for this status/closeout package.

## Next Gate

- Run focused docs/module/status tests, full `test_team_router.py`, truth_check, doctor, closeout_check, and diff checks.
- Reviewer and verifier role threads passed by direct-send; local commit completed after explicit user authorization.
- No further repo-local status/closeout action remains in this package.
