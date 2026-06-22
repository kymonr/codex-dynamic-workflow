# Team Router Registry Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a local JSON state layer for `codex-team-router` registry and task ledger files.

**Architecture:** Keep the MVP state helpers in `src/team_router.py` beside the existing protocol/path helpers. The layer stays deterministic and local: no thread tools, no daemon, no network. Public helpers normalize compatible old JSON shapes, raise a dedicated state error for bad files, and write atomically to the existing `registry_path()` and `task_path()` locations.

**Tech Stack:** Python standard library (`json`, `os.replace`, `Path`), `unittest`, existing `tests/test_team_router.py`.

---

### Task 1: Regression Tests For JSON State Layer

**Files:**
- Modify: `tests/test_team_router.py`

- [x] **Step 1: Write failing tests**

Add tests covering:

```python
class TestTeamRouterJsonState(unittest.TestCase):
    def test_registry_round_trip_normalizes_missing_fields(self): ...
    def test_task_ledger_round_trip_normalizes_missing_fields(self): ...
    def test_bad_registry_json_raises_state_store_error(self): ...
    def test_atomic_save_leaves_no_temp_file(self): ...
    def test_two_worktrees_share_registry_via_canonical_root(self): ...
```

- [x] **Step 2: Run tests to verify failure**

Run: `py -m unittest discover -s tests -p test_team_router.py`

Expected: FAIL because `StateStoreError`, `load_registry`, `save_registry`, `new_task_ledger`, `load_task_ledger`, and `save_task_ledger` do not exist yet.

### Task 2: Implement Registry And Ledger Helpers

**Files:**
- Modify: `src/team_router.py`

- [x] **Step 1: Add state error and JSON helpers**

Add `StateStoreError`, `_resolve_persistent_state_root()`, `_read_json_object()`, and `_atomic_write_json()`; reject durable state roots under `.codex-tmp`.

- [x] **Step 2: Add registry normalization and persistence**

Add `load_registry(state_root, project_id)` and `save_registry(state_root, project_id, registry)` using `registry_path()`.

- [x] **Step 3: Add task ledger construction, normalization, and persistence**

Add `new_task_ledger(...)`, `load_task_ledger(...)`, and `save_task_ledger(...)` using `task_path()`.

- [x] **Step 4: Run targeted tests**

Run: `py -m unittest discover -s tests -p test_team_router.py`

Expected: PASS.

### Task 3: Verification And gstack Review Pass

**Files:**
- Review: `src/team_router.py`, `tests/test_team_router.py`, `docs/superpowers/plans/2026-06-22-team-router-registry-ledger.md`

- [x] **Step 1: Run syntax and diff checks**

Run:

```text
py -m py_compile src\team_router.py tests\test_team_router.py
git diff --check
```

Expected: exit 0.

- [x] **Step 2: Run full tests**

Run: `py -m unittest discover -s tests`

Expected: all tests pass.

- [x] **Step 3: gstack-style pre-landing review**

Review the diff for JSON safety, path/state-root correctness, atomic-write cleanup, compatibility defaults, and test coverage gaps. Fix any concrete issue before commit.

- [x] **Step 4: Commit**

Run:

```text
git add docs/superpowers/plans/2026-06-22-team-router-registry-ledger.md src/team_router.py tests/test_team_router.py
git commit -m "feat: add team router JSON state store"
```