# Team Router Compounding Log

This is the project-level compounding ledger. Keep reusable lessons here when a task reveals a repeatable process, role, permission, verification, or workspace-risk rule.

## Recording Rule

- Record durable lessons that should change future Team Router behavior.
- Prefer generic rules over dated incident stories.
- Link the rule to the files/tests that enforce it.
- If closeout says `compoundingDecision: recorded`, this file should be updated or the closeout must explain why the record is pending/blocked.

## Entries

### 管理者只能调度，不能亲自越权改文件

- compoundingDecision: recorded
- 触发原因：用户说“你作为管理者”后，管理者本应只做调度，但直接改了仓库文件、跑了测试，还同步了全局安装的 skill 文件，属于管理者越权。
- 规则：进入管理者模式后，“优化 skill / 改规则 / 修 / 继续 / 复利”等请求只代表进入调度流程，不代表管理者可以亲自修改 Team Router 的 skill、规则、代码或文档。
- 规则：任何需要改文件的工作，管理者必须派执行者，并写清楚允许修改哪些文件；Team Router 自改、高风险流程或规则变更还必须经过审查者和验证者。
- 规则：回滚、提交、推送、发布、同步全局文件都必须单独明确授权，不能从“继续”“复利”或管理者身份中推断授权。
- 执行要求：管理者只能判断边界、拆任务、派执行者、派审查者、派验证者，并汇报结果；不能把自己当执行者。
### Archived Role No-Reuse And Delivery Degradation Must Be Explicit

- compoundingDecision: recorded
- reason: archived role/thread no-reuse and proactive role-return reliability are reusable Team Router process risks.
- Rule: archived role/thread is unavailable for reuse, period; create or use a non-archived visible replacement role and record the replacement reason.
- Rule: if a non-archived role is not user-visible, read_thread readable, or otherwise usable, treat it as unavailable/broken and replace it with a visible role.
- Rule: role completion requires proactive direct-send plus self-thread fallback; manager watcher-only collection is `deliveryStatus: fallback_only` / delivery degraded, not normal success.
- Enforced by: `src/team_router.py`, `tests/test_team_router.py`, `skills/codex-team-router/references/direct-return.md`, `skills/codex-team-router/references/manager-mode.md`, and `docs/workbench.md`.
### Direct Return Identity Must Be Explicit

- Trigger: direct-return contract docs and snapshots required `role` / `sourceRoleThreadId`, but runtime receipt validation still accepted missing identity fields by falling back to wrapper/source defaults.
- Rule: manager direct-send receipt validation must treat the Codex delegation wrapper source as transport metadata only; it cannot infer protocol identity from wrapper `<source_thread_id>` / normalized message `sourceThreadId`.
- Rule: direct-return protocol blocks must explicitly provide `sourceThreadId`, `role`, and `sourceRoleThreadId`; missing or mismatched fields are malformed/quarantined and must fall back to the role self-thread marker path.
- Rule: direct-return contract changes must lock runtime validator behavior, active docs/snapshot wording, and negative tests for both wrong values and missing fields.
- Enforced by: `src/team_router.py`, `tests/test_team_router.py`, `skills/codex-team-router/references/direct-return.md`, `skills/codex-team-router/references/testing-and-quality-gates.md`, and `docs/workbench.md`.

### Manager Overreach, Lightweight Flow, And Role Callback Discipline

- Trigger: manager wrote or attempted to write files during active Manager Mode, a narrow mechanical fix expanded into too many roles, and a role completed key checks without proactively returning the expected protocol block.
- Rule: active Manager Mode does not self-write durable lessons or implementation files unless the user explicitly switches role and authorizes that exact file change.
- Rule: narrow mechanical fixes such as CRLF/LF normalization should not default to executor -> reviewer -> verifier; use executor plus either reviewer or verifier unless semantic/process risk appears.
- Rule: any role that completes key checks must proactively return the final protocol block by direct-send and self-thread fallback; it must not rely on parent polling or parent follow-up.
- Rule: after bounded wait/read with no final protocol block, manager CONTROL must request only scope-limited closeout from already-confirmed facts.
- Enforced by: `skills/codex-team-router/SKILL.md`, `skills/codex-team-router/references/manager-mode.md`, `skills/codex-team-router/references/manual-orchestration.md`, `skills/codex-team-router/references/role-closeout.md`, `src/team_router.py`, and `tests/test_team_router.py`.
