# Functional Module Map

本项目同时包含轻量 Skill 合同、可恢复只读运行时和显式隔离写入运行时。下面按职责列出当前功能模块，避免把所有能力都归为一个“workflow”。

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
| Installation contract | `skill/installation/contract.py` | active manifest、history record、digest 和 rollback change Schema |
| Installation filesystem | `skill/installation/filesystem.py` | source discovery、安全目标解析、原子写入、backup 与 Git identity |
| Installation planner | `skill/installation/planner.py` | 零写入 diff、managed drift 阻断和 exact `plan_digest` |
| Installation apply | `skill/installation/apply.py` | 精确计划重验、before backup、原子写入与 manifest-last 发布 |
| Installation status | `skill/installation/status.py` | active identity、managed drift、history 一致性与 unmanaged file 报告 |
| Installation rollback | `skill/installation/rollback.py` | 一步 rollback、backup 校验与中断续跑 |
| Installation facade | `skill/installation/manager.py` | 保持稳定的 public import surface |
| Installation CLI | `skill/install_cli.py` | `install-plan/apply/status/rollback` 显式命令面 |

## 后续个人模块顺序

### P1：Candidate / Known-Good

目标不是增加新的 workflow 节点，而是把日常使用版本与实验版本分开：

```text
candidate install
→ real routing smoke / normal task observation
→ explicit promote-known-good
→ later candidate can reactivate the frozen known-good payload
```

需要在 installation history 中保存可重新激活的完整 payload，而不只保存被覆盖文件的 before backup。

### P1：Live Routing Evidence

增加手工、显式、低成本的真实探针记录：

- 固定 case allowlist；
- 最大调用数与绝对超时；
- 记录 Skill commit、安装 manifest digest、Codex 版本和结构化 route metadata；
- 永不进入普通 push/PR CI；
- 不调用 Writer，不修改目标仓库。

### P2：Personal Doctor

把当前分散的只读状态检查组合成一个个人诊断入口：

- active install identity 与 drift；
- policy consistency；
- 最近一次 routing smoke 身份；
- paused Human Gate；
- terminal/incomplete run；
- orphan Writer worktree 与明确 cleanup 命令。

### P2：按触碰范围拆分大型模块

不做一次性重写。只有修改某一复杂职责时，才把对应 invariant 连同测试一起抽离，例如 bounded loop executor、resume validation 或 completion reconciliation。功能正确性与回滚能力优先于文件行数。
