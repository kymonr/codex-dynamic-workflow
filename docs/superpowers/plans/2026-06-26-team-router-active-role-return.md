# Team Router Active Role Return Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Executor, Reviewer, and Verifier role threads actively send completed protocol blocks back to the Manager thread while preserving `self-thread-marker` fallback.

**Architecture:** Keep Team Router's existing direct-return scaffolding, but promote it into the explicit default contract. Role dispatch prompts carry manager and role-thread identity, role completions direct-send the protocol block first, then print the same protocol body locally. Manager receipt validates `taskId`, `role`, and role-thread identity before accepting a returned protocol block.

**Tech Stack:** Python `unittest`, Team Router policy snapshot in `src/team_router.py`, markdown docs under `README.md`, `docs/runbooks/`, and `skills/codex-team-router/references/`.

---

## File Structure

- Modify: `src/team_router.py`
  - Update `MANAGER_ORCHESTRATION_POLICY["callbackDeliveryModel"]`.
  - Update Executor/Reviewer/Verifier prompt builders to name `sourceThreadId`, `sourceRoleThreadId`, `role`, `callbackDelivery/reviewDelivery/verdictDelivery`, and fallback metadata.
  - Tighten manager-inbox receipt validation so direct-send blocks are accepted only for the pending role/thread.
- Modify: `tests/test_team_router.py`
  - Add focused snapshot tests for `callbackDeliveryModel`.
  - Add prompt builder assertions for Executor/Reviewer/Verifier active return fields.
  - Add manager-inbox acceptance/rejection tests for matching and mismatched role-thread identity.
  - Add fallback metadata tests for local fallback wording.
- Modify: `README.md`
  - Update manager-facing callback delivery wording.
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`
  - Add operational direct-send flow and fallback recovery.
- Modify: `skills/codex-team-router/references/manager-mode.md`
  - Update manager duties and validation boundary.
- Modify: `skills/codex-team-router/references/manual-orchestration.md`
  - Update manual role dispatch guidance.
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md`
  - Add smoke verification requirement.
- Do not modify: `skills/codex-team-router/SKILL.md`
  - It is near the 8192 byte cap.

---

### Task 1: Lock The Policy Snapshot Contract

**Files:**
- Modify: `src/team_router.py`
- Test: `tests/test_team_router.py`

- [ ] **Step 1: Write the failing policy snapshot test**

Add or extend the existing `TestTeamRouterProtocol` policy snapshot test so it asserts the active-return fields.

```python
    def test_protocol_contract_snapshot_includes_active_role_return_model(self):
        policy = team_router.protocol_contract_snapshot()["managerOrchestrationPolicy"]
        model = policy["callbackDeliveryModel"]

        self.assertIn("direct-send", model["primaryDelivery"])
        self.assertIn("self-thread-marker", model["fallback"])
        self.assertIn("sourceThreadId", model["requiredDispatchFields"])
        self.assertIn("sourceRoleThreadId", model["requiredDispatchFields"])
        self.assertIn("role", model["requiredDispatchFields"])
        self.assertIn("taskId", model["managerReceiptValidation"])
        self.assertIn("role", model["managerReceiptValidation"])
        self.assertIn("sourceRoleThreadId", model["managerReceiptValidation"])
        self.assertIn("same protocol block body", model["fallbackBodyInvariant"])
        self.assertIn("deliveryStatus: fallback_only", model["fallbackMetadata"])
        self.assertIn("deliveryError", model["fallbackMetadata"])
        self.assertIn("two-step bootstrap", model["roleThreadBootstrap"])
        self.assertIn("create", model["roleThreadBootstrap"])
        self.assertIn("dispatch", model["roleThreadBootstrap"])
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterProtocol
```

Expected: FAIL because `callbackDeliveryModel` still describes `self-thread-marker` as the normal collection path or lacks the new keys.

- [ ] **Step 3: Update `MANAGER_ORCHESTRATION_POLICY`**

