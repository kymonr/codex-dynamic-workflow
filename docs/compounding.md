# Team Router Compounding Log

This is the project-level compounding ledger. Keep reusable lessons here when a task reveals a repeatable process, role, permission, verification, or workspace-risk rule.

## Recording Rule

- Record durable lessons that should change future Team Router behavior.
- Prefer generic rules over dated incident stories.
- Link the rule to the files/tests that enforce it.
- If closeout says `compoundingDecision: recorded`, this file should be updated or the closeout must explain why the record is pending/blocked.

## 中文复利记录模板

后续新增复利记录默认使用中文正文；协议字段、命令、路径、文件名、日志和报错保持 literal。每条记录必须写清楚：

```text
### <可复用规则标题>

- compoundingDecision: recorded | skipped
- reason: <为什么记录或跳过；跳过也要说明没有新的可复用风险>
- 触发条件：<哪些用户请求、角色状态、权限边界或失败现象会触发这条规则>
- 越权/风险事实：<实际发生或需要防止的越权、权限、流程、测试、工作区污染、交付可靠性风险>
- 影响面：<影响哪些角色、流程、文件、测试、回调、验收或用户理解>
- 正确 delegation：<管理者应如何派给 executor/reviewer/verifier；写清 scope/files、permission、return protocol 和禁止事项>
- 验收证据：<应检查的文件、关键 diff 摘要、测试命令与结果、回调/verdict/review 证据>
- 规则：<可复用行为规则，避免只写一次性事故叙述>
- Enforced by: <文件、测试、协议快照或 runbook>
```

如果记录被跳过，仍要保留 `compoundingDecision: skipped` 与 `reason`，并说明为什么普通实现/验证没有产生新的可复用流程风险。用户不懂英文时，不能只返回英文模板。

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

### Codex And Claude Parallel Review Requires Stable Gates

- compoundingDecision: recorded
- reason: Codex+Claude 并行 review 发现本轮流程有可复用治理教训，尤其是 PACKAGE/STRICT 级任务的锚点、thread tool 异常、角色冻结和外部状态门需要前置稳定。
- 触发条件：Complex Task Stack / PACKAGE 级任务需要 Codex 与 Claude 并行 review、隔离 worktree 多包执行、主工作区 integration，或用户明确要求 durable compounding 经验沉淀。
- 越权/风险事实：管理者越权已被修正，后续写文件仍必须走 executor -> reviewer -> verifier；本轮 integration 正确派执行者执行 `cherry-pick`，没有由 manager 直接修改主工作区。
- 越权/风险事实：`set_thread_title` / `list_threads` 等必要 thread tools 出现 `No handler registered for tool: ...` 时，应进入 `tool_error` 或明确 manual/pre-created path；不能把宿主能力异常默默降级为正常流程。
- 影响面：影响 manager 派工、executor/reviewer/verifier 线程规划、taskId 绑定、role binding outcome、replacement/reuse reason、pending worktree threadId 查找、callback/closeout 可读性，以及用户对流程边界的理解。
- 正确 delegation：并行包开始前必须冻结 executor/reviewer/verifier 线程规划、taskId 绑定、复用/替换原因和 return protocol，减少 B/C 期间临时补线程和 pending worktree threadId 查找造成的混淆风险。
- 正确 delegation：Complex Task Stack / PACKAGE 级任务应在派工前建立稳定 brief/reviewPackage 锚点，例如 `.superpowers/sdd/<taskId>-brief.md`；不能只靠聊天记录承载任务边界。
- 验收证据：检查派工里是否有稳定 `reviewPackagePath` 或等价 brief 锚点，检查 role closeout 是否说明 `role binding outcome: reused | new | replacement` 与原因，检查 callback 是否中文说明人读内容且保留 literal 协议 key、命令、路径和 hash。
- 规则：repo/global skill mismatch 不能无限期悬空；push 和 global skill sync 是两个独立外部状态变更门，必须分别明确授权。`--check` mismatch 是待同步状态，不是失败，也不是自动授权 `--sync`。
- 规则：用户看不懂英文时，closeout 和 callback 的人读内容必须中文；协议 key、命令、路径、hash 保持 literal。
- Enforced by: `docs/compounding.md`, `docs/workbench.md`, `skills/codex-team-router/references/manager-mode.md`, `skills/codex-team-router/references/role-handoff-and-review-package.md`, `src/team_router.py`, and `tests/test_team_router.py`.

### Manager Waiting Must Not Become Short-Interval Polling

- compoundingDecision: recorded
- reason: 本轮管理者在执行者 inProgress 且没有 callback 时，短时间内多次 `read_thread`，把 bounded/event-driven result collection 误执行成了连续轮询。
- 触发条件：Team Router role thread 已经派发，状态仍是 `inProgress`，尚未出现 `TEAM_ROUTER_CALLBACK` / `TEAM_ROUTER_REVIEW` / `TEAM_ROUTER_VERDICT`，或管理者已经发送 CONTROL 要求 scope-limited closeout。
- 越权/风险事实：频繁 `read_thread` 会制造噪音、消耗工具调用、干扰用户对流程状态的理解，并违反 300 秒 heartbeat / user-triggered status check 纪律。
- 影响面：影响调度者等待策略、执行者/审查者/验证者回调收集、用户可见状态更新、watcher/heartbeat 语义，以及 closeout 可信度。
- 正确 delegation：派发 role thread 后，调度者只做一次短 observation；如果没有 final marker，应停止主动读取，等待 direct-send、用户触发状态请求、已约定 `firstCheckAt` / `nextAllowedReadAt`，或明确 timeout/blocker 窗口。发送 CONTROL 后也不得连续读；下一步只能等 callback/blocker 或按 300 秒 cadence 读取。
- 验收证据：检查调度者 closeout 或 handoff 是否记录 `lastReadAt`、`nextAllowedReadAt` 或明确的用户触发状态请求；检查没有在同一等待窗口内反复 `read_thread` 同一 role thread。
- 规则：`inProgress` 不是轮询许可。没有 final marker 时，管理者必须报告“等待中/下次允许读取时间/用户可手动要求状态”，而不是继续短间隔读取。
- Enforced by: `docs/compounding.md`, `skills/codex-team-router/references/manager-mode.md`, `skills/codex-team-router/references/manual-orchestration.md`, `docs/runbooks/codex-team-router-live-orchestration.md`, and future tests in `tests/test_team_router.py`.
