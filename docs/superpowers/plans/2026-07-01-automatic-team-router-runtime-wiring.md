# Automatic Team Router Runtime Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dry-run automatic Team Router runtime wiring gate that only allows the manager startup path when broker host readiness is ready.

**Architecture:** Keep live dispatch unchanged. Add a read-only runtime wiring check script that consumes an already-running localhost broker through `BrokerConfig`, derives the doctor host-readiness classification, and reports whether the manager may inject `host_context` into `orchestrate_team_task_with_adapter()`.

**Tech Stack:** Python stdlib, existing Team Router broker adapter, existing doctor host-readiness classifier, unittest.

## Global Constraints

- Do not start a production broker, daemon, scheduler service, or Desktop/plugin process.
- Do not call `create_thread`, `send_message_to_thread`, `read_thread`, or `set_thread_title` during dry-run; only inspect broker `/readiness` evidence.
- Automatic entry is allowed only when host readiness classifies as ready and the broker can build host-context kwargs.
- Missing or blocked broker readiness must report `manual_only` or `host_contract_blocked`, never automatic orchestration.
- The manager startup path is `broker_url/session_token -> broker_host_context_kwargs() -> make_live_orchestration_host_context() compatible kwargs -> orchestrate_team_task_with_adapter(host_context=...)`.
- This local package includes code, tests, docs, reviewer/verifier gates, and local commit only. It excludes push, PR, merge, deploy, publish/release, production daemon, live role dispatch, real external account/API use, and global skill sync.

---

### Task 1: Runtime Wiring Dry-Run Script

**Files:**
- Create: `scripts/team_router_runtime_wiring_check.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `team_router_broker_adapter.BrokerConfig`, `broker_host_context_kwargs()`, `broker_host_readiness_snapshot()`, `fetch_broker_readiness()`
- Consumes: `scripts.team_router_doctor.classify_host_readiness_snapshot()`
- Produces: CLI `py -B scripts\team_router_runtime_wiring_check.py --broker-url <url> --session-token <token> --json`

- [x] **Step 1: Write failing tests**

Add tests that prove:

- missing broker args returns `manual_only`;
- blocked readiness returns no automatic entry and no thread-tool calls;
- ready readiness returns `automaticEntryAllowed: true`, `managerStartupPath.injection: host_context`, and dry-run thread-tool calls remain empty.

- [x] **Step 2: Run tests to verify RED**

Run focused tests for the new script. Expected: fail because `scripts/team_router_runtime_wiring_check.py` does not exist.

- [x] **Step 3: Implement minimal script**

The script must fetch readiness, classify the host-readiness snapshot, build host-context kwargs only after readiness is ready, and emit JSON without calling thread tool endpoints.

- [x] **Step 4: Run focused tests to verify GREEN**

Run focused runtime wiring tests. Expected: all new tests pass.

### Task 2: Documentation And Package Current Truth

**Files:**
- Modify: `docs/workbench.md`
- Create: `docs/team-router/packages/ctr-20260701-automatic-runtime-wiring.md`
- Modify: `docs/superpowers/plans/2026-07-01-automatic-team-router-runtime-wiring.md`

**Interfaces:**
- Consumes: focused test and closeout command outputs
- Produces: current package record with evidence-only wording

- [x] **Step 1: Update workbench current task**

Record this active package, exact boundary, and next gates.

- [x] **Step 2: Update package verification record**

Add focused test, full test, truth, doctor, and closeout outputs after they are fresh.

- [x] **Step 3: Run stale truth checks**

Run `truth_check`, `doctor`, and `closeout_check`; correct stale current-truth wording if any script flags it.

### Task 3: Review, Verify, Commit

**Files:**
- Modify only files touched by Tasks 1-2 if reviewer/verifier finds issues

**Interfaces:**
- Consumes: local diff, verification output, reviewer/verifier findings
- Produces: local commit

- [x] **Step 1: Run full verification**

Run compile, focused tests, full Team Router test module, `git diff --check`, `truth_check`, `doctor`, and `closeout_check`.

- [x] **Step 2: Reviewer pass**

Read-only/adversarial reviewer checks that readiness gate prevents accidental automatic orchestration and dry-run does not mutate Desktop/thread state.

- [x] **Step 3: Verifier pass**

Read-only verifier accepts only if evidence supports local commit.

- [x] **Step 4: Local commit**

After acceptance, stage only this package's files and commit. No push.
