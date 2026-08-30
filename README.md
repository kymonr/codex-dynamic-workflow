# Codex Dynamic Workflow

面向 Codex v2 native subagent 的轻量编排 Skill。默认目标不是搭建复杂工作流，而是把普通任务拆成少量、窄而不重叠的子代理分支，由主线程统一整合。

```text
Multi-agent first
Workflow only when needed
Writer only when explicitly authorized
```

## 默认模式：Simple Swarm

普通分析、审核、研究、设计、诊断和规划，默认使用轻量 Simple Swarm：

```text
拆成 2–6 个窄分支
→ 并行派给 native subagent
→ 收集结果
→ 主线程去重、解决冲突、验收并回答
```

隐式触发至少需要两个依赖已就绪、可独立交付且不大面积重叠的分支。只有一个隐式分支时留在主线程；用户显式调用 `$dynamic-workflow` 或明确要求 subagent 时，可以派一个有界分支。

每个分支通常只负责一个问题、一个模块或 1–3 个主要文件。主线程不重复调查仍在运行的子代理范围。普通 Simple Swarm 不创建 Workflow IR、checkpoint、Human Gate、bounded loop、正式 evidence package 或 Worktree Writer run。

详细规则见 `skill/references/simple-swarm.md`。

## 高级模式按需开启

- **Managed Workflow**：明确需要 checkpoint/resume、Human Gate、bounded loop、条件分支、长时间恢复或可复现运行产物时才启用。
- **Agent Fleet**：用户明确指定 Agent Fleet，或自然要求深度审核、全面检查、对抗审核、多代理复核、仓库深审等需要相互质疑和独立复现的任务时启用。只使用 4、6、8 个界面可见的原生子代理：分别为 `3 Luna + 1 Sol`、`5 Luna + 1 Sol`、`6 Luna + 2 Sol`。Luna 负责发现、质疑、复现；Sol 复核证据、严重度、共同盲点和最终结论。
- **Writer Workflow**：只有用户明确授权隔离 Worktree Writer candidate 时才启用。v2 只接受含验收、约束、非目标、行为和实现上下文的 package v2，并固定使用 Sol/high Writer；随后由 fresh read-only Sol/xhigh reviewer 审核。CLI 和 package 都不能选择或降级 Writer。
- **Independent Review**：只有用户明确要求独立、全新、第二方或最终验收时才创建 dedicated reviewer。

## 当前路由

- Spark / Explorer：窄而明确、低风险、可本地核对的只读调查。
- Luna：默认处理普通只读委派任务；用户显式指定 Luna 写入时，可作为唯一 scoped writer。
- Sol：默认处理 native / delegated 写入，以及复杂、跨模块、高影响、架构/安全判断或最终技术判断。
- Grok：不属于 native subagent 路由，也不是 writer、native reviewer 或自动 fallback；只有用户明确要求时，才在 candidate 冻结后创建独立可见的只读二审对话任务。

Simple Swarm 禁止嵌套委派，最多只允许一个 native writer。默认 writer 是 Sol；用户显式指定受支持的 native 模型时优先，显式 Luna 可承担 scoped writing。Grok 始终没有写入权限。

机器可读的角色、Simple Swarm、原生 Agent Fleet、资源限制与路径合同统一位于 `config/workflow-policy.toml`；Worktree Writer 合同位于 `config/worktree-writer-policy.toml`。一致性检查会核对 4/6/8 的 Luna/Sol 配比、界面可见性、Root/Sol 责任和其他运行边界。

## 执行路径

Simple Swarm 的 native subagent 是默认路径。只有明确需要 checkpoint/resume、Human Gate、bounded loop、可复现 CLI 日志、逐任务产物目录、JSON summary 或真实 `codex exec` 探针时，才进入 Managed Workflow 或显式 CLI runner。

CLI runner 是有界只读路径，不提供 workspace write、Git 写入、任意命令或自动模型升级。使用跨平台入口：

```powershell
py -3.12 skill\cli.py run `
  --spec D:\path\workflow.json `
  --allowed-root D:\path\bounded-project `
  --ack-external-model-export
```

```bash
python3.12 skill/cli.py run \
  --spec /path/workflow.json \
  --allowed-root /path/bounded-project \
  --ack-external-model-export
```

中断后的显式恢复：

```powershell
py -3.12 skill\cli.py resume `
  --run-dir D:\path\to\runs\example-run `
  --allowed-root D:\path\bounded-project `
  --ack-external-model-export
```

`run` 会持续写入 `events.jsonl` 和 `checkpoint.json`。显式 `resume` 会核对计划摘要，只恢复未完成节点；已成功节点通过内容寻址 artifact 复用，不重新把完整结果塞入主线程或下游 prompt。

## 资源和结果边界

