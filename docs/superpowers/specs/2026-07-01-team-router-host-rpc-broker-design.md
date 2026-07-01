# Team Router Host RPC Broker Design

## Status

Design package only. This document defines the feasibility boundary and host contract for a future Desktop/plugin RPC broker. It does not implement broker code, Python adapter code, scheduler code, app/plugin code, push, PR, merge, deploy, release, or global skill sync.

Decision: use a localhost RPC broker as the preferred bridge from Codex Desktop thread tools to Team Router Python callables.

## Problem

Codex Desktop already exposes thread tools to the model/tool layer:

- `list_projects`
- `create_thread`
- `list_threads`
- `read_thread`
- `send_message_to_thread`
- `set_thread_title`

Team Router automatic orchestration needs the same capabilities as in-process Python callables. Today those are different surfaces:

```text
model/tool layer can call Codex Desktop thread tools
repo Python runtime cannot call those tools directly
```

Without a bridge, Team Router can still use manual orchestration, but it must not claim strict automatic orchestration. A fake adapter around model-side tool descriptors is not acceptable because it cannot be called by Python at watcher/scheduler time.

## Goal

Define the smallest host RPC contract that can turn the existing Codex Desktop thread tool surface into a real Python-callable adapter for Team Router.

The future bridge must support:

- fixed visible role reuse
- parent/orchestrator thread id injection
- direct-send callback delivery
- bounded `read_thread` fallback
- one 30 second first watcher check
- 300 second minimum role polling cadence after that
- evidence-based readiness reporting

## Non-Goals

- No repo-local fake implementation of Codex Desktop tools.
- No Desktop/plugin implementation in this design package.
- No production daemon implementation in this design package.
- No native `multi_agent_v1` replacement for visible Team Router role threads.
- No broad external API surface beyond the Team Router thread-tool allowlist.
- No automatic push, PR, remote merge, deploy, release, or global skill sync.

## Chosen Approach: Desktop/plugin Localhost RPC Broker

The broker runs in the Codex Desktop/plugin authority domain that can really call Codex app thread tools. It exposes a localhost-only RPC surface to the Team Router Python runtime.

Preferred shape:

```text
Codex Desktop/plugin tool authority
  -> localhost RPC broker on 127.0.0.1:<random-port>
    -> Python CodexAppThreadAdapter
      -> Team Router runtime
```

The broker is not a Team Router state machine. It only translates allowed RPC calls into Codex app tool calls and returns normalized evidence. Team Router remains responsible for registry, ledger, gate selection, direct-return validation, watcher discipline, and closeout.

## Hard Feasibility Requirement

The broker must run where it can actually invoke Codex app tools.

Allowed feasibility outcomes:

1. Desktop/plugin can host the broker or expose a broker API. Continue to implementation planning.
2. Desktop/plugin cannot expose app tool calls to any local broker. Record blocker and keep Team Router in `manual_only` / `host_contract_blocked`.
3. Only an external process can run, but it has no Codex app API. Treat as blocked. A localhost process without app tool authority is only another fake adapter.

The spec must not say automatic orchestration is available until outcome 1 is proven by readiness smoke evidence.

## Broker Process Model

The ideal user experience is not a manually opened terminal. The broker should be host-managed:

- started by Codex Desktop/plugin when Team Router automatic orchestration begins
- bound to a random localhost port
- issued a session-scoped token
- scoped to the current host, project, and parent thread
- shut down when Codex exits, the session expires, or the task is closed

Manual start may be acceptable for early feasibility only, but it must still produce the same readiness JSON and use the same security model.

## Parent Thread Identity

`parent_thread_id` is mandatory. It is the current orchestrator thread id used for:

- renaming the current parent thread with `set_thread_title`
- writing `returnThreadId`
- writing `orchestratorThreadId`
- validating direct-send protocol `sourceThreadId`
- routing role completion back to the manager inbox

The broker must expose parent identity through readiness:

```json
{
  "parentThreadId": "thread-parent",
  "parentThreadHostId": "local",
  "parentThreadRevision": "opaque-host-revision"
}
```

Invalidation rules:

- if the current thread is forked, handed off, archived, or moved to another host, the old readiness becomes stale
- if `parentThreadId` changes, the Python runtime must rebuild host context before dispatching new role work
- if the broker cannot identify the current parent thread id, automatic orchestration is blocked before child role dispatch

## RPC Surface

The broker exposes exactly these methods.

### `GET /readiness`

Returns evidence only. It must not create, send, read, or mutate thread state.

Required response shape:

```json
{
  "status": "ready",
  "brokerReady": true,
  "toolSmokeReady": true,
  "schedulerReady": true,
  "parentThreadId": "thread-parent",
  "parentThreadHostId": "local",
  "projectId": "project-team-router",
  "capabilities": {
    "list_projects": true,
    "create_thread": true,
    "list_threads": true,
    "read_thread": true,
    "send_message_to_thread": true,
    "set_thread_title": true,
    "heartbeat_scheduler": true
  },
  "runtimeProbe": {
    "status": "ready",
    "missing": []
  },
  "missing": []
}
```

