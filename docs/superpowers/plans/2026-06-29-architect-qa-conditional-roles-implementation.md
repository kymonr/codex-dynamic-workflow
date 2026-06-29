# Architect QA Conditional Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fixed conditional `architect` and `qa` Team Router role threads with protocol markers, route classifiers, ledger state, direct-return handling, verifier gating, docs, and tests.

**Architecture:** Preserve the existing Manager -> Executor -> Reviewer -> Verifier path. Add `architect` only before executor dispatch and `qa` only before verifier acceptance. Land tests around parser/snapshot/classifier/state/direct-return/watcher/verifier gating before runtime behavior so a marker cannot parse unless the state machine can also receive it.

**Tech Stack:** Python standard library, `unittest`, JSON fixtures, Markdown docs, Team Router runtime in `src/team_router.py`.

## Global Constraints

- Spec source: `docs/superpowers/specs/2026-06-29-architect-qa-roles-design.md`.
- Add only two fixed built-in conditional roles: `architect` and `qa`.
- Keep `CORE_ROLE_NAMES` as `manager`, `executor`, `verifier`.
- No custom role registry, runtime skill loading, push, PR, merge, deploy, release, or global skill sync.
- `skillProfileUsed` is a marker enum: `architect-default` or `qa-default`.
- Architect/QA `blocked` maps to existing terminal `blocked`; do not add recoverable blocked states.
- `architect_rework_pending` does not call `next_rework_dispatch()` and does not increment executor `reworkCount`.
- QA `needs_rework` uses the existing executor rework path and global `reworkCount` / `maxRework`.
- New markers require `sourceThreadId`, `sourceRoleThreadId`, `role`, and `skillProfileUsed`; do not backfill older markers in this package.
- Task 3 must implement Team Router direct-return runtime as the default callback path; `create_thread` plus `read_thread` polling is degraded/manual fallback only and must not be reported as proactive callback delivery.
- Plan snippets must use real current APIs or explicitly introduce new test helpers before use. Current parser API is `parse_message(text, marker, task_id)`, not `parse_protocol_block(...)`.
- Test skeletons in this plan are names plus required assertions, not completed tests. Implementation may not leave comment-only/empty tests for Task 4 transition, direct-return, unreachable, or re-review behavior.
- Execute serially. These tasks touch one shared protocol/state machine and should not be split across parallel writer roles.
- Commit steps are gated. Run them only if the user explicitly authorizes a local commit package during implementation.

---

## File Structure

- Modify: `src/team_router.py` - role constants, marker parser tables, classifiers, snapshot/policy fields, ledger normalization, request builders, direct-return capture, watcher wakeups, flow transitions, QA verifier gating.
- Modify: `tests/test_team_router.py` - focused tests for constants, snapshot, parser, classifiers, ledger, direct return, watcher, flow gating, docs, and `FakeThreadAdapter` role inference.
- Create: `tests/fixtures/team_router/architect_qa_visible_smoke_scenarios.json` - representative architect/QA role flows.
- Create: `skills/codex-team-router/references/conditional-roles.md` - detailed architect/QA policy reference.
- Modify: `skills/codex-team-router/SKILL.md` - one short pointer to the new reference; keep under the Codex size cap.
- Modify: `skills/codex-team-router/references/direct-return.md`, `reviewer-gate.md`, `manager-polling-cadence.md`, `testing-and-quality-gates.md` - cross-links and runtime contract details.

---

### Task 1: Contract Constants, Markers, And Snapshot

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Produces: `ROLE_NAMES`, `CONDITIONAL_ROLE_NAMES`, `ROLE_DISPLAY_NAMES`, `ROLE_ALIASES` entries for `architect` and `qa`.
- Produces: parser contract for `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW`.
- Produces: `protocol_contract_snapshot()` with new roles, markers, state additions, recoverable statuses, and required marker policy.

- [ ] **Step 1: Write failing snapshot tests**

Add tests near the existing protocol snapshot tests:

```python
def test_protocol_contract_snapshot_includes_architect_and_qa_roles(self):
    snapshot = team_router.protocol_contract_snapshot()
    self.assertEqual(set(snapshot["roleThreads"]), {"architect", "executor", "manager", "qa", "reviewer", "verifier"})
    self.assertEqual(snapshot["roleThreads"]["architect"]["displayName"], "架构师")
    self.assertEqual(snapshot["roleThreads"]["architect"]["englishAlias"], "Architect")
    self.assertTrue(snapshot["roleThreads"]["architect"]["conditional"])
    self.assertEqual(snapshot["roleThreads"]["qa"]["displayName"], "QA")
    self.assertEqual(snapshot["roleThreads"]["qa"]["englishAlias"], "QA")
    self.assertTrue(snapshot["roleThreads"]["qa"]["conditional"])
    self.assertEqual(team_router.CORE_ROLE_NAMES, frozenset({"manager", "executor", "verifier"}))


def test_architect_and_qa_markers_have_required_fields_and_enums(self):
    markers = team_router.protocol_contract_snapshot()["markers"]
    architect_required = set(markers["TEAM_ROUTER_ARCHITECT_REVIEW"]["requiredFields"])
    qa_required = set(markers["TEAM_ROUTER_QA_REVIEW"]["requiredFields"])
    self.assertTrue({"result", "sourceThreadId", "sourceRoleThreadId", "role", "summary", "findings", "requiredChanges", "evidenceChecked", "risks", "skillProfileUsed", "architectureImpact", "compatibilityNotes", "alternatives", "migrationRisks"}.issubset(architect_required))
    self.assertTrue({"result", "sourceThreadId", "sourceRoleThreadId", "role", "summary", "findings", "requiredChanges", "evidenceChecked", "risks", "skillProfileUsed", "coverageGaps", "verificationPlan", "regressionRisks"}.issubset(qa_required))
    self.assertEqual(markers["TEAM_ROUTER_ARCHITECT_REVIEW"]["allowedValues"]["role"], ["Architect"])
    self.assertEqual(markers["TEAM_ROUTER_ARCHITECT_REVIEW"]["allowedValues"]["skillProfileUsed"], ["architect-default"])
    self.assertEqual(markers["TEAM_ROUTER_QA_REVIEW"]["allowedValues"]["role"], ["QA"])
    self.assertEqual(markers["TEAM_ROUTER_QA_REVIEW"]["allowedValues"]["skillProfileUsed"], ["qa-default"])
```

