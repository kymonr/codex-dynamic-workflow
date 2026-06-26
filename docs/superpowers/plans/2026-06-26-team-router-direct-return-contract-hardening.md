# Team Router Direct Return Contract Hardening Implementation Record

> **Status:** Completed local implementation record. Do not execute this file as an active task plan; use it only as evidence of the completed RED/GREEN implementation sequence. Completed steps use checked checkbox syntax for auditability.

**Goal:** Make Team Router direct-return identity validation match the documented protocol and prevent manager-inbox direct-return blocks with the wrong parent `sourceThreadId` from advancing the ledger.

**Architecture:** Keep `src/team_router.py` as the current public module for this package. Harden only the direct-return capture seam first: the manager-inbox wrapper source remains the role sender thread, while the protocol block field `sourceThreadId` must equal the expected parent/orchestrator `returnThreadId`. Broader module extraction stays out of this package and should be planned after this protocol fix is green.

**Tech Stack:** Python 3.13 stdlib, `unittest`, existing Codex desktop thread adapter test doubles, Markdown contract docs.

## Global Constraints

- Do not add a project-root `AGENTS.md`.
- Keep `skills/codex-team-router/SKILL.md` under the Codex 8KB cap.
- Preserve direct-return fallback: malformed manager-inbox blocks must record `malformedDirectReturns` and then use self-thread-marker fallback when available.
- Preserve current manager polling cadence: one short `firstCheckAt`, then 300 second ordinary proactive read throttle unless user status/stop/immediate bypass applies.
- Do not stage, commit, push, PR, publish, or release inside this plan unless the user separately authorizes closeout.
- On Windows test runs, prefer `TMP/TEMP/PYTHONPYCACHEPREFIX=C:\tmp\...` to separate code failures from temp cleanup failures.

---

### Task 1: Add Failing Tests For Protocol `sourceThreadId`

**Files:**
- Modify: `tests/test_team_router.py:2891`
- Modify: `tests/test_team_router.py:5732`
- Modify: `tests/test_team_router.py:5943`

**Interfaces:**
- Consumes: existing `FakeThreadAdapter`, `watch_team_task_with_adapter()`, `record_executor_dispatch_sent()`, `record_reviewer_request_sent()`, `record_verifier_request_sent()`.
- Produces: tests proving manager-inbox direct-return requires protocol block `sourceThreadId` to match the pending return thread.

- [x] **Step 1: Update the reviewer direct-return test helper to include protocol `sourceThreadId`**

In `tests/test_team_router.py`, replace the private helper at `TestTeamRouterManagerIntegration._reviewer_direct_return_wrapper` with this exact shape. Keep existing call sites compatible by preserving the existing `source_thread_id` argument as the Codex delegation sender thread id.

```python
    def _reviewer_direct_return_wrapper(self,
                                        result,
                                        task_id=None,
                                        source_thread_id="thread-reviewer",
                                        source_role_thread_id=None,
                                        role="Reviewer",
                                        protocol_source_thread_id="parent-manager-thread"):
        review_task_id = task_id or self.task_id
        review_source_role_thread_id = source_role_thread_id or source_thread_id
        return (
            "<codex_delegation>\n"
            "  <source_thread_id>%s</source_thread_id>\n"
            "  <input>TEAM_ROUTER_REVIEW taskId=%s\n"
            "sourceThreadId: %s\n"
            "role: %s\n"
            "sourceRoleThreadId: %s\n"
            "result: %s\n"
            "summary: review result\n"
            "findings: focused check\n"
            "requiredChanges: none\n"
            "evidenceChecked: tests\n"
            "risks: none</input>\n"
            "</codex_delegation>"
        ) % (source_thread_id, review_task_id, protocol_source_thread_id, role, review_source_role_thread_id, result)
```

- [x] **Step 2: Add a failing reviewer test for wrong protocol `sourceThreadId`**

Add this method near the existing reviewer direct-return validation tests.

```python
    def test_watch_reviewer_direct_return_rejects_wrong_protocol_source_thread_id(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper(
                    "pass",
                    source_thread_id="thread-reviewer",
                    source_role_thread_id="thread-reviewer",
                    protocol_source_thread_id="wrong-parent-thread",
                ),
            },
        ]
        adapter.messages["thread-reviewer"] = [
            {"messageId": "msg-review", "sentAt": "2026-06-22T20:05:00+08:00", "text": "review request"},
            {
                "messageId": "msg-review-fallback",
                "sentAt": "2026-06-22T20:06:30+08:00",
                "text": (
                    "TEAM_ROUTER_REVIEW taskId=%s\n"
                    "result: pass\n"
                    "summary: fallback review\n"
                    "findings: fallback evidence\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: reviewer self-thread\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["summary"], "fallback review")
        self.assertEqual(
            update["ledger"]["review"]["result"]["receipt"]["source"],
            "self-thread-fallback/read_thread",
        )
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertIn("sourceThreadId", telemetry[0]["error"])
        self.assertEqual(telemetry[0]["returnThreadId"], "parent-manager-thread")
```

