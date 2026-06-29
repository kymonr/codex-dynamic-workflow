# Architect And QA Conditional Roles Design

## Status

Approved direction for spec drafting after brainstorming, Claude consult, visible Team Router reviewer pass, and a parallel Codex/Claude read-only review.

This revision incorporates the confirmed review gaps: recovery states, architect rework semantics, direct-return field names, marker validation, role display names, classifier requirements, classifier baseline terms, state semantics, code extension points, QA verifier gating, and test-fixture migration.

This document is a design spec only. It does not authorize implementation, commit beyond this spec, push, PR, merge, deploy, global skill sync, runtime skill loading, or production/data/API access.

## Problem

Team Router currently has fixed visible role threads for `manager`, `executor`, `reviewer`, and `verifier`. That model is strong for implementation delegation, policy review, and final acceptance, but it has two gaps:

- architecture-sensitive work needs an explicit architecture review surface before executor scope hardens
- validation-sensitive work needs a focused QA review surface before final verifier acceptance

Using external subagents or free-form skill text for these jobs would weaken the existing Team Router boundary. If these responsibilities become Team Router roles, they need formal protocol support rather than advisory text only.

## Goals

- Add two fixed built-in conditional roles: `architect` and `qa`.
- Keep both roles visible Team Router role threads when dispatched.
- Keep both roles read-only/advisory: no write permission, no commit/push/PR/release authority, no replacement of `reviewer` or `verifier`.
- Keep `CORE_ROLE_NAMES` unchanged as `manager`, `executor`, and `verifier`; `architect` and `qa` are never required for ordinary task creation.
- Give each role a protocol marker, ledger field, state transition, direct-return handling, and tests.
- Give each role a prompt-level skill profile without runtime skill auto-loading.
- Preserve current low-friction paths for ordinary tasks.

## Non-Goals

- No arbitrary custom role registry.
- No automatic runtime loading or invocation of skills.
- No permission expansion through `skillProfileUsed`.
- No replacement of `TEAM_ROUTER_REVIEW` for policy/process/permission/role protocol review.
- No replacement of `TEAM_ROUTER_VERDICT` as final acceptance.
- No publish/release/global sync behavior.

## Roles

### `architect`

Purpose: pre-execution architecture and design risk review.

Role identity:

```text
role key: architect
displayName: 架构师
englishAlias: Architect
protocol role field: Architect
skillProfileUsed: architect-default
```

Trigger only when there is a positive architecture signal:

- architecture design or cross-module contract change
- shared protocol/state-machine/direct-return behavior
- high-risk refactor or durable maintainability risk
- Team Router process, role, permission, or protocol changes
- migration, compatibility, or dependency-boundary uncertainty

Do not trigger for ordinary single-file or narrow mechanical changes unless they change a public contract or durable process boundary.

### `qa`

Purpose: post-execution validation strategy and regression-risk review before verifier acceptance.

Role identity:

```text
role key: qa
displayName: QA
englishAlias: QA
protocol role field: QA
skillProfileUsed: qa-default
```

Trigger only when there is a positive validation signal:

- unclear test strategy or acceptance criteria
- high regression risk
- behavior spans multiple paths or modes
- fix needs an independent verification plan
- evidence is insufficient for verifier to make a confident final acceptance decision

Do not trigger for ordinary low-risk changes where executor evidence is already enough for verifier acceptance.

## Routing Classification

Triggering architect and QA must be machine-readable, not only natural-language guidance. Add routing helpers or equivalent structured fields:

```text
classify_architect_gate(ledger) -> bool
classify_qa_gate(ledger) -> bool
explain_team_router_route(ledger) -> route summary
```

The helpers should read explicit boolean fields first, then conservative keyword signals from the objective, plan fields, scope, risk boundary, notes, and dispatch metadata.

Explicit fields may include:

```text
requiresArchitect: true | false
requiresQa: true | false
architectureGateRequired: true | false
qaGateRequired: true | false
```

Default behavior stays conservative. A task mentioning `architect` or `qa` as free text is not enough by itself to force either role unless the surrounding task content also matches the positive trigger signals or explicit fields.