- [ ] **Step 2: Run RED**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v`

Expected: FAIL because the new roles and markers do not exist.

- [ ] **Step 3: Implement constants and marker tables**

In `src/team_router.py`, update role constants:

```python
ROLE_NAMES = frozenset({"manager", "executor", "reviewer", "verifier", "architect", "qa"})
CORE_ROLE_NAMES = frozenset({"manager", "executor", "verifier"})
CONDITIONAL_ROLE_NAMES = frozenset({"reviewer", "architect", "qa"})
ROLE_DISPLAY_NAMES.update({"architect": "架构师", "qa": "QA"})
ROLE_ALIASES.update({"architect": "Architect", "qa": "QA"})
```

Add `_ALLOWED_BY_MARKER` entries:

```python
"TEAM_ROUTER_ARCHITECT_REVIEW": {"result": {"pass", "needs_rework", "blocked"}, "role": {"Architect"}, "skillProfileUsed": {"architect-default"}},
"TEAM_ROUTER_QA_REVIEW": {"result": {"pass", "needs_rework", "blocked"}, "role": {"QA"}, "skillProfileUsed": {"qa-default"}},
```

Add `_REQUIRED_BY_MARKER` tuples with all fields asserted in Step 1.

- [ ] **Step 4: Add state and policy snapshot entries**

Add recoverable states:

```python
RECOVERABLE_STATUSES.update({
    "architect_review_unreachable": "awaiting_architect_review",
    "qa_review_unreachable": "awaiting_qa_review",
})
```

Add `awaiting_architect_review`, `architect_rework_pending`, and `awaiting_qa_review` to `STATE_MACHINE_SNAPSHOT["main"]`, add unreachable mappings to `manual_recovery`, and keep `blocked` only in terminal statuses.

Add the new markers to `MANAGER_ORCHESTRATION_POLICY["completionFeedback"]["requiredMarkers"]` and to `MANAGER_ORCHESTRATION_POLICY["roleDirectReturn"]["markers"]` as `architect -> TEAM_ROUTER_ARCHITECT_REVIEW` and `qa -> TEAM_ROUTER_QA_REVIEW`.

- [ ] **Step 5: Run GREEN**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v`

Expected: PASS for the new contract tests.

- [ ] **Step 6: Commit gate**

If local commit is authorized: `git add src\team_router.py tests\test_team_router.py; git commit -m "feat: add architect qa role contract"`.

---

### Task 2: Route Classifiers And Fake Adapter Inference

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Produces: `ARCHITECT_GATE_TERMS`, `QA_GATE_TERMS`, `classify_architect_gate(ledger) -> bool`, `classify_qa_gate(ledger) -> bool`, `explain_team_router_route(ledger) -> dict[str, Any]`.
- Produces: `FakeThreadAdapter.create_thread()` role inference from explicit `role:` field before keyword scanning.

- [ ] **Step 1: Write failing classifier tests**

Add tests:

```python
def test_architect_gate_classifier_uses_explicit_fields_and_baseline_terms(self):
    self.assertTrue(team_router.classify_architect_gate({"plan": {"fields": {"requiresArchitect": True}}}))
    for ledger in ({"objective": "change shared protocol contract"}, {"plan": {"fields": {"scope": "state-machine and direct-return behavior"}}}, {"plan": {"fields": {"riskBoundary": "migration compatibility uncertainty"}}}):
        self.assertTrue(team_router.classify_architect_gate(ledger))
    self.assertFalse(team_router.classify_architect_gate({"objective": "ask architect to look at typo"}))


def test_qa_gate_classifier_uses_explicit_fields_and_baseline_terms(self):
    self.assertTrue(team_router.classify_qa_gate({"plan": {"fields": {"requiresQa": True}}}))
    for ledger in ({"objective": "unclear acceptance criteria"}, {"plan": {"fields": {"scope": "high regression risk across multiple paths"}}}, {"plan": {"fields": {"notes": "test matrix needed because evidence insufficient"}}}):
        self.assertTrue(team_router.classify_qa_gate(ledger))
    self.assertFalse(team_router.classify_qa_gate({"objective": "ask qa to glance at a comment"}))


def test_route_explanation_keeps_reviewer_independent_from_architect_and_qa(self):
    route = team_router.explain_team_router_route({"objective": "Team Router role protocol change with regression risk"})
    self.assertEqual(route["flow"], ["architect", "executor", "reviewer", "qa", "verifier"])
```

- [ ] **Step 2: Write failing FakeThreadAdapter test**

```python
def test_fake_thread_adapter_infers_architect_and_qa_from_explicit_role_field(self):
    adapter = FakeThreadAdapter()
    self.assertEqual(adapter.create_thread(prompt="中文说明\nrole: Architect\n")["threadId"], "thread-architect")
    self.assertEqual(adapter.create_thread(prompt="中文说明\nrole: QA\n")["threadId"], "thread-qa")


def test_fake_thread_adapter_does_not_infer_architect_or_qa_from_free_text(self):
    adapter = FakeThreadAdapter()
    self.assertNotEqual(adapter.create_thread(prompt="please ask architect about this\n")["threadId"], "thread-architect")
    self.assertNotEqual(adapter.create_thread(prompt="qa should glance at this later\n")["threadId"], "thread-qa")
```

- [ ] **Step 3: Run RED**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v`

Expected: FAIL because helpers and adapter behavior are absent.

- [ ] **Step 4: Implement classifier constants and helpers**

Add baseline tuples from the spec: `ARCHITECT_GATE_TERMS` with architecture, architectural, cross-module, contract change, protocol, state-machine, direct-return, role protocol, permission boundary, migration, compatibility, dependency-boundary, high-risk refactor, durable maintainability; `QA_GATE_TERMS` with test strategy, acceptance criteria, regression, verification plan, coverage gap, multiple paths, multiple modes, evidence insufficient, smoke, test matrix.

Add helpers using `_reviewer_gate_text(ledger)` and explicit fields `requiresArchitect`, `architectureGateRequired`, `requiresQa`, `qaGateRequired`. Bare role names must not be standalone trigger terms.

- [ ] **Step 5: Implement explicit role inference in `FakeThreadAdapter`**

In `FakeThreadAdapter.create_thread()`, parse `role:` lines first and map `Architect` to `architect`, `QA` to `qa`. Fallback keyword scanning remains only for legacy roles `manager`, `executor`, `verifier`, and `reviewer`; do not infer `architect` or `qa` from free text.

- [ ] **Step 6: Run GREEN**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v`

Expected: PASS for classifier and fake adapter tests.

- [ ] **Step 7: Commit gate**

If local commit is authorized: `git add src\team_router.py tests\test_team_router.py; git commit -m "feat: classify architect qa gates"`.

---

