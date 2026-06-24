# Team Router Fast Lane Design

- 日期：2026-06-24
- 状态：已设计，待用户审阅
- 范围：为 Team Router 增加推荐提速方案 B：task gate classifier + fast lane，同时保留 manager/executor/reviewer/verifier 边界。
- 非范围：不允许 manager 重新直接实现工作；不自动 push/PR/merge/deploy；不引入常驻服务或外部通知系统。

---

## 1. 背景

最近的 manager-discipline hardening 暴露了三个速度问题：

1. role thread 不会主动 push 回主线程，manager 必须读取 thread 才能拿到结果。
2. 连续轮询会打断角色线程纪律，所以读取必须 bounded。
3. 小 rework 和低风险任务如果全部走 executor -> reviewer -> verifier，会把角色往返成本放大。

已有规则已经补上 bounded polling 和 direct-return 文案，但还缺少一个明确的 fast lane 决策层：哪些任务可以跳过 reviewer，哪些必须保留 reviewer，以及什么时候 read_thread 只是 fallback。

## 2. 目标

实现后 Team Router 应能：

- 把任务分类为 `FAST`、`NORMAL`、`STRICT` 或 `PACKAGE`。
- 低风险小任务走 `executor -> verifier`。
- Team Router 自身流程、权限、安全、role protocol、shared/high-risk logic 仍走 `executor -> reviewer -> verifier`。
- 多个同类 manager-discipline 复利项可以作为一个 package 统一处理，减少重复 role 往返。
- direct-return 是首选完成路径，bounded read_thread 是 fallback。
- scheduler 输出下一次允许读取的时间/原因，防止 manager 连续轮询。

## 3. 任务分类

### FAST

适用：

- README / docs / reference 的窄文案修正。
- BOM、拼写、单个 policy phrase 对齐。
- 单个 doc-test needle 同步。
- 不改变 runtime 行为、不改变权限边界、不改变 role protocol。

流程：

```text
executor -> verifier
```

默认读取窗口：

```text
30s
```

### NORMAL

适用：

- 小范围 Python helper 或测试补强。
- 现有行为的聚焦回归。
- 不涉及 Team Router 自身治理边界。

流程：

```text
executor -> verifier
```

默认读取窗口：

```text
60s
```

### STRICT

适用：

- Team Router 自身 runtime/manager/orchestration policy。
- 权限、安全、side-effect taxonomy。
- role protocol、reviewer gate、direct-return、bounded polling。
- shared/high-risk logic。

流程：

```text
executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance)
```

默认读取窗口：

```text
90s
```

### PACKAGE

适用：

- 多个同类流程纪律复利项。
- 同一 task family 内的 title / polling / manager-overreach 等 hardening。

流程：

```text
executor -> reviewer -> verifier
```

默认读取窗口：

```text
120s
```

`PACKAGE` 不是降低审查，而是把多个小纪律项合并成一次审查/验收。

## 4. Direct Return

Direct return 是主路径。executor/reviewer/verifier 完成后必须在自己的线程输出 marker block，并调用：

```text
send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_* block>)
```

manager 只在以下情况下读 thread：

- 用户要求状态。
- direct-return 超过分类默认窗口未返回。
- 到达 `nextAllowedReadAt`。
- timeout/blocker recovery。

读取后只能观察和推进状态，不能把读取变成 mid-run instruction injection。

## 5. Scheduler

每次派发 role thread 后，ledger 或 update 应记录：

```json
{
  "readDiscipline": {
    "gateClass": "FAST",
    "lastReadAt": null,
    "nextAllowedReadAt": "2026-06-24T12:34:56+08:00",
    "readReason": "awaiting direct return fallback",
    "directReturnExpected": true
  }
}
```

当 manager 尝试读取时，helper 应先判断：

- 用户触发读取：允许。
- 当前时间未到 `nextAllowedReadAt`：返回 `read_suppressed`，不调用 `read_thread`。
- 到达窗口：允许一次读取并更新 `lastReadAt` / `nextAllowedReadAt`。
- timeout/blocker：允许读取并进入 recovery path。

## 6. Runtime 接口

建议新增或扩展：

```python
def classify_team_router_gate(ledger: Mapping[str, Any]) -> str:
    ...

def role_read_interval_seconds(gate_class: str) -> int:
    ...

def next_role_read_policy(ledger: Mapping[str, Any], *, observed_at: str) -> dict[str, Any]:
    ...

def role_read_allowed(
    ledger: Mapping[str, Any],
    *,
    observed_at: str,
    reason: str,
) -> dict[str, Any]:
    ...
```

`reviewer_gate_required_for_ledger()` 可以继续存在，但应由 classifier 的 `STRICT` / `PACKAGE` 结果驱动或与 classifier 保持一致。

## 7. 文档更新

需要同步：

- `README.md`：短说明 fast lane 和 gate classes。
- `skills/codex-team-router/SKILL.md`：manager 操作规则。
- `skills/codex-team-router/references/manager-mode.md`：详细纪律。
- `skills/codex-team-router/references/manual-orchestration.md`：manual continuation 如何使用 scheduler。
- `docs/runbooks/codex-team-router-live-orchestration.md`：live orchestration runbook。

## 8. 测试计划

至少覆盖：

- FAST docs/BOM rework 不要求 reviewer。
- STRICT Team Router runtime/policy/permission/role protocol 仍要求 reviewer。
- PACKAGE 多项 discipline hardening 仍要求 reviewer，但只走一次 reviewer/verifier。
- direct-return pending 时未到窗口不读。
- 用户触发读取允许一次 read。
- 到达窗口允许一次 read 并推进 `nextAllowedReadAt`。
- `read_thread` 检查不会产生 follow-up prompt。
- docs 覆盖 fast lane、direct return first、bounded fallback 和禁止 mid-run injection。

## 9. 风险

- 分类过宽会绕过 reviewer；因此默认不确定时归入 `STRICT`。
- direct-return 依赖子线程遵守工具调用；fallback 仍必须保留。
- scheduler 只能约束 Team Router helper，不能阻止人工在 UI 中手动读取。
- PACKAGE 会减少往返，但可能扩大单次 review 范围；需要限制为同一 task family。

## 10. 验收标准

- 分类结果可通过 `protocol_contract_snapshot()` 看到。
- fast lane 不改变 Manager Mode 的工作边界。
- STRICT 类任务仍强制 reviewer。
- direct-return-first 和 bounded fallback 都有测试。
- `git diff --check` 通过。
- 聚焦 `tests.test_team_router` 相关测试通过。
