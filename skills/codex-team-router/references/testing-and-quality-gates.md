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

## Version 2 Documentation Contract

Docs tests must lock the parent-owned V2 plan, no child Manager creation, Manager direct before side effects and only for read-only/design-only work, standard-entry versus explicit cost-aware model authorization, visible-thread-only dispatch, Luna/Terra/Sol defaults, and the Sol Ultra prohibition. They must also lock new FAST/NORMAL workspace-write Executor -> Verifier closure without automatic Reviewer, persisted pre-A3 low-risk route freezing, manager-owned pool reuse, canonical target/host fingerprinting, `parallelAllowed` propagation, bounded creation-intent recovery, one model-upgrade and one rework budget, and Manager-acceptance versus Reviewer/Verifier closure.

The routing receipt is a projection of requested dispatches. It may contain `routingReceipt`, `requestedModel`, `requestedThinking`, bootstrap/create/send acceptance, binding, upgrade, and rework fields; it must not contain `actualModel`, price, token, or cost claims. `requestedModel is not actualModel or billing evidence`.

Before the separate global sync, repo/global mismatch before sync is expected. `team_router_skill_sync_check.py --check` must report only repo-skill paths as `status: mismatch`; Task 10 is a separate explicit global-sync gate and is never part of a repository commit or Task 9 verification.

Tests must fail if the entrypoint grows past the 8KB cap, if required references are removed, if a project-local `AGENTS.md` is introduced without explicit authorization, or if key rules disappear from the combined SKILL.md plus references contract, including that protocol-block `sourceThreadId` must match `returnThreadId`. Tests must also lock the no-tools degradation rule: when required core thread tools or trusted identity evidence are unavailable, status must be `tool_error` / `manual orchestration only`, and copy-paste executor/reviewer/verifier prompts are handoff text rather than live Team Router dispatch evidence. Readiness tests must cover missing callable adapter, missing `parent_thread_id`, missing trusted Host sender/source or execution-domain identity, missing callable scheduler, and missing title support without pretending Codex app model-side tools are Python callables. Scheduler absence must downgrade unattended to interactive contract readiness; title absence must remain a warning.

`protocol_contract_snapshot()` is the code-side center of truth for role/state/marker contracts and policy snapshots. It must expose `sideEffectTaxonomy`, `roleCloseoutPolicy`, `roleHandoffReviewPackagePolicy`, and `agentAssistPolicy` so docs/tests do not drift from the implementation contract. Snapshot tests must lock the explicit path-field contract (`taskBriefPath`, `executorReportPath`, `reviewPackagePath`), gate-based package expectations, external-material safety boundary, Team Router project-context visible role defaults, and third-party skill intake boundary. Docs contract tests must also lock the active role return wording: `direct-send + self-thread-marker fallback`, `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`, `protocol direct-send is allowed and is not a workspace/file write`, `sourceRoleThreadId`, `role`, `taskId`, `two-step bootstrap`, `same protocol block body`, `deliveryStatus: fallback_only`, `deliveryError`, `protocol-block sourceThreadId must match returnThreadId`, `sourceRoleThreadId must match roleThreadId / role thread record`, `bounded result-collection read/check`, `continuous polling is not the default`, `inProgress is not polling permission`, and `CONTROL after bounded wait/read is not permission for immediate continuous read_thread polling`.

## Fixture Expectations

The fixture `tests/fixtures/team_router/live_read_thread_verdict.json` is a sanitized representative `read_thread` result from Codex desktop:

- top-level `schemaVersion`
- top-level `thread`
- `turns[].items[]`
- `agentMessage.text`
- numeric epoch `startedAt`

The unit test must prove that the fixture normalizes into a message containing `TEAM_ROUTER_VERDICT taskId=ctr-live-smoke-fixture-1` and keeps the numeric timestamp available for recovery-anchor filtering.

The fixture `tests/fixtures/team_router/live_manager_inbox_direct_return.json` is a sanitized representative manager-inbox direct-return result. It must prove that `normalize_thread_read_messages()` unwraps the `TEAM_ROUTER_CALLBACK`, promotes matching Host-structured `content[].codexDelegation` to `agentMessage`, preserves its trusted `sourceThreadId`, and keeps the numeric timestamp available before the parent state machine captures direct return. Text-only wrappers and conflicting structured metadata remain untrusted.

The fixture `tests/fixtures/team_router/three_role_visible_smoke_scenarios.json` snapshots the visible three-role mode. It must keep these paths represented:

- `direct-send-callback-success`: executor direct return reaches the parent inbox and records `returnThreadId`, `orchestratorThreadId`, `roleThreadId`, `returnSearchAnchor`, and `fallbackSearchAnchor`.
- `direct-send-missed-self-thread-fallback`: manager inbox misses direct return, so the self-thread marker and `read_thread searchAnchor` recover the callback on the 5 minutes / 300 seconds watcher fallback cadence.
- `direct-send-duplicate-callback-idempotent`: duplicate direct callbacks are ignored after the ledger advances past that role; observations are not recorded twice.
- `verifier-needs-rework`: verifier returns `needs_rework`; parent stops until user approval before redispatch.
- `verifier-blocked-closeout`: verifier returns `blocked`; parent emits `Team Router Closeout` with remaining work.

## Expected User Output

Version 2 Manager-acceptance and Verifier closeouts add `acceptedBy` and the same `routingReceipt`; a receipt reports requested routing rather than actual billing. Version 1 compatibility retains the fixed verifier output below.

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

