# Team Router Handoff Package: ctr-20260628-workbench-tool-error-governance

## Task Summary / 任务摘要

- taskId: `ctr-20260628-workbench-tool-error-governance`
- objective: 治理 `docs/workbench.md` 当前态陈旧风险，并固化 thread tools 缺失时的 `tool_error` / `manual orchestration only` 降级表达。
- gateClass: `PACKAGE`
- permission: `local-package`
- execution mode: historical manual executor package; its old current-host capability claim was later superseded by `ctr-20260628-live-capability-state-fix`. This package remains valid only for the no-tools `tool_error` / `manual orchestration only` governance rule.

## Scope / 范围

本包只覆盖 docs/tests/policy snapshot 文本，不改变 runtime behavior。

## Protocol References / 协议引用

- Expected callback marker: `TEAM_ROUTER_CALLBACK taskId=ctr-20260628-workbench-tool-error-governance`
- Required reviewer marker: `TEAM_ROUTER_REVIEW taskId=ctr-20260628-workbench-tool-error-governance`
- Required verifier marker: `TEAM_ROUTER_VERDICT taskId=ctr-20260628-workbench-tool-error-governance`

## Touched Files / 触及文件

- `tests/test_team_router.py`
- `docs/workbench.md`
- `skills/codex-team-router/references/manager-mode.md`
- `skills/codex-team-router/references/manual-orchestration.md`
- `skills/codex-team-router/references/testing-and-quality-gates.md`
- `docs/team-router/packages/ctr-20260628-workbench-tool-error-governance.md`

## Behavior Changes / 行为变化

- At the time of this historical package, `docs/workbench.md` 的 Current Task 改为本轮 `ctr-20260628-workbench-tool-error-governance`，不再把旧 isolated worktree C package 状态当成当前事实。Do not copy that historical current-host capability state into current status.
- Team Router skill contract 明确：当前 host 未暴露 required thread tools 时，状态只能是 `tool_error` / `manual orchestration only`；copy-paste executor/reviewer/verifier prompts 只是 handoff text，不是 live dispatch evidence。
- 测试锁定上述文档契约，避免后续 closeout 或 manager plan 再把缺失工具环境描述成已创建/派发/等待真实 role threads。

## Diff Summary / Diff 摘要

- 更新 workbench current task、current diff surface、verification record 和 integration boundary。
- 在 `manager-mode.md` 增加 no-tools 降级规则。
- 在 `manual-orchestration.md` 增加 no-tools 手工编排边界。
- 在 `testing-and-quality-gates.md` 增加 no-tools degradation 测试要求。
- 在 `tests/test_team_router.py` 增加 focused contract checks。

## Verification / 验证

- RED: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_thread_tool_absence_is_tool_error_or_manual_only_not_role_dispatch -v` failed as expected before docs updates.
- GREEN focused check: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_thread_tool_absence_is_tool_error_or_manual_only_not_role_dispatch -v`: pass.
- `py -m py_compile tests\test_team_router.py`: pass after rerunning without concurrent `.pyc` writes.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 33 tests.
- `py -m unittest tests.test_team_router -v`: pass, 241 tests.
- `git diff --check`: pass; Git printed CRLF/LF normalization warnings for existing working-copy files, with no whitespace errors.

## Excluded Changes / 未纳入改动

- No runtime behavior changes.
- No thread creation, no live Team Router role dispatch, no watcher reads.
- No commit, push, PR, merge, publish, or release.
- No global skill sync.

## Risks / 风险

- This package hardens documentation and contract tests only; live orchestration still depends on host-provided thread tools.
- Review should check that no wording implies real role-thread dispatch happened in this host.

## Remaining Todos / 剩余事项

- historical package; current-host no-tools claim superseded by `ctr-20260628-live-capability-state-fix`, while the no-tools governance rule remains active. Commit only as a historical/superseded package if included in the accepted closeout batch.
