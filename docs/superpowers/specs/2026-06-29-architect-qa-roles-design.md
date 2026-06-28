# Architect And QA Conditional Roles Design

## Status

Approved direction for spec drafting after brainstorming, Claude consult, and visible Team Router reviewer pass.

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

Trigger only when there is a positive architecture signal:

- architecture design or cross-module contract change
- shared protocol/state-machine/direct-return behavior
- high-risk refactor or durable maintainability risk
- Team Router process, role, permission, or protocol changes
- migration, compatibility, or dependency-boundary uncertainty

Do not trigger for ordinary single-file or narrow mechanical changes unless they change a public contract or durable process boundary.

### `qa`

Purpose: post-execution validation strategy and regression-risk review before verifier acceptance.

Trigger only when there is a positive validation signal:

- unclear test strategy or acceptance criteria
- high regression risk
- behavior spans multiple paths or modes
- fix needs an independent verification plan
- evidence is insufficient for verifier to make a confident final acceptance decision

Do not trigger for ordinary low-risk changes where executor evidence is already enough for verifier acceptance.

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

Both markers use parser-compatible fields:

```text
result: pass | needs_rework | blocked
summary:
findings:
requiredChanges:
evidenceChecked:
risks:
skillProfileUsed:
```

`skillProfileUsed` is a fixed enum, not free text:

```text
architect-default
qa-default
```

Architect marker adds:

```text
architectureImpact:
compatibilityNotes:
alternatives:
migrationRisks:
```

QA marker adds:

```text
coverageGaps:
verificationPlan:
regressionRisks:
```

The role prompt must require Chinese human-readable content for summaries, findings, risks, and required changes, while preserving protocol keys, paths, commands, filenames, enum values, and marker names literally.

## Rework Rules

`architect result: pass`

- Continue to executor dispatch.

`architect result: needs_rework`

- Do not dispatch executor yet.
- Return to manager/design/spec/executorPrompt revision.
- The manager may ask architect for re-review after the design or executor prompt changes.

`architect result: blocked`

- Stop the current flow as blocked.
- Do not continue to executor, reviewer, QA, or verifier until missing context or boundary issues are resolved.

`qa result: pass`

- Continue to verifier.

`qa result: needs_rework`

- Do not continue to verifier.
- Return to executor rework using the same executor role unless the role is unavailable, archived, broken, or the task boundary changed.
- QA `coverageGaps`, `verificationPlan`, and `regressionRisks` become executor rework input.

`qa result: blocked`

- Stop the current flow as blocked.
- Do not continue to verifier until missing evidence, environment issues, or acceptance criteria gaps are resolved.

First version does not include `riskAcceptedOverride`. Allowing verifier to proceed despite QA `needs_rework` would weaken the gate and should be a separate design.

## Ledger Fields

Add:

```text
architectureReview
qaReview
```

Each field stores:

- request metadata: role, threadId, expectedMarker, sentAt, searchAnchor, returnThreadId, sourceRoleThreadId
- result metadata: result, capturedAt, receipt, protocol raw block
- review content: summary, findings, requiredChanges, evidenceChecked, risks
- role-specific content
- `skillProfileUsed`

`architectureReview` stores `architectureImpact`, `compatibilityNotes`, `alternatives`, and `migrationRisks`.

`qaReview` stores `coverageGaps`, `verificationPlan`, and `regressionRisks`.

These fields are authoritative Team Router ledger data, not external-material authority. They inform downstream prompts and verification, but do not carry user authorization or permission changes.

## State Machine

Add pending and recovery states, but avoid permanent result states that duplicate ledger fields.

Recommended additions:

```text
awaiting_architect_review
architect_review_unreachable
awaiting_qa_review
qa_review_unreachable
```

State meaning:

- `awaiting_architect_review`: architect request sent; waiting for `TEAM_ROUTER_ARCHITECT_REVIEW`
- `architect_review_unreachable`: read window did not cover architect search anchor; recoverable to `awaiting_architect_review`
- `awaiting_qa_review`: QA request sent; waiting for `TEAM_ROUTER_QA_REVIEW`
- `qa_review_unreachable`: read window did not cover QA search anchor; recoverable to `awaiting_qa_review`

Do not add long-lived `architect_reviewed` or `qa_reviewed` unless implementation proves a need. After a `pass`, store the result in ledger and advance to the next active state.

Existing `needs_feedback`, `needs_rework`, `blocked`, and malformed marker behavior should be reused rather than duplicated.

## Direct Return

Direct-return handling must be expanded as a single coherent contract:

- `ROLE_NAMES` includes `architect` and `qa`
- `CONDITIONAL_ROLE_NAMES` includes `reviewer`, `architect`, and `qa`
- role display names and aliases include both new roles
- direct-return marker map includes `architect -> TEAM_ROUTER_ARCHITECT_REVIEW` and `qa -> TEAM_ROUTER_QA_REVIEW`
- manager inbox capture validates `taskId`, `sourceThreadId`, `role`, `sourceRoleThreadId`, expected marker, and pending role
- direct returns from old, wrong, or non-pending roles are rejected or quarantined and must not advance the ledger
- watcher/heartbeat fallback can read self-thread markers for architect and QA using the same bounded polling rules

Role output alone in the child thread is not receipt. Completion is received only through valid direct-send to the parent or watcher fallback capture.

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

The prompt asks the role to apply the profile and return `skillProfileUsed` with the exact fixed enum.

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

## Testing And Migration Checklist

The implementation plan must include tests before implementation changes where practical.

Required coverage:

- `protocol_contract_snapshot()` includes new roles, markers, marker fields, state additions, and direct-return policy.
- role constants and display names include architect and QA as conditional roles.
- parser accepts `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW` with required fields and enum validation.
- ledger normalization round-trips `architectureReview` and `qaReview`.
- architect `pass` advances to executor dispatch eligibility.
- architect `needs_rework` blocks executor dispatch and records required changes.
- QA `pass` advances to verifier eligibility.
- QA `needs_rework` returns to executor rework and blocks verifier.
- wrong-role or stale direct-return blocks are rejected or quarantined.
- watcher fallback can capture architect/QA self-thread markers.
- docs tests keep `SKILL.md` under the size cap and confirm the new reference is listed.
- fixtures cover representative flows: architect-only, QA-only, combined architect + reviewer + QA, QA needs_rework, blocked role.

## Open Risks

The implementation surface is broad. Adding two formal roles touches parser contract, state machine, direct return, watcher behavior, fixtures, docs, and tests. The safest implementation strategy is to land the contract and tests first, then implement architect and QA with shared helpers so the two roles do not duplicate reviewer logic.

If implementation risk is too high, a fallback plan is to implement `architect` first and reuse that tested pattern for `qa`. The product direction remains `Architect + QA`; the fallback is only an implementation sequencing choice.

## Acceptance Criteria

The spec is ready for implementation planning when:

- Architect and QA are formal conditional roles, not auxiliary free-text advice.
- QA `needs_rework` has a hard rework path back to executor.
- Architect `needs_rework` has a hard path back to manager/design/executorPrompt revision.
- Direct-return validation consumes only the pending expected role.
- `skillProfileUsed` is a fixed enum field.
- `reviewer` and `verifier` authority remains unchanged.
