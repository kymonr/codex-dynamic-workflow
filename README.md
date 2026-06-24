# Team Router

Team Router 是这个仓库的主项目：一个 Codex desktop thread-tools 控制面，用长期可见 role threads 管理复杂任务的规划、执行、条件审查和验收。旧的 dynamic-workflow / cli-runner 项目已移入 `dynamic-workflow/` 子目录；它的 runner 入口现在是 `dynamic-workflow/src/runner.py`，旧技能入口是 `dynamic-workflow/skill/SKILL.md`，runner 测试在 `dynamic-workflow/tests/`。

## Team Router 快速使用

`codex-team-router` 是 `dynamic-workflow` 之外的 Codex desktop thread-tools 控制面：它不直接跑子代理命令，也不替代 `dynamic-workflow/src/runner.py` 的 `cli-runner`；它把一个调度者的任务拆给长期可见 core role thread，并可按条件接入 reviewer，并用本地 registry/ledger 记录状态。

Progressive disclosure invariant：`skills/codex-team-router/SKILL.md` 是 Codex 8KB cap 下的短入口，只保留导航和 hard entry rules；深层协议细节放在 `skills/codex-team-router/references/`。这些 references 是 Team Router contract 的一部分，测试会同时锁住入口大小、required reference files 和关键规则覆盖。

sideEffectTaxonomy：manager 动作必须先按 `READ_ONLY`、`DISPATCH_ONLY`、`LOCAL_CLOSEOUT`、`WORKSPACE_WRITE`、`HEAVY_OR_RISKY`、`EXTERNAL_RELEASE` 分类。active Manager Mode 下 `可以`、`修`、`继续`、`开始修`、`先修`、`修这个`、`do it` 至多授权 `DISPATCH_ONLY`，不是 implementation authorization；`READ_ONLY` 只支持判断和 low-frequency/event-driven `read_thread`，不能变成实现；`WORKSPACE_WRITE` 在 active Manager Mode 下必须委派 executor，除非用户明确说“切回执行者”“你亲自改代码”或“按这个 plan 落地”；`LOCAL_CLOSEOUT` 只在 verifier pass 且 explicit user commit request 后允许本地 status/diff、stage 已验收文件、local commit，并排除无关 untracked 与 push/PR/merge/deploy；`EXTERNAL_RELEASE` 必须有独立 publish/release 授权；`HEAVY_OR_RISKY` 必须单独明确授权。命名 reviewer 审核 Team Router 自身改动时仍必须使用 visible reviewer role conversation，subagent fallback is not allowed。

roleHandoffPolicy / reviewPackagePolicy：role requests 优先通过 stable file/path handoff 传递事实，而不是依赖 accumulated chat history；manager prompt 保持短，只包含 taskId、objective、expected marker、permission boundary、相关 `taskBriefPath` / `executorReportPath` / `reviewPackagePath` 和 exact return protocol。小任务可用 inline protocol blocks；高风险 Team Router self changes、reviewer-gate/process/policy changes、长 executor results 应在 role threads 可访问同一 workspace/path 时使用 review package。review package 至少包含 taskId、objective、scope、touched/accepted files、diff summary、executor callback/report、test/verification evidence、reviewer requiredChanges、excluded unrelated untracked、risks/remainingTodos。package 只补充证据，不替代 `TEAM_ROUTER_CALLBACK` / `TEAM_ROUTER_REVIEW` / `TEAM_ROUTER_VERDICT`；写 workspace package artifacts 属于 `WORKSPACE_WRITE`，active Manager Mode 下应由 executor 做，除非明确角色切换。`taskBriefPath`、`executorReportPath`、`reviewPackagePath` 当前只是 policy concepts/future optional runtime fields，本轮不实现 runtime。commit closeout 时必须显式 stage 新 reference files，因为 `git diff --name-only` 会漏掉 untracked files。

角色分工固定为：

