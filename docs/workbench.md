# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: no active repo-local package; `ctr-20260702-manager-polling-status-consumption` has completed local review and acceptance and is locally closed out by explicit Complex Task authorization.
- Completed package objective: make manager polling status visible end-to-end from caller-supplied doctor evidence into manager-facing handoff and closeout summaries.
- Completed package starting evidence: doctor exposed `managerPollingStatus`, but reusable fixture/runbook evidence and manager-facing status summary consumption were still missing.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current package boundary: none after local closeout; latest package is complete unless fresh commands show otherwise.
- Current next gate: none after local closeout. Any push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync requires a separate explicit authorization.
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

- `ctr-20260702-manager-polling-status-consumption`: RED fixture/runbook tests `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-red1 py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture -v` first failed because the fixture file was missing and the runbook did not yet document `managerPolling`.
- `ctr-20260702-manager-polling-status-consumption`: GREEN fixture/runbook tests with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-green1b` -> Ran 2 tests OK.
- `ctr-20260702-manager-polling-status-consumption`: RED formatter tests `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-red2b py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_handoff_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterManagerIntegration.test_closeout_includes_manager_polling_status_summary -v` first failed because handoff/closeout output did not include `managerPolling:`.
- `ctr-20260702-manager-polling-status-consumption`: GREEN formatter tests with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-green2` -> Ran 2 tests OK.
- `ctr-20260702-manager-polling-status-consumption`: final focused suite `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-focused py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture tests.test_team_router.TestTeamRouterManagerIntegration.test_handoff_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterManagerIntegration.test_closeout_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_manager_polling_status_decision_from_snapshot tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 6 tests OK.
- `ctr-20260702-manager-polling-status-consumption`: compile `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-complex-compile py -B -m py_compile src\team_router_status.py scripts\team_router_doctor.py tests\test_team_router.py` -> exit 0.
- `ctr-20260702-manager-polling-status-consumption`: `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for `docs/runbooks/codex-team-router-live-orchestration.md`, `docs/workbench.md`, and `tests/test_team_router.py` only.
- `ctr-20260702-manager-polling-status-consumption`: `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty local package surface includes `docs/runbooks/codex-team-router-live-orchestration.md`, `docs/workbench.md`, `src/team_router_status.py`, `tests/test_team_router.py`, the implementation plan, package doc, and fixture.
- `ctr-20260702-manager-polling-status-consumption`: `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `managerPollingStatus.status: not_supplied`; `summary` includes `managerPolling=not_supplied`.
- `ctr-20260702-manager-polling-status-consumption`: `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`; dirty local package surface remains uncommitted before the authorized Complex Task local commit.
- `ctr-20260702-manager-polling-status-consumption`: local review pass -> no blocking findings; confirmed the package only formats supplied manager polling status evidence and does not add live `read_thread`, broker, scheduler, dispatch, parser, or registry/ledger transition paths.
- `ctr-20260702-manager-polling-status-consumption`: local acceptance -> focused suite OK, compile exit 0, `git diff --check` exit 0 with CRLF/LF warnings only, `truth_check` staleClaims empty, `doctor` exposes default `managerPollingStatus.status: not_supplied`, and `closeout_check` exits 0.
- `ctr-20260702-manager-polling-doctor-ux`: RED focused test `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-red py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_manager_polling_status_decision_from_snapshot -v` first failed with `KeyError: 'managerPollingStatus'`.
- `ctr-20260702-manager-polling-doctor-ux`: GREEN focused test after implementation: same test with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-green` -> Ran 1 test OK.
- `ctr-20260702-manager-polling-doctor-ux`: focused doctor/polling suite with role status, host readiness, broker arg guard, plain status, and manager polling helper tests -> Ran 10 tests OK.
- `ctr-20260702-manager-polling-doctor-ux`: final focused suite with workbench current-state test -> Ran 11 tests OK.
- `ctr-20260702-manager-polling-doctor-ux`: compile `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-doctor-compile py -B -m py_compile scripts\team_router_doctor.py tests\test_team_router.py` -> exit 0.
- `ctr-20260702-manager-polling-doctor-ux`: `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for `docs/workbench.md` and `tests/test_team_router.py` only.
- `ctr-20260702-manager-polling-doctor-ux`: `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty local package surface includes `docs/workbench.md`, `scripts/team_router_doctor.py`, `tests/test_team_router.py`, and untracked package doc.
- `ctr-20260702-manager-polling-doctor-ux`: `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `managerPollingStatus.status: not_supplied`; `summary` includes `managerPolling=not_supplied`; `nextAction` says reviewer then verifier before closeout.
- `ctr-20260702-manager-polling-doctor-ux`: `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`; dirty local package surface remains uncommitted.
- `ctr-20260702-manager-polling-doctor-ux`: local reviewer pass -> no blocking findings; confirmed doctor consumes caller-supplied snapshot evidence and does not add live `read_thread`, broker, scheduler, or dispatch paths.
- `ctr-20260702-manager-polling-doctor-ux`: local verifier acceptance -> fresh 11-test focused suite OK, compile exit 0, `git diff --check` exit 0 with CRLF/LF warnings only, `truth_check` staleClaims empty, `doctor` exposes `managerPollingStatus.status: not_supplied`, and `closeout_check` exits 0.
- `ctr-20260702-live-role-polling-ux-enforcement`: RED focused tests `py -B -m unittest tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_early_read_and_repeated_active_report tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_suppresses_unchanged_active_status_after_allowed_read tests.test_team_router.TestTeamRouterState.test_manager_polling_status_update_reports_status_changes_only -v` first failed with `AttributeError: module 'team_router' has no attribute 'manager_polling_status_update'`.
- `ctr-20260702-live-role-polling-ux-enforcement`: GREEN focused tests after implementation: same command -> Ran 3 tests OK. Focused regression suite with existing read/convergence checks and workbench test -> Ran 7 tests OK. Compile with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-polling-ux py -B -m py_compile src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py` -> exit 0. `git diff --check` -> exit 0 with CRLF/LF warnings only. `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`. `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.


