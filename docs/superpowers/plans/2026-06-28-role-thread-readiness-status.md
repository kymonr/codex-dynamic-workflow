# Role Thread Readiness Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or equivalent inline execution to implement this plan task-by-task. Use superpowers:test-driven-development for every behavior change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only manager-facing role-thread readiness/status surface so Team Router can explain whether a role thread is missing, created but not visible, visible but waiting, active, returned a protocol block, or unreachable.

**Architecture:** Keep this package in the status/doctor layer. Do not change `src/team_router.py` dispatch, watcher, registry, ledger, protocol parsing, or read cadence semantics. `scripts/team_router_doctor.py` will accept an optional bounded role-thread snapshot and classify it deterministically; docs/tests will lock that the status surface is evidence-only and does not create, read, poll, or send to threads.

**Tech Stack:** Python standard library, `unittest`, JSON snapshots, Markdown docs.

---

## Files

- Modify: `scripts/team_router_doctor.py` - add pure role-thread status classification and optional `--role-status-json` input.
- Modify: `tests/test_team_router.py` - add TDD coverage for role-thread status classification and doctor JSON output.
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md` - document role-thread status snapshots as read-only evidence.
- Modify: `docs/workbench.md` - update current task/gate for `ctr-20260628-role-thread-readiness-status`.
- Create: `docs/team-router/packages/ctr-20260628-role-thread-readiness-status.md` - review package with scope, tests, not-done gates, and risks.
- Do not modify: `src/team_router.py` in this package.
- Do not modify: `skills/codex-team-router/SKILL.md` unless an existing size/contract test forces a wording update.

---

### Task 1: Role Thread Status Classifier

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `scripts/team_router_doctor.py`

- [ ] **Step 1: Write failing tests for status classification**

Add tests to `TestTeamRouterState`:

```python
def test_router_doctor_classifies_role_thread_readiness_states(self):
    spec = importlib.util.spec_from_file_location(
        "team_router_doctor_under_test",
        ROOT / "scripts" / "team_router_doctor.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    snapshot = {
        "roles": [
            {"role": "executor"},
            {"role": "reviewer", "threadId": "thread-reviewer", "visible": False, "readError": "No Codex thread found"},
            {"role": "verifier", "threadId": "thread-verifier", "visible": True, "turnStatus": "inProgress", "messages": []},
            {"role": "manager", "threadId": "thread-manager", "visible": True, "turnStatus": "idle", "messages": [
                {"text": "TEAM_ROUTER_PLAN taskId=ctr-1\nstatus: planned"}
            ]},
        ],
        "expectedMarkers": {
            "manager": "TEAM_ROUTER_PLAN",
            "executor": "TEAM_ROUTER_CALLBACK",
            "reviewer": "TEAM_ROUTER_REVIEW",
            "verifier": "TEAM_ROUTER_VERDICT",
        },
    }

    result = module.classify_role_thread_status_snapshot(snapshot)

    by_role = {item["role"]: item for item in result}
    self.assertEqual(by_role["executor"]["status"], "missing")
    self.assertEqual(by_role["reviewer"]["status"], "created_not_visible")
    self.assertEqual(by_role["verifier"]["status"], "active_wait")
    self.assertEqual(by_role["manager"]["status"], "protocol_returned")
    self.assertIn("No Codex thread found", by_role["reviewer"]["reason"])
```

- [ ] **Step 2: Run RED**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_role_thread_readiness_states -v
```

Expected: FAIL because `classify_role_thread_status_snapshot` does not exist.

- [ ] **Step 3: Implement minimal classifier**

In `scripts/team_router_doctor.py`, add:

```python
ACTIVE_TURN_STATUSES = {"active", "inProgress", "running", "working"}


def _role_messages(role_record):
    messages = role_record.get("messages")
    return messages if isinstance(messages, list) else []


def _message_text(message):
    if isinstance(message, dict):
        return str(message.get("text") or "")
    return str(message or "")


def _has_marker(messages, marker):
    if not marker:
        return False
    return any(marker in _message_text(message) for message in messages)


def classify_role_thread_status(role_record, expected_marker=None):
    role = str(role_record.get("role") or "role")
    thread_id = str(role_record.get("threadId") or "").strip()
    if not thread_id:
        return {"role": role, "threadId": None, "status": "missing", "reason": "no role thread id recorded"}
    read_error = str(role_record.get("readError") or "").strip()
    visible = bool(role_record.get("visible"))
    if read_error or not visible:
        return {
            "role": role,
            "threadId": thread_id,
            "status": "created_not_visible",
            "reason": read_error or "role thread not visible in supplied snapshot",
        }
    messages = _role_messages(role_record)
    if _has_marker(messages, expected_marker):
        return {"role": role, "threadId": thread_id, "status": "protocol_returned", "reason": "%s marker observed" % expected_marker}
    turn_status = str(role_record.get("turnStatus") or "").strip()
    if turn_status in ACTIVE_TURN_STATUSES:
        return {"role": role, "threadId": thread_id, "status": "active_wait", "reason": "role turn is %s; observe without polling escalation" % turn_status}
    return {"role": role, "threadId": thread_id, "status": "visible_waiting", "reason": "role thread visible; no expected protocol marker observed"}


def classify_role_thread_status_snapshot(snapshot):
    expected = snapshot.get("expectedMarkers") if isinstance(snapshot.get("expectedMarkers"), dict) else {}
    roles = snapshot.get("roles") if isinstance(snapshot.get("roles"), list) else []
    return [
        classify_role_thread_status(role, expected.get(str(role.get("role") or "")))
        for role in roles
        if isinstance(role, dict)
    ]
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_role_thread_readiness_states -v
```

Expected: PASS.

---

### Task 2: Doctor JSON Integration

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `scripts/team_router_doctor.py`

