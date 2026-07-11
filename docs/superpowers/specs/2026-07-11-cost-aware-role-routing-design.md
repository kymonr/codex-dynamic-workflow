# Team Router Cost-Aware Role Routing Design

- 日期：2026-07-11
- 状态：设计已确认，待用户审阅本文档
- 范围：让当前主线程承担 Manager/Orchestrator，轻量任务直接处理，需要外派时按智能、速度和额度选择并复用可见 Codex role 线程。
- 非范围：本设计不授权实现、全局 skill 同步、全局 `AGENTS.md` 修改、push、PR、merge、deploy、生产/API 操作或 native subagent 派工。

## 1. 背景

当前 Team Router 默认创建独立 `manager`、`executor`、`verifier` 核心线程，普通任务也走固定的 `executor -> verifier`。这会产生额外的线程启动、上下文交接和复核成本。

当前 Codex 线程接口允许 `create_thread` 和 `send_message_to_thread` 显式指定 `model` 与 `thinking`，且复用线程时可以按消息覆盖模型。相比之下，native `spawn_agent` 没有可控的 `model/thinking` 参数，不能满足本设计的额度控制目标。

## 2. 目标

- 当前主线程直接承担 Manager/Orchestrator，不再创建独立 Manager role。
- 小型、低风险、上下文密集的任务由管理者直接完成。
- 只有外派带来并行、隔离、独立复核或模型成本收益时才创建 role。
- 同一管理者、同一项目优先复用现有 role，并在每次派工时显式设置模型。
- 默认使用 Luna Medium、Terra Medium、Sol High 三档路由，同时允许受控覆盖。
- 日常任务取消固定 verifier；`STRICT/PACKAGE` 保留独立 Reviewer 和 Verifier。
- 防止自动升级、返工或并行扩张造成失控消耗。
- 最终回复提供简短、可审计的模型路由回执。

## 3. Manager Mode 入口与授权

标准入口：

```text
你作为管理者，完成 <目标>
```

该表达表示：

- 进入 Manager Mode。
- 授权管理者在目标范围内直接完成符合本设计边界的小任务。
- 授权按需创建、复用、切换模型和升级可见 role。
- 允许目标所需的本地最小修改与验证。
- 不包含 commit、push、PR、merge、deploy 或其他外部 gate。
- 目标包含“只读 / review / 检查”等零写入语义时，仍保持零写入。

只说“进入 Manager Mode”只进入分析与方案阶段，不创建 role。

Manager Mode 不检查或限制当前主管理者使用的模型。本设计的 Sol Ultra 限制只作用于管理者创建或派发的 role。

## 4. Complex Task Stack 组合语义

入口：

```text
你作为管理者，走复杂任务流程完成 <目标>
```

该表达同时触发 Manager Mode 和 Complex Task Stack。

规划 gate：

- 核对当前真相、拆分任务、风险和验收标准。
- 仅在独立证据确有价值时派只读 role。
- 不修改工作区文件，不 commit。
- 输出执行方案后等待用户确认。

用户确认执行方案后进入执行 gate，每项连续执行：

```text
当前真相 -> 前置 review -> 最小实现 -> 定向复审 -> 验证 -> scoped commit -> 检查点 -> 下一项
```

Complex Task Stack 不自动等于风险等级 `PACKAGE`。每个执行项独立分类。任何外部 gate 仍需单独授权。

## 5. 无状态直做路径

管理者直接处理的任务必须同时满足：

- 风险等级为 `FAST` 或 `NORMAL`。
- 单一、低风险、可串行完成。
- 不需要独立上下文或并行。
- 存在明确的轻量验证方式。
- 不涉及安全、金额、生产、全局配置或外部 gate。

直做路径不创建 Team Router ledger、registry 或 role。只读任务因此保持真正零写入。

只有首次需要派工时才启动 Team Router 状态，创建该任务 ledger，并把目标、已完成内容、剩余范围、授权和停止条件写入 dispatch。

`STRICT/PACKAGE` 不允许管理者独自实现和验收，必须使用角色流程。

## 6. 模型路由

### 6.1 默认映射

