# ctr-20260701-role-thread-bootstrap-package-only

## Package Metadata

- taskId: `ctr-20260701-role-thread-bootstrap-package-only`
- branch: `codex/role-thread-bootstrap-package-only`
- permission: local-package implementation only; commit/push/global sync not included unless separately authorized.
- scope: `src/team_router.py`, `tests/test_team_router.py`, `docs/workbench.md`, this package file.

## Objective

Make manual/role-thread bootstrap package-only: when a reviewer/verifier role thread is created from a package handoff, the bootstrap can carry only the role, permission, package id, `reviewPackagePath`, and short role metadata. It must not inline raw callback evidence, reviewer marker blocks, verifier marker blocks, full logs, or full review output.

## Boundary

Included:

- Add `make_role_thread_package_bootstrap_message()` as a deterministic prompt helper in `src/team_router.py`.
- Cover the helper with a focused test that asserts package pointer fields are present and raw review/verifier evidence fields are absent.
- Update workbench/package state for this active repo-local package.

Excluded:

- No parser, gate, direct-return, watcher, host, thread adapter, live adapter, registry, ledger, production scheduler, push, PR, deploy, publish/release, or global skill sync behavior.
- No change to existing `make_reviewer_request_message()` / `make_verifier_request_message()` formal role request semantics.

## Implementation Notes

- New helper validates `taskId`, `role`, `permission`, and `reviewPackagePath` using existing local validators.
- The helper emits a short `<codex_delegation>` block with optional `sourceThreadId`, `reviewerThreadId`, and `reviewerResult` fields.
- The helper now includes the role entry marker (`TEAM_ROUTER_REVIEW_REQUEST`, `TEAM_ROUTER_VERIFY`, or dispatch fallback) so callers can use its output directly as the initial thread prompt.
- Human instruction says to read only the package path and short fields, return the role's standard `TEAM_ROUTER_*` marker from the package contract, and not copy raw callback/review/verifier evidence or full logs.
- Rework note: a manual reviewer/verifier dispatch on 2026-07-01 still pasted scope, checklist, and output schema into the initial prompt. This package now treats that as invalid dispatch shape and tests that bootstrap output omits `Scope:`, `Please check`, `Return only`, `evidenceChecked:`, `findings:`, and `requiredChanges:`.

## Role Thread Instructions

- Reviewer: read this package and current diff, then return the standard `TEAM_ROUTER_REVIEW` marker. Do not require inline scope/checklist/schema from the initial prompt.
- Verifier: read this package, current diff, and reviewer marker, then return the standard `TEAM_ROUTER_VERDICT` marker. Do not require inline scope/checklist/schema from the initial prompt.
- Both roles must keep the thread read-only and must not stage, commit, push, PR, merge, deploy, publish/release, or global skill sync.

## Verification Record

- RED: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_thread_package_bootstrap_is_pointer_only -v` failed before implementation with `AttributeError: module 'team_router' has no attribute 'make_role_thread_package_bootstrap_message'`.
- GREEN: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_thread_package_bootstrap_is_pointer_only -v` -> OK.
- REWORK: user observed live dispatch still had a long prompt; tightened the helper/test so the generated bootstrap is directly sendable and excludes scope/checklist/output-schema prose.
- REWORK focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_thread_package_bootstrap_is_pointer_only -v` -> OK; related prompt/workbench tests -> Ran 6 OK; generated reviewer bootstrap length 572 and contains no `Scope:`, `Please check`, or `Return only`.
- REVIEWER REWORK: short bootstrap fields now reject multiline protocol/schema injection, `reviewerResult` is limited to short enum values, and `reviewPackagePath` uses workspace path validation. `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 354 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- Related prompt/workbench checks: focused package-bootstrap test, role request language/path-handoff tests, workbench current-state test, and module-map boundary test -> OK.
- Full suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 354 tests OK.
- Truth check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; commit/push/globalSync authorization false.
- Doctor check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; next action is reviewer then verifier before closeout.
- `git diff --check` -> exit 0 with CRLF/LF warning for `docs/workbench.md` only.
- Reviewer v3: thread `019f1c7b-e299-7822-bf8a-fbcba74e6049` -> pass; `requiredChanges: none`.
- Verifier: thread `019f1c7d-d43c-70b1-a681-adb6fb4a6ea4` -> pass; `requiredChanges: []`.
- Local closeout: explicitly authorized in-thread; commit is the only included side effect. push/PR/merge/deploy/publish/global sync remain outside this package.

## Review And Verification Gate

Current next gate: none after local closeout commit. push, PR, merge to remote, deploy, publish/release, and global skill sync remain outside this package unless separately authorized.
