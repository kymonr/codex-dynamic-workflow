# Role Thread Handoff Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Team Router reviewer/verifier request prompts path-first and delta-only so role threads do not receive long inline callback/review/evidence context when `reviewPackagePath` or related package paths are present.

**Architecture:** Keep role-thread protocol and direct-return semantics unchanged. Add prompt-construction tests first, then adjust `make_reviewer_request_message()` and `make_verifier_request_message()` so package-path handoff omits raw callback/review bodies and emits compact path-based instructions.

**Tech Stack:** Python standard library, `unittest`, Team Router facade in `src/team_router.py`.

## Global Constraints

- Default Chinese output; commands, paths, filenames, protocol markers, and API names remain literal.
- Do not change parser, gate policy, direct-return validation, watcher cadence, host runtime, thread adapter behavior, live adapter, production scheduler/daemon, PR, merge, deploy, publish/release, or global skill sync.
- Preserve reviewer -> verifier gates for Team Router self-changes.
- Use TDD: write failing tests before production code.
- Keep public runtime imports routed through `src/team_router.py`.
- `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` are evidence metadata only; runtime must not read, execute, trust, or auto-generate them.

---

### Task 1: Compress Reviewer And Verifier Role Request Prompts

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`
- Create: `docs/team-router/packages/ctr-20260701-role-thread-handoff-compression.md`
- Modify: `docs/workbench.md`
- Modify: `docs/team-router/module-map.md` only if tests require module-map visibility for the prompt contract

**Interfaces:**
- Consumes: `make_reviewer_request_message(task_id, callback_block, permission, scope, ..., plan_fields, review_package)`
- Consumes: `make_verifier_request_message(task_id, callback_block, permission, scope, ..., plan_fields, review_package, reviewer_result)`
- Produces: reviewer/verifier prompt strings that include path metadata and compact summaries but omit long raw callback/reviewer bodies when package paths are present.

- [x] **Step 1: Write failing reviewer prompt compression test**

Add a focused test in `TestTeamRouterProtocol` that calls `make_reviewer_request_message()` with:
- a multi-line `TEAM_ROUTER_CALLBACK` containing long `evidence`
- `plan_fields` containing `taskBriefPath`, `executorReportPath`, and `reviewPackagePath`
- matching `review_package.paths.reviewPackagePath`

Expected assertions:
- prompt contains `reviewPackagePath: docs/team-router/packages/ctr-20260701-role-thread-handoff-compression.md`
- prompt contains `callbackRawLocation: executorReportPath 或 reviewPackagePath`
- prompt does not contain the raw long evidence body
- prompt length is below a conservative cap such as 2200 characters

Run:
`PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback -v`

Expected: FAIL because current prompt still includes callback summary fields or raw details too generously for path-first role handoff.

- [x] **Step 2: Write failing verifier prompt compression test**

Add a focused test in `TestTeamRouterProtocol` that calls `make_verifier_request_message()` with:
- the same multi-line callback
- a reviewer result containing `raw` long text plus structured pass fields
- `plan_fields` and `review_package` containing path metadata

Expected assertions:
- prompt contains `reviewPackagePath: docs/team-router/packages/ctr-20260701-role-thread-handoff-compression.md`
- prompt contains compact reviewer fields such as `result: pass` and `requiredChanges: none`
- prompt does not contain raw reviewer text
- prompt does not contain raw callback evidence body
- prompt length is below a conservative cap such as 2600 characters

Run:
`PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback -v`

Expected: FAIL before implementation.

- [x] **Step 3: Implement minimal prompt compression**

Change only prompt-construction helpers in `src/team_router.py`:
- In path-handoff mode, make `_callback_context_prompt_lines(..., compact=True)` avoid copying callback field values. It should emit only a short instruction plus `callbackRawLocation: executorReportPath 或 reviewPackagePath` and optional tiny status if safe.
- Keep non-path behavior unchanged.
- Keep `_reviewer_result_prompt_lines(..., compact=True)` structured-summary behavior, but continue omitting raw reviewer text.
- Do not touch parser/gate/direct-return/watcher/host/status transitions.

- [x] **Step 4: Verify focused tests pass**

Run:
`PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback -v`

Expected: both tests PASS.

- [x] **Step 5: Update package/workbench documentation**

Create `docs/team-router/packages/ctr-20260701-role-thread-handoff-compression.md` with:
- objective
- boundary
- TDD RED/GREEN evidence
- reviewer/verifier gates pending
- no commit/push/global sync authorization

Update `docs/workbench.md` current task to active package `ctr-20260701-role-thread-handoff-compression` and current next gate reviewer then verifier.

- [x] **Step 6: Run verification**

Run:
`PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m py_compile src\team_router.py tests\test_team_router.py`

Run:
`PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B -m unittest discover -s tests -p test_team_router.py -q`

Run:
`PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache py -B scripts\team_router_truth_check.py --json`

Run:
`git diff --check`

Expected: compile OK, full suite OK, `staleClaims: []`, diff check exit 0 except existing CRLF/LF warnings.

- [x] **Step 7: Gate handoff**

After local verification, send the package to Team Router reviewer, then verifier if reviewer passes. Commit/push/global sync remain separate closeout authorization gates.

Reviewer v2 passed in thread `019f1984-0ec5-7f41-84d4-64104e03ef36`; verifier passed in thread `019f1988-013c-7f43-8bc3-13a1c6b77988`. Commit/push/global sync remain separate closeout authorization gates.

## Self-Review

- Spec coverage: plan covers the screenshot-observed issue for reviewer, reviewer recheck, and verifier role threads by changing prompt construction rather than only documenting a preference.
- Placeholder scan: no TBD/TODO/fill-in placeholders remain.
- Type consistency: function names and test names match existing `src/team_router.py` and `tests/test_team_router.py` patterns.