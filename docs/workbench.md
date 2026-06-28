# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: idle / no active local package task.
- Current git truth: repo clean before `ctr-20260628-team-router-optimization-local-package` dispatch; `master` synchronized with `origin/master`; global installed `codex-team-router` skill check matched repo before this package.
- Current next gate: wait for a new explicit dispatch or user authorization. No local closeout, commit, push, PR, merge, publish, release, or global skill sync is pending.
- Not done: no current task actions are pending.

## Current Diff Surface

No current diff surface is expected in idle state. For any new package, refresh from `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, and `git diff --name-only` before reporting scope.

## Verification Record

Idle-state verification baseline before the current optimization package:

- repo clean.
- `master` and `origin/master` synchronized.
- global skill check matched repo.

Current package verification belongs in the active package callback, not in this idle baseline.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

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

- Current gate: none while idle.
- Next gated step: wait for explicit dispatch or user authorization.