Blocked response shape:

```json
{
  "status": "blocked",
  "brokerReady": true,
  "toolSmokeReady": false,
  "schedulerReady": false,
  "parentThreadId": null,
  "capabilities": {
    "create_thread": false
  },
  "runtimeProbe": {
    "status": "blocked",
    "missing": ["parent_thread_id", "callable create_thread"]
  },
  "missing": ["parent_thread_id", "callable create_thread"]
}
```

Readiness must be conservative. If tool access is uncertain, report blocked.

### `POST /thread-tools/list_projects`

Request:

```json
{
  "requestId": "uuid",
  "sessionToken": "opaque",
  "timeoutMs": 10000
}
```

Response:

```json
{
  "requestId": "uuid",
  "ok": true,
  "result": {
    "projects": []
  }
}
```

### `POST /thread-tools/list_threads`

Request includes project/host scope:

```json
{
  "requestId": "uuid",
  "sessionToken": "opaque",
  "projectId": "project-team-router",
  "hostId": "local",
  "limit": 100,
  "timeoutMs": 10000
}
```

Response must include enough fields for fixed role reuse:

```json
{
  "requestId": "uuid",
  "ok": true,
  "result": {
    "threads": [
      {
        "threadId": "thread-executor",
        "title": "Executor-Team Router host bridge",
        "archived": false,
        "hostId": "local",
        "projectId": "project-team-router",
        "updatedAt": "2026-07-01T10:00:00+08:00"
      }
    ]
  }
}
```

Archived or unavailable threads must be visible as such. Missing archived state is not proof of reusability.

### `POST /thread-tools/create_thread`

Request:

```json
{
  "requestId": "uuid",
  "sessionToken": "opaque",
  "prompt": "role bootstrap prompt",
  "target": {
    "type": "project",
    "projectId": "project-team-router",
    "environment": {"type": "local"}
  },
  "timeoutMs": 30000
}
```

Response must expose a thread id in one of the result shapes already accepted by Team Router runtime:

```json
{
  "requestId": "uuid",
  "ok": true,
  "result": {
    "threadId": "thread-new-role",
    "title": "Executor-Team Router host bridge"
  }
}
```

No thread id means failure. The Python adapter must not invent one.

### `POST /thread-tools/send_message_to_thread`

Request:

```json
{
  "requestId": "uuid",
  "sessionToken": "opaque",
  "threadId": "thread-parent",
  "prompt": "TEAM_ROUTER_CALLBACK ...",
  "timeoutMs": 30000
}
```

Response should include a send anchor:

```json
{
  "requestId": "uuid",
  "ok": true,
  "result": {
    "messageId": "message-123",
    "sentAt": "2026-07-01T10:00:00+08:00"
  }
}
```

If `messageId` is unavailable, `sentAt` fallback is allowed but weaker.

### `POST /thread-tools/read_thread`

Request:

```json
{
  "requestId": "uuid",
  "sessionToken": "opaque",
  "threadId": "thread-executor",
  "turnLimit": 20,
  "timeoutMs": 30000
}
```

Response must contain messages or turns with enough content and ordering evidence for Team Router normalizers:

```json
{
  "requestId": "uuid",
  "ok": true,
  "result": {
    "messages": [
      {
        "messageId": "message-456",
        "createdAt": "2026-07-01T10:02:00+08:00",
        "text": "TEAM_ROUTER_CALLBACK ..."
      }
    ]
  }
}
```

If the result cannot prove the read window covers the dispatch anchor, Team Router must enter unreachable/fallback handling rather than assuming no callback exists.

### `POST /thread-tools/set_thread_title`

Request:

```json
{
  "requestId": "uuid",
  "sessionToken": "opaque",
  "threadId": "thread-parent",
  "title": "Orchestrator-Team Router host bridge",
  "timeoutMs": 10000
}
```

Response may be empty, but failure blocks adapter-created orchestration.

### `POST /scheduler/wake`

This endpoint is host-internal. It is used by the broker/plugin scheduler to wake Team Router Python with a whitelisted callback.

Allowed callback:

```text
watch_team_task_with_adapter
```

Request:

```json
{
  "requestId": "uuid",
  "sessionToken": "opaque",
  "callback": "watch_team_task_with_adapter",
  "runAt": "2026-07-01T10:05:00+08:00",
  "payload": {
    "watchArgs": {},
    "kwargs": {}
  }
}
```

The host must call Python with:

- callable `thread_adapter`
- actual `observed_at` or `runAt`
- callable `heartbeat_scheduler`
- optional `turn_limit`

The Python side must materialize scheduler payloads through `materialize_watcher_call_kwargs()` before calling `watch_team_task_with_adapter()`.

## Python Adapter Contract

A future `CodexAppThreadAdapter` wraps broker RPC and exposes the existing Team Router callable surface:

```python
adapter.list_projects(**kwargs)
adapter.create_thread(**kwargs)
adapter.list_threads(**kwargs)
adapter.read_thread(**kwargs)
adapter.send_message_to_thread(**kwargs)
adapter.set_thread_title(**kwargs)
```

