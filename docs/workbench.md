# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: active local package implementation for `ctr-20260628-team-router-optimization-1-6`; P2-5 is the current workbench/package-state refresh.
- Current git truth before this P2-5 document refresh was sourced from `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, and `py -B scripts\team_router_closeout_check.py --json`.
- Current next gate: P2-5 docs update -> reviewer pass -> verifier pass -> P2-6 final verification.
- Not done: no commit, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync. Those remain separate parent-thread gates after verifier acceptance.

## Current Diff Surface

Latest `git status -s --untracked-files=all` for the current workbench/package refresh reports:

- `M docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md`
- `M docs/workbench.md`
- `M skills/codex-team-router/SKILL.md`
- `M src/team_router.py`
- `M tests/test_team_router.py`

Latest `git diff --name-only` reports the same five tracked files. Current closeout must use fresh `git status -s --untracked-files=all` and the read-only closeout helper, not historical package lists.

## Verification Record

Active package verification so far:

- P1/P2 runtime and skill work have passed focused reviewer/verifier gates through P2-4.
- P2-4 closeout helper review initially requested stronger unauthorized-gate assertions for `pullRequest`, `merge`, and `deploy`; the focused test was updated with those assertions.
- P2-4 reviewer pass: rework satisfied the unauthorized-gate assertion gap; no required changes remained.
- P2-4 verifier pass: closeout helper accepted after `docs/workbench.md` was explicitly accounted as out-of-scope dirty and the helper correctly reported it in `diffFiles`.
- Focused closeout test: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_closeout_check_reports_read_only_status_and_unauthorized_gates` -> OK.
- Manager full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-p2-4-manager'; py -B -m unittest tests.test_team_router` -> Ran 265 tests OK.
- `py -B scripts\team_router_closeout_check.py --json` reports `skill.entrypointBytes: 6969`, `skill.underTarget: true`, `authorization` all false, and `skillSync.status: mismatch` because repo `SKILL.md` changed while global sync is unauthorized.
- Remaining verification: P2-5 document review/verifier, then P2-6 py_compile, full unittest, `git diff --check`, repo/global skill drift check, and read-only closeout check.

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

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- `docs/workbench.md` includes the Addy note above as an out-of-scope dirty item; it is accounted here and must not be treated as a Team Router runtime/protocol change.
- `skillSync.status` remains `mismatch` until a separately authorized global skill sync is run.
- Git may print CRLF/LF replacement warnings for `src/team_router.py` and `tests/test_team_router.py`.

## Review And Verification Gate

- Current gate: P2-5 document-state refresh.
- Next gated step: reviewer pass, then verifier pass, then P2-6 final verification.
- Commit, push, PR, merge, deploy, publish, release, and global skill sync remain unauthorized.