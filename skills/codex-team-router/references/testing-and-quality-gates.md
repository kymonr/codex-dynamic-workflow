# Testing And Quality Gates

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep testing and fixture details here.

## Progressive Disclosure

`skills/codex-team-router/SKILL.md` must stay under the Codex 8KB cap. It should contain navigation and hard entry rules only. Deep protocol material belongs in this `references/` directory, and these references are part of the Team Router contract.

The hard cap remains 8KB, and the active entrypoint target is under 7200 bytes so future policy detail stays in references instead of the startup file. Tests should lock both the 7200 byte target and required hard-rule phrases.

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

Tests must fail if the entrypoint grows past the 8KB cap, if required references are removed, if a project-local `AGENTS.md` is introduced without explicit authorization, or if key rules disappear from the combined SKILL.md plus references contract, including that protocol-block `sourceThreadId` must match `returnThreadId`. Tests must also lock the no-tools degradation rule: when required thread tools are not exposed in the current host, status must be `tool_error` / `manual orchestration only`, and copy-paste executor/reviewer/verifier prompts are handoff text rather than live Team Router dispatch evidence. Readiness tests must cover missing callable adapter, missing `parent_thread_id`, missing callable `set_thread_title`, and missing callable heartbeat scheduler without pretending Codex app model-side tools are Python callables.

`protocol_contract_snapshot()` is the code-side center of truth for role/state/marker contracts and policy snapshots. It must expose `sideEffectTaxonomy`, `roleCloseoutPolicy`, `roleHandoffReviewPackagePolicy`, and `agentAssistPolicy` so docs/tests do not drift from the implementation contract. Snapshot tests must lock the explicit path-field contract (`taskBriefPath`, `executorReportPath`, `reviewPackagePath`), gate-based package expectations, external-material safety boundary, Team Router project-context visible role defaults, and third-party skill intake boundary. Docs contract tests must also lock the active role return wording: `direct-send + self-thread-marker fallback`, `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`, `protocol direct-send is allowed and is not a workspace/file write`, `sourceRoleThreadId`, `role`, `taskId`, `two-step bootstrap`, `same protocol block body`, `deliveryStatus: fallback_only`, `deliveryError`, `protocol-block sourceThreadId must match returnThreadId`, `sourceRoleThreadId must match roleThreadId / role thread record`, `bounded result-collection read/check`, `continuous polling is not the default`, `inProgress is not polling permission`, and `CONTROL after bounded wait/read is not permission for immediate continuous read_thread polling`.

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
receiptSource: <manager-inbox/direct-send or self-thread-fallback/read_thread>
receiptChannel: <manager-inbox or read_thread>
compoundingDecision: skipped
reason: ordinary successful implementation/testing with no new reusable risk
```

For a non-terminal task, display the handoff so the next parent turn can resume from ledger/registry anchors. All closeout or handoff user output must include `remainingTodos`; passing verifier closeouts use `remainingTodos: none`, while `needs_rework` and `blocked` use the verifier `requiredChanges` or derived `nextAction`.

Compatibility anchor: legacy shorthand send_message_to_thread(sourceThreadId, protocolBlock) means the same protocol delivery target as send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>); prefer the explicit `threadId=<returnThreadId>` form in role request templates.
## Optimization 1-6 Regression Gates

- `explain_team_router_gate()` must keep `classify_team_router_gate()` compatible while reporting readable reasons for local-package, package term, reviewer-required term, fast docs term, and normal fallback.
- Malformed direct-return tests must cover wrong or missing protocol-block `sourceThreadId`, `role`, and `sourceRoleThreadId`; `_record_malformed_direct_return` should preserve the observed protocol field values and keep `self-thread-marker fallback` recovery without advancing the ledger.
- `scripts/team_router_closeout_check.py` is read-only closeout evidence: report git status, diff files, SKILL hard cap and 7200 target, repo/global skill sync status, and unauthorized commit/push/global sync gates. It must not stage, commit, push, PR, merge, deploy, or sync.

## Read-only Current-State Tools

- `scripts/team_router_closeout_check.py` remains read-only closeout evidence: report git status, diff files, SKILL hard cap and 7200 target, repo/global skill sync status, and unauthorized commit/push/global sync gates. It must not stage, commit, push, PR, merge, deploy, or sync.
- `scripts/team_router_truth_check.py` is read-only current-truth evidence: report branch status, short status, diff files, SKILL cap/target, repo/global skill comparison, stale workbench/package claims, and the same unauthorized gates. It must not stage, commit, push, PR, merge, deploy, or sync.
- `scripts/team_router_doctor.py` is read-only manager-facing status UX: summarize currentMode, truthStatus, orchestrationStatus, nextAction, and unauthorized actions without claiming role-thread creation or live dispatch unless explicit readiness evidence exists. It must not stage, commit, push, PR, merge, deploy, or sync.
- These tools do not replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`; they are evidence inputs for executor/reviewer/verifier gates, not protocol acceptance.
## Host Readiness Snapshots

- `scripts/team_router_doctor.py --host-readiness-json <path> --json` accepts an evidence-only host adapter readiness snapshot and reports `hostReadiness` plus a derived `orchestrationStatus`.
- Without a host readiness snapshot, doctor remains `orchestrationStatus: manual_only` and must not infer callable adapter support from model-side tool descriptors.
- When Codex app thread tools are exposed but the Python helper lacks a callable adapter, explicit `parent_thread_id`, callable `set_thread_title`, or callable heartbeat scheduler evidence, doctor reports `host_contract_blocked` with missing items such as `callable adapter`, `parent_thread_id`, and `callable heartbeat scheduler`.
- Only a supplied snapshot proving callable thread tools, callable `set_thread_title`, explicit `parent_thread_id`, and callable heartbeat scheduler may report `adapter_smoke_ready`.
- The boundary text must keep this sentence true: model-side Codex app tool exposure is not a Python callable adapter. This status surface is evidence-only; it does not create, read, poll, send, stage, commit, push, PR, merge, deploy, or sync.
## Role Thread Status Snapshots

- `scripts/team_router_doctor.py --role-status-json <path> --json` accepts a bounded, caller-supplied role-thread snapshot and reports `roleThreadStatus`.
- The snapshot status vocabulary is `missing`, `created_not_visible`, `visible_waiting`, `active_wait`, and `protocol_returned`.
- This is evidence-only status UX. It does not create, read, poll, send, stage, commit, push, PR, merge, deploy, or sync.
- `active_wait` means observe under the existing cadence; it is not permission for immediate continuous `read_thread` polling.
- `protocol_returned` means the expected marker was present in supplied evidence; final acceptance still requires reviewer/verifier protocol gates as applicable.
## Conditional Role Coverage

See `references/conditional-roles.md` for architect and QA semantics.

The fixture `tests/fixtures/team_router/architect_qa_visible_smoke_scenarios.json` snapshots conditional role visible flows and must cover exactly these scenario names:

- `architect_only`
- `qa_only`
- `architect_reviewer_no_qa`
- `architect_reviewer_qa`
- `qa_needs_rework`
- `architect_blocked`
- `qa_blocked`

Docs and runtime tests must keep marker mapping for `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW`, parser-required `sourceThreadId`, `sourceRoleThreadId`, `role`, and `skillProfileUsed`, direct-return request paths, watcher fallback, architect/QA result transitions, QA-gated verifier request, and QA-gated evidence-only fast path covered.