- 调度者：理解用户目标、选择下一步、调用 Codex thread tools，并输出 `Team Router Handoff` 或 `Team Router Closeout`。
- 状态控制器：在父线程侧维护 registry、task ledger、recovery anchors、direct-return 捕获和状态转移；它不是单独 thread。
- 规划者：只回复 `TEAM_ROUTER_PLAN`，定义 scope、stopWhen、riskBoundary 和 executorPrompt。
- 执行者：按 `TEAM_ROUTER_DISPATCH` 做 read-only/design-only 工作，并回复 `TEAM_ROUTER_CALLBACK`。
- 审查者：conditional reviewer；只在 router/manager/orchestration policy、权限/安全边界、流程规则、role protocol、shared/high-risk logic 等任务中介入，做 read-only/adversarial 挑刺并回复 `TEAM_ROUTER_REVIEW`；普通小修/明确低风险任务跳过。
- 验证者：检查 callback、reviewer 要求、证据和边界，并回复 `TEAM_ROUTER_VERDICT`；verifier remains final acceptance。

当前 Team Router 能力边界仅为 `read-only/design-only`；不支持 `workspace-write`、commit、push、PR、merge、deploy、真实 API、账号或生产数据操作。需要写代码时，应回到明确授权的普通本地实现流程，或使用 `dynamic-workflow` 写模式的 `prepare` / `dispatch` / `collect` 隔离 worktree 流程。

Manager Mode 是当前任务内的粘性角色：用户说“你作为管理者”后，该角色会一直持续到明确角色切换；后续无称呼或同类实现命令，例如 `修`、`继续`、`处理`、`先修`、`开始修`、`修这个`、`开始处理`、`先处理`、`按刚才说的修`、`go`、`do it`，只能触发计划细化、规则更新建议或 dispatch/prepare executor work，不代表 manager 可以亲自改文件或跑测试；退出该边界需要用户明确说“切回执行者”“你亲自改代码”或“按这个 plan 落地”。

父线程入口先用 `parent_entry_guard()` 判定路径：有完整 callable adapter 时才走 `orchestrate_team_task_with_adapter()`；没有 callable adapter 或 thread tools 时，只能走 manual/pre-created continuation，并且必须已经有 `manager`、`executor`、`verifier` 三个 core role thread 绑定；conditional reviewer 只在 gate 适用时创建或复用。manual/pre-created continuation 由父线程直接调用 app tools 和 manual helper/record/capture functions 续跑，不把 pre-created roles 送进 adapter runner；`parent_entry_guard(...precreated_roles...)` 只做边界判定/提示。协议/角色/状态快照由 `protocol_contract_snapshot()` 提供给测试和文档对齐；三角色可见模式 fixture 在 `tests/fixtures/team_router/three_role_visible_smoke_scenarios.json`。

Direct return 规则：当父线程/manager thread id 可用时，executor dispatch 必须包含 `returnThreadId`、`callbackDelivery: direct-send`、`callbackFallback: self-thread-marker`，并要求执行者写完 `TEAM_ROUTER_CALLBACK` 后调用 `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK block>)` 主动返回父线程；reviewer request 必须包含 `returnThreadId`、`reviewDelivery: direct-send`、`reviewFallback: self-thread-marker`，并要求审查者写完 `TEAM_ROUTER_REVIEW` 后调用 `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)`；verifier request 同理必须包含 `returnThreadId`、`verdictDelivery: direct-send`、`verdictFallback: self-thread-marker`，并要求验证者写完 `TEAM_ROUTER_VERDICT` 后调用 `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)`。保留 self-thread marker 作为 fallback/audit 路径。

管理者 orchestration policy：等待 executor/reviewer/verifier 时，`read_thread` 只能是 bounded、low-frequency、event-driven；Role threads do not actively push back，所以不是 zero-read waiting。允许读取仅限 user-triggered status check、agreed or explicit interval（默认 30-60s cadence）后、known expected completion window 后、timeout/blocker handling；不得 continuous polling，也不得把读取变成 mid-run instruction injection；只有状态变化、timeout、blocked 或 completion 才给用户可见汇报。Role reuse policy：同一 `taskId` 或同一 task family 默认 reuse existing executor、existing reviewer（当 conditional reviewer gate 适用）和 existing verifier thread；返工继续发给 original executor，审查返工继续发给 original reviewer，复核返工继续发给 original verifier；只有 role、permission、workspace、task-family boundary 或 isolation requirement 变化时才 `create_thread` 新 role thread。conditional reviewer gate：普通小修/明确低风险任务保持 executor -> verifier；router/manager/orchestration policy、权限/安全边界、流程规则、role protocol、shared/high-risk logic 必须走 executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance)。reviewer 独立挑设计风险、规则漏洞、遗漏和新坏模式，不做实现，not final acceptance；verifier remains final acceptance。runtime gate 使用 `send_reviewer_request_with_adapter()`、`read_reviewer_review_update_with_adapter()` 和 `capture_reviewer_review_from_read()` 执行 reviewer step：reviewer `pass` 后才进入 verifier，`needs_rework` 回到 executor rework，`blocked` 进入 blocked。用户点名 `reviewer` 审核 Team Router 自身改动时，manager 必须使用 reviewer role conversation/thread；没有 existing reviewer thread 时必须显式 create/register reviewer role conversation，或说明缺口并等待确认，subagent fallback is not allowed。Trigger logic covers `runtime gate`, `reviewer gate`, `Team Router self changes`, and `Team Router` combined with reviewer/runtime/protocol/policy/permission/safety/process/shared/high-risk semantics; a plain `team_router.py` filename or low-risk docs-only/single-file cleanup does not trigger reviewer by itself。

