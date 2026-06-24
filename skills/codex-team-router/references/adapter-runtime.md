# Adapter Runtime

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep adapter runtime details here.

## Parent Thread Entry Flow

The parent thread is the orchestrator. The role threads only reply in their own threads with marker blocks. The required live-tool order is:

```text
list_projects -> create_thread -> send_message_to_thread -> read_thread
```

Use exactly one role-thread creation path per task. Do not mix the adapter-created and pre-created paths.

## Recommended Adapter Runner

Use `parent_entry_guard()` at the parent boundary before choosing the adapter-created path. If callable thread tools are unavailable or the adapter object only contains model-side tool descriptors, do not continue the adapter runner; continue only with the manual/pre-created path and existing `manager` / `executor` / `verifier` role bindings, plus an existing reviewer only when conditional reviewer review is required.

Use `orchestrate_team_task_with_adapter()` when the parent host can provide adapter callables. The helper probes required thread tools, resolves the current project target with `list_projects`, discovers/reuses role threads with `list_threads`, normalizes titles with `set_thread_title`, starts a missing task, sends or reads the next required manager/executor/reviewer/verifier step, and returns `action`, `status`, `ledger`, `userOutput`, `capabilities`, `codexProjectId`, and `projectTarget`. It is not the entrypoint for pre-created role threads when the host lacks callable tools.

Use a filesystem-safe Team Router `project_id` for local state, such as `codex-dynamic-workflow`. If Codex desktop `list_projects` returns a path-like project id such as `D:\codex\codex-dynamic-workflow`, pass it as `codex_project_id` so target lookup uses the real Codex id while registry and ledger paths stay safe.

Use `run_team_task_with_adapter()` only when the parent has already probed tools and resolved the project target. It is the lower-level runner behind the orchestration entry.

Call it once per parent turn or after a role thread has replied. It stops after sending work to a role thread, after a read that is still waiting/unreachable/blocked, or after terminal closeout. Parent thread rule: emit `update["userOutput"]` to the user when the returned payload contains closeout or handoff content.

### Adapter-created roles path

Use this path when the parent host can provide adapter callables whose functions invoke the real Codex app tools.

1. Probe the required tools and run `list_projects`; choose the current `projectId` and a project `target` with a local or worktree environment.
2. Resolve `stateRoot` and load the project registry.
3. Prefer `orchestrate_team_task_with_adapter()` for normal parent orchestration.
4. Use `start_team_task_with_adapter()` only when you need the lower-level start primitive. It reuses registry role bindings, calls `create_thread` only for missing manager/executor/verifier core roles; create or reuse reviewer only when the conditional reviewer gate applies, then writes the registry role bindings and task ledger.
5. Do not pre-call `create_thread` for role threads before calling `start_team_task_with_adapter()`.

### Adapter continuation

Use this continuation when the parent host can pass Codex thread tool callables into Python.

1. Send the manager plan request with `send_manager_plan_request_with_adapter()`. This records the send anchor for later `read_thread` recovery.
2. Call `read_thread` for the manager thread through `read_manager_plan_with_adapter()`. Do not dispatch if the plan is blocked, malformed, unreachable, or asks for escalation.
3. Send executor work with `send_executor_dispatch_with_adapter()`. The dispatch must include `callbackMode: self-thread-marker` and `TEAM_ROUTER_CALLBACK taskId=<taskId>`. When `returnThreadId` is available, also include `callbackDelivery: direct-send`.
4. Call `read_thread` for the executor thread through `read_executor_callback_with_adapter()`. If no final callback is present but the read window covers the anchor, leave the task waiting and give the user a copy-paste reminder for the executor thread.
5. Send verifier work with `send_verifier_request_with_adapter()`. Forward the raw executor callback block; do not summarize it first.
6. Call `read_thread` for the verifier thread through `read_verifier_verdict_update_with_adapter()` so the parent gets both the updated ledger and the exact user-facing output payload.
7. Parent thread rule: emit `update["userOutput"]` to the user. Do not replace it with an unstructured summary. If the task is not terminal, the helper returns a handoff with recovery anchors; if it is terminal with closeout, the helper returns a closeout.

