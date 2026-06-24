# Manual Orchestration

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep manual/pre-created orchestration details here.

### Pre-created roles path

Use this path when the parent thread has already called `create_thread` manually or the host cannot pass tool callables into Python directly.

1. Probe the required tools and run `list_projects`; choose the current `projectId` and project target.
2. Resolve `stateRoot` and load the project registry.
3. Normalize the parent/current manager-dispatcher thread title to `调度者-Team Router <task label>` when the host UI exposes a current-thread title hook; this adapter path does not implement a callable current-thread title hook. Then call `create_thread` only for missing manager/executor/verifier core role threads; add reviewer only when the conditional reviewer gate applies. Immediately call `set_thread_title` for each created or discovered role thread and normalize titles to `角色-任务名`, such as `执行者-Team Router <task label>`, `审查者-Team Router <task label>`, or `验证者-Team Router <task label>`.
4. Build a `roles` mapping with `manager`, `executor`, and `verifier`, each containing `threadId`, normalized `title`, `createdAt`, and `lastObservedAt`.
5. Persist the pre-created role bindings with `create_team_task()` or the lower-level `update_registry_roles()` plus task-ledger helpers.
6. Do not call `start_team_task_with_adapter()` after manually creating role threads.

### Manual/pre-created continuation

Use this continuation after the pre-created roles path when the parent thread directly invokes Codex app tools or the host cannot pass tool callables into Python. This path uses manual helper/record/capture functions; it does not continue through `orchestrate_team_task_with_adapter()` or `run_team_task_with_adapter()`. `parent_entry_guard(...precreated_roles...)` is only a boundary decision and prompt aid here, not an end-to-end adapter-runner entrypoint.

1. Build the manager request with `make_plan_request_message()`, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist the anchor with `record_plan_request_sent()`.
2. Call `read_thread` for the manager thread, normalize the plain result with `normalize_thread_read_messages()`, then pass messages to `capture_manager_plan_from_read()`. Do not dispatch if the plan is blocked, malformed, unreachable, or asks for escalation.
3. Build executor work with `make_executor_dispatch_message()`, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist the anchor with `record_executor_dispatch_sent()`.
4. Call `read_thread` for the executor thread, normalize the result with `normalize_thread_read_messages()`, then pass messages to `capture_executor_callback_from_read()`. If no final callback is present but the read window covers the anchor, leave the task waiting and give the user a copy-paste reminder for the executor thread.
5. Build verifier work with `make_verifier_request_message()` using the raw executor callback block, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist the anchor with `record_verifier_request_sent()`.
6. Call `read_thread` for the verifier thread, normalize the result with `normalize_thread_read_messages()`, then pass messages to `capture_verifier_verdict_from_read()`.
7. Load the project registry and emit `format_task_update_for_user()` to the user. Do not replace it with an unstructured summary.

After dispatching a role thread, do not continuously poll it. Role threads do not actively push back, so bounded status reads are allowed, but only when user-triggered, after an agreed or explicit interval, after a known expected completion window, or for timeout/blocker handling. A `read_thread` check is observation, not a channel for mid-run instruction injection.

Fast Lane policy: classify Team Router work as FAST, NORMAL, STRICT, or PACKAGE. FAST covers docs/BOM/single phrase rework, routes executor -> verifier, and uses a 30s bounded read_thread fallback window. NORMAL covers small focused code/test work, routes executor -> verifier, and uses a 60s bounded read_thread fallback window. STRICT covers Team Router process/permission/safety/role protocol/shared-risk changes, routes executor -> reviewer -> verifier, and uses a 90s bounded read_thread fallback window. PACKAGE covers same task family discipline hardening, keeps one executor -> reviewer -> verifier chain, and uses a 120s bounded read_thread fallback window. Completion is direct-return first; bounded read_thread fallback is allowed only after the class window, user-triggered status request, known expected completion window, or timeout/blocker handling.
Closeout reporting policy: after `format_task_update_for_user()` or any protocol closeout, report implemented changes, verification actually run and results, blockers/exceptions, remaining risks, and current state and next step. Also make a closeout-time compounding decision: record a reusable lesson for manager overreach, role conflict, permission/sandbox issue, test instability, temp-file/workspace pollution, or when the user explicitly adds a reusable process preference; do not record ordinary successful implementation/testing with no new reusable risk.
## Watcher Fallback

For hosts without direct return, missed direct delivery, or recovery audits, use `watch_team_task_with_adapter()` from a real scheduler/automation. The watcher reads the ledger/registry recovery anchor, calls `read_thread`, captures a manager plan, executor callback, reviewer review, or verifier verdict, and immediately performs the next safe parent continuation such as sending executor work, sending reviewer work, sending verifier work, or returning closeout `userOutput`.

It returns `action`, `status`, `userOutput`, `nextWakeup`, and `automationBoundary`. If `nextWakeup` is not null, the host automation must schedule another watcher call for that role/anchor. Direct return is possible when role threads are instructed with `returnThreadId` and can call `send_message_to_thread`; watcher/scheduler polling is the fallback when that is unavailable or misses delivery.

When the verifier returns `needs_rework`, the runner stops with `action: needs_rework_pending`. Call it with `confirm_rework=True` only after the user approves another executor dispatch.