每次运行始终存在有限上限：

- 单节点结构化输出；
- 单节点日志；
- 整次运行产物；
- 注入下游 prompt 的上游结果累计字节；
- 单条事件日志。

默认值和不可突破的硬上限记录在 `config/workflow-policy.toml`。超过限制会终止相关节点；超量日志会截断到上限，超量结构化输出会被丢弃，并保留最后一个仍可安全写入的 checkpoint，不会无限增长磁盘或上下文。

所有成功结果都会生成 SHA-256 内容寻址 artifact。小结果仍可内联；超过累计 inline budget 时，下游只收到带摘要、哈希和精确只读路径的 `UPSTREAM_ARTIFACT_REFERENCE`，避免重复复制大对象。

## 原生 Agent Fleet

Agent Fleet 不再是后台 CLI 或 package runtime，而是 Codex 界面中可见的原生多代理深审流程：

```text
Root 冻结范围和 Git 状态
→ Luna 独立发现
→ Root 去重并分配 F-001 等 finding ID
→ Luna 逐项质疑
→ Luna 独立复现
→ Sol 复核证据、风险和遗漏
→ Root 公开采用、拒绝或标记 UNKNOWN
```

自动规模：

- 4 个：`3 Luna + 1 Sol`，用于小而明确、风险较低的深审；
- 6 个：`5 Luna + 1 Sol`，作为跨文件或跨模块深审的默认规模；
- 8 个：`6 Luna + 2 Sol`，用于安全、数据、权限、并发、安装器、发布或大型架构等高风险范围。

启动前先公开 workflow、总数、Luna/Sol 配比、阶段分工和选择原因，然后直接启动。每个成员都是 fresh、顶层、唯一命名、`fork_turns=none`、只读且界面可见的 native subagent；禁止嵌套、代理间直接通信、仓库写入和隐藏的 Fleet `codex exec` 进程。

证据优先于人数。被独立复现的严重问题不能被多数“未发现”抵消。Sol 没有单方面否决权，但 Root 必须逐项公开处理每个重要 Sol 意见：采用、给出代码/测试/复现依据后拒绝，或标记 `UNKNOWN`。无法解决的 Luna/Sol 重大冲突必须保留为 `UNKNOWN`，不能包装成审核通过。

Agent Fleet 不再提供机器化 candidate digest、JSON records、run directory、evidence manifest 或离线状态重建。明确需要 checkpoint/resume 或正式持久化证据时，使用 Managed Workflow。完整合同见 `skill/references/agent-fleet.md`。

## Workflow IR v3

仓库已加入声明式 Workflow IR v3 基础：

```powershell
py -3.12 skill\cli.py validate-ir --spec workflow-v3.json
```

当前静态 `agent` 节点仍可编译成 v2 只读 DAG。v3 可信控制流 runtime 支持满足 Bounded Loop v1 完整合同的受限 `loop`；旧式或不完整的 `loop` 声明仍只在声明层通过校验，执行时会被明确拒绝，不会被静默迁移。详细合同见 `skill/references/workflow-ir.md` 与 `skill/references/bounded-loop-v1.md`。

## 仓库结构

```text
config/workflow-policy.toml      机器可读路由、原生 Agent Fleet、限制与路径合同
config/worktree-writer-policy.toml Worktree Writer v2 profile 与安全合同
config/agents/                   配套 native agent 角色模板
integration/                     工作区 AGENTS.md 接入片段
skill/VERSION                    人工可读的严格语义版本
skill/versioning.py              显式版本递增与原子 VERSION 更新
skill/SKILL.md                   Dynamic Workflow Skill 主规则
skill/references/simple-swarm.md 默认轻量多代理合同
skill/references/agent-fleet.md  4/6/8 原生可见 Agent Fleet 合同
skill/cli.py                     Managed Workflow、Writer 与个人运维 CLI 入口
skill/install_cli.py             个人版本与安装管理 CLI
skill/installation/              安装合同、安全文件操作、计划、状态与单步回滚
skill/platform_paths.py          本地状态、产物与 worktree 路径解析
skill/runner.py                  有界、可恢复的只读 DAG runner
skill/runtime/                   schema、artifact、limits、state、Workflow IR 模块
skill/scripts/                   路由 smoke 与合同检查
skill/tests/                     离线回归测试
docs/personal-operations.md      个人版本、安装、状态检查与回滚操作
docs/module-map.md               功能模块地图与明确排除项
```

完整职责边界见 `docs/module-map.md`。

`config/agents/grok_writer.toml.disabled` 仅作为停用状态的历史参考，不应复制、重命名或启用。显式 Grok 二审通过独立可见的只读对话任务完成，不使用该角色文件。