### Task 3: Ledger Fields, Role Request Builders, And Dispatch Prompts

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Produces: normalized `architectureReview` and `qaReview` mappings.
- Produces: `make_architect_review_request_message(...)`, `make_qa_review_request_message(...)`, `send_architect_review_request_with_adapter(...)`, `send_qa_review_request_with_adapter(...)`.
- Consumes: `_ensure_role_with_adapter()`, `_adapter_call()`, `thread_send_anchor()`, `save_task_ledger()`, and existing read cadence helpers.

**Default Callback Addendum:**

Task 3 is the first runtime step after the Task 1-2 contract/classifier baseline. It must implement Team Router callback semantics as direct-return-first, not as a visible child-thread plus parent polling workflow.

- Role request prompts must explicitly require the role to call `send_message_to_thread(threadId=<returnThreadId>, prompt=<complete TEAM_ROUTER_* block>)` with the full marker block, then output the same block in its own thread as the self-thread marker fallback.
- Request records must distinguish `direct-return runtime` from `manual orchestration fallback`. A request without `returnThreadId`, `roleThreadId`, or callable direct-send support must be marked `tool_error`, `manual orchestration only`, or `fallback_only`; it must not be treated as successful proactive callback delivery.
- Manager receipt must prefer valid manager-inbox direct-send. Bounded `read_thread` capture remains only fallback recovery from the role self-thread marker.
- Tests must assert both the prompt text and the request metadata so child-thread output alone is never counted as default receipt.

- [ ] **Step 1: Write failing ledger normalization test**

```python
def test_task_ledger_normalizes_architecture_and_qa_review_fields(self):
    with workspace_temp_dir() as state_root:
        task_id = "ctr-architect-qa-normalize"
        project_id = "project-123"
        path = team_router.task_path(state_root, project_id, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "taskId": task_id,
            "projectId": project_id,
            "status": "awaiting_architect_review",
            "architectureReview": {"request": {"threadId": "thread-architect"}},
            "qaReview": {"request": {"threadId": "thread-qa"}},
        }), encoding="utf-8")
        ledger = team_router.load_task_ledger(state_root, project_id, task_id)
    self.assertEqual(ledger["architectureReview"]["request"]["threadId"], "thread-architect")
    self.assertEqual(ledger["qaReview"]["request"]["threadId"], "thread-qa")
```

- [ ] **Step 2: Write failing prompt tests**

```python
def test_architect_review_request_prompt_contains_marker_identity_and_skill_profile(self):
    message = team_router.make_architect_review_request_message(
        task_id="ctr-1",
        objective="change state-machine protocol",
        scope="Team Router state machine",
        return_thread_id="manager-thread",
        role_thread_id="thread-architect",
        plan_fields={"riskBoundary": "direct-return"},
    )
    for needle in ("TEAM_ROUTER_ARCHITECT_REVIEW", "sourceThreadId: manager-thread", "sourceRoleThreadId: thread-architect", "role: Architect", "skillProfileUsed: architect-default", "architectureImpact:", "compatibilityNotes:", "alternatives:", "migrationRisks:", "architectReviewDelivery: direct-send", "architectReviewFallback: self-thread-marker", "send_message_to_thread(threadId=<returnThreadId>", "manual orchestration fallback"):
        self.assertIn(needle, message)


def test_qa_review_request_prompt_contains_marker_identity_and_skill_profile(self):
    message = team_router.make_qa_review_request_message(
        task_id="ctr-1",
        executor_callback="TEAM_ROUTER_CALLBACK taskId=ctr-1\nstatus: done\nsummary: ok",
        scope="Team Router verifier gating",
        return_thread_id="manager-thread",
        role_thread_id="thread-qa",
        plan_fields={"riskBoundary": "regression"},
        reviewer_result={"fields": {"result": "pass", "summary": "ok"}},
    )
    for needle in ("TEAM_ROUTER_QA_REVIEW", "sourceThreadId: manager-thread", "sourceRoleThreadId: thread-qa", "role: QA", "skillProfileUsed: qa-default", "coverageGaps:", "verificationPlan:", "regressionRisks:", "qaReviewDelivery: direct-send", "qaReviewFallback: self-thread-marker", "send_message_to_thread(threadId=<returnThreadId>", "manual orchestration fallback"):
        self.assertIn(needle, message)
```

- [ ] **Step 3: Run RED**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`

Expected: FAIL because ledger fields and prompt builders are missing.

- [ ] **Step 4: Normalize ledger fields**

In `_normalize_task_ledger()`, add explicit mapping normalization for `architectureReview` and `qaReview` using the same `_as_mapping(..., default_empty=False)` pattern as `review` and `verification`.

- [ ] **Step 5: Add prompt builders**

Add `make_architect_review_request_message(...)` near reviewer prompt helpers. It must include: read-only authority text, `TEAM_ROUTER_ARCHITECT_REVIEW`, `sourceThreadId`, `sourceRoleThreadId`, `role: Architect`, `skillProfileUsed: architect-default`, `architectureImpact`, `compatibilityNotes`, `alternatives`, `migrationRisks`, `architectReviewDelivery: direct-send`, and `architectReviewFallback: self-thread-marker`.

Add `make_qa_review_request_message(...)`. It must include: read-only authority text, `TEAM_ROUTER_QA_REVIEW`, `sourceThreadId`, `sourceRoleThreadId`, `role: QA`, `skillProfileUsed: qa-default`, `coverageGaps`, `verificationPlan`, `regressionRisks`, `qaReviewDelivery: direct-send`, and `qaReviewFallback: self-thread-marker`.

- [ ] **Step 6: Add send request functions**

Add `send_architect_review_request_with_adapter(...)`:

```python
# Required behavior shape
if not classify_architect_gate(ledger):
    raise StateStoreError("architect gate is not required for task: %s" % task_id)
# ensure role "architect"
# send make_architect_review_request_message(...)
# store ledger["architectureReview"] = {"request": {"role": "architect", "threadId": architect_thread_id, "expectedMarker": "TEAM_ROUTER_ARCHITECT_REVIEW", "expectedCallback": "TEAM_ROUTER_ARCHITECT_REVIEW", "sentAt": anchor["sentAt"], "messageId": anchor["messageId"], "searchAnchor": anchor, "returnThreadId": return_thread_id, "orchestratorThreadId": return_thread_id, "roleThreadId": architect_thread_id, "sourceRoleThreadId": architect_thread_id, "architectReviewDelivery": "direct-send", "architectReviewFallback": "self-thread-marker", "fallbackSearchAnchor": anchor, "returnSearchAnchor": {"messageId": None, "sentAt": anchor["sentAt"]}, "revisionInputHash": revision_input_hash, "revisionInputSource": revision_input_source}}
# set ledger["status"] = "awaiting_architect_review"
```

Add `send_qa_review_request_with_adapter(...)`:

```python
# Required behavior shape
if not classify_qa_gate(ledger):
    raise StateStoreError("QA gate is not required for task: %s" % task_id)
