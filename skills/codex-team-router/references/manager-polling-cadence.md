# Manager Polling Cadence

When a manager or dispatcher delegates work to a router, executor, reviewer, or verifier, the parent thread must not poll aggressively.

## Core Rule

- After dispatch, give the role thread time to work.
- Do not spam `read_thread` every few seconds just because the task was freshly assigned.
- User-facing progress updates still matter, but updates do not require frequent polling.

## First Check

- Wait a reasonable initial interval before the first status check.
- For ordinary background roles, one short observation-only first check at `firstCheckAt` is allowed right after dispatch/read registration so fast completions can be received without waiting for the full heartbeat window.
- After that single first check, set `lastReadAt` to the observation time and move `nextAllowedReadAt` to at least `lastReadAt + 300 seconds`; ordinary proactive polling then returns to the 5 minutes / 300 second minimum heartbeat unless the current user explicitly asks for status/stop/immediate handling.

## Backoff

- Use backoff for follow-up checks instead of fixed short intervals.
- A normal pattern is one ordinary heartbeat no more frequently than every 5 minutes for the same role/thread; do not shrink the cadence just because the role has not pushed a reply.
- Do not perform multiple `read_thread` calls within a few seconds unless there is a concrete reason to intervene immediately.

## When To Read Or Intervene

- Read or intervene when the expected timeout window has been reached.
- Read or intervene when the role thread appears idle or completed.
- Read or intervene when the user asks for status.
- Read or intervene when the manager needs to send a convergence instruction or otherwise unblock the flow.
- Avoid background curiosity reads that do not change the next action.

## Convergence Discipline

- Convergence prompts must also be used sparingly.
- Usually the manager should let the role thread work for a meaningful interval before sending a nudge.
- Do not send a convergence prompt immediately after dispatch just because no output appeared yet.

## User Updates

- Keep the user informed in plain language about what is happening.
- Summaries should reflect the current state in terms a user can understand.
- A good user update does not require high-frequency polling.

Manager watcher heartbeat contract: ordinary manager watcher/read_thread polling for the same role thread is at most once every 5 minutes (300 seconds). The app or host heartbeat must use the watcher ledger fields role/thread id, expected marker, lastReadAt, firstCheckAt, nextAllowedReadAt, waiting reason, and next manager action to call watch_team_task_with_adapter() at wake time; the helper itself also suppresses repeated scheduled reads before the allowed time unless the read reason is user-triggered status/stop/immediate, timeout, or blocker handling. Run one short observation-only first check at firstCheckAt so very fast role completions can be received immediately; after that single short check, set the next proactive read to at least 300 seconds after that read and return to the normal 5 minutes heartbeat cadence. User-triggered status/stop/immediate requests may bypass the 300 second wait, but active/running role threads still require observation-only waiting and no convergence instruction. Role writing a marker is not receipt by the manager; completion feedback is received only when direct-send reaches the manager inbox or the watcher/heartbeat reads the role thread and captures TEAM_ROUTER_PLAN, TEAM_ROUTER_CALLBACK, TEAM_ROUTER_REVIEW, or TEAM_ROUTER_VERDICT. If a role appears completed or idle without the expected marker, the manager records needs_feedback/missing protocol and asks the same role thread for structured feedback instead of treating the task as successful. When the flow finishes, report the result once in plain language for the user, stop_and_delete_heartbeat for accepted closeout, explicitly say stage/commit/push/PR/publish/release were not done, and keep the manager boundary: the manager/dispatcher does not directly edit files unless the user explicitly authorizes that specific file change; commit/PR/publish/release require a separate prompt and authorization.
## Architect And QA Watcher Paths

See `references/conditional-roles.md` for the conditional role contract.

Watcher fallback uses the pending request anchors already recorded by runtime:

- `architectureReview.request` expects `TEAM_ROUTER_ARCHITECT_REVIEW`; read-window misses move to `architect_review_unreachable` and are recoverable back to `awaiting_architect_review`.
- `qaReview.request` expects `TEAM_ROUTER_QA_REVIEW`; read-window misses move to `qa_review_unreachable` and are recoverable back to `awaiting_qa_review`.

Manager inbox direct-send remains preferred. Watcher capture is bounded fallback recovery, not normal proactive return.
