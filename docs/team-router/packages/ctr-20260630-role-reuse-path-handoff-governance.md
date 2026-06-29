# Team Router Handoff Package: ctr-20260630-role-reuse-path-handoff-governance

## Task Summary / 任务摘要
实现一个小型 Team Router governance package，目标是把 role reuse 与 path-based handoff 的关键规则变成可验证的 runtime/test/doc 行为。

## Scope / 范围
允许修改：`src/team_router.py`、`tests/test_team_router.py`、本 package 文件。

明确不做：不修改 `src/team_router_state.py`，不触碰 phase 2a state extraction 语义，不创建新 role thread，不 stage/commit/push/PR/merge/deploy/global sync。

## Protocol References / 协议引用
- `taskId`: `ctr-20260630-role-reuse-path-handoff-governance`
- `taskBriefPath`: `docs/team-router/packages/ctr-20260630-role-reuse-path-handoff-governance.md`
- `executorReportPath`: `docs/team-router/packages/ctr-20260630-role-reuse-path-handoff-governance.md`
- `reviewPackagePath`: `docs/team-router/packages/ctr-20260630-role-reuse-path-handoff-governance.md`
- Required route: executor -> reviewer -> verifier

## Design Decisions / 设计决策
- 保持 `src/team_router.py` 作为 public facade/runtime surface，本包不编辑 `src/team_router_state.py`、`src/team_router_protocol.py`、`src/team_router_policy.py`。
- `resolve_role_threads_with_adapter` 继续作为 live/manual orchestration 的正常入口：先 registry reuse，再 `list_threads` discovery，再只为仍缺失的 role 调用 `create_thread`。
- `create_role_threads_with_adapter` 新增内部 `discovery_checked` 参数。正常 orchestrate/send 路径在先 discovery 后以 `discovery_checked=True` 调用；直接绕过 discovery 且 adapter 可发现可复用非归档 role thread 时，抛出 `StateStoreError`，阻止重复创建。
- start path 对不可用 registry role 的 replacement 也写入 `replacesThreadId` 和 `replacementReason`；send/reviewer/verifier 路径原有 replacement metadata 保持不变。
- path handoff 保持 PACKAGE/STRICT 稳定路径形状：executor callback 模板在 path handoff 启用时同时要求 `executorReportPath` 和 `reviewPackagePath`，并要求长日志/完整证据放入路径文件而不是塞进 callback。

## Implementation Notes / 实现说明
- `src/team_router.py`
  - `create_role_threads_with_adapter(..., discovery_checked=False)` 默认会先调用 `discover_role_threads_with_adapter`；发现可复用线程时错误信息包含 `role=threadId`。
  - `_ensure_role_with_adapter` 和 `resolve_role_threads_with_adapter` 在已完成 discovery 后传入 `discovery_checked=True`，避免重复 discovery，同时保留已有正常流。
  - 新增 `_role_replacement_metadata` / `_record_with_replacement_metadata`，用于 start path 将不可用 registry role 的替换原因写入最终 registry record。
  - executor dispatch callback 模板将 evidence 收敛为短摘要，并在路径交接启用时补充 `reviewPackagePath` 字段。
- `tests/test_team_router.py`
  - 新增直接创建守卫回归：发现 `live-executor` 时阻止 `create_thread`。
  - 扩展 start replacement 回归：broken executor 被 replacement 时记录 `replacesThreadId` 和 `replacementReason`。
  - 扩展 compact path template 回归：executor callback 包含 `executorReportPath`、`reviewPackagePath`，且长证据写路径。

## Behavior Changes / 行为变化
- 可复用 role thread 可由 adapter discovery 暴露时，直接调用创建函数不能跳过 discovery 盲目创建重复 role thread。
- start path replacement 与 send/reviewer/verifier replacement 一致，都会记录明确 replacement reason。
- PACKAGE/STRICT 路径交接下，callback 默认保持简短，完整证据进入 `executorReportPath` / `reviewPackagePath`。

## Diff Summary / Diff 摘要
- Modified: `src/team_router.py`
- Modified: `tests/test_team_router.py`
- Added: `docs/team-router/packages/ctr-20260630-role-reuse-path-handoff-governance.md`
- Not modified: `src/team_router_state.py`, `src/team_router_protocol.py`, `src/team_router_policy.py`, skills, scripts, module map, global skill files.

## Verification / 验证
- `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterManagerIntegration.test_create_role_threads_with_adapter_blocks_create_when_discovery_finds_reusable_role tests.test_team_router.TestTeamRouterManagerIntegration.test_start_team_task_with_adapter_replaces_broken_registry_role_without_duplicate_active_roles -v`
  - Result: exit 0; Ran 3 tests in 0.025s; OK.
- `py -B -m unittest discover -s tests -p test_team_router.py -v`
  - Result: exit 0; Ran 334 tests in 11.026s; OK.
- `py -B scripts\team_router_truth_check.py --json`
  - Result: exit 0; `authorization` all false for commit/deploy/globalSync/merge/pullRequest/push; `staleClaims`: `[]`; `skillSync.status`: `match`.
- `git diff --check`
  - Result after final package write: exit 0; only CRLF normalization warnings for `src/team_router.py` and `tests/test_team_router.py`; no whitespace errors.
- `git status -sb --untracked-files=all`
  - Result after final package write: `## master...origin/master [ahead 3]`; modified `src/team_router.py`, `tests/test_team_router.py`; untracked this package file.

## Excluded Changes / 未纳入改动
- 不修改 `src/team_router_state.py`。
- 不做提交、推送、PR、merge、deploy 或 global sync。
- 不创建新的 role threads。
- 不编辑 skills/reference docs，因为现有 docs tests 已覆盖 standing role reuse、replacement reason、PACKAGE/STRICT path handoff 规则；本包只补 runtime/test enforcement。

## Risks / 风险
- `create_role_threads_with_adapter` 新增默认 discovery guard。没有 `list_threads` 的 adapter 保持原行为；有 `list_threads` 且返回可复用线程的直接调用会从创建变为报错，需要调用方走 discovery/reuse 正常入口。
- `git diff --check` 在本仓库当前配置下输出 CRLF normalization warning，但命令 exit 0 且无 whitespace error。

## Remaining Todos / 剩余事项
- Executor 完成后需要 reviewer gate。
- Reviewer 通过后再进入 verifier。
