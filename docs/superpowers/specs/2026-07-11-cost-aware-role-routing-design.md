# Team Router Cost-Aware Role Routing Design

- 日期：2026-07-11
- 状态：四轮 review findings 已合并，待用户复核
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

显式成本感知模型入口：

```text
你作为管理者，按 Luna Medium、Terra Medium、Sol High 成本感知路由完成 <目标>
```

该表达表示：

- 进入 Manager Mode。
- 授权管理者在目标范围内直接完成符合本设计边界的小任务。
- 标准入口授权管理者直做和准备 role 路由，但不等于用户明确请求具体 role 模型；如果任务需要派工，必须在任何 ledger、标题、heartbeat 或线程操作前取得显式成本感知模型授权。
- 显式成本感知模型入口授权按需创建、复用、在 Luna Medium、Terra Medium、Sol High 之间切换和升级可见 role，并形成 `modelRoutingAuthorization`；受控覆盖仍需逐次提供完整覆盖字段。
- 允许目标所需的本地最小修改与验证。
- 不包含 commit、push、PR、merge、deploy 或其他外部 gate。
- 目标包含“只读 / review / 检查”等零写入语义时，仍保持零写入。
- 当任务实际进入派工时，授权把当前父线程标题规范化为 `管理者-Team Router <任务名>`，并按本文规则规范化该任务使用的 role 标题；纯直做或纯 review 不为标题而产生额外状态变更。

只说“进入 Manager Mode”只进入分析与方案阶段，不创建 role。

Manager Mode 不检查或限制当前主管理者使用的模型。本设计的 Sol Ultra 限制只作用于管理者创建或派发的 role。

### 3.1 跨回合授权寿命

`你作为管理者，完成 <目标>` 建立一个仅限该目标的 `taskAuthorizationPackage`。它在同一父线程、同一 taskId、同一 scope/permission/stopCondition 内持续到任一 terminal status（`done/blocked/malformed_callback/tool_error/missing_role/abandoned`）、用户取消或明确切换角色。只有显式成本感知模型入口或用户逐次明确指定具体模型组合时，授权包才包含 `modelRoutingAuthorization`。

授权包有效期间，后续 `继续 / 处理 / go / do it` 可以继续已经批准的管理者直做；只有授权包已经包含 `modelRoutingAuthorization` 时，才可继续已批准的 role 创建/复用、模型切换和 dispatch，不需要逐个 role 再次确认。这些短回复不能补出缺失的模型授权、创建新目标、扩大文件/项目范围、改变 permission、增加高风险动作，或打开 commit/push/PR/merge/deploy 等独立 gate。

裸“进入 Manager Mode”或没有 `taskAuthorizationPackage` 的 Manager Mode 保持 proposal-only：短回复只能细化方案和准备 dispatch metadata，不能创建线程、写 registry/ledger 或实现。任务进入 terminal status 后，短回复不能复活旧授权包；恢复必须由用户明确重启或重新授权目标。

## 4. Complex Task Stack 组合语义

入口：

```text
你作为管理者，走复杂任务流程完成 <目标>
```

该表达同时触发 Manager Mode 和 Complex Task Stack。

规划 gate：

- 核对当前真相、拆分任务、风险和验收标准。
- 仅在独立证据确有价值时派只读 role。
- 组合入口本身授权必要的 `DISPATCH_ONLY` 副作用：创建/复用可见只读 role、规范化标题、写 Team Router registry/ledger；这些状态写入不得扩大目标或权限。
- 不修改项目工作区文件，不 commit，不执行任何 `WORKSPACE_WRITE` 或外部 gate。
- 如果目标同时明确写有“只读 / review / 检查 / 不要改”等零写入边界，第 3 节的零写入规则优先：不得创建 role 或写 registry/ledger，除非用户另行明确授权这些可见线程状态副作用。
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

