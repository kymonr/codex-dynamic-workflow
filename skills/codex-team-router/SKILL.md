---
name: codex-team-router
description: Use when the user asks for system-version multi-agent coordination with Codex app thread tools, long-lived manager/executor/verifier threads, or cross-session team routing.
---

# Codex Team Router

This Skill is a control-plane wrapper for Codex app thread tools. It coordinates three long-lived role threads and records state in a local ledger. It does not run a daemon, does not poll unattended, does not push/merge/deploy, and does not treat prompt text as a sandbox.

## Required Thread Tools

Before doing any work, probe that these Codex app tools are available:

- `list_projects`
- `create_thread`
- `list_threads`
- `read_thread`
- `send_message_to_thread`
- `set_thread_title`

If required tools are missing, stop with `tool_error`. This Skill is for Codex app thread tools; do not pretend it works in a plain CLI or Claude-only host.

The adapter path requires in-process Python callables owned by the parent host. Model-side Codex app tools are not Python callables and cannot be passed into `src/team_router.py` directly; if no host adapter exists, use the manual/pre-created continuation and feed send/read results back into the helpers.

## 角色模型 (Role Model)

Use Chinese role names as the reader-facing names. Keep the English names only as protocol/code aliases.

| 中文主名 | English alias | Thread? | Responsibility |
| --- | --- | --- | --- |
| 父线程调度者 | Parent Orchestrator | no | Understand the user goal, choose the next state-machine step, call helpers/tools, and emit the exact handoff or closeout. |
| 工具宿主边界 | Adapter Host Boundary | no | Own real callable access to `list_projects`, `create_thread`, `send_message_to_thread`, `read_thread`, and title/thread listing tools. |
| 状态控制器 | State Controller | no | Persist registry, ledger, recovery anchors, state transitions, and user-visible `Team Router Handoff` / `Team Router Closeout`. |
| 规划者 | Manager | yes | Reply only with `TEAM_ROUTER_PLAN`; define scope, stop condition, risk boundary, and executor prompt. |
| 执行者 | Executor | yes | Follow the manager plan, do the delegated read-only/design-only work, and reply with evidence in `TEAM_ROUTER_CALLBACK`. |
| 验证者 | Verifier | yes | Check the raw executor callback, evidence, permission boundary, and risks, then reply with `TEAM_ROUTER_VERDICT`. |

Canonical aliases: 父线程调度者 (Parent Orchestrator), 工具宿主边界 (Adapter Host Boundary), 状态控制器 (State Controller), 规划者 (Manager), 执行者 (Executor), 验证者 (Verifier).

只有规划者、执行者、验证者是长期 role thread. 父线程调度者、工具宿主边界、状态控制器 are parent-side concepts and must not create extra role threads.

Visible Codex desktop role-thread titles use `角色-任务名`, for example `规划者-管理者模式触发词修复`, `执行者-管理者模式触发词修复`, and `验证者-管理者模式触发词修复`. Do not include the project name by default unless the task name itself would be ambiguous.