| executionClass | 默认模型 | 默认 thinking | 适用范围 |
|---|---|---|---|
| `mechanical` | `gpt-5.6-luna` | `medium` | 规则明确、无需业务判断、范围有限、可确定性验证 |
| `standard` | `gpt-5.6-terra` | `medium` | 普通检索、分析、修改和文档工作 |
| `high` | `gpt-5.6-sol` | `high` | 复杂调试、跨模块设计、高风险判断或升级处理 |

管理者选择 `executionClass`，Runtime 解析为完整的 `model + thinking`。

### 6.2 受控覆盖

管理者可以为单次派工覆盖默认组合，但必须同时提供：

```text
model
thinking
modelOverrideReason
```

缺少任一字段时拒绝派工，不猜测、不继承上一次设置。覆盖组合必须由当前目标 host 支持。

硬性禁止管理者为任何 role 派发：

```text
model: gpt-5.6-sol
thinking: ultra
```

其他当前 host 支持的组合允许使用。Runtime 在每次 `create_thread` 和 `send_message_to_thread` 中发送最终解析后的完整 `model + thinking`。

模型不可用或参数不受支持时失败关闭，不静默继承管理者默认模型，也不自动换成 Max/Ultra。

## 7. Role 类型与按需策略

正式可见 role 保留：

- `executor`
- `reviewer`
- `verifier`
- `architect`
- `qa`

不再把 `manager` 作为子 role；当前主线程即 Manager/Orchestrator。

Architect 和 QA 保留现有协议与运行能力，但取消仅凭关键词自动创建。只有用户明确要求，或管理者确认需要并行、隔离或独立复核时才创建。

普通架构判断和验证设计由主管理者完成。

Team Router 只能使用可显式设置 `model/thinking` 的可见 Codex role 线程。禁止回退到 native `spawn_agent`、协作 subagent 或其他无法确认模型的隐式子代理。线程工具不可用时，管理者直接处理或报告阻塞。

## 8. Role 复用与并发

复用边界：

```text
同一 projectId + 同一 parentThreadId + 同一 role 类型
```

模型不属于 role 身份。同一个 role 可在不同 dispatch 中切换 Luna、Terra、Sol 或其他受支持组合。

每次复用必须生成新的 `taskId`、授权范围、停止条件、模型选择和 fresh search anchor，不能继承旧任务权限或旧模型设置。

复用时将可见标题更新为：

```text
<角色显示名>-<当前任务名>
```

同一任务并行创建多个同类 role 时，从第二个开始使用 `<角色显示名>2-<当前任务名>`、`<角色显示名>3-<当前任务名>`。标题不包含模型名称。

Role 忙碌由 Team Router ledger 的 pending dispatch 判定，不使用 Codex 线程的粗粒度 `active` 状态：

- 无 pending dispatch：可复用。
- 有 pending dispatch，且新任务不能独立并行：等待原 role。
- 有 pending dispatch，且新任务可独立并行：在当前运行时容量内创建新的同类 role。
- 并行 role 完成后进入同一管理者和项目的复用池。

“可独立并行”要求没有顺序依赖、共享写入冲突或权限边界冲突。不实现自动任务队列，不预创建 role，不硬编码并发数量；并发受当前运行时能力和实际独立任务数限制。

只有以下情况创建或替换 role：

- 没有可复用 role。
- 现有 role 忙碌且任务可独立并行。
- 现有 role 已归档、异常、不可用或身份不可信。
- 任务需要干净上下文或新的权限隔离。

Role 不自动归档。用户手动归档后，该 role 永不复用，需要时创建替代 role。

## 9. Registry 与旧状态兼容

当前项目级单一 `roles` 结构不能隔离同一项目中的多个管理者。新状态按 `projectId + parentThreadId` 保存 role pool。

建议结构固定为：

```text
projects[projectId].managerPools[parentThreadId].roles[role] = [roleRecord, ...]
```

每个 role 使用数组是为了容纳任务可并行时创建的多个同类线程。`roleRecord` 至少保留 `threadId`、`title`、创建/最近观察时间和 replacement metadata；忙碌状态仍从任务 ledger 推导，不复制为第二份权威状态。

设计要求：

- 新任务只复用当前 `parentThreadId` 所属的 role。
- 旧项目级 registry 保留读取兼容，仅用于恢复旧任务。
- 不做批量迁移。
- 旧项目级 role 记录不自动删除、不供新任务绑定；只有旧任务恢复路径读取它。

