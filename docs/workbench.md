# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: active repo-local package `ctr-20260701-role-thread-handoff-compression` on branch `codex/role-thread-handoff-compression`; local implementation, reviewer v2 gate, and verifier gate passed; local closeout is pending explicit authorization.
- Current package objective: make reviewer and verifier request prompts path-first and package-oriented so role threads receive `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` pointers instead of inline callback/review evidence bodies.
- Starting evidence before opening this package: Latest completed package `ctr-20260701-latest-executor-callback-state-extraction` was committed as `8189ce1`, pushed to `origin/master`, and repo/global skill sync reported `match`; this package then opened on branch `codex/role-thread-handoff-compression`.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Active package boundary: prompt-construction only in `src/team_router.py`, tests, and package/workbench/module-map docs; no parser/gate/direct-return/watcher/host/thread-adapter/live adapter/production scheduler behavior is included.
- Current next gate: local closeout decision; gate sequence reviewer pass, then verifier pass is complete. Commit, push, PR, merge, deploy, publish/release, and global skill sync are outside this package unless explicitly authorized later.
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

- Package opening: created Superpowers plan `docs/superpowers/plans/2026-07-01-role-thread-handoff-compression.md` and branch `codex/role-thread-handoff-compression`.
- Baseline suite before code edits: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 351 tests OK.
- RED tests: focused reviewer/verifier path-first prompt tests failed before implementation because compact prompts still copied callback evidence or exceeded the package handoff length cap.
- GREEN focused tests: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback -v` -> Ran 2 tests OK.
- Related prompt contract regression: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise tests.test_team_router.TestTeamRouterProtocol.test_manager_reviewer_verifier_prompts_codify_path_handoff_contract -v` -> Ran 4 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- Full suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 353 tests OK.
- Truth check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; authorization reports commit/push/globalSync false; dirty surface is this active package.
- Doctor check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `nextAction` says reviewer pass then verifier pass before closeout; unauthorized includes commit, push, PR, merge, deploy, global skill sync.
- Closeout check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_closeout_check.py --json` -> exit 0; commit/push/globalSync false. Skill-sync output is evidence-only: main worktree reported `status: match`, while reviewer worktree reported `status: mismatch` for `references/testing-and-quality-gates.md`; verifier must use fresh local output and this package does not authorize global sync.
- `git diff --check` -> exit 0 with CRLF/LF warnings only.
- Reviewer status: pass in v2 thread `019f1984-0ec5-7f41-84d4-64104e03ef36`; original reviewer thread `019f1980-44fb-7300-86d9-485025e89645` found documentation freshness rework, and v2 confirmed `requiredChanges: none`.
- Verifier status: pass in thread `019f1988-013c-7f43-8bc3-13a1c6b77988`; `findings: none`, `requiredChanges: none`. Fresh verifier worktree `skillSync.status` was `mismatch` for `references/testing-and-quality-gates.md`; this is evidence-only, outside scoped diff, and does not authorize global sync.

Previous package verification:

- Implementation: moved `_latest_executor_callback_observation()` into `src/team_router_state.py` in previous `ctr-20260701-latest-executor-callback-state-extraction`; it passed reviewer v2 and verifier, then was explicitly authorized and committed as `8189ce1`; it was pushed to `origin/master`, and repo/global skill sync reported `match`. It moved `_latest_executor_callback_observation()` into `src/team_router_state.py` as a pure in-memory executor callback observation lookup and is historical baseline only.
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
- Path-first prompt compression in this package is evidence handoff UX only; it does not modify dispatch, watcher cadence, registry, ledger, protocol parsing, host integration, direct-return behavior, or production scheduling.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- Prompt compression can accidentally hide evidence from reviewer/verifier if path metadata is missing; non-package/no-path inline fallback must remain covered by tests.
- Public imports must continue through `src/team_router.py` unless a later explicit compatibility gate broadens the import contract.
- Real host integration is still external: no live host adapter implementation, no production scheduler/daemon, and no callable host readiness snapshot is supplied by this repo package.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: reviewer v2 and verifier passed for `ctr-20260701-role-thread-handoff-compression`; await explicit closeout authorization before commit, push, or global skill sync.
- No commit, push, PR, merge, deploy, publish/release, live adapter, production scheduler/daemon, or global skill sync is included in the current authorization.