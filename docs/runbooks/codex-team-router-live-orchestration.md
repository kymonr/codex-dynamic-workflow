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
3. Create missing role threads with `create_thread`:
   - manager prompt: role `manager`, wait for `TEAM_ROUTER_PLAN`.
   - executor prompt: role `executor`, wait for `TEAM_ROUTER_CALLBACK`.
   - verifier prompt: role `verifier`, wait for `TEAM_ROUTER_VERDICT`.
4. Persist role bindings and create the task ledger with `start_team_task_with_adapter()` or the equivalent `create_team_task()` registry path when the host cannot pass tool callables into Python directly.
5. Send the manager request with `send_message_to_thread`, record the send anchor, then call `read_thread` for the manager. Feed the read result through `normalize_thread_read_messages()` and `read_manager_plan_with_adapter()`/capture helpers.
6. If the manager plan is valid and does not require escalation, send executor dispatch with `send_message_to_thread`. The dispatch must include `callbackMode: self-thread-marker` and `TEAM_ROUTER_CALLBACK taskId=<taskId>`.
7. Call `read_thread` for the executor. Capture the final callback with `read_executor_callback_with_adapter()` or the equivalent capture helper.
8. Send verifier request with `send_message_to_thread`. Forward the raw executor callback block.
9. Call `read_thread` for the verifier and finish with `read_verifier_verdict_update_with_adapter()`.
10. Emit `update["userOutput"]` exactly:
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