Replace or extend `MANAGER_ORCHESTRATION_POLICY["callbackDeliveryModel"]` with this shape while preserving existing accepted policy keys elsewhere:

```python
    "callbackDeliveryModel": {
        "primaryDelivery": "direct-send via send_message_to_thread(sourceThreadId, protocolBlock)",
        "fallback": "self-thread-marker in the role thread remains mandatory audit and recovery path",
        "requiredDispatchFields": (
            "sourceThreadId",
            "sourceRoleThreadId",
            "role",
            "callbackDelivery/reviewDelivery/verdictDelivery: direct-send",
            "callbackFallback/reviewFallback/verdictFallback: self-thread-marker",
        ),
        "roleThreadBootstrap": "newly created role threads require two-step bootstrap: create role thread first, record sourceRoleThreadId, then send formal dispatch containing that id; reused roles already have a known sourceRoleThreadId",
        "managerReceiptValidation": "manager accepts direct-send protocol blocks only when taskId, role, and sourceRoleThreadId match the pending role ledger entry; unmatched blocks are rejected or quarantined and must not expand task scope",
        "fallbackBodyInvariant": "direct-send and local fallback must contain the same protocol block body",
        "fallbackMetadata": "local fallback may append deliveryStatus: fallback_only and deliveryError when direct-send is unavailable or failed",
        "normalCadence": "manager waits for direct-send first; perform one bounded read/check only on failed/unknown send, expected idle role, user completion signal, or timeout; avoid continuous polling",
    },
```

- [ ] **Step 4: Run the focused test and confirm pass**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterProtocol
```

Expected: PASS for the policy snapshot test.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src\team_router.py tests\test_team_router.py
git commit -m "feat: define active role return policy"
```

---

### Task 2: Update Role Prompt Builders For Active Return

**Files:**
- Modify: `src/team_router.py`
- Test: `tests/test_team_router.py`

- [ ] **Step 1: Write failing prompt tests**

Add prompt assertions for each role. Use existing tests around `build_executor_dispatch_message`, reviewer request builders, and verifier request builders.

```python
    def test_executor_direct_return_prompt_includes_active_return_fields(self):
        message = team_router.build_executor_dispatch_message(
            task_id="ctr-1",
            permission="local-package",
            scope="docs",
            stop_when="done",
            risk_boundary="workspace only",
            executor_prompt="update docs",
            message_id="msg-1",
            sent_at="2026-06-26T10:00:00+08:00",
            return_thread_id="manager-thread",
            role_thread_id="executor-thread",
        )

        self.assertIn("sourceThreadId: manager-thread", message)
        self.assertIn("sourceRoleThreadId: executor-thread", message)
        self.assertIn("role: Executor", message)
        self.assertIn("callbackDelivery: direct-send", message)
        self.assertIn("callbackFallback: self-thread-marker", message)
        self.assertIn("send_message_to_thread(sourceThreadId, protocolBlock)", message)
        self.assertIn("same protocol block body", message)
        self.assertIn("deliveryStatus: fallback_only", message)
        self.assertIn("deliveryError", message)
```

Add analogous assertions for Reviewer and Verifier:

```python
self.assertIn("sourceRoleThreadId: reviewer-thread", review_message)
self.assertIn("role: Reviewer", review_message)
self.assertIn("reviewDelivery: direct-send", review_message)
self.assertIn("reviewFallback: self-thread-marker", review_message)

self.assertIn("sourceRoleThreadId: verifier-thread", verify_message)
self.assertIn("role: Verifier", verify_message)
self.assertIn("verdictDelivery: direct-send", verify_message)
self.assertIn("verdictFallback: self-thread-marker", verify_message)
```

- [ ] **Step 2: Run the focused prompt tests and confirm failure**