# require latest executor callback observation
# ensure role "qa"
# send make_qa_review_request_message(...)
# store ledger["qaReview"] = {"request": {"role": "qa", "threadId": qa_thread_id, "expectedMarker": "TEAM_ROUTER_QA_REVIEW", "expectedCallback": "TEAM_ROUTER_QA_REVIEW", "sentAt": anchor["sentAt"], "messageId": anchor["messageId"], "searchAnchor": anchor, "returnThreadId": return_thread_id, "orchestratorThreadId": return_thread_id, "roleThreadId": qa_thread_id, "sourceRoleThreadId": qa_thread_id, "qaReviewDelivery": "direct-send", "qaReviewFallback": "self-thread-marker", "fallbackSearchAnchor": anchor, "returnSearchAnchor": {"messageId": None, "sentAt": anchor["sentAt"]}}}
# set ledger["status"] = "awaiting_qa_review"
```

Use the existing reviewer/verifier read discipline pattern; do not introduce a tighter polling cadence. Add request-record tests that call the actual send helpers and assert the saved `architectureReview.request` / `qaReview.request` include the delivery/fallback fields required by `_direct_return_record()`: `architectReviewDelivery` / `qaReviewDelivery`, fallback marker field, `returnThreadId`, `orchestratorThreadId`, `roleThreadId`, `sourceRoleThreadId`, `fallbackSearchAnchor`, and `returnSearchAnchor`.

- [ ] **Step 7: Run GREEN**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`

Expected: PASS for ledger and prompt/request tests.

- [ ] **Step 8: Commit gate**

If local commit is authorized: `git add src\team_router.py tests\test_team_router.py; git commit -m "feat: add architect qa role requests"`.

---

### Task 4: Parser Capture, Direct Return, Watcher Wakeups, And Result Transitions

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Produces: architect/QA capture from direct-send and self-thread fallback.
- Produces: `_direct_return_record()` lookup support for `architectureReview.request` and `qaReview.request`.
- Produces: `_direct_return_capture_allowed()` support for `architect` and `qa`.
- Produces: manager inbox direct-return capture branches for architect and QA.
- Produces: `watch_team_task_with_adapter()` direct-return branches for architect and QA.
- Produces: `_watch_next_wakeup()` branches using `architectureReview.request` and `qaReview.request`.
- Produces: result transitions for architect pass/needs_rework/blocked and QA pass/needs_rework/blocked.
- Produces: read-window miss paths that enter `architect_review_unreachable` and `qa_review_unreachable`.
- Produces: explicit architect re-review from `architect_rework_pending` only after revised design/spec/executorPrompt is supplied.

**Task 4 Scope Delta:**

Task 4 is the receive-side runtime for architect/QA role results. It must not implement Task 5 gating. Do not block executor dispatch merely because architect is required, and do not block verifier/evidence-only paths merely because QA is required; those policy gates remain Task 5.

Task 4 must implement these state semantics:

- manager-inbox direct-send capture is preferred and runs before role self-thread fallback reads.
- fallback self-thread reads are degraded recovery only.
- wrong task, wrong role, wrong role thread, stale request, malformed marker, or non-pending return is rejected or quarantined without mutating the ledger.
- architect `pass` records `architectureReview.result` and returns to `planned`; it does not create executor dispatch.
- architect `needs_rework` records `architectureReview.result`, moves to `architect_rework_pending`, and does not increment executor `reworkCount`.
- architect `blocked` records result and moves to terminal `blocked`.
- QA `pass` records `qaReview.result` and returns to `verifying`.
- QA `needs_rework` records `qaReview.result` and uses the existing executor rework path, incrementing the existing global `reworkCount` exactly once.
- QA `blocked` records result and moves to terminal `blocked`.
- read-window misses use the pending request anchors and move to `architect_review_unreachable` / `qa_review_unreachable`.

- [ ] **Step 1: Write failing parser identity tests**

```python
def test_architect_and_qa_markers_reject_missing_identity_fields(self):
    cases = [
        ("TEAM_ROUTER_ARCHITECT_REVIEW", "Architect", "skillProfileUsed: architect-default\narchitectureImpact: shared state\ncompatibilityNotes: ok\nalternatives: none\nmigrationRisks: low"),
        ("TEAM_ROUTER_QA_REVIEW", "QA", "skillProfileUsed: qa-default\ncoverageGaps: none\nverificationPlan: py -B -m unittest tests.test_team_router\nregressionRisks: low"),
    ]
    for marker, role, extra in cases:
        base = f"{marker} taskId=ctr-1\nresult: pass\nsourceThreadId: parent-thread\nsourceRoleThreadId: role-thread\nrole: {role}\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none\n{extra}\n"
        for missing in ("sourceThreadId", "sourceRoleThreadId", "role", "skillProfileUsed"):
            filtered = "\n".join(line for line in base.splitlines() if not line.startswith(missing + ":"))
            with self.assertRaises(team_router.ProtocolError):
                team_router.parse_message(filtered, marker, "ctr-1")


def test_architect_and_qa_markers_reject_wrong_role_and_skill_profile_enums(self):
    architect = "TEAM_ROUTER_ARCHITECT_REVIEW taskId=ctr-1\nresult: pass\nsourceThreadId: parent-thread\nsourceRoleThreadId: thread-architect\nrole: Architect\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none\nskillProfileUsed: architect-default\narchitectureImpact: shared state\ncompatibilityNotes: ok\nalternatives: none\nmigrationRisks: low\n"
    qa = "TEAM_ROUTER_QA_REVIEW taskId=ctr-1\nresult: pass\nsourceThreadId: parent-thread\nsourceRoleThreadId: thread-qa\nrole: QA\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none\nskillProfileUsed: qa-default\ncoverageGaps: none\nverificationPlan: py -B -m unittest tests.test_team_router\nregressionRisks: low\n"
    wrong_architect_role = architect.replace("role: Architect", "role: QA")
    wrong_architect_skill = architect.replace("skillProfileUsed: architect-default", "skillProfileUsed: qa-default")
    wrong_qa_role = qa.replace("role: QA", "role: Architect")
    wrong_qa_skill = qa.replace("skillProfileUsed: qa-default", "skillProfileUsed: architect-default")
    for marker, text in (
        ("TEAM_ROUTER_ARCHITECT_REVIEW", wrong_architect_role),
        ("TEAM_ROUTER_ARCHITECT_REVIEW", wrong_architect_skill),
        ("TEAM_ROUTER_QA_REVIEW", wrong_qa_role),
        ("TEAM_ROUTER_QA_REVIEW", wrong_qa_skill),
    ):
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_message(text, marker, "ctr-1")
```