Reviewer routing remains separate. `classify_architect_gate()` and `classify_qa_gate()` must not imply `reviewer` unless existing reviewer gate rules also apply.

## Classifier Baseline

The implementation must add named classifier constants or an equivalent testable table. The exact names may follow local style, but the implementation plan should assume:

```text
ARCHITECT_GATE_TERMS
QA_GATE_TERMS
```

`ARCHITECT_GATE_TERMS` must cover at least these positive signals:

- `architecture`
- `architectural`
- `cross-module`
- `contract change`
- `protocol`
- `state-machine`
- `direct-return`
- `role protocol`
- `permission boundary`
- `migration`
- `compatibility`
- `dependency-boundary`
- `high-risk refactor`
- `durable maintainability`

`QA_GATE_TERMS` must cover at least these positive signals:

- `test strategy`
- `acceptance criteria`
- `regression`
- `verification plan`
- `coverage gap`
- `multiple paths`
- `multiple modes`
- `evidence insufficient`
- `smoke`
- `test matrix`

Do not include bare role names such as `architect`, `architecture reviewer`, or `qa` as standalone trigger terms. A bare role mention can explain intent in `explain_team_router_route()`, but it must not be enough to dispatch the role without a positive scope/risk/validation signal or an explicit boolean field.

Classifier tests must lock both the explicit boolean path and representative term-derived paths. Adding extra conservative terms is allowed, but removing the baseline examples requires updating the spec and tests together.

## Flow

Existing low-risk flow stays unchanged:

```text
executor -> verifier
```

Existing reviewer-gated flow stays unchanged:

```text
executor -> reviewer -> verifier
```

Architect-gated flow:

```text
architect -> executor -> reviewer? -> verifier
```

QA-gated flow:

```text
executor -> reviewer? -> qa -> verifier
```

Combined flow:

```text
architect -> executor -> reviewer? -> qa -> verifier
```

`reviewer?` is conditional only in the existing Team Router sense. If the task triggers policy/process/permission/role-protocol/shared-risk review, reviewer is mandatory.

`qa` always runs before verifier because QA findings are evidence for final acceptance.

## Protocol Markers

Add two formal markers:

```text
TEAM_ROUTER_ARCHITECT_REVIEW
TEAM_ROUTER_QA_REVIEW
```

Both markers require parser-compatible fields:

```text
result: pass | needs_rework | blocked
sourceThreadId:
sourceRoleThreadId:
role:
summary:
findings:
requiredChanges:
evidenceChecked:
risks:
skillProfileUsed:
```

`skillProfileUsed` is marker-specific, required, and not free text:

```text
TEAM_ROUTER_ARCHITECT_REVIEW.skillProfileUsed: architect-default
TEAM_ROUTER_QA_REVIEW.skillProfileUsed: qa-default
```

`role` is marker-specific:

```text
TEAM_ROUTER_ARCHITECT_REVIEW.role: Architect
TEAM_ROUTER_QA_REVIEW.role: QA
```

Architect marker adds required role-specific fields:

```text
architectureImpact:
compatibilityNotes:
alternatives:
migrationRisks:
```

QA marker adds required role-specific fields:

```text
coverageGaps:
verificationPlan:
regressionRisks:
```

The marker contract must be implemented through `_REQUIRED_BY_MARKER` and `_ALLOWED_BY_MARKER` or equivalent parser tables. Tests must reject missing `skillProfileUsed`, wrong marker-specific `skillProfileUsed`, missing `sourceThreadId`, missing `sourceRoleThreadId`, and wrong marker-specific `role`.

For `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW`, `sourceThreadId`, `sourceRoleThreadId`, `role`, and `skillProfileUsed` are required parser fields. This is intentionally stricter than the existing `TEAM_ROUTER_CALLBACK` and `TEAM_ROUTER_REVIEW` parser tables, where some direct-return identity checks are enforced later by manager inbox validation. Do not backfill the older markers in this change unless a separate migration explicitly asks for it.

Manual fallback metadata such as `deliveryStatus: fallback_only` and `deliveryError` remains optional only when direct-send is unavailable or failed.

