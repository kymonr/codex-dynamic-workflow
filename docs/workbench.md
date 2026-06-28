# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: active local package implementation for `ctr-20260628-trust-and-modularity`; scope is P0 current-state truth checker, P1 module split plan, and router doctor/status UX.
- Current git truth is sourced from `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_closeout_check.py --json`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current next gate: executor implementation -> reviewer pass -> verifier pass -> local closeout.
- Reviewer note: pre-save reviewer threads `019f0e79-746a-7bb2-b509-7ca9f74a7bf2` and `019f0e7b-5c1c-7b22-b6fe-32be6bc8b5c2` did not return final `TEAM_ROUTER_REVIEW`; post-implementation reviewer thread `019f0e86-513b-7901-acc2-025652491814` first returned `needs_rework`, then `pass` after the doctor nextAction fix.
- Not done: no commit, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync. Those remain separate parent-thread gates after reviewer/verifier acceptance.

## Current Diff Surface

Current truth is command-derived, not a copied package list. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

During this package, expected touched areas are tests, read-only status scripts, this workbench, package docs, `docs/team-router/module-map.md`, and `skills/codex-team-router/references/testing-and-quality-gates.md`. The exact list must be taken from fresh commands because the package is still active.

`scripts/team_router_truth_check.py` is the stale-claim gate for workbench/package current-state text. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must not claim live role dispatch unless explicit readiness evidence exists.

## Verification Record

Active package verification so far:

- RED: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` failed because `scripts/team_router_truth_check.py` and `scripts/team_router_doctor.py` did not exist.
- GREEN: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 38 tests OK after adding the read-only truth and doctor scripts.
- RED docs gate: targeted `TestTeamRouterSkillDoc` workbench/module-map/quality-gates tests failed against stale workbench text, missing `docs/team-router/module-map.md`, and missing truth/doctor quality-gate documentation.
- Final compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-trust'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> OK.
- Final whitespace check: `git diff --check` -> exit 0 with CRLF/LF warnings only.
- Final full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-trust'; py -B -m unittest tests.test_team_router` -> Ran 269 tests OK.
- Final closeout check: `py -B scripts\team_router_closeout_check.py --json` -> read-only, unauthorized gates false, `skill.entrypointBytes: 6969`, `skill.underTarget: true`.
- Final truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `truthStatus` inputs dirty because this package is active.
- Final doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, no live-dispatch claim.
- Final skill sync check: `py -B scripts\team_router_skill_sync_check.py --check` -> `status: mismatch`, changed `references/testing-and-quality-gates.md`; this is expected until a separately authorized global skill sync.
- Reviewer/verifier gates: reviewer thread `019f0e86-513b-7901-acc2-025652491814` -> `pass` after rework; verifier thread `019f0e8c-163e-7ba0-82b0-b16b592168ea` -> `pass`.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-team-router-optimization-1-6` is a completed historical package. Its recorded dirty surface, skill sync result, reviewer evidence, and P2 step labels are not current git truth.
- Previous `ctr-20260628-team-router-optimization-local-package` records are historical baseline only; they are not the current active package.
- Previous `ctr-20260628-anchor-and-closeout-freshness-fix` records: verifier accepted/pass; prior local closeout/commit language is historical and no longer the Current Task.
- Previous `ctr-20260628-role-request-direct-send-and-waiting-fix` records are accepted/pass at reviewer and verifier gates.
- Previous `ctr-20260628-live-capability-state-fix` records clarified exposed app tools vs missing Python adapter/runtime orchestration. That remains true but is not the current task.
- Previous `ctr-20260628-workbench-tool-error-governance` records described a no-tools governance state. That wording is historical and must not be copied into the current state now that the Codex app thread tool surface is exposed.
- Older ahead/behind, stale current diff surface, isolated-worktree status, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, the truth/doctor scripts, and latest role-thread marker evidence.

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

- Reviewer pre-save attempts were unreachable, so post-implementation reviewer/verifier gates remain required before closeout can claim acceptance.
- Current docs are intentionally dirty while this package is active; use command output rather than copied lists.
- Repo/global skill comparison may be match or mismatch depending on whether separately authorized global sync has happened; the current value must come from `scripts/team_router_truth_check.py`, not prose.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: local implementation, reviewer, and verifier gates complete.
- Next gated step: local closeout decision only; commit, push, PR, merge, deploy, publish, release, and global skill sync remain separate unauthorized gates.
- Commit, push, PR, merge, deploy, publish, release, and global skill sync remain unauthorized.