主管理者直做路径不写 registry。只有首次 role 派工才初始化管理者所属 role pool。

## 10. 风险等级与权限

### 10.1 等级定义

- `FAST`：低风险、机械、可确定性验证。
- `NORMAL`：普通本地任务，风险可控。
- `STRICT`：安全、金额、生产、全局规则、复杂协议或需要独立复核。
- `PACKAGE`：多个相关改动作为正式交付包，需要稳定 handoff、完整证据和 Reviewer/Verifier。

“同一任务家族”不再自动触发 `PACKAGE`。风险 `PACKAGE` 与 `publish/release package` 是不同概念，前者不得授权任何外部 gate。

### 10.2 混合判定

管理者在计划中填写：

```text
gateClass
gateReason
```

Runtime 保留硬性风险下限：安全、金额、生产、破坏性操作、全局配置、外部 gate 等不得判为 `FAST/NORMAL`。用户明确要求 `STRICT/PACKAGE` 时不得降级。

Runtime 可以提高管理者分类，但不能自动降低。普通关键词只作为提示，不单独决定流程。

模型等级与风险等级相互独立。任务可以由 Terra Medium 执行，但因权限风险进入 `STRICT`。

### 10.3 `local-package`

`local-package` 只表示允许目标范围内的本地修改与验证，不再因权限名称本身自动升级为 `STRICT`。风险分类决定由管理者直做、派 Executor，或进入 Reviewer/Verifier。

`local-package` 不包含 commit 或任何外部 gate。

## 11. Review 与 Verification

日常路径：

- Luna 机械任务：确定性命令通过即可，不额外创建 Verifier。
- Terra 普通任务：管理者执行定向检查，结果可靠即可结束。
- 验证失败、证据冲突、范围遗漏：携带已有结果升级处理，不从头重做。
- 高风险、关键交付或用户明确要求独立复核：创建独立 role。

`STRICT/PACKAGE` 强制：

```text
Executor -> Reviewer -> Verifier
```

模型建议：

- Reviewer 风险审查：Sol High。
- Verifier 只重跑明确命令：Luna Medium。
- Verifier 需要分析覆盖或解释结果：Terra Medium。
- 验证证据冲突或涉及高风险判断：Sol High。

Reviewer/Verifier 只检查风险点和验证证据，不重复整个任务。

Architect/QA 是纯按需角色，不替代 Reviewer/Verifier。

## 12. 升级与返工

- 每个任务最多一次自动模型升级。
- 每个任务最多一次自动返工，使用共享的全局 `reworkCount`。
- Luna 或 Terra 失败后，由管理者根据证据选择下一模型，不机械逐级重试。
- 升级 dispatch 必须携带已完成结果、读取过的文件、精确失败项和尚未解决的问题。
- Role 只能申请升级，不能自行创建或派发其他 role。
- 第二次仍未通过时停止并向用户报告；只有用户明确继续才再次派工。

## 13. 协议与 Runtime 数据

Manager 计划或 dispatch 至少携带：

```text
taskId
objective
scope
permission
stopCondition
gateClass
gateReason
executionClass
model
thinking
modelOverrideReason (仅覆盖时必需)
returnThreadId
sourceRoleThreadId
```

Runtime 负责：

- 解析默认模型或校验覆盖组合。
- 拒绝 Sol Ultra role dispatch。
- 记录 role 是 `new`、`reused` 还是 `replacement`。
- 记录模型、thinking、覆盖原因、升级和返工次数。
- 校验 manager-owned role pool、任务身份和 direct-return。
- 在复用 role 时刷新标题与 search anchor。

当前父线程直接产出 Manager 计划。Runtime 不再发送 `TEAM_ROUTER_PLAN` 到独立 Manager role，也不再等待独立 Manager callback。状态机跳过旧的 child-manager planning/awaiting-plan 阶段。

新 role 仍采用两步 bootstrap：先创建并取得 `sourceRoleThreadId`，再发送包含正式身份与 return contract 的 dispatch。复用 role 直接发送新 dispatch。

## 14. 错误处理