默认映射只在 `modelRoutingAuthorization` 已明确列出 Luna Medium、Terra Medium、Sol High 时生效。没有该授权时，Runtime 可以完成 Manager direct，但若 route closure 需要任何 role，必须在持久化 plan 或触发线程/状态副作用前返回 `model_authorization_required`；不得用 Skill 语义替代用户对具体模型的明确选择。

`executionClass` 是每次 role request 的字段，不是整个 task 共用的单值。一个 `STRICT` task 可以分别使用 Terra Executor、Sol Reviewer 和 Luna/Terra/Sol Verifier。

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

当前 adapter 没有独立的模型能力查询接口。Runtime 只做字段、默认映射、覆盖完整性和 Sol Ultra 禁止项校验；目标 host 的线程工具是模型组合可用性的最终权威。工具拒绝必须规范化为 `model_unavailable`，且不得推进 dispatch ledger。

新 role 的首个 `create_thread` 只执行机械 bootstrap（等待正式身份和 dispatch），默认固定使用 `gpt-5.6-luna + medium`；取得 `sourceRoleThreadId` 后，正式 `send_message_to_thread` 再使用该 role request 解析出的模型。这样不会用 Sol High 消耗一个空 bootstrap 回合。Bootstrap prompt 必须包含 `requestId/projectId/parentThreadId/role` 并明确禁止提前执行任务，使 creation intent 可在崩溃恢复时通过 `list_threads` 定向发现和接管，避免重复创建。Bootstrap 模型同样显式记录和失败关闭。

## 7. Role 类型与按需策略

正式可见 role 保留：

- `executor`
- `reviewer`
- `verifier`
- `architect`
- `qa`

不再把 `manager` 作为子 role；当前主线程即 Manager/Orchestrator。

Role 常量按 workflow version 分层，避免破坏旧任务：

```text
ROLE_NAMES = manager | executor | reviewer | verifier | architect | qa
LEGACY_CORE_ROLE_NAMES = manager | executor | verifier
V2_DELEGATED_BASE_ROLE_NAMES = executor
V2_CONDITIONAL_ROLE_NAMES = reviewer | verifier | architect | qa
```

`manager` 继续存在于 parser、direct-return、legacy registry 和 version 1 contract 中，但 version 2 的 role resolution/create path 永远不创建 Manager。Version 2 是否需要 Verifier 由 route closure 决定，不属于固定 base role。`protocol_contract_snapshot()` 必须分别暴露 version 1 和 version 2 的 role/state/marker contract，不能用一套 `CORE_ROLE_NAMES` 混合表达。

Architect 和 QA 保留现有协议与运行能力，但取消仅凭关键词自动创建。只有用户明确要求，或管理者确认需要并行、隔离或独立复核时才创建。

普通架构判断和验证设计由主管理者完成。

Team Router 只能使用可显式设置 `model/thinking` 的可见 Codex role 线程。禁止回退到 native `spawn_agent`、协作 subagent 或其他无法确认模型的隐式子代理。线程工具不可用时，管理者直接处理或报告阻塞。

## 8. Role 复用与并发

复用边界：

```text
同一 hostId + 同一 targetFingerprint + 同一 projectId + 同一 parentThreadId + 同一 role 类型
```

`targetFingerprint` 由 Runtime 在解析真实结构化 `target` 后生成：使用标准库对 canonical JSON `{"hostId": hostId, "target": target}`（UTF-8、键排序、紧凑分隔符）计算 SHA-256。它必须为非空稳定值；调用方提供的值只能在与 Runtime 计算结果一致时接受。Fingerprint 必须在任何 manager-pool ledger/registry 写入前完成，不能把 `None`、空字符串或 `targetFingerprint` 本身传给线程工具。

模型不属于 role 身份。同一个 role 可在不同 dispatch 中切换 Luna、Terra、Sol 或其他受支持组合。

每次复用必须生成新的 `taskId`、授权范围、停止条件、模型选择和 fresh search anchor，不能继承旧任务权限或旧模型设置。

复用时将可见标题更新为：

```text
<角色显示名>-<当前任务名>
```

