# Team Router Handoff Package: ctr-20260627-info-format-impl

## Task Summary / 任务摘要

- taskId: `ctr-20260627-info-format-impl`
- objective: 实现 Team Router 双层跨线程信息格式：严格 protocol blocks + 持久 Markdown review package。
- status: Tasks 1-5 implemented and verified locally.
- reviewPackagePath: `docs/team-router/packages/ctr-20260627-info-format-impl.md`

## Scope / 范围

本次仅在 `D:\codex\Team Router` 本地 checkout 内工作。范围限定为 dispatch 指令的 acceptedFiles；未 commit、push、PR、merge、deploy、publish、安装依赖或触达外部服务。

## Protocol References / 协议引用

- `TEAM_ROUTER_DISPATCH taskId=ctr-20260627-info-format-impl`
- callbackMarker: `TEAM_ROUTER_CALLBACK taskId=ctr-20260627-info-format-impl`
- callbackMode: `self-thread-marker`
- sourceRoleThreadId: `019f073f-7101-7f71-82cf-561bb7a0242e`
- roleThreadId: `019f073f-7101-7f71-82cf-561bb7a0242e`
- permission: `local-package`
- reviewPackagePath: `docs/team-router/packages/ctr-20260627-info-format-impl.md`

## Touched Files / 触及文件

- `src/team_router.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/references/role-handoff-and-review-package.md`
- `docs/team-router/packages/ctr-20260627-info-format-impl.md`

Accepted but not edited by executor:

- `docs/superpowers/specs/2026-06-27-team-router-cross-thread-information-format-design.md`
- `docs/superpowers/plans/2026-06-27-team-router-cross-thread-information-format.md`

## Behavior Changes / 行为变化

- `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY` 现在暴露 `defaultReviewPackagePath`、`defaultPathScope`、`gitPolicy`、`languagePolicy`、`diffPolicy` 和 bilingual template sections。
- `reviewPackage.minimumContent` 扩展为包含 protocol marker references、behavior changes、diff summary without full diff、verification evidence and actual commands/results、excluded changes and untracked files。
- `STRICT` 仍是 recommended；`PACKAGE` 仍是 default required unless explicit inline fallback is marked。
- `role-handoff-and-review-package.md` 记录 durable path `docs/team-router/packages/<taskId>.md`、语言规则、不贴完整 diff 的规则、bilingual package shape 和 legacy package warning。
- 没有让 runtime 读取、执行、解析或信任 Markdown package content。

## Diff Summary / Diff 摘要

- `src/team_router.py`: 只更新 policy snapshot 常量，未修改 parser/state transition/runtime package-reading code。
- `tests/test_team_router.py`: 增加 policy snapshot 和 reference doc 断言；对旧 README/runbook 文本保留兼容 alternatives。
- `skills/codex-team-router/references/role-handoff-and-review-package.md`: 增加 durable path、语言和 diff 规则、bilingual template、legacy warning。
- 本包只给摘要，不包含 full diff。
- 实施备注：plan 同时要求 `STRICT == "recommended"` 和更详细的 `STRICT` 字符串，因此测试改为检查包含 `recommended`，保留非阻塞语义。

## Verification / 验证

- Task 1 focused failure captured: `py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy -v` -> FAIL, 原因为 old `minimumContent` 未包含新合同字段。
- After policy update before doc update: focused test -> FAIL, 原因为 reference doc 尚未包含 durable path / bilingual sections / no-full-diff 规则。
- `git diff -- src\team_router.py | Select-String -Pattern "def parse_message|def parse_plan|def parse_callback|def parse_verdict|def parse_review|def _apply_review_package_path_metadata|read_text|open\("` -> exit 0, no output.
- `Select-String -Path .gitignore -Pattern "docs/team-router/packages|team-router/packages"` -> exit 0, no output.
- `Select-String -Path skills\codex-team-router\references\role-handoff-and-review-package.md -Pattern "docs/team-router/packages/<taskId>.md|must not include a full diff|free-text fields default to Chinese|Behavior Changes / 行为变化"` -> exit 0, required matches found.
- `py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy -v` -> PASS.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> PASS, 27 tests.
- `py -m py_compile src\team_router.py tests\test_team_router.py` -> PASS, exit 0.
- `py -m unittest discover -s tests -p test_team_router.py -v` -> PASS, 224 tests.
- `git diff --check` -> PASS, exit 0; warning only: CRLF will be replaced by LF for `skills/codex-team-router/references/role-handoff-and-review-package.md` and `tests/test_team_router.py`.

Manual edit note:

- `apply_patch` failed because the Windows sandbox could not prepare the restricted-token wrapper. I used precise workspace-local PowerShell/Python text replacements and recorded this fallback here.

## Excluded Changes / 未纳入改动

- 未修改 `.gitignore`。
- 未修改 `skills/codex-team-router/SKILL.md`。
- 未修改 parser functions：`parse_message`、`parse_plan`、`parse_callback`、`parse_verdict`、`parse_review`。
- 未增加 runtime Markdown package reading、`read_text` 或 `open(` trust path。
- 未 stage、commit、push、PR、merge、deploy、publish。
- 未编辑 README/runbook；测试对旧文档用 alternatives 兼容旧用语，新合同由 policy snapshot 和 reference doc 锁定。

Current untracked files:

- `docs/superpowers/plans/2026-06-27-team-router-cross-thread-information-format.md`
- `docs/superpowers/specs/2026-06-27-team-router-cross-thread-information-format-design.md`
- `docs/team-router/packages/ctr-20260627-info-format-impl.md`

## Risks / 风险

- `git diff --check` 只有 CRLF/LF warning，无 whitespace error。
- Package content 仍是人和角色审查约束，runtime 按设计不做 Markdown schema 校验。

## Remaining Todos / 剩余事项

- Manager Task 6: dispatch visible Team Router Reviewer and Verifier.
- Commit/push/PR/merge/publish/release: not done; only after separate authorization.