Adapter responsibilities:

- add session token and request id
- enforce per-call timeout
- map broker errors into `StateStoreError` / protocol errors
- return raw result shapes acceptable to existing normalizers
- never execute arbitrary code or arbitrary callbacks
- never treat a broker method descriptor as a callable unless it is actually callable Python code

## Security Model

Minimum required controls:

- bind only to `127.0.0.1`
- random high port per session
- session-scoped bearer token or equivalent nonce
- method allowlist only
- project/thread allowlist scoped to current Team Router task
- request id on every call
- default timeout on every call
- audit log of method, thread id, project id, request id, result status, and timing
- no arbitrary shell command execution
- no arbitrary file read/write RPC
- no arbitrary Python code execution
- no arbitrary callback name execution
- no cross-project or cross-host action unless explicitly supplied by readiness/project scope

A broker that exposes arbitrary app control is not acceptable for Team Router automatic orchestration.

## Fixed Role Reuse Requirements

The broker must give Python enough data to enforce role reuse. `list_threads` must support or return:

- project scope
- host id when available
- thread id
- title/name
- archived state
- enough freshness/metadata to resolve duplicates conservatively

Reuse order remains:

1. registry role binding
2. `list_threads` discovery
3. `create_thread` only for missing or invalid roles

Archived roles are never reused. Duplicate role candidates require conservative resolution. If the runtime cannot prove a candidate is the correct visible role, it must not silently reuse it.

## Direct-Send Contract

Direct-send remains the primary role completion path:

```text
send_message_to_thread(threadId=<returnThreadId>, prompt=<complete TEAM_ROUTER_* block>)
```

The same protocol block body is also emitted in the role thread as self-thread-marker fallback.

The broker only sends messages. It does not decide whether a callback is valid. Python Team Router validates:

- `taskId`
- expected marker
- protocol `sourceThreadId`
- `role`
- `sourceRoleThreadId`
- currently awaited role in the ledger

Malformed or stale direct-send blocks must not advance task state.

## Watcher Cadence

The host scheduler must preserve existing Team Router timing:

- first check at `sentAt + 30 seconds`
- one observation-only first `read_thread`
- later reads at least `300 seconds` after `lastReadAt`
- user-triggered status/stop/immediate, timeout, or blocker handling can bypass cadence using explicit reason
- terminal status and completed receipts must not schedule new heartbeats

The broker/scheduler must not implement tight polling. If a scheduler bug would wake too frequently, Python watcher discipline must still block or classify the read as not allowed.

## Error Taxonomy

Map host failures into existing Team Router states:

- no broker or no readiness snapshot: `manual_only`
- broker present but missing callable evidence: `host_contract_blocked`
- app tool call fails during runtime: `tool_error` or existing unreachable/fallback state depending on operation
- scheduler cannot wake Python: `host_contract_blocked` until fixed
- read result cannot prove anchor window: role-specific unreachable/fallback handling
- invalid protocol block: malformed direct-return record, no state advance

Do not retry forever. Retries must be bounded and same-scope.

## Feasibility Probe

Before implementation, the host package must prove these facts:

1. Broker can run in the Desktop/plugin authority domain.
2. Broker can call all six thread tools for the current user/session.
3. Broker can identify the current parent thread id.
4. Broker can start a scheduler wake and call Python at the right time.
5. Python can call the broker from the Team Router repo process.
6. Readiness returns `runtimeProbe.status == "ready"` only after real smoke evidence.

If any item cannot be proven, document the blocker and keep automatic orchestration disabled.

## Acceptance Criteria For This Design Package

This design package is complete when:

- it clearly states that Desktop/plugin tool authority is required
- it defines the localhost RPC broker as the preferred bridge
- it defines exact RPC methods and expected request/response shapes
- it defines parent thread id lifecycle and invalidation
- it defines scheduler responsibilities without implementing the scheduler
- it defines readiness JSON including `runtimeProbe`
- it defines security controls and disallows arbitrary callback/code execution
- it keeps current repo state honest: no live automatic orchestration claim

## Acceptance Criteria For A Future Implementation Package

A later implementation package can start only after this design is reviewed. It should be split into smaller gates:

1. Repo-local Python adapter interface and tests using a fake localhost broker.
2. Broker readiness and error taxonomy tests.
3. Scheduler wake contract tests around `materialize_watcher_call_kwargs()`.
4. Desktop/plugin feasibility spike outside this repo.
5. End-to-end smoke using real Desktop/plugin broker, fixed role reuse, direct-send callback, and watcher cadence.

No end-to-end automatic orchestration claim is allowed before step 5 passes.

## Open Blocker

The current confirmed blocker remains:

```text
Codex Desktop has thread tools at the model/tool layer, but this repo does not yet have a Desktop/plugin-hosted broker that exposes those tools as Python-callable RPC methods.
```

Until that bridge exists and produces readiness evidence, Team Router remains manual-only or host-contract-blocked for live automatic orchestration.
