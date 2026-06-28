# Team Router Trust And Modularity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` and `superpowers:test-driven-development` task-by-task. In active Team Router Manager Mode, implementation must run through one visible Executor, then read-only Reviewer, then read-only Verifier. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Team Router's current-state docs and package records machine-checkable, document a safe future module split, and add a plain manager-facing router status surface without changing live dispatch behavior.

**Architecture:** Keep `protocol_contract_snapshot()` as the role/policy contract center. Add read-only truth/status helpers before changing docs, then update workbench/package records from fresh git/skill evidence. Module work in this package is documentation only; runtime extraction is deferred to a later explicit refactor package.

**Tech Stack:** Python standard library, `unittest`, Markdown docs, PowerShell verification commands.

## Global Constraints

- Manager Mode is orchestration-only; manager direct edits are allowed in this turn only because the user explicitly authorized saving the plan and entering the local executor implementation package.
- No commit, push, PR, merge, deploy, release, publish, or global skill sync in this package.
- Write work is serialized through one Executor chain. Reviewer and Verifier are read-only gates. Do not use parallel writer roles.
- Tool-level read-only checks may run in parallel when they do not write or race.
- `skills/codex-team-router/SKILL.md` must stay under the 7200 byte target and 8192 byte hard cap.
- Current truth must come from `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `scripts/team_router_closeout_check.py --json`, and the new truth checker.
- Reviewer pre-save attempt note: original reviewer thread `019f0e79-746a-7bb2-b509-7ca9f74a7bf2` and replacement reviewer thread `019f0e7b-5c1c-7b22-b6fe-32be6bc8b5c2` did not return a final `TEAM_ROUTER_REVIEW` after bounded read/control. Treat this as reviewer-unreachable evidence, not reviewer acceptance. A post-implementation reviewer gate remains required.

---

## Files

- Create: `scripts/team_router_truth_check.py` - read-only current-state and stale-claim checker.
- Create: `scripts/team_router_doctor.py` - read-only manager-facing status summary.
- Modify: `tests/test_team_router.py` - TDD coverage for truth check, stale workbench/package docs, module map, and doctor output.
- Modify: `docs/workbench.md` - replace stale active-dirty state with current truth and historical package boundaries.
- Modify: `docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md` - mark old dirty/sync claims historical and record current clean/synced status.
- Create: `docs/team-router/module-map.md` - documentation-only module split plan and extraction order.
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md` - document new read-only evidence tools and gates.
- Do not modify unless tests force a pointer update: `README.md`.
- Do not modify: `skills/codex-team-router/SKILL.md` unless a size/contract test requires wording.

---

### Task 1: P0 Current Truth Checker

**Interfaces:**
- Produces: `build_truth_report(repo_root: Path, global_skill: Path | None = None) -> dict[str, object]`
- Produces: `find_stale_state_claims(report: Mapping[str, object], text_by_path: Mapping[str, str]) -> list[dict[str, str]]`
- CLI: `py -B scripts\team_router_truth_check.py --json`

- [ ] Add failing tests in `tests/test_team_router.py`.
  - Assert the report contains `gitStatusBranch`, `gitStatusShort`, `diffFiles`, `skillSync`, `staleClaims`, `authorization`, and `readOnlyGuarantee`.
  - Assert stale text containing five current dirty files is reported when `gitStatusShort` and `diffFiles` are empty.
  - Assert stale text containing `skillSync.status: mismatch` is reported when skill sync is `match`.
  - Assert the script does not write to repo/global skill paths.
