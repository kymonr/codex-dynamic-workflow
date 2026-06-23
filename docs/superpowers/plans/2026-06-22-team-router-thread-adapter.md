# Team Router Thread Adapter Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the codex-team-router JSON registry/ledger helper layer to a testable thread-tool adapter boundary for `create_thread`, `send_message_to_thread`, and `read_thread`; add manager/executor/verifier orchestration smoke coverage; add user-facing closeout and handoff output; sync stale plan checkboxes.

**Architecture:** Keep `src/team_router.py` deterministic and import-only safe. It must not import or call Codex app tools directly. Instead, helper functions accept a thread adapter object or mapping with `create_thread`, `send_message_to_thread`, and `read_thread` callables. Tests use a fake adapter; live Codex app smoke is run by the parent agent with real tools.

**Tech Stack:** Python standard library, `unittest`, existing JSON registry/ledger helpers, Codex app thread tools at the outer orchestration layer.

---

### Task 1: Sync Stale Plan State

**Files:**
- Modify: `docs/superpowers/plans/2026-06-20-claude-read-backend.md`

- [x] Mark completed steps as checked because the current code and tests already implement the Claude read backend.
- [x] Do not change the historical implementation details unless they are actively misleading.

### Task 2: Adapter Result Normalization

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`

- [x] Add tests for `thread_send_anchor()` accepting common `send_message_to_thread` result shapes.
- [x] Add tests for `normalize_thread_read_messages()` accepting raw lists, `{messages: [...]}`, nested `{thread: {messages: [...]}}`, and Codex turn summaries.
- [x] Implement minimal normalization helpers with explicit bad-shape errors.

### Task 3: Manager/Executor/Verifier Adapter Flow

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`

- [x] Add a fake adapter smoke test that creates role threads, creates a task ledger, sends manager plan request, reads manager plan, dispatches executor, reads executor callback, sends verifier request, and reads verifier verdict.
- [x] Implement role thread creation and send/read wrapper functions around existing ledger state helpers.
- [x] Keep terminal/rework protections in the existing state helpers, not duplicated in the adapter wrappers.

### Task 4: User-Facing Closeout And Handoff

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`
- Modify: `skills/codex-team-router/SKILL.md`

- [x] Add tests for `format_closeout_for_user()` and `format_handoff_for_user()`.
- [x] Include task id, status, role thread ids, anchors, evidence, risks, and next action.
- [x] Update the skill doc to name the adapter functions and user-facing output helpers.

### Task 5: Verification And Review

**Files:**
- Modify: this plan file

- [x] Run targeted team-router tests.
- [x] Run full test suite.
- [x] Run `py_compile` for touched Python files.
- [x] Run `git diff --check`.
- [x] Run final review or Claude review if useful before closing the goal.
- [x] Run live Codex thread tool smoke for create/send/read on manager/executor/verifier threads.