- [x] **Step 3: Add an executor direct-return test for wrong protocol `sourceThreadId`**

Add this method near `test_watch_team_task_ignores_manager_inbox_callback_with_wrong_source_thread_id`.

```python
    def test_watch_executor_direct_return_rejects_wrong_protocol_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "sourceThreadId: wrong-parent-thread\n"
                    "sourceRoleThreadId: thread-executor\n"
                    "role: Executor\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: manager inbox\n"
                    "evidence: direct return\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:30+08:00",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: fallback callback\n"
                    "evidence: executor self-thread\n"
                    "risks: none\n"
                    "next: verifier" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["parsedFields"]["summary"], "fallback callback")
        self.assertEqual(update["ledger"]["observations"][-1]["receipt"]["source"], "self-thread-fallback/read_thread")
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertIn("sourceThreadId", telemetry[0]["error"])
```

- [x] **Step 4: Add a verifier direct-return test for wrong protocol `sourceThreadId`**

Add this method near `test_watch_team_task_prefers_manager_inbox_direct_return_verdict`.

```python
    def test_watch_verifier_direct_return_rejects_wrong_protocol_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
        )
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: verifier" % self.task_id,
            },
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            callback_messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-verdict-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-verifier</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=%s\n"
                    "sourceThreadId: wrong-parent-thread\n"
                    "sourceRoleThreadId: thread-verifier\n"
                    "role: Verifier\n"
                    "result: pass\n"
                    "summary: manager inbox verdict\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: direct return\n"
                    "risks: none</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {
                "messageId": "msg-verdict",
                "sentAt": "2026-06-22T20:06:30+08:00",
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: fallback verdict\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: verifier self-thread\n"
                    "risks: none" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "done")
        self.assertEqual(update["ledger"]["verification"]["verdict"]["fields"]["summary"], "fallback verdict")
        self.assertEqual(update["ledger"]["verification"]["verdict"]["receipt"]["source"], "self-thread-fallback/read_thread")
        telemetry = update["ledger"]["malformedDirectReturns"]
        self.assertEqual(len(telemetry), 1)
        self.assertIn("sourceThreadId", telemetry[0]["error"])
```

- [x] **Step 5: Run focused tests and verify RED**

Run in PowerShell:

```powershell
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache'
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_reviewer_direct_return_rejects_wrong_protocol_source_thread_id -v
```

Expected: FAIL because the manager-inbox direct-return review is accepted instead of recorded as malformed and recovered from self-thread fallback.

Run the executor and verifier focused tests too:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_executor_direct_return_rejects_wrong_protocol_source_thread_id -v
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_verifier_direct_return_rejects_wrong_protocol_source_thread_id -v
```

Expected: FAIL for the same reason.

### Task 2: Enforce Protocol `sourceThreadId` In Direct-Return Validation

**Files:**
- Modify: `src/team_router.py:2851`
- Modify: `src/team_router.py:4047`
- Modify: `src/team_router.py:4099`
- Modify: `src/team_router.py:4151`

**Interfaces:**
- Consumes: `ProtocolMessage`, direct-return record mappings with `returnThreadId`.
- Produces: `_validate_direct_return_receipt(..., expected_return_thread_id=...) -> dict[str, Any] | None`.

- [x] **Step 1: Extend `_validate_direct_return_receipt()` signature and logic**

Change the function to this shape.

```python
def _validate_direct_return_receipt(msg: ProtocolMessage,
                                    manager_message: Mapping[str, Any] | None,
                                    *,
                                    task_id: str,
                                    expected_role: str,
                                    expected_role_thread_id: str,
                                    expected_return_thread_id: str | None = None) -> dict[str, Any] | None:
    message = manager_message if isinstance(manager_message, Mapping) else {}
    role_value = str(msg.fields.get("role") or "").strip()
    source_role_thread_id = str(msg.fields.get("sourceRoleThreadId") or "").strip()
    protocol_source_thread_id = str(msg.fields.get("sourceThreadId") or "").strip()
    expected_return = str(expected_return_thread_id or "").strip()
    errors: list[str] = []
    if msg.task_id != task_id:
        errors.append("%s.taskId must be %r, got %r" % (msg.marker, task_id, msg.task_id))
    if expected_return:
        if not protocol_source_thread_id:
            errors.append("%s.sourceThreadId is required" % msg.marker)
        elif protocol_source_thread_id != expected_return:
            errors.append(
                "%s.sourceThreadId must be %r, got %r"
                % (msg.marker, expected_return, protocol_source_thread_id)
            )
    if not role_value:
        errors.append("%s.role is required" % msg.marker)
    elif _normalize_direct_return_role(role_value, expected_role=expected_role) != expected_role:
        errors.append(
            "%s.role must be %r, got %r"
            % (msg.marker, expected_role, role_value)
        )
    if not source_role_thread_id:
        errors.append("%s.sourceRoleThreadId is required" % msg.marker)
    elif source_role_thread_id != expected_role_thread_id:
        errors.append(
            "%s.sourceRoleThreadId must be %r, got %r"
            % (msg.marker, expected_role_thread_id, source_role_thread_id)
        )
    if not errors:
        return None
    return {
        "messageId": message.get("messageId"),
        "sentAt": message.get("sentAt"),
        "sourceThreadId": message.get("sourceThreadId"),
        "error": "; ".join(errors),
    }
