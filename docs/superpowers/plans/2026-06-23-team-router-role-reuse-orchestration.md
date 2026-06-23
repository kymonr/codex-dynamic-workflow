# Team Router Role Reuse And Parent Orchestration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task and superpowers:verification-before-completion before reporting completion. Use gstack/Claude only for read-only review and verification unless the user grants a wider publish package.

**Goal:** Make Team Router safe to run repeatedly from a parent thread by reusing existing manager/executor/verifier role bindings, creating only missing role threads, and defining the next one-call parent orchestration entry around the existing Codex thread-tool adapter boundary.

**Architecture:** Keep `src/team_router.py` as a deterministic Python state machine. Codex desktop tools stay outside the core module and enter only through adapter callables. Registry JSON remains the project-level source of truth for role thread bindings; task ledgers remain the per-task source of truth for anchors, dispatches, observations, verifier state, closeout, and handoff text.

**Tech Stack:** Python standard library, `unittest`, JSON registry/ledger files under `.codex-team-router`, Codex desktop thread tools exposed as adapter callables, Markdown skill/runbook docs.

---

### Task 1: Existing Role Binding Guard

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`

- [x] Add a failing test where registry already has all three role bindings and `start_team_task_with_adapter()` creates no new threads.
- [x] Add a failing test where registry has one role binding and `start_team_task_with_adapter()` creates only the missing roles.
- [x] Implement registry-first role resolution for `start_team_task_with_adapter()`.
- [x] Preserve `create_role_threads_with_adapter()` as the explicit create-all helper for callers that need fresh role records.

### Task 2: Parent Orchestration Entry

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`

- [x] Add a one-call parent orchestration helper that starts or resumes the next required manager/executor/verifier step with adapter callables.
- [x] Make the helper return structured action/status plus `userOutput` when a closeout or handoff is ready.
- [x] Preserve the existing lower-level `send_*_with_adapter()`, `read_*_with_adapter()`, `record_*`, and `capture_*` helpers.
- [x] Update docs so parent users have one recommended entry and lower-level recovery paths.

### Task 3: Live Role Discovery And Reuse

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`

- [x] Add adapter capability probes for `list_projects`, `list_threads`, and `set_thread_title`.
- [x] Discover current project target from `list_projects` before creating or reusing live role threads.
- [x] Search existing live threads by role title before creating missing role threads.
- [x] Use `set_thread_title` to normalize reused or newly created role titles.
- [x] Avoid automatic binding when multiple live thread candidates match the same role.

### Task 4: Manual/Pre-Created Smoke

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`

- [x] Add a manual/pre-created end-to-end smoke that uses direct `send_message_to_thread`/`read_thread` adapter calls plus `record_*`/`capture_*` helpers.
- [x] Assert the manual smoke does not call `_with_adapter()` continuation helpers.
- [x] Assert multiline protocol fields keep their newlines through the manual smoke.

### Task 5: Verification And Review

**Files:**
- Modify: this plan file

- [x] Run focused `py -m unittest discover -s tests -p test_team_router.py`.
- [x] Run `py -m py_compile src\team_router.py tests\test_team_router.py`.
- [x] Run `git diff --check`.
- [x] Run full `py -m unittest discover -s tests`.
- [x] Run Claude read-only review/verify on the patch.
- [x] Fix confirmed review findings or document why they are not taken.
- [x] Commit the focused implementation patch.
