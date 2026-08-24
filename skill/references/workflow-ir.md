# Workflow IR v3

Workflow IR v3 是面向后续 Claude 风格 Dynamic Workflow Runtime 的声明式计划格式。它把控制流表示为数据，由可信 runner 校验和执行；模型不直接获得任意 Python、JavaScript、shell 或 Git 执行权限。

## 当前边界

- IR 版本固定为整数 `3`。
- 静态 `agent` 节点仍可编译为现有只读 v2 DAG。
- Workflow IR v3 可信 runtime 可执行 `agent`、`map`、`verify`、`reduce`、`conditional`、`human_gate`，以及满足 Bounded Loop v1 完整合同的 `loop` 实例。
- `max_tokens` 是 advisory 字段；soft/hard timeout 仍是 per-agent 进程边界。可选的 `workflow_timeout_seconds` 是额外的 whole-workflow 绝对上界。

Executable node kinds: `agent`, `map`, `verify`, `loop`, `reduce`, `conditional`, `human_gate`.
Validated-only node kinds: none.

Only `loop` instances that fully satisfy the Bounded Loop v1 contract are executable. Legacy `loop` declarations remain instance-level validated-only and are explicitly rejected at execution.

- 旧式或不完整的 `loop` 声明仍可通过声明级格式校验，但不会进入 executable 集合，也不会被静默迁移。完整实例合同见 [Bounded Loop v1](bounded-loop-v1.md)。
- 所有 writer、外部状态、凭据、commit、push、merge、deploy 和破坏性权限仍受 Dynamic Workflow 的既有授权规则约束；IR 本身不是授权。

## 示例

```json
{
  "version": 3,
  "name": "repository-audit",
  "mode": "workflow",
  "objective": "并行审核模块并形成可验证结论",
  "workdir": "D:\\projects\\example",
  "budgets": {
    "max_agents": 8,
    "max_concurrency": 4,
    "max_iterations": 3,
    "max_tokens": 200000,
    "soft_timeout_seconds": 900,
    "hard_timeout_seconds": 3600
  },
  "nodes": [
    {
      "id": "inspect-api",
      "kind": "agent",
      "depends_on": [],
      "config": {
        "profile": "luna",
        "access": "read_only",
        "prompt": "只读检查 API 模块并给出证据。"
      }
    },
    {
      "id": "final-judge",
      "kind": "agent",
      "depends_on": ["inspect-api"],
      "config": {
        "profile": "sol",
        "access": "read_only",
        "prompt": "结合上游证据形成最终技术判断。"
      }
    }
  ]
}
```

验证：

```powershell
py -3.12 skill\cli.py validate-ir --spec workflow-v3.json
```

当计划只含静态 `agent` 节点时，可查看编译后的 v2 规格：

```powershell
py -3.12 skill\cli.py validate-ir --spec workflow-v3.json --emit-v2
```

## 版本化原则

1. 未知顶层字段、节点字段、预算字段或节点类型一律拒绝。
2. 节点 ID 在大小写不敏感语义下必须唯一。
3. 外层依赖图必须无环；循环只允许由显式 `loop` 节点在自身版本化配置内表达。
4. 仅处于 validated-only 集合的节点不会被自动执行、重试或降级；runner 会明确报告不可执行。
5. 未来 IR 变更通过新的整数版本演进，不在 v3 下悄悄改变现有字段含义。

## Bounded Loop v1 与 workflow deadline

Bounded Loop v1 只接受 2..8 个顺序 `agent` 模板。每个模板必须使用 `{{loop_state}}`，最后一个模板必须返回固定 verifier Schema，`stop_when` 必须为 `verification_accept`。宿主根据候选输出的 canonical SHA-256 判断停滞；模型不能提供任意表达式或覆盖停止判断。

`budgets.workflow_timeout_seconds` 可选，范围为 60..172800 秒。运行时在首次执行时持久化绝对 deadline；`resume-ir` 复用同一值，human gate 暂停时间计入。每个 agent 的实际可用时间不超过 per-agent timeout 与 whole-workflow 剩余时间中的较小值。省略该字段时，旧 IR 的 normalized shape 与 canonical digest 保持不变。

## Trusted map → verify → reduce runtime

v3 runner 只解释声明式数据，不执行工作流提供的 Python、JavaScript、Shell 或 selector 表达式。动态来源必须是 exact node ID，并同时列入 `depends_on`。

- `map` 从前置 `agent` 或 `reduce` 的有限 JSON 数组展开稳定 child ID，并受 `item_limit`、`max_agents` 与全局并发预算约束。
- `verify` 只能消费 map manifest，每个 verifier 固定返回 `accept | reject | unknown`、summary 和 evidence。语义 reject 是数据，不伪装成进程失败。
- `reduce` 只能消费声明依赖中的 map/verify manifest；大型输入通过内容寻址 artifact reference 传递。
- `checkpoint.json` 保存动态 child、claimed agents 与 artifact identity；`resume-ir` 复用已成功 child，只重排确认中断的 running 工作。

## Trusted conditional and human gate

`conditional.config.condition` 是 `{source, pointer, operator, value?}`，不支持表达式或可执行 selector。`then` 与 `else` 显式列出分支入口；未选入口及其后继默认传播为 `skipped`。普通节点只接受全部 `succeeded` 的依赖；显式 `dependency_policy: "join"` 的节点可在至少一项 `succeeded` 且其余项为 `succeeded | skipped` 时汇合。全部依赖均为 `skipped` 时 join 本身也被跳过。条件无法确定时节点进入 `needs_escalation`。

`human_gate` 使用 `{prompt, options}`。运行第一次到达 gate 时原子创建不可变 `human-gates/<node-id>.json` contract 并返回 paused；`gate-decide` 使用 exclusive-create 写入 `<node-id>.decision.json`，因此并发冲突只有一个决定能成功。记录绑定依赖 artifact identity，终态决策不可覆盖。`actor` 与 `source` 是审计标签，不构成认证；显式决策后由 `resume-ir` 重新核对 identity 并继续。
