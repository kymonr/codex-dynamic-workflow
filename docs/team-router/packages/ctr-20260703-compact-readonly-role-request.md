# Team Router Handoff Package: ctr-20260703-compact-readonly-role-request

## Task Summary / 任务摘要

修普通 `READ_ONLY` reviewer/verifier 请求模板：无 `reviewPackagePath` 时也保持短输出；协议 marker/字段名/枚举值保持英文，人类说明默认中文。

## Scope / 范围

- `src/team_router.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/role-handoff-and-review-package.md`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260703-compact-readonly-role-request.md`

## Protocol References / 协议引用

- `TEAM_ROUTER_REVIEW_REQUEST`
- `TEAM_ROUTER_VERIFY`
- `TEAM_ROUTER_REVIEW`
- `TEAM_ROUTER_VERDICT`
- `reviewPackagePath`
- `inlineFallback: true`

## Touched Files / 触及文件

- `src/team_router.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/role-handoff-and-review-package.md`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260703-compact-readonly-role-request.md`

## Behavior Changes / 行为变化

- Added a compact branch for ordinary `permission: read-only` reviewer/verifier requests when no package path and no `inlineFallback: true` are present.
- The no-path compact branch keeps `riskBoundary:`, adds Chinese `action:`, summarizes parsed callback fields without embedding raw callback text, and uses one-line `reply:` field guidance.
- Path-based package handoff still uses `replyMarker` / `replyFields` / `reviewPackagePath: <path|inline>`.
- Explicit inline fallback without paths remains on the detailed template.
- Direct-return semantics are preserved; compact no-path requests use the same compact direct-return instruction shape as package-path compact prompts.

## Diff Summary / Diff 摘要

- `src/team_router.py`: added compact-mode helpers and wired them into `make_reviewer_request_message()` / `make_verifier_request_message()`.
- `tests/test_team_router.py`: added RED/GREEN regression for no-package `read-only` reviewer/verifier requests and retained adjacent prompt regressions.
- `skills/codex-team-router/SKILL.md` and `role-handoff-and-review-package.md`: documented the no-path `READ_ONLY` compact rule.
- `docs/workbench.md`: refreshed current task, gate, risks, and verification record for this package.

## Verification / 验证

- RED: `py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_read_only_role_requests_without_review_package_stay_compact -v` first failed because no-package `read-only` reviewer/verifier requests still emitted raw callback, detailed reply template, and no compact Chinese `action:` / one-line `reply:`.
- GREEN: `py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_read_only_role_requests_without_review_package_stay_compact -v` -> Ran 1 test OK.
- Adjacent prompt regression: `py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_package_path_manager_requests_reference_callback_and_review_results_by_path tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template -v` -> Ran 6 tests OK.
- Focused final regression after direct-return rework: `py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_reviewer_request_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterManagerIntegration.test_verifier_request_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterManagerIntegration.test_verifier_request_uses_recent_executor_callback_observation tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_sends_reviewer_request_for_high_risk_callback tests.test_team_router.TestTeamRouterProtocol.test_read_only_role_requests_without_review_package_stay_compact -v` -> Ran 5 tests OK.
- Full suite: `py -X utf8 -B -m unittest tests.test_team_router -v` -> Ran 425 tests OK.
- Truth check: `py -X utf8 -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skill.entrypointBytes: 7169`; initial `skillSync.status: mismatch` before global sync authorization.
- Closeout check: `py -X utf8 -B scripts\team_router_closeout_check.py --json` -> exit 0; reports read-only; no commit/push/PR/merge/deploy/global sync authorized.
- Skill sync check: `py -X utf8 -B scripts\team_router_skill_sync_check.py --check` -> exit 1 with `status: mismatch`; changed `SKILL.md` and `references/role-handoff-and-review-package.md`; expected until explicit global sync authorization.
- Diff whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for existing text files only.
- Fresh status: `git status -sb --untracked-files=all` -> dirty tracked files are `docs/workbench.md`, `skills/codex-team-router/SKILL.md`, `skills/codex-team-router/references/role-handoff-and-review-package.md`, `src/team_router.py`, `tests/test_team_router.py`; untracked package is `docs/team-router/packages/ctr-20260703-compact-readonly-role-request.md`.
- Reviewer: direct-return pass from thread `019f23eb-6322-7aa0-91f5-869fb607d87b`; findings none; requiredChanges none.
- Verifier: direct-return pass from thread `019f23ef-0610-7912-86d2-034ebfaa0240`; requiredChanges none; accepted for local closeout.
- Authorized global sync: `py -X utf8 -B scripts\team_router_skill_sync_check.py --sync` -> `status: match`; follow-up `py -X utf8 -B scripts\team_router_skill_sync_check.py --check` -> `status: match`.

## Excluded Changes / 未纳入改动

- No PR, merge, deploy, or independent service work.
- No changes to project `AGENTS.md`.
- No parser, ledger transition, watcher, adapter, host runtime, gate-class classifier, or production scheduling changes.

## Risks / 风险

- Compact no-path read-only prompts rely on parsed callback summary fields; reviewers/verifiers should request more detail only when the compact evidence is insufficient.
- Explicit `inlineFallback: true` remains detailed to avoid losing package-fallback semantics.

## Remaining Todos / 剩余事项

- Local commit and publish were authorized after verifier pass.
