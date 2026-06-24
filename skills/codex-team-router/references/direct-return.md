# Direct Return

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep direct-return details here.

For direct return, pass the current manager/parent thread id as `returnThreadId` when building executor dispatches, reviewer requests, and verifier requests.

Executor prompts must include `callbackDelivery: direct-send` plus `callbackFallback: self-thread-marker`.

Reviewer prompts must include `reviewDelivery: direct-send` plus `reviewFallback: self-thread-marker`.

Verifier prompts must include `verdictDelivery: direct-send` plus `verdictFallback: self-thread-marker`.

The role prompt must tell the role to call `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_REVIEW/TEAM_ROUTER_VERDICT block>)` after it writes the marker in its own thread.

Compatibility anchors:

- executor direct-return specifically includes `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK block>)`.
- reviewer direct-return specifically requires `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)`.
- verifier direct-return specifically requires `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)`.
- older executor/verifier compatibility still includes `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_VERDICT block>)`.

Manager inbox capture is part of the ledger state machine: a direct-return callback, review, or verdict captured from the return thread must update ledger state, not just notify the manager. Keep `self-thread-marker` as the fallback/audit path.

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
returnThreadId: <manager thread id when direct return is available>
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

Use `callbackDelivery: direct-send` when a manager/parent `returnThreadId` is available and the role can call `send_message_to_thread`; keep `callbackMode: self-thread-marker` so the role thread remains recoverable by `read_thread`. Use the last matching final callback for fallback/audit reads.

### Verifier Verdict

```text
TEAM_ROUTER_VERIFY taskId=<taskId>
callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>
returnThreadId: <manager thread id when direct return is available>
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
