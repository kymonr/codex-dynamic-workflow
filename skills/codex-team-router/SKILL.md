---
name: codex-team-router
description: "Use when the user explicitly requests Codex Team Router, Manager Mode, visible role threads, or Team Router gates."
---

# Codex Team Router

Short entrypoint only. Keep under the Codex 8KB cap; deep protocol details live in `references/` and are part of the Team Router contract.

Team Router controls Codex desktop role threads, registry/ledger, direct return, and reviewer gates. architect/qa details: `references/conditional-roles.md`.

## Roles

Roles: 调度者/Orchestrator, 工具宿主边界/Adapter Host Boundary, 状态控制器/State Controller, 规划者/Manager (`TEAM_ROUTER_PLAN`), 执行者/Executor (`TEAM_ROUTER_CALLBACK`), conditional 审查者/Reviewer (`TEAM_ROUTER_REVIEW`), 验证者/Verifier (`TEAM_ROUTER_VERDICT`). Details: `references/manager-mode.md`.

Visible titles, complete-outcome Executor delegation, and broker-recovery boundaries are versioned in `references/manager-mode.md`. Title changes require explicit current-turn authorization; authorized dispatch also requires callable `set_thread_title` and `parent_thread_id`, or returns `tool_error`.

## Manager Mode Hard Rules

Manager Mode only starts on explicit role-intent phrases: “你是管理者”, “你作为管理者”, “团队管理者”, “进入 Manager Mode”, or `act as team manager`. Bare `manager` or `team manager` does not trigger Manager Mode; 裸 `manager` 不触发 Manager Mode.

Manager Mode is sticky for the current task and continues an already-active Manager Mode task with terse follow-ups. Terse follow-ups such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `go`, or `do it` authorize only plan/rule refinement, classification, or preparation of a dispatch proposal; they do not authorize `create_thread`, message dispatch, or ledger writes. Manager file edits require current-turn explicit authorization for the exact file-changing task; otherwise propose executor/verifier routing or ask for role switch.

Manager intake separates read-only, dispatch, workspace write, local closeout, and external release gates; ambiguous follow-ups never skip the next gate. Skill/rule/process writes route executor -> reviewer -> verifier when applicable. Superpowers grants no manager write authority. `local-package` is executor-only.

Version 2 Manager direct is decided before ledger, title, heartbeat, or thread operations. A standard Manager entry does not select a concrete role model. Explicit cost-aware model entry authorizes Luna Medium, Terra Medium, and Sol High role routing. Bare Manager Mode is proposal-only. See `references/manager-mode.md` for the entry/continuation contract.

Daily Manager shortcut: `references/manager-quick-card.md`.

## Live Boundary

Before live orchestration, probe required Codex app tools and stop with `tool_error` if unavailable:

```text
list_projects -> set_thread_title -> create_thread -> send_message_to_thread -> read_thread
```

Adapter orchestration requires callable thread tools, `parent_thread_id`, `set_thread_title`, and a heartbeat scheduler. Model-side descriptors are not Python callables; otherwise status is `tool_error` / `manual orchestration only`. See `references/adapter-runtime.md` and `references/manager-polling-cadence.md`.

Reuse existing roles for the same task/task family; rework returns to the original role. Archived role/thread is unavailable for reuse, period: replace it with a non-archived visible role and record the replacement reason; there is no unarchive exception.

Luna Medium / Terra Medium / Sol High map to `gpt-5.6-luna + medium`, `gpt-5.6-terra + medium`, and `gpt-5.6-sol + high`. Sol Ultra is forbidden for role dispatch.

## Direct Return

Roles direct-send the protocol block to `returnThreadId`, then emit the same self-thread marker fallback. Validate `taskId`, `sourceThreadId`, `role`, and `sourceRoleThreadId`; malformed returns cannot advance scope. See `references/direct-return.md`.

Visible Codex role threads only; never fall back to native spawn_agent. Team Router dispatch uses Codex desktop thread roles, not collaboration subagents.

## Gates

FAST/NORMAL read-only/design-only work may be Manager direct; when delegated without Reviewer/QA it ends with Manager acceptance. Manager direct is never allowed for workspace write: new FAST/NORMAL `local-package` work closes Executor -> Verifier without making Reviewer mandatory. STRICT/PACKAGE requires Reviewer then Verifier, and explicit Reviewer/QA also requires Verifier. A required review-only role must already be authorized or the flow blocks without creating one. See `references/reviewer-gate.md`.

## Lifecycle Gates

- Brainstorming/planning, design acceptance, implementation, verification, closeout file writes, commit, and create task actions are separate gates.
- `review-only` and verification-only requests do not edit files, create visible roles/tasks, send role messages, or write registry/ledger state.
- Design acceptance does not authorize implementation, closeout, commit, or create task actions. A named-fix request stays within its authorized findings and files.
- `create_thread`, role dispatch, and registry/ledger writes require an explicit current-turn create task or dispatch request plus a known objective, scope, permission boundary, and stop condition.
- A verifier result produces a user-facing report; closeout file writes and commit still require their own authorization. Stop after the authorized stage.

## Closeout And Handoff

Closeout reports changed, verified, accepted by, boundaries, risks, next gate, and `compoundingDecision`; file writes and commit remain separately authorized. See `references/role-closeout.md` and `references/side-effect-taxonomy.md`.

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
