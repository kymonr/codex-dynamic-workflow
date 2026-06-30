# Team Router Phase 2b3 Host Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Team Router pure host-readiness and live-host-context helpers into `src/team_router_host_runtime.py` while keeping watcher, capture, state-save, and orchestration side effects in `src/team_router.py`.

**Architecture:** `team_router.py` remains the public facade and compatibility import surface. `team_router_host_runtime.py` owns only callable host contract checks, heartbeat scheduler callable normalization, readiness snapshots, and the immutable `LiveOrchestrationHostContext`. Watcher runtime stays local because it reads threads, mutates ledgers, captures direct-return messages, sends next role requests, and schedules heartbeat callbacks.

**Tech Stack:** Python standard library, `unittest`, existing Team Router modules under `src/`.

## Global Constraints

- Manager mode implementation boundary: no push, PR, deploy, release, global skill sync, or external state changes in phase 2b3.
- No behavior change: public calls continue through `src/team_router.py`.
- No watcher extraction: keep `_watcher_ledger()`, `_watch_next_wakeup()`, `_watcher_read_allowed()`, `_schedule_watcher_heartbeat()`, `_attach_watcher_heartbeat_schedule()`, `_refresh_watcher_ledger()`, and `watch_team_task_with_adapter()` in `team_router.py`.
- No capture/state-save extraction: keep direct-return capture, malformed direct-return ledger mutation, registry/ledger persistence, and role send/read orchestration in `team_router.py`.
- New module must not import `team_router.py`.
- Use Windows-safe verification when needed: set `PYTHONPYCACHEPREFIX`, `TMP`, and `TEMP` under `C:\tmp`.

---

## File Structure

- Create `src/team_router_host_runtime.py`: pure host runtime contract helpers.
- Modify `src/team_router.py`: import/re-export host runtime symbols; keep `parent_entry_guard()` and watcher/orchestration functions local.
- Modify `tests/test_team_router.py`: add focused facade/module extraction coverage and keep existing readiness/host-context behavior tests.
- Modify `docs/team-router/module-map.md`: mark host runtime extraction implemented and leave watcher runtime as future/deferred.

## Task 1: Lock Host Runtime Facade Contract

**Files:**
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: current facade symbols in `team_router.py`.
- Produces: a regression test proving the facade re-exports host runtime helpers from `team_router_host_runtime`.

- [ ] **Step 1: Add a focused re-export test**

Add a test near the existing facade/module extraction tests:

```python
    def test_facade_reexports_host_runtime_symbols(self):
        import team_router_host_runtime

        names = (
            "THREAD_TOOL_NAMES",
            "LiveOrchestrationHostContext",
            "probe_thread_adapter_capabilities",
            "_heartbeat_scheduler_call",
            "assess_live_orchestration_readiness",
            "make_live_orchestration_host_context",
            "_raise_if_host_context_conflict",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIs(getattr(team_router, name), getattr(team_router_host_runtime, name))
```

