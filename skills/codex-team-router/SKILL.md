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

## Parent Thread Entry Flow

The parent thread is the orchestrator. The role threads only reply in their own threads with marker blocks. The required live-tool order is:

```text
list_projects -> create_thread -> send_message_to_thread -> read_thread
```

Use exactly one role-thread creation path per task. Do not mix the adapter-created and pre-created paths.

### Adapter-created roles path

Use this path when the parent host can provide adapter callables whose functions invoke the real Codex app tools.

1. Probe the required tools and run `list_projects`; choose the current `projectId` and a project `target` with a local or worktree environment.
2. Resolve `stateRoot` and load the project registry.
3. Call `start_team_task_with_adapter()`. It calls `create_thread` through the adapter for manager/executor/verifier roles, then writes the registry role bindings and task ledger.
4. Do not pre-call `create_thread` for role threads before calling `start_team_task_with_adapter()`.

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
3. Send executor work with `send_executor_dispatch_with_adapter()`. The dispatch must include `callbackMode: self-thread-marker` and `TEAM_ROUTER_CALLBACK taskId=<taskId>`.
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

Only `callbackMode: self-thread-marker` is valid in MVP. Use the last matching final callback.

### Verifier Verdict

```text
TEAM_ROUTER_VERIFY taskId=<taskId>
callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>
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

## Local Manager State Helpers

The implementation keeps the manager flow deterministic and local. Thread tools are an adapter layer: they send messages and pass plain send/read results back into helper functions. The helper layer performs registry role persistence, task ledger updates, protocol parsing, and recovery anchor selection.

Registry role persistence uses `update_registry_roles()` and `create_team_task()` to record the `manager`, `executor`, and `verifier` thread ids under the project registry before task dispatch. Task creation writes `tasks/<taskId>.json` immediately and moves the ledger to `roles_ready`.

The ledger stores read recovery anchors in three places:

- `planRequest.searchAnchor` for manager `TEAM_ROUTER_PLAN` reads.
- The latest `dispatches[]` entry for executor `TEAM_ROUTER_CALLBACK` reads.
- `verification.request.searchAnchor` for verifier `TEAM_ROUTER_VERDICT` reads.

Use `recovery_read_request()` to derive the role thread id and `searchAnchor` from the ledger plus registry before calling `read_thread`. Do not infer recovery state from the current conversation alone.

The adapter-facing entrypoints are:

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

Report the final status, relevant task id, last observed thread ids, state transitions, evidence summary, uncovered risk, and next action. Do not claim a child thread is currently active unless a fresh `read_thread` result proves that exact fact.