- `explain_team_router_gate()` must keep `classify_team_router_gate()` compatible while treating local-package as permission rather than risk; `explain_team_router_route()` must report workspace-write Verifier closure, package term, reviewer-required term, fast docs term, normal fallback, and persisted V2 `routeRoles` consistently.
- UTF-8 contract assertions must lock `PACKAGE > STRICT bilingual risk > NORMAL bilingual QA floor > FAST > NORMAL fallback`; the five English/Chinese STRICT phrase groups require Reviewer and Architect, while `regression test / 回归测试` and `coverage gap / 覆盖缺口` keep a NORMAL floor with QA=true and Reviewer=false. They must also lock upgrade-only requested gates, the PACKAGE ceiling, complete-phrase false-positive boundaries, no A4 NLP/path-classifier/regex inference, FAST/NORMAL workspace-write Executor -> Verifier, `local-package` as permission rather than a Reviewer trigger, and historical persisted `routeRoles` compatibility.
- Malformed direct-return tests must cover wrong or missing protocol-block `sourceThreadId`, `role`, and `sourceRoleThreadId`; `_record_malformed_direct_return` should preserve the observed protocol field values and keep `self-thread-marker fallback` recovery without advancing the ledger.
- UTF-8 contract checks must distinguish V1 `角色-任务名` / `调度者-Team Router <task label>` / legacy discovery alias from V2 `管理者-Team Router <task label>` / `角色-Team Router <projectId>` / temporary `#2`, while preserving pool identity. They must also lock complete-outcome Executor delegation, terminal role outcomes `done | needs_feedback | blocked`, no continuation or micro-dispatch, and the unchanged callback enum `done | blocked`. Host write-capability failure evidence is `blocked + zero-write + clean worktree + exact error`; Manager broker-recovery must never be labeled Executor success, parallel writer success, isolated-worktree write, or hard permission.
- Regression coverage must lock independent worktree fan-out for multiple ready, dependency-free execution units with disjoint write sets, and must reject parallel execution for overlapping writes, ordering dependencies, or permission conflicts.

## Strict V2 Dispatch Correlation Regression Gate

- Every strict V2 fixture and role reply builder must echo `protocolVersion`, `dispatchId`, `requestId`, and positive `attempt` from the current prepared dispatch, exactly and without fixture-generated substitutes. The validator remains fail-closed for a missing, malformed, stale, or unknown-version value.
- A single protocol message with a duplicate field, or more than one final role marker for the same task, is malformed; duplicate receipts are identified by the same channel/message key and do not consume routing again.
- The delivery state sequence is `prepared` before send, `acknowledged` only after the send acknowledgement, and `outcome_unknown` when send outcome is not known. `outcome_unknown` has no automatic retry: later matching evidence may be accepted once.
- Result consumption is once-only. A late acknowledgement may add delivery evidence without undoing a consumed result; later distinct receipt evidence may be recorded without replaying state transitions.
- Current ownership is determined by the latest dispatch for the Role across strict and legacy records; a newer record of either version makes an older strict result non-current.
- A strict consume-and-route failure before persistence keeps the result pending, the task nonterminal, and the Role claim active. The exact correlated result must succeed after the routing prerequisite is repaired, without creating a second dispatch.
- Legacy V1 and designated live legacy V2 fixtures keep their existing shapes. Strict V2 correlation is not backfilled into them, and mixed strict/legacy or unknown-version receipts fail closed.

## Read-only Current-State Tools

- `scripts/team_router_closeout_check.py` remains read-only closeout evidence: report git status, diff files, SKILL hard cap and 7200 target, repo/global skill sync status, and unauthorized commit/push/global sync gates. It must not stage, commit, push, PR, merge, deploy, or sync.
- `scripts/team_router_truth_check.py` is read-only current-truth evidence: report branch status, short status, diff files, SKILL cap/target, repo/global skill comparison, stale workbench/package claims, and the same unauthorized gates. It must not stage, commit, push, PR, merge, deploy, or sync.
- `scripts/team_router_doctor.py` is read-only manager-facing status UX: summarize currentMode, truthStatus, orchestrationStatus, nextAction, and unauthorized actions without claiming role-thread creation or live dispatch unless explicit readiness evidence exists. It must not stage, commit, push, PR, merge, deploy, or sync.
- When `scripts/team_router_truth_check.py` reports `staleClaims`, `scripts/team_router_doctor.py` must tell the manager to refresh workbench/package current-state text from truth_check/doctor evidence before claiming current truth.
- Stale current-state detection should focus on explicit Current Task / Current Diff Surface / current-state sections, so completed historical package archives do not become false current blockers.
- These tools do not replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`; they are evidence inputs for executor/reviewer/verifier gates, not protocol acceptance.
## Host Readiness Snapshots

- `scripts/team_router_doctor.py --host-readiness-json <path> --json` accepts an evidence-only host adapter readiness snapshot and reports `hostReadiness` plus a derived `orchestrationStatus`.
- Without a host readiness snapshot, doctor remains `orchestrationStatus: manual/pre-created` and must not infer callable adapter support from model-side tool descriptors.
- When Codex app thread tools are exposed but the Python helper lacks a callable core adapter, explicit `parent_thread_id`, trusted Host sender/source identity, or trusted execution-domain identity, doctor reports `manual/pre-created`. Missing scheduler yields `interactive_contract_ready`; a callable scheduler permits `unattended_contract_ready`. Missing title support is warning-only.
- A supplied callable snapshot can prove only contract readiness. Only explicit `codex-desktop-live` call-count evidence may report `interactive_live_verified` or `unattended_live_verified`.
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
