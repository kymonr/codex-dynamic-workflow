# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: no active repo-local package after verifier acceptance for `ctr-20260701-broker-host-readiness-injection` on branch `codex/desktop-plugin-feasibility-spike`; local commit is the closeout side effect.
- Current package objective: broker/adapter startup readiness plus host-readiness injection. The target is to let an already-running localhost broker feed doctor/readiness evidence and host context injection without starting a production daemon.
- Starting evidence before opening this package: previous `ctr-20260701-desktop-plugin-feasibility-spike` live smoke was locally closed out as commit `aa7c618`; `create_thread`, `read_thread`, `send_message_to_thread`, and `set_thread_title` are smoke-proven only at the Codex app tool layer, while runtime readiness still needs a Python callable adapter wrapper, `parent_thread_id`, and heartbeat scheduler evidence.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Completed package boundary: localhost broker readiness mapping, doctor host-readiness injection, focused tests, package/workbench/plan records, and local closeout commit. No live role dispatch, production daemon, push, PR, merge, deploy, publish/release, or global skill sync was included.
- Current next gate: none after this local closeout commit; push, PR, merge, deploy, publish/release, production scheduler/broker daemon, live role dispatch, and global skill sync remain outside this package unless explicitly authorized later.
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

- Implemented `broker_host_readiness_snapshot()` in `src/team_router_broker_adapter.py` to map already-running localhost broker `/readiness` evidence into doctor host-readiness snapshot fields.
- `scripts/team_router_broker_feasibility_check.py --json` now includes `hostReadinessSnapshot`.
- `scripts/team_router_doctor.py` now accepts `--broker-url` plus `--session-token` for read-only broker readiness injection; explicit `--host-readiness-json` remains mutually exclusive with broker args.
- Focused new tests ran OK: 5 tests covering ready/blocked broker snapshot mapping, feasibility output, doctor broker injection, and conflict rejection.
- Existing broker/feasibility group ran OK: 29 tests.
- Existing doctor host-readiness group ran OK: 6 tests.
- Full Team Router test module before reviewer rework ran OK: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 393 tests OK.
- Reviewer v1 found a P1 overclaim path: blocked broker top-level readiness with otherwise-ready tools/runtime could map to doctor `adapter_smoke_ready`.
- Rework blocks runtimeProbe in `broker_host_readiness_snapshot()` unless top-level broker readiness is ready and broker missing is empty; added regression for `host_contract_blocked`.
- Rework focused tests ran OK: 6 tests.
- Broker/feasibility group after rework ran OK: 30 tests.
- Full Team Router test module after rework ran OK: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 394 tests OK.
- Reviewer v2: pass; `requiredChanges: none`; confirmed blocked broker readiness cannot classify as `adapter_smoke_ready`.
- Verifier: accepted; `requiredChanges: none`; next was local commit only, with no push/PR/merge/deploy/publish/global sync.

Previous package verification:

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
- Current broker host-readiness injection package may change broker adapter/status wiring and tests only; it must not modify dispatch, watcher cadence, registry, ledger, protocol parsing, direct-return behavior, production broker startup, or production scheduling.
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

- Current gate: none after verifier acceptance and local closeout commit for `ctr-20260701-broker-host-readiness-injection`.
- No push, PR, remote merge, deploy, publish/release, production scheduler/broker daemon, or global skill sync is included unless explicitly authorized later.
