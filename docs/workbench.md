# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: active local package implementation for `ctr-20260628-team-router-optimization-1-6`.
- Current git truth: refreshed during this package with `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, and `git diff --name-only`; branch is `master...origin/master` with no ahead/behind marker shown, and the worktree has the package diff listed below.
- Current next gate: executor callback -> reviewer pass -> verifier pass. No local closeout, commit, push, PR, merge, publish, release, or global skill sync is authorized in this executor package.
- Not done: No commit, no push, no PR, no merge, no deploy, no global skill sync. Final commit/global sync decisions remain parent-thread gates after verifier pass.

## Current Diff Surface

Fresh `git status -s --untracked-files=all` for this active package currently reports:

- `M skills/codex-team-router/SKILL.md`
- `M skills/codex-team-router/references/adapter-runtime.md`
- `M skills/codex-team-router/references/testing-and-quality-gates.md`
- `M src/team_router.py`
- `M tests/test_team_router.py`
- `?? docs/superpowers/plans/2026-06-28-team-router-optimization-1-6.md`
- `?? docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md`
- `?? scripts/team_router_closeout_check.py`

Fresh `git diff --name-only` reports tracked modified files only and does not include untracked plan/script/package files until they are tracked. Closeout/package scope must therefore use `git status -s --untracked-files=all` as the current diff surface source, not `git diff --name-only` alone.

## Verification Record

Active package verification so far:

- RED: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` failed as expected for missing `explain_team_router_gate`, missing `assess_live_orchestration_readiness`, and missing closeout check script; one environment-only temp cleanup issue was corrected to avoid Windows restricted-token Temp cleanup.
- GREEN focused: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` passed after helper/script implementation.
- Remaining verification: py_compile, focused/full unittest, `git diff --check`, `py -B scripts/team_router_skill_sync_check.py --check`, and `py -B scripts/team_router_closeout_check.py`.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-team-router-optimization-local-package` records are historical baseline only; they are not the current active package.
- Previous `ctr-20260628-anchor-and-closeout-freshness-fix` records: verifier accepted/pass; prior local closeout/commit language is historical and no longer the Current Task.
- Previous `ctr-20260628-role-request-direct-send-and-waiting-fix` records are accepted/pass at reviewer and verifier gates.
- Previous `ctr-20260628-live-capability-state-fix` records clarified exposed app tools vs missing Python adapter/runtime orchestration. That remains true but is not the current task.
- Previous `ctr-20260628-workbench-tool-error-governance` records described a no-tools governance state. That wording is historical and must not be copied into the current state now that the Codex app thread tool surface is exposed.
- Older ahead/behind, stale current diff surface, isolated-worktree status, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, and the latest role-thread marker evidence.

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library.
- Runtime/docs/tests changes require an active package plus reviewer/verifier gates.
- Workbench current state must not claim old completed tasks as active work.

## Review And Verification Gate

- Current gate: active executor package; next is reviewer.
- Next gated step: reviewer pass, then verifier pass. Commit, push, PR, merge, deploy, publish, release, and global skill sync remain unauthorized.