The role prompt must require Chinese human-readable content for summaries, findings, risks, and required changes, while preserving protocol keys, paths, commands, filenames, enum values, and marker names literally.

## Rework Rules

`architect result: pass`

- Continue to executor dispatch.

`architect result: needs_rework`

- Do not dispatch executor yet.
- Return to manager/design/spec/executorPrompt revision.
- Set a distinct manager-level state such as `architect_rework_pending`; do not use the existing executor `needs_rework -> dispatched` path.
- Do not increment the executor `reworkCount`, because no executor implementation has run yet.
- The manager may ask architect for re-review after the design or executor prompt changes.
- First version does not add `architectReworkCount`, `maxArchitectRework`, or an exhaustion limit for architect re-reviews. Re-review requires an explicit revised design/spec/executorPrompt; it is not an automatic loop.

`architect result: blocked`

- Stop the current flow using the existing terminal `blocked` status.
- Do not continue to executor, reviewer, QA, or verifier in the same task.
- Resuming after missing context or boundary issues are resolved requires a new task or an explicit user restart path; first version does not add `architect_review_blocked` as a recoverable state.

`qa result: pass`

- Continue to verifier.

`qa result: needs_rework`

- Do not continue to verifier.
- Return to executor rework using the same executor role unless the role is unavailable, archived, broken, or the task boundary changed.
- QA `coverageGaps`, `verificationPlan`, and `regressionRisks` become executor rework input.
- Use the existing global `reworkCount` / `maxRework` counter because QA rework causes another executor implementation pass. First version does not add `qaReworkCount` or `maxQaRework`.

`qa result: blocked`

- Stop the current flow using the existing terminal `blocked` status.
- Do not continue to verifier in the same task.
- Resuming after missing evidence, environment issues, or acceptance criteria gaps are resolved requires a new task or an explicit user restart path; first version does not add `qa_review_blocked` as a recoverable state.

First version does not include `riskAcceptedOverride`. Allowing verifier to proceed despite QA `needs_rework` would weaken the gate and should be a separate design.

## Ledger Fields

Add:

```text
architectureReview
qaReview
```

Each field stores:

- request metadata under `architectureReview.request` / `qaReview.request`: role, threadId, expectedMarker or existing `expectedCallback`, sentAt, searchAnchor, returnThreadId, sourceRoleThreadId
- result metadata at the role review top level: result, capturedAt, receipt, protocol raw block
- review content: summary, findings, requiredChanges, evidenceChecked, risks
- role-specific content
- `skillProfileUsed`

`architectureReview` stores `architectureImpact`, `compatibilityNotes`, `alternatives`, and `migrationRisks`.

`qaReview` stores `coverageGaps`, `verificationPlan`, and `regressionRisks`.

These fields are authoritative Team Router ledger data, not external-material authority. They inform downstream prompts and verification, but do not carry user authorization or permission changes.

`architectureReview.request` and `qaReview.request` are the canonical watcher lookup paths. Watcher fallback must not infer request metadata from free-form review content or from the latest unrelated dispatch.

Ledger normalization must explicitly normalize both fields as mappings or `None`, following the existing `review` and `verification` pattern:

```text
architectureReview: null | mapping
qaReview: null | mapping
```

Do not leave these fields as untyped extras in the task ledger.

## State Machine

Add pending and recovery states, but avoid permanent result states that duplicate ledger fields.

Recommended additions:

```text
awaiting_architect_review
architect_review_unreachable
architect_rework_pending
awaiting_qa_review
qa_review_unreachable
```

State meaning:

- `awaiting_architect_review`: architect request sent; waiting for `TEAM_ROUTER_ARCHITECT_REVIEW`
- `architect_review_unreachable`: read window did not cover architect search anchor; recoverable to `awaiting_architect_review`
- `architect_rework_pending`: architect returned `needs_rework`; manager must revise design/spec/executorPrompt before re-requesting architect or dispatching executor
- `awaiting_qa_review`: QA request sent; waiting for `TEAM_ROUTER_QA_REVIEW`
- `qa_review_unreachable`: read window did not cover QA search anchor; recoverable to `awaiting_qa_review`

Recoverable status table additions:

```text
architect_review_unreachable -> awaiting_architect_review
qa_review_unreachable -> awaiting_qa_review
```

Do not add long-lived `architect_reviewed` or `qa_reviewed` unless implementation proves a need. After a `pass`, store the result in ledger and advance to the next active state.

Existing `needs_feedback`, `blocked`, and malformed marker behavior should be reused rather than duplicated. Existing executor `needs_rework` behavior is reused only for QA-triggered executor rework, not for architect pre-executor design rework.

## State Semantics

`blocked` from `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW` maps to the existing terminal `blocked` status in `TERMINAL_STATUSES`. First version does not add `architect_review_blocked` or `qa_review_blocked` to `STATE_MACHINE_SNAPSHOT`, `RECOVERABLE_STATUSES`, or watcher recovery logic.

Only unreachable states are recoverable in this design:

```text
architect_review_unreachable -> awaiting_architect_review
qa_review_unreachable -> awaiting_qa_review
```

`architect_rework_pending` is non-terminal and manager-facing. It blocks executor dispatch until the manager updates the design/spec/executorPrompt and either requests another architect review or explicitly starts a new task boundary. It must not call `next_rework_dispatch()`, must not use executor `reworkCount`, and must not be treated as executor `needs_rework`.

QA `needs_rework` is different: it returns to executor rework and uses the existing global `reworkCount` / `maxRework` semantics because executor implementation already happened.

## Direct Return

Direct-return handling must be expanded as a single coherent contract:

- `ROLE_NAMES` includes `architect` and `qa`
- `CORE_ROLE_NAMES` remains unchanged and does not include `architect` or `qa`
- `CONDITIONAL_ROLE_NAMES` includes `reviewer`, `architect`, and `qa`
- role display names and aliases include both new roles
- direct-return marker map includes `architect -> TEAM_ROUTER_ARCHITECT_REVIEW` and `qa -> TEAM_ROUTER_QA_REVIEW`
- `roleDirectReturn.markers` in `MANAGER_ORCHESTRATION_POLICY` and the `protocol_contract_snapshot()` output include both new mappings
- manager inbox capture validates `taskId`, `sourceThreadId`, `role`, `sourceRoleThreadId`, expected marker, and pending role
- direct returns from old, wrong, or non-pending roles are rejected or quarantined and must not advance the ledger
- watcher/heartbeat fallback can read self-thread markers for architect and QA using the same bounded polling rules
- `completionFeedback.requiredMarkers` includes `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW`

Role output alone in the child thread is not receipt. Completion is received only through valid direct-send to the parent or watcher fallback capture.

Prompt metadata by role:

```text
architectReviewDelivery: direct-send
architectReviewFallback: self-thread-marker
qaReviewDelivery: direct-send
qaReviewFallback: self-thread-marker
```

The direct-send body and self-thread fallback body must contain the same `TEAM_ROUTER_ARCHITECT_REVIEW` or `TEAM_ROUTER_QA_REVIEW` protocol block. The direct-return block must include `sourceThreadId`, `sourceRoleThreadId`, and marker-specific `role` so manager inbox validation can consume only the pending expected role.

If direct-send is unavailable, the manager records fallback-only delivery metadata and uses watcher/heartbeat capture. Fallback-only capture is degraded delivery, not proof that direct-send worked.

### Default Callback Contract

Team Router's default role completion contract is direct-return-first. A role thread is complete for runtime purposes only when the manager receives a valid direct-send protocol block at the pending `returnThreadId`, or when the manager explicitly records degraded fallback capture.

Runtime dispatch must distinguish two modes:

- `direct-return runtime`: adapter-created role dispatch has a parent/orchestrator `returnThreadId`, a role `roleThreadId`, and a callable `send_message_to_thread` path. The role prompt requires direct-send to `returnThreadId` with the complete `TEAM_ROUTER_*` block, then the role outputs the same block in its own thread as the self-thread marker fallback.
- `manual orchestration fallback`: a visible Codex role thread is created with `create_thread` and the manager later reads it with `read_thread`. This is allowed only as degraded/manual fallback. It must not be reported as successful proactive callback delivery.

