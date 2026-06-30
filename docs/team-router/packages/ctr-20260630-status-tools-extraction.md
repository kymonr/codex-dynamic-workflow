# Team Router Review Package: ctr-20260630-status-tools-extraction

## Summary

- taskId: `ctr-20260630-status-tools-extraction`
- package type: repo-local implementation package
- baseline: committed status/closeout package `d66b77d`
- scope: extract read-only status tools shared by truth_check, doctor, and closeout_check into `src/team_router_status_tools.py`
- Commit: authorized for local closeout

## Changed Files

- `src/team_router_status_tools.py`: new read-only status tools module for shared helpers.
- `scripts/team_router_truth_check.py`: thin CLI wrapper importing `build_truth_report` and `find_stale_state_claims` from the extracted module.
- `scripts/team_router_closeout_check.py`: thin CLI wrapper importing `build_closeout_report as build_report` from the extracted module.
- `scripts/team_router_doctor.py`: reuses extracted `truth_status` and `next_action`; doctor-specific host readiness and role-thread snapshot classification remain local to the script.
- `tests/test_team_router.py`: covers the extraction boundary and the workbench/package/module-map records.
- `docs/workbench.md`: records the active package state and gates.
- `docs/team-router/module-map.md`: records phase 2b6 and the extracted status-tools module.

## Extraction Boundary

`src/team_router_status_tools.py` owns these read-only status tools:

- `build_truth_report`
- `find_stale_state_claims`
- `build_closeout_report`
- `truth_status`
- `next_action`

The module does not import `team_router`, does not call thread tools, and does not mutate registry, ledger, watcher, protocol, role-thread, host adapter, or scheduler state. The scripts remain read-only evidence wrappers and must not stage, commit, push, PR, merge, deploy, publish, or sync.

real live host integration remains an external host package gate. This package does not implement a live host adapter, callable production scheduler, daemon, real API access, push, PR, merge, deploy, publish, release, global skill sync, or external account action.

## Verification Record

- RED implementation test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-red'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_status_tools_module_extracts_read_only_script_helpers -v` -> failed before implementation because `team_router_status_tools` was missing.
- GREEN implementation test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-green2'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_status_tools_module_extracts_read_only_script_helpers -v` -> Ran 1 test OK.
- Focused status tool regression: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-focused2'; py -B -m unittest tests.test_team_router -k truth_check -k router_doctor -k closeout_check -v` -> Ran 13 tests OK.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-compile2'; py -B -m py_compile src\team_router_status_tools.py scripts\team_router_truth_check.py scripts\team_router_doctor.py scripts\team_router_closeout_check.py tests\test_team_router.py` -> OK.
- RED docs tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-doc-red'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_tools_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> failed before docs update because workbench/module-map/package did not record this package.
- Focused docs/module tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-doc-green2'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_tools_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> Ran 3 tests OK.
- Focused extraction/doc regression: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-focused3'; py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_status_tools_module_extracts_read_only_script_helpers tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_status_tools_package_records_extraction_boundary tests.test_team_router.TestTeamRouterSkillDoc.test_module_map_documents_phase1_protocol_policy_split -v` -> Ran 4 tests OK.
- Full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-full'; py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 344 tests OK.
- Truth check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-truth'; py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`.
- Doctor/closeout checks: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-doctor'; py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`; `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-status-tools-closeout'; py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`, entrypoint `underTarget: true`.
- Whitespace/status: `git diff --check` -> exit 0 with CRLF/LF warnings only; `git status -sb --untracked-files=all` -> `## master...origin/master [ahead 4]` plus this package diff/untracked files.
- Reviewer result: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: needs_rework`; `deliveryStatus: direct_send`; required fixing TAB/BS control-character pollution in active verification command records.
- Reviewer-required fix: restored verification command records to literal text, added workbench/package assertions rejecting TAB and BS controls, and reran focused docs/module tests -> Ran 3 tests OK; explicit control-char check reports TAB=False and BS=False for workbench and package docs.
- Reviewer re-review result: Codex reviewer role thread `019f1809-6453-7d90-bf2f-3de7ae3bd1de` returned `TEAM_ROUTER_REVIEW result: pass`; `deliveryStatus: direct_send`; `requiredChanges: none`.
- Verifier result: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: needs_rework`; `deliveryStatus: direct_send`; required fixing stale workbench review-gate wording that still routed back to reviewer after reviewer re-review pass.
- Verifier-required fix: workbench review gate now states reviewer re-review has passed and verifier is the only remaining role gate before closeout; workbench tests reject stale reviewer-next wording in that section. Focused docs/module tests -> Ran 3 tests OK; truth_check -> `staleClaims: []`, `skillSync.status: match`; control-char check remains TAB=False and BS=False.
- Verifier re-check result: Codex verifier role thread `019f1819-8446-7381-bb6e-e366ee3d9f60` returned `TEAM_ROUTER_VERDICT result: pass`; `deliveryStatus: direct_send`; `requiredChanges: none`.

## Review And Gate State

- Reviewer: pass after rework by direct-send; requiredChanges none.
- Verifier: pass after rework by direct-send; requiredChanges none.
- Commit: authorized for local closeout.
- Push/PR/merge/deploy/publish/global skill sync: not authorized.
- Real live host integration: external host package gate.