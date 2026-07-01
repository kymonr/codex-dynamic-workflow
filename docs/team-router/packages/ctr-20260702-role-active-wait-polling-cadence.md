# ctr-20260702-role-active-wait-polling-cadence

## Package Metadata

- taskId: `ctr-20260702-role-active-wait-polling-cadence`
- branch: `master`
- permission: local package for Team Router role active-wait and read_thread polling cadence hardening. Includes contract snapshot, skill/docs, focused tests, package/workbench updates, and local verification. Excludes push, PR, merge, deploy, publish/release, production scheduler/broker daemon, live role dispatch, thread-tool calls, global skill sync, and commit unless separately authorized.
- scope: codify that active role threads are still processing and must not be interrupted/restarted/replaced, plus make manual/read_thread polling quieter and backoff-based.

## Objective

Turn the observed live-role UX issue into a durable Team Router rule: `active` / `inProgress` / `running` / `working` means the role is processing information, not stuck. The manager should wait, respect `firstCheckAt` / `nextAllowedReadAt`, and avoid high-frequency `read_thread` polling or repeated unchanged status narration.

## Boundary

Included:

- Add contract snapshot fields for active-role meaning, no-interruption boundary, manual polling backoff, one-time timeout notice, and schedule respect.
- Update the short `codex-team-router` skill entrypoint and polling/runbook docs.
- Add focused tests proving the contract and docs cover active-role waiting and polling backoff.
- Update workbench/package current truth and run local verification.

Excluded:

- No live role dispatch or Codex thread-tool calls.
- No broker/adapter/scheduler daemon startup.
- No changes to parser marker schema, registry/ledger state transitions, direct-return receipt validation, production scheduling, or host adapter implementation.
- No push, PR, merge, deploy, publish/release, global skill sync, or commit unless separately authorized.

## Acceptance Criteria

- `protocol_contract_snapshot()["managerOrchestrationPolicy"]` exposes `manualPollBackoffSeconds: (10, 20, 40)`.
- The contract says active/inProgress/running/working means normal processing, not failure/stuck.
- The contract forbids restart/replacement/shorter delta prompt while the role remains active.
- The contract says to respect `firstCheckAt` / `nextAllowedReadAt` and avoid manual reads before `nextAllowedReadAt` except user-triggered status/stop/immediate, timeout, or blocker handling.
- Skill/docs say to report only first active observation, status changes, timeout/blocker, or completion, and to emit only one timeout notice before intervention.
- Focused tests pass.

## Verification Record

- RED focused contract test first failed with `KeyError: 'manualPollBackoffSeconds'` before adding the new policy fields.
- GREEN focused tests: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_defends_active_role_wait_and_polling_backoff tests.test_team_router.TestTeamRouterSkillDoc.test_manager_docs_cover_active_role_wait_and_polling_backoff -v` -> Ran 2 tests OK.
- Skill documentation suite after entrypoint compression and workbench current-truth test update: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -q` -> Ran 51 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- Focused regression suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_defends_active_role_wait_and_polling_backoff tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_includes_active_role_return_model tests.test_team_router.TestTeamRouterSkillDoc.test_manager_docs_cover_active_role_wait_and_polling_backoff tests.test_team_router.TestTeamRouterSkillDoc.test_manager_orchestration_policy_docs_cover_polling_reuse_and_verifier_return tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 5 tests OK.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skill.entrypointBytes: 7160`; `skill.underTarget: true`; `skillSync.status: mismatch` because repo skill changes are not globally synced in this package.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`; `nextAction` says reviewer then verifier before closeout; unauthorized includes commit, push, PR, merge, deploy, global skill sync.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-active-wait py -B scripts\team_router_closeout_check.py --json` -> exit 0; reports the same expected dirty package surface and `skillSync.status: mismatch`.
- Reviewer v1: thread `019f1e8a-2a08-7971-921d-96d967da59a2` -> `needs_rework`; required change was to align package/workbench next-gate wording with the already-completed local verification record and doctor output.
- Rework after reviewer v1: updated package/workbench next-gate wording and the workbench current-truth test anchor; reran focused 2-test suite OK; git diff --check exit 0 with CRLF/LF warnings only; truth_check/doctor/closeout_check exit 0 with staleClaims empty, truthStatus dirty, orchestrationStatus manual_only, and expected skillSync mismatch.
- Reviewer v2: thread `019f1e8a-2a08-7971-921d-96d967da59a2` -> `pass`; requiredChanges: none; confirmed current-gate rework is aligned and no dense polling or premature restart ambiguity was reintroduced.
- Verifier v1: thread `019f1e93-a360-7220-af9e-a801336e13dd` -> `rejected`; required change was to align package/workbench current-gate wording with reviewer v2 already passed, making verifier final acceptance the current gate and leaving local commit separate unless accepted and explicitly authorized.
- Verifier v2: thread `019f1e93-a360-7220-af9e-a801336e13dd` -> `accepted`; requiredChanges: none; acceptedForCommit: true; local commit still requires explicit user authorization and push/PR/merge/global sync remain outside.

## Review And Verification Gate

Current next gate: local commit only if explicitly authorized after verifier v2 acceptance. No push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, or global skill sync is authorized.

push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, and global skill sync remain outside this package unless separately authorized.
