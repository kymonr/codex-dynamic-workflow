---
name: codex-team-router
description: Use when the user asks for system-version multi-agent coordination with Codex app thread tools, long-lived manager/executor/verifier threads plus a conditional reviewer gate, cross-session team routing, explicitly asks the assistant to act as a team manager, or continues an already-active Manager Mode task with terse follow-ups such as 修, 继续, 处理, go, or do it. Manager Mode is orchestration-only and must not perform implementation work directly.
---

# Codex Team Router

Short entrypoint only. Keep this file under the Codex 8KB cap; deep protocol details live in `references/` and are part of the Team Router contract.

Use Team Router as a Codex desktop thread-tools control plane. It coordinates visible long-lived role threads, records local registry/ledger state, and adds a conditional reviewer gate for high-risk routing work. It does not run a daemon, does not poll unattended, does not push/merge/deploy, and does not treat prompt text as a sandbox.

## Roles

| 中文主名 | English alias | Thread? | Responsibility |
| --- | --- | --- | --- |
| 调度者 | Orchestrator | no | Understand the user goal, choose the next state-machine step, call helpers/tools, and emit handoff or closeout. |
| 工具宿主边界 | Adapter Host Boundary | no | Own real callable access to Codex thread tools. |
| 状态控制器 | State Controller | no | Persist registry, ledger, recovery anchors, state transitions, and user-visible output. |
| 规划者 | Manager | yes | Reply only with `TEAM_ROUTER_PLAN`; define scope, stop condition, risk boundary, and executor prompt. |
| 执行者 | Executor | yes | Follow the delegated work and reply with evidence in `TEAM_ROUTER_CALLBACK`. |
| 审查者 | Reviewer | conditional yes | For router/manager/orchestration policy, permission/safety boundaries, process rules, role protocol, and shared/high-risk logic; perform read-only/adversarial review and reply with `TEAM_ROUTER_REVIEW`. |
| 验证者 | Verifier | yes | Check callback, reviewer requirements when present, evidence, boundary, and risks, then reply with `TEAM_ROUTER_VERDICT`; verifier remains final acceptance. |

Visible Codex desktop thread titles use `角色-任务名`, e.g. `调度者-Team Router <task>` and `执行者-Team Router <task>`; when acting as manager, rename the current/parent conversation itself, not only child role threads. Normalize role threads with `set_thread_title`.

## Manager Mode Hard Rule

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`. Bare `manager` or `team manager` does not trigger Manager Mode; 裸 `manager` 不触发 Manager Mode.

Manager Mode is sticky for the current task after it is triggered. Terse follow-ups such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` authorize only plan refinement, rule updates, or executor/verifier dispatch. Manager/dispatcher file changes are opt-in: prompt before commit/PR/release, and do other file edits only when the user explicitly says in the current turn that you should do that exact work; otherwise dispatch executor or ask for role switch.

## Minimal Live Tool Order

Before live orchestration, probe the Codex app tools and stop with `tool_error` if required tools are unavailable:

```text
list_projects -> create_thread -> send_message_to_thread -> read_thread
```

Use exactly one role-thread creation path per task. If callable adapter tools are unavailable, use the manual/pre-created continuation and existing role bindings instead of the adapter runner.

## Direct Return

When an explicit orchestrator/parent id is available, prompts/ledger records include `returnThreadId`, `orchestratorThreadId`, and `roleThreadId`. Roles direct-send their final marker to `returnThreadId`, keep self-thread markers as fallback/audit anchors, and use the role-specific delivery/fallback fields. Manager validates sourceThreadId, taskId, expected marker, return/orchestrator target, and role/source; duplicate direct callbacks are ignored after ledger advance. watcher/heartbeat remains the 5 minutes fallback. See `references/direct-return.md`.

Team Router role dispatch must use Codex desktop thread roles for executor, reviewer, and verifier. Do not use `multi_agent_v1` workers/subagents as Team Router role threads: they may lack `send_message_to_thread` and cannot provide reliable direct-return. If a role thread is archived, broken, or lacks thread-tool capability, create or reuse a proper Codex thread role before dispatching work that expects role-to-manager callback.

## Fast Lane

Fast Lane policy: classes are FAST, NORMAL, STRICT, PACKAGE. Completion is direct-return first with bounded read_thread fallback; FAST docs/BOM/single phrase rework and NORMAL small focused code/test work use executor -> verifier, while STRICT Team Router process/permission/safety/role protocol/shared-risk changes and PACKAGE same task family discipline hardening use executor -> reviewer -> verifier.

## Conditional Reviewer Gate

Ordinary small fixes and clearly low-risk tasks use executor -> verifier. Router/manager/orchestration policy, permission or safety boundary rules, process rules, role protocol, and shared/high-risk logic must use executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance). Reviewer is not final acceptance; verifier remains final acceptance. When the user names `reviewer` for Team Router self changes, use a reviewer role conversation/thread; if none exists, create/register it or stop and report it. subagent fallback is not allowed.

## roleCloseoutPolicy

After task completion, default is 不 clear role thread and no extra `ROLE_CLOSEOUT` to role threads. Protocol blocks are sufficient role-thread anchors. Parent manager still gives the user a plain-language closeout after every completed flow: changed, verified, accepted by, not done, risks, next gated step. compact is native operation, not chat prompt; do not send `compact` or `ROLE_CLOSEOUT` text to pretend context compression happened. If no compact tool is available, do nothing.

## sideEffectTaxonomy

Classify manager actions as `READ_ONLY`, `DISPATCH_ONLY`, `LOCAL_CLOSEOUT`, `WORKSPACE_WRITE`, `HEAVY_OR_RISKY`, or `EXTERNAL_RELEASE`. In active Manager Mode, terse approvals such as `可以`, `修`, `继续`, `开始修`, `先修`, `修这个`, or `do it` authorize at most `DISPATCH_ONLY`; `WORKSPACE_WRITE` requires explicit `local-package` executor delegation and required gates unless the user explicitly switches roles and authorizes manager file edits in the current turn, `LOCAL_CLOSEOUT` requires verifier pass plus an explicit commit request, and `EXTERNAL_RELEASE` always needs separate authorization.

## roleHandoffPolicy / reviewPackagePolicy

Prefer stable file/path handoff over accumulated chat history when role threads share the workspace. Keep role prompts short: task id, objective, expected marker, permission boundary, relevant `taskBriefPath` / `executorReportPath` / `reviewPackagePath`, and exact return protocol. These path fields are explicit protocol fields with gate expectations: FAST/NORMAL optional, STRICT recommended, PACKAGE default required unless explicit inline fallback is marked. Review packages are preferred evidence bundles for high-risk Team Router self changes and long executor results; they supplement but never replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`. Runtime validates/records supplied path metadata, but does not read, execute, trust, or auto-generate package files.

## References

Read only the relevant deep reference for the current step:

- `references/manager-mode.md`
- `references/side-effect-taxonomy.md`
- `references/role-handoff-and-review-package.md`
- `references/agent-assist-policy.md`
- `references/direct-return.md`
- `references/manager-polling-cadence.md`
- `references/reviewer-gate.md`
- `references/role-closeout.md`
- `references/adapter-runtime.md`
- `references/manual-orchestration.md`
- `references/testing-and-quality-gates.md`