`config/agents/ox.toml.disabled` 仅作为停用状态的参考，不会被 Codex 自动加载。

如需重新创建 Ox 角色，先确认 `opencode-zen/x-preview-f-free` 当前可用，并确认父任务与第三方子任务的传输兼容性。然后将 `config/agents/ox.toml.disabled` 复制为 `$CODEX_HOME/agents/ox.toml`。该操作只注册角色；除非另行修改路由策略，否则 Dynamic Workflow 的普通只读委派仍使用 Luna，未显式指定 native 模型的 delegated 写入仍使用 Sol。

## 版本与安装

当前人工可读版本只来自 `skill/VERSION`。文件接受 `MAJOR.MINOR.PATCH` 或 `MAJOR.MINOR.PATCH-rc.N`。需要下一个版本时单独执行：

```powershell
py -3.12 skill\cli.py version-bump --source-root .
```

```bash
python3.12 skill/cli.py version-bump --source-root .
```

当前为 RC 时默认递增 RC；当前为正式版时默认递增 patch。也可显式使用 `--prerelease`、`--release`、`--patch`、`--minor` 或 `--major`。该命令只修改 `skill/VERSION`，不会安装、提交 Git、创建 tag 或发布 release。

确定版本并审阅源码后，生成零写入安装计划：

```powershell
py -3.12 skill\cli.py install-plan --source-root .
```

```bash
python3.12 skill/cli.py install-plan --source-root .
```

检查输出中的 `skill_version`、`source_commit`、`source_dirty`、文件动作、`blocked` 和 `plan_digest`。然后只应用该精确摘要：

```powershell
py -3.12 skill\cli.py install-apply `
  --source-root . `
  --expected-plan-digest <SHA256> `
  --ack-install
```

```bash
python3.12 skill/cli.py install-apply \
  --source-root . \
  --expected-plan-digest <SHA256> \
  --ack-install
```

安装器会复制完整 `skill/` 载荷和 `config/agents/` 根目录下启用的 `.toml`，记录版本、Git identity 与逐文件 SHA-256，先备份被替换或删除的目标，并在任何目标写入前发布 active transaction pointer，最后发布 active manifest。它不会复制 `.disabled` agent，不会删除未管理文件，也不会修改任何工作区 `AGENTS.md`。

安装后检查实际身份：

```powershell
py -3.12 skill\cli.py install-status
```

重点字段为 `skill_version`、`source_commit`、`payload_digest`、`install_id` 和 `rollback_available`。版本号便于人工查看，commit 与 payload digest 用于精确确认实际内容。若返回 `apply_incomplete` 或 `rollback_incomplete`，按输出中的 pending/current install ID 执行同一个 `install-rollback`；中断 apply 会恢复到 apply 前状态，不自动继续原计划。

需要退回紧邻的上一状态时，使用 status 返回的当前 `install_id`：

```powershell
py -3.12 skill\cli.py install-rollback `
  --expected-install-id <INSTALL_ID> `
  --ack-rollback