- [ ] **Step 2: Write failing direct-return and watcher tests**

```python
def test_direct_return_capture_allowed_for_architect_and_qa_states(self):
    self.assertTrue(team_router._direct_return_capture_allowed({"status": "awaiting_architect_review"}, "architect"))
    self.assertTrue(team_router._direct_return_capture_allowed({"status": "architect_review_unreachable"}, "architect"))
    self.assertTrue(team_router._direct_return_capture_allowed({"status": "awaiting_qa_review"}, "qa"))
    self.assertTrue(team_router._direct_return_capture_allowed({"status": "qa_review_unreachable"}, "qa"))
    self.assertFalse(team_router._direct_return_capture_allowed({"status": "awaiting_qa_review"}, "architect"))


def test_watch_next_wakeup_reads_architect_and_qa_request_paths(self):
    architect = {"status": "awaiting_architect_review", "architectureReview": {"request": {"threadId": "thread-architect", "expectedCallback": "TEAM_ROUTER_ARCHITECT_REVIEW", "searchAnchor": {"messageId": "msg-a"}}}}
    qa = {"status": "awaiting_qa_review", "qaReview": {"request": {"threadId": "thread-qa", "expectedCallback": "TEAM_ROUTER_QA_REVIEW", "searchAnchor": {"messageId": "msg-q"}}}}
    self.assertEqual(team_router._watch_next_wakeup(architect)["role"], "architect")
    self.assertEqual(team_router._watch_next_wakeup(qa)["role"], "qa")
    self.assertFalse(team_router._direct_return_capture_allowed({"status": "planned"}, "architect"))
    self.assertFalse(team_router._direct_return_capture_allowed({"status": "verifying"}, "qa"))
```

Add direct-return record tests:

```python
def test_direct_return_record_supports_architect_and_qa_requests(self):
    architect = {"architectureReview": {"request": {"threadId": "thread-architect", "returnThreadId": "manager-thread", "architectReviewDelivery": "direct-send"}}}
    qa = {"qaReview": {"request": {"threadId": "thread-qa", "returnThreadId": "manager-thread", "qaReviewDelivery": "direct-send"}}}
    self.assertEqual(team_router._direct_return_record(architect, "architect")["threadId"], "thread-architect")
    self.assertEqual(team_router._direct_return_record(qa, "qa")["threadId"], "thread-qa")
```

Add read-window miss tests mirroring the existing reviewer unreachable tests:

```python
def test_architect_capture_marks_unreachable_when_read_window_misses_anchor(self):
    # Use a ledger with architectureReview.request.searchAnchor and no returned anchor coverage.
    # Expected: capture helper sets status to architect_review_unreachable.


def test_qa_capture_marks_unreachable_when_read_window_misses_anchor(self):
    # Use a ledger with qaReview.request.searchAnchor and no returned anchor coverage.
    # Expected: capture helper sets status to qa_review_unreachable.
```

Add manager inbox direct-return tests:

```python
def test_manager_inbox_captures_architect_direct_return_only_in_architect_states(self):
    # Positive: awaiting_architect_review + TEAM_ROUTER_ARCHITECT_REVIEW advances according to result.
    # Negative: stale architect marker after status planned returns None and does not mutate ledger.


def test_manager_inbox_captures_qa_direct_return_only_in_qa_states(self):
    # Positive: awaiting_qa_review + TEAM_ROUTER_QA_REVIEW advances according to result.
    # Negative: stale QA marker after status verifying returns None and does not mutate ledger.
```

- [ ] **Step 3: Write failing transition tests**

Add tests for these exact outcomes:

```python
def test_architect_pass_returns_to_planned_without_dispatching_executor(self):
    # status awaiting_architect_review -> planned
    # architectureReview.result.fields.result == "pass"
    # no executor dispatch is created by capture itself


def test_architect_needs_rework_enters_architect_rework_pending_without_executor_rework_increment(self):
    # status awaiting_architect_review -> architect_rework_pending
    # reworkCount remains unchanged
    # architectureReview.result preserves architectureImpact/compatibilityNotes/alternatives/migrationRisks


def test_architect_blocked_enters_terminal_blocked(self):
    # status awaiting_architect_review -> blocked


def test_qa_pass_returns_to_verifying(self):
    # status awaiting_qa_review -> verifying
    # qaReview.result.fields.result == "pass"


def test_qa_needs_rework_uses_existing_executor_rework_path_and_increments_rework_count(self):
    # status awaiting_qa_review -> needs_rework or dispatched according to next_rework_dispatch(...)
    # reworkCount increments exactly once
    # qaReview.result preserves coverageGaps/verificationPlan/regressionRisks for executor rework input


def test_qa_blocked_enters_terminal_blocked(self):
    # status awaiting_qa_review -> blocked
```

Each test must use complete marker blocks with `sourceThreadId`, `sourceRoleThreadId`, `role`, `skillProfileUsed`, and role-specific fields.

- [ ] **Step 4: Run RED**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`

Expected: FAIL because capture, direct-return, and watcher branches are missing.

- [ ] **Step 5: Extend direct-return routing**

Extend `_direct_return_record()` with exact branches:

```python
if role == "architect":
    review = ledger.get("architectureReview") if isinstance(ledger.get("architectureReview"), Mapping) else None
    request = review.get("request") if isinstance(review, Mapping) else None
    # require request.returnThreadId and request.architectReviewDelivery == "direct-send"
if role == "qa":
    review = ledger.get("qaReview") if isinstance(ledger.get("qaReview"), Mapping) else None
    request = review.get("request") if isinstance(review, Mapping) else None
    # require request.returnThreadId and request.qaReviewDelivery == "direct-send"
```

Extend `_direct_return_capture_allowed()` with architect and QA branches:

```python
if role == "architect":
    return status in {"awaiting_architect_review", "architect_review_unreachable"} or needs_feedback_role == "architect"
if role == "qa":
    return status in {"awaiting_qa_review", "qa_review_unreachable"} or needs_feedback_role == "qa"