```

- [x] **Step 2: Pass expected return thread for executor manager-inbox capture**

In `_capture_executor_callback_from_manager_inbox()`, update the `_validate_direct_return_receipt()` call:

```python
        malformed = _validate_direct_return_receipt(
            msg,
            manager_message,
            task_id=task_id,
            expected_role="executor",
            expected_role_thread_id=_required_str(dispatch.get("roleThreadId") or dispatch.get("threadId"), "executorDispatch.roleThreadId"),
            expected_return_thread_id=_required_str(dispatch.get("returnThreadId"), "executorDispatch.returnThreadId"),
        )
```

- [x] **Step 3: Pass expected return thread for reviewer manager-inbox capture**

In `_capture_reviewer_review_from_manager_inbox()`, update the call:

```python
        malformed = _validate_direct_return_receipt(
            msg,
            manager_message,
            task_id=task_id,
            expected_role="reviewer",
            expected_role_thread_id=_required_str(request.get("roleThreadId") or request.get("threadId"), "reviewerRequest.roleThreadId"),
            expected_return_thread_id=_required_str(request.get("returnThreadId"), "reviewerRequest.returnThreadId"),
        )
```

- [x] **Step 4: Pass expected return thread for verifier manager-inbox capture**

In `_capture_verifier_verdict_from_manager_inbox()`, update the call:

```python
        malformed = _validate_direct_return_receipt(
            msg,
            manager_message,
            task_id=task_id,
            expected_role="verifier",
            expected_role_thread_id=_required_str(request.get("roleThreadId") or request.get("threadId"), "verifierRequest.roleThreadId"),
            expected_return_thread_id=_required_str(request.get("returnThreadId"), "verifierRequest.returnThreadId"),
        )
```

- [x] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache'
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_reviewer_direct_return_rejects_wrong_protocol_source_thread_id -v
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_executor_direct_return_rejects_wrong_protocol_source_thread_id -v
py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_verifier_direct_return_rejects_wrong_protocol_source_thread_id -v
```

Expected: PASS.

### Task 3: Align Direct-Return Documentation With Runtime Terminology

**Files:**
- Modify: `skills/codex-team-router/references/direct-return.md`
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md`
- Modify: `tests/test_team_router.py:6894`

**Interfaces:**
- Consumes: direct-return runtime behavior from Task 2.
- Produces: docs contract that distinguishes sender metadata from protocol `sourceThreadId`.

- [x] **Step 1: Update direct-return reference terminology**

In `skills/codex-team-router/references/direct-return.md`, add this paragraph after the opening paragraph:

```markdown
Terminology: Codex delegation wrapper metadata may expose the sender role thread as `<source_thread_id>` / normalized message `sourceThreadId`. That wrapper source identifies the role thread that sent the message. Inside the Team Router protocol block, `sourceThreadId` is the parent/orchestrator return thread id and must match the pending ledger `returnThreadId`; `sourceRoleThreadId` is the role thread id and must match the pending role ledger entry.
```

- [x] **Step 2: Strengthen manager inbox validation bullets**

In the same file, make sure the validation bullet list includes these exact bullets:

```markdown
- validate protocol-block `sourceThreadId` against the expected parent/orchestrator `returnThreadId`.
- validate `sourceRoleThreadId` against the expected `roleThreadId` / role thread record.
```

- [x] **Step 3: Update testing reference**

In `skills/codex-team-router/references/testing-and-quality-gates.md`, extend the docs contract sentence so it includes:

```markdown
protocol-block `sourceThreadId` must match `returnThreadId`
```

- [x] **Step 4: Add docs contract assertions**

In `tests/test_team_router.py`, update `test_direct_return_reference_matches_active_role_return_contract` to assert the new terminology:

```python
        self.assertIn("protocol block", text)
        self.assertIn("must match the pending ledger `returnThreadId`", text)
        self.assertIn("wrapper source identifies the role thread", text)
