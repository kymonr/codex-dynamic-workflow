# Agent Fleet v1 合同

Agent Fleet v1 是 Dynamic Workflow 的高级只读多代理模式。它为一个冻结候选或明确研究对象调度 **4–12 个 fresh Luna 子代理**，通过发现、质疑和独立复现建立 finding graph，再由宿主决定是否需要一个 fresh Sol/xhigh 做最终裁决。

```text
固定验证与候选冻结
  ↓
2–8 Luna discovery
  ↓
1–2 Luna challenge
  ↓
1–2 Luna reproduction
  ↓
宿主去重、冲突识别与升级判断
  ├─ clean low-risk → accept
  └─ blocker / conflict / UNKNOWN / high risk → fresh Sol/xhigh
```

Agent Fleet 不授予写权限，不让代理自由聊天，不按多数票决定正确性，也不把 Sol 当成运行失败兜底。

## 1. 何时选择

使用 Agent Fleet，当用户明确要求以下任一能力：

- 4–12 个子代理组成的 fleet、team、council 或 panel；
- adversarial review、red/blue review、相互质疑或独立复现；
- 超过普通 Simple Swarm 宽度的多维审核；
- competing hypotheses、architecture council、test matrix、repository audit 或 research synthesis；
- 先由多个 Luna 检查，再依据证据决定是否调用 Sol。

普通的 2–6 个不重叠分支仍使用 Simple Swarm。单个复杂判断直接使用 Sol。需要 checkpoint/resume、Human Gate 或长时间恢复时使用 Managed Workflow。

## 2. 规模与阶段

Fleet 大小只能是 4–12，默认 6。宿主按大小确定阶段配额：

| 总数 | Discovery | Challenge | Reproduction |
|---:|---:|---:|---:|
| 4 | 2 | 1 | 1 |
| 5 | 3 | 1 | 1 |
| 6 | 4 | 1 | 1 |
| 7 | 4 | 2 | 1 |
| 8 | 5 | 2 | 1 |
| 9 | 6 | 2 | 1 |
| 10 | 6 | 2 | 2 |
| 11 | 7 | 2 | 2 |
| 12 | 8 | 2 | 2 |

所有角色必须不同。第一轮不是把同一 prompt 复制 12 次；每个 discovery 角色拥有独立 focus。每个支持规模都包含 challenge 与 reproduction。Finding 提出者不能挑战或复现自己的 finding，且每份 challenge/reproduction 记录必须恰好覆盖宿主分配的全部 finding ID。

## 3. 固定路由

所有 Fleet 成员固定为：

```text
role=luna
model=gpt-5.6-luna
effort=max
tier=fast
sandbox=read-only
fresh=true
attempts=1
retry=0
nested_agents=0
```

条件裁决者固定为：

```text
role=fleet_sol_arbiter
model=gpt-5.6-sol
effort=xhigh
sandbox=read-only
fresh=true
attempts=1
retry=0
nested_agents=0
```

Package、仓库内容、其他代理记录和模型输出都不能选择模型、修改 effort、扩大 sandbox 或授权写入。CLI 不提供 `--model`、`--effort` 或代理间消息参数。`requested_sandbox=read-only` 来自宿主构造的命令；当前 backend 不提供独立的 per-process sandbox attestation，因此 `observed_sandbox=unknown` 必须如实保留，不能把请求值冒充观察值。

## 4. Presets

v1 支持七个只读 preset：

- `adversarial-review`：正确性、回归、测试证据、反方论证、API、安全、生命周期与平台风险；
- `competing-hypotheses`：并行验证不同根因并尝试推翻领先假设；
- `architecture-council`：约束、API、数据、运维、安全、性能、迁移和简化方案；
- `security-red-blue`：攻击身份、输入、边界与供应链，同时检查防御控制和可观测性；
- `test-matrix`：单元、集成、错误路径、性质、兼容、平台、并发和性能测试；
- `repository-audit`：CLI、runtime、安全、持久化、测试、文档、打包和平台；
- `research-synthesis`：一手证据、反证、方法、统计、时间线、假设、复现与综合质疑。

