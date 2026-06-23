# Codex Team Router Live Orchestration Runbook

This runbook is the parent-thread entry point for a real Codex desktop smoke. It verifies that `codex-team-router` can use the host thread tools without moving those tools into `src/team_router.py`.

## Preconditions

- The parent thread can call `list_projects`, `create_thread`, `send_message_to_thread`, and `read_thread`.
- The target project is visible in `list_projects`.
- The task is read-only or design-only. Write, commit, push, PR, merge, deploy, real API, account, or production-data work must route to a separately authorized workflow.
- The adapter path requires in-process Python callables owned by the parent host. Model-side Codex app tools are not Python callables and cannot be passed into `src/team_router.py` directly; if no host adapter exists, use the manual/pre-created continuation and feed send/read results back into the helpers.

## Tool Sequence

The live order is:

```text
list_projects -> create_thread -> send_message_to_thread -> read_thread
```

Use `src/team_router.py` helpers to keep state deterministic around those host-tool calls.

## Role Names

Use Chinese role names in user-facing planning and handoff text while preserving English protocol/code aliases:

| 中文主名 | English alias | Thread? | Live responsibility |
| --- | --- | --- | --- |
| 父线程调度者 | Parent Orchestrator | no | Calls tools, advances the state machine, and emits helper output. |
| 工具宿主边界 | Adapter Host Boundary | no | Provides in-process callable access to Codex thread tools. |
| 状态控制器 | State Controller | no | Owns registry, ledger, recovery anchors, and state transitions. |
| 规划者 | Manager | yes | Replies with `TEAM_ROUTER_PLAN`. |
| 执行者 | Executor | yes | Does delegated work and replies with `TEAM_ROUTER_CALLBACK`. |
| 审查者 | Reviewer | conditional yes | Conditional reviewer for router/manager/orchestration policy, permission/safety boundaries, process rules, role protocol, and shared/high-risk logic; performs read-only/adversarial review and replies with `TEAM_ROUTER_REVIEW`. |
| 验证者 | Verifier | yes | Checks callback, reviewer requirements when present, evidence, and boundary, then replies with `TEAM_ROUTER_VERDICT`; verifier remains final acceptance. |

Canonical aliases: 父线程调度者 (Parent Orchestrator), 工具宿主边界 (Adapter Host Boundary), 状态控制器 (State Controller), 规划者 (Manager), 执行者 (Executor), 审查者 (Reviewer), 验证者 (Verifier).

规划者 / 执行者 / 验证者 are default core role threads. 审查者 is a conditional reviewer role thread and should be created or reused only when its gate applies. The parent-side concepts must not create extra threads.

Visible Codex desktop role-thread titles use `角色-任务名`, for example `执行者-管理者模式触发词修复` and `验证者-管理者模式触发词修复`. Do not include the project name by default unless the task name itself would be ambiguous.

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`.

Bare `manager` or `team manager` does not trigger Manager Mode. 裸 `manager` 不触发 Manager Mode; this avoids accidental activation for ordinary implementation requests such as `manager thread`, `manager parser`, or `manager integration`.

Manager Mode is sticky for the current task after it is triggered, and it persists until an explicit role switch. A terse follow-up or implementation command such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` is not execution authorization. Treat those replies only as permission to refine the plan, propose rule updates, or dispatch/prepare executor/verifier work inside Team Router, not as permission for the manager to personally edit files or run project commands.

If implementation is requested during active Manager Mode, produce an executor task, a verifier task, or ask for an explicit role switch. Do not personally edit files or run project commands from Manager Mode unless the user explicitly says “切回执行者”, “你亲自改代码”, or “按这个 plan 落地”.

## Steps

1. Call `list_projects` and select the target project.
2. Resolve a shared `stateRoot` and `projectId`.
3. Run `probe_thread_adapter_capabilities()` if the parent host is using adapter callables.
4. Choose exactly one role-thread creation path for the task. Do not mix the adapter-created and pre-created paths.

### Recommended adapter runner

