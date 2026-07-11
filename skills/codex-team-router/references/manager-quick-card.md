# Manager Quick Card

Use this for real Manager Mode operation when the user wants Team Router but not a long inline checklist. It is a shortcut over the existing contract, not a new runtime feature.

## Trigger

Start only when the user clearly asks for a manager role, for example:

```text
你作为管理者，完成 <目标>
```

That standard entry allows Manager direct or a plan proposal; it does not select a concrete role model. For visible-role routing, require the explicit opt-in:

```text
你作为管理者，按 Luna Medium、Terra Medium、Sol High 成本感知路由完成 <目标>
```

## Default Short Protocol

Use this shape first:

```text
先解析 authorization -> effective gate -> route closure。
Manager direct 在 ledger、标题、heartbeat、线程操作前返回，且不写状态。
派工前确认显式模型授权；Luna Medium / Terra Medium / Sol High 只是该授权下的默认路由。
Role 仅用可见 Codex thread，并显式传 model + thinking；Sol Ultra 和 native spawn_agent fallback 都禁止。
FAST/NORMAL: direct 或 Executor -> Manager acceptance；STRICT/PACKAGE: Executor -> Reviewer -> Verifier。
commit、push、PR、merge、deploy、global sync 都单独授权；Task 10 global sync 另开 gate。
```

## Manager Defaults

- Keep the manager message short; put task detail in a Markdown package path.
- Prefer `taskBriefPath`, `executorReportPath`, or `reviewPackagePath` over inline evidence.
- Use reviewer/verifier direct-return as the normal closeout path when a parent thread id is available.
- Treat `local-package` as executor-only workspace write permission.
- Keep `commit`, `push`, `PR`, `merge`, `deploy`, and `global sync` outside the package unless the user explicitly opens that gate.
- Reuse only the same manager-owned pool identity (`parentThreadId`, host, target fingerprint, role). A creation intent with an unknown outcome is terminal; do not automatically retry create.
- Version 1 compatibility only: a legacy nonterminal ledger keeps its child Manager flow; never convert it in place.

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
