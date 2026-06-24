# Manager Mode

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep deep Manager Mode rules here.

## Required Thread Tools

Before live work, probe that these Codex app tools are available:

- `list_projects`
- `create_thread`
- `list_threads`
- `read_thread`
- `send_message_to_thread`
- `set_thread_title`

If required tools are missing, stop with `tool_error`. This Skill is for Codex app thread tools; do not pretend it works in a plain CLI or Claude-only host.

The adapter path requires in-process Python callables owned by the parent host. Model-side Codex app tools are not Python callables and cannot be passed into `src/team_router.py` directly; if no host adapter exists, use the manual/pre-created continuation and feed send/read results back into the helpers.

## Role Model

Use Chinese role names as the reader-facing names. Keep the English names only as protocol/code aliases.

| 中文主名 | English alias | Thread? | Responsibility |
| --- | --- | --- | --- |
| 调度者 | Orchestrator | no | Understand the user goal, choose the next state-machine step, call helpers/tools, and emit the exact handoff or closeout. |
| 工具宿主边界 | Adapter Host Boundary | no | Own real callable access to `list_projects`, `create_thread`, `send_message_to_thread`, `read_thread`, and title/thread listing tools. |
| 状态控制器 | State Controller | no | Persist registry, ledger, recovery anchors, state transitions, and user-visible `Team Router Handoff` / `Team Router Closeout`. |
| 规划者 | Manager | yes | Reply only with `TEAM_ROUTER_PLAN`; define scope, stop condition, risk boundary, and executor prompt. |
| 执行者 | Executor | yes | Follow the manager plan, do the delegated read-only/design-only work, and reply with evidence in `TEAM_ROUTER_CALLBACK`. |
| 审查者 | Reviewer | conditional yes | Conditional reviewer for router/manager/orchestration policy, permission/safety boundaries, process rules, role protocol, and shared/high-risk logic; perform read-only/adversarial design review and reply with `TEAM_ROUTER_REVIEW`. |
| 验证者 | Verifier | yes | Check the raw executor callback, reviewer requirements when present, evidence, permission boundary, and risks, then reply with `TEAM_ROUTER_VERDICT`; verifier remains final acceptance. |

Canonical aliases: 调度者 (Orchestrator), 工具宿主边界 (Adapter Host Boundary), 状态控制器 (State Controller), 规划者 (Manager), 执行者 (Executor), 审查者 (Reviewer), 验证者 (Verifier).

规划者、执行者、验证者 are the default core role threads. 审查者 is a conditional reviewer role thread: create or reuse it only when the gate applies. 调度者、工具宿主边界、状态控制器 are parent-side concepts and must not create extra role threads.

只有规划者、执行者、验证者是长期 role thread；reviewer 是 conditional reviewer，不属于普通低风险任务的默认三段式。

Visible Codex desktop role-thread titles use `角色-任务名`, for example `规划者-管理者模式触发词修复`, `执行者-管理者模式触发词修复`, and `验证者-管理者模式触发词修复`. Do not include the project name by default unless the task name itself would be ambiguous.

### Manager Mode Hard Rule

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`.

Bare `manager` or `team manager` does not trigger Manager Mode. 裸 `manager` 不触发 Manager Mode; this avoids accidental activation for ordinary implementation requests such as `manager thread`, `manager parser`, or `manager integration`.

Manager Mode is sticky for the current task after it is triggered, and it persists until an explicit role switch. A terse follow-up or implementation command such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` is not execution authorization. Treat those replies only as permission to refine the plan, propose rule updates, or dispatch/prepare executor/verifier work inside Team Router, not as permission for the manager to personally edit files or run project commands.

Manager Mode responsibilities:

1. Understand the objective.
2. Define scope.
3. Identify permission and safety boundaries.
4. Split work across roles.
5. Write `executorPrompt` and, when needed, `verifierPrompt`.
6. Define acceptance criteria.
7. Track status, identify blockers, and decide whether work needs rework.

Manager Mode 禁止亲自修改文件、跑测试、执行实现命令、commit、push、PR 或 merge. It must not act as the executor, fabricate child-thread results, or switch back to execution without explicit user approval.

If implementation is needed, Manager Mode must output a task for the executor instead of doing the work. If implementation is requested during active Manager Mode, produce an executor task, a verifier task, or ask for an explicit role switch. Do not personally edit files or run project commands from Manager Mode. 除非用户明确说“切回执行者”, “你亲自改代码”, or “按这个 plan 落地”, keep the response in planning/review/orchestration mode only.

## Waiting And Reuse

Manager waiting policy: `read_thread` polling is allowed only as low-frequency, event-driven waiting. Use one short initial wait when a role may have replied, then default to 30-60s between watcher/read_thread checks or slower for large tasks. Do not surface every poll as user-visible progress; report only status changes, timeout, blocked states, or completion.

Role reuse policy: for the same `taskId` or task family, reuse existing executor, existing reviewer when the conditional reviewer gate applies, and existing verifier threads by default. Rework goes back to the original executor thread, rework review goes back to the original reviewer thread, and rework verification goes back to the original verifier thread. Create a new role thread only when the role boundary, permission boundary, workspace boundary, task-family boundary, or isolation requirement changes.
