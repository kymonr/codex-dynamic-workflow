# Codex Team Router Live Orchestration Runbook

This runbook is the parent-thread entry point for a real Codex desktop smoke. It verifies that `codex-team-router` can use the host thread tools without moving those tools into `src/team_router.py`.

## Preconditions

- The parent thread can call `list_projects`, `create_thread`, `send_message_to_thread`, and `read_thread`.
- The target project is visible in `list_projects`.
- The task is read-only or design-only. Write, commit, push, PR, merge, deploy, real API, account, or production-data work must route to a separately authorized workflow.

## Tool Sequence

The live order is:

```text
list_projects -> create_thread -> send_message_to_thread -> read_thread
```

Use `src/team_router.py` helpers to keep state deterministic around those host-tool calls.

## Steps

1. Call `list_projects` and select the target project.
2. Resolve a shared `stateRoot` and `projectId`.
3. Run `probe_thread_adapter_capabilities()` if the parent host is using adapter callables.
4. Choose exactly one role-thread creation path for the task. Do not mix the adapter-created and pre-created paths.

### Recommended adapter runner

Use `orchestrate_team_task_with_adapter()` when the parent host can pass Codex thread tool callables into Python. The helper probes required thread tools, resolves the current project target with `list_projects`, discovers/reuses role threads with `list_threads`, normalizes titles with `set_thread_title`, starts a missing task, advances the next send/read step, and returns `action`, `status`, `ledger`, `userOutput`, `capabilities`, `codexProjectId`, and `projectTarget`.

Use a filesystem-safe Team Router `project_id` for local state, such as `codex-dynamic-workflow`. If Codex desktop `list_projects` returns a path-like project id such as `D:\codex\codex-dynamic-workflow`, pass it as `codex_project_id` so target lookup uses the real Codex id while registry and ledger paths stay safe.

Use `run_team_task_with_adapter()` only when the parent has already probed tools and resolved the project target. It is the lower-level runner behind the orchestration entry.

Call it again after a role thread has replied. It stops after sending work to a role thread, after a read that is still waiting/unreachable/blocked, or after terminal closeout. Emit `update["userOutput"]` exactly when the helper returns closeout or handoff content.

When the verifier returns `needs_rework`, the runner stops with `action: needs_rework_pending`. Call it with `confirm_rework=True` only after the user approves another executor dispatch.

### Adapter-created roles path

Use this path when the parent host can pass Codex thread tool callables into Python.

1. Prefer `orchestrate_team_task_with_adapter()` for normal parent orchestration.
2. Use `start_team_task_with_adapter()` only when testing or manually driving the lower-level start primitive.
3. Let the helper reuse registry role bindings and call `create_thread` through the adapter only for missing manager/executor/verifier role threads.
4. Let the helper persist registry role bindings and create the task ledger.
5. Do not pre-call `create_thread` for role threads before calling `start_team_task_with_adapter()`.

### Pre-created roles path

Use this path when the parent thread manually calls Codex app tools or the host cannot pass tool callables into Python.

1. Create missing role threads with `create_thread`:
   - manager prompt: role `manager`, wait for `TEAM_ROUTER_PLAN`.
   - executor prompt: role `executor`, wait for `TEAM_ROUTER_CALLBACK`.
   - verifier prompt: role `verifier`, wait for `TEAM_ROUTER_VERDICT`.
2. Build a `roles` mapping with each returned thread id, title, creation time, and observation time.
3. Persist role bindings and create the task ledger with `create_team_task()` or the equivalent lower-level registry helpers.
4. Do not call `start_team_task_with_adapter()` after manually creating role threads.

### Adapter continuation

Use this continuation when the parent host can pass Codex thread tool callables into Python.

1. Send the manager request with `send_manager_plan_request_with_adapter()`.
2. Read and capture the manager plan with `read_manager_plan_with_adapter()`.
3. If the manager plan is valid and does not require escalation, send executor dispatch with `send_executor_dispatch_with_adapter()`.
4. Read and capture the final executor callback with `read_executor_callback_with_adapter()`.
5. Send verifier request with `send_verifier_request_with_adapter()`. Forward the raw executor callback block.
6. Read the verifier result and finish with `read_verifier_verdict_update_with_adapter()`.
7. Emit `update["userOutput"]` exactly:
    - `Team Router Closeout` for terminal tasks with closeout.
    - `Team Router Handoff` for waiting, unreachable, interrupted, or non-terminal tasks.

### Manual/pre-created continuation

Use this continuation when the parent thread directly invokes Codex app tools or the host cannot pass tool callables into Python.

1. Build the manager request with `make_plan_request_message()`, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist it with `record_plan_request_sent()`.
2. Call `read_thread` for the manager, normalize the result with `normalize_thread_read_messages()`, then capture the plan with `capture_manager_plan_from_read()`.
3. If the manager plan is valid and does not require escalation, build executor dispatch with `make_executor_dispatch_message()`, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist it with `record_executor_dispatch_sent()`.
4. Call `read_thread` for the executor, normalize the result with `normalize_thread_read_messages()`, then capture the final callback with `capture_executor_callback_from_read()`.
5. Build verifier request with `make_verifier_request_message()` and the raw executor callback block, call `send_message_to_thread`, normalize the send result with `thread_send_anchor()`, then persist it with `record_verifier_request_sent()`.
6. Call `read_thread` for the verifier, normalize the result with `normalize_thread_read_messages()`, then capture the verdict with `capture_verifier_verdict_from_read()`.
7. Emit `format_task_update_for_user()` exactly:
   - `Team Router Closeout` for terminal tasks with closeout.
   - `Team Router Handoff` for waiting, unreachable, interrupted, or non-terminal tasks.

## Fixture

The fixture `tests/fixtures/team_router/live_read_thread_verdict.json` is a sanitized representative `read_thread` result from Codex desktop:

- top-level `schemaVersion`
- top-level `thread`
- `turns[].items[]`
- `agentMessage.text`
- numeric epoch `startedAt`

The unit test must prove that the fixture normalizes into a message containing `TEAM_ROUTER_VERDICT taskId=ctr-live-smoke-fixture-1` and keeps the numeric timestamp available for recovery-anchor filtering.

## Expected User Output

For a passing verifier result, the parent thread must display the helper output, not a rewritten summary:

```text
Team Router Closeout
taskId: <taskId>
status: done
threads:
  manager: <threadId>
  executor: <threadId>
  verifier: <threadId>
summary: <verifier summary>
evidenceChecked: <checked evidence>
risks: <none or risks>
nextAction: none
```

For a non-terminal task, display the handoff so the next parent turn can resume from ledger/registry anchors.
