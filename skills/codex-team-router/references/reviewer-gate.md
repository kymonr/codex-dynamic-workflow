# Reviewer Gate

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep conditional reviewer details here.

## Conditional Reviewer Gate

Version 2 starts with route closure, not a fixed three-role chain. FAST/NORMAL read-only/design-only Manager direct has no role; delegated read-only/design-only work uses executor -> Manager acceptance unless the route explicitly includes Reviewer or QA. FAST/NORMAL `local-package` workspace write is never Manager direct and uses executor -> verifier without requiring Reviewer. STRICT/PACKAGE requires executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance). `local-package` is a workspace permission, not a reviewer trigger by itself.

Version 1 compatibility: Ordinary small fixes and clearly low-risk tasks use executor -> verifier.

Router/manager/orchestration policy, permission or safety boundary rules, process rules, role protocol, and shared/high-risk logic must use executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance).

Team Router skill/rule/process self-changes and Manager Mode boundary optimizations are process/policy changes. When they require local-package writes, keep one executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance) chain.

The reviewer independently looks for design risks, rule gaps, omissions, and new bad modes; it does not implement changes and is not final acceptance. Reviewer pass is permission to continue to verifier, not completion. The verifier remains final acceptance and confirms the executor result plus any reviewer requiredChanges are satisfied.

Runtime adapters execute this gate with `send_reviewer_request_with_adapter()`, `read_reviewer_review_update_with_adapter()`, and `capture_reviewer_review_from_read()`:

- reviewer `pass` continues to verifier.
- reviewer `needs_rework` returns to executor rework.
- reviewer `blocked` blocks the task.

When the user names `reviewer` for Team Router self changes, the manager must use a reviewer role conversation/thread; if no existing reviewer thread exists, explicitly create/register reviewer role conversation or stop and report it. subagent fallback is not allowed.

Trigger logic covers `runtime gate`, `reviewer gate`, `Team Router self changes`, and `Team Router` combined with reviewer/runtime/protocol/policy/permission/safety/process/shared/high-risk semantics. Deterministic risk-floor precedence is `PACKAGE > STRICT bilingual risk > NORMAL bilingual QA floor > FAST > NORMAL fallback`.

The bilingual route matrix matches only these complete phrases:

| Complete phrase group | Effective floor | Conditional roles |
| --- | --- | --- |
| `cross-module refactor / 跨模块重构` | STRICT | Reviewer=true, Architect=true |
| `permission boundary / 权限边界` | STRICT | Reviewer=true, Architect=true |
| `state machine / state-machine / 状态机` | STRICT | Reviewer=true, Architect=true |
| `legacy protocol compatibility / compatibility with legacy protocol / 兼容旧协议` | STRICT | Reviewer=true, Architect=true |
| `database migration / 数据库迁移` | STRICT | Reviewer=true, Architect=true |
| `regression test / 回归测试` | NORMAL | QA=true, Reviewer=false |
| `coverage gap / 覆盖缺口` | NORMAL | QA=true, Reviewer=false |

The requested gate is a lower bound: requested FAST/NORMAL may only upgrade, requested STRICT/PACKAGE never downgrade, and PACKAGE remains the ceiling. Matching is conservative and literal: related single words or near phrases do not trigger this bilingual floor, but a complete phrase in negation, quotation, or discussion text still upgrades the route. This leaves a documented contextual false-positive risk; A4 does not introduce NLP, a path classifier, or regex inference.

A3 behavior remains intact: FAST/NORMAL workspace write routes Executor -> Verifier, `local-package` is not a Reviewer trigger, and historical persisted `routeRoles` remain compatible and authoritative. A plain `team_router.py` filename or low-risk docs-only/single-file cleanup does not trigger Reviewer by itself.

Role binding policy applies to Reviewer too: within the same active `taskId + requestId`, send re-review back to the original Reviewer thread. Without trusted execution-domain evidence, an idle/released/terminal Reviewer is not reusable.

## Reviewer Review Protocol

Use the single normative Reviewer request/result schema in `references/direct-return.md`; do not copy or fork the template here.

Natural-language reviews do not move state. Reviewer is a conditional reviewer, not final acceptance; verifier remains final acceptance.
## Architect And QA Boundary

See `references/conditional-roles.md` for architect and QA policy.

The reviewer remains separate from architect/QA. architect/QA do not replace reviewer, and QA does not replace verifier. Architect checks architecture risk before executor dispatch; QA checks validation risk before verifier request. Reviewer still owns read-only/adversarial policy, process, permission, role protocol, and shared/high-risk review when the reviewer gate applies.
