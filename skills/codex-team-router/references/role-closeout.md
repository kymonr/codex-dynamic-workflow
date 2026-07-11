# Role Closeout

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep closeout policy details here.

## Version 2 Routing Receipt And Acceptance

FAST/NORMAL delegated Executor work closes only through structured Manager acceptance; STRICT/PACKAGE closes through Verifier. Both closeouts include the same `routingReceipt`: dispatch-order role, `binding`, optional thread id, `requestedModel`, `requestedThinking`, create/bootstrap and dispatch acceptance when attempted, override reason, `upgradedFrom`, rework count, and `solUltraDispatched: false`.

`requestedModel` is not `actualModel` or billing evidence. The Runtime has no actual-model, token, price, or cost source, so the receipt must never claim those facts. Automatic budgets are one automatic model upgrade and one automatic rework per task; preserve the failed delta on the first attempt and enforce a hard stop after the second attempt fails or the budget is exhausted.

## Manager commit closeout policy

When the user only talks to manager, manager owns commit workflow. After verifier pass and an explicit user request to commit, manager may perform local `git status` / `git diff`, stage 已验收文件, and commit as a closeout operation.

Commit closeout is not implementation authorization. Manager must not use commit as permission to continue implementation, modify files, or run heavy commands. Manager must 排除无关 untracked. Before commit, PR, push, merge, deploy, publish, or release, manager prompts for explicit authorization; push/PR/merge/deploy 单独授权.


## Parent user closeout

Every completed Team Router flow needs a parent-thread report in ordinary, user-readable language. Lead with a 用户听得懂的人话 closeout before any protocol appendix or raw helper output. Protocol blocks close the role threads, but they do not replace the parent-thread explanation.

That human-readable closeout must explicitly cover:

- what this task actually completed
- which key files/areas/rules changed
- what verification actually ran and what the result was
- what was not done and why it stayed out of scope
- remaining risks, or state clearly that there are none
- the next suggested step or next gated step

Keep it short, concrete, and free of unnecessary internal jargon. Use literal protocol keys, paths, commands, and thread ids only where they help the user inspect evidence. Raw `TEAM_ROUTER_*` blocks, `pass`, `requiredChanges: none`, or helper/state labels alone are not an acceptable parent closeout.

Compounding落实 ownership: the manager reports `compoundingDecision`, concrete reason, and evidence. Durable lesson writes are executor-owned and gated through executor/reviewer/verifier; the manager may not self-write the lesson as an exception. Project-level reusable lessons may be recorded in `docs/compounding.md`, and current task state may be refreshed in `docs/workbench.md`, only through a separately authorized workspace-write gate. Review-only, verification-only, and the parent user-facing closeout never write those files automatically. If no durable file is written, parent closeout states why the compounding record is pending/blocked/skipped rather than silently omitting it.

## roleCloseoutPolicy

After task completion, default is 不 clear role thread and manager does not send extra ROLE_CLOSEOUT or ordinary closeout messages to role threads by default.

final protocol block is the closeout:

- executor `TEAM_ROUTER_CALLBACK`
- reviewer `TEAM_ROUTER_REVIEW`
- verifier `TEAM_ROUTER_VERDICT`

These protocol blocks are sufficient task-ending anchors for the role threads, but they are not sufficient by themselves as the user-facing parent closeout.

When key checks are complete, the role must proactively return its protocol block by direct-send and self-thread fallback; it must not rely on parent polling. If the manager sends CONTROL after bounded wait/read because no final protocol block arrived, the role closeout is scope-limited to already-confirmed facts.

compact is native operation, not chat prompt. Manager must not send `compact` or `ROLE_CLOSEOUT` text to pretend context compression happened. If native compact is available and truly needed, such as role thread 上下文过长, manager may trigger native compact; if no compact tool is available, do nothing.

Only send the shortest closeout/stop message when one of these exceptions applies:

- a role thread is still active/inProgress and must stop.
- no final protocol block exists and a minimal stop anchor is needed.
- a compact/archive recovery anchor is needed before compact/archive.
- 用户明确要求.

clear is not a default action. Create or archive an old role thread only for 身份污染, 上下文过长, task family/permission/workspace boundary 变化, or 用户明确要求.
