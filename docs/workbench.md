# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: repo-local package `ctr-20260630-dispatch-prompt-path-handoff` is locally committed; starts from committed status-tools package `4dd5a95`.
- Completed package objective: executor dispatch prompts use stable `taskBriefPath` / `reviewPackagePath` handoff instead of copying long `executorPrompt` text across role conversations.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live host adapter implementation, no production scheduler/daemon, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync in this package. Repo/global skill comparison remains `status: match` unless this package explicitly edits skill files.
- Current next gate: none inside repo-local dispatch-prompt path-handoff package; Real live host integration remains an external host package gate.

## Current Diff Surface

Current truth is command-derived. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

This file intentionally does not list a live diff surface. The dispatch-prompt path-handoff package files are recorded in the review package, and the exact current surface must be taken from fresh commands before any new claim.

`scripts/team_router_truth_check.py` is the stale-current-state gate for workbench/package text. It should focus on Current Task / Current Diff Surface style sections so historical package archives are not treated as live truth. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must remain read-only/evidence-only.

## Verification Record

Completed package verification:

- Implementation: `src/team_router.py` now omits overlong executor dispatch objective text only when readable `taskBriefPath` or `reviewPackagePath` handoff metadata is present, replacing it with `executorPrompt: <omitted; see taskBriefPath/reviewPackagePath>` while preserving short inline prompts, no-path fallback, `inlineFallback: true`, and executorReportPath-only handoff behavior.
- Test coverage: `tests/test_team_router.py` adds `test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists`, proving dispatch prompts include stable package paths and do not include the long `executorPrompt` payload; reviewer-required `test_executor_dispatch_keeps_long_prompt_inline_without_task_or_review_path` proves inlineFallback-only, no-path, and executorReportPath-only cases remain inline.
- RED test: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists -v` -> failed before implementation because the full long prompt was copied under `目标：`.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists -v` -> Ran 1 test OK; related prompt template tests -> Ran 3 tests OK. Reviewer rework RED caught inlineFallback-only and executorReportPath-only omission; rework GREEN `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_keeps_long_prompt_inline_without_task_or_review_path tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists -v` -> Ran 2 tests OK.
- Boundary: no parser, gate, direct-return, watcher, host adapter, production scheduler/daemon, push, PR, merge, deploy, publish/release, or global skill sync change in this package.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py` -> Ran 347 tests OK after reviewer-required rework. Truth check -> `staleClaims: []`, `skillSync.status: match`; doctor -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`; closeout_check -> `skillSync.status: match`, `underTarget: true`; `git diff --check` -> exit 0 with CRLF/LF warnings only. Reviewer re-review returned `pass` by direct-send with `requiredChanges: none`; verifier returned `pass` by direct-send with `requiredChanges: none`.
Previous package verification:

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

- Dispatch prompt path handoff is prompt transport only; it must not change parser, gate, direct-return, watcher, host readiness, or role-thread snapshot semantics.
- Real host integration is still external: no live host adapter implementation, no production scheduler/daemon, and no callable host readiness snapshot is supplied by this repo package.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: repo-local dispatch-prompt path-handoff package is locally committed; no repo-local role-thread gate remains.
- Next external gated step after local commit: real live host integration remains blocked until an external host supplies callable adapter/scheduler evidence.