```

Add manager inbox capture functions near `_capture_executor_callback_from_manager_inbox()` / reviewer / verifier equivalents:

```python
_capture_architect_review_from_manager_inbox(...)
_capture_qa_review_from_manager_inbox(...)
```

They must call `_direct_return_protocol_message(...)` with `TEAM_ROUTER_ARCHITECT_REVIEW` / `TEAM_ROUTER_QA_REVIEW`, validate `sourceThreadId`, `sourceRoleThreadId`, and expected return thread, and return `None` for stale states instead of mutating the ledger.

Extend `watch_team_task_with_adapter()` with architect and QA manager-inbox direct-return branches, following the current executor branch around `status == "awaiting_callback"` and the reviewer/verifier branches. These branches must run before fallback self-thread reads for the same role.

Keep invalid role behavior raising `StateStoreError`.

- [ ] **Step 6: Extend `_watch_next_wakeup()`**

Add architect and QA branches before verifier handling:

```python
# architect branch reads ledger["architectureReview"]["request"] and returns role/threadId/expectedMarker/searchAnchor
# qa branch reads ledger["qaReview"]["request"] and returns role/threadId/expectedMarker/searchAnchor
```

Expected markers are `TEAM_ROUTER_ARCHITECT_REVIEW` and `TEAM_ROUTER_QA_REVIEW`.

Also wire the self-thread fallback capture paths so a read window that does not cover `architectureReview.request.searchAnchor` or `qaReview.request.searchAnchor` marks the ledger as `architect_review_unreachable` / `qa_review_unreachable`, matching the existing `review_unreachable` behavior.

- [ ] **Step 7: Implement capture transitions**

Implement capture helpers mirroring reviewer/verifier capture patterns. Store parsed fields under `architectureReview["result"]` or `qaReview["result"]`.

Architect mapping:

```python
pass -> planned
needs_rework -> architect_rework_pending
blocked -> blocked
```

QA mapping:

```python
pass -> verifying
needs_rework -> next_rework_dispatch(ledger["reworkCount"], ledger["maxRework"])
blocked -> blocked
```

QA `needs_rework` must preserve `coverageGaps`, `verificationPlan`, and `regressionRisks` as executor rework input.

Implement an explicit re-review entry from `architect_rework_pending`: compute `revisionInputHash` from the current `plan.fields.executorPrompt` plus any explicit revised design/spec path metadata, and store `revisionInputSource` alongside each `architectureReview.request`. A second `send_architect_review_request_with_adapter()` call is allowed only when the new `revisionInputHash` differs from the hash stored on the previous architect request/result. The re-request creates a fresh `architectureReview.request`, moves the prior `architectureReview.result` into `architectureReview.history`, and sets status back to `awaiting_architect_review`. Do not auto-loop without a revised input.

Add a test:

```python
def test_architect_rework_pending_can_request_fresh_architect_review_after_revised_prompt(self):
    # Start with architect needs_rework -> architect_rework_pending.
    # Update plan.fields.executorPrompt so revisionInputHash changes.
    # Assert send_architect_review_request_with_adapter(...) creates a new request, stores the new revisionInputHash/revisionInputSource, preserves prior result in architectureReview.history, and returns awaiting_architect_review.


def test_architect_rework_pending_rejects_rerequest_without_revised_input_hash(self):
    # Start with architect needs_rework -> architect_rework_pending.
    # Do not change plan.fields.executorPrompt or revised design/spec metadata.
    # Assert send_architect_review_request_with_adapter(...) raises StateStoreError and does not create a new request.
```

- [ ] **Step 8: Run GREEN**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`

Expected: PASS for parser, capture, direct-return, watcher, and transition tests.

- [ ] **Step 9: Commit gate**

If local commit is authorized: `git add src\team_router.py tests\test_team_router.py; git commit -m "feat: capture architect qa role returns"`.

---

### Task 5: Flow Gating And Verifier Integration

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Produces: architect gate blocks executor dispatch until architect pass.
- Produces: QA gate blocks verifier request and evidence-only fast path until QA pass.
- Produces: verifier prompt includes `coverageGaps`, `verificationPlan`, and `regressionRisks` after QA pass.

**Task 5 Scope Delta:**
- Task 5 is send-side gating and verifier prompt integration only. It consumes `architectureReview.result` and `qaReview.result` from Task 4 and must not rework parser/capture/watcher semantics, docs/fixtures, role creation policy, or Task 6 documentation.
- `send_executor_dispatch_with_adapter()` must reject before adapter send or ledger rewrite when `classify_architect_gate(ledger)` is true and `architectureReview.result.fields.result != "pass"`. The paired passing path must prove executor dispatch remains possible after architect pass. Non-architect flows must remain unchanged.
- `send_verifier_request_with_adapter()` must reject before adapter send or ledger rewrite when `classify_qa_gate(ledger)` is true and `qaReview.result.fields.result != "pass"`. Reviewer pass alone must not bypass a required QA gate. Non-QA flows must preserve existing verifier behavior.
- `verifier_evidence_only_fast_path(...)` or its call-site wrapper must accept QA context. If QA is required and not passed, it returns not allowed with a QA-specific reason and the verifier prompt must not offer evidence-only acceptance. If QA is not required, preserve current evidence/reviewer behavior. If QA is required and passed, existing evidence checks still apply.
- `make_verifier_request_message(...)` / `send_verifier_request_with_adapter(...)` must include QA `result`, `summary`, `coverageGaps`, `verificationPlan`, `regressionRisks`, `evidenceChecked`, and `risks` when QA passed and those fields are present. QA context is verifier input only and must not mark the task done.
- Tests must cover rejection before send/no ledger rewrite for architect-required executor dispatch and QA-required verifier request, passing paths after role pass, evidence-only gating before/after QA pass, verifier prompt QA context, and unchanged behavior for ordinary non-architect/non-QA flows.

- [ ] **Step 1: Write failing architect gate tests**

```python
def test_architect_required_flow_blocks_executor_until_architect_pass(self):
    ledger = self._planned_ledger()
    ledger["objective"] = "change shared protocol state-machine"
    ledger["architectureReview"] = {"required": True}
    team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)
    with self.assertRaises(team_router.StateStoreError) as ctx:
        team_router.send_executor_dispatch_with_adapter(self.root, self.project_id, ledger["taskId"], thread_adapter=FakeThreadAdapter(), permission="local-package", sent_at="2026-06-29T10:00:00+08:00", return_thread_id="manager-thread")
    self.assertIn("architect gate is required", str(ctx.exception))
```

Add a paired test where `ledger["architectureReview"]["result"]["fields"]["result"] == "pass"` and executor dispatch succeeds.

- [ ] **Step 2: Write failing QA verifier tests**

```python
def _ledger_after_executor_callback_with_qa_required(self):
    ledger = self._planned_ledger()
    ledger["objective"] = "high regression risk with test matrix needed"
    # Use existing send_executor_dispatch_with_adapter(...) and capture callback helpers
    # to reach the current verifier-ready state; do not invent a fixture that bypasses
    # dispatch/callback ledger shape.
    # Then set qaReview.required = True and return the saved ledger.


def test_qa_required_flow_blocks_verifier_until_qa_pass(self):
    ledger = self._ledger_after_executor_callback_with_qa_required()
    team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)
    with self.assertRaises(team_router.StateStoreError) as ctx:
        team_router.send_verifier_request_with_adapter(self.root, self.project_id, ledger["taskId"], thread_adapter=FakeThreadAdapter(), permission="local-package", sent_at="2026-06-29T10:00:00+08:00", return_thread_id="manager-thread")
    self.assertIn("QA gate is required", str(ctx.exception))
```