Use `parent_entry_guard()` at the parent boundary before choosing the adapter-created path. If the host lacks callable thread tools, or the adapter only exposes model-side tool descriptors, the adapter runner is not available. Continue only through the manual/pre-created path with existing `manager` / `executor` / `verifier` role bindings, plus reviewer only when conditional reviewer review is required.

Use `orchestrate_team_task_with_adapter()` when the parent host can pass Codex thread tool callables into Python. The helper probes required thread tools, resolves the current project target with `list_projects`, discovers/reuses role threads with `list_threads`, normalizes titles with `set_thread_title`, starts a missing task, advances the next send/read step, and returns `action`, `status`, `ledger`, `userOutput`, `capabilities`, `codexProjectId`, and `projectTarget`. It is not the entrypoint for pre-created role threads when the host lacks callable tools.

Use a filesystem-safe Team Router `project_id` for local state, such as `codex-dynamic-workflow`. If Codex desktop `list_projects` returns a path-like project id such as `D:\codex\codex-dynamic-workflow`, pass it as `codex_project_id` so target lookup uses the real Codex id while registry and ledger paths stay safe.

Use `run_team_task_with_adapter()` only when the parent has already probed tools and resolved the project target. It is the lower-level runner behind the orchestration entry.

Call it again after a role thread has replied. It stops after sending work to a role thread, after a read that is still waiting/unreachable/blocked, or after terminal closeout. Emit `update["userOutput"]` exactly when the helper returns closeout or handoff content.

Manager waiting policy: `read_thread` polling is allowed only as low-frequency, event-driven waiting. Use one short initial wait when a role may have replied, then default to 30-60s between watcher/read_thread checks or slower for large tasks. Do not surface every poll as user-visible progress; report only status changes, timeout, blocked states, or completion.

Role reuse policy: for the same `taskId` or task family, reuse existing executor, existing reviewer when the conditional reviewer gate applies, and existing verifier threads by default. Rework goes back to the original executor thread, rework review goes back to the original reviewer thread, and rework verification goes back to the original verifier thread. Create a new role thread only when the role boundary, permission boundary, workspace boundary, task-family boundary, or isolation requirement changes.

For direct return, pass the current manager/parent thread id as `returnThreadId` when sending executor dispatches, reviewer requests, and verifier requests. The role prompt should include `callbackDelivery: direct-send` plus `callbackFallback: self-thread-marker` for executor dispatches, `reviewDelivery: direct-send` plus `reviewFallback: self-thread-marker` for reviewer requests, or `verdictDelivery: direct-send` plus `verdictFallback: self-thread-marker` for verifier requests, and instruct the role to call `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_REVIEW/TEAM_ROUTER_VERDICT block>)` after it writes the marker in its own thread; reviewer direct-return specifically requires `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)`, and verifier direct-return specifically requires `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)`. This is possible when the role thread has `send_message_to_thread` access. Manager inbox capture of those direct-return blocks should drive the ledger state machine forward, including review, verifier dispatch, and closeout generation.
Compatibility anchor: executor/verifier direct-return still includes `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_VERDICT block>)`; reviewer adds `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)`.


Conditional reviewer gate: ordinary small fixes and clearly low-risk tasks use executor -> verifier. Router/manager/orchestration policy, permission or safety boundary rules, process rules, role protocol, and shared/high-risk logic must use executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance). The reviewer independently looks for design risks, rule gaps, omissions, and new bad modes; it does not implement changes and is not final acceptance. The verifier remains final acceptance and confirms the executor result plus any reviewer requiredChanges are satisfied. Runtime adapters execute this gate with `send_reviewer_request_with_adapter()`, `read_reviewer_review_update_with_adapter()`, and `capture_reviewer_review_from_read()`: reviewer `pass` continues to verifier, reviewer `needs_rework` returns to executor rework, and reviewer `blocked` blocks the task. When the user names `reviewer` for Team Router self changes, the manager must use a reviewer role conversation/thread; if no existing reviewer thread exists, explicitly create/register reviewer role conversation or stop and report it. subagent fallback is not allowed. Trigger logic covers `runtime gate`, `reviewer gate`, `Team Router self changes`, and `Team Router` combined with reviewer/runtime/protocol/policy/permission/safety/process/shared/high-risk semantics; a plain `team_router.py` filename or low-risk docs-only/single-file cleanup does not trigger reviewer by itself.