If a dispatch path cannot provide `returnThreadId`, `roleThreadId`, or callable direct-send, the runtime must mark the request as `tool_error`, `manual orchestration only`, or `fallback_only` according to the existing side-effect taxonomy. It must not silently downgrade Team Router's default callback semantics to parent polling.

Tests must lock this distinction: child-thread protocol output alone is a self-thread marker, not receipt; valid manager-inbox direct-send is the normal receipt; bounded `read_thread` capture is fallback recovery.

### Task 4 Capture Semantics

Task 4 completes the receive side for architect and QA role results. It must accept valid manager-inbox direct returns before any role self-thread fallback read, and it must treat fallback reads as degraded recovery only.

Architect and QA capture must validate `taskId`, `sourceThreadId`, marker-specific `role`, `sourceRoleThreadId`, pending request role/thread, expected marker, and return target before mutating the ledger. Wrong-task, wrong-role, wrong-thread, stale, malformed, or non-pending returns are rejected or quarantined and must not advance state.

Task 4 state transitions are limited to role result receipt:

```text
architect pass -> planned
architect needs_rework -> architect_rework_pending
architect blocked -> blocked
qa pass -> verifying
qa needs_rework -> existing executor rework path
qa blocked -> blocked
```

Architect `pass` restores executor-dispatch eligibility but must not dispatch an executor by itself. Architect `needs_rework` preserves the role result and must not increment executor `reworkCount`. QA `needs_rework` uses the existing executor rework path and increments the existing global rework counter exactly once. Task 4 must not implement Task 5 gating that blocks executor/verifier requests based on whether architect/QA is required or passed.

Watcher fallback must mark missed self-thread read windows as `architect_review_unreachable` or `qa_review_unreachable` using the pending request anchor. These states are recoverable back to the corresponding awaiting state and are not successful proactive callback receipt.

## Code Extension Points

Implementation must explicitly update these runtime surfaces. This list is part of the design contract, not an optional implementation note:

- role constants: `ROLE_NAMES`, `CORE_ROLE_NAMES`, `CONDITIONAL_ROLE_NAMES`, `ROLE_DISPLAY_NAMES`, `ROLE_ALIASES`
- classifier constants or tables: `ARCHITECT_GATE_TERMS`, `QA_GATE_TERMS`, plus tests for explicit fields and baseline terms
- protocol parser tables: `_REQUIRED_BY_MARKER`, `_ALLOWED_BY_MARKER`, `CONDITIONAL_REQUIRED_BY_MARKER` if needed
- state constants: `STATE_MACHINE_SNAPSHOT`, `RECOVERABLE_STATUSES`, and `TERMINAL_STATUSES` only to confirm `blocked` remains terminal
- policy snapshot fields: `completionFeedback.requiredMarkers`, `MANAGER_ORCHESTRATION_POLICY.roleDirectReturn.markers`, `protocol_contract_snapshot()`
- direct-return request lookup helpers so `architect` resolves `architectureReview.request` and `qa` resolves `qaReview.request`
- `_direct_return_capture_allowed(ledger, role)` so `architect` is accepted only while status is `awaiting_architect_review` or `architect_review_unreachable`, or while `needs_feedback` targets `architect`; `qa` is accepted only while status is `awaiting_qa_review` or `qa_review_unreachable`, or while `needs_feedback` targets `qa`
- `_watch_next_wakeup(ledger)` so architect states read `architectureReview.request` and expect `TEAM_ROUTER_ARCHITECT_REVIEW`, and QA states read `qaReview.request` and expect `TEAM_ROUTER_QA_REVIEW`
- role request builders/prompts so dispatch includes explicit `role: Architect` / `role: QA`, `sourceRoleThreadId`, `returnThreadId`, and the marker-specific `skillProfileUsed`
- default direct-return prompt/runtime contract so role prompts require `send_message_to_thread(threadId=<returnThreadId>, prompt=<complete TEAM_ROUTER_* block>)` before relying on self-thread fallback
- direct-send and self-thread fallback capture so wrong role, wrong role thread, stale request, or old marker cannot advance the ledger
- verifier gating and evidence-only fast path so QA-gated flows cannot proceed without `qaReview.result: pass`

