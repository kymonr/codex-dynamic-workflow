# Bounded Loop v1 合同

本文件定义 Workflow IR v3 中 `loop` 的第一版可信执行合同。它是有限、只读、可恢复的收敛循环，不执行模型生成的 Python、JavaScript、Shell、表达式、选择器或 DAG。

在实现和 RC 完成前，`loop` 仍保持 validated-only；本合同不得被文档描述为已经可执行。

## 目标

Bounded Loop v1 用于以下确定性流程：

```text
一个已成功的初始结果
  ↓
迭代 1：修订 agent → 独立 verifier
  ├─ accept  → loop succeeded
  ├─ reject  → 下一轮
  └─ unknown → needs_escalation
  ↓
重复，直到 accept、停滞、deadline 或 max_iterations
```

模型只在声明的只读 agent 叶节点中工作。循环次数、顺序、agent ID、输入 identity、预算、停止条件、停滞判断、checkpoint 和最终状态均由可信宿主控制。

## IR 声明

可执行 loop 使用现有顶层 `loop` 节点，并引用普通顶层 `agent` 节点作为**模板**：

```json
{
  "id": "converge-design",
  "kind": "loop",
  "depends_on": ["initial-design"],
  "config": {
    "max_iterations": 3,
    "no_progress_limit": 1,
    "body": ["revise-template", "verify-template"],
    "stop_when": "verification_accept"
  }
}
```

模板节点：

```json
{
  "id": "revise-template",
  "kind": "agent",
  "depends_on": ["converge-design"],
  "config": {
    "profile": "luna",
    "access": "read_only",
    "prompt": "根据受限循环状态修订候选。状态：{{loop_state}}",
    "output_schema": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "candidate": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["candidate", "changes"]
    }
  }
}
```

最后一个模板必须是 verifier，并使用运行时固定的 `accept | reject | unknown` Schema：

```json
{
  "id": "verify-template",
  "kind": "agent",
  "depends_on": ["converge-design"],
  "config": {
    "profile": "luna",
    "access": "read_only",
    "prompt": "独立验证本轮候选。状态：{{loop_state}}",
    "output_schema": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "verdict": {"type": "string", "enum": ["accept", "reject", "unknown"]},
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["verdict", "summary", "evidence"]
    }
  }
}
```

## 可执行合同

一个 loop 只有同时满足以下条件才进入 executable 集合；否则继续作为 validated-only 节点被明确拒绝执行：

1. `stop_when` 精确等于 `verification_accept`。
2. `depends_on` 恰好包含一个已声明的初始结果节点。
3. `body` 包含 2..8 个大小写不敏感唯一的顶层节点 ID。
4. 每个 body 节点存在、kind=`agent`、且 `depends_on` 精确等于 `[loop-id]`。
5. 每个 body prompt 都包含 `{{loop_state}}`；可额外包含 `{{iteration}}`。
6. 最后一个 body 节点的 `output_schema` 精确等于固定 verifier Schema。
7. `max_iterations` 不超过 `budgets.max_iterations`。
8. `no_progress_limit` 为 1..5 的整数，默认 1。
9. 一个模板节点最多归属于一个 loop。
10. 模板节点不能是 conditional 分支入口，不能被 loop 之外的任何节点依赖，也不能作为 map/verify/reduce 的 source。
11. loop 不能包含另一个 loop、map、verify、reduce、conditional 或 human gate；v1 的 body 只允许顺序 agent 模板。

旧格式（例如 `body` 指向不满足上述所有权合同的普通节点，或 `stop_when="verified"`）继续被严格校验但不可执行，不能被静默迁移。

## 循环状态与数据流

每个 step 收到一个宿主生成、CAS-backed 的 `loop_state`：

```json
{
  "loop_version": 1,
  "loop_node_id": "converge-design",
  "iteration": 1,
  "max_iterations": 3,
  "initial": "<初始结果或 artifact reference>",
  "previous_candidate": null,
  "previous_feedback": null,
  "current_steps": [],
  "history": []
}
```

- `initial` 来自 loop 唯一的 `depends_on`。
- 同一轮中，后续 step 会看到前面 step 的输出。
- 下一轮会看到上一轮候选和 verifier feedback。
- `history` 只保存受限摘要与 SHA-256 identity，不无界复制完整 prompt 或结果。
- 任何大输入继续通过 `UPSTREAM_ARTIFACT_REFERENCE` 传递。
- `depends_on` 只控制外层调度；loop step 的数据注入必须由运行时显式替换 `{{loop_state}}`。

## 稳定身份与预算

每个迭代 step 的 agent ID 由以下字段确定性派生：

```text
loop node ID + iteration index + step index + template node ID
```

同一 resolved IR、同一 iteration 和同一步骤必须生成相同 ID；不同迭代不能冲突。ID 必须满足现有 40 字符限制和 Windows 大小写不敏感唯一语义。

`plan-ir` 的保守上界必须计算：