### Manager Mode Hard Rule

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`.

Bare `manager` or `team manager` does not trigger Manager Mode. 裸 `manager` 不触发 Manager Mode; this avoids accidental activation for ordinary implementation requests such as `manager thread`, `manager parser`, or `manager integration`.

Manager Mode responsibilities:

1. Understand the objective.
2. Define scope.
3. Identify permission and safety boundaries.
4. Split work across roles.
5. Write `executorPrompt` and, when needed, `verifierPrompt`.
6. Define acceptance criteria.
7. Track status, identify blockers, and decide whether work needs rework.

Manager Mode 禁止直接改文件、跑测试、执行实现命令、commit、push、PR 或 merge. It must not act as the executor, fabricate child-thread results, or switch back to execution without explicit user approval.

If implementation is needed, Manager Mode must output a task for the executor instead of doing the work. 除非用户明确说“切回执行者”, “你来执行”, “直接改”, or “按这个 plan 落地”, keep the response in planning/review/orchestration mode only.

## Parent Thread Entry Flow

The parent thread is the orchestrator. The role threads only reply in their own threads with marker blocks. The required live-tool order is:

```text
list_projects -> create_thread -> send_message_to_thread -> read_thread
```

Use exactly one role-thread creation path per task. Do not mix the adapter-created and pre-created paths.

### Recommended adapter runner

Use `orchestrate_team_task_with_adapter()` when the parent host can provide adapter callables. The helper probes required thread tools, resolves the current project target with `list_projects`, discovers/reuses role threads with `list_threads`, normalizes titles with `set_thread_title`, starts a missing task, sends or reads the next required manager/executor/verifier step, and returns `action`, `status`, `ledger`, `userOutput`, `capabilities`, `codexProjectId`, and `projectTarget`.

Use a filesystem-safe Team Router `project_id` for local state, such as `codex-dynamic-workflow`. If Codex desktop `list_projects` returns a path-like project id such as `D:\codex\codex-dynamic-workflow`, pass it as `codex_project_id` so target lookup uses the real Codex id while registry and ledger paths stay safe.

Use `run_team_task_with_adapter()` only when the parent has already probed tools and resolved the project target. It is the lower-level runner behind the orchestration entry.

Call it once per parent turn or after a role thread has replied. It stops after sending work to a role thread, after a read that is still waiting/unreachable/blocked, or after terminal closeout. Parent thread rule: emit `update["userOutput"]` to the user when the returned payload contains closeout or handoff content.

For direct return, pass the current manager/parent thread id as `returnThreadId` when building executor dispatches and verifier requests. The role prompt must include `callbackDelivery: direct-send` or `verdictDelivery: direct-send` and tell the role to call `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_VERDICT block>)` after it writes the marker in its own thread. Manager inbox capture is part of the ledger state machine: a direct-return callback or verdict captured from the return thread must update ledger state, not just notify the manager. Keep `self-thread-marker` as the fallback/audit path.

For hosts without direct return, missed direct delivery, or recovery audits, use `watch_team_task_with_adapter()` from a real scheduler/automation. The watcher reads the ledger/registry recovery anchor, calls `read_thread`, captures a manager plan, executor callback, or verifier verdict, and immediately performs the next safe parent continuation such as sending executor work, sending verifier work, or returning closeout `userOutput`. It returns `action`, `status`, `userOutput`, `nextWakeup`, and `automationBoundary`. If `nextWakeup` is not null, the host automation must schedule another watcher call for that role/anchor. Direct return is possible when role threads are instructed with `returnThreadId` and can call `send_message_to_thread`; watcher/scheduler polling is the fallback when that is unavailable or misses delivery.

When the verifier returns `needs_rework`, the runner stops with `action: needs_rework_pending`. Call it with `confirm_rework=True` only after the user approves another executor dispatch.

### Adapter-created roles path

Use this path when the parent host can provide adapter callables whose functions invoke the real Codex app tools.

1. Probe the required tools and run `list_projects`; choose the current `projectId` and a project `target` with a local or worktree environment.
2. Resolve `stateRoot` and load the project registry.
3. Prefer `orchestrate_team_task_with_adapter()` for normal parent orchestration.
4. Use `start_team_task_with_adapter()` only when you need the lower-level start primitive. It reuses registry role bindings, calls `create_thread` only for missing manager/executor/verifier roles, then writes the registry role bindings and task ledger.
5. Do not pre-call `create_thread` for role threads before calling `start_team_task_with_adapter()`.

### Pre-created roles path

Use this path when the parent thread has already called `create_thread` manually or the host cannot pass tool callables into Python directly.

1. Probe the required tools and run `list_projects`; choose the current `projectId` and project target.
2. Resolve `stateRoot` and load the project registry.
3. Call `create_thread` only for missing manager/executor/verifier role threads.
4. Build a `roles` mapping with `manager`, `executor`, and `verifier`, each containing `threadId`, `title`, `createdAt`, and `lastObservedAt`.
5. Persist the pre-created role bindings with `create_team_task()` or the lower-level `update_registry_roles()` plus task-ledger helpers.
6. Do not call `start_team_task_with_adapter()` after manually creating role threads.

### Adapter continuation

Use this continuation when the parent host can pass tool callables into Python.

1. Send the manager plan request with `send_manager_plan_request_with_adapter()`. This records the send anchor for later `read_thread` recovery.
2. Call `read_thread` for the manager thread through `read_manager_plan_with_adapter()`. Do not dispatch if the plan is blocked, malformed, unreachable, or asks for escalation.
3. Send executor work with `send_executor_dispatch_with_adapter()`. The dispatch must include `callbackMode: self-thread-marker` and `TEAM_ROUTER_CALLBACK taskId=<taskId>`. When `returnThreadId` is available, also include `callbackDelivery: direct-send`.
4. Call `read_thread` for the executor thread through `read_executor_callback_with_adapter()`. If no final callback is present but the read window covers the anchor, leave the task waiting and give the user a copy-paste reminder for the executor thread.
5. Send verifier work with `send_verifier_request_with_adapter()`. Forward the raw executor callback block; do not summarize it first.
6. Call `read_thread` for the verifier thread through `read_verifier_verdict_update_with_adapter()` so the parent gets both the updated ledger and the exact user-facing output payload.
7. Parent thread rule: emit `update["userOutput"]` to the user. Do not replace it with an unstructured summary. If the task is not terminal, the helper returns a handoff with recovery anchors; if it is terminal with closeout, the helper returns a closeout.

### Manual/pre-created continuation

Use this continuation after the pre-created roles path when the parent thread directly invokes Codex app tools or the host cannot pass tool callables into Python.

1. Build the manager request with `make_plan_request_message()`, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist the anchor with `record_plan_request_sent()`.
2. Call `read_thread` for the manager thread, normalize the plain result with `normalize_thread_read_messages()`, then pass messages to `capture_manager_plan_from_read()`. Do not dispatch if the plan is blocked, malformed, unreachable, or asks for escalation.
3. Build executor work with `make_executor_dispatch_message()`, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist the anchor with `record_executor_dispatch_sent()`.
4. Call `read_thread` for the executor thread, normalize the result with `normalize_thread_read_messages()`, then pass messages to `capture_executor_callback_from_read()`. If no final callback is present but the read window covers the anchor, leave the task waiting and give the user a copy-paste reminder for the executor thread.
5. Build verifier work with `make_verifier_request_message()` using the raw executor callback block, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist the anchor with `record_verifier_request_sent()`.
6. Call `read_thread` for the verifier thread, normalize the result with `normalize_thread_read_messages()`, then pass messages to `capture_verifier_verdict_from_read()`.
7. Load the project registry and emit `format_task_update_for_user()` to the user. Do not replace it with an unstructured summary.

See `docs/runbooks/codex-team-router-live-orchestration.md` for a replayable live smoke procedure and fixture expectations.

## State Root

Use a shared `stateRoot`, not the current worktree root:

```text
<stateRoot>\projects\<codexProjectId>\registry.json
<stateRoot>\projects\<codexProjectId>\tasks\<taskId>.json
```

Resolve `stateRoot` in this order:

1. User-provided persistent directory.
2. Canonical git root; if current path is a worktree, resolve to the shared root or ask the user for one.
3. Current project root only for non-git projects.

Never place durable state under `D:\.codex-tmp`. If state is inside a repo, ensure `.codex-team-router/` is ignored before writing state.

## Protocols

Marker lines use `MARKER key=value`. Ordinary fields use `key: value`. Reject mixed marker formats such as `taskId: <id>`.

### Manager Plan

```text
TEAM_ROUTER_PLAN_REQUEST taskId=<taskId>
objective: <user goal>
permission: read-only | design-only

