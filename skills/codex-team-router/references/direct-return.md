# Direct Return

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep direct-return details here.

Terminology: Codex delegation wrapper metadata may expose the sender role thread as `<source_thread_id>` / normalized message `sourceThreadId`. That wrapper source identifies the role thread that sent the message. Inside the Team Router protocol block, `sourceThreadId` is the parent/orchestrator return thread id and must match the pending ledger `returnThreadId`; `sourceRoleThreadId` is the role thread id and must match the expected `roleThreadId` / role thread record for the pending role ledger entry.

Direct return is the primary completion path when the current orchestrator/parent thread id is known. The role must first call `send_message_to_thread(sourceThreadId, protocolBlock)` to direct-send the final protocol block to Manager, then output the same protocol block body in its own thread as the `self-thread-marker` fallback/audit copy.

Use these explicit fields together:

- `sourceThreadId`: the current orchestrator/parent thread that should receive the direct callback first.
- `sourceRoleThreadId`: the executor/reviewer/verifier role thread that is allowed to emit the direct callback for this pending ledger entry.
- `role`: the active role name that must match the pending ledger entry.
- `returnThreadId`: the current orchestrator/parent thread recorded for compatibility and audit.
- `orchestratorThreadId`: the same parent/orchestrator thread id recorded for audit and validation.
- `roleThreadId`: the executor/reviewer/verifier thread expected to send the callback.

Do not default `returnThreadId` to the manager/planner role thread. If no explicit parent/source thread id is available, omit direct-send metadata and rely on watcher/heartbeat fallback.

## Role Thread Requirement

Executor, reviewer, and verifier roles must be Codex desktop thread roles when Team Router expects direct return. Do not dispatch Team Router role work to `multi_agent_v1` workers/subagents or other non-thread agents: they are not reliable role threads and may not expose `send_message_to_thread`.

Before reusing a role thread for direct-return work, confirm it is a usable Codex thread, not archived/broken, and can call `send_message_to_thread`. An archived role/thread is unavailable for reuse, period: create or use a non-archived visible replacement role and record the replacement reason. If a non-archived role is still not user-visible, read_thread readable, or otherwise usable, treat it as unavailable/broken and replace it with a visible role. If direct-send is unavailable or fails for a given run, keep the self-thread marker as fallback for that run and record fallback-only metadata on the local protocol block: `deliveryStatus: fallback_only` plus `deliveryError` only when direct-send was unavailable or failed.

Prompt metadata by role:

- executor: `callbackDelivery: direct-send` plus `callbackFallback: self-thread-marker`.
- reviewer: `reviewDelivery: direct-send` plus `reviewFallback: self-thread-marker`.
- verifier: `verdictDelivery: direct-send` plus `verdictFallback: self-thread-marker`.

Compatibility anchors:

- executor direct-return specifically means `send_message_to_thread(sourceThreadId, protocolBlock)` with a `TEAM_ROUTER_CALLBACK` block body.
- reviewer direct-return specifically means `send_message_to_thread(sourceThreadId, protocolBlock)` with a `TEAM_ROUTER_REVIEW` block body.
- verifier direct-return specifically means `send_message_to_thread(sourceThreadId, protocolBlock)` with a `TEAM_ROUTER_VERDICT` block body.
- the fallback invariant is unchanged: after any direct-send attempt, output the same protocol block body in the role thread as the `self-thread-marker` fallback/audit copy.

Manager inbox capture is part of the ledger state machine. A direct-return callback, review, or verdict captured from the return thread must update ledger state, not just notify the manager.

Manager inbox validation requirements:

- validate `taskId` against the active ledger task.
- validate protocol-block `sourceThreadId` against the expected parent/orchestrator `returnThreadId`.
- validate `sourceRoleThreadId` against the expected `roleThreadId` / role thread record.
- validate `role` against the pending role ledger entry.
- validate the expected marker: `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`.
- consume the callback only while the ledger is currently awaiting that role result, including that role's `needs_feedback` recovery state.

Manager accepts direct-send only when `taskId`, protocol-block `sourceThreadId`, `role`, and `sourceRoleThreadId` all match the pending role ledger entry, including that `sourceThreadId` matches the pending ledger `returnThreadId`. Unmatched direct-send blocks are rejected/quarantined, cannot advance the ledger, and cannot expand scope.

Duplicate direct callbacks are ignored after the ledger advances past that role. Do not record duplicate observations and do not let old executor/reviewer/verifier callbacks trigger the next state twice.

