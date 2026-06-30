# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: active repo-local package `ctr-20260701-latest-executor-callback-state-extraction`; local implementation, verification, reviewer v2, and verifier passed; closeout authorization remains pending.
- Current package objective: continue the conservative registry/ledger state extraction by moving only `_latest_executor_callback_observation()` into `src/team_router_state.py`.
- Starting evidence before opening this package: `git status -sb --untracked-files=all` reported `## master...origin/master`; previous package `ctr-20260630-ledger-transition-state-extraction` was committed and pushed before this new package opened.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: only the pure in-memory executor callback observation lookup may move from `src/team_router.py` to `src/team_router_state.py`; no parser/gate/direct-return/watcher/host/prompt behavior, live adapter, production scheduler/daemon, PR, merge, deploy, publish/release, commit, push, or global skill sync is authorized for this package yet.
- Current next gate: closeout authorization; commit/push/global skill sync require separate authorization after verifier pass, and no closeout side effect is authorized yet.
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

Latest package verification:

- Package opening: update this workbench, create `docs/team-router/packages/ctr-20260701-latest-executor-callback-state-extraction.md`, and keep module-map/current-state tests aligned with the new active package.
- Starting evidence before opening this package: `git status -sb --untracked-files=all` reported `## master...origin/master`.
- Implementation: moved `_latest_executor_callback_observation()` from `src/team_router.py` to `src/team_router_state.py`; facade compatibility remains through import/re-export.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m py_compile src\team_router.py src\team_router_state.py tests\test_team_router.py` -> exit 0. Direct `py_compile` without isolated cache hit `[WinError 5]` writing old `src\__pycache__`, so verification uses the existing Windows temp-cache workaround.
- Focused tests: facade re-export, latest executor callback observation behavior, workbench current-state contract, and module-map contract -> Ran 4 tests OK.
- Full suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 351 tests OK.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; authorization reports commit/push/globalSync false; current truth is dirty only because this package diff is present.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; nextAction is reviewer pass then verifier pass before closeout; unauthorized includes commit, push, PR, merge, deploy, global skill sync.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_closeout_check.py --json` -> exit 0; commit/push/globalSync false; skill-sync output is evidence-only and must be freshly checked by each reviewer/verifier worktree.
- `git diff --check` -> exit 0 with CRLF/LF warnings only.
- Reviewer v2 status: pass; `TEAM_ROUTER_REVIEW` thread `019f1959-2aea-71a1-986d-56ee156f9804` reported `requiredChanges: none`.
- Verifier status: pass; `TEAM_ROUTER_VERDICT` thread `019f195c-f32d-7582-95d6-ad532339053a` reported `requiredChanges: none`.
- Closeout status: pending explicit authorization; no commit, push, PR, merge, deploy, publish/release, or global skill sync is authorized for this new package yet.

Previous package verification:

- Previous `ctr-20260630-ledger-transition-state-extraction` passed reviewer v3 and verifier, then was explicitly authorized and committed as `35a3a7f`; it was pushed to `origin/master`, and authorized global skill sync reported `match`. It moved `_has_observation_content()` into `src/team_router_state.py` and is historical baseline only.
- Previous `ctr-20260630-registry-ledger-state-extraction` passed reviewer and verifier, then was explicitly authorized and committed as `9b7ac98`; it was pushed to `origin/master`. It moved `_search_anchor()`, `_role_review_request_record()`, and pure latest-request accessors into `src/team_router_state.py` and is historical baseline only.
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

- Current gate: closeout authorization for `ctr-20260701-latest-executor-callback-state-extraction`; reviewer v2 and verifier passed.
- No commit, push, PR, merge, deploy, publish/release, live adapter, production scheduler/daemon, or global skill sync is authorized for this new package yet.
