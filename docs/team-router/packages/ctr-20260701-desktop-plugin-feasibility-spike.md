# ctr-20260701-desktop-plugin-feasibility-spike

## Package Metadata

- taskId: `ctr-20260701-desktop-plugin-feasibility-spike`
- branch: `codex/desktop-plugin-feasibility-spike`
- permission: original feasibility-spike package plus separately authorized live smoke follow-up. This follow-up includes doc-only evidence update, reviewer/verifier re-check, and local commit after gates. Runtime implementation, push, PR, merge, deploy, publish/release, and global skill sync are not included.
- scope: `docs/workbench.md`, this package file, and read-only feasibility evidence for Codex Desktop/plugin callable availability.

## Objective

Confirm one thing only: whether Codex Desktop/plugin can provide callable Team Router host tools for:

- `create_thread`
- `read_thread`
- `send_message_to_thread`
- `set_thread_title`
- scheduler/broker startup capability

The package should answer availability and invocation boundary. It should not change runtime behavior.

## Boundary

Included:

- Record this active package and its narrow feasibility target.
- Collect current-environment evidence for whether the named callables are exposed to this Codex session or can be supplied by a Desktop/plugin path.
- Distinguish model-side tool descriptors, MCP/plugin tool discovery, and in-process Python callables.
- State whether scheduler/broker startup is callable from the current Desktop/plugin surface or remains external/manual.

Excluded:

- No Team Router runtime implementation, adapter rewrite, watcher behavior change, scheduler daemon, broker service, production startup, thread creation smoke, push, PR, merge, deploy, publish/release, or global skill sync unless separately authorized.
- No claim that a displayed tool name is an in-process Python callable without direct evidence.
- No live thread creation or message send unless separately authorized as a feasibility smoke.

## Feasibility Questions

- Does this Codex Desktop session expose `create_thread`, `read_thread`, `send_message_to_thread`, and `set_thread_title` as callable tools?
- If exposed through plugin discovery, are they callable by this agent directly, or only visible as product/app capabilities?
- Can scheduler/broker startup be initiated through Desktop/plugin tooling, or only through a local process/CLI outside Team Router?
- What exact evidence should `assess_live_orchestration_readiness()` or a future host-readiness snapshot trust?

## Role Thread Instructions

- Executor: gather only feasibility evidence for the named callables and scheduler/broker startup. Do not implement runtime behavior.
- Reviewer: verify the evidence proves callable availability or non-availability without overclaiming.
- Verifier: accept only if the package cleanly answers the narrow feasibility target and preserves no-implementation boundary.


## Executor Feasibility Evidence

- Tool discovery in the controller session reported `codex_app` tool descriptors for `create_thread`, `read_thread`, `send_message_to_thread`, `set_thread_title`, `list_projects`, and `list_threads`. Initial reviewer required mutating-tool claims to stay descriptor-observed until a separate live smoke was authorized.
- Read-only `codex_app.list_projects()` succeeded and returned project `D:\codex\Team Router` with host `local`.
- Read-only `codex_app.list_threads(query="Team Router")` succeeded and returned Team Router threads, including active thread `019f1df4-cae0-7dd3-9ed0-9e0b7f0b63c4`.
- Read-only `codex_app.read_thread(threadId="019f1df4-cae0-7dd3-9ed0-9e0b7f0b63c4", hostId="local")` succeeded and returned recent turns from this active thread.
- After separate live smoke authorization, `create_thread`, `send_message_to_thread`, and `set_thread_title` were invoked against smoke thread `019f1e10-cb80-7321-af2a-e7a4b2c45820`; all three are now smoke-proven for the current Codex Desktop session. `set_thread_title` failed once immediately after creation with `No Codex thread found...`, then succeeded on retry, so callers should use short retry/backoff after `create_thread`.
- CodeGraph evidence: `src/team_router_host_runtime.py` requires in-process Python callables for the thread adapter, a `parent_thread_id`, and a callable heartbeat scheduler before live orchestration is ready. Model-side tool descriptors still need a host adapter wrapper before Team Router runtime can use them as Python callables.
- CodeGraph evidence: `src/team_router_broker_adapter.py` provides `CodexAppThreadAdapter.create_thread/read_thread/send_message_to_thread/set_thread_title` methods and `BrokerHeartbeatScheduler.schedule()`, but these call a localhost broker; they do not start the broker.
- `py -B scripts\team_router_broker_feasibility_check.py --json` without broker args returned `status: blocked`, missing `broker-url` and `session-token`.
- `py -B -m unittest tests.test_team_router.TestTeamRouterBrokerFeasibilityScript -v` -> Ran 6 tests OK.
- `py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_heartbeat_scheduler_posts_only_allowed_watcher_callback tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_returns_heartbeat_scheduler_after_task_4 -v` -> Ran 2 tests OK.

