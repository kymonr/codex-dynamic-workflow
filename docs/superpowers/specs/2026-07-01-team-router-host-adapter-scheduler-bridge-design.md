# Team Router Host Adapter Scheduler Bridge Design

## Status

Draft design after Superpowers brainstorming, Codex review, and Claude read-only consult.

This document is design only. It does not implement runtime code, commit, push, PR, merge, deploy, release, global skill sync, or any Codex Desktop host/plugin change.

## Problem

Team Router can model strict orchestration, but current Codex Desktop use is still manual at the host boundary:

- model-side Codex app tools expose `list_projects`, `create_thread`, `list_threads`, `read_thread`, `send_message_to_thread`, and `set_thread_title`
- `team_router.py` requires an in-process Python callable adapter for those tools
- no current host bridge supplies that callable adapter plus `parent_thread_id` plus heartbeat scheduler evidence

Because of that gap, visible role threads can be manually created/read, but the repo must not report live automatic orchestration until the host callable contract is satisfied.

## Goals

- Upgrade manual create/read role handling into strict host-backed orchestration when the host contract is available.
- Keep fixed visible role reuse: registry reuse, then `list_threads` discovery, then `create_thread` only for missing or invalid roles.
- Preserve direct-send as primary callback delivery and `read_thread` as bounded fallback only.
- Preserve watcher cadence: one short 30 second first check, then at least 300 seconds between reads for the same role/thread.
- Define a repo-local readiness contract that can report the current blocker without pretending model-side tools are Python callables.
- Define enough host bridge and scheduler contract detail for a later implementation plan.

## Non-Goals

- No fake adapter that wraps model tool descriptors inside this repo.
- No daemon or production heartbeat scheduler in this design package.
- No replacement of visible Team Router role threads with native subagents or `multi_agent_v1`.
- No relaxation of reviewer/verifier gates, direct-return validation, or role reuse rules.
- No automatic push, PR, merge, deploy, publish/release, or global skill sync.

## Current Truth

Repo-local runtime already has these pieces:

- `src/team_router_host_runtime.py` checks callable adapter tools, `parent_thread_id`, and callable heartbeat scheduler.
- `src/team_router.py` blocks adapter-created orchestration unless readiness is complete.
- `src/team_router_watcher_runtime.py` defines `FIRST_ROLE_CHECK_DELAY_SECONDS = 30` and `MIN_ROLE_POLL_INTERVAL_SECONDS = 300`.
- direct-return parsing validates `taskId`, expected marker, protocol `sourceThreadId`, `role`, and `sourceRoleThreadId`.
- `scripts/team_router_doctor.py --host-readiness-json` is evidence-only. It does not call real host tools.

Current blocker:

```text
Codex app thread tools are model-side tool calls, not Python callables available to team_router.py.
```

Until an external host supplies callable adapter and scheduler evidence, the safe states remain `manual_only` or `host_contract_blocked`.

## Architecture

Use three layers.

### 1. Repo Contract Layer

The repo owns readiness checks, ledger semantics, prompt contracts, watcher payload shape, doctor classification, and tests.

It must continue to accept only an adapter object with callable methods or a mapping with callable entries:

```python
thread_adapter.list_projects(...)
thread_adapter.create_thread(...)
thread_adapter.list_threads(...)
thread_adapter.read_thread(...)
thread_adapter.send_message_to_thread(...)
thread_adapter.set_thread_title(...)
```

Equivalent mapping entries are allowed, for example `thread_adapter["read_thread"](...)`. Every required value must be a real Python callable.

`parent_thread_id` means the current parent/orchestrator thread id used for:

- parent/current thread title normalization before child dispatch
- `returnThreadId` / `orchestratorThreadId` routing for direct-send callbacks

If the host cannot provide this id, adapter-created orchestration must stop before role dispatch.

### 2. Host Bridge Layer

The external Codex Desktop/plugin/host bridge owns conversion from app thread tool surface to Python callable adapter.

This is outside current repo implementation. The bridge must expose a Python object or mapping with callable entries matching the repo contract. Model-side tool descriptors alone are not sufficient.

The bridge must preserve host evidence rather than hiding it:

- tool callable availability
- current `parent_thread_id`
- scheduler callable availability
- host id or project target when available
- adapter result ids/timestamps when available

### 3. Scheduler Layer

The host scheduler owns delayed invocation. Repo code only builds heartbeat payload and calls the supplied scheduler callable.

Scheduler contract:

```python
scheduler(**payload)
```

or:

```python
scheduler.schedule(**payload)
```

Payload contains:

- `callback`: `watch_team_task_with_adapter`
- `runAt`
- `taskId`
- `projectId`
- `threadId`
- `role`
- `expectedMarker`
- `readReason`
- `watchArgs`
- `kwargs`

`watchArgs` and `kwargs` carry duplicate snake_case and camelCase keys for compatibility:

```text
state_root / stateRoot
project_id / projectId
task_id / taskId
read_reason / readReason
return_thread_id / returnThreadId, when present
```

The host scheduler must call `watch_team_task_with_adapter()` with the Python `kwargs` shape expected by the repo runtime, not with raw UI text.

The host scheduler must also inject runtime-only objects and wake timing that are not serialized in the payload:

- `thread_adapter`: the same callable adapter or a fresh callable adapter for the current host
- `observed_at`: the actual wake time, or `runAt` when the host has no better observed timestamp
- `heartbeat_scheduler`: the callable scheduler again when the watcher should reschedule itself
- `turn_limit`: optional host/user bound when applicable

Without `thread_adapter` and `observed_at`, `watch_team_task_with_adapter()` cannot run.

## Host Readiness States

### `manual_only`

No host readiness snapshot supplied. Doctor is read-only and no live adapter/scheduler evidence exists.

### `host_contract_blocked`

Host evidence exists but one or more required parts are missing:

- callable adapter
- callable thread tool method
- `parent_thread_id`
- callable heartbeat scheduler or callable `.schedule(**kwargs)`

### `adapter_smoke_ready`

Host evidence proves all required callable parts exist. This is still smoke readiness, not proof that an entire task completed. Runtime must still validate real adapter results and role receipts.

Doctor `adapter_smoke_ready` and runtime readiness must not diverge silently. If doctor claims ready but runtime `probe_thread_adapter_capabilities()` fails, runtime wins and orchestration blocks.

## Adapter Result Schema

Host bridge result shapes must be explicit enough for existing runtime parsing.

### `list_projects`

Allowed shapes:

- list of project objects
- `{ "projects": [...] }`
- `{ "items": [...] }`
- nested under `{ "data": ... }` or `{ "result": ... }`

Each project must expose an id via `projectId`, `project_id`, or `id`.

Each selected project must expose target data through `target`, `environment`, or recognized local project metadata.

### `list_threads`

Allowed shapes:

- list of thread objects
- `{ "threads": [...] }`
- `{ "items": [...] }`
- nested under `{ "data": ... }` or `{ "result": ... }`

Each reusable role thread must expose:

- `threadId`, `thread_id`, or `id`
- `title` or `name`, or explicit Team Router role metadata
- no unavailable status such as archived, blocked, broken, invalid, or unavailable

### `create_thread`

Must return a thread id via:

- `threadId`
- `thread_id`
- `id`
- or the same inside `thread`, `data`, or `result`

If no id is present, runtime must fail rather than inventing one.

### `send_message_to_thread`

Should return message anchor data when available:

- `messageId`, `message_id`, or `id`
- `sentAt`, `sent_at`, `createdAt`, `created_at`, or `timestamp`

If message id is unavailable, runtime may use the supplied `sentAt` fallback as a weak anchor.

### `read_thread`

Must return a JSON object or array containing sortable messages/turn items. Messages need enough text and anchor metadata for post-dispatch window checks.

If the read result cannot prove the window covers the dispatch/search anchor, runtime must enter the corresponding unreachable/fallback state instead of assuming no callback exists.

### `set_thread_title`

Must be callable. Return value may be empty, but callable failure means parent/role title normalization is not proven.

## Strict Role Reuse

Role creation must use this order:

1. registry role binding, if valid
2. `list_threads` discovery by role metadata/title
3. `create_thread` only for missing replacement roles

Do not reuse:

- archived role/thread
- broken, invalid, unavailable, blocked role/thread
- role with workspace, permission, task-family, isolation, audit, concurrency, or model/capability boundary mismatch

Archived role/thread is unavailable for reuse, period. Use a non-archived visible replacement role and record replacement reason.

Rework returns to the original role thread unless that role is unavailable or a boundary changed.

## Direct-Send Callback Contract

Role dispatch must include:

```text
sourceThreadId: <returnThreadId>
sourceRoleThreadId: <roleThreadId>
role: Executor | Reviewer | Verifier | Architect | QA
returnThreadId: <parent/orchestrator thread id>
orchestratorThreadId: <parent/orchestrator thread id>
<roleDeliveryField>: direct-send
<roleFallbackField>: self-thread-marker
```

Role-specific delivery field names:

```text
Executor: callbackDelivery / callbackFallback
Reviewer: reviewDelivery / reviewFallback
Verifier: verdictDelivery / verdictFallback
Architect: architectReviewDelivery / architectReviewFallback
QA: qaReviewDelivery / qaReviewFallback
```

Role completion sequence:

1. send the complete protocol block to `returnThreadId` with `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_* block>)`
2. output the same protocol block body in the role thread as self-thread-marker fallback

Manager accepts direct-send only when:

- `taskId` matches
- marker matches the currently awaited role
- protocol `sourceThreadId` matches pending `returnThreadId`
- protocol `role` matches pending role
- protocol `sourceRoleThreadId` matches pending role thread id

Manager inbox must consume only the role currently awaited by the ledger. Out-of-order or stale direct-send blocks are rejected, quarantined, or ignored without advancing state.

## Fallback And Degraded Delivery

`read_thread` is fallback recovery, not normal proactive callback.

When watcher/manual read captures a role self-thread marker because direct-send was missed, unavailable, or bypassed:

```text
deliveryStatus: fallback_only
delivery degraded
not normal proactive return
```

After bounded wait/read with no final protocol block, manager sends CONTROL for scope-limited closeout from already-confirmed facts. It must not inject broad new work or expand task scope.

## Watcher Cadence

Initial dispatch/read registration creates watcher metadata.

Timing:

- `firstCheckAt = sentAt + 30 seconds`
- first check is a single observation-only `read_thread`
- after first check, next allowed read is at least `lastReadAt + 300 seconds`
- same role/thread must not be read more often than 300 seconds unless current user asks status/stop/immediate, timeout, or blocker handling applies

Reading while role status is active/running/working is observation-only. It must not send mid-run instruction prompts or convergence demands.

Terminal status or `needs_rework` must not schedule a new heartbeat.

## Host Failure Behavior

Adapter or scheduler failures must not widen task scope.

If a command/tool startup failure matches known environment failure signatures, manager follows startup failure recovery:

- pause role escalation
- run minimal parent probes
- if probes recover, retry same narrow package only
- if probes fail after escalation, mark environment blocked

Scheduler must not infinite-retry a failing adapter call. It should surface blocked state and stop or defer the heartbeat according to host policy.

## Acceptance Tests Before Implementation

Add or preserve tests for these cases before bridge implementation:

- non-callable model-side tool descriptors are rejected as `host_contract_blocked`
- missing `parent_thread_id` blocks before child role dispatch
- callable adapter plus callable scheduler reaches `adapter_smoke_ready`
- doctor `adapter_smoke_ready` evidence and runtime readiness cannot disagree silently
- `create_thread` result without thread id fails
- `list_threads` discovered archived role is not reused
- duplicate discovered role matches require explicit resolution
- new role creation is blocked when discovery found reusable role and caller skipped normal reuse path
- scheduler payload includes `runAt`, `callback`, `watchArgs`, and `kwargs`
- first heartbeat uses `firstCheckAt`, later heartbeat respects 300 second cadence
- terminal task does not schedule heartbeat
- non-callable scheduler is rejected
- direct-send rejects wrong task id, wrong role, wrong protocol `sourceThreadId`, and wrong `sourceRoleThreadId`
- manager inbox ignores or quarantines a direct-send for a role that is not currently awaited
- duplicate direct-send after ledger advanced is idempotent
- fallback `read_thread` capture is marked `fallback_only` / degraded
- timeout without final marker sends CONTROL instead of broad follow-up
- adapter startup/environment failure blocks or retries same narrow scope only

## Rollout

### Stage 1: Repo Contract Spec

Write this design, review it, and keep repo current state honest:

- no claim of live automatic orchestration
- doctor remains evidence-only
- current default remains `manual_only` without host readiness snapshot

### Stage 2: Implementation Plan

Write a TDD plan for repo-local readiness/schema/scheduler contract hardening only.

No host bridge implementation starts until the host callable surface is confirmed.

### Stage 3: Host Bridge Package

External Codex Desktop/plugin/host work supplies:

- callable thread adapter
- current parent thread id
- callable heartbeat scheduler
- readiness snapshot generation
- smoke test that drives adapter-created orchestration without manual role create/read

### Stage 4: Strict Automatic Orchestration Smoke

Only after Stage 3:

- create/reuse fixed roles via adapter
- dispatch with direct-send metadata
- observe direct-send manager inbox receipt
- schedule watcher at 30 seconds then 300 second cadence
- prove fallback reads are degraded and bounded

## Open Blocker

Current desktop host has model-side app tools, but this repo has no in-process Python callable bridge to them.

Therefore the design must not claim true automatic orchestration until the host bridge supplies callable adapter and scheduler evidence.
