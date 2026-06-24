# Team Router Fast Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task and superpowers:verification-before-completion before reporting completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Team Router fast lane routing with task gate classification, direct-return-first behavior, and bounded fallback reads.

**Architecture:** Keep `src/team_router.py` as the deterministic policy/state-machine layer. Add a classifier and read scheduler as pure helpers first, then wire them into watcher/run updates without weakening existing reviewer gates. Keep docs and tests synchronized through `protocol_contract_snapshot()`.

**Tech Stack:** Python standard library, `unittest`, Markdown skill/runbook docs, existing Codex desktop thread-tool adapter boundary.

## Global Constraints

- Manager Mode must not perform implementation work directly.
- FAST and NORMAL tasks use `executor -> verifier`.
- STRICT and PACKAGE tasks use `executor -> reviewer -> verifier`.
- Direct return is the preferred completion path; bounded `read_thread` is fallback.
- User-triggered status reads are allowed; continuous polling and mid-run instruction injection remain forbidden.
- No push/PR/merge/deploy in this implementation.

---

### Task 1: Gate Classifier

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: existing `reviewer_gate_required_for_ledger(ledger) -> bool`
- Produces: `classify_team_router_gate(ledger: Mapping[str, Any]) -> str`
- Produces: `gate_class_requires_reviewer(gate_class: str) -> bool`

- [ ] **Step 1: Add failing classifier tests**

Add tests near existing reviewer gate tests:

```python
def test_classify_team_router_gate_fast_docs_rework(self):
    ledger = {
        "objective": "restore README BOM and keep polling wording",
        "plan": {"fields": {
            "scope": "README.md",
            "riskBoundary": "docs-only encoding rework",
            "executorPrompt": "restore UTF-8 BOM only",
            "notes": "no runtime change",
        }},
    }

    self.assertEqual(team_router.classify_team_router_gate(ledger), "FAST")
    self.assertFalse(team_router.gate_class_requires_reviewer("FAST"))


def test_classify_team_router_gate_strict_for_router_policy(self):
    ledger = {
        "objective": "Team Router bounded polling runtime policy",
        "plan": {"fields": {
            "scope": "src/team_router.py tests/test_team_router.py",
            "riskBoundary": "manager orchestration policy",
            "executorPrompt": "change role protocol and polling rules",
            "notes": "process rules",
        }},
    }

    self.assertEqual(team_router.classify_team_router_gate(ledger), "STRICT")
    self.assertTrue(team_router.gate_class_requires_reviewer("STRICT"))


def test_classify_team_router_gate_package_for_compounded_discipline(self):
    ledger = {
        "objective": "manager-discipline hardening package",
        "plan": {"fields": {
            "scope": "Team Router discipline package",
            "riskBoundary": "role title plus polling plus manager overreach",
            "executorPrompt": "bundle related process hardening",
            "notes": "package same task family",
        }},
    }

    self.assertEqual(team_router.classify_team_router_gate(ledger), "PACKAGE")
    self.assertTrue(team_router.gate_class_requires_reviewer("PACKAGE"))
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_classify_team_router_gate_fast_docs_rework tests.test_team_router.TestTeamRouterState.test_classify_team_router_gate_strict_for_router_policy tests.test_team_router.TestTeamRouterState.test_classify_team_router_gate_package_for_compounded_discipline -v
```

Expected: fail because helper functions do not exist.

- [ ] **Step 3: Implement minimal classifier**

Add constants and helpers near reviewer gate constants:

