# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: repo-local package `ctr-20260630-registry-ledger-state-extraction` is open. It starts after `0596316` was pushed to `origin/master` and the authorized global skill sync reported `match`; fresh command output overrides this note.
- Active package objective: define and execute the next conservative registry/ledger state extraction step, starting from the current split where `src/team_router_state.py` owns JSON primitives and role binding persistence while `src/team_router.py` still owns higher-level ledger mutation and orchestration transitions.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live host adapter implementation, no production scheduler/daemon, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync in this package unless separately authorized. Implementation moved only pure registry/ledger state helpers into `src/team_router_state.py`; remaining work before closeout is verification, reviewer gate, verifier gate, then local commit if authorized by this package flow.
- Current next gate: finish verification for `ctr-20260630-registry-ledger-state-extraction`, then run reviewer and verifier gates before local closeout commit.

## Current Diff Surface
Current truth is command-derived. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

This file intentionally does not list a live diff surface. The current package files and exact surface must be taken from fresh commands before any new claim.

`scripts/team_router_truth_check.py` is the stale-current-state gate for workbench/package text. It should focus on Current Task / Current Diff Surface style sections so historical package archives are not treated as live truth. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must remain read-only/evidence-only.

## Verification Record

Active package verification so far:

- Package opening: update this workbench and create `docs/team-router/packages/ctr-20260630-registry-ledger-state-extraction.md`.
- Starting evidence before opening this package: `0596316` was pushed to `origin/master`; authorized global skill sync reported `skillSync.status: match`; truth check reported `staleClaims: []`; doctor reported `truthStatus: clean_synced`.
- Implementation: moved `_search_anchor()`, `_role_review_request_record()`, `_latest_executor_dispatch()`, `_latest_reviewer_request()`, `_return_thread_id_from_record()`, `_inherited_reviewer_return_thread_id()`, and `_inherited_verifier_return_thread_id()` from `src/team_router.py` to `src/team_router_state.py`; facade compatibility remains through imports.
- Focused verification passed: `py -B -m py_compile src\team_router.py src\team_router_state.py tests\test_team_router.py`, `test_facade_reexports_extracted_state_symbols`, dispatch search-anchor/fallback tests, and architect/QA direct-return request metadata tests.
- Reviewer v2 found duplicate unittest method name; fixed by restoring unique `test_manager_reviewer_verifier_prompts_codify_path_handoff_contract` and adding `test_test_case_names_are_unique` guard.
- Focused recheck after fix: `test_facade_reexports_extracted_state_symbols`, `test_manager_reviewer_verifier_prompts_codify_path_handoff_contract`, and `test_test_case_names_are_unique` -> Ran 3 tests OK.
- Full suite after fix: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 349 tests OK.
- Reviewer gate: v2 thread `019f190d-4ff5-79f0-bda6-00c7ea1d0e49` first returned `needs_rework` for duplicate unittest method name; after the fix it returned `pass` with `requiredChanges: none`.
- Verifier gate: thread `019f1914-ec15-7fa2-9357-10946ccf52cf` first returned `needs_rework` for literal `\\n-` doc artifacts; after the docs fix it returned `pass` with `requiredChanges: none`.\n- Remaining planned checks: final truth/doctor/closeout refresh and local commit.
- Boundary: no parser, gate, direct-return, watcher, host adapter, production scheduler/daemon, push, PR, merge, deploy, publish/release, or global skill sync change in this package unless separately authorized.
Previous package verification:

- Previous `ctr-20260630-role-thread-prompt-path-contract` passed reviewer and verifier, then was explicitly authorized and committed as `0596316`; it was pushed to `origin/master`, and its authorized global skill sync reported `match`. Its role-thread prompt path handoff is historical baseline only.
- Previous `ctr-20260630-dispatch-prompt-path-handoff` passed reviewer and verifier, then was explicitly authorized and committed as `ffcebd7`; its executor dispatch prompt path handoff is historical baseline only.
- Previous `ctr-20260630-status-tools-extraction` passed reviewer and verifier, then was explicitly authorized and committed as `4dd5a95`; its read-only status tool extraction is historical baseline only.
- Previous `ctr-20260630-status-closeout-extraction` passed reviewer and verifier, then was explicitly authorized and committed as `d66b77d`; its closeout/status helper extraction is now historical baseline only.
- Previous `ctr-20260630-watcher-status-extraction` was explicitly authorized and committed as `dcff722`; its watcher runtime extraction is historical baseline only.

## Historical Records
Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-role-thread-readiness-status` completed read-only role-thread status UX in `scripts/team_router_doctor.py`; it added `--role-status-json` and `roleThreadStatus` from supplied snapshots only.
- Previous `ctr-20260628-live-capability-state-fix` clarified exposed app tools versus missing Python callable adapter/runtime orchestration. That remains the baseline boundary for this package.
- Previous `ctr-20260628-trust-and-modularity` is a completed historical package covering the current-state truth checker, module split plan, and initial doctor/status UX. Its recorded diff surface, verifier evidence, and sync state are not current git truth.
- Previous `ctr-20260628-team-router-optimization-1-6` is a completed historical package. Its recorded dirty surface, skill sync result, reviewer evidence, and P2 step labels are not current git truth.
- Previous `ctr-20260628-team-router-optimization-local-package` records are historical baseline only; they are not the current active package.
- Previous `ctr-20260628-anchor-and-closeout-freshness-fix` records: verifier accepted/pass; prior local closeout/commit language is historical and no longer the Current Task.
- Previous `ctr-20260628-role-request-direct-send-and-waiting-fix` records are accepted/pass at reviewer and verifier gates.
- Previous `ctr-20260628-workbench-tool-error-governance` records described a no-tools governance state. That wording is historical and must not be copied into the current state now that the Codex app thread tool surface is exposed.
- Older ahead/behind, stale current diff surface, isolated-worktree status, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, the truth/doctor scripts, and latest role-thread marker evidence.

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library.
- Runtime/docs/tests changes require an active package plus reviewer/verifier gates.
- Workbench current state must not claim old completed tasks as active work.
- Stale-current-state detection and doctor nextAction in this package are evidence-only UX; they do not modify dispatch, watcher cadence, registry, ledger, protocol parsing, host integration, or production scheduling.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- Registry/ledger extraction can accidentally change on-disk state compatibility, task status transitions, role binding semantics, or direct-return recovery behavior if helpers are moved with hidden orchestration side effects.
- Public imports must continue through `src/team_router.py` unless a later explicit compatibility gate broadens the import contract.
- Real host integration is still external: no live host adapter implementation, no production scheduler/daemon, and no callable host readiness snapshot is supplied by this repo package.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: reviewer and verifier passed for `ctr-20260630-registry-ledger-state-extraction`; local closeout commit is next.
- No commit, push, PR, merge, deploy, publish/release, or global skill sync has been authorized for this active package.