Run the smallest existing test class containing the role prompt tests:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration
```

Expected: FAIL on missing `sourceThreadId`, `sourceRoleThreadId`, `role`, or fallback metadata strings.

- [ ] **Step 3: Update Executor prompt builder**

In the executor dispatch prompt builder, when `return_thread_id` and `role_thread_id` are present, include this block. Keep existing `returnThreadId` and `roleThreadId` aliases for backward compatibility if tests depend on them.

```python
        direct_lines = [
            "sourceThreadId: %s" % return_thread_id,
            "sourceRoleThreadId: %s" % _required_str(role_thread_id, "roleThreadId"),
            "role: Executor",
            "returnThreadId: %s" % return_thread_id,
            "orchestratorThreadId: %s" % return_thread_id,
            "roleThreadId: %s" % _required_str(role_thread_id, "roleThreadId"),
            "callbackDelivery: direct-send",
            "callbackFallback: self-thread-marker",
            "Direct return contract: first call send_message_to_thread(sourceThreadId, protocolBlock) with the final TEAM_ROUTER_CALLBACK block.",
            "Direct return contract: then output the same protocol block body in this role thread final answer for self-thread-marker fallback.",
            "Direct return validation fields: taskId, role, sourceThreadId, sourceRoleThreadId.",
            "Direct return fallback metadata: deliveryStatus: fallback_only; deliveryError: <short error only when direct-send failed>.",
        ]
```

- [ ] **Step 4: Update Reviewer and Verifier prompt builders**

Use the same pattern with role-specific markers:

```python
"sourceThreadId: %s" % return_thread_id
"sourceRoleThreadId: %s" % _required_str(role_thread_id, "roleThreadId")
"role: Reviewer"
"reviewDelivery: direct-send"
"reviewFallback: self-thread-marker"
"Direct return contract: first call send_message_to_thread(sourceThreadId, protocolBlock) with the final TEAM_ROUTER_REVIEW block."
```

```python
"sourceThreadId: %s" % return_thread_id
"sourceRoleThreadId: %s" % _required_str(role_thread_id, "roleThreadId")
"role: Verifier"
"verdictDelivery: direct-send"
"verdictFallback: self-thread-marker"
"Direct return contract: first call send_message_to_thread(sourceThreadId, protocolBlock) with the final TEAM_ROUTER_VERDICT block."
```

- [ ] **Step 5: Run focused prompt tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src\team_router.py tests\test_team_router.py
git commit -m "feat: prompt roles to direct-send results"
```

---

### Task 3: Enforce Manager Receipt Validation

**Files:**
- Modify: `src/team_router.py`
- Test: `tests/test_team_router.py`

- [ ] **Step 1: Write failing manager-inbox validation tests**

Add tests near existing manager-inbox/direct-send tests.

```python
    def test_manager_inbox_accepts_matching_reviewer_direct_send(self):
        # Arrange a ledger waiting on reviewer-thread for task ctr-1.
        # Feed a TEAM_ROUTER_REVIEW block from sourceRoleThreadId reviewer-thread.
        # Assert the ledger advances and receipt source is manager-inbox/direct-send.
        update = self._watch_with_manager_inbox_message(
            role="Reviewer",
            source_role_thread_id="thread-reviewer",
            text=(
                "TEAM_ROUTER_REVIEW taskId=ctr-1\n"
                "role: Reviewer\n"
                "sourceRoleThreadId: thread-reviewer\n"
                "result: pass\n"
                "summary: ok\n"
                "findings: none\n"
                "requiredChanges: none\n"
                "evidenceChecked: tests\n"
                "risks: none\n"
            ),
        )
        self.assertEqual(update["ledger"]["review"]["result"]["receipt"]["source"], "manager-inbox/direct-send")
```

Add rejection tests:

```python
    def test_manager_inbox_rejects_reviewer_direct_send_from_wrong_role_thread(self):
        update = self._watch_with_manager_inbox_message(
            role="Reviewer",
            source_role_thread_id="wrong-reviewer-thread",
            text=(
                "TEAM_ROUTER_REVIEW taskId=ctr-1\n"
                "role: Reviewer\n"
                "sourceRoleThreadId: wrong-reviewer-thread\n"
                "result: pass\n"
                "summary: stale\n"
                "findings: none\n"
                "requiredChanges: none\n"
                "evidenceChecked: tests\n"
                "risks: none\n"
            ),
        )
        self.assertNotEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["directReturnTelemetry"][-1]["recovery"], "self-thread-marker fallback")
```

