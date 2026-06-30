# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: repo-local package `ctr-20260630-role-thread-prompt-path-contract` is in progress; starts from committed dispatch-prompt path-handoff package `ffcebd7`.
- Active package objective: codify role-thread prompt path handoff across Manager, Reviewer, and Verifier prompt surfaces so bootstrap and plan/request prompts state `roleCommunicationMode: concise-protocol-plus-paths`, path evidence boundaries, and the `taskBriefPath` / `executorReportPath` / `reviewPackagePath` fields.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live host adapter implementation, no production scheduler/daemon, no push, no PR, no merge, no deploy, no publish/release, and no global skill sync in this package. This package edits the repo-local Team Router skill entrypoint/reference docs only; global skill sync remains a separate gate.
- Current next gate: send `ctr-20260630-role-thread-prompt-path-contract` to reviewer gate, then verifier gate before any local closeout commit.

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

Active package verification so far:

- Implementation: `src/team_router.py` adds `ROLE_THREAD_PATH_HANDOFF_PROMPT_LINES` and includes it in role-thread bootstrap prompts plus `make_plan_request_message()`.
- Test coverage: `tests/test_team_router.py` adds `test_manager_reviewer_verifier_prompts_codify_path_handoff_contract`, covering Manager/Reviewer/Verifier bootstrap prompts and Manager plan request path handoff wording.
- RED test: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_manager_reviewer_verifier_prompts_codify_path_handoff_contract -v` -> failed before implementation because role bootstrap prompts and Manager plan request lacked `roleCommunicationMode: concise-protocol-plus-paths`.
- GREEN focused test: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_manager_reviewer_verifier_prompts_codify_path_handoff_contract -v` -> Ran 1 test OK.
- Related prompt/doc checks -> Ran 7 tests OK.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 348 tests OK.
- Truth check -> `staleClaims: []`, `skill.entrypointBytes: 7145`, `skill.underTarget: true`, `skillSync.status: mismatch` because this package changes repo-local skill/reference docs and global sync is not authorized.
- Doctor check -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, next action is reviewer then verifier before closeout.
- Closeout check -> `skill.entrypointBytes: 7145`, `underTarget: true`, `skillSync.status: mismatch`.
- Whitespace check: `git diff --check` -> exit 0 with CRLF/LF replacement warnings only.
- Boundary: no parser, gate, direct-return, watcher, host adapter, production scheduler/daemon, push, PR, merge, deploy, publish/release, or global skill sync change in this package.
Previous package verification:

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

- Role-thread prompt path handoff is prompt contract text only; it must not change parser, gate, direct-return, watcher, host readiness, or role-thread snapshot semantics.
- Real host integration is still external: no live host adapter implementation, no production scheduler/daemon, and no callable host readiness snapshot is supplied by this repo package.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: local verification is complete for `ctr-20260630-role-thread-prompt-path-contract`; send this package to reviewer gate, then verifier gate.
- No commit, push, PR, merge, deploy, publish/release, or global skill sync has been authorized for this active package.
