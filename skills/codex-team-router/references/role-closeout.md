# Role Closeout

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep closeout policy details here.

## Manager commit closeout policy

When the user only talks to manager, manager owns commit workflow. After verifier pass and an explicit user request to commit, manager may perform local `git status` / `git diff`, stage 已验收文件, and commit as a closeout operation.

Commit closeout is not implementation authorization. Manager must not use commit as permission to continue implementation, modify files, or run heavy commands. Manager must 排除无关 untracked. Before commit, PR, push, merge, deploy, publish, or release, manager prompts for explicit authorization; push/PR/merge/deploy 单独授权.


## Parent user closeout

Every completed Team Router flow needs a parent-thread report in ordinary, user-readable language. Protocol blocks close the role threads, but the manager still tells the user what changed, what verification actually ran, who accepted it, what was not done, remaining risks, current state, and the next gated step. Keep it short, concrete, and free of unnecessary internal jargon; use protocol names only where they clarify evidence.

Compounding落实 ownership: the manager reports `compoundingDecision`, concrete reason, and evidence. Durable lesson writes are executor-owned and gated through executor/reviewer/verifier; the manager may not self-write the lesson as an exception. Project-level reusable lessons are continuously recorded in `docs/compounding.md`; current task state is recorded in `docs/workbench.md` as a living record and must be refreshed when task state, diff surface, verification, or next gate changes. If no durable file is written, parent closeout states why the compounding record is pending/blocked/skipped rather than silently omitting it.

## roleCloseoutPolicy

After task completion, default is 不 clear role thread and manager does not send extra ROLE_CLOSEOUT or ordinary closeout messages to role threads by default.

final protocol block is the closeout:

- executor `TEAM_ROUTER_CALLBACK`
- reviewer `TEAM_ROUTER_REVIEW`
- verifier `TEAM_ROUTER_VERDICT`

These protocol blocks are sufficient task-ending anchors.

When key checks are complete, the role must proactively return its protocol block by direct-send and self-thread fallback; it must not rely on parent polling. If the manager sends CONTROL after bounded wait/read because no final protocol block arrived, the role closeout is scope-limited to already-confirmed facts.

compact is native operation, not chat prompt. Manager must not send `compact` or `ROLE_CLOSEOUT` text to pretend context compression happened. If native compact is available and truly needed, such as role thread 上下文过长, manager may trigger native compact; if no compact tool is available, do nothing.

Only send the shortest closeout/stop message when one of these exceptions applies:

- a role thread is still active/inProgress and must stop.
- no final protocol block exists and a minimal stop anchor is needed.
- a compact/archive recovery anchor is needed before compact/archive.
- 用户明确要求.

clear is not a default action. Create or archive an old role thread only for 身份污染, 上下文过长, task family/permission/workspace boundary 变化, or 用户明确要求.