For hosts without direct return, missed direct delivery, or recovery audits, run `watch_team_task_with_adapter()` from scheduler/automation. The watcher reads the ledger/registry recovery anchor, calls `read_thread`, captures role-thread replies including reviewer reviews, sends the next safe parent-side message when possible, and returns `action`, `status`, `userOutput`, `nextWakeup`, and `automationBoundary`. When `nextWakeup` is not null, schedule another watcher call for that role/anchor. Watcher polling is the fallback path, not the only possible Desktop thread-to-thread return path.

When the verifier returns `needs_rework`, the runner stops with `action: needs_rework_pending`. Call it with `confirm_rework=True` only after the user approves another executor dispatch.

### Adapter-created roles path

Use this path when the parent host can pass Codex thread tool callables into Python.

1. Prefer `orchestrate_team_task_with_adapter()` for normal parent orchestration.
2. Use `start_team_task_with_adapter()` only when testing or manually driving the lower-level start primitive.
3. Let the helper reuse registry role bindings and call `create_thread` through the adapter only for missing manager/executor/verifier core role threads; create or reuse reviewer only when the conditional reviewer gate applies.
4. Let the helper persist registry role bindings and create the task ledger.
5. Do not pre-call `create_thread` for role threads before calling `start_team_task_with_adapter()`.

### Pre-created roles path

Use this path when the parent thread manually calls Codex app tools or the host cannot pass tool callables into Python.

1. Create missing role threads with `create_thread`:
   - manager prompt: role `manager`, wait for `TEAM_ROUTER_PLAN`.
   - executor prompt: role `executor`, wait for `TEAM_ROUTER_CALLBACK`.
   - reviewer prompt when the conditional reviewer gate applies: role `reviewer`, wait for `TEAM_ROUTER_REVIEW`.
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

Use this continuation when the parent thread directly invokes Codex app tools or the host cannot pass tool callables into Python. This path uses manual helper/record/capture functions; it does not continue through `orchestrate_team_task_with_adapter()` or `run_team_task_with_adapter()`. `parent_entry_guard(...precreated_roles...)` is only a boundary decision and prompt aid here, not an end-to-end adapter-runner entrypoint.

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

The fixture `tests/fixtures/team_router/live_manager_inbox_direct_return.json` is a sanitized representative manager-inbox direct-return result. It must prove that `normalize_thread_read_messages()` unwraps the `TEAM_ROUTER_CALLBACK`, preserves `sourceThreadId`, and keeps the numeric timestamp available before the parent state machine captures direct return.

The fixture `tests/fixtures/team_router/three_role_visible_smoke_scenarios.json` snapshots the visible three-role mode. It must keep these paths represented:

- `direct-send-callback-success`: executor direct return reaches the parent inbox and records `returnThreadId`, `returnSearchAnchor`, and `fallbackSearchAnchor`.
- `direct-send-missed-self-thread-fallback`: manager inbox misses direct return, so the self-thread marker and `read_thread searchAnchor` recover the callback.
- `verifier-needs-rework`: verifier returns `needs_rework`; parent stops until user approval before redispatch.
- `verifier-blocked-closeout`: verifier returns `blocked`; parent emits `Team Router Closeout` with remaining work.

## Expected User Output

For a passing verifier result, the parent thread must display the helper output, not a rewritten summary:

```text
Team Router Closeout
taskId: <taskId>
status: done
threads:
  manager: <threadId>
  executor: <threadId>
  reviewer: <threadId when conditional reviewer gate applied>
  verifier: <threadId>
summary: <verifier summary>
evidenceChecked: <checked evidence>
risks: <none or risks>
nextAction: none
remainingTodos: none
```

For a non-terminal task, display the handoff so the next parent turn can resume from ledger/registry anchors. All closeout or handoff user output must include `remainingTodos`; passing verifier closeouts use `remainingTodos: none`, while `needs_rework` and `blocked` use the verifier `requiredChanges` or derived `nextAction`.