- 不受支持的模型/推理组合：`model_unavailable`，不派工。
- Sol Ultra role 请求：`model_forbidden`，不派工。
- 非默认覆盖字段不完整：`model_override_invalid`，不派工。
- Role 线程工具不可用：管理者直做或 `tool_error`，不回退 native subagent。
- Role 忙碌且任务不可并行：返回等待状态，不创建新 role。
- Role 已归档或异常：创建 non-archived replacement，并记录原因。
- 自动升级或返工预算耗尽：停止并向用户报告。
- 错任务、错 role、错 thread、过期 marker 或错误 return target：不得推进 ledger。

## 15. 路由回执

只要使用 role，最终用户回复附简短回执，例如：

```text
Executor: reused | gpt-5.6-terra | medium | upgrade: none
Verifier: new | gpt-5.6-luna | medium | rework: 0
Sol Ultra dispatched: no
```

回执覆盖：

- role 新建、复用或替换。
- 实际派发模型与 thinking。
- 非默认覆盖及原因。
- 自动升级和返工情况。
- 明确确认未派出 Sol Ultra。

当前接口没有可靠账单或 token 数据，因此不估算价格与实际额度消耗。

## 16. 实现范围

实现计划应聚焦现有模块，不增加依赖或通用插件系统。预计影响：

- `src/team_router.py`
- `src/team_router_policy.py`
- `src/team_router_state.py`
- 现有 adapter/runtime/direct-return 模块中与 role 创建、派发和状态推进直接相关的函数
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/` 下相关契约文档
- `tests/test_team_router.py` 与必要 fixtures
- README/runbook 中已经声明固定三 role 流程的段落

全局 `C:\Users\Orz\.codex\skills\codex-team-router` 只在实现通过验证且用户授权同步 gate 后，从源仓库同步。全局 `C:\Users\Orz\.codex\AGENTS.md` 不修改。

## 17. 测试计划

至少覆盖：

- 当前父线程承担 Manager，不创建独立 Manager role。
- 直做路径不创建 ledger、registry 或 role。
- 首次派工延迟创建 ledger 和 manager-owned role pool。
- 同一 `projectId + parentThreadId` 复用 role；不同 parent 不复用。
- 复用 role 时更新标题、刷新任务权限和 search anchor。
- 每次 create/send 都携带显式 `model + thinking`。
- 三档默认模型映射正确。
- 非默认覆盖缺字段时拒绝。
- `gpt-5.6-sol + ultra` 在 create 和 send 路径都被拒绝。
- 目标 host 不支持模型时失败关闭，不继承默认模型。
- Role 忙碌且可并行时创建新 role；不可并行时等待。
- Architect/QA 不再由关键词自动创建，显式按需时仍可工作。
- `local-package` 不再自动触发 `STRICT`。
- Runtime 只提高风险等级，不自动降低。
- FAST/NORMAL 不固定创建 Verifier。
- STRICT/PACKAGE 强制 Reviewer 和 Verifier。
- 自动模型升级和全局返工次数均最多一次。
- 升级只接管失败部分并保留已有证据。
- native subagent 不作为 Team Router fallback。
- 旧项目级 registry 可读取恢复，新任务使用 manager-owned pool。
- closeout 路由回执包含 role、模型、thinking、复用、覆盖、升级和 Sol Ultra 否定项。
- `git diff --check`、聚焦单元测试、skill 大小与 repo/global drift 检查通过。

## 18. 验收标准

- 普通轻量任务无需创建任何 role 即可完成。
- 需要外派时，管理者能在同一 role 上按任务切换 Luna Medium、Terra Medium 或 Sol High。
- 非默认模型覆盖可审计且不会继承旧设置。
- Team Router 无法派出 Sol Ultra，也不会回退到 native subagent。
- 同一管理者和项目复用 role；不同管理者或项目保持隔离。
- 普通任务不固定消耗 Verifier；高风险任务保留独立 Reviewer/Verifier。
- 自动升级、返工和并行创建有明确停止条件。
- Complex Task Stack 保留规划确认和逐项 scoped commit gate。
- 用户可以从最终路由回执确认实际使用的模型和 role 生命周期。
- 旧任务可恢复，新任务不再依赖项目级单一 role registry。