The implementation plan should update tests around these extension points before or alongside runtime changes. Missing `_direct_return_capture_allowed()` or `_watch_next_wakeup()` support is a blocking design failure because the marker can parse while the state machine still cannot receive it.

## Skill Profiles

Skill profiles are prompt-level profiles only. They do not load skills at runtime and do not grant authority.

`architect-default` profile:

- architecture boundaries
- dependency impact
- protocol compatibility
- alternatives
- migration risk

`qa-default` profile:

- test matrix
- regression surface
- acceptance criteria
- uncovered paths
- verification command suggestions

The prompt asks the role to apply the profile and return `skillProfileUsed` with the exact marker-specific enum.

## Verifier Integration

QA findings are verifier input. If `classify_qa_gate()` says QA is required:

- verifier request must not be sent while `qaReview` is missing
- verifier request must not be sent after `qaReview.result: needs_rework` or `blocked`
- evidence-only fast path must not be offered until `qaReview.result: pass`
- verifier prompt must include QA result, `coverageGaps`, `verificationPlan`, and `regressionRisks` after QA pass

Reviewer pass alone is no longer sufficient for evidence-only fast path in QA-gated flows.

### Task 5 Flow Gating Semantics

Task 5 completes the send-side gating and verifier integration only. It must use the Task 4 receive-side results already stored under `architectureReview.result` and `qaReview.result`; it must not reimplement capture, docs/fixtures, role creation policy, or Task 6 documentation work.

Executor dispatch is blocked only when `classify_architect_gate(ledger)` is true and the current `architectureReview.result.fields.result` is not `pass`. Missing architect result, `needs_rework`, `blocked`, malformed/stale architect result, or a non-pending architect flow must raise before adapter send or ledger rewrite. When architect is not required, existing executor dispatch behavior stays unchanged.

Verifier request is blocked only when `classify_qa_gate(ledger)` is true and the current `qaReview.result.fields.result` is not `pass`. Missing QA result, `needs_rework`, `blocked`, malformed/stale QA result, or a non-passing QA result must raise before adapter send or ledger rewrite. Reviewer pass alone is insufficient for verifier request eligibility in QA-gated flows.

The evidence-only verifier fast path must receive QA gate context. If QA is required and QA has not passed, it must return a not-allowed result with a clear QA reason and must not offer evidence-only acceptance wording. If QA is not required, current reviewer/evidence behavior must be preserved. If QA is required and passed, existing evidence checks still apply.

After QA pass, the verifier prompt must include the QA result context needed for final acceptance: QA `result`, `summary`, `coverageGaps`, `verificationPlan`, `regressionRisks`, `evidenceChecked`, and `risks` when present. This context is verifier input only; QA does not replace the verifier and does not mark the task done.

Task 5 must add tests proving architect-required executor dispatch rejects before architect pass and succeeds after architect pass; QA-required verifier request and evidence-only fast path reject before QA pass and succeed after QA pass; the verifier prompt includes QA context after QA pass; and non-QA / non-architect flows remain unchanged.

## Documentation

Keep `skills/codex-team-router/SKILL.md` short. It should only mention that `architect` and `qa` are formal conditional roles and point to the detailed reference.

Add a new reference file, recommended:

```text
skills/codex-team-router/references/conditional-roles.md
```

That reference owns:

- trigger rules
- flow positions
- marker fields
- rework loops
- skill profiles
- authority boundaries
- direct-return notes

Update existing references only where necessary for cross-links:

- `direct-return.md`
- `reviewer-gate.md`
- `manager-polling-cadence.md`
- `testing-and-quality-gates.md`

Also update policy text that lists the visible role boundary. Any text that currently says only `manager/executor/reviewer/verifier` must include `architect` and `qa` when referring to formal Team Router visible roles.

## Testing And Migration Checklist

The implementation plan must include tests before implementation changes where practical.

Required coverage:

