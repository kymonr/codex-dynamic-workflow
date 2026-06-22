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
- `format_closeout_for_user()` and `format_handoff_for_user()` for user-visible summaries.

Adapter functions must accept plain keyword arguments matching the Codex app tool names: `create_thread(prompt=..., target=...)`, `send_message_to_thread(threadId=..., prompt=...)`, and `read_thread(threadId=...)`. Normalize send/read tool results through `thread_send_anchor()` and `normalize_thread_read_messages()` before updating ledger state.
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
