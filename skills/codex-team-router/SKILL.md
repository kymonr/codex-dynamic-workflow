---
name: codex-team-router
description: Use for Codex Team Router orchestration: visible roles, Manager Mode, gates, direct return, architect/qa, self-change, sync gates.
---

# Codex Team Router

Short entrypoint only. Keep this file under the Codex 8KB cap; deep protocol details live in `references/` and are part of the Team Router contract.

Team Router controls Codex desktop role threads, registry/ledger state, direct return, and conditional reviewer gates. Formal conditional roles `architect` and `qa` are documented in `references/conditional-roles.md`.

## Roles

- 调度者 / Orchestrator: parent step choice and closeout.
- 工具宿主边界 / Adapter Host Boundary: callable Codex thread tools.
- 状态控制器 / State Controller: registry, ledger, anchors, transitions.
- 规划者 / Manager: role thread; `TEAM_ROUTER_PLAN`.
- 执行者 / Executor: delegated work; `TEAM_ROUTER_CALLBACK`.
- 审查者 / Reviewer: conditional read-only/adversarial gate; `TEAM_ROUTER_REVIEW`.
- 验证者 / Verifier: final acceptance; `TEAM_ROUTER_VERDICT`.

Visible titles use `角色-任务名`. Manager first renames parent/current to `调度者-Team Router <task>` with callable `set_thread_title`; adapter-created orchestration also requires `parent_thread_id`. Missing either means `tool_error` before child dispatch. Normalize child role titles with `set_thread_title`.

## Manager Mode Hard Rules

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`. Bare `manager` or `team manager` does not trigger Manager Mode; 裸 `manager` 不触发 Manager Mode.

Manager Mode is sticky for the current task and continues an already-active Manager Mode task with terse follow-ups. Terse follow-ups such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `go`, or `do it` authorize only plan/rule refinement, classification, or role dispatch. Manager file edits require current-turn explicit authorization for the exact file-changing task; otherwise dispatch executor/verifier or ask for role switch.

Manager intake separates read-only, dispatch, workspace write, local closeout, and external release gates; ambiguous follow-ups never skip the next gate. Skill/rule/Superpowers write requests such as `记录进skill`, `优化 skill`, or `改规则`, and skill/process requests such as `记录进skill`, `修`, `继续`, or `复利`, still route through executor/reviewer/verifier (executor -> reviewer -> verifier) when the gate applies. Superpowers can guide planning/TDD/debugging/verification, but does not grant manager write authority. `local-package` is executor-only, not manager direct-edit permission.

## Live Boundary

Before live orchestration, probe required Codex app tools and stop with `tool_error` if unavailable:

```text
list_projects -> set_thread_title -> create_thread -> send_message_to_thread -> read_thread
```

Use one role-thread creation path per task. Adapter-created orchestration requires in-process Python callables, `parent_thread_id`, callable `set_thread_title`, and a host heartbeat scheduler for `watch_team_task_with_adapter()` at `firstCheckAt` / `nextAllowedReadAt`. Model-side tool descriptors are not Python callables. Without that contract, status is `tool_error` / `manual orchestration only`; copy-paste prompts are handoff text, not live dispatch evidence. Explain blocked readiness with `assess_live_orchestration_readiness()` / `parent_entry_guard()`.

Reuse existing roles for the same task/task family; rework returns to the original role. Archived role/thread is unavailable for reuse, period: replace it with a non-archived visible role and record the replacement reason; there is no unarchive exception.

## Direct Return

With explicit parent id, role records include `returnThreadId`, `orchestratorThreadId`, and `roleThreadId`. Roles direct-send to `returnThreadId` with `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`, then output the same protocol block body as self-thread-marker fallback. Manager validates `taskId`, protocol-block `sourceThreadId`, `role`, and `sourceRoleThreadId`; malformed returns are recorded for fallback recovery and cannot advance scope. See `references/direct-return.md`.

Team Router dispatch uses Codex desktop thread roles, not `multi_agent_v1` workers/subagents.

## Gates

FAST/NORMAL use executor -> verifier. STRICT/PACKAGE process, role protocol, shared-risk, or same-family discipline changes use executor -> reviewer -> verifier. Completion is direct-return first with bounded `read_thread` fallback. Use `classify_team_router_gate()` for compatibility and `explain_team_router_gate()` when a readable reason is needed.

Small low-risk tasks skip reviewer. Router/manager policy, safety/process/role protocol, and shared/high-risk logic use reviewer(read-only/adversarial) before verifier(read-only acceptance). Reviewer is not final; verifier is. Named reviewer self-changes require a reviewer role thread; no subagent fallback.

## Closeout And Handoff

After completion, default is no role-thread clear and no extra `ROLE_CLOSEOUT`; protocol blocks are anchors. Parent closeout still states changed, verified, accepted by, not done/boundary, risks, next gated step, and `compoundingDecision: recorded | skipped`. Records: durable -> `docs/compounding.md`; task living -> `docs/workbench.md`.

Classify manager actions as `READ_ONLY`, `DISPATCH_ONLY`, `LOCAL_CLOSEOUT`, `WORKSPACE_WRITE`, `HEAVY_OR_RISKY`, or `EXTERNAL_RELEASE`. Terse approvals authorize at most `DISPATCH_ONLY`; workspace writes require explicit `local-package` executor delegation; local closeout needs verifier pass plus explicit commit request; push/PR/merge/deploy/global sync require separate authorization.

Prefer stable file/path handoff. `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` are explicit protocol fields: FAST/NORMAL optional, STRICT recommended, PACKAGE default required unless explicit inline fallback is marked. Review packages supplement protocol blocks. Runtime validates/records supplied path metadata, but does not read, execute, trust, or auto-generate package files.

Role Communication Economy: preserve gates; use protocol block plus stable path references and delta-only follow-up. Put long context in `taskBriefPath`, `executorReportPath`, or `reviewPackagePath`.

Use `scripts/team_router_closeout_check.py` for read-only closeout status: git status, diff files, SKILL size, repo/global skill drift, and unauthorized commit/push/global sync gates. It reports only; it must not sync, stage, commit, push, PR, merge, or deploy.

## References

- `references/manager-mode.md`
- `references/side-effect-taxonomy.md`
- `references/role-handoff-and-review-package.md`
- `references/agent-assist-policy.md`
- `references/direct-return.md`
- `references/manager-polling-cadence.md`
- `references/reviewer-gate.md`
- `references/conditional-roles.md`
- `references/role-closeout.md`
- `references/adapter-runtime.md`
- `references/manual-orchestration.md`
- `references/testing-and-quality-gates.md`
