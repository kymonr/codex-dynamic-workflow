# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: local package accepted, committed, and global skill synced for `ctr-20260628-role-thread-readiness-status`; scope is read-only role-thread readiness/status UX in `scripts/team_router_doctor.py`.
- Current git truth is sourced from `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_closeout_check.py --json`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- New status surface: `scripts/team_router_doctor.py --role-status-json <path> --json` reports `roleThreadStatus` from a caller-supplied snapshot only; it does not create, read, poll, or send to role threads.
- Current next gate: push/PR decision or stop; local package commit and global skill sync are complete. Gate sequence completed: executor implementation -> reviewer pass -> verifier pass -> local closeout.
- Not done: no push, no PR, no merge, no deploy, and no publish/release. Those remain separate parent-thread gates after local commit and global skill sync.

## Current Diff Surface

Current truth is command-derived, not a copied package list. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

During this package, expected touched areas are `scripts/team_router_doctor.py`, `tests/test_team_router.py`, this workbench, package docs, the saved Superpowers plan, and `skills/codex-team-router/references/testing-and-quality-gates.md`. The exact list must be taken from fresh commands because the package is still active.

`scripts/team_router_truth_check.py` is the stale-claim gate for workbench/package current-state text. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must not claim live role dispatch unless explicit readiness evidence exists.

## Verification Record

Active package verification so far:

- Plan saved: `docs/superpowers/plans/2026-06-28-role-thread-readiness-status.md`.
- RED classifier: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_role_thread_readiness_states -v` failed because `classify_role_thread_status` did not exist.
- GREEN classifier: same command -> OK after adding read-only role-thread state classification.
- RED CLI: `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_role_thread_status_snapshot -v` failed because `--role-status-json` was unrecognized.
- GREEN CLI: focused classifier + CLI tests -> OK after adding `--role-status-json` and `roleThreadStatus`.
- RED docs gate: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_role_thread_status_snapshots -v` failed because quality gates did not document the role status snapshot contract.
- GREEN docs gate: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_role_thread_status_snapshots tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> OK.
- Focused state tests: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 41 tests OK.
- Focused docs tests: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 39 tests OK.
- Final compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-role-status'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> OK.
- Final full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-role-status'; py -B -m unittest tests.test_team_router` -> Ran 274 tests OK.
- Final whitespace check: `git diff --check` -> exit 0 with CRLF/LF warnings only.
- Post-sync truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `gitStatusShort: []`, `diffFiles: []`, `skillSync.status: match`, branch `master...origin/master [ahead 2]`.
- Post-sync doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: clean_synced`, `orchestrationStatus: manual_only`, `roleThreadStatus: {mode: read-only, roles: []}` by default.
- Post-sync skill sync check: `py -B scripts\team_router_skill_sync_check.py --check` -> `status: match`.
- Reviewer gate: reviewer thread `019f0ea7-0ad7-7931-9e2e-89c13401c14a` first returned `needs_rework` because this workbench and the package doc still described verification as pending; after current-state documentation rework, reviewer re-review returned `pass` with `requiredChanges: none`.
- Verifier gate: verifier thread `019f0eaa-ac70-7831-9b12-5d7f28686c72` first returned `needs_rework` on stale reviewer-gate wording; after docs rework and tests, verifier re-check returned `pass` with `requiredChanges: none`.
- Local commit: `73596fa Add role thread readiness status`.
- Global skill sync: `py -B scripts\\team_router_skill_sync_check.py --sync` -> `status: match`.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-trust-and-modularity` is a completed historical package covering the current-state truth checker, module split plan, and initial doctor/status UX. Its recorded diff surface, verifier evidence, and sync state are not current git truth.
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
- Role-thread readiness/status in this package is evidence-only UX; it does not modify dispatch, watcher cadence, registry, ledger, or protocol parsing.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- This package intentionally documents role-thread state from supplied snapshots only; live visibility still depends on the host thread tools and explicit manager observations.
- Reviewer re-review passed, verifier accepted/pass, local commit completed, and global skill sync completed for this package. Push, PR, merge, deploy, publish, and release remain separate gates.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: push/PR decision or stop; verifier accepted/pass, local commit complete, global skill sync complete.
- Next gated step: push/PR decision only if explicitly authorized; merge, deploy, publish, and release remain separate unauthorized gates.