- [ ] Run RED:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterState -v`
  - Expected: fails because `scripts/team_router_truth_check.py` and its report fields do not exist.
- [ ] Implement `scripts/team_router_truth_check.py` as read-only.
  - Reuse the same git and skill comparison semantics as `scripts/team_router_closeout_check.py`.
  - Do not stage, commit, push, sync, or edit docs.
  - Default stale scan paths: `docs/workbench.md` and `docs/team-router/packages/*.md`.
- [ ] Run GREEN:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterState -v`
  - Expected: focused tests pass.

### Task 2: P0 Workbench And Package Current Truth

**Interfaces:**
- Consumes: `build_truth_report(...)`
- Produces: current docs that do not claim old dirty files or old skill mismatch as current truth.

- [ ] Update failing docs tests first.
  - `test_workbench_tracks_current_task_without_stale_diff_surface` should expect a clean/synced current state for the completed optimization package.
  - It should still require `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, and truth/closeout check commands as current-truth sources.
  - It should assert old five-file dirty surface strings are absent from current sections.
- [ ] Run RED:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterDocs.test_workbench_tracks_current_task_without_stale_diff_surface -v`
  - Expected: fails against current stale docs.
- [ ] Update `docs/workbench.md`.
  - Current Task: idle or planning `ctr-20260628-trust-modularity` local package, depending on implementation progress.
  - Current Diff Surface: must come from fresh command output, not old package records.
  - Historical Records: keep `ctr-20260628-team-router-optimization-1-6` as completed historical package.
  - Risks: mention no commit/push/PR/merge/deploy/global sync unless later authorized.
- [ ] Update `docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md`.
  - Convert "current expected dirty surface" and "expected mismatch" to historical package evidence.
  - Add a current closeout note that current repo/global skill status is rechecked by the truth checker.
- [ ] Run GREEN:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterDocs.test_workbench_tracks_current_task_without_stale_diff_surface -v`
  - `py -B scripts\team_router_truth_check.py --json`
  - Expected: tests pass and `staleClaims` is empty or only points at intentionally historical sections.

### Task 3: P1 Documentation-Only Module Map

**Interfaces:**
- Produces: `docs/team-router/module-map.md`
- This task must not move code or change runtime imports.

- [ ] Add failing docs test in `tests/test_team_router.py`.
  - Assert module map exists.
  - Assert it names current domains: protocol parsing, policy snapshot, registry/ledger state, adapter runtime, direct return, watcher/heartbeat, closeout/status, docs/skill contract tests.
  - Assert it says "no runtime extraction in this package" and "public imports continue through `src/team_router.py`".
  - Assert extraction order is policy constants, protocol parsing, direct return, state/ledger, adapter runtime.
- [ ] Run RED:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterDocs -v`
  - Expected: fails because module map is missing.
- [ ] Create `docs/team-router/module-map.md`.
  - Keep it decision-oriented, not a passive inventory.
  - Include each proposed future module, responsibility, dependencies, first tests to move, and acceptance gate.
  - Explicitly state that this package only documents the map.
- [ ] Run GREEN:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterDocs -v`

### Task 4: P2 Router Doctor Status UX

**Interfaces:**
- Produces: `build_router_doctor_status(repo_root: Path, adapter_readiness: Mapping[str, object] | None = None) -> dict[str, object]`
- CLI: `py -B scripts\team_router_doctor.py --json`

- [ ] Add failing tests in `tests/test_team_router.py`.
  - Clean/synced repo should report `truthStatus: clean_synced`.
  - Dirty or stale claims should report `truthStatus: dirty_or_stale`.
  - Missing callable adapter readiness should report `orchestrationStatus: manual_only` or `tool_error`.
  - The human summary must include current mode, blocker/next action, unauthorized actions, and no live-dispatch claim unless readiness is explicit.
- [ ] Run RED:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterState -v`
  - Expected: fails because doctor script/helper does not exist.
- [ ] Implement `scripts/team_router_doctor.py`.
  - Import or reuse `team_router_truth_check.py`.
  - Optionally import `src.team_router.assess_live_orchestration_readiness` for caller-supplied readiness facts.
  - Do not create threads, dispatch roles, send messages, or edit files.
  - Output JSON and concise text modes.
- [ ] Run GREEN:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterState -v`
  - `py -B scripts\team_router_doctor.py --json`

### Task 5: Testing And Quality Gate Docs

**Interfaces:**
- Produces updated contract docs for the read-only tools.

- [ ] Add or update docs tests first.
  - Assert `skills/codex-team-router/references/testing-and-quality-gates.md` names `team_router_truth_check.py` and `team_router_doctor.py`.
  - Assert `SKILL.md` remains below 7200 bytes and does not absorb deep truth-check details.
- [ ] Run RED if tests changed:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterDocs -v`
- [ ] Update `skills/codex-team-router/references/testing-and-quality-gates.md`.
  - Document truth checker and doctor as read-only evidence tools.
  - State they must not stage, commit, push, PR, merge, deploy, or sync.
  - State they do not replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`.
- [ ] Run GREEN:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterDocs -v`

### Task 6: Package Review Evidence And Final Verification

**Interfaces:**
- Produces: `docs/team-router/packages/ctr-20260628-trust-and-modularity.md`

- [ ] Create a review package with objective, scope, changed files, tests, reviewer-unreachable note, not done gates, and risks.
- [ ] Run compile:
  - `py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py`
- [ ] Run tests:
  - `py -B -m unittest tests.test_team_router`
- [ ] Run whitespace check:
  - `git diff --check`
- [ ] Run read-only status tools:
  - `py -B scripts\team_router_closeout_check.py --json`
  - `py -B scripts\team_router_truth_check.py --json`
  - `py -B scripts\team_router_doctor.py --json`
- [ ] Confirm not done:
  - no commit
  - no push
  - no PR
  - no merge
  - no deploy
  - no release/publish
  - no global skill sync
- [ ] Request or perform read-only Reviewer gate and Verifier gate. If role tools remain unreachable, record `review_unreachable` / `verifier_unreachable` honestly in closeout and do not claim acceptance.