同一任务并行创建多个同类 role 时，从第二个开始使用 `<角色显示名>2-<当前任务名>`、`<角色显示名>3-<当前任务名>`。标题不包含模型名称。

Role 忙碌由 State Controller 的权威 claim 判定，不使用 Codex 线程的粗粒度 `active` 状态。任务 ledger 保留请求和恢复证据，但不作为并发分配时需要跨文件猜测的第二份权威：

- 无 active claim：可复用。
- 有 active claim，且新任务不能独立并行：等待原 role。
- 有 active claim，且新任务可独立并行：尝试创建新的同类 role。
- 并行 role 完成后进入同一管理者和项目的复用池。

“可独立并行”要求没有顺序依赖、共享写入冲突或权限边界冲突。不实现自动任务队列，不预创建 role，不硬编码并发数量。当前工具不提供容量查询；Runtime 只在任务可并行时尝试 `create_thread`，容量拒绝规范化为等待状态，不连续重试。

Role 分配必须通过一个 State Controller 临界区完成：锁定当前 manager pool、重新检查 claim、选择 role、写入 `claim.taskId/requestId/claimedAt`，然后才允许发送正式 dispatch。需要新建线程时，先在临界区写入同一 `requestId` 的 creation intent，释放锁后调用 `create_thread`，再重新进入临界区完成 roleRecord/claim 或清理 intent；不得在外部工具调用期间长期持有状态锁。`parallelAllowed` 必须从 resolved plan 贯穿 role request、分配和 reserve helper，不能在 adapter 层丢失；共享写入、顺序依赖或权限冲突存在时始终为 `false`。

Creation intent 只能提供可审计恢复锚点，当前 `create_thread` 接口没有幂等键，因此 Runtime 不得声称跨进程 exactly-once。恢复时只接受 `list_threads + read_thread` 唯一验证出的完整 bootstrap identity；零候选或多候选均不得自动再次 `create_thread`。零候选经过一次有界恢复检查后转为 terminal `tool_error`，reason 为 `creation_outcome_unknown`，并把 request identity 保存到 ledger recovery observation；只有用户明确授权人工清理/重试后才可产生新的 create attempt。这样禁止自动重复创建，也避免非终态 `busy` 永久卡死。未来只有 host 提供以 `requestId` 为键的幂等创建后，才允许自动重试零候选 intent。

发送失败时释放 claim。每个 role 的有效最终回传被捕获后立即释放该 role 的 active claim，task ledger 保留 `preferredThreadId` 供返工优先重用；如果原 role 已被其他任务占用，返工等待或按并行规则创建新 role。任务进入任一 terminal status 时兜底释放所有残余 claim/creation intent。不得仅按时间自动清除 claim；stale recovery 必须同时核对关联 task ledger 已终止或明确 abandoned。

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

每个 role 使用数组是为了容纳任务可并行时创建的多个同类线程。`roleRecord` 至少保留 `threadId`、`hostId`、`targetFingerprint`、`title`、创建/最近观察时间、replacement metadata 和唯一权威 `claim`。

设计要求：

- 新任务只复用当前 `parentThreadId` 所属的 role。
- Registry schema 升为 version 2，同时保留旧项目级 `roles`，仅用于恢复 version 1 任务。
- 新 task ledger 写入 `workflowVersion: 2`；缺少该字段的旧 ledger 视为 version 1。
- Version 1 非终态任务继续原有 child Manager、`TEAM_ROUTER_PLAN` 和项目级 role 流程，直到终态；不得中途切换为 version 2 状态机。
- 不做批量迁移。
- 旧项目级 role 记录不自动删除、不供新任务绑定；只有旧任务恢复路径读取它。

