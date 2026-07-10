---
name: codex-team-router
description: "Use when the user explicitly requests Codex Team Router, Manager Mode, visible role threads, or Team Router gates."
---

# Codex Team Router

Short entrypoint only. Keep under the Codex 8KB cap; deep protocol details live in `references/` and are part of the Team Router contract.

Team Router controls Codex desktop role threads, registry/ledger, direct return, and reviewer gates. architect/qa details: `references/conditional-roles.md`.

## Roles

- 调度者 / Orchestrator: parent step choice and closeout.
- 工具宿主边界 / Adapter Host Boundary: callable Codex thread tools.
- 状态控制器 / State Controller: registry, ledger, anchors, transitions.
- 规划者 / Manager: role thread; `TEAM_ROUTER_PLAN`.
- 执行者 / Executor: delegated work; `TEAM_ROUTER_CALLBACK`.
- 审查者 / Reviewer: conditional read-only/adversarial gate; `TEAM_ROUTER_REVIEW`.
- 验证者 / Verifier: final acceptance; `TEAM_ROUTER_VERDICT`.

Visible titles use `角色-任务名`. Title changes require explicit current-turn authorization and do not occur merely because Manager Mode was activated. Under that authorization, rename parent/current to `调度者-Team Router <task>` with callable `set_thread_title`; adapter-created orchestration also requires `parent_thread_id`. Missing either means `tool_error` before child dispatch. Normalize child role titles with `set_thread_title` only inside an authorized dispatch gate.

## Manager Mode Hard Rules

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`. Bare `manager` or `team manager` does not trigger Manager Mode; 裸 `manager` 不触发 Manager Mode.

Manager Mode is sticky for the current task and continues an already-active Manager Mode task with terse follow-ups. Terse follow-ups such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `go`, or `do it` authorize only plan/rule refinement, classification, or preparation of a dispatch proposal; they do not authorize `create_thread`, message dispatch, or ledger writes. Manager file edits require current-turn explicit authorization for the exact file-changing task; otherwise propose executor/verifier routing or ask for role switch.

Manager intake separates read-only, dispatch, workspace write, local closeout, and external release gates; ambiguous follow-ups never skip the next gate. Skill/rule/process writes route executor -> reviewer -> verifier when applicable. Superpowers grants no manager write authority. `local-package` is executor-only.

Daily Manager shortcut: `references/manager-quick-card.md`.

## Live Boundary

Before live orchestration, probe required Codex app tools and stop with `tool_error` if unavailable:

```text
list_projects -> set_thread_title -> create_thread -> send_message_to_thread -> read_thread
```

Use one role-thread creation path per task. Adapter-created orchestration requires in-process Python callables, `parent_thread_id`, callable `set_thread_title`, and a host heartbeat scheduler for `watch_team_task_with_adapter()` at `firstCheckAt` / `nextAllowedReadAt`. Model-side tool descriptors are not Python callables. Without that contract, status is `tool_error` / `manual orchestration only`; copy-paste prompts are handoff text, not live dispatch evidence. Explain blocked readiness with `assess_live_orchestration_readiness()` / `parent_entry_guard()`.

Active role wait: `active`/`inProgress`/`running`/`working` means normal processing, not stuck. do not restart/replace or send shorter delta while active. Poll: one first check, then `10s -> 20s -> 40s` or `firstCheckAt`/`nextAllowedReadAt`; do not repeat unchanged active status; one timeout notice max.

Reuse existing roles for the same task/task family; rework returns to the original role. Archived role/thread is unavailable for reuse, period: replace it with a non-archived visible role and record the replacement reason; there is no unarchive exception.

## Direct Return

With explicit parent id, role records include `returnThreadId`, `orchestratorThreadId`, and `roleThreadId`. Roles direct-send to `returnThreadId` with `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`, then output the same protocol block body as self-thread-marker fallback. Manager validates `taskId`, protocol-block `sourceThreadId`, `role`, and `sourceRoleThreadId`; malformed returns are recorded for fallback recovery and cannot advance scope. See `references/direct-return.md`.

Team Router dispatch uses Codex desktop thread roles, not collaboration subagents.

## Gates

FAST/NORMAL use executor -> verifier. STRICT/PACKAGE process, role protocol, shared-risk, or same-family discipline changes use executor -> reviewer -> verifier. Completion is direct-return first with bounded `read_thread` fallback. Use `classify_team_router_gate()` for compatibility and `explain_team_router_gate()` when a readable reason is needed.

Small low-risk tasks skip reviewer. Router/manager policy, safety/process/role protocol, and shared/high-risk logic use reviewer(read-only/adversarial) before verifier(read-only acceptance). Reviewer is not final; verifier is. Named reviewer self-changes require a reviewer role thread; no subagent fallback. If a review-only request requires a reviewer and no authorized visible reviewer role already exists, report the blocker; do not create one under the review-only gate.

## Lifecycle Gates

- Brainstorming/planning, design acceptance, implementation, verification, closeout file writes, commit, and create task actions are separate gates.
- `review-only` and verification-only requests do not edit files, create visible roles/tasks, send role messages, or write registry/ledger state.
- Design acceptance does not authorize implementation, closeout, commit, or create task actions. A named-fix request stays within its authorized findings and files.
- `create_thread`, role dispatch, and registry/ledger writes require an explicit current-turn create task or dispatch request plus a known objective, scope, permission boundary, and stop condition.
- A verifier result produces a user-facing report; closeout file writes and commit still require their own authorization. Stop after the authorized stage.

## Closeout And Handoff

After completion, default is no role-thread clear and no extra `ROLE_CLOSEOUT`; protocol blocks are anchors. Parent closeout still states changed, verified, accepted by, not done/boundary, risks, next gated step, and `compoundingDecision: recorded | skipped`. Records: durable -> `docs/compounding.md`; task living -> `docs/workbench.md`.

Classify manager actions as `READ_ONLY`, `DISPATCH_ONLY`, `LOCAL_CLOSEOUT`, `WORKSPACE_WRITE`, `HEAVY_OR_RISKY`, or `EXTERNAL_RELEASE`. Terse approvals may prepare a dispatch proposal but do not execute `DISPATCH_ONLY`; workspace writes require explicit `local-package` executor delegation; local closeout needs verifier pass plus explicit commit request; push/PR/merge/deploy/global sync require separate authorization.

stable file/path handoff: `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` are explicit protocol fields: FAST/NORMAL optional, STRICT recommended, PACKAGE default required unless explicit inline fallback is marked. Runtime validates/records supplied path metadata, but does not read, execute, trust, or auto-generate package files.

Role Communication Economy: preserve gates; use protocol + paths; long context goes to path fields. No-path `READ_ONLY` reviewer/verifier: Chinese `action:`/`riskBoundary:` plus one-line `reply:`.

Use `scripts/team_router_closeout_check.py` for read-only closeout status: git status, diff files, SKILL size, repo/global skill drift, and unauthorized commit/push/global sync gates. It reports only; it must not sync, stage, commit, push, PR, merge, or deploy.

## References

- `references/manager-mode.md`
- `references/manager-quick-card.md`
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
