# Team Router Review Package: ctr-20260630-current-truth-prompt-compact

## Package Metadata

- taskId: `ctr-20260630-current-truth-prompt-compact`
- permission: `local-package`
- objective: fix downstream prompt bloat by using path-handoff summaries, and tighten workbench/current-truth stale detection against latest package/module-map evidence.
- scope: `src/team_router.py`, `scripts/team_router_truth_check.py`, `tests/test_team_router.py`, `docs/workbench.md`, `docs/superpowers/plans/2026-06-30-team-router-current-truth-prompt-compact.md`, this package file.
- outOfScope: host adapter/scheduler implementation, watcher/status module extraction, push, PR, merge, deploy, publish/release, global skill sync.

## Changes

- `src/team_router.py`: added compact callback/reviewer-result prompt helpers. Reviewer, verifier, and QA prompts now summarize parsed callback/review fields when `taskBriefPath`, `executorReportPath`, or `reviewPackagePath` is present, while preserving raw inline fallback when no path handoff exists.
- `scripts/team_router_truth_check.py`: default scan includes `docs/team-router/module-map.md`; workbench current sections are checked for package-date lag and completed phase 1 next-gate drift.
- `tests/test_team_router.py`: added regression tests for downstream prompt compaction and workbench/package-lag detection; refreshed workbench current-state expectations.
- `docs/workbench.md`: current state now records this package and keeps host adapter/scheduler plus watcher/status extraction as separate explicit gates.

## Host And Extraction Boundary

`py -B scripts\team_router_doctor.py --json` currently reports `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`, and `hostReadiness.summary: no host readiness snapshot supplied; manual orchestration only`. That means host adapter/scheduler work is not implemented here; it needs a later host package with callable Python adapter/scheduler evidence. Watcher/status extraction remains a separate module package after that boundary.

## Verification

- RED focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterState.test_truth_check_detects_workbench_current_package_behind_latest_package -v` -> failed before implementation.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterState.test_truth_check_detects_workbench_current_package_behind_latest_package -v` -> Ran 2 tests OK.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-prompt-compact'; py -B -m py_compile src\team_router.py scripts\team_router_truth_check.py tests\test_team_router.py` -> OK.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py -v` -> Ran 337 tests OK.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; `skillSync.status: match`; dirty files limited to this package's docs/runtime/tests edits before commit.
- Doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; entrypoint `underTarget: true`; dirty files limited to this package before commit.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.

## Review And Verification Gate

- Reviewer focus: confirm prompt compaction does not remove inline fallback evidence when no path handoff exists, and truth_check remains section-scoped.
- Reviewer result: local self-review found no required changes after full-suite and current-truth checks.
- Verifier result: focused tests, full suite, truth/doctor/closeout, and `git diff --check` passed before local commit.
