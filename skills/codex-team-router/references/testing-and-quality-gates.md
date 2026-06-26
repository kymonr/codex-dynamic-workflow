# Testing And Quality Gates

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep testing and fixture details here.

## Progressive Disclosure

`skills/codex-team-router/SKILL.md` must stay under the Codex 8KB cap. It should contain navigation and hard entry rules only. Deep protocol material belongs in this `references/` directory, and these references are part of the Team Router contract.

Required reference files:

- `manager-mode.md`
- `side-effect-taxonomy.md`
- `role-handoff-and-review-package.md`
- `agent-assist-policy.md`
- `direct-return.md`
- `reviewer-gate.md`
- `role-closeout.md`
- `adapter-runtime.md`
- `manual-orchestration.md`
- `testing-and-quality-gates.md`

Tests must fail if the entrypoint grows past the 8KB cap, if required references are removed, if a project-local `AGENTS.md` is introduced without explicit authorization, or if key rules disappear from the combined SKILL.md plus references contract, including that protocol-block `sourceThreadId` must match `returnThreadId`.

`protocol_contract_snapshot()` is the code-side center of truth for role/state/marker contracts and policy snapshots. It must expose `sideEffectTaxonomy`, `roleCloseoutPolicy`, `roleHandoffReviewPackagePolicy`, and `agentAssistPolicy` so docs/tests do not drift from the implementation contract. Snapshot tests must lock the explicit path-field contract (`taskBriefPath`, `executorReportPath`, `reviewPackagePath`), gate-based package expectations, external-material safety boundary, Team Router project-context visible role defaults, and third-party skill intake boundary. Docs contract tests must also lock the active role return wording: `direct-send + self-thread-marker fallback`, `send_message_to_thread(sourceThreadId, protocolBlock)`, `sourceRoleThreadId`, `role`, `taskId`, `two-step bootstrap`, `same protocol block body`, `deliveryStatus: fallback_only`, `deliveryError`, `protocol-block sourceThreadId must match returnThreadId`, `sourceRoleThreadId must match roleThreadId / role thread record`, `bounded result-collection read/check`, and `continuous polling is not the default`.

## Fixture Expectations

The fixture `tests/fixtures/team_router/live_read_thread_verdict.json` is a sanitized representative `read_thread` result from Codex desktop:

- top-level `schemaVersion`
- top-level `thread`
- `turns[].items[]`
- `agentMessage.text`
- numeric epoch `startedAt`

The unit test must prove that the fixture normalizes into a message containing `TEAM_ROUTER_VERDICT taskId=ctr-live-smoke-fixture-1` and keeps the numeric timestamp available for recovery-anchor filtering.

The fixture `tests/fixtures/team_router/live_manager_inbox_direct_return.json` is a sanitized representative manager-inbox direct-return result. It must prove that `normalize_thread_read_messages()` unwraps the `TEAM_ROUTER_CALLBACK`, preserves `sourceThreadId`, and keeps the numeric timestamp available before the parent state machine captures direct return.

The fixture `tests/fixtures/team_router/three_role_visible_smoke_scenarios.json` snapshots the visible three-role mode. It must keep these paths represented:

- `direct-send-callback-success`: executor direct return reaches the parent inbox and records `returnThreadId`, `orchestratorThreadId`, `roleThreadId`, `returnSearchAnchor`, and `fallbackSearchAnchor`.
- `direct-send-missed-self-thread-fallback`: manager inbox misses direct return, so the self-thread marker and `read_thread searchAnchor` recover the callback on the 5 minutes / 300 seconds watcher fallback cadence.
- `direct-send-duplicate-callback-idempotent`: duplicate direct callbacks are ignored after the ledger advances past that role; observations are not recorded twice.
- `verifier-needs-rework`: verifier returns `needs_rework`; parent stops until user approval before redispatch.
- `verifier-blocked-closeout`: verifier returns `blocked`; parent emits `Team Router Closeout` with remaining work.

## Expected User Output

For a passing verifier result, the parent thread must display the helper output, not a rewritten summary:

```text
Team Router Closeout
taskId: <taskId>
status: done
threads:
  manager: <threadId>
  executor: <threadId>
  reviewer: <threadId when conditional reviewer gate applied>
  verifier: <threadId>
summary: <verifier summary>
evidenceChecked: <checked evidence>
risks: <none or risks>
nextAction: none
remainingTodos: none
compoundingDecision: skipped
reason: ordinary successful implementation/testing with no new reusable risk
```

For a non-terminal task, display the handoff so the next parent turn can resume from ledger/registry anchors. All closeout or handoff user output must include `remainingTodos`; passing verifier closeouts use `remainingTodos: none`, while `needs_rework` and `blocked` use the verifier `requiredChanges` or derived `nextAction`.