If the helper names differ in current tests, use the existing manager-inbox fixture helpers instead of creating broad new scaffolding.

- [ ] **Step 2: Run the manager-inbox tests and confirm failure**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration
```

Expected: FAIL until direct-send parsing and validation checks the new metadata.

- [ ] **Step 3: Normalize direct-send metadata from protocol blocks**

In the manager-inbox capture path, extract these fields from the parsed protocol block when present:

```python
source_role_thread_id = msg.fields.get("sourceRoleThreadId") or manager_message.get("sourceThreadId")
role = msg.fields.get("role") or expected_role
```

Preserve existing adapter-level source metadata as fallback for older messages.

- [ ] **Step 4: Validate against the pending ledger entry**

Before accepting the direct-send result, check:

```python
if msg_task_id != task_id:
    return _record_malformed_direct_return(...)
if normalized_role != expected_role:
    return _record_malformed_direct_return(...)
if source_role_thread_id != expected_role_thread_id:
    return _record_malformed_direct_return(...)
```

Use existing malformed direct-return telemetry when available. Do not silently accept mismatched blocks.

- [ ] **Step 5: Run focused manager-inbox tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src\team_router.py tests\test_team_router.py
git commit -m "fix: validate active role return source"
```

---

### Task 4: Update Docs And Contract Tests

**Files:**
- Modify: `README.md`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`
- Modify: `skills/codex-team-router/references/manager-mode.md`
- Modify: `skills/codex-team-router/references/manual-orchestration.md`
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md`
- Test: `tests/test_team_router.py`

- [ ] **Step 1: Write failing docs contract tests**

Extend the docs contract test to require exact active-return terms.

```python
    def test_team_router_docs_describe_active_role_return(self):
        docs = "\n".join(
            Path(path).read_text(encoding="utf-8")
            for path in (
                "README.md",
                "docs/runbooks/codex-team-router-live-orchestration.md",
                "skills/codex-team-router/references/manager-mode.md",
                "skills/codex-team-router/references/manual-orchestration.md",
                "skills/codex-team-router/references/testing-and-quality-gates.md",
            )
        )
        for needle in (
            "direct-send + self-thread-marker fallback",
            "send_message_to_thread(sourceThreadId, protocolBlock)",
            "sourceRoleThreadId",
            "role",
            "taskId",
            "two-step bootstrap",
            "deliveryStatus: fallback_only",
            "deliveryError",
            "same protocol block body",
            "bounded result-collection read/check",
            "continuous polling is not the default",
        ):
            self.assertIn(needle, docs)
```

- [ ] **Step 2: Run docs tests and confirm failure**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterSkillDoc
```

Expected: FAIL on missing active-return docs terms.

- [ ] **Step 3: Update README**

Add a short manager-facing rule:

```markdown
- Role return uses `direct-send + self-thread-marker fallback`: Executor, Reviewer, and Verifier first call `send_message_to_thread(sourceThreadId, protocolBlock)` with the final protocol block, then print the same protocol block body in their role thread. New role threads use a two-step bootstrap: create the role thread, record `sourceRoleThreadId`, then dispatch with `sourceThreadId`, `sourceRoleThreadId`, and `role`.
```

- [ ] **Step 4: Update runbook and references**

Use the same compact wording in each reference. Include the validation boundary:

```markdown
Manager accepts direct-send only when `taskId`, `role`, and `sourceRoleThreadId` match the pending role ledger entry. Unmatched blocks are rejected or quarantined and cannot expand scope. If direct-send fails, local fallback may append `deliveryStatus: fallback_only` and `deliveryError`, but the protocol body must stay the same.
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterSkillDoc
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add README.md docs\runbooks\codex-team-router-live-orchestration.md skills\codex-team-router\references\manager-mode.md skills\codex-team-router\references\manual-orchestration.md skills\codex-team-router\references\testing-and-quality-gates.md tests\test_team_router.py
git commit -m "docs: document active role return fallback"
```

---

### Task 5: Verify With Tests And Reviewer Smoke

**Files:**
- Modify only if Task 5 finds defects: `src/team_router.py`, `tests/test_team_router.py`, or docs from Task 4.

- [ ] **Step 1: Run focused suite**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterProtocol tests.test_team_router.TestTeamRouterSkillDoc
```