Add a paired test where QA pass causes the verifier prompt to include:

```text
coverageGaps: none after focused direct-return tests
verificationPlan: py -B -m unittest tests.test_team_router
regressionRisks: role dispatch and verifier gating
```

- [ ] **Step 3: Run RED**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`

Expected: FAIL because dispatch and verifier gates are not wired.

- [ ] **Step 4: Gate executor dispatch**

In `send_executor_dispatch_with_adapter()`, before sending to executor, if `classify_architect_gate(ledger)` is true, require `architectureReview.result.fields.result == "pass"`. If missing, `needs_rework`, or `blocked`, raise `StateStoreError("architect gate is required before executor dispatch: %s" % task_id)`.

- [ ] **Step 5: Gate verifier request**

In `send_verifier_request_with_adapter()`, if `classify_qa_gate(ledger)` is true, require `qaReview.result.fields.result == "pass"`. If missing, `needs_rework`, or `blocked`, raise `StateStoreError("QA gate is required before verifier request: %s" % task_id)`.

- [ ] **Step 6: Add QA result to verifier prompt**

Extend `make_verifier_request_message(..., qa_result: Mapping[str, Any] | None = None)` and append QA fields when present. Pass `qaReview.result` from `send_verifier_request_with_adapter()`.

- [ ] **Step 7: Gate evidence-only fast path**

Exact anchor: change `verifier_evidence_only_fast_path(callback_fields, reviewer_result)` in `src/team_router.py` and its call in `make_verifier_request_message()` / `send_verifier_request_with_adapter()`.

Add an explicit QA gate input, either:

```python
verifier_evidence_only_fast_path(callback_fields, reviewer_result, qa_required=False, qa_result=None)
```

or a small wrapper at the `make_verifier_request_message()` call site that passes `qa_required` and `qaReview.result`.

Required behavior:

- If QA is not required, preserve current reviewer/evidence behavior.
- If QA is required and `qaReview.result.fields.result != "pass"`, return `{"allowed": False, "reason": "QA result is missing or not pass"}`.
- If QA is required and QA passed, preserve existing reviewer/evidence checks.

Add assertions to direct `verifier_evidence_only_fast_path(...)` tests, `make_verifier_request_message(...)` tests, and `send_verifier_request_with_adapter(...)` tests so the user-facing evidence-only prompt is not offered before QA pass and is offered after QA pass plus clean reviewer pass.

- [ ] **Step 8: Run GREEN**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`

Expected: PASS for architect dispatch, QA verifier, verifier prompt, and evidence-only tests.

- [ ] **Step 9: Commit gate**

If local commit is authorized: `git add src\team_router.py tests\test_team_router.py; git commit -m "feat: gate executor verifier with architect qa roles"`.

---

### Task 6: Fixtures, Documentation, And Skill Entry Point

**Files:**
- Modify: `tests/test_team_router.py`
- Create: `tests/fixtures/team_router/architect_qa_visible_smoke_scenarios.json`
- Create: `skills/codex-team-router/references/conditional-roles.md`
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `skills/codex-team-router/references/direct-return.md`
- Modify: `skills/codex-team-router/references/reviewer-gate.md`
- Modify: `skills/codex-team-router/references/manager-polling-cadence.md`
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md`

**Interfaces:**
- Produces: role docs and smoke fixture coverage for architect/QA flows.
- Consumes: all runtime semantics from Tasks 1-5.

- [ ] **Step 1: Write failing docs and fixture tests**

```python
def test_conditional_roles_reference_documents_architect_and_qa_contract(self):
    reference = ROOT / "skills" / "codex-team-router" / "references" / "conditional-roles.md"
    self.assertTrue(reference.exists())
    text = reference.read_text(encoding="utf-8")
    for needle in ("architect", "qa", "TEAM_ROUTER_ARCHITECT_REVIEW", "TEAM_ROUTER_QA_REVIEW", "architect-default", "qa-default", "architectureReview.request", "qaReview.request", "CORE_ROLE_NAMES remains unchanged", "QA does not replace verifier", "no runtime skill loading"):
        self.assertIn(needle, text)


def test_skill_entrypoint_mentions_conditional_roles_without_exceeding_size_cap(self):
    text = (ROOT / "skills" / "codex-team-router" / "SKILL.md").read_text(encoding="utf-8")
    self.assertIn("architect", text)
    self.assertIn("qa", text)
    self.assertIn("references/conditional-roles.md", text)
    self.assertLess(len(text.encode("utf-8")), 8192)


def test_architect_qa_visible_smoke_fixture_covers_required_paths(self):
    raw = json.loads((ROOT / "tests" / "fixtures" / "team_router" / "architect_qa_visible_smoke_scenarios.json").read_text(encoding="utf-8"))
    self.assertEqual(set(raw["scenarios"]), {"architect_only", "qa_only", "architect_reviewer_no_qa", "architect_reviewer_qa", "qa_needs_rework", "architect_blocked", "qa_blocked"})
    self.assertEqual(raw["markers"]["architect"], "TEAM_ROUTER_ARCHITECT_REVIEW")
    self.assertEqual(raw["markers"]["qa"], "TEAM_ROUTER_QA_REVIEW")
```

- [ ] **Step 2: Run RED**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`

Expected: FAIL because docs and fixture are missing.

- [ ] **Step 3: Create fixture**

Create `tests/fixtures/team_router/architect_qa_visible_smoke_scenarios.json`:

```json
{
  "roles": {"manager": "规划者", "executor": "执行者", "reviewer": "审查者", "verifier": "验证者", "architect": "架构师", "qa": "QA"},
  "markers": {"manager": "TEAM_ROUTER_PLAN", "executor": "TEAM_ROUTER_CALLBACK", "reviewer": "TEAM_ROUTER_REVIEW", "verifier": "TEAM_ROUTER_VERDICT", "architect": "TEAM_ROUTER_ARCHITECT_REVIEW", "qa": "TEAM_ROUTER_QA_REVIEW"},
  "scenarios": {
    "architect_only": ["architect", "executor", "verifier"],
    "qa_only": ["executor", "qa", "verifier"],
    "architect_reviewer_no_qa": ["architect", "executor", "reviewer", "verifier"],
    "architect_reviewer_qa": ["architect", "executor", "reviewer", "qa", "verifier"],
    "qa_needs_rework": ["executor", "qa", "executor", "qa", "verifier"],
    "architect_blocked": ["architect", "blocked"],
    "qa_blocked": ["executor", "qa", "blocked"]
  },
  "notes": ["architect and qa are conditional visible roles, not CORE_ROLE_NAMES", "qa pass is verifier input, not final acceptance", "reviewer remains separate from architect and qa"]
}
```

