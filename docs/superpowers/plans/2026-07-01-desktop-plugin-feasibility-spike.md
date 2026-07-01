# Desktop Plugin Feasibility Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm whether Codex Desktop/plugin can provide callable Team Router host tools for `create_thread`, `read_thread`, `send_message_to_thread`, `set_thread_title`, and scheduler/broker startup capability.

**Architecture:** This is an evidence-only spike. It records current Codex app tool callability, separates model-side app tools from in-process Python adapter callables, and records whether the repo has a broker/scheduler startup surface or only a broker client/checker.

**Tech Stack:** Codex app tools, Team Router Python host-runtime helpers, `scripts/team_router_broker_feasibility_check.py`, `docs/workbench.md`, package docs.

## Global Constraints

- No Team Router runtime implementation, adapter rewrite, watcher change, scheduler daemon, broker service, production startup, push, PR, merge, deploy, publish/release, or global skill sync.
- No live `create_thread`, `send_message_to_thread`, or `set_thread_title` smoke unless separately authorized because those mutate Codex Desktop state.
- `read_thread`, `list_projects`, and `list_threads` may be used as read-only feasibility evidence.
- Final answer must distinguish model-side Codex app tools from in-process Python callables required by `assess_live_orchestration_readiness()`.
- Local commit is allowed only after evidence docs, verification, reviewer, and verifier gates are satisfied.

---

### Task 1: Current Tool Surface Evidence

**Files:**
- Modify: `docs/team-router/packages/ctr-20260701-desktop-plugin-feasibility-spike.md`
- Modify: `docs/workbench.md`

**Interfaces:**
- Consumes: `codex_app.list_projects`, `codex_app.list_threads`, `codex_app.read_thread`, tool descriptors for `codex_app.create_thread`, `codex_app.send_message_to_thread`, and `codex_app.set_thread_title`.
- Produces: documented tool-callability verdict for current Codex Desktop session.

- [x] **Step 1: Discover tools**

Run: `tool_search` for `create_thread read_thread send_message_to_thread set_thread_title Codex thread tools scheduler broker startup`.

Expected: `codex_app.read_thread`, `codex_app.list_projects`, and `codex_app.list_threads` are verified through read-only calls. `codex_app.create_thread`, `codex_app.send_message_to_thread`, and `codex_app.set_thread_title` are recorded only as descriptor-observed unless a separately authorized live smoke invokes them.

- [x] **Step 2: Run read-only app probes**

Run: `codex_app.list_projects`, `codex_app.list_threads`, and `codex_app.read_thread` only.

Expected: read-only calls succeed. Do not call `create_thread`, `send_message_to_thread`, or `set_thread_title` because they mutate Desktop state.

- [x] **Step 3: Record evidence**

Update package/workbench with exact verdict: model-side Desktop app thread tools are callable in this session; mutating tools are not smoke-tested; Python host readiness still needs an adapter wrapper.

### Task 2: Broker And Scheduler Boundary Evidence

**Files:**
- Modify: `docs/team-router/packages/ctr-20260701-desktop-plugin-feasibility-spike.md`
- Modify: `docs/workbench.md`

**Interfaces:**
- Consumes: `src/team_router_host_runtime.py`, `src/team_router_broker_adapter.py`, `scripts/team_router_broker_feasibility_check.py`.
- Produces: documented scheduler/broker startup verdict.

- [x] **Step 1: Inspect repo host-runtime boundary**

Use CodeGraph on `assess_live_orchestration_readiness`, `CodexAppThreadAdapter`, `BrokerHeartbeatScheduler`, and broker readiness helpers.

Expected: host readiness requires Python-callable adapter methods, `parent_thread_id`, and callable heartbeat scheduler; broker adapter is a localhost client, not a broker starter.

- [x] **Step 2: Run broker feasibility checker without broker credentials**

Run: `py -B scripts\team_router_broker_feasibility_check.py --json`.

Expected: blocked with missing `broker-url` and `session-token`; no Desktop mutation.

- [x] **Step 3: Run focused broker tests**

Run: `py -B -m unittest tests.test_team_router.TestTeamRouterBrokerFeasibilityScript -v` and selected broker scheduler tests.

Expected: tests pass, proving checker and scheduler wrapper contracts in repo.

- [x] **Step 4: Record evidence**

Update package/workbench with exact verdict: no Desktop/plugin broker startup callable was exposed; repo can consume a broker and schedule via `/scheduler/wake` only when broker URL/token/readiness exist.

### Task 3: Verification, Review, And Closeout

**Files:**
- Modify: `docs/workbench.md`
- Modify: `docs/team-router/packages/ctr-20260701-desktop-plugin-feasibility-spike.md`
- Create: `docs/superpowers/plans/2026-07-01-desktop-plugin-feasibility-spike.md`

**Interfaces:**
- Consumes: Team Router `truth_check`, `doctor`, `closeout_check`, `git diff --check`.
- Produces: local closeout-ready evidence, pending reviewer/verifier decision.

- [x] **Step 1: Run current truth checks**

Run: `py -B scripts\team_router_truth_check.py --json`, `py -B scripts\team_router_doctor.py --json`, `py -B scripts\team_router_closeout_check.py --json`, and `git diff --check`.

Expected: no stale claims, active package dirty state, skill sync match, no unauthorized push/PR/sync.

- [x] **Step 2: Run reviewer/verifier gates**

Use read-only reviewer/verifier for the evidence docs. They must verify no overclaim, no runtime implementation, and exact boundary preservation.

- [x] **Step 3: Commit after gates**

If reviewer and verifier pass, stage only task files and commit locally. No push/PR/merge/deploy/global sync.