Expected: `Ran 29 tests ... OK` or updated count with OK.

- [ ] **Step 2: Run full Team Router suite**

Run:

```powershell
py -m unittest tests.test_team_router
```

Expected: full suite OK.

- [ ] **Step 3: Run compile and diff checks**

Run:

```powershell
py -m py_compile src\team_router.py tests\test_team_router.py
git diff --check
Get-Item skills\codex-team-router\SKILL.md | Select-Object Length
```

Expected:

- `py_compile` exits 0.
- `git diff --check` exits 0, CRLF normalization warnings are acceptable if no whitespace errors are reported.
- `SKILL.md` stays under 8192 bytes.

- [ ] **Step 4: Run one Reviewer smoke trial**

Create or reuse a Reviewer role thread with a prompt that contains:

```text
sourceThreadId: <current manager thread id>
sourceRoleThreadId: <reviewer thread id>
role: Reviewer
reviewDelivery: direct-send
reviewFallback: self-thread-marker
```

The prompt must instruct the Reviewer:

```text
First send this exact TEAM_ROUTER_REVIEW block back to sourceThreadId with send_message_to_thread(sourceThreadId, protocolBlock). Then output the same protocol block body in this role thread final answer.
```

Expected Manager-thread receipt:

```text
TEAM_ROUTER_REVIEW taskId=team-router-active-role-return-smoke-20260626
role: Reviewer
sourceRoleThreadId: <reviewer thread id>
result: pass
summary: active role return smoke reached manager
findings: none
requiredChanges: none
evidenceChecked: send_message_to_thread direct-send smoke
risks: none
```

- [ ] **Step 5: Verify fallback if smoke does not reach Manager**

If the Manager thread does not receive the direct-send block, perform one bounded `read_thread` check of the Reviewer thread and confirm the same protocol body appears there with fallback metadata:

```text
deliveryStatus: fallback_only
deliveryError: <short send failure reason>
```

Expected: fallback recovers the result without continuous polling.

- [ ] **Step 6: Commit any smoke-driven fixes**

If Task 5 required code or docs fixes, commit only those fixes:

```powershell
git add <changed files>
git commit -m "fix: harden active role return smoke path"
```

If no fixes were required, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Active direct-send primary path: Task 1, Task 2, Task 5.
- `self-thread-marker` fallback: Task 1, Task 2, Task 4, Task 5.
- `sourceThreadId`, `sourceRoleThreadId`, and `role`: Task 1, Task 2, Task 3, Task 4.
- Manager validation and ordinary-user-input boundary: Task 3 and Task 4.
- Fallback metadata: Task 1, Task 2, Task 4, Task 5.
- Bounded result collection and no continuous polling: Task 1, Task 4, Task 5.
- Reviewer smoke: Task 5.
- Avoid `SKILL.md`: File Structure and Task 5 verification.

Placeholder scan:

- No placeholder terms remain.
- Each code-changing task includes explicit code snippets or exact string requirements.
- Each verification step includes exact commands and expected results.

Type consistency:

- `sourceThreadId` is the Manager/return thread id used in prompt text.
- `sourceRoleThreadId` is the role thread id used for Manager receipt validation.
- Existing `returnThreadId` and `roleThreadId` remain compatibility aliases where current code already uses them.
- Fallback metadata names are consistently `deliveryStatus` and `deliveryError`.