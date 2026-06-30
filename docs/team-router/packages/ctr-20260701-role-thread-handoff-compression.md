# ctr-20260701-role-thread-handoff-compression

## Package Metadata

- taskId: `ctr-20260701-role-thread-handoff-compression`
- permission: `local-package`
- objective: compress reviewer/verifier role request prompts so package-path handoff carries raw callback/review evidence through `executorReportPath` or `reviewPackagePath` instead of inline thread text.
- scope: `src/team_router.py`, `tests/test_team_router.py`, `docs/workbench.md`, `docs/team-router/module-map.md`, `docs/superpowers/plans/2026-07-01-role-thread-handoff-compression.md`, this package file.
- outOfScope: parser, gate policy, direct-return validation, watcher cadence, host runtime, thread adapter behavior, live adapter, production scheduler/daemon, commit, push, PR, merge, deploy, publish/release, global skill sync.

## Changes

- `src/team_router.py`: compact callback context now emits `callbackRawLocation: executorReportPath 或 reviewPackagePath` and omits callback field values in compact path-handoff mode. Package-handoff role prompts use a shorter policy block while preserving `roleCommunicationMode`, token boundary, long-context policy, and evidence boundary anchors.
- `tests/test_team_router.py`: added reviewer and verifier prompt tests that assert package paths remain visible while callback evidence and raw reviewer text stay out of role prompts.
- `docs/workbench.md`: records this active package, boundary, current verification, and reviewer -> verifier next gate.
- `docs/team-router/module-map.md`: records that reviewer/verifier package-handoff prompt compression remains facade-local prompt transport.

## Boundary

This package changes only prompt construction and docs/tests. Runtime still treats `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` as evidence metadata. It does not read, execute, trust, or auto-generate package files.

## TDD Evidence

- Baseline: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 351 tests OK before implementation.
- RED: reviewer/verifier path-first prompt tests failed before implementation because compact prompts still copied callback evidence or exceeded length caps.
- GREEN: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback -v` -> Ran 2 tests OK.
- Related prompt regression: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise tests.test_team_router.TestTeamRouterProtocol.test_manager_reviewer_verifier_prompts_codify_path_handoff_contract -v` -> Ran 4 tests OK.

## Verification

- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- Full suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 353 tests OK.
- Truth check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; dirty surface is this active package; commit/push/globalSync false.
- Doctor check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_doctor.py --json` -> exit 0; nextAction is reviewer pass then verifier pass before closeout.
- Closeout check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_closeout_check.py --json` -> exit 0; commit/push/globalSync false. Skill-sync output is evidence-only: main worktree reported `status: match`, while reviewer worktree reported `status: mismatch` for `references/testing-and-quality-gates.md`; verifier must use fresh local output and this package does not authorize global sync.
- `git diff --check` -> exit 0 with CRLF/LF warnings only.

## Review Gates

- Reviewer gate: pass in v2 thread `019f1984-0ec5-7f41-84d4-64104e03ef36`; original reviewer thread `019f1980-44fb-7300-86d9-485025e89645` found the skill-sync freshness wording issue, and v2 confirmed the rework with `requiredChanges: none`.
- Verifier gate: pass in thread `019f1988-013c-7f43-8bc3-13a1c6b77988`; `findings: none`, `requiredChanges: none`. Fresh verifier worktree `skillSync.status` was `mismatch` for `references/testing-and-quality-gates.md`; this is evidence-only, outside scoped diff, and does not authorize global sync.
- Commit, push, and global skill sync: not authorized in this package.