```python
GATE_CLASSES = ("FAST", "NORMAL", "STRICT", "PACKAGE")
FAST_GATE_TERMS = (
    "bom",
    "encoding",
    "docs-only",
    "typo",
    "wording",
    "readme",
)
PACKAGE_GATE_TERMS = (
    "package",
    "bundle",
    "compounded",
    "same task family",
    "discipline hardening",
)


def classify_team_router_gate(ledger: Mapping[str, Any]) -> str:
    text = _reviewer_gate_text(ledger)
    if any(term in text for term in PACKAGE_GATE_TERMS):
        return "PACKAGE"
    if reviewer_gate_required_for_ledger(ledger):
        return "STRICT"
    if any(term in text for term in FAST_GATE_TERMS):
        return "FAST"
    return "NORMAL"


def gate_class_requires_reviewer(gate_class: str) -> bool:
    gate = _required_str(gate_class, "gateClass").upper()
    if gate not in GATE_CLASSES:
        raise ProtocolError("invalid gateClass: %r" % (gate_class,))
    return gate in {"STRICT", "PACKAGE"}
```

- [ ] **Step 4: Update reviewer gate to use classifier where appropriate**

In paths that currently call `reviewer_gate_required_for_ledger(ledger)` for routing, keep compatibility but derive from classifier when possible:

```python
def reviewer_gate_required_for_ledger(ledger: Mapping[str, Any]) -> bool:
    if _reviewer_gate_explicitly_required(ledger):
        return True
    text = _reviewer_gate_text(ledger)
    if any(term in text for term in REVIEWER_GATE_REQUIRED_TERMS):
        return True
    return "team router" in text and any(term in text for term in REVIEWER_GATE_TEAM_ROUTER_QUALIFIERS)
```

Do not replace this helper yet if it creates recursion. Instead, make routing code call `gate_class_requires_reviewer(classify_team_router_gate(ledger))` in the next task.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_classify_team_router_gate_fast_docs_rework tests.test_team_router.TestTeamRouterState.test_classify_team_router_gate_strict_for_router_policy tests.test_team_router.TestTeamRouterState.test_classify_team_router_gate_package_for_compounded_discipline tests.test_team_router.TestTeamRouterState.test_reviewer_gate_required_for_runtime_gate_reviewer_gate_and_team_router_self_changes tests.test_team_router.TestTeamRouterState.test_reviewer_gate_required_does_not_trigger_on_team_router_filename_only -v
```

Expected: pass.

### Task 2: Direct-Return-First Scheduler

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `classify_team_router_gate(ledger)`
- Produces: `role_read_interval_seconds(gate_class: str) -> int`
- Produces: `next_role_read_policy(ledger: Mapping[str, Any], *, observed_at: str) -> dict[str, Any]`
- Produces: `role_read_allowed(ledger: Mapping[str, Any], *, observed_at: str, reason: str) -> dict[str, Any]`

- [ ] **Step 1: Add failing scheduler tests**

Add tests near manager orchestration policy tests:

```python
def test_fast_gate_default_read_window_is_30_seconds(self):
    self.assertEqual(team_router.role_read_interval_seconds("FAST"), 30)
    self.assertEqual(team_router.role_read_interval_seconds("NORMAL"), 60)
    self.assertEqual(team_router.role_read_interval_seconds("STRICT"), 90)
    self.assertEqual(team_router.role_read_interval_seconds("PACKAGE"), 120)


def test_role_read_allowed_suppresses_early_fallback_reads(self):
    ledger = {
        "taskId": "ctr-20260624-120000-fast",
        "objective": "restore README BOM",
        "status": "awaiting_callback",
        "plan": {"fields": {"scope": "README.md", "riskBoundary": "docs-only encoding"}},
        "readDiscipline": {
            "gateClass": "FAST",
            "nextAllowedReadAt": "2026-06-24T12:00:30+08:00",
            "directReturnExpected": True,
        },
    }

    decision = team_router.role_read_allowed(
        ledger,
        observed_at="2026-06-24T12:00:10+08:00",
        reason="scheduled-fallback",
    )

    self.assertFalse(decision["allowed"])
    self.assertEqual(decision["action"], "read_suppressed")
    self.assertIn("direct return", decision["reason"])