加载器必须在 normalize 覆盖 schema version 之前保留原始版本/`workflowVersion`，否则无法选择兼容分支。Version 2 registry 可以同时包含 legacy `roles` 与新的 `managerPools`。

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
requestedGateClass
gateReason
```

Runtime 先验证用户授权和 side-effect package，再进行风险分类。分类只能收紧流程，不能创造缺失权限：全局配置/skill、破坏性操作、生产、真实 API、账号、commit 或外部 gate 没有对应明确授权时直接阻塞，不能通过改判 `STRICT` 继续。

Runtime 保留硬性风险下限：安全、金额、生产、破坏性操作、全局配置、外部 gate，以及 Team Router 自身 runtime/policy/process/permission/safety/role protocol 修改不得判为 `FAST/NORMAL`。用户明确要求 `STRICT/PACKAGE` 时不得降级。

Runtime 可以提高管理者分类，但不能自动降低。普通关键词只作为提示，不单独决定流程。

模型等级与风险等级相互独立。任务可以由 Terra Medium 执行，但因权限风险进入 `STRICT`。

### 10.3 规划流水线与回调后升级

Version 2 在持久化 plan 或创建任何 role 前，必须按固定顺序完成：

```text
解析用户目标与 taskAuthorizationPackage
-> 验证 side-effect permission
-> 计算 effectiveGateClass（应用硬性风险下限）
-> 根据 effectiveGateClass 和显式角色需求计算 route closure
-> 若 route 非空，验证 modelRoutingAuthorization
-> 补齐并校验闭包后每个 roleRouting
-> 持久化 resolved plan
-> claim/create/send
```

Ledger 保存用户/管理者提出的 `requestedGateClass` 和 Runtime 最终采用的 `effectiveGateClass`，不得只覆盖成一个无法审计的值。

Executor callback、Reviewer/QA findings 或验证证据出现新风险时，Runtime 在进入 Manager acceptance 或下一 role 前重新运行 permission、effective gate 和 route closure。若 FAST/NORMAL 升为 STRICT/PACKAGE，状态不得进入 `manager_acceptance_pending`；父 Manager 必须为新增 Reviewer/Verifier 补齐 `roleRouting`，更新 resolved plan 后再继续派工。风险升级不能增加权限或打开新 gate。

### 10.4 `local-package`

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

### 11.1 Route matrix 与依赖闭包

| 场景 | 正式路径 |
|---|---|
| FAST/NORMAL，管理者直做 | Manager direct，无 ledger |
| FAST/NORMAL，需要 Executor | Executor -> Manager acceptance |
| 显式 Architect | Architect -> Executor -> 后续适用的 acceptance/review 路径 |
| 显式 Reviewer | Executor -> Reviewer -> Verifier |
| 显式 QA | Executor -> QA -> Verifier |
| STRICT/PACKAGE | Executor -> Reviewer -> Verifier |
| STRICT/PACKAGE + Architect/QA | Architect? -> Executor -> Reviewer -> QA? -> Verifier |

Reviewer 和 QA 都不是最终验收者；任一被选择时必须同时选择 Verifier。Architect 不替代 Executor。Runtime 根据 route matrix 计算依赖闭包，不能创建孤立 Reviewer/QA 后直接结束。依赖闭包必须在 plan 持久化和任何 role 创建之前完成；`routeRoles` 保存闭包后的有序角色列表，且每个角色都必须有对应 `roleRouting[role]`，缺失时返回 `plan_invalid` 而不是猜测模型。

### 11.2 Manager acceptance

FAST/NORMAL 使用 Executor 但不需要独立 Verifier 时，Executor callback 后进入 `manager_acceptance_pending`。当前父线程写入结构化 `managerAcceptance`：

```text
result: pass | needs_rework | blocked
acceptedAt
callbackReceipt
scopeChecked
evidenceChecked
riskBoundaryChecked
remainingRisks
```

只有 gate 仍为 FAST/NORMAL、route 不包含 Reviewer/QA/Verifier、Executor final callback 有效且验证证据满足计划时，Manager `pass` 才能把状态推进为 `done` 并生成 closeout。`needs_rework` 消耗共享的单次自动返工预算；`blocked` 终止任务。Executor 不能自行把任务标记为 `done`。

Manager acceptance 的 closeout 必须复用 Verifier 路径的用户可见契约，至少包含：

```text
acceptedBy: manager
changed
verified
notDone
risks
nextGate
remainingTodos
routingReceipt
compoundingDecision: recorded | skipped
reason
```

`compoundingDecision` 只报告决定，不自动写长期经验文件。Manager acceptance 进入 `done` 后停止并删除该 task 的 heartbeat；closeout file 写入、commit 和任何外部 gate 仍需独立授权。

## 12. 升级与返工

- 每个任务最多一次自动模型升级。
- 每个任务最多一次自动返工，使用共享的全局 `reworkCount`。
- Luna 或 Terra 失败后，由管理者根据证据选择下一模型，不机械逐级重试。
- 升级 dispatch 必须携带已完成结果、读取过的文件、精确失败项和尚未解决的问题。
- Role 只能申请升级，不能自行创建或派发其他 role。
- 第二次仍未通过时停止并向用户报告；只有用户明确继续才再次派工。

## 13. 协议与 Runtime 数据

Version 2 Manager plan 由当前父线程直接持久化，至少携带：

```text
taskId
taskAuthorizationPackageId
modelRoutingAuthorization (仅 routeRoles 非空时必需)
objective
scope
permission
stopCondition
requestedGateClass
effectiveGateClass
gateReason
routeRoles
parallelAllowed
parallelConflicts
roleRouting[role].executionClass
roleRouting[role].model (仅覆盖时必需)
roleRouting[role].thinking (仅覆盖时必需)
roleRouting[role].modelOverrideReason (仅覆盖时必需)
```

每次 resolved role request/dispatch 再写入：

```text
role
requestId
threadId/sourceRoleThreadId
returnThreadId
hostId
targetFingerprint
executionClass
requestedModel
requestedThinking
modelOverrideReason (仅覆盖时存在)
bootstrapModel/bootstrapThinking (仅新建 role 时存在)
creationAccepted (仅新建 role 时存在)
dispatchAccepted
upgradedFrom (发生升级时存在)
```

Runtime 负责：

- 解析默认模型或校验覆盖组合。
- 拒绝 Sol Ultra role dispatch。
- 记录 role 是 `new`、`reused` 还是 `replacement`。
- 在每个 role request 上记录 requested model/thinking、create/send 各自的工具接受结果、覆盖原因、升级和返工次数。
- 校验 manager-owned role pool、任务身份和 direct-return。
- 在复用 role 时刷新标题与 search anchor。

当前父线程直接产出 Manager 计划。Version 2 Runtime 不再发送 `TEAM_ROUTER_PLAN` 到独立 Manager role，也不再等待独立 Manager callback。

Version 2 主状态路径固定为：

```text
manager direct: no ledger
delegated: created -> planned -> awaiting_architect_review? -> dispatched -> awaiting_callback
post-callback: reviewing? -> awaiting_qa_review? -> verifying? | manager_acceptance_pending -> done
rework: needs_rework -> dispatched (全任务最多一次自动返工)
terminal: done | blocked | malformed_callback | tool_error | missing_role | abandoned
```

`planning/awaiting_plan/plan_unreachable/roles_ready` 只属于 version 1 兼容流程。Version 2 不得复用这些状态表达不同语义。

新 role 仍采用两步 bootstrap：先创建并取得 `sourceRoleThreadId`，再发送包含正式身份与 return contract 的 dispatch。复用 role 直接发送新 dispatch。

## 14. 错误处理

- 不受支持的模型/推理组合：`model_unavailable`，不派工。
- 需要 role 但缺少具体模型路由授权：`model_authorization_required`，不写 ledger、不改标题、不设置 heartbeat、不派工。
- Sol Ultra role 请求：`model_forbidden`，不派工。
- 非默认覆盖字段不完整：`model_override_invalid`，不派工。
- 目标 host 拒绝模型组合：规范化为 `model_unavailable`；失败 request 在对应调用记录 `creationAccepted: false` 或 `dispatchAccepted: false`，不得进入 awaiting 状态。
- Role 线程工具不可用：只有任务仍独立满足 FAST/NORMAL 直做边界时才允许管理者直做；其他情况返回 `tool_error`，不回退 native subagent。
- Role 忙碌且任务不可并行，或并行创建被容量限制拒绝：返回等待状态，不连续创建/重试。
- Role 已归档或异常：创建 non-archived replacement，并记录原因。
- 新 role 已创建但正式 dispatch 失败：保留为 unclaimed idle role，释放 task claim，并报告 `tool_error`；不得伪造已派工状态。
- 自动升级或返工预算耗尽：停止并向用户报告。
- 错任务、错 role、错 thread、过期 marker 或错误 return target：不得推进 ledger。

## 15. 路由回执

只要使用 role，最终用户回复附简短回执，例如：

```text
Executor: reused | requested gpt-5.6-terra | medium | dispatchAccepted: true | upgrade: none
Verifier: new | bootstrap gpt-5.6-luna medium | requested gpt-5.6-luna medium | creationAccepted: true | dispatchAccepted: true | rework: 0
Sol Ultra dispatched: no
```

回执覆盖：

- role 新建、复用或替换。
- 请求的模型与 thinking，以及 create/send 是否分别接受。
- 非默认覆盖及原因。
- 自动升级和返工情况。
- 明确确认未派出 Sol Ultra。

当前接口没有可靠账单、token 或最终计费模型数据，因此不估算价格与实际额度消耗，也不把 requested model 表述为 `actualModel`。只有线程工具将来明确返回实际模型时，才可另行记录 `actualModel`。

## 16. 实现范围

实现计划应聚焦现有模块，不增加依赖或通用插件系统。预计影响：

- `src/team_router.py`
- `src/team_router_policy.py`
- `src/team_router_state.py`
- `src/team_router_status.py`
- 现有 adapter/runtime/direct-return 模块中与 role 创建、派发和状态推进直接相关的函数
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/` 下相关契约文档
- `tests/test_team_router.py` 与必要 fixtures
- README/runbook 中已经声明固定三 role 流程的段落