- [ ] **Step 2: Run the focused test and confirm it fails before implementation**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_facade_reexports_host_runtime_symbols -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'team_router_host_runtime'` or missing facade re-export.

## Task 2: Extract Pure Host Runtime Helpers

**Files:**
- Create: `src/team_router_host_runtime.py`
- Modify: `src/team_router.py`

**Interfaces:**
- Consumes: `team_router_runtime._adapter_method`, `team_router_state.StateStoreError`.
- Produces:
  - `THREAD_TOOL_NAMES: tuple[str, ...]`
  - `probe_thread_adapter_capabilities(thread_adapter, required_tools=THREAD_TOOL_NAMES) -> dict[str, bool]`
  - `_is_callable_heartbeat_scheduler(heartbeat_scheduler) -> bool`
  - `_heartbeat_scheduler_call(heartbeat_scheduler) -> Any`
  - `assess_live_orchestration_readiness(thread_adapter, *, parent_thread_id, heartbeat_scheduler, required_tools=THREAD_TOOL_NAMES) -> dict[str, Any]`
  - `LiveOrchestrationHostContext`
  - `make_live_orchestration_host_context(...) -> LiveOrchestrationHostContext`
  - `_raise_if_host_context_conflict(name, explicit_value, context_value) -> None`

- [ ] **Step 1: Create `src/team_router_host_runtime.py`**

Move the current helper bodies from `team_router.py` unchanged except for imports:

```python
# -*- coding: utf-8 -*-
"""Host readiness and live orchestration context helpers for Team Router."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from team_router_runtime import _adapter_method
from team_router_state import StateStoreError


THREAD_TOOL_NAMES = (
    "list_projects",
    "create_thread",
    "list_threads",
    "read_thread",
    "send_message_to_thread",
    "set_thread_title",
)
```

Then include the exact current implementations of the produced helpers listed above.

- [ ] **Step 2: Update `src/team_router.py` imports**

Remove `dataclass` from the top-level import if no longer used:

```python
from datetime import datetime, timedelta, timezone
```

Import host runtime symbols:

```python
from team_router_host_runtime import (
    THREAD_TOOL_NAMES,
    LiveOrchestrationHostContext,
    _heartbeat_scheduler_call,
    _raise_if_host_context_conflict,
    assess_live_orchestration_readiness,
    make_live_orchestration_host_context,
    probe_thread_adapter_capabilities,
)
```

- [ ] **Step 3: Remove moved definitions from `src/team_router.py`**

Delete local definitions for `THREAD_TOOL_NAMES`, `probe_thread_adapter_capabilities()`, `_is_callable_heartbeat_scheduler()`, `_heartbeat_scheduler_call()`, `assess_live_orchestration_readiness()`, `LiveOrchestrationHostContext`, `make_live_orchestration_host_context()`, and `_raise_if_host_context_conflict()`.

Do not move `parent_entry_guard()`. It stays local because it calls `_has_complete_precreated_roles()` and selects between adapter-created and manual-precreated role binding paths.

- [ ] **Step 4: Run host focused behavior tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_facade_reexports_host_runtime_symbols tests.test_team_router.TestTeamRouterProtocol.test_live_orchestration_readiness_reports_missing_host_contracts tests.test_team_router.TestTeamRouterProtocol.test_parent_entry_guard_accepts_full_callable_adapter_path tests.test_team_router.TestTeamRouterProtocol.test_parent_entry_guard_blocks_non_callable_heartbeat_scheduler tests.test_team_router.TestTeamRouterProtocol.test_orchestrate_team_task_accepts_live_host_context tests.test_team_router.TestTeamRouterProtocol.test_live_host_context_blocks_missing_parent_thread_id_without_side_effects tests.test_team_router.TestTeamRouterProtocol.test_live_host_context_blocks_non_callable_scheduler_without_side_effects tests.test_team_router.TestTeamRouterProtocol.test_orchestrate_team_task_rejects_host_context_conflicts_before_side_effects -v
```

Expected: all selected tests pass.

## Task 3: Update Module Map And Full Verification

**Files:**
- Modify: `docs/team-router/module-map.md`
- Modify if needed: `tests/test_team_router.py`

**Interfaces:**
- Consumes: phase 2b3 extraction boundary.
- Produces: module-map text with no conflict between implemented and future modules.

- [ ] **Step 1: Update module-map current domains**

Change the adapter/runtime bullets so they state:

```markdown
- host runtime: `src/team_router_host_runtime.py` owns host readiness, callable heartbeat scheduler validation, live orchestration context creation, and host-context conflict checks. `src/team_router.py` still owns parent entry path selection, watcher timing, heartbeat scheduling, and public compatibility imports.
- watcher/heartbeat: still local to `src/team_router.py`; enforce first-check and 300 second read discipline, heartbeat scheduling, timeout/control boundaries, and `watch_team_task_with_adapter()` continuation behavior.
```

- [ ] **Step 2: Update module table**

Add `team_router_host_runtime.py` to implemented modules and remove it from deferred future modules. Leave future watcher extraction explicit:

```markdown
| `team_router_host_runtime.py` | host readiness, heartbeat scheduler callable validation, live orchestration context, and host-context conflict checks | `team_router_runtime`, `team_router_state`, standard library | must not import `team_router` |
```

Future module row:

```markdown
| `team_router_watcher_runtime.py` | watcher timing, heartbeat scheduling, and watch continuation policy | watcher, heartbeat, read discipline tests | no ledger mutation or live dispatch claim moves without explicit watcher-runtime package |
```

- [ ] **Step 3: Update extraction order text**

Change the remaining safe extraction order from:

```markdown
host readiness/watcher runtime -> status/closeout
```

to:

```markdown
watcher runtime -> status/closeout
```

- [ ] **Step 4: Run py_compile**

Run:

```powershell
py -m py_compile src\team_router.py src\team_router_host_runtime.py
```

Expected: no output and exit 0.

- [ ] **Step 5: Run focused host runtime tests**

Run the focused command from Task 2 Step 4 again.

Expected: all selected tests pass.

- [ ] **Step 6: Run full Team Router test file**

Run:

```powershell
py -B -m unittest discover -s tests -p test_team_router.py -v
```

Expected: full `test_team_router.py` passes.

- [ ] **Step 7: Review diff boundary**

Run:

```powershell
git diff --name-only
git diff --check
```

Expected changed files only:

```text
docs/team-router/module-map.md
docs/superpowers/plans/2026-06-30-team-router-phase-2b3-host-runtime.md
src/team_router.py
src/team_router_host_runtime.py
tests/test_team_router.py
```

`git diff --check` exits 0.

## Review And Commit Gates

- [ ] **Review gate:** confirm `team_router_host_runtime.py` has no ledger mutation, state save, capture, watcher read, thread send/read, or heartbeat scheduling responsibility.
- [ ] **Verifier gate:** confirm focused tests and full `test_team_router.py` passed after implementation.
- [ ] **Local commit gate:** if verifier accepts, run `git status -s`, stage only phase 2b3 files, and commit locally.
- [ ] **Publish gate:** do not push until separately authorized.

