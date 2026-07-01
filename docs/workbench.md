# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: no active repo-local package after verifier acceptance and local commit for `ctr-20260701-automatic-runtime-wiring`; local branch is ahead of `origin/master` until a separate push/PR gate is authorized.
- Current package objective: automatic Team Router runtime wiring dry-run. The target is to make the manager automatic-entry path explicit and allow it only when an already-running localhost broker supplies ready host-readiness evidence.
- Starting evidence before opening this package: previous `ctr-20260701-broker-host-readiness-injection` was merged through PR #7 at `2dc7be4`; post-merge `truth_check`, `doctor`, and `closeout_check` reported clean/synced with `skillSyncStatus: match` and no diff.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current package boundary: add a read-only dry-run runtime wiring report that consumes broker `/readiness`, classifies host readiness, and reports whether `host_context` may be injected into `orchestrate_team_task_with_adapter()`. No thread-tool endpoints are called during dry-run.
- Current next gate: none for local closeout. push, PR, merge, deploy, publish/release, production scheduler/broker daemon, live role dispatch, and global skill sync remain outside this package unless explicitly authorized later.
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

Current package verification:

- Added `scripts/team_router_runtime_wiring_check.py` as a read-only dry-run automatic runtime wiring gate.
- The dry-run consumes broker `/readiness`, classifies the doctor host-readiness snapshot, and reports `automaticEntryAllowed` only when host readiness is ready and `broker_host_context_kwargs()` can build manager startup kwargs.
- The dry-run does not call `/thread-tools/create_thread`, `/thread-tools/send_message_to_thread`, `/thread-tools/read_thread`, or `/thread-tools/set_thread_title`; tests assert thread-tool calls remain empty.
- RED focused tests first failed because `scripts/team_router_runtime_wiring_check.py` did not exist.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterRuntimeWiringScript -v` -> Ran 3 tests OK.
- Compile: `py -B -m py_compile src\team_router.py src\team_router_broker_adapter.py scripts\team_router_runtime_wiring_check.py scripts\team_router_broker_feasibility_check.py scripts\team_router_doctor.py tests\test_team_router.py` -> exit 0.
- Focused broker/runtime group: `py -B -m unittest tests.test_team_router.TestTeamRouterRuntimeWiringScript tests.test_team_router.TestTeamRouterBrokerFeasibilityScript tests.test_team_router.TestTeamRouterBrokerAdapter -v` -> Ran 33 tests OK.
- Full Team Router test module: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 397 tests OK after updating the workbench current-state guard for this active package.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty surface is this package only.
- Doctor check: `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; next action is reviewer then verifier before closeout.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`; dirty surface is this package only.
- `git diff --check` initially reported CRLF/LF warnings plus `tests/test_team_router.py:13705: new blank line at EOF`; EOF cleanup is part of this package before final re-run.
- Reviewer v1 returned `needs_rework` for stale next-gate wording after verification had completed; rework updated workbench/package next gate to `reviewer re-check, verifier acceptance, then local commit only`.
- Reviewer v2: pass; `requiredChanges: none`; confirmed dry-run remains non-mutating and current-truth next gate is no longer stale.
- Verifier: accepted; `requiredChanges: []`; confirmed dry-run only reads `/readiness`, no thread-tool endpoints are called, reviewer stale next-gate finding is fixed, and local commit may proceed.

Previous package verification:

- Previous `ctr-20260701-broker-host-readiness-injection`: implemented `broker_host_readiness_snapshot()`, broker-injected doctor readiness, feasibility `hostReadinessSnapshot`, reviewer v2 pass, verifier accepted, and full suite `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 394 tests OK.
- RED focused test: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_thread_package_bootstrap_is_pointer_only -v` first failed with `AttributeError: module 'team_router' has no attribute 'make_role_thread_package_bootstrap_message'`.
- GREEN focused test after implementation: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_thread_package_bootstrap_is_pointer_only -v` -> OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- Related prompt/workbench checks: focused package-bootstrap test, role request language/path-handoff tests, workbench current-state test, and module-map boundary test -> OK after correcting the module-map test invocation name.
- Rework after live dispatch: user observed the reviewer/verifier initial prompt still included a long scope/checklist/output schema. The package now requires the helper output itself to be the directly sendable short bootstrap and tests that it omits `Scope:`, `Please check`, `Return only`, `evidenceChecked:`, `findings:`, and `requiredChanges:`.
- Reviewer rework: short bootstrap fields now reject multiline protocol/schema injection, `reviewerResult` is limited to short enum values, and `reviewPackagePath` uses workspace path validation. Full suite after this rework: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 354 tests OK.
- Full suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 354 tests OK.
- Truth check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; commit/push/globalSync authorization false.
- Doctor check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `nextAction` says reviewer pass then verifier pass before closeout; unauthorized includes commit, push, PR, merge, deploy, global skill sync.
- `git diff --check` -> exit 0 with CRLF/LF warning for `docs/workbench.md` only.
- Reviewer v3: thread `019f1c7b-e299-7822-bf8a-fbcba74e6049` -> pass; `requiredChanges: none` after short-field/path validation rework.
- Verifier: thread `019f1c7d-d43c-70b1-a681-adb6fb4a6ea4` -> pass; `requiredChanges: []`.
- Local closeout: explicitly authorized in-thread; commit is the only included side effect. push/PR/merge/deploy/publish/global sync remain outside this package.

- `ctr-20260701-role-thread-handoff-compression`: reviewer/verifier request prompts became path-first and package-oriented; package passed reviewer v2 and verifier, was committed as `27447ee`, and was merged locally to `master` as `4634d23`; no push, PR, deploy, publish/release, or global skill sync was included.
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
- Current automatic runtime wiring package may change read-only broker runtime wiring checks, docs, and tests only; it must not modify dispatch, watcher cadence, registry, ledger, protocol parsing, direct-return behavior, production broker startup, live role dispatch, or production scheduling.
- Package-only role bootstrap and path-first prompt compression are evidence handoff UX only; they do not modify dispatch, watcher cadence, registry, ledger, protocol parsing, host integration, direct-return behavior, or production scheduling.

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
- Real host integration may still be external. This active package must prove whether Desktop/plugin callables exist before any runtime readiness claim.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: none after verifier acceptance and local commit for this package.
- No push, PR, remote merge, deploy, publish/release, production scheduler/broker daemon, live role dispatch, or global skill sync is included unless explicitly authorized later.
