# Team Router Role Communication Economy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested Team Router contract that keeps executor/reviewer/verifier accuracy gates while reducing role-thread chat volume.

**Architecture:** Extend the existing `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY` instead of adding a separate runtime path. Document the rule in the short skill entrypoint and the detailed handoff/review-package reference, then lock it with `tests/test_team_router.py`.

**Tech Stack:** Python standard library, `unittest`, Markdown contract docs.

---

### Task 1: Contract Test

**Files:**
- Modify: `tests/test_team_router.py`

- [x] **Step 1: Write the failing test**

Add `test_role_communication_economy_policy_keeps_gates_but_limits_chat` under `TestTeamRouterSkillDoc`. The test reads `team_router.protocol_contract_snapshot()` and `_skill_contract_text()`, then asserts the new `roleCommunicationEconomy` policy preserves gates, uses stable path references, requires delta-only follow-up, and documents token budget hints.

- [x] **Step 2: Run test to verify it fails**

Run: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_role_communication_economy_policy_keeps_gates_but_limits_chat`

Expected: failure with `KeyError: 'roleCommunicationEconomy'`.

### Task 2: Policy And Docs

**Files:**
- Modify: `src/team_router.py`
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `skills/codex-team-router/references/role-handoff-and-review-package.md`

- [x] **Step 1: Add minimal policy snapshot field**

Add `roleCommunicationEconomy` under `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY` with `accuracyBoundary`, `defaultMode`, `protocolBlockPolicy`, `followUpPolicy`, `longContextPolicy`, `managerCloseoutPolicy`, and `budgetHintsTokens`.

- [x] **Step 2: Document short entrypoint rule**

Add one compact `Role Communication Economy` paragraph to `skills/codex-team-router/SKILL.md` without exceeding the entrypoint byte cap.

- [x] **Step 3: Document detailed reference rule**

Add a `## Role Communication Economy` section to `skills/codex-team-router/references/role-handoff-and-review-package.md`.

- [x] **Step 4: Run focused test to verify it passes**

Run: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_role_communication_economy_policy_keeps_gates_but_limits_chat`

Expected: `Ran 1 test` and `OK`.

### Task 3: Verification And Closeout

**Files:**
- Create: `docs/team-router/packages/ctr-20260628-role-communication-economy.md`
- Modify: `docs/compounding.md`

- [x] **Step 1: Record package evidence**

Create a package with task summary, scope, touched files, behavior changes, diff summary, verification, risks, and remaining todos.

- [x] **Step 2: Record durable lesson**

Add a compounding entry describing that role-thread token savings must come from protocol/path discipline, not from removing gates.

- [x] **Step 3: Run verification**

Run focused docs suite and full Team Router suite:

`py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`

`py -m unittest tests.test_team_router`

- [ ] **Step 4: Commit accepted files**

Check `git status -sb --untracked-files=all` and related diff summary, stage only this task's files, and commit after verification passes.