```

- [x] **Step 5: Run docs contract focused test**

Run:

```powershell
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache'
py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_direct_return_reference_matches_active_role_return_contract -v
```

Expected: PASS.

### Task 4: Add Workbench Freshness Guard

**Files:**
- Modify: `tests/test_team_router.py:6739`
- Modify: `docs/workbench.md`

**Interfaces:**
- Consumes: current repository state expectation.
- Produces: a docs-contract guard that catches stale workbench claims such as `uncommitted local diff only` when the tracked project state is meant to be current.

- [x] **Step 1: Update workbench current state**

Edit `docs/workbench.md` so the current task state no longer claims live uncommitted diff when `git status -s` is empty. Use this replacement for the Current Task bullet block:

```markdown
## Current Task

- Objective: direct-return contract hardening and Team Router architecture cleanup planning.
- State: planning package pending execution; no implementation diff at the time this record was refreshed.
- Last refreshed: 2026-06-26 Superpowers plan handoff.
- Not done: implementation, validation, stage, commit, push, PR, publish, release.
```

- [x] **Step 2: Add docs contract test for stale diff wording**

Add this test to `TestTeamRouterSkillDoc`.

```python
    def test_workbench_does_not_claim_uncommitted_diff_when_used_as_current_record(self):
        text = (ROOT / "docs" / "workbench.md").read_text(encoding="utf-8")

        self.assertIn("## Current Task", text)
        self.assertNotIn("State: uncommitted local diff only", text)
```

- [x] **Step 3: Run focused docs test**

Run:

```powershell
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache'
py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_does_not_claim_uncommitted_diff_when_used_as_current_record -v
```

Expected: PASS.

### Task 5: Full Verification And Closeout Evidence

**Files:**
- Verify only: `src/team_router.py`
- Verify only: `tests/test_team_router.py`
- Verify only: `skills/codex-team-router/references/direct-return.md`
- Verify only: `skills/codex-team-router/references/testing-and-quality-gates.md`
- Verify only: `docs/workbench.md`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: verified local package ready for user review.

- [x] **Step 1: Compile Python files**

Run:

```powershell
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache'
py -m py_compile src\team_router.py tests\test_team_router.py
```

Expected: exit code 0.

- [x] **Step 2: Run Team Router test suite**

Run:

```powershell
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache'
py -m unittest discover -s tests -p test_team_router.py -v
```

Expected: PASS. If Windows temp cleanup fails after assertions pass, rerun with a fresh `PYTHONPYCACHEPREFIX` under `C:\tmp` before treating it as code failure.

- [x] **Step 3: Check whitespace and diff**

Run:

```powershell
git diff --check
git status -s --untracked-files=all
```

Expected: `git diff --check` passes or only reports known CRLF/LF context already accepted by the project; `git status -s --untracked-files=all` shows only files intentionally touched by this package.

- [x] **Step 4: Prepare closeout summary**

Closeout must state:

```text
implemented changes: direct-return protocol sourceThreadId validation, docs contract update, workbench freshness update
verification actually run: <commands and pass/fail>
not done: stage/commit/push/PR/publish/release
remaining risks: broader module extraction and test split still pending as separate architecture package
compoundingDecision: skipped
reason: ordinary successful implementation/testing with no new reusable risk, unless execution reveals a new reusable process lesson
```

## Deferred Separate Plans

- `team_router.py` module extraction into protocol/policy/state/thread/direct-return/orchestration modules.
- `tests/test_team_router.py` split into focused test files.
- Skill reference canonicalization to remove repeated full contract paragraphs.
- Artifact audit command hygiene for `.tmp`, `pet-runs`, `__pycache__`, and `.pytest_cache`.

These are intentionally separate because this package fixes a runtime contract bug first.
