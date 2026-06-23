# Team Router Manager Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing JSON registry/ledger helpers to a deterministic codex-team-router manager state flow that records task creation, role threads, plan requests, executor dispatches, callbacks, verifier requests, verdicts, closeout state, and read_thread recovery anchors.

**Architecture:** Keep the integration layer local and deterministic in `src/team_router.py`; it must not call Codex app thread tools directly. The functions consume plain send/read results from a future adapter layer, persist registry/ledger JSON through the existing helpers, and produce protocol messages that the adapter can send to manager/executor/verifier threads.

**Tech Stack:** Python standard library, `unittest`, existing `team_router.py` JSON/protocol helpers.

---

### Task 1: Registry Role And Task Creation Flow

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`

- [x] **Step 1: Write failing tests**

Add tests under `TestTeamRouterManagerIntegration`:

```python
def test_create_team_task_writes_registry_roles_and_task_file(self):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "state"
        project_id = "project-123"
        task_id = "ctr-20260622-160000-a7f3"
        roles = {
            "manager": {"threadId": "thread-manager", "title": "TeamRouter manager - repo"},
            "executor": {"threadId": "thread-executor", "title": "TeamRouter executor - repo"},
            "verifier": {"threadId": "thread-verifier", "title": "TeamRouter verifier - repo"},
        }

        ledger = team_router.create_team_task(
            root,
            project_id,
            task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            roles=roles,
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        saved_ledger = team_router.load_task_ledger(root, project_id, task_id)
        self.assertEqual(saved_ledger["objective"], "inspect docs")
        registry = team_router.load_registry(root, project_id)
        project = registry["projects"][project_id]
        self.assertEqual(project["roles"]["manager"]["threadId"], "thread-manager")
        self.assertEqual(project["roles"]["executor"]["threadId"], "thread-executor")
        self.assertEqual(project["roles"]["verifier"]["threadId"], "thread-verifier")
```

- [x] **Step 2: Run test to verify failure**

Run: `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_create_team_task_writes_registry_roles_and_task_file`

Expected: FAIL with `AttributeError: module 'team_router' has no attribute 'create_team_task'`.

- [x] **Step 3: Implement minimal registry/task creation helpers**

Add:

```python
ROLE_NAMES = frozenset({"manager", "executor", "verifier"})


def _validate_role(role: str) -> None: ...

def _normalize_role_record(role: str, data: Mapping[str, Any], observed_at: str) -> dict[str, Any]: ...

def update_registry_roles(state_root, project_id, roles, observed_at): ...

def create_team_task(state_root, project_id, task_id, *, objective, project_local_path, roles, observed_at, max_rework=3): ...
```

`create_team_task()` must load/update/save registry, create a task ledger through `new_task_ledger()`, set status `roles_ready`, save the task file, and return the saved ledger.

- [x] **Step 4: Run test to verify pass**

Run the same single test. Expected: PASS.

### Task 2: Plan Request And Executor Dispatch Persistence

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`

- [x] **Step 1: Write failing tests**

Add tests:

```python
def test_plan_request_records_anchor_from_send_result(self):
    ledger = self._ready_ledger()
    message = team_router.make_plan_request_message(ledger["taskId"], ledger["objective"], "read-only")
    self.assertIn("TEAM_ROUTER_PLAN_REQUEST taskId=ctr-20260622-160000-a7f3", message)
    updated = team_router.record_plan_request_sent(
        self.root,
        self.project_id,
        ledger["taskId"],
        manager_thread_id="thread-manager",
        sent_at="2026-06-22T20:01:00+08:00",
        message_id="msg-plan",
    )
    self.assertEqual(updated["status"], "awaiting_plan")
    self.assertEqual(updated["planRequest"]["searchAnchor"]["messageId"], "msg-plan")


def test_executor_dispatch_records_attempt_and_anchor(self):
    ledger = self._planned_ledger()
    message = team_router.make_executor_dispatch_message(
        ledger["taskId"],
        {"scope": "src", "stopWhen": "done", "executorPrompt": "inspect src"},
        "read-only",
        {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"},
    )
    self.assertIn("callbackMode: self-thread-marker", message)
    updated = team_router.record_executor_dispatch_sent(
        self.root,
        self.project_id,
        ledger["taskId"],
        executor_thread_id="thread-executor",
        sent_at="2026-06-22T20:02:00+08:00",
        message_id="msg-dispatch",
    )
    self.assertEqual(updated["status"], "awaiting_callback")
    self.assertEqual(updated["dispatches"][-1]["attempt"], 1)
```

- [x] **Step 2: Run tests to verify failure**

Run: `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration`

Expected: FAIL for missing message/record functions.

- [x] **Step 3: Implement plan/dispatch helpers**

Add default ledger field `planRequest` in `_normalize_task_ledger()`. Add message builders and persistence helpers:

```python
def make_plan_request_message(task_id, objective, permission): ...
def record_plan_request_sent(state_root, project_id, task_id, *, manager_thread_id, sent_at, message_id=None): ...
def make_executor_dispatch_message(task_id, plan_fields, permission, search_anchor): ...
def record_executor_dispatch_sent(state_root, project_id, task_id, *, executor_thread_id, sent_at, message_id=None): ...
```

- [x] **Step 4: Run tests to verify pass**

Run: `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration`.

### Task 3: read_thread Recovery And Callback Capture

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`

- [x] **Step 1: Write failing tests**

Add tests:

```python
def test_callback_capture_uses_dispatch_anchor_from_ledger(self):
    ledger = self._awaiting_callback_ledger()
    messages = [
        {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
        {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
    ]
    updated = team_router.capture_executor_callback_from_read(
        self.root,
        self.project_id,
        ledger["taskId"],
        messages,
        captured_at="2026-06-22T20:04:00+08:00",
    )
    self.assertEqual(updated["status"], "verifying")
    self.assertEqual(updated["observations"][-1]["type"], "callback_raw")


def test_callback_capture_marks_unreachable_when_read_window_misses_anchor(self):
    ledger = self._awaiting_callback_ledger()
    messages = [{"text": "summary without ids or timestamps"}]
    updated = team_router.capture_executor_callback_from_read(
        self.root,
        self.project_id,
        ledger["taskId"],
        messages,
        captured_at="2026-06-22T20:04:00+08:00",
    )
    self.assertEqual(updated["status"], "callback_unreachable")
```

- [x] **Step 2: Run tests to verify failure**

Run: `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration`.

Expected: FAIL for missing callback capture helper.

- [x] **Step 3: Implement read recovery helpers**

Add helpers:

```python
def _message_text(message): ...
def _messages_text(messages): ...
def recovery_read_request(ledger, role): ...
def capture_executor_callback_from_read(state_root, project_id, task_id, messages, *, captured_at): ...
```

`recovery_read_request()` must return the role thread id and anchor from `planRequest`, latest executor dispatch, or `verification.request`.

- [x] **Step 4: Run tests to verify pass**

Run: `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration`.

### Task 4: Verifier Request, Verdict, Rework, And Closeout

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`

- [x] **Step 1: Write failing tests**

Add tests:

```python
def test_verifier_pass_writes_verification_and_closeout(self):
    ledger = self._verifying_ledger()
    verify_message = team_router.make_verifier_request_message(ledger["taskId"], ledger["observations"][-1]["content"], "read-only", "src")
    self.assertIn("TEAM_ROUTER_VERIFY taskId=ctr-20260622-160000-a7f3", verify_message)
    team_router.record_verifier_request_sent(self.root, self.project_id, ledger["taskId"], verifier_thread_id="thread-verifier", sent_at="2026-06-22T20:05:00+08:00", message_id="msg-verify")
    messages = [{"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"}]
    updated = team_router.capture_verifier_verdict_from_read(self.root, self.project_id, ledger["taskId"], messages, captured_at="2026-06-22T20:07:00+08:00")
    self.assertEqual(updated["status"], "done")
    self.assertEqual(updated["closeout"]["status"], "done")


def test_verifier_needs_rework_respects_max_rework(self):
    ledger = self._verifying_ledger(max_rework=0)
    team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)
    messages = [{"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"}]
    updated = team_router.capture_verifier_verdict_from_read(self.root, self.project_id, ledger["taskId"], messages, captured_at="2026-06-22T20:07:00+08:00")
    self.assertEqual(updated["status"], "blocked")
```

- [x] **Step 2: Run tests to verify failure**

Run: `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration`.

Expected: FAIL for missing verifier helpers.

- [x] **Step 3: Implement verifier helpers**

Add:

```python
def make_verifier_request_message(task_id, callback_block, permission, scope): ...
def record_verifier_request_sent(state_root, project_id, task_id, *, verifier_thread_id, sent_at, message_id=None): ...
def capture_verifier_verdict_from_read(state_root, project_id, task_id, messages, *, captured_at): ...
def _make_closeout(ledger, verdict_fields, captured_at): ...
```

`result: pass` moves to `done`; `needs_rework` moves to `needs_rework` if `reworkCount < maxRework`, otherwise `blocked`; `blocked` moves to `blocked`.

- [x] **Step 4: Run tests to verify pass**

Run: `py -m unittest tests.test_team_router.TestTeamRouterManagerIntegration`.

### Task 5: Skill Documentation And Final Verification

**Files:**
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `tests/test_team_router.py`

- [x] **Step 1: Add doc static test**

Extend `test_skill_doc_contains_required_boundaries()` to assert the skill text names `planRequest`, `searchAnchor`, `recovery_read_request`, and registry role persistence.

- [x] **Step 2: Update skill doc**

Add a short local helper section explaining that the manager flow records JSON state through deterministic helpers and stores anchors in `planRequest`, latest `dispatches[]`, and `verification.request`.

- [x] **Step 3: Run target tests**

Run: `py -m unittest discover -s tests -p test_team_router.py`

Expected: PASS.

- [x] **Step 4: Run full verification**

Run:

```text
py -m py_compile src\team_router.py tests\test_team_router.py
py -m unittest discover -s tests
git diff --check
```

Expected: all exit 0.

- [x] **Step 5: Commit**

Run:

```text
git add src/team_router.py tests/test_team_router.py skills/codex-team-router/SKILL.md docs/superpowers/plans/2026-06-22-team-router-manager-integration.md
git commit -m "feat: integrate team router manager state flow"
```