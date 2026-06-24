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

Visible Codex desktop thread titles use `角色-任务名`, such as `调度者-Team Router role title 规范化` and `执行者-Team Router 管理者模式触发词修复`; normalize the parent/current manager-dispatcher title when the host UI exposes it, and normalize created/discovered role threads immediately with `set_thread_title`.

## Manager Mode Hard Rule

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`. Bare `manager` or `team manager` does not trigger Manager Mode; 裸 `manager` 不触发 Manager Mode.

Manager Mode is sticky for the current task after it is triggered. Terse follow-ups or implementation commands such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` are not execution authorization. Treat them only as permission to refine the plan, propose rule updates, or dispatch/prepare executor/verifier work. Manager Mode 禁止亲自修改文件、跑测试、执行实现命令、commit、push、PR 或 merge. Explicit role switch phrases such as “切回执行者”, “你亲自改代码”, or “按这个 plan 落地” are required before parent-side implementation.

## Minimal Live Tool Order

Before live orchestration, probe the Codex app tools and stop with `tool_error` if required tools are unavailable:

```text
list_projects -> create_thread -> send_message_to_thread -> read_thread
```

Use exactly one role-thread creation path per task. If callable adapter tools are unavailable, use the manual/pre-created continuation and existing role bindings instead of the adapter runner.

## Direct Return

When the parent/manager thread id is available, include `returnThreadId` in executor, reviewer, and verifier prompts. Executor uses `callbackDelivery: direct-send` plus `callbackFallback: self-thread-marker`; reviewer uses `reviewDelivery: direct-send` plus `reviewFallback: self-thread-marker`; verifier uses `verdictDelivery: direct-send` plus `verdictFallback: self-thread-marker`. After writing its marker block in its own thread, the role must call `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_REVIEW/TEAM_ROUTER_VERDICT block>)`. Keep self-thread markers as fallback/audit anchors.

## Fast Lane

Fast Lane policy: classes are FAST, NORMAL, STRICT, PACKAGE. Completion is direct-return first with bounded read_thread fallback; FAST docs/BOM/single phrase rework and NORMAL small focused code/test work use executor -> verifier, while STRICT Team Router process/permission/safety/role protocol/shared-risk changes and PACKAGE same task family discipline hardening use executor -> reviewer -> verifier.

## Conditional Reviewer Gate

Ordinary small fixes and clearly low-risk tasks use executor -> verifier. Router/manager/orchestration policy, permission or safety boundary rules, process rules, role protocol, and shared/high-risk logic must use executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance). Reviewer is not final acceptance; verifier remains final acceptance. When the user names `reviewer` for Team Router self changes, use a reviewer role conversation/thread; if none exists, create/register it or stop and report it. subagent fallback is not allowed.

## roleCloseoutPolicy

After task completion, default is 不 clear role thread and no extra `ROLE_CLOSEOUT` or ordinary closeout message to role threads. final protocol block is the closeout: `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, and `TEAM_ROUTER_VERDICT` are sufficient task-ending anchors. compact is native operation, not chat prompt; do not send `compact` or `ROLE_CLOSEOUT` text to pretend context compression happened. If no compact tool is available, do nothing.

## sideEffectTaxonomy

Classify manager actions as `READ_ONLY`, `DISPATCH_ONLY`, `LOCAL_CLOSEOUT`, `WORKSPACE_WRITE`, `HEAVY_OR_RISKY`, or `EXTERNAL_RELEASE`. In active Manager Mode, terse approvals such as `可以`, `修`, `继续`, `开始修`, `先修`, `修这个`, or `do it` authorize at most `DISPATCH_ONLY`; `WORKSPACE_WRITE` requires executor delegation unless the user explicitly switches roles, `LOCAL_CLOSEOUT` requires verifier pass plus an explicit commit request, and `EXTERNAL_RELEASE` always needs separate authorization.

## roleHandoffPolicy / reviewPackagePolicy

Prefer stable file/path handoff over accumulated chat history when role threads share the workspace. Keep role prompts short: task id, objective, expected marker, permission boundary, relevant `taskBriefPath` / `executorReportPath` / `reviewPackagePath`, and exact return protocol. Review packages are preferred evidence bundles for high-risk Team Router self changes and long executor results; they supplement but never replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`. Package path fields are policy concepts/future optional runtime fields, not implemented runtime fields in this task.

## References

Read only the relevant deep reference for the current step:

- `references/manager-mode.md`
- `references/side-effect-taxonomy.md`
- `references/role-handoff-and-review-package.md`
- `references/direct-return.md`
- `references/reviewer-gate.md`
- `references/role-closeout.md`
- `references/adapter-runtime.md`
- `references/manual-orchestration.md`
- `references/testing-and-quality-gates.md`