全局 `C:\Users\Orz\.codex\skills\codex-team-router` 只在实现通过验证且用户授权同步 gate 后，从源仓库同步。全局 `C:\Users\Orz\.codex\AGENTS.md` 不修改。

同步前后的验收分开：

- 实现验证 gate：repo 测试、文档契约、SKILL 大小通过；`team_router_skill_sync_check.py --check` 允许且预期返回 `status: mismatch`，但差异只能来自本实现授权修改的 repo skill 文件。
- 独立全局同步 gate：用户授权后运行 sync，再要求 check 返回 `status: match`。

## 17. 测试计划

至少覆盖：

- 当前父线程承担 Manager，不创建独立 Manager role。
- Version 1 使用 `LEGACY_CORE_ROLE_NAMES`，Version 2 使用 delegated base + route closure；snapshot 同时暴露两套 contract。
- 标准“完成 X”授权包可在同一任务内跨回合继续；裸 Manager Mode 的短回复仍为 proposal-only。
- 标准入口不会隐式取得具体模型授权；显式成本感知模型入口才允许 Luna/Terra/Sol 默认映射和后续派工。
- 父线程标题使用 `管理者-Team Router <任务名>`，且仅在已授权派工时规范化。
- 直做路径不创建 ledger、registry 或 role。
- 首次派工延迟创建 ledger 和 manager-owned role pool。
- 同一 `projectId + parentThreadId` 复用 role；不同 parent 不复用。
- Role 复用同时校验 `hostId + targetFingerprint`。
- Role claim 在并发选择中互斥；send 失败和 terminal/abandoned 状态正确释放。
- `parallelAllowed` 从 resolved plan 贯穿到 reserve helper；共享写入、顺序依赖或权限冲突时不能并行创建。
- 新 role 使用 Luna Medium bootstrap，正式 dispatch 再切换到该 request 的模型。
- Bootstrap prompt 带稳定 request identity；creation intent 恢复不会重复创建同一 role。
- Role 最终回传后释放 active claim，并保留 preferredThreadId 供返工优先重用。
- 复用 role 时更新标题、刷新任务权限和 search anchor。
- 每次 create/send 都携带显式 `model + thinking`。
- 默认 Manager plan 只要求 executionClass；resolved request 才要求 requested model/thinking。
- 同一 STRICT task 的 Executor/Reviewer/Verifier 可解析为不同模型组合。
- 三档默认模型映射正确。
- 非默认覆盖缺字段时拒绝。
- `gpt-5.6-sol + ultra` 在 create 和 send 路径都被拒绝。
- 目标 host 不支持模型时失败关闭，不继承默认模型。
- Role 忙碌且可并行时创建新 role；不可并行时等待。
- Creation intent 崩溃恢复可按 bootstrap request identity 接管唯一候选；零候选或多候选转 `creation_outcome_unknown`/`tool_error` 并禁止自动重试创建。
- `targetFingerprint` 从真实 target + hostId 稳定计算，空值、调用方不一致值和跨 target/host 复用均被拒绝。
- Architect/QA 不再由关键词自动创建，显式按需时仍可工作。
- `local-package` 不再自动触发 `STRICT`。
- 风险分类不能补出缺失授权；未授权全局/生产/外部动作在派工前阻塞。
- Runtime 只提高风险等级，不自动降低。
- Plan 按 permission -> effective gate -> route closure -> roleRouting -> persist 顺序执行。
- Callback 后风险升级会重算 route；升级为 STRICT 时禁止 Manager acceptance，并补齐 Reviewer/Verifier routing。
- FAST/NORMAL 不固定创建 Verifier。
- FAST/NORMAL Executor callback 可通过结构化 Manager acceptance 到达 `done`，且不能由 Executor 自验收。
- Manager acceptance closeout 与 Verifier closeout 字段等价，并停止 task heartbeat。
- STRICT/PACKAGE 强制 Reviewer 和 Verifier。
- Reviewer/QA 依赖闭包强制 Verifier；Architect 不替代 Executor。
- Route closure 后的每个 role 都必须有独立 `roleRouting`；缺失时不得创建线程。
- Complex 规划 gate 遇到显式零写入语义时不创建 role/ledger，除非用户另行授权线程状态副作用。
- Version 1 非终态任务继续旧 Manager 流程；Version 2 使用新状态机。
- 自动模型升级和全局返工次数均最多一次。
- 升级只接管失败部分并保留已有证据。
- native subagent 不作为 Team Router fallback。
- 旧项目级 registry 可读取恢复，新任务使用 manager-owned pool。
- closeout 路由回执包含 role、requested model/thinking、creation/dispatch accepted、复用、覆盖、升级和 Sol Ultra 否定项。
- `git diff --check`、聚焦单元测试和 skill 大小通过；全局同步前预期受控 mismatch，同步后才要求 match。

## 18. 验收标准

- 普通轻量任务无需创建任何 role 即可完成。
- 取得显式成本感知模型授权后，管理者能在同一 role 上按任务切换 Luna Medium、Terra Medium 或 Sol High。
- 非默认模型覆盖可审计且不会继承旧设置。
- Team Router 无法派出 Sol Ultra，也不会回退到 native subagent。
- 同一管理者和项目复用 role；不同管理者或项目保持隔离。
- 普通任务不固定消耗 Verifier；高风险任务保留独立 Reviewer/Verifier。
- 自动升级、返工和并行创建有明确停止条件；未知创建结果不会自动重试或永久保持非终态 busy。
- Complex Task Stack 保留规划确认和逐项 scoped commit gate。
- 用户可以从最终路由回执确认请求模型、工具接受结果和 role 生命周期；不把它误报为最终计费模型。
- 旧任务可恢复，新任务不再依赖项目级单一 role registry。
- 标准完成授权包仅在原 task scope 内跨回合持续，terminal 后不会被短回复复活。
