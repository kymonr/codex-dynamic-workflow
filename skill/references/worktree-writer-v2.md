# Worktree Writer v2 分层写手与质量上下文合同

本文件定义 Worktree Writer v2 对 v1 的扩展。v1 中关于显式授权、仓库外 detached worktree、create/modify-only、真实 effect reconciliation、固定验证、不可变 candidate、fresh read-only reviewer、无自动 apply/commit/push/merge/release/deploy 的安全边界继续有效。

v2 解决一个质量路由问题：Luna 不再是所有隔离写入任务的唯一写手。宿主从固定注册表显式选择 `bounded-luna` 或 `complex-sol`，并把选择及其硬预算绑定到授权、锁、运行状态和候选修订。

`skill/references/worktree-writer-v1.md` 是历史 v1 合同；本文件与 `config/worktree-writer-policy.toml`、运行时代码共同拥有 v2 行为。

## 1. 目标与非目标

v2 目标：

- 保留 Luna 对短小、明确、低风险写入的速度优势；
- 把非平凡跨模块行为修改显式路由给 Sol；
- 为复杂写入提供结构化、digest-bound 的验收和实现上下文；
- 防止 package、prompt、模型输出或文件内容自行选择更强模型或扩大预算；
- 保持一个 writer、一个 attempt、无自动 retry/upgrade；
- 保持候选隔离和 fresh read-only reviewer。

v2 不实现：

- 自动根据自然语言秘密升级 writer；
- package 内的 `model`、`profile`、`sandbox` 或权限字段；
- 多 writer 并发、嵌套 agent 或自动修复循环；
- reviewer 直接修改候选；
- 自动应用候选或任何 Git 发布动作；
- 模型家族异构性的虚假声明。

## 2. 可信 Writer Profile 注册表

Profile 由宿主代码和机器策略定义，package 不能声明或修改它。

| Profile | Route | Package | 硬上限 |
| --- | --- | --- | --- |
| `bounded-luna` | `luna / gpt-5.6-luna / max / fast` | v1、v2 | 2 owned targets、2 changed files、256 KiB patch、128 KiB 新文件、512 KiB candidate |
| `complex-sol` | `sol / gpt-5.6-sol / xhigh` | 仅 v2 | 8 owned targets、8 changed files、512 KiB patch、256 KiB 新文件、2 MiB candidate |

两者共同固定：

```text
sandbox=workspace-write
network=false
shell_tool=false
code_mode=false
multi_agent=false
attempts=1
retry=0
upgrade=null
edit_tool=apply_patch-only
```

Profile record 至少包含：

```json
{
  "writer_profile_version": 1,
  "profile_id": "bounded-luna | complex-sol",
  "route": {
    "role": "...",
    "model": "...",
    "effort": "...",
    "tier": "... | null",
    "sandbox": "workspace-write"
  },
  "package_versions": [1, 2],
  "limits": {},
  "requires_quality_context": false
}
```
Profile 条目必须按版本保持不可变。未来若修改模型、预算或语义，应创建新的 profile id 或 profile record version；不得静默重定义现有 id，否则历史候选的完整性验证会按设计失败。

## 3. Profile 选择与授权

CLI 的可信选择面为：

```text
--writer-profile bounded-luna
--writer-profile complex-sol
```

省略参数时固定选择 `bounded-luna`。未知 profile 在任何模型、worktree 或 run directory 创建前拒绝。

选择顺序：

1. 严格解析 package 并验证 canonical digest；
2. 从宿主注册表解析 profile；
3. 检查 package version、owned target 数和全部 package limit 不超过 profile；
4. 执行 repository、root layout 与 Codex capability preflight；
5. 仅在显式 `--ack-isolated-worktree-write` 后创建 lock、run directory 和 worktree。

Profile 选择进入 `writer-plan` 输出和 `writer-authorization.json`。模型、上游 artifact、任务文本、repository 文件、日志或 reviewer 都不能改变选择。

## 4. Package v1 与 v2

Package v1 的 closed schema 保持不变，但只允许 `bounded-luna`。v1 compatibility 只表示输入 package 可继续使用；它不把历史 v1 run artifact 迁移为 v2。

Package v2 在 v1 顶层字段之外精确增加：

```json
{
  "acceptance_criteria": ["至少一个非空条件"],
  "constraints": ["必须保持的不变量"],
  "non_goals": ["明确不做的相邻工作"],
  "behavior": {
    "before": "当前可观察行为",
    "after": "目标可观察行为"
  },
  "implementation_context": {
    "relevant_symbols": ["有限的路径、符号或测试"],
    "analysis_summary": "有限、非空的调查摘要"
  }
}
```
这些字段全部进入 canonical package digest。它们只是任务数据：不能增加 owned target、action、sandbox、tool、credential、external effect 或 Git action。