```text
非模板 static agent/reduce claims
+ map child upper bound
+ verify child upper bound
+ Σ(loop.max_iterations × len(loop.body))
```

loop 模板节点本身不单独计入 static claim，因为它们不会作为顶层 agent 启动。投影超过 `budgets.max_agents` 时必须在模型启动前 fail closed。

## 停止语义

最后一个 step 的 verifier 输出决定本轮结果：

- `accept`：loop `succeeded`，`stop_reason=verification_accept`。
- `reject` 且仍有迭代额度：进入下一轮。
- `reject` 且已达到上限：loop `needs_escalation`，`stop_reason=iteration_limit`。
- `unknown`：loop `needs_escalation`，`stop_reason=verification_unknown`。
- 任一步骤执行失败、取消或 needs_escalation：loop 传播该非成功状态，不启动后续 step。

### 确定性停滞检测

每轮以倒数第二个 body step 的完整 JSON 输出计算 canonical SHA-256，作为 progress digest。

- digest 连续重复达到 `no_progress_limit` 时，loop 进入 `needs_escalation`。
- `stop_reason=no_progress`。
- 不允许由模型自行声明“有进展”覆盖 digest 判断。
- verifier 的 `reject` 不能绕过停滞检测。

## Whole-workflow deadline

新增可选预算字段：

```json
"workflow_timeout_seconds": 7200
```

合同：

1. 范围 60..172800 秒；省略时保持现有行为，不改变旧 IR 的 canonical digest。
2. 新运行在 checkpoint 中持久化一次绝对 `workflow_deadline_epoch_ms`。
3. resume 必须复用同一个绝对 deadline，不能重新获得完整时间。
4. human gate 暂停时间计入 deadline。
5. 每次 agent 调用最多使用 `min(per-agent remaining timeout, workflow remaining time)`。
6. deadline 到期后不启动新 agent；当前调用被取消，相关节点进入 `needs_escalation`，并记录 `workflow.deadline.exceeded`。
7. deadline 字段缺失、类型错误、被回拨或与 resolved IR 不一致时 fail closed。

## Checkpoint、resume 与 no-replay

Loop entry 至少保存：

```text
current_iteration
completed_iterations
progress_digests
stop_reason
children[deterministic-agent-id]
workflow_deadline_epoch_ms（若声明）
```

要求：

- 已成功的 step 不重跑。
- 中断时为 running 的 step 在显式 resume 后重新排队，并增加 resume_count。
- 未开始的后续 step 保持 pending。
- 已完成迭代的候选、反馈和 digest 从 artifact/checkpoint 恢复。
- resolved IR 在 resume 前后不改写。
- checkpoint、summary、events 和 artifact identity 必须一致。
- 如果 partial iteration、step identity、模板 ID、artifact 或 progress digest 不一致，fail closed。

## 顶层模板节点状态

Body 模板节点只是 IR 中可审计的静态模板，不作为顶层任务运行。Loop 首次启动时将其顶层状态标记为 `skipped`：

```text
reason = executed_as_bounded_loop_template
```

模板节点不得创建自己的顶层 task directory、attempt 或 output artifact。真实 step 只出现在 loop entry 的 children 和确定性 task directory 中。

## 事件

至少记录：

```text
workflow.loop.iteration.started
workflow.loop.step.started
workflow.loop.step.completed
workflow.loop.iteration.completed
workflow.loop.stopped
workflow.deadline.exceeded
```

事件 sequence 必须连续；每个事件受 `max_event_bytes` 和 run 总 artifact limit 约束。

## 安全边界

Bounded Loop v1 不增加：

- workspace write 或 Git write；
- 任意命令 backend；
- 模型生成代码执行；
- 自动模型升级；
- 隐藏 retry；
- writer/worktree；
- merge、release 或 deploy；
- 模型自定义停止表达式或 selector。

所有模板仍固定 `access=read_only`，沿用原生 Codex CLI、ephemeral execution、Windows elevated read-only backend 和现有 external-model-export acknowledgement。

## 必须通过的测试门

1. 旧 loop 声明仍 validated-only 且不可执行。
2. 合法 bounded loop 进入 executable 集合。
3. accept 首轮收敛。
4. reject 后第二轮 accept。
5. unknown fail closed。
6. 达到 max_iterations fail closed。
7. progress digest 重复触发 no_progress。
8. agent budget 投影包含所有迭代 step。
9. body 模板所有权、依赖、Schema、placeholder 和 source 使用违规均拒绝。
10. 中断/恢复不重跑已成功 step。
11. resume 保留绝对 deadline，暂停时间计入。
12. deadline 期间取消当前调用且不启动后续调用。
13. resolved/checkpoint/summary/artifact/events 完整。
14. Windows/Ubuntu 完整测试通过。
15. 一次真实 Windows read-only RC 至少覆盖 reject→下一轮→accept 或明确的 no-progress/iteration-limit 终态。
