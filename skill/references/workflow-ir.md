# Workflow IR v3

Workflow IR v3 是面向后续 Claude 风格 Dynamic Workflow Runtime 的声明式计划格式。它把控制流表示为数据，由可信 runner 校验和执行；模型不直接获得任意 Python、JavaScript、shell 或 Git 执行权限。

## 当前边界

- IR 版本固定为整数 `3`。
- 静态 `agent` 节点仍可编译为现有只读 v2 DAG。
- Workflow IR v3 可信 runtime 现可执行 `agent`、`map`、`verify` 与 `reduce`；`loop`、`conditional` 和 `human_gate` 仍只验证、不执行。
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
4. 动态节点不会被自动展开、重试或降级；直到对应 runtime 实现完成前，它们只通过校验并明确报告不可执行。
5. 未来 IR 变更通过新的整数版本演进，不在 v3 下悄悄改变现有字段含义。

## Trusted map → verify → reduce runtime

v3 runner 只解释声明式数据，不执行工作流提供的 Python、JavaScript、Shell 或 selector 表达式。动态来源必须是 exact node ID，并同时列入 `depends_on`。

- `map` 从前置 `agent` 或 `reduce` 的有限 JSON 数组展开稳定 child ID，并受 `item_limit`、`max_agents` 与全局并发预算约束。
- `verify` 只能消费 map manifest，每个 verifier 固定返回 `accept | reject | unknown`、summary 和 evidence。语义 reject 是数据，不伪装成进程失败。
- `reduce` 只能消费声明依赖中的 map/verify manifest；大型输入通过内容寻址 artifact reference 传递。
- `checkpoint.json` 保存动态 child、claimed agents 与 artifact identity；`resume-ir` 复用已成功 child，只重排确认中断的 running 工作。
