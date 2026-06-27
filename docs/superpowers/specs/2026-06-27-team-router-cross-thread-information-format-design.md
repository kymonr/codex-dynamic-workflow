# Team Router Cross-Thread Information Format Design

## 1. Context

Team Router already has strict role protocol markers:

- `TEAM_ROUTER_PLAN`
- `TEAM_ROUTER_CALLBACK`
- `TEAM_ROUTER_REVIEW`
- `TEAM_ROUTER_VERDICT`

Those marker blocks are good for state-machine progress, but they are too small to carry full task context, evidence, excluded changes, and review history. Existing policy also supports path handoff fields:

- `taskBriefPath`
- `executorReportPath`
- `reviewPackagePath`

This design standardizes how role threads exchange information without changing the existing parser, marker names, or runtime trust model.

## 2. Goals

- Keep protocol blocks machine-strict and compatible with the current line-based parser.
- Use a durable Markdown handoff package for complete context and evidence when the task risk justifies it.
- Make cross-thread evidence readable to the user, reviewer, verifier, and future maintainers.
- Keep small Team Router tasks low-friction.
- Support Chinese task descriptions while preserving parser-compatible English field names, markers, and enum values.

## 3. Non-Goals

- Do not replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT` with package files.
- Do not make runtime read, execute, parse, or trust package Markdown content.
- Do not change marker syntax from line-based key/value to YAML or JSON.
- Do not require package files for every FAST or NORMAL task.
- Do not paste full diffs into package files.

## 4. Chosen Approach

Use the minimal incremental design:

- Protocol block: machine-strict state transition surface.
- Handoff package: durable human-readable evidence bundle.
- Runtime: validates and records path metadata only.
- Parser: unchanged.
- Package content: governed by documentation, prompts, and review/verifier expectations rather than runtime Markdown parsing.

This preserves compatibility with the current Team Router contract while making evidence transfer more predictable.

## 5. Protocol Block Rules

Protocol blocks keep the current format:

```text
TEAM_ROUTER_CALLBACK taskId=<taskId>
status: done
final: true
summary: 已完成跨线程信息格式规范，未修改 parser
evidence: docs/team-router/packages/<taskId>.md；聚焦测试通过
risks: package 是证据包，runtime 不读取或信任内容
next: verifier
reviewPackagePath: docs/team-router/packages/<taskId>.md
```

Rules:

- Marker names stay English: `TEAM_ROUTER_PLAN`, `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, `TEAM_ROUTER_VERDICT`.
- Field names stay English and line-based.
- Enum/literal values stay English, including `status`, `final`, `result`, permission values, and gate-class values.
- Paths, commands, filenames, and tool names stay literal.
- Free-text fields default to Chinese when they are meant for humans, such as `summary`, `evidence`, `risks`, `next`, `scope`, `riskBoundary`, `executorPrompt`, and `notes`.
- Gate-sensitive fields should preserve enough English signals for existing keyword classifiers, especially paths such as `README.md`, `src/team_router.py`, and terms such as `Team Router`, `reviewer`, `runtime`, `policy`, `permission`, `safety`, `encoding`, or `docs-only`.
- If English classifier signals would be absent, the manager should use explicit fields such as `requiresReviewer: true`, `riskClass: high`, or a clear English phrase in `riskBoundary` / `notes`.

## 6. Handoff Package Path

Default durable package path:

```text
docs/team-router/packages/<taskId>.md
```

This default applies to `reviewPackagePath`.

It does not automatically apply to `taskBriefPath` or `executorReportPath`. Those fields may still point to separate task brief or executor report files when useful.

Package files under `docs/team-router/packages/` are durable project evidence. They are intended to be committed with the task when they are created. They must not be added to `.gitignore` under this design.

Commit closeout must explicitly account for package files because untracked files are not shown by `git diff --name-only`.

## 7. Gate Expectations

Package requirements by gate:

- `FAST`: package not required by default. Use inline protocol blocks unless the user requests a package or context would otherwise be lost.
- `NORMAL`: package optional. Manager decides whether the executor should produce one.
- `STRICT`: package recommended. Manager should require a package for high-risk, long-running, multi-file, policy, role-protocol, permission, safety, or reviewer-gate work.
- `PACKAGE`: package required unless the manager explicitly marks `inlineFallback: true` or `reviewPackagePath: inline`.

This keeps the existing runtime contract intact:

- `STRICT` missing package does not block the ledger by itself.
- `PACKAGE` missing `reviewPackagePath` and missing inline fallback blocks the ledger.

If role threads cannot access the same workspace/path, use inline fallback and mark it explicitly. The protocol block remains authoritative in that case.

## 8. Package Ownership

Writing a package file is workspace write work.

In active Manager Mode:

- The manager may decide whether a package is needed.
- The manager must not write the package directly unless the user explicitly switches role and authorizes that exact file edit in the current turn.
- The normal path is executor-owned package creation under an authorized `local-package` or equivalent workspace-write scope.
- Reviewer and verifier consume the package as evidence, but they do not treat it as authority over the protocol block.

## 9. Package Required Shape

Package Markdown defaults to Chinese body text. Section headings are bilingual for scanning by both human readers and role prompts.

Required shape:

```markdown
# Team Router Handoff Package: <taskId>

## Task Summary / 任务摘要
## Scope / 范围
## Protocol References / 协议引用
## Touched Files / 触及文件
## Behavior Changes / 行为变化
## Diff Summary / Diff 摘要
## Verification / 验证
## Excluded Changes / 未纳入改动
## Risks / 风险
## Remaining Todos / 剩余事项
```

Minimum required content:

- `taskId`
- objective
- scope
- protocol marker references
- touched files
- accepted files, when different from touched files
- behavior changes
- diff summary
- executor callback/report summary
- reviewer findings and `requiredChanges`, when present
- verification evidence and actual commands/results
- excluded unrelated changes and untracked files
- risks
- remaining todos

Packages must include a diff summary, but must not include a full diff. Use paths, symbols, behavior descriptions, and verification evidence instead of pasting the entire patch.

## 10. Trust Boundary

The handoff package supplements evidence. It never replaces role protocol blocks.

Runtime behavior:

- Records supplied `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` metadata.
- Validates path safety and workspace containment.
- Does not read Markdown package content.
- Does not execute package content.
- Does not trust package content for state transitions.
- Does not auto-generate package content.

State transitions remain driven by the current protocol markers:

- `TEAM_ROUTER_CALLBACK`
- `TEAM_ROUTER_REVIEW`
- `TEAM_ROUTER_VERDICT`

Reviewer/verifier behavior:

- Reviewer inspects the package plus focused diff/evidence.
- Verifier checks the executor callback, reviewer result when present, package evidence, permission boundary, accepted files, excluded changes, and final user-facing closeout.
- If package content and protocol block conflict, the protocol block and direct ledger evidence win; the conflict is a review/verifier finding.

## 11. Example Package

```markdown
# Team Router Handoff Package: ctr-20260627-info-format

## Task Summary / 任务摘要

- taskId: ctr-20260627-info-format
- objective: 规范 Team Router 跨线程信息格式
- gateClass: STRICT
- reviewPackagePath: docs/team-router/packages/ctr-20260627-info-format.md

## Scope / 范围

本任务只调整 Team Router 信息格式规范。保持 parser、marker、runtime trust boundary 不变。

## Protocol References / 协议引用

- `TEAM_ROUTER_CALLBACK`
- `TEAM_ROUTER_REVIEW`
- `TEAM_ROUTER_VERDICT`
- `reviewPackagePath`

## Touched Files / 触及文件

- `skills/codex-team-router/references/role-handoff-and-review-package.md`
- `tests/test_team_router.py`

## Behavior Changes / 行为变化

- 明确 package 是 durable evidence。
- 明确自由文本默认中文，字段名和枚举保持英文。
- 明确 package 要写 diff summary，但不贴完整 diff。

## Diff Summary / Diff 摘要

- 更新 review package 最小内容列表。
- 增加 bilingual package heading 示例。
- 增加测试锁定 package 内容规范关键词。

## Verification / 验证

- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass
- `git diff --check`: pass

## Excluded Changes / 未纳入改动

- 未修改 parser。
- 未修改 direct-return receipt validation。
- 未修改 watcher cadence。

## Risks / 风险

- package 内容仍由人类和角色审查约束，runtime 不做 Markdown schema 校验。

## Remaining Todos / 剩余事项

- none
```

## 12. Implementation Impact

Expected implementation is documentation/test focused:

- Update `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY` minimum content to include behavior changes and the no-full-diff rule.
- Update `skills/codex-team-router/references/role-handoff-and-review-package.md` with the durable package path and bilingual template.
- Update `skills/codex-team-router/SKILL.md` only if the short entrypoint needs a compact pointer; keep it under the Codex size cap.
- Add or update docs-contract tests in `tests/test_team_router.py`.
- Do not make runtime read package Markdown.
- Do not make `STRICT` missing package a blocking runtime error.
- Do not add `docs/team-router/packages/` to `.gitignore`.
- Consider updating old ignored `.superpowers/sdd/` examples or adding a warning that those legacy examples predate the no-full-diff package rule.

## 13. Testing Strategy

Focused tests should cover:

- `protocol_contract_snapshot()` exposes the updated review package minimum content.
- Reference docs mention `docs/team-router/packages/<taskId>.md`.
- Reference docs specify `PACKAGE` required-or-inline-fallback and `STRICT` recommended.
- Reference docs specify free-text Chinese defaults while markers, field names, enums, paths, commands, and filenames stay literal English.
- Reference docs include bilingual package headings.
- Reference docs state full diffs should not be pasted into package files.

Runtime tests should not parse package Markdown because that would violate this design.

## 14. Review Feedback Incorporated

Codex and Claude read-only review raised these design corrections:

- Do not say `STRICT` must write package as a runtime rule. Keep `STRICT` recommended and `PACKAGE` required-or-inline-fallback.
- Clarify that `docs/team-router/packages/<taskId>.md` is durable and committed, not ignored temporary state.
- Limit Chinese-default wording to free-text fields; keep parser literals English.
- Document that gate classification still needs English path/keyword signals or explicit gate fields.
- Add behavior changes and no-full-diff expectations to package content.
- Clarify that the default path applies to `reviewPackagePath`, not all path fields.

These corrections are part of the accepted design.