- RED focused contract test first failed with `KeyError: 'manualPollBackoffSeconds'` before adding the new policy fields.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_defends_active_role_wait_and_polling_backoff tests.test_team_router.TestTeamRouterSkillDoc.test_manager_docs_cover_active_role_wait_and_polling_backoff -v` -> Ran 2 tests OK.
- Skill documentation suite after entrypoint compression and workbench current-truth test update: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -q` -> Ran 51 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- Focused regression suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_defends_active_role_wait_and_polling_backoff tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_includes_active_role_return_model tests.test_team_router.TestTeamRouterSkillDoc.test_manager_docs_cover_active_role_wait_and_polling_backoff tests.test_team_router.TestTeamRouterSkillDoc.test_manager_orchestration_policy_docs_cover_polling_reuse_and_verifier_return tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 5 tests OK.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.
- Truth check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skill.entrypointBytes: 7160`; `skill.underTarget: true`; `skillSync.status: mismatch` because repo skill changes are not globally synced in this package.
- Doctor check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout; unauthorized includes commit, push, PR, merge, deploy, global skill sync.
- Closeout check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B scripts\team_router_closeout_check.py --json` -> exit 0; reports the same expected dirty package surface and `skillSync.status: mismatch`.
- Reviewer v1: thread `019f1e8a-2a08-7971-921d-96d967da59a2` -> `needs_rework`; required change was to align package/workbench next-gate wording with the already-completed local verification record and doctor output.
- Rework after reviewer v1: updated package/workbench next-gate wording and the workbench current-truth test anchor; reran focused 2-test suite OK; git diff --check exit 0 with CRLF/LF warnings only; truth_check/doctor/closeout_check exit 0 with staleClaims empty, truthStatus dirty, orchestrationStatus manual_only, and expected skillSync mismatch.
- Reviewer v2: thread `019f1e8a-2a08-7971-921d-96d967da59a2` -> `pass`; requiredChanges: none; confirmed current-gate rework is aligned and no dense polling or premature restart ambiguity was reintroduced.
- Verifier v1: thread `019f1e93-a360-7220-af9e-a801336e13dd` -> `rejected`; required change was to align package/workbench current-gate wording with reviewer v2 already passed, making verifier final acceptance the current gate and leaving local commit separate unless accepted and explicitly authorized.
- Verifier v2: thread `019f1e93-a360-7220-af9e-a801336e13dd` -> `accepted`; requiredChanges: none; acceptedForCommit: true; local commit still requires explicit user authorization and push/PR/merge/global sync remain outside.

Previous package verification:
- Previous `ctr-20260701-automatic-runtime-wiring`: added the read-only runtime wiring dry-run, passed reviewer v2 and verifier, was committed as `5931dda`, pushed, and merged through PR #8 at `a99b767`.
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
- Current manager-polling status consumption package may change doctor evidence fixture/runbook text, manager-facing summary formatting, tests, package/workbench records, and verification notes only; it must not modify parser marker schema, registry/ledger state transitions, direct-return receipt validation, production broker startup, live role dispatch, thread-tool calls, or host adapter implementation.
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
- Active role status can be misread as stuck if the manager narrates every unchanged poll or suggests duplicate role restart too early; the current package exposes and formats quiet polling status from supplied evidence without live reads.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: none after local closeout for `ctr-20260702-manager-polling-status-consumption`.
- No push, PR, remote merge, deploy, publish/release, production scheduler/broker daemon, live role dispatch, thread-tool calls, or global skill sync is included unless explicitly authorized later.