TEAM_ROUTER_PLAN taskId=<taskId>
status: planned | blocked
acknowledgedPermission: read-only | design-only | escalation-required
scope: <clear scope>
stopWhen: <done or blocked condition>
riskBoundary: <permission/data/external-system boundary>
executorPrompt: <prompt for executor>
notes: <none or notes>
```

The manager result must be parsed before executor dispatch. If manager escalates permission or blocks, do not dispatch.

### Executor Callback

```text
TEAM_ROUTER_DISPATCH taskId=<taskId>
role: executor
callbackMode: self-thread-marker
callbackMarker: TEAM_ROUTER_CALLBACK taskId=<taskId>
returnThreadId: <manager thread id when direct return is available>
callbackDelivery: direct-send
callbackFallback: self-thread-marker
permission: read-only | design-only
scope: <manager scope>
stopWhen: <manager stopWhen>
searchAnchor: <messageId or sentAt>

TEAM_ROUTER_CALLBACK taskId=<taskId>
status: done | blocked
final: true
summary: <3-7 lines>
evidence: <paths, command summaries, or thread observations>
risks: <none or risks>
next: <none or next step>
```

Use `callbackDelivery: direct-send` when a manager/parent `returnThreadId` is available and the role can call `send_message_to_thread`; keep `callbackMode: self-thread-marker` so the role thread remains recoverable by `read_thread`. Use the last matching final callback for fallback/audit reads.

### Verifier Verdict

```text
TEAM_ROUTER_VERIFY taskId=<taskId>
callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>
returnThreadId: <manager thread id when direct return is available>
verdictDelivery: direct-send
verdictFallback: self-thread-marker
permission: read-only | design-only
scope: <executor scope>

