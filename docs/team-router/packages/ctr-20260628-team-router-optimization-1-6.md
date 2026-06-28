# Team Router Optimization 1-6 Review Package

## Objective

Implement `ctr-20260628-team-router-optimization-1-6` local package items 1-6 without push, PR, merge, deploy, release, or global skill sync.

## Current Scope

Current expected dirty surface after this P2-5 document refresh:

- `docs/workbench.md` - workbench current-state refresh and out-of-scope Addy note accounting.
- `docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md` - this review package refresh.
- `skills/codex-team-router/SKILL.md` - slimmed entrypoint, currently 6969 bytes and under the 7200 target.
- `src/team_router.py` - runtime helper and live orchestration readiness/heartbeat/direct-return support.
- `tests/test_team_router.py` - focused and integration coverage, including closeout authorization gates.

Tracked clean or not in the current diff surface before this P2-5 refresh:

- `scripts/team_router_closeout_check.py`
- `skills/codex-team-router/references/adapter-runtime.md`
- `skills/codex-team-router/references/testing-and-quality-gates.md`
- `README.md`
- `docs/superpowers/plans/2026-06-28-team-router-optimization-1-6.md`

Out of scope:

- `C:\Users\Orz\.codex\skills\codex-team-router`
- push, PR, merge, deploy, release, publish
- global skill sync
- commit until a later explicit local closeout/commit gate
- reverting unrelated user or external dirty work without explicit instruction

## Diff Summary

- Slimmed `skills/codex-team-router/SKILL.md` to 6969 bytes while preserving hard Manager Mode, live boundary, direct return, reviewer/verifier, closeout, and authorization rules.
- Added/connected deterministic runtime helpers for readable gate explanations, live orchestration readiness, parent thread id, host adapter context, callable heartbeat scheduling, and malformed direct-return telemetry.
- Strengthened malformed direct-return tests for wrong/missing protocol `sourceThreadId`, `role`, and `sourceRoleThreadId` while preserving self-thread fallback behavior.
- Added and validated read-only closeout reporting for git status, diff files, SKILL size/cap/target, repo/global skill drift, and unauthorized commit/push/PR/merge/deploy/global sync gates.
- Updated `tests/test_team_router.py` closeout coverage after reviewer found missing `pullRequest`, `merge`, and `deploy` false assertions.
- Accounted for `docs/workbench.md` Addy Engineering Checklists note as out-of-scope dirty, not a Team Router runtime, protocol, package, role-contract, or authorization change.
- Refreshed workbench/package state so historical package records are not reused as current git truth.

## TDD And Review Evidence

- Earlier RED work exposed missing helper/readiness/closeout contracts; implementation then moved through focused GREEN tests.
- P2-1 heartbeat scheduler interface: reviewer/verifier accepted callable/interface scheduler validation and scheduling behavior.
- P2-2 host context helper: reviewer/verifier accepted readiness-based host context and conflict-before-side-effect behavior.
- P2-3 direct-return malformed telemetry: reviewer/verifier accepted telemetry/fallback test hardening.
- P2-4 closeout helper: reviewer first requested missing unauthorized-gate assertions; after rework, reviewer passed and verifier passed after `docs/workbench.md` was explicitly accounted as out-of-scope dirty.

## Tests And Checks

Passed in the current package sequence:

- `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_closeout_check_reports_read_only_status_and_unauthorized_gates` -> OK.
- `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-p2-4-manager'; py -B -m unittest tests.test_team_router` -> Ran 265 tests OK.
- `git diff --check` -> exit 0, with CRLF/LF warnings only for `src/team_router.py` and `tests/test_team_router.py`.
- `py -B scripts\team_router_closeout_check.py --json` -> reports read-only mode, `authorization` all false, `skill.entrypointBytes: 6969`, `skill.underTarget: true`, and `skillSync.status: mismatch` due unsynced repo `SKILL.md`.

Required for P2-6 final verification:

- `py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py`
- `py -B -m unittest tests.test_team_router`
- `git diff --check`
- `py -B scripts\team_router_skill_sync_check.py --check`
- `py -B scripts\team_router_closeout_check.py`

## Not Done

- no commit
- no push
- no PR
- no merge
- no deploy
- no release/publish
- no global skill sync

## Risks

- `py -B scripts\team_router_skill_sync_check.py --check` is expected to report `status: mismatch` until a separately authorized global skill sync copies the changed repo skill entrypoint.
- `docs/workbench.md` contains an out-of-scope Addy checklist note. It is explicitly accounted, but it should remain separate from the Team Router runtime/protocol package.
- Git may print CRLF/LF replacement warnings for existing text files.
- Several executor attempts were blocked by the Windows `apply_patch` sandbox wrapper; parent manager applied narrow, reviewed edits where required.

## Global Sync / Commit / Push Status

- globalSyncStatus: not run with `--sync`; repo/global expected mismatch until separate authorization.
- commitStatus: not committed; local commit requires a separate explicit gate after reviewer and verifier acceptance.
- pushStatus: not pushed / not authorized.