## Feasibility Verdict

- Current Codex Desktop/plugin session smoke-proved `create_thread`, `read_thread`, `send_message_to_thread`, and `set_thread_title` as model-side Codex app tools.
- `read_thread` is proven callable by a successful read-only invocation.
- `create_thread`, `send_message_to_thread`, and `set_thread_title` are smoke-proven at the Codex app tool layer, but this still does not make them in-process Python callables for Team Router runtime without an adapter wrapper.
- Team Router runtime still cannot treat model-side tool descriptors as in-process Python callables by itself. Runtime readiness needs an adapter wrapper such as the existing localhost broker adapter plus broker readiness including `parentThreadId` and runtime probe.
- No Desktop/plugin callable for scheduler/broker startup was exposed in this session. Existing repo code can call `/scheduler/wake` through `BrokerHeartbeatScheduler` only after an external broker exists and supplies URL/token/readiness.

## Live Smoke Evidence

- Separate authorization granted for live smoke after local closeout commit `9c68c34`.
- `codex_app.list_projects()` succeeded and returned project `D:\codex\Team Router`.
- `codex_app.create_thread(target project D:\codex\Team Router local)` succeeded with thread `019f1e10-cb80-7321-af2a-e7a4b2c45820`.
- Initial smoke thread replied exactly:
  - `TEAM_ROUTER_SMOKE_ACK`
  - `status: ready`
  - `summary: create_thread succeeded`
- `codex_app.send_message_to_thread(threadId="019f1e10-cb80-7321-af2a-e7a4b2c45820")` succeeded.
- Follow-up smoke reply was exactly:
  - `TEAM_ROUTER_SMOKE_ACK`
  - `status: followup_received`
  - `summary: send_message_to_thread succeeded`
- `codex_app.read_thread(threadId="019f1e10-cb80-7321-af2a-e7a4b2c45820")` succeeded and returned both smoke turns.
- `codex_app.set_thread_title(threadId="019f1e10-cb80-7321-af2a-e7a4b2c45820")` first returned `No Codex thread found for threadId: 019f1e10-cb80-7321-af2a-e7a4b2c45820`, then succeeded on retry.
- Final `read_thread` confirmed title `smoke-Team Router Desktop callable test`.
## Verification Record

- Package opened from clean `master` baseline on `codex/desktop-plugin-feasibility-spike`.
- Executor feasibility evidence collected and recorded in this package.
- Reviewer v1 returned needs_rework for mutating-tool overclaim and incomplete plan status; package/workbench/plan reworked to mark `create_thread`, `send_message_to_thread`, and `set_thread_title` as descriptor-observed / not smoke-proven.
- Reviewer v2: pass; `requiredChanges: none`; risk retained that live smoke needs separate authorization.
- Verifier: accepted; `requiredChanges: []`; confirmed package target and evidence boundary, no runtime implementation, no live smoke at that gate, no push/PR/sync.
- Local closeout: commit `9c68c34` recorded the evidence-only package closeout; later live smoke was separately authorized and this follow-up records that evidence only.
- Live smoke reviewer: pass; `requiredChanges: none`; confirmed app-tool-layer smoke conclusion stays bounded and runtime/broker/scheduler non-readiness remains explicit.
- Live smoke verifier: accepted; `requiredChanges: none`; confirmed doc-only closeout may proceed to local commit, with no push/PR/merge/deploy/publish/global sync.

## Review And Verification Gate

Current next gate: none after this doc-only live-smoke closeout commit.

push, PR, merge, deploy, publish/release, additional live thread smoke, scheduler/broker startup, and global skill sync remain outside this package unless separately authorized.