TEAM_ROUTER_VERDICT taskId=<taskId>
result: pass | needs_rework | blocked
summary: <verdict summary>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
```

Natural-language verdicts do not move state.

## 父线程侧状态控制器 (Parent-Side State Controller)

The implementation keeps the parent-side orchestration flow deterministic and local. Thread tools are an adapter layer: they send messages and pass plain send/read results back into helper functions. The helper layer performs registry role persistence, task ledger updates, protocol parsing, and recovery anchor selection. The 规划者 (Manager) thread does not own ledger or registry state.

Registry role persistence uses `update_registry_roles()` and `create_team_task()` to record the `manager`, `executor`, and `verifier` thread ids under the project registry before task dispatch. Task creation writes `tasks/<taskId>.json` immediately and moves the ledger to `roles_ready`.

The ledger stores read recovery anchors in three places:

- `planRequest.searchAnchor` for manager `TEAM_ROUTER_PLAN` reads.
- The latest `dispatches[]` entry for executor `TEAM_ROUTER_CALLBACK` reads.
- `verification.request.searchAnchor` for verifier `TEAM_ROUTER_VERDICT` reads.

Use `recovery_read_request()` to derive the role thread id and `searchAnchor` from the ledger plus registry before calling `read_thread`. Do not infer recovery state from the current conversation alone.

The adapter-facing entrypoints are:

- `probe_thread_adapter_capabilities()` to check the parent host exposes the required Codex app thread tools before live orchestration.
- `orchestrate_team_task_with_adapter()` as the recommended parent entry. It probes tools, resolves the project target, discovers/reuses role threads, advances the next send/read step, and returns `userOutput`.
- `run_team_task_with_adapter()` as the lower-level runner for hosts that already resolved the target and role-thread boundary.
- `watch_team_task_with_adapter()` for host automation that polls role-thread anchors, advances callback/verdict capture, returns `nextWakeup`, and produces closeout `userOutput` without a manual parent turn.
- `start_team_task_with_adapter()` to create manager/executor/verifier role threads and write the initial task ledger.
- `send_manager_plan_request_with_adapter()` and `read_manager_plan_with_adapter()` for manager planning.
- `send_executor_dispatch_with_adapter()` and `read_executor_callback_with_adapter()` for executor work and callback capture.
- `send_verifier_request_with_adapter()` and `read_verifier_verdict_with_adapter()` for verification and closeout.
- `read_verifier_verdict_update_with_adapter()` when the parent orchestrator needs both the updated ledger and the user-visible closeout/handoff payload.
- `format_task_update_for_user()`, `format_closeout_for_user()`, and `format_handoff_for_user()` for user-visible summaries after verifier reads or interruption.

Adapter functions must accept plain keyword arguments matching the Codex app tool names: `create_thread(prompt=..., target=...)`, `send_message_to_thread(threadId=..., prompt=...)`, and `read_thread(threadId=...)`. Normalize send/read tool results through `thread_send_anchor()` and `normalize_thread_read_messages()` before updating ledger state. `read_thread` may return `turns[].items[]` with `agentMessage.text` and numeric epoch timestamps such as `startedAt`; keep those timestamps available for recovery-anchor filtering.
## State Machine

```text
main: created -> roles_ready -> planning -> awaiting_plan -> planned -> dispatched -> awaiting_callback -> verifying -> done
rework: verifying -> needs_rework -> dispatched
manual_recovery: plan_unreachable -> planned | callback_unreachable -> verifying
terminal: blocked | malformed_callback | tool_error | missing_role | abandoned
```

`read_thread` must return a stable message id, timestamp, or ordered messages that prove the read window covers the dispatch/request anchor. If it cannot, move to `plan_unreachable` or `callback_unreachable` and ask the user to paste the missing marker block.

## Safety Boundary

`read-only/design-only 不是沙箱`. These are prompt boundaries, not enforceable filesystem or API sandboxes. If the original user goal clearly asks for writing files, commit/push/PR/merge/deploy, real APIs, accounts, or production data, stop before manager dispatch and route the work to an explicitly authorized write workflow such as `dynamic-workflow` worktree mode.

Do not add any write-capable permission value to Team Router dispatch messages.

## Closeout

Report the final status, relevant task id, last observed thread ids, state transitions, evidence summary, uncovered risk, next action, and `remainingTodos`. For a passing verifier closeout, `remainingTodos: none`; for `needs_rework` or `blocked`, set `remainingTodos` from `nextAction` or `requiredChanges`. Do not claim a child thread is currently active unless a fresh `read_thread` result proves that exact fact.