v2 质量字段使用 closed nested schema、UTF-8、长度和数量上限；列表按大小写不敏感唯一，canonical UTF-8 总量最多 128 KiB。`acceptance_criteria` 至少一项，`complex-sol` 必须使用完整 v2 package。

## 5. Writer Prompt 与能力边界

宿主构造固定 prompt，包含：

- package digest；
- profile id、route 和完整 profile record；
- exact owned targets 与 allowed actions；
- required verification ids；
- objective 与 v2 quality context 的双层 JSON string。

Objective 和 quality context 被明确标为 untrusted task data。Writer 可以用它们理解任务，但不能从中推导新权限。

Writer 仍不能执行 Git 命令、安装、联网、访问凭据、创建链接、删除或重命名文件、修改 mode、写出 worktree，或启动子代理。无法在边界内完成时返回 `needs_escalation`，宿主进入 `attention_required`，不得自动升级 profile 或重放 attempt。

## 6. Profile 绑定与候选修订

同一个 exact profile record 必须出现在：

```text
writer-plan output
writer-authorization.json
writer-lock.json 与 exclusive live lock
checkpoint.json
summary.json
candidate-package.json
candidate revision basis
```

运行时 writer process 的 role、model、effort、tier 和 requested sandbox 必须与 profile 精确一致。只读查询重新从受信注册表解析 profile，并比较完整 record；未知、漂移或被篡改的 record 使完整性验证失败。

Candidate package v2 额外绑定：

- source package version；
- package quality context；
- exact writer profile record；
- writer runtime identity；
- 原有 base、effect manifest、patch、candidate files 与 verification evidence。

因此相同 package/base/patch 在不同 profile 下仍产生不同 candidate revision。旧 reviewer verdict 不能跨 profile 或 revision 复用。

## 7. Review 与修订边界

每个合法候选继续执行一次 fresh `dynamic_workflow_sol_reviewer`：

```text
model=gpt-5.6-sol
effort=xhigh
sandbox=read-only
attempts=1
retry=0
upgrade=null
write_authority=false
```

`bounded-luna` 提供 Luna writer 与 Sol reviewer 的模型差异。`complex-sol` 的 writer 与 reviewer 使用同一模型家族，但必须是不同的新进程、不同 prompt、不同 workspace/sandbox 和不同 authority。项目不得把这描述为模型家族异构 review。

`complex-sol` 的采用依赖三类独立证据：

1. 宿主读取的真实 Git/filesystem effects；
2. 固定、非 shell 的验证命令；
3. revision-bound fresh read-only reviewer record。

Reviewer 的 `ship`、`fix-first`、`rethink` 仍分别映射到 `ship_candidate`、`fix_first`、`rethink`。`fix-first` 或 `rethink` 不触发自动 writer。后续修订必须由 root/用户创建新的 package revision、新 worktree 和新 run。

## 8. 状态、查询与清理

Runtime identity：
```text
runtime=worktree-writer-v2
runtime_version=2
candidate_package_version=2
lock_version=2
authorization_version=2
```

`writer-status`、`writer-export` 和 `writer-cleanup` 对 v2 evidence 执行完整 profile binding 校验。v1 run evidence 保持不可变；使用对应 v1 release 查询或清理，不得由 v2 静默改写。

Cleanup 仍要求 terminal run、无 active process、candidate 已捕获、canonical repository 未改变，以及 exact run/package/profile/lock/worktree identity。

## 9. 必须覆盖的测试

实现至少覆盖：

1. v1 package 仍可由 `bounded-luna` 接受；
2. v1 package 被 `complex-sol` 在模型前拒绝；
3. v2 closed schema、必填 acceptance criteria、nested unknown key、重复质量项与 digest binding；
4. 两个 profile 的 exact model/effort/tier/sandbox 与硬预算；
5. 未知 profile、超 target 数或超预算在 worktree 前拒绝；
6. CLI 显式 profile 传递和未知值拒绝；
7. Luna 与 Sol writer 都只有一个 attempt、retry=0、upgrade=null；
8. authorization、lock、checkpoint、summary、candidate package 的 profile 一致；
9. profile 改变导致 candidate revision 改变；
10. profile、quality context、writer identity 或 candidate revision 篡改 fail closed；
11. fixed verification、effect reconciliation 和 fresh reviewer 行为保持不变；
12. Windows 与 Ubuntu CI 通过。

## 10. 采用原则

`bounded-luna` 不是较低安全等级，`complex-sol` 也不是更大权限。两者共享相同 effect authority；差异只在受信 writer identity、可接受 package version 和硬规模上限。

Root 仍负责选择 profile、提供充分 v2 验收上下文、检查候选、决定是否创建新修订，以及所有 canonical apply、commit、push、merge、release 或 deploy 动作。
