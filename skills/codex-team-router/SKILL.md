---
name: codex-team-router
description: Use for Codex desktop Team Router orchestration with visible manager/executor/verifier threads, a conditional reviewer gate, cross-session routing, explicit team-manager requests, or continues an already-active Manager Mode task with terse follow-ups. Manager Mode is orchestration-only.
---

# Codex Team Router

Short entrypoint only. Keep this file under the Codex 8KB cap; deep protocol details live in `references/` and are part of the Team Router contract.

Team Router is a Codex desktop thread-tools control plane: visible long-lived role threads, local registry/ledger state, and a conditional reviewer gate. It does not run a daemon, poll unattended, push/merge/deploy, or treat prompt text as a sandbox.

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

Visible thread titles use `角色-任务名`. Manager first renames the parent/current conversation to `调度者-Team Router <task>` before child dispatch; adapter-created orchestration requires `parent_thread_id` plus callable `set_thread_title`, otherwise return `tool_error` / blocked. Normalize role threads with `set_thread_title`.

## Manager Mode Hard Rule

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`. Bare `manager` or `team manager` does not trigger Manager Mode; 裸 `manager` 不触发 Manager Mode.

Manager Mode is sticky for the current task. Terse follow-ups such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `go`, or `do it` authorize only plan/rule refinement, classification, or role dispatch. Manager file edits require current-turn explicit authorization for the exact file-changing task; otherwise dispatch executor/verifier or ask for role switch.
Manager intake separates read-only, dispatch, workspace write, local closeout, and external release gates; ambiguous follow-ups never skip the next gate.
Skill/rule/Superpowers write requests such as `记录进skill`, `改进skill`, `superpowers修`, or `写进规则` still route through executor/reviewer/verifier. Manager classifies and delegates exact `local-package` scope; `local-package` is executor-only, not manager direct-edit permission.

## Minimal Live Tool Order

Before live orchestration, probe required Codex app tools and stop with `tool_error` if unavailable:

```text
list_projects -> set_thread_title -> create_thread -> send_message_to_thread -> read_thread
```

Use one role-thread creation path per task. Reuse existing roles for the same task/task family; rework returns to the original role. Archived role/thread is unavailable for reuse, period: replace it with a non-archived visible role and record the replacement reason; there is no unarchive exception. Create replacements only for concrete unavailable/archived/broken/invalid role state or real boundary/capability change. If adapter callables are unavailable, use manual/pre-created continuation with existing bindings.

## Direct Return

When an explicit parent id is available, records include `returnThreadId`, `orchestratorThreadId`, and `roleThreadId`. Roles direct-send final markers to `returnThreadId` and keep self-thread markers as fallback. Bare `create_thread` plus `read_thread` is not formal return; manually created roles must be registered, dispatched with return metadata, and captured by direct-send or watcher ledger advancement. Manager validates source/task/marker/role ids; duplicates are ignored after ledger advance. Watcher heartbeat remains the 5 minute fallback. See `references/direct-return.md`.

Team Router dispatch uses Codex desktop thread roles, not `multi_agent_v1` workers/subagents, because role threads need thread tools and reliable direct-return.

## Fast Lane

Fast Lane: FAST/NORMAL use executor -> verifier; STRICT/PACKAGE process, role protocol, shared-risk, or same-family discipline changes use executor -> reviewer -> verifier. Completion is direct-return first with bounded `read_thread` fallback; CRLF/LF normalization escalates only for semantic/process risk.

## Conditional Reviewer Gate

Small low-risk tasks use executor -> verifier. Router/manager policy, safety/process/role protocol, and shared/high-risk logic use executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance). Reviewer is not final; verifier is. Named reviewer self-changes require a reviewer role thread; no subagent fallback.

## roleCloseoutPolicy

After completion, default is 不 clear role thread and no extra `ROLE_CLOSEOUT`; protocol blocks are anchors. Parent manager still gives plain-language closeout: changed, verified, accepted by, not done, risks, next gated step. compact is native, not chat prompt. Records: durable -> `docs/compounding.md`; task living -> `docs/workbench.md`.

## sideEffectTaxonomy

Classify manager actions as `READ_ONLY`, `DISPATCH_ONLY`, `LOCAL_CLOSEOUT`, `WORKSPACE_WRITE`, `HEAVY_OR_RISKY`, or `EXTERNAL_RELEASE`. In Manager Mode, terse approvals authorize at most `DISPATCH_ONLY`; workspace writes require explicit `local-package` executor delegation and gates, local closeout needs verifier pass plus explicit commit request, and external release needs separate authorization.

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
