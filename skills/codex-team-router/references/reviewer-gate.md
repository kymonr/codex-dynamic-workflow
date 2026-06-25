# Reviewer Gate

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep conditional reviewer details here.

## Conditional Reviewer Gate

Ordinary small fixes and clearly low-risk tasks use executor -> verifier.

Router/manager/orchestration policy, permission or safety boundary rules, process rules, role protocol, and shared/high-risk logic must use executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance).

The reviewer independently looks for design risks, rule gaps, omissions, and new bad modes; it does not implement changes and is not final acceptance. The verifier remains final acceptance and confirms the executor result plus any reviewer requiredChanges are satisfied.

Runtime adapters execute this gate with `send_reviewer_request_with_adapter()`, `read_reviewer_review_update_with_adapter()`, and `capture_reviewer_review_from_read()`:

- reviewer `pass` continues to verifier.
- reviewer `needs_rework` returns to executor rework.
- reviewer `blocked` blocks the task.

When the user names `reviewer` for Team Router self changes, the manager must use a reviewer role conversation/thread; if no existing reviewer thread exists, explicitly create/register reviewer role conversation or stop and report it. subagent fallback is not allowed.

Trigger logic covers `runtime gate`, `reviewer gate`, `Team Router self changes`, and `Team Router` combined with reviewer/runtime/protocol/policy/permission/safety/process/shared/high-risk semantics. A plain `team_router.py` filename or low-risk docs-only/single-file cleanup does not trigger reviewer by itself.

Role reuse policy applies to reviewer too: for the same `taskId` or task family, reuse existing reviewer when the conditional reviewer gate applies, and send rework review back to the original reviewer thread.

## Reviewer Review Protocol

```text
TEAM_ROUTER_REVIEW_REQUEST taskId=<taskId>
reviewMarker: TEAM_ROUTER_REVIEW taskId=<taskId>
returnThreadId: <explicit orchestrator/parent thread id when direct return is available>
reviewDelivery: direct-send
reviewFallback: self-thread-marker
reviewerMode: read-only/adversarial
permission: read-only | design-only | local-package
scope: <review scope>

TEAM_ROUTER_REVIEW taskId=<taskId>
result: pass | needs_rework | blocked
summary: <review summary>
findings: <adversarial findings or none>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
```

Natural-language reviews do not move state. Reviewer is a conditional reviewer, not final acceptance; verifier remains final acceptance.