def test_role_read_allowed_user_triggered_status_read(self):
    ledger = {
        "taskId": "ctr-20260624-120000-fast",
        "objective": "restore README BOM",
        "status": "awaiting_callback",
        "readDiscipline": {
            "gateClass": "FAST",
            "nextAllowedReadAt": "2026-06-24T12:00:30+08:00",
            "directReturnExpected": True,
        },
    }

    decision = team_router.role_read_allowed(
        ledger,
        observed_at="2026-06-24T12:00:10+08:00",
        reason="user-triggered status check",
    )

    self.assertTrue(decision["allowed"])
    self.assertEqual(decision["action"], "read_allowed")
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_fast_gate_default_read_window_is_30_seconds tests.test_team_router.TestTeamRouterState.test_role_read_allowed_suppresses_early_fallback_reads tests.test_team_router.TestTeamRouterState.test_role_read_allowed_user_triggered_status_read -v
```

Expected: fail because scheduler helpers do not exist.

- [ ] **Step 3: Implement interval and ISO helpers**

Add:

```python
GATE_READ_INTERVAL_SECONDS = {
    "FAST": 30,
    "NORMAL": 60,
    "STRICT": 90,
    "PACKAGE": 120,
}


def role_read_interval_seconds(gate_class: str) -> int:
    gate = _required_str(gate_class, "gateClass").upper()
    if gate not in GATE_READ_INTERVAL_SECONDS:
        raise ProtocolError("invalid gateClass: %r" % (gate_class,))
    return GATE_READ_INTERVAL_SECONDS[gate]
```

Use existing timestamp helpers if present. If none exists, add a private helper using `datetime.fromisoformat()` and preserve timezone offsets.

- [ ] **Step 4: Implement read policy helpers**

Add:

```python
def next_role_read_policy(ledger: Mapping[str, Any], *, observed_at: str) -> dict[str, Any]:
    gate = classify_team_router_gate(ledger)
    seconds = role_read_interval_seconds(gate)
    next_allowed = _isoformat_plus_seconds(observed_at, seconds)
    return {
        "gateClass": gate,
        "lastReadAt": None,
        "nextAllowedReadAt": next_allowed,
        "readReason": "awaiting direct return fallback",
        "directReturnExpected": True,
    }


def role_read_allowed(ledger: Mapping[str, Any], *, observed_at: str, reason: str) -> dict[str, Any]:
    reason_text = _required_str(reason, "reason")
    if "user-triggered" in reason_text or "timeout" in reason_text or "blocker" in reason_text:
        return {"allowed": True, "action": "read_allowed", "reason": reason_text}
    discipline = ledger.get("readDiscipline") if isinstance(ledger.get("readDiscipline"), Mapping) else {}
    next_allowed = discipline.get("nextAllowedReadAt")
    if isinstance(next_allowed, str) and _iso_timestamp_before(observed_at, next_allowed):
        return {
            "allowed": False,
            "action": "read_suppressed",
            "reason": "await direct return until nextAllowedReadAt",
            "nextAllowedReadAt": next_allowed,
        }
    return {"allowed": True, "action": "read_allowed", "reason": reason_text}
```

- [ ] **Step 5: Attach read discipline to dispatch/update records**

When sending executor/reviewer/verifier work and returning `nextWakeup`, include:

```python
ledger["readDiscipline"] = next_role_read_policy(ledger, observed_at=sent_at)
```

If modifying ledger shape is too broad for this task, attach it to the returned update first:

```python
update["readDiscipline"] = next_role_read_policy(ledger, observed_at=observed_at)
```

Prefer update-only if ledger migrations would expand scope.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_fast_gate_default_read_window_is_30_seconds tests.test_team_router.TestTeamRouterState.test_role_read_allowed_suppresses_early_fallback_reads tests.test_team_router.TestTeamRouterState.test_role_read_allowed_user_triggered_status_read -v
```

Expected: pass.

### Task 3: Wire Fast Lane Into Reviewer Gate Flow

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `classify_team_router_gate()`
- Consumes: `gate_class_requires_reviewer()`
- Affects: `capture_executor_callback_from_read()` and watcher paths that choose reviewing vs verifying