- `protocol_contract_snapshot()` includes new roles, markers, marker fields, state additions, and direct-return policy.
- role constants and display names include architect and QA as conditional roles.
- `CORE_ROLE_NAMES` remains `manager`, `executor`, `verifier`; ordinary FAST/NORMAL task creation does not require `architect` or `qa`.
- parser accepts `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW` with required fields and enum validation.
- parser rejects missing `skillProfileUsed`, wrong marker-specific `skillProfileUsed`, missing `sourceThreadId`, missing `sourceRoleThreadId`, and wrong marker-specific `role`.
- ledger normalization round-trips `architectureReview` and `qaReview`.
- architect `pass` advances to executor dispatch eligibility.
- architect `needs_rework` blocks executor dispatch and records required changes.
- architect `needs_rework` enters `architect_rework_pending` or the chosen equivalent and does not call `next_rework_dispatch()` or increment executor `reworkCount`.
- QA `pass` advances to verifier eligibility.
- QA `needs_rework` returns to executor rework and blocks verifier.
- QA `needs_rework` increments the existing global `reworkCount`; rework exhaustion blocks the task through the existing `maxRework` semantics.
- QA-required flows cannot send verifier or offer evidence-only fast path while `qaReview` is missing, blocked, or `needs_rework`.
- QA-required flows that pass QA include QA result, `coverageGaps`, `verificationPlan`, and `regressionRisks` in the verifier prompt.
- `_direct_return_capture_allowed()` accepts architect/QA only in their pending, unreachable, or targeted `needs_feedback` states and rejects old, wrong, or non-pending role returns.
- `_watch_next_wakeup()` returns architect and QA wakeups from `architectureReview.request` and `qaReview.request`, including expected marker and search anchor.
- wrong-role or stale direct-return blocks are rejected or quarantined.
- watcher fallback can capture architect/QA self-thread markers.
- architect/QA `blocked` maps to the existing terminal `blocked` status; no recoverable blocked states are added in first version.
- architect re-review has no v1 counter or exhaustion limit; it requires an explicit revised design/spec/executorPrompt and does not touch executor `reworkCount`.
- docs tests keep `SKILL.md` under the size cap and confirm the new reference is listed.
- docs tests update `direct-return.md`, `manager-polling-cadence.md`, `testing-and-quality-gates.md`, and the visible role boundary text.
- tests update fake adapters and fixtures so `architect` and `qa` are inferred from the explicit dispatch `role:` field, not from free-text keyword scanning, and do not collapse to generic `role`.
- route classifier tests cover explicit fields, baseline term-derived architect/QA triggers, non-triggering ordinary tasks, and reviewer-gate independence.
- fixtures cover representative flows: architect-only, QA-only, architect + reviewer with no QA, combined architect + reviewer + QA, QA needs_rework, architect blocked, QA blocked.

## Open Risks

The implementation surface is broad. Adding two formal roles touches parser contract, state machine, direct return, watcher behavior, fixtures, docs, and tests. The safest implementation strategy is to land the contract and tests first, then implement architect and QA with shared helpers so the two roles do not duplicate reviewer logic.

If implementation risk is too high, a fallback plan is to implement `architect` first and reuse that tested pattern for `qa`. The product direction remains `Architect + QA`; the fallback is only an implementation sequencing choice.

## Acceptance Criteria

The spec is ready for implementation planning when:

- Architect and QA are formal conditional roles, not auxiliary free-text advice.
- Machine-readable route classifiers decide architect and QA gates.
- Classifier baseline terms are named and testable.
- QA `needs_rework` has a hard rework path back to executor and uses the existing global rework counter.
- Architect `needs_rework` has a hard path back to manager/design/executorPrompt revision and does not use executor rework dispatch.
- Architect and QA `blocked` results intentionally map to the existing terminal `blocked` status.
- Runtime extension points include `_direct_return_capture_allowed()` and `_watch_next_wakeup()` with exact role states and request paths.
- Direct-return validation consumes only the pending expected role.
- Direct-return runtime is the default completion path; `create_thread` plus `read_thread` polling is degraded/manual fallback, not proactive callback delivery.
- `skillProfileUsed` is a fixed marker-specific enum field.
- `CORE_ROLE_NAMES` and ordinary low-friction flows stay unchanged.
- QA-gated verifier requests and evidence-only fast path require QA pass.
- `reviewer` and `verifier` authority remains unchanged.
