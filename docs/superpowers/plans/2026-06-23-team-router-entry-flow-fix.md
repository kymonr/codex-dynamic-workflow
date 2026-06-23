# Team Router Entry Flow Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task and superpowers:verification-before-completion before reporting completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the ambiguous parent-thread entry instructions that can cause duplicate manager/executor/verifier role threads, while preserving the live Codex thread-tool order and user-output contract.

**Architecture:** Keep `src/team_router.py` as the deterministic state machine and adapter helper layer. Fix only the public entry documentation and tests so parent orchestrators choose exactly one role-thread creation path: adapter-created roles via `start_team_task_with_adapter()` or pre-created roles via `create_team_task()`/registry helpers.

**Tech Stack:** Python standard library, `unittest`, Markdown skill/runbook docs, existing Codex desktop thread-tool adapter boundary.

---

### Task 1: Entry Flow Contract Tests

**Files:**
- Modify: `tests/test_team_router.py`

- [x] Add a failing test that `skills/codex-team-router/SKILL.md` separates `Adapter-created roles path` from `Pre-created roles path`.
- [x] Add a failing test that `docs/runbooks/codex-team-router-live-orchestration.md` separates the same two paths.
- [x] Assert the adapter-created path uses `start_team_task_with_adapter()` and warns not to pre-call `create_thread`.
- [x] Assert the pre-created path uses `create_team_task()` and warns not to call `start_team_task_with_adapter()` after manually creating role threads.
- [x] Run `py -m unittest discover -s tests -p test_team_router.py` and confirm the tests fail before the docs change.

### Task 2: Skill And Runbook Update

**Files:**
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`

- [x] Update the skill entry flow to say each task must use exactly one role-thread creation path.
- [x] Document `Adapter-created roles path`: host provides adapter callables, call `start_team_task_with_adapter()`, and do not pre-call `create_thread`.
- [x] Document `Pre-created roles path`: parent manually calls `create_thread` for missing roles, builds the roles mapping, persists with `create_team_task()` or lower-level registry helpers, and does not call `start_team_task_with_adapter()`.
- [x] Preserve the live order string `list_projects -> create_thread -> send_message_to_thread -> read_thread`.
- [x] Preserve the final parent-thread rule to emit `update["userOutput"]`.

### Task 3: Verification And Commit

**Files:**
- Modify: this plan file

- [x] Run `py -m unittest discover -s tests -p test_team_router.py`.
- [x] Run `py -m py_compile src\team_router.py tests\test_team_router.py`.
- [x] Run `git diff --check`.
- [x] Run full `py -m unittest discover -s tests`.
- [x] Commit the focused entry-flow fix.