这些 preset 共享相同的可信运行边界、条件 Sol 规则和 finding lifecycle，但使用不同的 discovery 角色池。没有 preset 能绕过证据聚合或把 Luna 多数当作最终决定。

## 5. Finding lifecycle

Fleet 不使用多数投票。每个问题经历：

```text
proposed
  ↓
challenged
  ↓
reproduced | refuted | unresolved
  ↓
accepted | discarded | conflict | unresolved
```

Finding ID 由类别、规范化摘要和位置生成。完全相同的问题会合并证据和 proposer，但 proposer 数量不是票数。

一个可复现的 P1 即使只由 1 个代理发现，也不能被另外 11 个 clean 结果覆盖。相反，没有证据的重复主张不会因为出现次数多而自动成立。

## 6. 条件 Sol

以下任一**语义证据**触发 fresh Sol/xhigh：

- 任一代理存在 `UNKNOWN`；
- accepted P1/P2；
- finding 出现事实冲突；
- finding 无法确认也无法推翻；
- risk tag 涉及 public API、schema、migration、安全、凭据、权限、并发、状态机、恢复、持久化、发布、sandbox 或完整性。

固定验证失败、候选变化、identity mismatch、stale revision、非空 effects、格式错误、进程失败或证据损坏属于执行证据无效，直接 fail closed 返回 root，不能触发 Sol。

只有同时满足以下条件才能跳过 Sol：

- 固定验证全部通过；
- candidate revision 稳定且所有进程/记录证据有效；
- 无 `UNKNOWN`；
- 无强制高风险标签；
- 无 accepted P1/P2；
- 无 conflict 或 unresolved finding。

Accepted P3 可以形成 `accepted_with_notes`，不必单独调用 Sol。

Sol 只裁决 surviving evidence，不重新从头审核整个仓库。代理身份错误、stale revision、非空 effects、格式错误或运行证据损坏必须直接 fail closed 返回 root，不能用 Sol 掩盖。

## 7. Candidate 与固定验证

Package 精确绑定：

- repository full name；
- expected Git HEAD；
- changed-file set；
- objective、acceptance、scope、exclusions 和 risk tags；
- 固定非 shell 验证命令；
- candidate、patch、untracked file、agent output 和 log 上限。

宿主从 live Git 捕获 tracked patch 与 UTF-8 untracked content，拒绝 binary/NUL、路径逃逸、symlink、Windows reparse/junction 和 changed-file 漂移，并计算：

```text
candidate_revision=sha256:<canonical candidate material digest>
```

绝对 `repository_root` 仅用于本机读回，不进入 revision basis；相同 Git identity、patch、status 与 untracked bytes 在不同 checkout 路径下得到相同 revision。

固定验证在任何模型调用之前执行。每轮结束后重新捕获候选；任何变化进入 `attention_required`。

## 8. 证据与完整性

运行目录保存 resolved package、candidate package、schedule、verification evidence、各阶段 records、finding graph、aggregation、可选 Sol arbitration、event journal、summary 和最终 evidence manifest。

`fleet-status` 不调用模型，也不修改证据。它重新验证：

- evidence manifest 与每个文件的 SHA-256；
- package digest；
- candidate revision；
- deterministic schedule；
- terminal summary identity。

v1 不提供 retry、resume、自动修复、写入、commit、push、merge、release 或 deploy。

## 9. 与 Claude 风格对抗审核的关系

Agent Fleet 采用相似的并行专业化、相互质疑和独立验证思想，但不是对任何未公开内部实现或固定代理数量的复制。项目自己的可信合同是 4–12 个 fresh 子代理、宿主介导的结构化 artifact、无自由消息、无多数投票和条件 Sol 裁决。