## 父线程侧状态控制器 (Parent-Side State Controller)

The implementation keeps the parent-side orchestration flow deterministic and local. Thread tools are an adapter layer: they send messages and pass plain send/read results back into helper functions. The helper layer performs registry role persistence, task ledger updates, protocol parsing, and recovery anchor selection. The 规划者 (Manager) thread does not own ledger or registry state.

Registry role persistence uses `update_registry_roles()` and `create_team_task()` to record the `manager`, `executor`, and `verifier` thread ids under the project registry before task dispatch. Task creation writes `tasks/<taskId>.json` immediately and moves the ledger to `roles_ready`.

The ledger stores read recovery anchors in three places:

- `planRequest.searchAnchor` for manager `TEAM_ROUTER_PLAN` reads.
- The latest `dispatches[]` entry for executor `TEAM_ROUTER_CALLBACK` reads.
- `verification.request.searchAnchor` for verifier `TEAM_ROUTER_VERDICT` reads.

Use `recovery_read_request()` to derive the role thread id and `searchAnchor` from the ledger plus registry before calling `read_thread`. Do not infer recovery state from the current conversation alone.

The adapter-facing entrypoints include `probe_thread_adapter_capabilities()`, `parent_entry_guard()`, `protocol_contract_snapshot()`, `orchestrate_team_task_with_adapter()`, `run_team_task_with_adapter()`, `watch_team_task_with_adapter()`, `start_team_task_with_adapter()`, `send_manager_plan_request_with_adapter()`, `read_manager_plan_with_adapter()`, `send_executor_dispatch_with_adapter()`, `read_executor_callback_with_adapter()`, `send_verifier_request_with_adapter()`, `read_verifier_verdict_with_adapter()`, `read_verifier_verdict_update_with_adapter()`, `format_task_update_for_user()`, `format_closeout_for_user()`, and `format_handoff_for_user()`.

Adapter functions must accept plain keyword arguments matching the Codex app tool names: `create_thread(prompt=..., target=...)`, `send_message_to_thread(threadId=..., prompt=...)`, and `read_thread(threadId=...)`. Normalize send/read tool results through `thread_send_anchor()` and `normalize_thread_read_messages()` before updating ledger state. `read_thread` may return `turns[].items[]` with `agentMessage.text` and numeric epoch timestamps such as `startedAt`; keep those timestamps available for recovery-anchor filtering.

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

## State Machine

```text
main: created -> roles_ready -> planning -> awaiting_plan -> planned -> dispatched -> awaiting_callback -> reviewing -> verifying -> done
rework: verifying -> needs_rework -> dispatched
manual_recovery: plan_unreachable -> planned | callback_unreachable -> verifying | review_unreachable -> reviewing
terminal: blocked | malformed_callback | tool_error | missing_role | abandoned
```

`read_thread` must return a stable message id, timestamp, or ordered messages that prove the read window covers the dispatch/request anchor. If it cannot, move to `plan_unreachable` or `callback_unreachable` and ask the user to paste the missing marker block.

## Safety Boundary

`read-only/design-only 不是沙箱`. These are prompt boundaries, not enforceable filesystem or API sandboxes. If the original user goal asks for workspace writes, continue only when the manager dispatch explicitly grants an authorized `local-package` executor scope and the task uses the required reviewer/verifier gates. Unsupported or high-risk writes still stop before dispatch: commit/push/PR/merge/deploy, global config, project-local `AGENTS.md`, destructive operations, real APIs, accounts, or production data require separate explicit authorization outside ordinary Team Router dispatch.

Team Router dispatch messages may use `read-only`, `design-only`, or `local-package`. `local-package` authorizes executor-delegated workspace writes only within the stated package; it does not authorize manager direct edits, commits, pushes, global config changes, production/API actions, or destructive operations.

## Closeout

Report the final status, relevant task id, last observed thread ids, state transitions, evidence summary, uncovered risk, next action, and `remainingTodos`. For a passing verifier closeout, `remainingTodos: none`; for `needs_rework` or `blocked`, set `remainingTodos` from `nextAction` or `requiredChanges`. Do not claim a child thread is currently active unless a fresh `read_thread` result proves that exact fact.
