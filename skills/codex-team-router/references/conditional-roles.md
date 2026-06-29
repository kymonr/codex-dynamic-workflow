# Conditional Roles

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep architect and QA policy details here.

## Architect

`architect` is a formal conditional visible role for architecture-sensitive work before executor dispatch. Trigger it for architecture design, cross-module contracts, shared protocol/state-machine/direct-return behavior, migration or compatibility risk, dependency-boundary uncertainty, high-risk refactors, and durable maintainability risks.

The architect role uses the prompt profile `architect-default`. It is advisory/read-only and returns `TEAM_ROUTER_ARCHITECT_REVIEW` with `result: pass | needs_rework | blocked`.

## QA

`qa` is a formal conditional visible role for validation-sensitive work after executor callback and before verifier request. Trigger it for test strategy, acceptance criteria, regression, verification plan, coverage gaps, multiple paths/modes, evidence insufficiency, smoke coverage, and test matrix risk.

The QA role uses the prompt profile `qa-default`. QA findings are verifier input only. QA does not replace verifier, does not mark the task done, and does not provide final acceptance.

## Boundaries

CORE_ROLE_NAMES remains unchanged: `manager`, `executor`, and `verifier`. `architect` and `qa` are conditional visible roles, not default task-creation roles.

There is no runtime skill loading. `skillProfileUsed` records the prompt profile that was requested; it does not load skills, expand permission, or grant authority.

There is no custom role registry. Architect and QA are fixed built-in conditional roles only.

architect/QA do not replace reviewer. The reviewer remains separate from architect/QA and still owns read-only/adversarial policy, process, permission, role protocol, and shared-risk review when the reviewer gate applies.

## Markers

Architect result marker:

```text
TEAM_ROUTER_ARCHITECT_REVIEW taskId=<taskId>
result: pass | needs_rework | blocked
sourceThreadId: <returnThreadId>
sourceRoleThreadId: <architect roleThreadId>
role: Architect
summary: <summary>
findings: <findings or none>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
skillProfileUsed: architect-default
architectureImpact: <impact>
compatibilityNotes: <compatibility notes>
alternatives: <alternatives or none>
migrationRisks: <migration risks>
```

QA result marker:

```text
TEAM_ROUTER_QA_REVIEW taskId=<taskId>
result: pass | needs_rework | blocked
sourceThreadId: <returnThreadId>
sourceRoleThreadId: <qa roleThreadId>
role: QA
summary: <summary>
findings: <findings or none>
requiredChanges: <none or changes>
evidenceChecked: <checked evidence>
risks: <none or risks>
skillProfileUsed: qa-default
coverageGaps: <coverage gaps or none>
verificationPlan: <verification plan>
regressionRisks: <regression risks or none>
```

For `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW`, `sourceThreadId`, `sourceRoleThreadId`, `role`, and `skillProfileUsed` are required parser fields. The marker-specific `role` enum is `Architect` for architect and `QA` for QA. The marker-specific `skillProfileUsed` enum is `architect-default` or `qa-default`.

## Rework

Architect `pass` restores executor-dispatch eligibility but does not dispatch executor by itself. Architect `needs_rework` records the result and moves to `architect_rework_pending`; it does not increment executor `reworkCount`. Architect `blocked` maps to terminal `blocked`.

QA `pass` records `qaReview.result` and restores verifier-request eligibility. QA `needs_rework` uses the existing executor rework path and increments the existing global `reworkCount` exactly once. QA `blocked` maps to terminal `blocked`.

## Direct Return

Architect direct return maps `architect -> TEAM_ROUTER_ARCHITECT_REVIEW` and reads/writes the pending request at `architectureReview.request`. QA direct return maps `qa -> TEAM_ROUTER_QA_REVIEW` and reads/writes the pending request at `qaReview.request`.

Direct-send to the manager inbox is preferred. The role first calls `send_message_to_thread(threadId=<returnThreadId>, prompt=<complete TEAM_ROUTER_* block>)`, then outputs the same protocol block body in the role thread as `self-thread-marker` fallback.

Manager inbox and fallback capture validate `taskId`, `sourceThreadId`, marker-specific `role`, `sourceRoleThreadId`, pending request role/thread, expected marker, and return target before mutating the ledger. Wrong task, wrong role, wrong role thread, stale request, malformed marker, or non-pending return must not advance state.

Watcher fallback reads `architectureReview.request` for `TEAM_ROUTER_ARCHITECT_REVIEW` and `qaReview.request` for `TEAM_ROUTER_QA_REVIEW`. Fallback-only capture is degraded recovery, not proof that direct-send worked.

## Testing

Docs and fixtures must cover `architect_only`, `qa_only`, `architect_reviewer_no_qa`, `architect_reviewer_qa`, `qa_needs_rework`, `architect_blocked`, and `qa_blocked`.

Runtime tests must keep parser fields, direct-return validation, watcher fallback, result transitions, architect-required executor gating, QA-required verifier gating, and QA-gated evidence-only fast path locked. QA pass is verifier input, not final acceptance.