- [ ] **Step 4: Create conditional roles reference**

Create `skills/codex-team-router/references/conditional-roles.md` with sections: `Architect`, `QA`, `Boundaries`, `Markers`, `Rework`, `Direct Return`, and `Testing`. It must state: `CORE_ROLE_NAMES remains unchanged`; no runtime skill loading; no custom role registry; QA does not replace verifier; architect/QA do not replace reviewer; `sourceThreadId`, `sourceRoleThreadId`, `role`, and `skillProfileUsed` are required parser fields for the two new markers.

- [ ] **Step 5: Update short skill entrypoint and references**

In `skills/codex-team-router/SKILL.md`, add one short line pointing to `references/conditional-roles.md`. In `direct-return.md`, add architect/QA direct-return marker mapping and pending request paths. In `reviewer-gate.md`, clarify reviewer remains separate from architect/QA. In `manager-polling-cadence.md`, add watcher request paths and markers. In `testing-and-quality-gates.md`, add required conditional role coverage.

- [ ] **Step 6: Run GREEN**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`

Expected: PASS and `SKILL.md` remains under 8192 bytes.

- [ ] **Step 7: Commit gate**

If local commit is authorized: `git add tests\test_team_router.py tests\fixtures\team_router\architect_qa_visible_smoke_scenarios.json skills\codex-team-router; git commit -m "docs: describe architect qa conditional roles"`.

---

### Task 7: Full Verification, Reviewer Gate, Verifier Gate, And Closeout Boundary

**Files:**
- Modify only if verification finds defects: files touched in Tasks 1-6.

**Interfaces:**
- Produces: local verification evidence and reviewer/verifier acceptance.
- Consumes: all task outputs.

- [ ] **Step 1: Run focused protocol tests**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v`

Expected: PASS.

- [ ] **Step 2: Run focused manager integration tests**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration -v`

Expected: PASS.

- [ ] **Step 3: Run focused docs tests**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`

Expected: PASS.

- [ ] **Step 4: Run compile check**

Run: `py -B -m py_compile src\team_router.py tests\test_team_router.py`

Expected: exit code 0.

- [ ] **Step 5: Run full Team Router suite**

Run: `py -B -m unittest tests.test_team_router`

Expected: exits 0 with `OK`.

- [ ] **Step 6: Run diff and size checks**

Run:

```powershell
git diff --check
(Get-Item skills\codex-team-router\SKILL.md).Length
```

Expected: `git diff --check` exits 0 and `SKILL.md` is under 8192 bytes.

- [ ] **Step 7: Run read-only closeout check**

Run: `py -B scripts\team_router_closeout_check.py --json`

Expected: read-only report lists only intended files and does not claim push, PR, deploy, release, or global sync.

- [ ] **Step 8: Request visible reviewer gate**

Create a visible reviewer role thread. It must review only the implementation diff and return:

```text
TEAM_ROUTER_REVIEW taskId=ctr-20260629-architect-qa-conditional-roles-implementation
result: pass | needs_rework | blocked
sourceThreadId: <manager-thread-id>
sourceRoleThreadId: <reviewer-thread-id>
role: Reviewer
summary:
findings:
requiredChanges:
evidenceChecked:
risks:
```

Expected: `result: pass` before verifier is requested. If `needs_rework`, fix with TDD and repeat reviewer gate.

- [ ] **Step 9: Request verifier gate**

After reviewer pass, request verifier acceptance with test evidence and reviewer output. Expected verifier block:

```text
TEAM_ROUTER_VERDICT taskId=ctr-20260629-architect-qa-conditional-roles-implementation
result: pass | needs_rework | blocked
summary:
requiredChanges:
evidenceChecked:
risks:
```

Do not claim final acceptance until verifier returns `result: pass`.

- [ ] **Step 10: Commit gate**

If and only if the user explicitly authorizes local commit after verifier pass:

```powershell
git status -s
git diff -- docs\superpowers\specs\2026-06-29-architect-qa-roles-design.md docs\superpowers\plans\2026-06-29-architect-qa-conditional-roles-implementation.md src\team_router.py tests\test_team_router.py skills\codex-team-router tests\fixtures\team_router
git add docs\superpowers\specs\2026-06-29-architect-qa-roles-design.md docs\superpowers\plans\2026-06-29-architect-qa-conditional-roles-implementation.md src\team_router.py tests\test_team_router.py tests\fixtures\team_router\architect_qa_visible_smoke_scenarios.json skills\codex-team-router
git commit -m "feat: add architect qa conditional roles"
```

If commit is not explicitly authorized, stop after verifier pass with changed files and verification evidence.

---

## Self-Review

Spec coverage:

- Fixed built-in conditional roles: Tasks 1 and 6.
- No custom registry or runtime skill loading: Global Constraints and Task 6.
- Classifier baseline terms and bare-role non-trigger rule: Task 2.
- Protocol markers, parser fields, role/skillProfile enums: Tasks 1 and 4.
- Ledger fields `architectureReview` and `qaReview`: Tasks 3 and 4.
- State semantics, unreachable recovery, terminal blocked, architect rework, QA rework: Tasks 1, 4, and 5.
- Direct-return mapping, `_direct_return_capture_allowed()`, `_watch_next_wakeup()`: Task 4.
- Direct-return record lookup, manager inbox capture, watch loop direct-return branches, and stale-state rejection: Task 4.
- Verifier integration and QA-gated evidence-only fast path: Task 5.
- Documentation, skill entrypoint, and fixtures: Task 6.
- Reviewer/verifier gates and closeout boundary: Task 7.

Placeholder scan:

- No unresolved placeholder markers or vague deferred-work wording remain in this plan.
- Each task has concrete files, interfaces, commands, expected outcomes, and implementation requirements.
- Commit commands are gated by explicit user authorization.

Type and name consistency:

- Role keys: `architect`, `qa`.
- Protocol role fields: `Architect`, `QA`.
- Markers: `TEAM_ROUTER_ARCHITECT_REVIEW`, `TEAM_ROUTER_QA_REVIEW`.
- Ledger request paths: `architectureReview.request`, `qaReview.request`.
- Skill profile enums: `architect-default`, `qa-default`.
- QA fields: `coverageGaps`, `verificationPlan`, `regressionRisks`.
- Architect fields: `architectureImpact`, `compatibilityNotes`, `alternatives`, `migrationRisks`.
