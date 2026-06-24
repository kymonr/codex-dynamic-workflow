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
| 执行者 | Executor | yes | Follow the manager plan, do delegated read-only/design-only work or explicitly authorized local-package workspace writes, and reply with evidence in `TEAM_ROUTER_CALLBACK`. |
| 审查者 | Reviewer | conditional yes | Conditional reviewer for router/manager/orchestration policy, permission/safety boundaries, process rules, role protocol, and shared/high-risk logic; perform read-only/adversarial design review and reply with `TEAM_ROUTER_REVIEW`. |
| 验证者 | Verifier | yes | Check the raw executor callback, reviewer requirements when present, evidence, permission boundary, and risks, then reply with `TEAM_ROUTER_VERDICT`; verifier remains final acceptance. |

Canonical aliases: 调度者 (Orchestrator), 工具宿主边界 (Adapter Host Boundary), 状态控制器 (State Controller), 规划者 (Manager), 执行者 (Executor), 审查者 (Reviewer), 验证者 (Verifier).

规划者、执行者、验证者 are the default core role threads. 审查者 is a conditional reviewer role thread: create or reuse it only when the gate applies. 调度者、工具宿主边界、状态控制器 are parent-side concepts and must not create extra role threads.

只有规划者、执行者、验证者是长期 role thread；reviewer 是 conditional reviewer，不属于普通低风险任务的默认三段式。

Visible Codex desktop thread titles use `角色-任务名`: the parent/current manager-dispatcher thread should be `调度者-Team Router <task label>` when the host UI exposes a current-thread title hook, and role threads use titles such as `规划者-Team Router 管理者模式触发词修复`, `执行者-Team Router 管理者模式触发词修复`, `审查者-Team Router 管理者模式触发词修复`, and `验证者-Team Router 管理者模式触发词修复`. Immediately after creating or discovering any role thread, normalize it with `set_thread_title`; do not leave adapter/default titles such as `TeamRouter executor - <projectId>` in the registry.

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

Manager Mode 禁止亲自修改文件、跑测试、执行实现命令、commit、push、PR 或 merge. Manager file edits require explicit current-turn user authorization. It must not act as the executor, fabricate child-thread results, or switch back to execution without explicit user approval.

If implementation is needed, Manager Mode must output a task for the executor instead of doing the work. If implementation is requested during active Manager Mode, produce an executor task, a verifier task, or ask for an explicit role switch. Do not personally edit files or run project commands from Manager Mode. 除非用户明确说“切回执行者”, “你亲自改代码”, or “按这个 plan 落地” and gives explicit current-turn user authorization for manager file edits, keep the response in planning/review/orchestration mode only.

## Waiting And Reuse

Manager waiting policy: `read_thread` polling is allowed only as bounded, low-frequency, event-driven waiting. Role threads do not actively push back, so this is not zero-read waiting: allowed reads are user-triggered status checks, reads after an agreed or explicit interval such as the default 30-60s cadence, reads after a known expected completion window, and timeout/blocker handling. Forbid continuous polling, do not turn reads into mid-run instruction injection, and report only status changes, timeout, blocked states, or completion.

Fast Lane policy: classify Team Router work as FAST, NORMAL, STRICT, or PACKAGE. FAST covers docs/BOM/single phrase rework, routes executor -> verifier, and uses a 30s bounded read_thread fallback window. NORMAL covers small focused code/test work, routes executor -> verifier, and uses a 60s bounded read_thread fallback window. STRICT covers Team Router process/permission/safety/role protocol/shared-risk changes, routes executor -> reviewer -> verifier, and uses a 90s bounded read_thread fallback window. PACKAGE covers same task family discipline hardening, keeps one executor -> reviewer -> verifier chain, and uses a 120s bounded read_thread fallback window. Completion is direct-return first; bounded read_thread fallback is allowed only after the class window, user-triggered status request, known expected completion window, or timeout/blocker handling. Path handoff expectations follow the same classes: `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` are optional for `FAST`/`NORMAL`, recommended for `STRICT`, and default required for `PACKAGE` unless the manager explicitly marks inline fallback.
Closeout reporting policy: every task closeout must report implemented changes, verification actually run and results, blockers/exceptions, remaining risks, and current state and next step. At closeout, make a compounding decision: record a reusable lesson when there is manager overreach, role conflict or role-authority confusion, permission/sandbox issue, test instability, temp-file/workspace pollution, or the user explicitly adds a reusable process preference. Durable policy should state the generic rule; dated incident facts belong in `docs/evidence/`. Do not record ordinary successful implementation/testing with no new reusable risk.
Role reuse policy: for the same `taskId` or task family, reuse existing executor, existing reviewer when the conditional reviewer gate applies, and existing verifier threads by default. Rework goes back to the original executor thread, rework review goes back to the original reviewer thread, and rework verification goes back to the original verifier thread. Create a new role thread only when the role boundary, permission boundary, workspace boundary, task-family boundary, or isolation requirement changes.
