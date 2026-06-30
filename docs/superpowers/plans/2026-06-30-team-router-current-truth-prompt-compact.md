# Team Router Current Truth Prompt Compact Implementation Plan

**Goal:** Keep Team Router current-state evidence aligned with the latest accepted package/module state, and ensure downstream role prompts use compact path handoff instead of copying long callback/review bodies.

**Architecture:** Keep `src/team_router.py` as the public facade while making prompt-template compaction local to role request generation. Keep `scripts/team_router_truth_check.py` read-only and section-scoped, but add a narrow check for workbench current-state lag against module-map/package evidence. Host adapter/scheduler and watcher/status extraction remain separate gates unless this package can change them without needing an external host runtime.

**Tech Stack:** Python stdlib, `unittest`, Team Router local docs/scripts.

### Task 1: Current-Truth Regression

- [x] Add a failing test for workbench current package lag and completed module extraction phase references.
- [x] Implement narrow stale detection for current-state sections only.
- [x] Refresh `docs/workbench.md` current task and expected docs tests.

### Task 2: Downstream Prompt Compact Handoff

- [x] Add a failing test proving reviewer, verifier, and QA prompts omit long callback/review payloads when package paths exist.
- [x] Add compact callback/reviewer-result helpers in `src/team_router.py`.
- [x] Preserve inline fallback behavior when no path handoff exists.

### Task 3: Host And Extraction Boundary

- [x] Record `team_router_doctor.py --json` host/readiness status.
- [x] Keep host adapter/scheduler and watcher/status extraction as separate explicit gates unless the current repo exposes a callable host integration point.

### Task 4: Verification And Closeout

- [x] Run focused tests.
- [x] Run full `tests/test_team_router.py` suite.
- [x] Run truth/doctor/closeout checks and `git diff --check`.
- [ ] Commit only this package's accepted files after successful verification.
