# Team Router Review Package: ctr-20260630-role-thread-prompt-path-contract

## Package Metadata

- taskId: `ctr-20260630-role-thread-prompt-path-contract`
- permission: `local-package`
- baseline: committed dispatch-prompt path-handoff package `ffcebd7`
- objective: codify role-thread prompt path handoff across Manager, Reviewer, and Verifier prompt surfaces.
- scope: `src/team_router.py`, `tests/test_team_router.py`, `README.md`, `skills/codex-team-router/SKILL.md`, `skills/codex-team-router/references/role-handoff-and-review-package.md`, `docs/workbench.md`, this package file.
- outOfScope: parser/state-machine/direct-return semantics, live host adapter/scheduler implementation, production daemon, push, PR, merge, deploy, publish/release, global skill sync.

## Task Summary / 任务摘要

本包把 path handoff 从 executor dispatch 细节提升为 role-thread prompt 合同：Manager、Reviewer、Verifier 的 bootstrap prompt 必须先声明 `roleCommunicationMode: concise-protocol-plus-paths`，Manager plan request 也必须把 PACKAGE 路径交接规则说清楚。路径仍只是证据交接，不会扩大 permission 或 riskBoundary。

## Behavior Changes / 行为变化

- New role-thread bootstrap prompts now include `roleCommunicationMode: concise-protocol-plus-paths`.
- Bootstrap prompts state that formal `TEAM_ROUTER_*` messages should use `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` for long context, reports, and evidence.
- Bootstrap prompts state that paths are handoff evidence only and cannot expand permission or risk boundaries.
- Manager plan requests now include the same mode plus PACKAGE default `reviewPackagePath` / inline fallback wording before the plan response template.

## Diff Summary / Diff 摘要

- Modified: `src/team_router.py`
  - Added `ROLE_THREAD_PATH_HANDOFF_PROMPT_LINES`.
  - Included the shared prompt lines in `make_role_thread_prompt()`.
  - Included the shared prompt lines and PACKAGE default note in `make_plan_request_message()`.
- Modified: `tests/test_team_router.py`
  - Added `test_manager_reviewer_verifier_prompts_codify_path_handoff_contract`.
- Modified: `README.md`
  - Clarified that role bootstrap and Manager plan requests are part of the stable file/path handoff contract.
- Modified: `skills/codex-team-router/SKILL.md`
  - Kept the short entrypoint under target and added the bootstrap/Manager request mode sentence.
- Modified: `skills/codex-team-router/references/role-handoff-and-review-package.md`
  - Documented bootstrap and Manager plan request path handoff expectations.
- Modified: `docs/workbench.md`
  - Updated current package state and verification notes.

## Verification / 验证

- RED: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_manager_reviewer_verifier_prompts_codify_path_handoff_contract -v` -> failed before implementation because bootstrap prompts and Manager plan request lacked `roleCommunicationMode: concise-protocol-plus-paths`.
- GREEN focused: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_manager_reviewer_verifier_prompts_codify_path_handoff_contract -v` -> Ran 1 test OK.
- Related prompt/doc checks: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_manager_reviewer_verifier_prompts_codify_path_handoff_contract tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterSkillDoc.test_skill_entrypoint_contains_explicit_path_field_contract tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_role_handoff_and_review_package_policy_docs_cover_stable_packages tests.test_team_router.TestTeamRouterSkillDoc.test_dispatch_prompt_path_handoff_package_records_boundary -v` -> Ran 7 tests OK.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 348 tests OK.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `skill.entrypointBytes: 7145`, `skill.underTarget: true`, `skillSync.status: mismatch` because repo-local `SKILL.md` and `references/role-handoff-and-review-package.md` changed; global sync is not authorized.
- Doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `nextAction: review the local diff, run the required reviewer pass, then run the required verifier pass before closeout`.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> `skill.entrypointBytes: 7145`, `underTarget: true`, `skillSync.status: mismatch`.
- Whitespace check: `git diff --check` -> exit 0 with CRLF/LF replacement warnings only for `docs/workbench.md`, `src/team_router.py`, and `tests/test_team_router.py`.

## Excluded Changes / 未纳入改动

- No parser, ledger schema, state-machine, watcher, direct-return capture, host adapter, or scheduler behavior change.
- No global skill sync; repo/global skill mismatch is expected until a separately authorized sync gate.
- No commit, push, PR, merge, deploy, publish, or release.

## Risks / 风险

- This changes prompt wording only. It does not make role threads able to read filesystem paths unless the current host/workspace already gives them access.
- The repo-local skill entrypoint remains under its size target, but global skill sync is intentionally separate.

## Remaining Todos / 剩余事项

- Send this package to reviewer gate.
- Send to verifier gate after reviewer pass.
- Commit remains separate and requires explicit authorization after verifier pass.