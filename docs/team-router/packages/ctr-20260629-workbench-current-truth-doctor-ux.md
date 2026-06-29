# Team Router Review Package: ctr-20260629-workbench-current-truth-doctor-ux

## Task Summary

- taskId: `ctr-20260629-workbench-current-truth-doctor-ux`
- objective: reduce manager misjudgment when workbench/package current-state text claims active or pending work while live git/skill truth is clean/synced.
- permission: `local-package`; closeout later explicitly authorized global skill sync and local commit.
- execution mode: executor local implementation, reviewer/verifier gates, global skill sync, and local closeout commit only. No push, PR, merge, deploy, publish/release, external network, real APIs, or module extraction.

## Scope

- Generic stale current-state detection in `scripts/team_router_truth_check.py`.
- Manager-facing doctor `nextAction`/summary UX in `scripts/team_router_doctor.py`.
- Focused regression tests in `tests/test_team_router.py`.
- Contract documentation in `skills/codex-team-router/references/testing-and-quality-gates.md`.
- Current active-state refresh in `docs/workbench.md`.

## Touched Files

- `scripts/team_router_truth_check.py`
- `scripts/team_router_doctor.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/references/testing-and-quality-gates.md`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260629-workbench-current-truth-doctor-ux.md`

## Behavior Changes

- `team_router_truth_check.py` now scans explicit Current Task / Current Diff Surface / current-state sections instead of relying only on the old hardcoded `ctr-20260628-team-router-optimization-1-6` stale detector.
- Rework after reviewer P1 narrowed stale markers: section headings and neutral field labels such as `## Current Diff Surface`, `Current next gate: none`, and `no action required` are not stale claims.
- When live git status/diff are clean and repo/global skill sync is `match`, current-state text claiming active package work, explicit pending reviewer/verifier gates, or explicit dirty diff entries/status is reported in `staleClaims`.
- Historical package/archive sections with stale-sounding text are ignored when they are not in current-state sections.
- `team_router_doctor.py` exposes top-level `nextAction` and tells managers to refresh workbench/package current-state text from truth_check/doctor evidence before claiming current truth when stale claims exist.
- Both tools remain read-only/evidence-only.

## Diff Summary

- Added current-state heading and marker constants plus helpers for section-scoped stale detection.
- Reworked dirty/pending marker matching to ignore headings and neutral current-state labels.
- Added tests for clean/synced stale active workbench claims, clean/synced neutral current sections, historical false-positive avoidance, and stale doctor `nextAction` wording.
- Updated workbench current task from the old host-adapter package to this package, then refreshed it at closeout to avoid post-commit stale active/pending claims.
- Documented stale-current-state detector and doctor UX contract in quality gates.

## Verification

- Rework focused stale-current-state tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_truth_check_detects_stale_current_state_when_clean_synced tests.test_team_router.TestTeamRouterState.test_truth_check_does_not_flag_clean_synced_neutral_current_sections tests.test_team_router.TestTeamRouterState.test_truth_check_does_not_flag_historical_package_records_as_current tests.test_team_router.TestTeamRouterState.test_truth_check_reports_stale_claims_and_is_read_only tests.test_team_router.TestTeamRouterState.test_router_doctor_stale_next_action_names_truth_check_and_doctor tests.test_team_router.TestTeamRouterState.test_router_doctor_reports_plain_status_without_dispatch -v` -> Ran 6 tests OK.
- Rework synthetic clean/synced probe: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -c "... find_stale_state_claims(... ## Current Diff Surface ... Current next gate: none; no action required ...)"` -> `[]`.
- Focused docs contract tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_name_truth_and_doctor_read_only_tools -v` -> Ran 2 tests OK.
- Full docs suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 46 tests OK before rework; focused docs tests were rerun after rework and remain OK.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m py_compile scripts\team_router_truth_check.py scripts\team_router_doctor.py tests\test_team_router.py` -> OK.
- Full relevant state suite attempt before rework: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 47 tests; 46 OK, 1 unrelated existing failure in `test_protocol_contract_snapshot_includes_manager_orchestration_policy` because current runtime snapshot includes architect/QA direct-return markers while this assertion expects only executor/reviewer/verifier markers.
- Global skill sync: `Copy-Item -LiteralPath 'D:\codex\Team Router\skills\codex-team-router\references\testing-and-quality-gates.md' -Destination 'C:\Users\Orz\.codex\skills\codex-team-router\references\testing-and-quality-gates.md' -Force` -> exit 0 after closeout authorization.
- Closeout check after global sync: `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`; no global skill reference differences.
- Truth check after global sync: `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; package files still reported before local commit; `skillSync.status: match`.
- Doctor check after global sync: `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty` before local commit; `orchestrationStatus: manual_only`; top-level `nextAction` present.
- Focused closeout tests after global sync: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_name_truth_and_doctor_read_only_tools tests.test_team_router.TestTeamRouterState.test_truth_check_detects_stale_current_state_when_clean_synced tests.test_team_router.TestTeamRouterState.test_truth_check_does_not_flag_clean_synced_neutral_current_sections tests.test_team_router.TestTeamRouterState.test_router_doctor_stale_next_action_names_truth_check_and_doctor -v` -> Ran 5 tests OK.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.
- Git status: `git status -sb --untracked-files=all` -> `master...origin/master` with modified `docs/workbench.md`, `scripts/team_router_doctor.py`, `scripts/team_router_truth_check.py`, `skills/codex-team-router/references/testing-and-quality-gates.md`, `tests/test_team_router.py`, and untracked package doc.

## Excluded Changes

- No changes to `src/team_router.py` runtime, adapter orchestration, watcher cadence, registry, ledger, protocol parsing, or module extraction.
- No project-local `AGENTS.md` changes.
- No push, PR, merge, deploy, publish/release, external network, real API, or module extraction.
- Commit/stage and global skill sync were added only by the explicit closeout authorization.

## Risks

- The detector is intentionally conservative and section-scoped; stale claims outside recognized current-state sections may require a future explicit marker/heading contract.
- The reviewer P1 false-positive risk for neutral `Current Diff Surface` / `Current next gate: none` text is covered by a negative regression test and synthetic probe.
- A broader `TestTeamRouterState` suite currently exposes an unrelated existing marker-contract assertion mismatch around architect/QA markers; this package does not change that runtime contract.

## Remaining Todos

- None for this package after the local closeout commit.
- Next package candidate remains `module extraction phase 1: policy/protocol split`, only on explicit dispatch.