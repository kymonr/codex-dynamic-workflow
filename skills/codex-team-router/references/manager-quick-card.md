# Manager Quick Card

Use this for real Manager Mode operation when the user wants Team Router but not a long inline checklist. It is a shortcut over the existing contract, not a new runtime feature.

## Trigger

Start only when the user clearly asks for a manager role, for example:

```text
你作为管理者，使用 Team Router 管这个任务。
```

## Default Short Protocol

Use this shape first:

```text
你作为管理者，使用 Team Router 管这个任务。
默认短协议 + md path。
长上下文写入 taskBriefPath / executorReportPath / reviewPackagePath。
按权限分 gate：read-only / dispatch-only / local-package / external-release。
需要实现时派 executor；过程、协议、共享风险变化先 reviewer，最终 verifier。
角色完成优先 direct-return 到调度者；self-thread marker 只是 fallback。
commit、push、PR、merge、deploy、global sync 都单独授权。
出问题才展开 references。
```

## Manager Defaults

- Keep the manager message short; put task detail in a Markdown package path.
- Prefer `taskBriefPath`, `executorReportPath`, or `reviewPackagePath` over inline evidence.
- Use reviewer/verifier direct-return as the normal closeout path when a parent thread id is available.
- Treat `local-package` as executor-only workspace write permission.
- Keep `commit`, `push`, `PR`, `merge`, `deploy`, and `global sync` outside the package unless the user explicitly opens that gate.

## Do Not Inline By Default

- Do not paste full checklist text into role requests when a package path is available.
- Do not paste full diffs, logs, or long evidence bodies unless the role cannot read the path.
- Do not treat manual copy-paste as live dispatch evidence.
- Do not expand manager authorization into workspace writes, commit, push, or global sync.

## Expand References Only When Needed

- Use `references/manager-mode.md` for trigger ambiguity, sticky mode, or permission classification.
- Use `references/role-handoff-and-review-package.md` when path handoff, package metadata, or inline fallback is unclear.
- Use `references/direct-return.md` when callback routing, parent id, source role id, or fallback validation is unclear.
- Use `references/manual-orchestration.md` when live thread tools are unavailable and the task must stay manual.
