# Team Router Optimization 1-6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for runtime behavior and superpowers:verification-before-completion before callback. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement optimization items 1-6 for Team Router without commit, push, PR, merge, deploy, or global skill sync.

**Architecture:** Keep `SKILL.md` as a short entrypoint and move deep rules into references. Add deterministic helper contracts in `src/team_router.py` for gate explanations and live orchestration readiness, and keep closeout checking as a read-only script. Update docs and tests so current state comes from fresh git/status checks rather than historical package records.

**Tech Stack:** Python standard library, `unittest`, Markdown docs, PowerShell command execution.

---

## Files

- Modify: `skills/codex-team-router/SKILL.md` for entrypoint slimming under 7200 bytes while preserving hard entry rules and current description semantics.
- Modify: `skills/codex-team-router/references/adapter-runtime.md` for host adapter, parent thread id, title tool, and heartbeat scheduler readiness contract.
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md` for the 7200 byte target, readiness contract tests, malformed direct-return tests, gate reason tests, and closeout check.
- Modify: `src/team_router.py` for pure helper additions and minimal malformed direct-return telemetry refinement if tests expose a gap.
- Modify: `tests/test_team_router.py` for RED/GREEN coverage.
- Create: `scripts/team_router_closeout_check.py` as a read-only reporting script.
- Modify: `docs/workbench.md` for active package state and current truth boundaries.
- Modify: `README.md` only if needed to point at readiness/closeout helpers.
- Create: `docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md` as the review package after implementation.
- Do not modify: `C:\Users\Orz\.codex\skills\codex-team-router`, commit history, remotes, PRs, deploy targets, or release state.

## Parallelism

The six items overlap in `SKILL.md`, references, runtime helper tests, and closeout docs. Actual writes must be single-executor serial. Tool-level read-only inspection and independent verification commands may be parallelized only when they do not write or race.

## Tasks

### Task 1: Write RED Tests For Runtime Helpers

**Files:**
- Modify: `tests/test_team_router.py`

- [ ] Add tests asserting `explain_team_router_gate(ledger)` returns a dict with `gateClass` and readable `reasons` for local-package, explicit package term, reviewer-required term, fast docs term, and normal fallback.
- [ ] Add tests asserting `assess_live_orchestration_readiness(...)` reports blocked reasons for missing callable adapter tools, missing `parent_thread_id`, missing callable `set_thread_title`, and missing heartbeat scheduler when live orchestration is requested.
- [ ] Add tests asserting malformed direct-return capture records wrong or missing `sourceThreadId`, `role`, and `sourceRoleThreadId`, keeps fallback recovery, and does not advance the ledger.
- [ ] Add tests asserting `SKILL.md` remains below 7200 bytes and required references carry moved contract phrases.
- [ ] Run focused RED command:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState -v
```

Expected before implementation: new helper imports/tests fail because helpers or fields are missing.

### Task 2: Implement Runtime Helper Contracts

**Files:**
- Modify: `src/team_router.py`

- [ ] Implement `explain_team_router_gate(ledger)` as a pure helper preserving `classify_team_router_gate(ledger)` compatibility.
- [ ] Implement `assess_live_orchestration_readiness(...)` as a pure helper that does not call Codex app tools and does not fabricate host capabilities.
- [ ] Update `_record_malformed_direct_return` only if RED tests show missing telemetry fields are needed for recovery diagnostics.
- [ ] Run focused GREEN command:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState -v
```

Expected after implementation: focused tests pass.

### Task 3: Slim Skill Entrypoint And Move Detail To References

**Files:**
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `skills/codex-team-router/references/adapter-runtime.md`
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md`

- [ ] Compress `SKILL.md` to hard rules, role summary, minimal live order, direct return anchor, Fast Lane rule, closeout anchor, side-effect taxonomy, and references.
- [ ] Preserve description semantics and hard rules: Manager Mode explicit trigger, sticky dispatch-only terse follow-ups, archived role no reuse, visible role threads, `parent_thread_id` plus `set_thread_title`, direct-send plus fallback, reviewer gate, verifier final acceptance, and no commit/push/release/global sync without authorization.
- [ ] Move deep live readiness and testing details into references.
- [ ] Run size check:

```powershell
(Get-Item skills\codex-team-router\SKILL.md).Length
```

Expected: less than 7200.

### Task 4: Add Read-Only Closeout Check

**Files:**
- Create: `scripts/team_router_closeout_check.py`
- Modify: `tests/test_team_router.py`

- [ ] Add tests for a read-only report shape covering git status, diff files, `SKILL.md` 8KB cap and 7200 target, repo/global sync status, and unauthorized commit/push/global sync warnings.
- [ ] Implement the script with subprocess reads only; it must not sync, stage, commit, push, or mutate files.
- [ ] Run focused command:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState -v
```

Expected: closeout helper tests pass.

### Task 5: Update Workbench And Package State

**Files:**
- Modify: `docs/workbench.md`
- Modify: `README.md` if runtime helper discoverability needs a root pointer.
- Create: `docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md`

- [ ] Update `docs/workbench.md` to mark `ctr-20260628-team-router-optimization-1-6` as active during this package, with current dirty truth sourced from fresh git checks.
- [ ] Keep older package records under historical records only.
- [ ] Write the review package with objective, scope, changed files, diff summary, tests, not done, risks, global sync status, and commit/push status.

### Task 6: Full Verification And Callback Evidence

**Files:**
- No new implementation files beyond above.

- [ ] Run compile:

```powershell
py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py
```

- [ ] Run focused and full tests:

```powershell
py -B -m unittest tests.test_team_router
```

- [ ] Run whitespace check:

```powershell
git diff --check
```

- [ ] Run repo/global skill drift check:

```powershell
py -B scripts\team_router_skill_sync_check.py --check
```

If repo skill changed but global sync is unauthorized, `status: mismatch` is an expected pending gate, not an implementation failure.

- [ ] Run read-only closeout check:

```powershell
py -B scripts\team_router_closeout_check.py
```

- [ ] Return only `TEAM_ROUTER_CALLBACK` with required fields and no commit/push/PR/merge/deploy/global sync.
