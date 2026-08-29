# Functional Module Map

本项目同时包含轻量 Skill 合同、可恢复只读运行时、显式隔离写入运行时和个人安装维护工具。下面按职责列出当前功能模块，避免把所有能力都归为一个“workflow”。

## 入口与模式选择

| 模块 | 主要文件 | 职责 |
|---|---|---|
| Skill 主合同 | `skill/SKILL.md` | root 权限、模式选择、委派与结果采用规则 |
| Simple Swarm | `skill/references/simple-swarm.md` | 普通任务的 2–6 个窄分支、无嵌套、默认只读 |
| 路由策略 | `config/workflow-policy.toml`, `config/agents/*.toml` | Spark、Luna、Sol、reviewer 的模型、effort、tier 与访问边界 |
| 工作区接入 | `integration/AGENTS.dynamic-workflow.md` | 把 Skill 触发与授权边界合并进具体工作区 |
| Portable CLI router | `skill/cli.py` | 把显式命令路由到各独立功能面，不扩大权限 |

## Managed Workflow 功能

| 模块 | 主要文件 | 职责 |
|---|---|---|
| v2 DAG runner | `skill/runner.py` | 有界只读 task DAG、artifact、checkpoint、resume 与进程收口 |
| Workflow IR | `skill/runtime/workflow_ir.py` | IR v3 Schema、静态校验、节点预算投影与可信编译 |
| 控制流调度器 | `skill/runtime/control_flow.py` | `agent/map/verify/loop/reduce/conditional/human_gate` 执行与恢复 |
| 条件原语 | `skill/runtime/condition.py` | exact node ID、JSON Pointer 和封闭运算符 |
| Human Gate | `skill/runtime/human_gate.py`, `skill/gate_cli.py` | 不可变 waiting contract、exclusive-create decision 与显式继续 |
| 操作查询 | `skill/ops_cli.py` | `plan-ir` 与 `run-status` 的零模型只读检查 |
| Preset compiler | `skill/swarm_presets.py` | 固定、版本化、预算受限的 design/review/repo presets |
| Auto Planner | `skill/auto_planner.py` | 一个 Luna 只从固定 preset registry 中选择，不生成任意 DAG |

## 运行时完整性基础

| 模块 | 主要文件 | 职责 |
|---|---|---|
| Artifact store | `skill/runtime/artifacts.py` | SHA-256 内容寻址结果和受限下游引用 |
| Limits | `skill/runtime/limits.py` | 节点结果、日志、事件、运行总量与 inline budget |
| State store | `skill/runtime/state_store.py` | 原子 checkpoint、版本化 events 和摘要身份 |
| Path safety | `skill/runtime/path_safety.py` | containment、symlink/junction/reparse 与 Windows 路径身份 |
| Run lease | `skill/runtime/run_lease.py` | 同一运行的跨进程排他锁 |
| Deadline | `skill/runtime/deadline.py` | 单调检查后的绝对 workflow deadline |
| Schema contract | `skill/runtime/schema_contract.py` | provider envelope 与本地可执行 Schema 子集 |

## Writer Workflow 功能

| 模块 | 主要文件 | 职责 |
|---|---|---|
| Writer contract | `skill/writer_contract.py` | owned targets、允许动作、验证 argv 和不可扩大权限 |
| Effect reconciliation | `skill/writer_effects.py` | 从真实 Git/filesystem effects 判定越界、删除、binary、LFS 等 |
| Writer process | `skill/writer_process.py` | 固定命令面、禁 shell/network/agents 与进程收口 |
| Candidate review | `skill/writer_review.py` | fresh read-only reviewer 对冻结 candidate 给出终态结论 |
| Writer runtime/CLI | `skill/writer_runtime.py`, `skill/writer_cli.py` | plan、run、status、export 和显式 cleanup |

## Personal Operations 功能

| 模块 | 主要文件 | 职责 |
|---|---|---|
| Semantic version | `skill/VERSION`, `skill/versioning.py` | 严格 SemVer、显式 bump 类型和原子版本文件更新 |
| Installation contract | `skill/installation/contract.py` | active manifest、单步 rollback record、active transaction pointer 和 change Schema |
| Installation filesystem | `skill/installation/filesystem.py` | source discovery、规范 POSIX 路径、Windows target identity、原子写入、backup 与 pointer I/O |
| Installation planner | `skill/installation/planner.py` | 零写入 diff、版本身份、managed drift 阻断和 exact `plan_digest` |
| Installation apply | `skill/installation/apply.py` | 精确计划重验、before backup、原子写入、manifest-last 发布与单步历史截断 |
| Installation status | `skill/installation/status.py` | `skill_version`、源码身份、payload、managed drift 和 rollback 可用性 |
| Installation transaction | `skill/installation/transaction.py` | before/after 状态识别、未完成 apply 恢复和 manifest 幂等切换 |
| Installation rollback | `skill/installation/rollback.py` | 只回退一步、未完成 apply 回收、rollback 续跑和 snapshot 清理 |
| Installation facade | `skill/installation/manager.py` | 保持稳定的 public import surface |
| Personal CLI | `skill/install_cli.py` | `version-bump` 与 `install-plan/apply/status/rollback` 显式命令面 |

## 当前明确不包含

本轮个人维护功能刻意不建立完整发布系统：

- 没有 candidate / known-good 状态机；
- 没有可选择的长期安装历史；
- 没有自动 Git commit、tag 或 release；
- 没有自动修改工作区 `AGENTS.md`；
- 没有把 live routing probe 放进普通 CI；
- 没有因为文件较大而进行一次性运行时重构。

只有单步 rollback 在实际使用中不足时，才重新讨论长期版本保留或 known-good 激活。

## 后续仍可单独讨论的模块

### Live Routing Evidence

可增加手工、显式、低成本的真实探针记录：固定 case allowlist、最大调用数与绝对超时，并绑定 Skill 版本、安装 payload、Codex 版本和结构化 route metadata。该能力不进入普通 push/PR CI，也不调用 Writer。

### Personal Doctor

可把 active install identity、managed drift、policy consistency、最近 routing smoke、paused Human Gate、incomplete run 和 orphan Writer worktree 汇总为一个只读诊断入口。

### 按触碰范围拆分大型模块

不做一次性重写。只有修改某一复杂职责时，才把对应 invariant 连同测试一起抽离，例如 bounded loop executor、resume validation 或 completion reconciliation。功能正确性与回滚能力优先于文件行数。