- [ ] **Step 1: Write failing CLI test**

Add test:

```python
def test_router_doctor_includes_role_thread_status_snapshot(self):
    with workspace_temp_dir() as tmp:
        tmp_path = Path(tmp)
        snapshot_path = tmp_path / "role-status.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "roles": [
                        {"role": "reviewer", "threadId": "thread-reviewer", "visible": True, "turnStatus": "idle", "messages": []},
                    ],
                    "expectedMarkers": {"reviewer": "TEAM_ROUTER_REVIEW"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "team_router_doctor.py"),
                "--repo-root",
                str(ROOT),
                "--role-status-json",
                str(snapshot_path),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "read-only")
        self.assertEqual(report["roleThreadStatus"][0]["role"], "reviewer")
        self.assertEqual(report["roleThreadStatus"][0]["status"], "visible_waiting")
        self.assertNotIn("created role thread", report["summary"])
        self.assertFalse(report["authorization"]["commit"])
        self.assertFalse(report["authorization"]["push"])
```

- [ ] **Step 2: Run RED**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_role_thread_status_snapshot -v
```

Expected: FAIL because `--role-status-json` is not accepted.

- [ ] **Step 3: Add CLI argument and report field**

In `scripts/team_router_doctor.py`:

```python
def _load_role_status_snapshot(path):
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))
```

Change `build_doctor_report(...)` to accept `role_status_snapshot=None` and add:

```python
role_status = (
    classify_role_thread_status_snapshot(role_status_snapshot)
    if isinstance(role_status_snapshot, dict)
    else []
)
```

Return:

```python
"roleThreadStatus": role_status,
```

In `main`, add:

```python
parser.add_argument("--role-status-json", type=Path)
role_status_snapshot = _load_role_status_snapshot(args.role_status_json)
report = build_doctor_report(args.repo_root, args.global_skill, args.scan_file, role_status_snapshot)
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_role_thread_status_snapshot -v
```

Expected: PASS.

---

### Task 3: Documentation And Package Evidence

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md`
- Modify: `docs/workbench.md`
- Create: `docs/team-router/packages/ctr-20260628-role-thread-readiness-status.md`

- [ ] **Step 1: Write failing docs tests**

Add docs test:

```python
def test_quality_gates_document_role_thread_status_snapshots(self):
    text = (ROOT / "skills" / "codex-team-router" / "references" / "testing-and-quality-gates.md").read_text(encoding="utf-8")

    for needle in (
        "--role-status-json",
        "roleThreadStatus",
        "created_not_visible",
        "active_wait",
        "protocol_returned",
        "does not create, read, poll, send, stage, commit, push, PR, merge, deploy, or sync",
    ):
        self.assertIn(needle, text)
```

- [ ] **Step 2: Run RED**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_role_thread_status_snapshots -v
```

Expected: FAIL because docs do not mention the new status snapshot contract.

- [ ] **Step 3: Update quality-gates docs**

Append to `skills/codex-team-router/references/testing-and-quality-gates.md`:

```markdown
## Role Thread Status Snapshots

- `scripts/team_router_doctor.py --role-status-json <path> --json` accepts a bounded, caller-supplied role-thread snapshot and reports `roleThreadStatus`.
- The snapshot status vocabulary is `missing`, `created_not_visible`, `visible_waiting`, `active_wait`, and `protocol_returned`.
- This is evidence-only status UX. It does not create, read, poll, send, stage, commit, push, PR, merge, deploy, or sync.
- `active_wait` means observe under the existing cadence; it is not permission for immediate continuous `read_thread` polling.
- `protocol_returned` means the expected marker was present in supplied evidence; final acceptance still requires reviewer/verifier protocol gates as applicable.
```

- [ ] **Step 4: Update workbench and package doc**

Update `docs/workbench.md` current task:

```markdown
- State: active local package implementation for `ctr-20260628-role-thread-readiness-status`; scope is read-only role-thread status UX in `scripts/team_router_doctor.py`.
- Not done: no commit, no push, no PR, no merge, no deploy, no publish/release, no global skill sync unless separately authorized.
```

Create `docs/team-router/packages/ctr-20260628-role-thread-readiness-status.md` with objective, scope, files, tests, reviewer/verifier placeholders, not-done gates, and risks.

- [ ] **Step 5: Run GREEN docs tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_role_thread_status_snapshots tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v
```

Expected: PASS, adjusting existing workbench test only if it currently locks the previous package as current.

---

### Task 4: Final Verification And Gates

**Files:**
- No new source files beyond prior tasks.

- [ ] **Step 1: Run focused state tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState -v
```

Expected: PASS.

- [ ] **Step 2: Run docs tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v
```

Expected: PASS.

- [ ] **Step 3: Run compile and full suite**

Run:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-role-status'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-role-status'; py -B -m unittest tests.test_team_router
```

Expected: PASS / OK.

- [ ] **Step 4: Run closeout evidence tools**

Run:

```powershell
git diff --check
py -B scripts\team_router_truth_check.py --json
py -B scripts\team_router_doctor.py --json
py -B scripts\team_router_skill_sync_check.py --check
```

Expected: `git diff --check` exit 0, `staleClaims: []`, doctor does not claim live dispatch, and skill sync remains `match` unless package docs intentionally changed global skill references.

- [ ] **Step 5: Reviewer and verifier gates**

Request a read-only reviewer role for the package. If reviewer returns `needs_rework`, fix with TDD and request re-review. After reviewer `pass`, request verifier. Do not claim final acceptance until verifier returns `TEAM_ROUTER_VERDICT result: pass`.

- [ ] **Step 6: Closeout boundary**

Do not commit, push, PR, merge, deploy, publish, release, or global skill sync unless the user explicitly opens that gate after verifier acceptance.