Keep `self-thread-marker` as the fallback/audit path. If direct-send is unavailable or misses delivery, watcher/heartbeat must read the role thread at the normal 5 minutes / 300 seconds fallback cadence and capture the self-thread marker. watcher-only collection is `deliveryStatus: fallback_only` / delivery degraded, not normal success, and manager closeout must record that degraded path instead of presenting it as proactive role return. User-facing wording must say fallback-only is degraded delivery, not normal proactive return, and name the watcher 300s fallback path when that is how the result was collected.

## Protocols

Marker lines use `MARKER key=value`. Ordinary fields use `key: value`. Reject mixed marker formats such as `taskId: <id>`.

### Manager Plan

```text
TEAM_ROUTER_PLAN_REQUEST taskId=<taskId>
objective: <user goal>
permission: read-only | design-only | local-package

TEAM_ROUTER_PLAN taskId=<taskId>
status: planned | blocked
acknowledgedPermission: read-only | design-only | local-package | escalation-required
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
sourceThreadId: <manager/orchestrator thread id that receives direct-send first>
sourceRoleThreadId: <executor role thread id>
role: Executor
returnThreadId: <explicit orchestrator/parent thread id when direct return is available>
orchestratorThreadId: <same current orchestrator/parent thread id>
roleThreadId: <executor role thread id>
callbackDelivery: direct-send
callbackFallback: self-thread-marker
permission: read-only | design-only | local-package
scope: <manager scope>
stopWhen: <manager stopWhen>
searchAnchor: <messageId or sentAt>

TEAM_ROUTER_CALLBACK taskId=<taskId>
sourceThreadId: <manager/orchestrator thread id>
sourceRoleThreadId: <executor role thread id>
role: Executor
status: done | blocked
final: true
summary: <3-7 lines>
evidence: <paths, command summaries, or thread observations>
risks: <none or risks>
next: <none or next step>
deliveryStatus: fallback_only
deliveryError: <short error only when direct-send was unavailable or failed>
```

Use `callbackDelivery: direct-send` when an explicit orchestrator/parent `sourceThreadId` is available and the role can call `send_message_to_thread`; direct-send return is preferred, and `callbackMode: self-thread-marker` keeps the role thread recoverable by `read_thread`. The normal order is: first call `send_message_to_thread(sourceThreadId, protocolBlock)`, then output the same protocol block body locally. Include `deliveryStatus: fallback_only` only on the local fallback block when direct-send was unavailable or failed. Use the last matching final callback for fallback/audit reads.

### Reviewer Review

```text
TEAM_ROUTER_REVIEW_REQUEST taskId=<taskId>
callbackMarker: TEAM_ROUTER_REVIEW taskId=<taskId>
sourceThreadId: <manager/orchestrator thread id that receives direct-send first>
sourceRoleThreadId: <reviewer role thread id>
role: Reviewer
returnThreadId: <explicit orchestrator/parent thread id when direct return is available>
orchestratorThreadId: <same current orchestrator/parent thread id>
roleThreadId: <reviewer role thread id>
reviewDelivery: direct-send
reviewFallback: self-thread-marker
permission: read-only | design-only | local-package
scope: <executor scope>

TEAM_ROUTER_REVIEW taskId=<taskId>
sourceThreadId: <manager/orchestrator thread id>
sourceRoleThreadId: <reviewer role thread id>
role: Reviewer
result: pass | needs_rework | blocked
summary: <review summary>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
deliveryStatus: fallback_only
deliveryError: <short error only when direct-send was unavailable or failed>
```
### Verifier Verdict

```text
TEAM_ROUTER_VERIFY taskId=<taskId>
callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>
sourceThreadId: <manager/orchestrator thread id that receives direct-send first>
sourceRoleThreadId: <verifier role thread id>
role: Verifier
returnThreadId: <explicit orchestrator/parent thread id when direct return is available>
orchestratorThreadId: <same current orchestrator/parent thread id>
roleThreadId: <verifier role thread id>
verdictDelivery: direct-send
verdictFallback: self-thread-marker
permission: read-only | design-only | local-package
scope: <executor scope>

TEAM_ROUTER_VERDICT taskId=<taskId>
sourceThreadId: <manager/orchestrator thread id>
sourceRoleThreadId: <verifier role thread id>
role: Verifier
result: pass | needs_rework | blocked
summary: <verdict summary>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
deliveryStatus: fallback_only
deliveryError: <short error only when direct-send was unavailable or failed>
```

Natural-language verdicts do not move state.
