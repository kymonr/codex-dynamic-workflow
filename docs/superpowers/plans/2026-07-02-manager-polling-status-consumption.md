# Manager Polling Status Consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the manager polling doctor UX usable end-to-end without adding live thread-tool calls.

**Architecture:** Keep runtime observation and user-facing reporting separated. `scripts/team_router_doctor.py` continues to compute `managerPollingStatus` only from caller-supplied snapshots; `src/team_router_status.py` only formats an already-computed polling status mapping when present on the ledger. Fixtures and runbook text show operators how to provide evidence, including the non-live boundary for broker/readiness smoke.

**Tech Stack:** Python standard library, `unittest`, JSON fixtures, Markdown docs.

## Global Constraints

- Do not call real `read_thread`, `send_message_to_thread`, `create_thread`, `set_thread_title`, broker daemons, live role dispatch, push, PR, merge, deploy, publish/release, or global skill sync in this package.
- Keep all status output evidence-only and deterministic.
- Use TDD for production behavior changes.
- Commit locally after verification because this is an explicitly authorized Complex Task Stack local package.

---

### Task 1: Manager Polling Snapshot Fixture And Runbook

**Files:**
- Create: `tests/fixtures/team_router/manager_polling_status_snapshot.json`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`
- Test: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `scripts/team_router_doctor.py --role-status-json <path> --json`
- Produces: a reusable fixture with top-level `roles`, `expectedMarkers`, and `managerPolling`.

- [x] **Step 1: Write the failing test**

Add a `TestTeamRouterState` test that loads `tests/fixtures/team_router/manager_polling_status_snapshot.json`, runs `scripts/team_router_doctor.py --role-status-json <fixture> --json`, and asserts:

```python
report["managerPollingStatus"]["status"] == "read_suppressed"
report["managerPollingStatus"]["nextAllowedReadAt"] == "2026-07-02T10:05:30+08:00"
"managerPolling=read_suppressed" in report["summary"]
```

Add a `TestTeamRouterSkillDoc` test that asserts the runbook names:

```text
managerPolling
tests/fixtures/team_router/manager_polling_status_snapshot.json
--role-status-json
evidence-only
does not call live thread tools
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache-complex-red1'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_fixture_reports_manager_polling_status tests.test_team_router.TestTeamRouterSkillDoc.test_runbook_documents_manager_polling_snapshot_fixture -v
```

Expected: FAIL because the fixture and runbook text are missing.

- [x] **Step 3: Write minimal implementation**

Create the fixture with a representative suppressed-read `managerPolling` snapshot and add a short runbook section showing the command:

```powershell
py -B scripts\team_router_doctor.py --role-status-json tests\fixtures\team_router\manager_polling_status_snapshot.json --json
```

- [x] **Step 4: Run test to verify it passes**

Run the same command. Expected: PASS.

### Task 2: User-Facing Status Formatter Consumption

**Files:**
- Modify: `src/team_router_status.py`
- Test: `tests/test_team_router.py`

**Interfaces:**
- Consumes: optional `ledger["managerPollingStatus"]` mapping with `status`, `shouldRead`, `shouldReport`, `nextAllowedReadAt`, and `summary`.
- Produces: handoff/closeout text section:

```text
managerPolling:
  status: ...
  shouldRead: ...
  shouldReport: ...
  nextAllowedReadAt: ...
  summary: ...
```

- [x] **Step 1: Write the failing tests**

Add tests for `team_router.format_handoff_for_user(...)` and `team_router.format_closeout_for_user(...)` with a ledger containing `managerPollingStatus`, asserting the section appears and no live thread-tool wording is introduced.

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache-complex-red2'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_handoff_includes_manager_polling_status_summary tests.test_team_router.TestTeamRouterState.test_closeout_includes_manager_polling_status_summary -v
```

Expected: FAIL because formatters do not emit `managerPolling`.

- [x] **Step 3: Write minimal implementation**

Add a helper in `src/team_router_status.py` that formats the optional mapping and call it from both handoff and closeout formatters.

- [x] **Step 4: Run tests to verify they pass**

Run the same command. Expected: PASS.

### Task 3: Package Closeout

**Files:**
- Create: `docs/team-router/packages/ctr-20260702-manager-polling-status-consumption.md`
- Modify: `docs/workbench.md`

**Interfaces:**
- Consumes: fresh test/truth/doctor/closeout outputs.
- Produces: current-truth package record ready for local commit.

- [x] **Step 1: Update package/workbench current state**

Record scope, exclusions, red/green evidence, and reviewer/verifier/local closeout status.

- [x] **Step 2: Run final verification**

Run focused tests, `py_compile`, `git diff --check`, `truth_check`, `doctor`, and `closeout_check` with `PYTHONPYCACHEPREFIX` under `C:\tmp`.

- [x] **Step 3: Commit**

Stage only this package's files and commit:

```powershell
git add -- docs/superpowers/plans/2026-07-02-manager-polling-status-consumption.md tests/fixtures/team_router/manager_polling_status_snapshot.json docs/runbooks/codex-team-router-live-orchestration.md src/team_router_status.py tests/test_team_router.py docs/workbench.md docs/team-router/packages/ctr-20260702-manager-polling-status-consumption.md
git commit -m "surface manager polling status consumption"
```
