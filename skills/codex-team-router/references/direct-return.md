# Direct Return

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep direct-return details here.

Direct return is the primary completion path when the current orchestrator/parent thread id is known. The role still writes its final marker in its own thread, then sends the same marker block back to the parent with `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_REVIEW/TEAM_ROUTER_VERDICT block>)`.

Use these explicit fields together:

- `returnThreadId`: the current orchestrator/parent thread that should receive the direct callback.
- `orchestratorThreadId`: the same parent/orchestrator thread id recorded for audit and validation.
- `roleThreadId`: the executor/reviewer/verifier thread expected to send the callback.

Do not default `returnThreadId` to the manager/planner role thread. If no explicit parent/source thread id is available, omit direct-send metadata and rely on watcher/heartbeat fallback.

Prompt metadata by role:

- executor: `callbackDelivery: direct-send` plus `callbackFallback: self-thread-marker`.
- reviewer: `reviewDelivery: direct-send` plus `reviewFallback: self-thread-marker`.
- verifier: `verdictDelivery: direct-send` plus `verdictFallback: self-thread-marker`.

Compatibility anchors:

- executor direct-return specifically includes `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK block>)`.
- reviewer direct-return specifically requires `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)`.
- verifier direct-return specifically requires `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)`.
- older executor/verifier compatibility still includes `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_VERDICT block>)`.

Manager inbox capture is part of the ledger state machine. A direct-return callback, review, or verdict captured from the return thread must update ledger state, not just notify the manager.

Manager inbox validation requirements:

- validate `taskId` against the active ledger task.
- validate `sourceThreadId` against the expected `roleThreadId` / role thread record.
- validate the expected marker: `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`.
- consume the callback only while the ledger is currently awaiting that role result, including that role's `needs_feedback` recovery state.

Duplicate direct callbacks are ignored after the ledger advances past that role. Do not record duplicate observations and do not let old executor/reviewer/verifier callbacks trigger the next state twice.

Keep `self-thread-marker` as the fallback/audit path. If direct-send is unavailable or misses delivery, watcher/heartbeat must read the role thread at the normal 5 minutes / 300 seconds fallback cadence and capture the self-thread marker.

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
status: done | blocked
final: true
summary: <3-7 lines>
evidence: <paths, command summaries, or thread observations>
risks: <none or risks>
next: <none or next step>
```

Use `callbackDelivery: direct-send` when an explicit orchestrator/parent `returnThreadId` is available and the role can call `send_message_to_thread`; direct-send return is preferred, and `callbackMode: self-thread-marker` keeps the role thread recoverable by `read_thread`. Use the last matching final callback for fallback/audit reads.

### Reviewer Review

```text
TEAM_ROUTER_REVIEW_REQUEST taskId=<taskId>
callbackMarker: TEAM_ROUTER_REVIEW taskId=<taskId>
returnThreadId: <explicit orchestrator/parent thread id when direct return is available>
orchestratorThreadId: <same current orchestrator/parent thread id>
roleThreadId: <reviewer role thread id>
reviewDelivery: direct-send
reviewFallback: self-thread-marker
permission: read-only | design-only | local-package
scope: <executor scope>

TEAM_ROUTER_REVIEW taskId=<taskId>
result: pass | needs_rework | blocked
summary: <review summary>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
```
### Verifier Verdict

```text
TEAM_ROUTER_VERIFY taskId=<taskId>
callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>
returnThreadId: <explicit orchestrator/parent thread id when direct return is available>
orchestratorThreadId: <same current orchestrator/parent thread id>
roleThreadId: <verifier role thread id>
verdictDelivery: direct-send
verdictFallback: self-thread-marker
permission: read-only | design-only | local-package
scope: <executor scope>

TEAM_ROUTER_VERDICT taskId=<taskId>
result: pass | needs_rework | blocked
summary: <verdict summary>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
```

Natural-language verdicts do not move state.