```

只保留当前安装对应的一份 rollback snapshot。成功回退后恢复出的版本会显示 `rollback_available: false`，不能继续链式回退；下一次成功安装会重新建立一份单步 snapshot。

工作区接入仍需人工把 `integration/AGENTS.dynamic-workflow.md` 合并进对应 `AGENTS.md`，不要覆盖已有项目规则。完整操作与状态含义见 `docs/personal-operations.md`。

仍可手工复制 `skill/` 和启用的 agent TOML，但手工路径不会生成安装 manifest、逐文件身份、before backup 或一步 rollback。

## 本地路径

运行状态默认保存在平台合适的用户状态目录，worktree 默认保存在系统临时目录，不再要求固定盘符或用户名。以下变量可以显式覆盖：

| 变量 | 用途 |
|---|---|
| `CODEX_HOME` | Codex 配置、Skill 与 agent 根目录；未设置时使用 `~/.codex` |
| `DYNWF_HOME` | Dynamic Workflow 本地状态和当前 rollback snapshot 根目录 |
| `DYNWF_RUNS_ROOT` | CLI run artifacts 根目录 |
| `DYNWF_WORKTREE_ROOT` | 隔离 worktree 根目录 |
| `DYNWF_MAX_RESULT_BYTES` | 单节点输出上限，不能超过硬上限 |
| `DYNWF_MAX_LOG_BYTES` | 单节点日志上限，不能超过硬上限 |
| `DYNWF_MAX_RUN_ARTIFACT_BYTES` | 单次运行总产物上限 |
| `DYNWF_MAX_UPSTREAM_INLINE_BYTES` | 每个下游 prompt 的累计上游内联预算 |
| `DYNWF_MAX_EVENT_BYTES` | 单条事件上限 |

优先级为“spec 显式限制 → 环境变量 → 默认值”。共享配置和文档中不得提交个人用户名、固定 Node 安装路径或固定盘符临时目录。

## 验证

在仓库根目录运行：

```powershell
py -3.12 skill\scripts\check_policy_consistency.py
py -3.12 skill\scripts\routing_smoke.py
py -3.12 -m unittest discover -s skill\tests -v
```

```bash
python3.12 skill/scripts/check_policy_consistency.py
python3.12 skill/scripts/routing_smoke.py
python3.12 -m unittest discover -s skill/tests -v
```

GitHub Actions 会在 Windows 和 Linux 的 Python 3.12 上运行编译检查、policy consistency、routing smoke 和完整离线单元测试。

离线路由 smoke 只能验证 evaluator 和静态路由合同，不能证明某次任务实际使用了哪个模型、推理强度或 service tier。运行态身份应以新任务产生的原生结构化元数据为准。`routing_smoke.py --live` 会创建真实任务，只应在得到明确授权并指定 case 时使用。

## Trusted Workflow IR 控制流

Workflow IR v3 可通过 `skill/cli.py run-ir` 执行可信的只读 `agent`、`map`、`verify`、`loop`、`reduce`、`conditional` 和 `human_gate` 节点，并用 `resume-ir` 从 checkpoint 显式恢复。动态 child、manifest、事件和结果均受既有资源预算与内容寻址 artifact 边界约束。

Executable node kinds: `agent`, `map`, `verify`, `loop`, `reduce`, `conditional`, `human_gate`.
Validated-only node kinds: none.

Only `loop` instances that fully satisfy the Bounded Loop v1 contract are executable. Legacy `loop` declarations remain instance-level validated-only and are explicitly rejected at execution.

`max_tokens` 目前是 advisory 预算字段，因为 Codex CLI usage 仍来自可能缺失的日志数据；它不是硬停止条件。`soft_timeout_seconds` 与 `hard_timeout_seconds` 继续作用于每个 agent 进程。可选的 `workflow_timeout_seconds` 另外建立 whole-workflow 绝对 deadline；`resume-ir` 不会重置该 deadline，human gate 暂停时间也计入。IR 本身不是授权，不能扩大写入、凭据、发布或破坏性权限。

## Conditional 与 Human Gate

受限 `conditional` 只使用 exact node ID、JSON Pointer 与封闭运算符；`unknown` 会返回 root。未选分支及其后继默认传播为 `skipped`，不会执行。只有显式声明 `dependency_policy: "join"` 的汇合节点才能消费一边 `succeeded`、一边 `skipped` 的依赖；所有依赖都为 `skipped` 时，汇合节点也会保持 `skipped`。

human gate 使用不可变 contract 与原子 exclusive-create decision record。运行进入 `paused` 后，只有 `gate-decide` 再配合显式 `resume-ir` 才继续。`actor` 与 `source` 只是未经认证的审计标签；gate decision 只是数据，不授予 workspace write、凭据、Git、发布、合并、部署或破坏性权限。

reference repository audit 的 closeout 保持两条显式、互斥的结果路径：

```text
discover-modules → audit-modules → verify-audits
                                      ├→ summarize-audit
                                      └→ choose-verification-path
                                           ├→ prepare-clean-candidate ─┐
                                           └→ prepare-blocker-report ──┴→ review-gate (join)
                                                                          └→ choose-gate-outcome
                                                                               ├→ record-accepted → finalize-accepted
                                                                               └→ record-rejected → finalize-rejected
```

`record-accepted` 与 `record-rejected` 都显式接收 `choose-gate-outcome`、`review-gate` 和 `summarize-audit`；它们的严格对象合同包含 `decision`（`approve`/`reject`）、`summary`、`evidence[]` 与 `next_actions[]`。每个 finalizer 只接收对应的 record，并在该合同上增加 `status`（`accepted`/`rejected`）与 `uncertainty[]`。未选中的 record 及其 finalizer 会按依赖传播为 `skipped`，不会创建 task 目录。

## 计划预览与运行状态

在启动模型前，可使用 `plan-ir` 验证并预览完整控制流；它不会访问 `workdir`、调用模型或写入运行目录：

```powershell
py -3.12 skill\cli.py plan-ir `
  --spec examples\reference-repository-audit.workflow-ir.json
```

运行后可使用 `run-status` 只读检查 checkpoint、summary 与 gate 元数据，不会推进节点：

```powershell
py -3.12 skill\cli.py run-status `
  --run-dir D:\path\to\one-run
```

`checkpoint.json` 是状态事实来源；如果 `summary.json` 与 checkpoint 不一致，命令会明确报告 mismatch，不会静默覆盖。完整命令合同、输出字段和 reference workflow 说明见 `skill/references/operations.md`。