Fast Lane policy: classify Team Router work as FAST, NORMAL, STRICT, or PACKAGE. FAST covers docs/BOM/single phrase rework, routes executor -> verifier, and uses a 30s bounded read_thread fallback window. NORMAL covers small focused code/test work, routes executor -> verifier, and uses a 60s bounded read_thread fallback window. STRICT covers Team Router process/permission/safety/role protocol/shared-risk changes, routes executor -> reviewer -> verifier, and uses a 90s bounded read_thread fallback window. PACKAGE covers same task family discipline hardening, keeps one executor -> reviewer -> verifier chain, and uses a 120s bounded read_thread fallback window. Completion is direct-return first; bounded read_thread fallback is allowed only after the class window, user-triggered status request, known expected completion window, or timeout/blocker handling.
Manager commit closeout policy：用户只和 manager 对话时，manager owns commit workflow。verifier pass 后且用户明确要求提交时，manager 可以作为 closeout 操作执行本地 `git status` / `git diff`、stage 已验收文件、commit；不得借提交继续实现、修改文件或跑重型命令；必须排除无关 untracked。push/PR/merge/deploy 单独授权。

roleCloseoutPolicy：任务完成后默认不 clear role thread，也默认不向 role threads 额外发送 ROLE_CLOSEOUT 或普通 closeout 消息。final protocol block is the closeout：executor 的 `TEAM_ROUTER_CALLBACK`、reviewer 的 `TEAM_ROUTER_REVIEW`、verifier 的 `TEAM_ROUTER_VERDICT` 已经足够作为任务结束锚点。compact is native operation, not chat prompt；manager 不得通过发送 `compact` 或 `ROLE_CLOSEOUT` 文本假装压缩上下文。若当前环境支持 native compact 且确有必要（例如 role thread 上下文过长），manager 可以触发 native compact；没有可用 compact 工具则不做。只有 role thread 仍 active/inProgress 且需要停止、没有 final protocol block 需要最短停止锚点、准备 compact/archive 前需要极短恢复锚点、或用户明确要求时，才可发送最短 closeout/stop message。clear 不作为默认动作；新建或归档旧 role thread 仅限身份污染、上下文过长、task family/permission/workspace boundary 变化或用户明确要求。

## Project Layout

```text
README.md                                      # Team Router root entrypoint
src/team_router.py                             # Team Router protocol, registry, ledger, adapter helpers
skills/codex-team-router/SKILL.md              # short Codex skill entrypoint
skills/codex-team-router/references/           # Team Router contract references
docs/runbooks/codex-team-router-live-orchestration.md
docs/artifact-policy.md                    # 生成产物与证据留存规则
docs/evidence/                             # 小型审查/验证证据，不放二进制生成资产
tests/test_team_router.py
tests/fixtures/team_router/
dynamic-workflow/                              # legacy dynamic-workflow / cli-runner subproject
```

## dynamic-workflow Subproject

The older dynamic-workflow / cli-runner files now live under `dynamic-workflow/`:

```powershell
py -m py_compile dynamic-workflow\src\runner.py
py -m unittest discover -s dynamic-workflow\tests -v
```

Its detailed docs are in `dynamic-workflow/README.md`, `dynamic-workflow/skill/SKILL.md`, and `dynamic-workflow/docs/`. The later physical folder rename to `D:\codex\Team Router` is not part of this repository layout change.

## Tests

```powershell
py -m unittest discover -s tests -p test_team_router.py -v
py -m unittest discover -s dynamic-workflow\tests -v
```