- [ ] **Step 1: Add failing routing tests**

Add tests for callback capture status:

```python
def test_fast_gate_callback_skips_reviewer_and_enters_verifying(self):
    ledger = self._awaiting_callback_ledger()
    ledger["objective"] = "restore README BOM"
    ledger["plan"]["fields"]["scope"] = "README.md"
    ledger["plan"]["fields"]["riskBoundary"] = "docs-only encoding rework"
    team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)

    updated = team_router.capture_executor_callback_from_read(
        self.root,
        self.project_id,
        ledger["taskId"],
        [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-24T12:00:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-24T12:00:20+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: restored BOM\nevidence: README.md\nrisks: none\nnext: verifier" % ledger["taskId"],
            },
        ],
        captured_at="2026-06-24T12:00:21+08:00",
    )

    self.assertEqual(updated["status"], "verifying")


def test_strict_gate_callback_enters_reviewing(self):
    ledger = self._awaiting_callback_ledger()
    ledger["objective"] = "Team Router runtime gate policy"
    ledger["plan"]["fields"]["scope"] = "src/team_router.py"
    ledger["plan"]["fields"]["riskBoundary"] = "manager orchestration policy"
    team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)

    updated = team_router.capture_executor_callback_from_read(
        self.root,
        self.project_id,
        ledger["taskId"],
        [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-24T12:00:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-24T12:00:20+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: policy changed\nevidence: tests\nrisks: none\nnext: reviewer" % ledger["taskId"],
            },
        ],
        captured_at="2026-06-24T12:00:21+08:00",
    )

    self.assertEqual(updated["status"], "reviewing")
```

- [ ] **Step 2: Run tests and confirm current behavior**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_fast_gate_callback_skips_reviewer_and_enters_verifying tests.test_team_router.TestTeamRouterState.test_strict_gate_callback_enters_reviewing -v
```

Expected: strict likely passes, fast may pass or fail depending current keyword behavior. If fast already passes, keep the test as regression.

- [ ] **Step 3: Replace routing decision**

In `capture_executor_callback_from_read()`, replace direct reviewer gate status assignment with:

```python
gate_class = classify_team_router_gate(ledger)
ledger["gateClass"] = gate_class
ledger["status"] = "reviewing" if gate_class_requires_reviewer(gate_class) else "verifying"
```

If storing `gateClass` in ledger affects too many tests, store it in observation metadata first:

```python
observation["gateClass"] = gate_class
```

Prefer ledger-level `gateClass` because closeout and handoff can explain the route.

- [ ] **Step 4: Ensure reviewer send path rejects non-reviewer gates**

Update `send_reviewer_request_with_adapter()` guard:

```python
if not gate_class_requires_reviewer(classify_team_router_gate(ledger)):
    raise StateStoreError("reviewer gate is not required for task: %s" % task_id)
```

- [ ] **Step 5: Run routing tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_fast_gate_callback_skips_reviewer_and_enters_verifying tests.test_team_router.TestTeamRouterState.test_strict_gate_callback_enters_reviewing tests.test_team_router.TestTeamRouterManagerIntegration.test_watch_sends_reviewer_request_when_callback_requires_gate -v
```

Expected: pass. If the exact manager integration test name differs, run the nearest reviewer-request watch tests from `tests/test_team_router.py`.

### Task 4: Docs And Protocol Snapshot

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`
- Modify: `README.md`
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `skills/codex-team-router/references/manager-mode.md`
- Modify: `skills/codex-team-router/references/manual-orchestration.md`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`

**Interfaces:**
- Extends: `protocol_contract_snapshot()["managerOrchestrationPolicy"]`

- [ ] **Step 1: Add failing snapshot/doc tests**

Extend existing `test_protocol_contract_snapshot_includes_manager_orchestration_policy`:

```python
fast_lane = policy["fastLane"]
self.assertEqual(fast_lane["classes"], ("FAST", "NORMAL", "STRICT", "PACKAGE"))
self.assertIn("executor -> verifier", fast_lane["FAST"])
self.assertIn("executor -> reviewer", fast_lane["STRICT"])
self.assertIn("direct-return first", fast_lane["completion"])
self.assertIn("bounded read_thread fallback", fast_lane["completion"])
```

Extend doc tests to require:

```python
"FAST"
"NORMAL"
"STRICT"
"PACKAGE"
"direct-return first"
"bounded read_thread fallback"
"executor -> verifier"
"executor -> reviewer -> verifier"
```

- [ ] **Step 2: Run focused doc tests and confirm failure**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_manager_orchestration_policy tests.test_team_router.TestTeamRouterSkillDoc.test_manager_orchestration_policy_docs_cover_polling_reuse_and_verifier_return -v
```

Expected: fail until docs/snapshot are updated.

- [ ] **Step 3: Add snapshot policy**

In `MANAGER_ORCHESTRATION_POLICY`, add:

```python
"fastLane": {
    "classes": ("FAST", "NORMAL", "STRICT", "PACKAGE"),
    "FAST": "docs/BOM/single phrase rework uses executor -> verifier",
    "NORMAL": "small focused code or test work uses executor -> verifier",
    "STRICT": "Team Router process, permission, safety, role protocol, shared/high-risk logic uses executor -> reviewer -> verifier",
    "PACKAGE": "same task family discipline hardening package uses one executor -> reviewer -> verifier chain",
    "completion": "direct-return first; bounded read_thread fallback",
},
```

- [ ] **Step 4: Update docs**

Add a short section to each relevant doc:

```markdown
Fast lane gate classes:
- FAST: docs/BOM/single phrase rework, `executor -> verifier`, default 30s fallback window.
- NORMAL: small focused code/test work, `executor -> verifier`, default 60s fallback window.
- STRICT: Team Router process/permission/safety/role protocol/shared-risk changes, `executor -> reviewer -> verifier`, default 90s fallback window.
- PACKAGE: same task family discipline hardening, one `executor -> reviewer -> verifier` chain, default 120s fallback window.

Completion is direct-return first. Use bounded `read_thread` fallback only after the class window, user-triggered status request, expected completion window, or timeout/blocker handling.
```

- [ ] **Step 5: Run doc tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_manager_orchestration_policy tests.test_team_router.TestTeamRouterSkillDoc.test_manager_orchestration_policy_docs_cover_polling_reuse_and_verifier_return tests.test_team_router.TestTeamRouterSkillDoc.test_readme_documents_team_router_quick_start_and_boundaries -v
```

Expected: pass.

### Task 5: Verification

**Files:**
- Modify: this plan file only if tracking checkboxes during implementation.

- [ ] **Step 1: Run focused Team Router tests**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState tests.test_team_router.TestTeamRouterManagerIntegration tests.test_team_router.TestTeamRouterSkillDoc -v
```

Expected: pass.

- [ ] **Step 2: Run syntax check**

Run:

```powershell
py -m py_compile src\team_router.py tests\test_team_router.py
```

Expected: no output and exit 0.

- [ ] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: exit 0. CRLF warnings are acceptable only if they match current repository behavior and no whitespace errors appear.

- [ ] **Step 4: Confirm generated artifacts remain untouched**

Run:

```powershell
git status --short --ignored --untracked-files=all pet-runs ig_*.png .gitignore docs\evidence
```

Expected: generated artifacts appear only as ignored `!!` entries; evidence docs remain versionable/untracked unless explicitly staged later.

- [ ] **Step 5: Closeout**

Report:

```text
Implemented Fast Lane B:
- gate classifier: FAST/NORMAL/STRICT/PACKAGE
- direct-return-first completion
- bounded read_thread fallback scheduler
- docs/tests updated
Verification:
- <commands and results>
Not done:
- no commit/push/stage unless explicitly requested
```
