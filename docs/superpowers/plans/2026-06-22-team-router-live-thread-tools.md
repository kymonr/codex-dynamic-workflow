# Team Router Live Thread Tools Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement code changes and superpowers:verification-before-completion before reporting completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the codex-team-router adapter flow to the Codex desktop thread-tool boundary, run a real manager/executor/verifier smoke, and expose closeout/handoff output for the parent user thread.

**Architecture:** Keep `src/team_router.py` deterministic and host-tool agnostic. The Codex desktop app supplies `create_thread`, `send_message_to_thread`, and `read_thread` as outer adapter callables; `team_router.py` owns state transitions, recovery anchors, and user-facing output formatting.

**Tech Stack:** Python standard library, `unittest`, Codex desktop thread tools, existing JSON registry/ledger state.

---

### Task 1: User Output Bridge

**Files:**
- Modify: `tests/test_team_router.py`
- Modify: `src/team_router.py`
- Modify: `skills/codex-team-router/SKILL.md`

- [x] Add tests for a helper that formats terminal ledgers as closeout and non-terminal ledgers as handoff.
- [x] Add tests for a verifier-read wrapper that returns both the updated ledger and user-facing output.
- [x] Implement the helper without changing existing ledger return contracts.
- [x] Update the skill doc to tell parent orchestrators to call the user-output helper after verifier read or interruption.

### Task 2: Real Codex Thread Smoke

**Files:**
- Modify: this plan file after smoke evidence is collected.

- [x] Create manager, executor, and verifier threads using Codex desktop `create_thread`.
- [x] Send protocol prompts with `send_message_to_thread`.
- [x] Read each thread with `read_thread` and confirm normal result shapes are accepted by `normalize_thread_read_messages`.
- [x] Record the thread ids and final observed result in this plan.

Smoke evidence collected on 2026-06-22:

- manager thread: `019eefe8-2a4d-7fe0-89b9-264b65e75758`; observed `TEAM_ROUTER_PLAN taskId=ctr-live-smoke-20260622-1`.
- executor thread: `019eefe8-4663-7730-a9bd-01ebcdd8f01c`; observed `TEAM_ROUTER_CALLBACK taskId=ctr-live-smoke-20260622-1`.
- verifier thread: `019eefe8-68e1-7a03-8a29-01e3569e15f8`; observed `TEAM_ROUTER_VERDICT taskId=ctr-live-smoke-20260622-1`.
- `read_thread` returned Codex desktop shape `turns[].items[]` with `agentMessage.text` and numeric `turn.startedAt`; `normalize_thread_read_messages()` now preserves numeric timestamps and `_parse_thread_timestamp()` accepts numeric epoch seconds for anchor filtering.

Regression smoke evidence collected on 2026-06-23:

- reused manager thread: `019ef253-8f71-7111-b794-27154c77ed2e`; observed `TEAM_ROUTER_PLAN taskId=ctr-live-regression-20260623-1103-anchor-fix`.
- reused executor thread: `019ef254-07ef-7710-a0c4-adcb7004c101`; observed `TEAM_ROUTER_CALLBACK taskId=ctr-live-regression-20260623-1103-anchor-fix` with a two-line `summary` preserved.
- reused verifier thread: `019ef254-44df-7121-b2ad-423fd34a2183`; observed `TEAM_ROUTER_VERDICT taskId=ctr-live-regression-20260623-1103-anchor-fix` with `result: pass`.
- `send_message_to_thread` returned only `{ "threadId": ... }`, not a stable sent-message id.
- `read_thread` returned `page.order: newest_first` and item ids such as `item-5` / `item-6`; anchor recovery must use the persisted `sentAt` fallback when the send result has no matching read item id.
- The regression covered manager -> executor -> verifier marker transport, multiline callback summary preservation, and the verifier closeout path after the message-id fallback/newest-first fix.

Orchestrator first-step smoke evidence collected on 2026-06-23:

- canonical role thread titles were set with Codex desktop `set_thread_title`:
  - manager: `019ef253-8f71-7111-b794-27154c77ed2e` -> `TeamRouter manager - codex-dynamic-workflow`.
  - executor: `019ef254-07ef-7710-a0c4-adcb7004c101` -> `TeamRouter executor - codex-dynamic-workflow`.
  - verifier: `019ef254-44df-7121-b2ad-423fd34a2183` -> `TeamRouter verifier - codex-dynamic-workflow`.
- `list_projects` returned Codex desktop project shape with path-like id `D:\codex\codex-dynamic-workflow`, `projectKind: local`, and no prebuilt `target` field.
- `orchestrate_team_task_with_adapter()` was replayed against the real Codex desktop result shapes with local state id `codex-dynamic-workflow` and `codex_project_id: D:\codex\codex-dynamic-workflow`; it returned `action: sent_manager_plan_request`, `status: awaiting_plan`, `createdCount: 0`, and selected manager thread `019ef253-8f71-7111-b794-27154c77ed2e`.
- Real `send_message_to_thread` then sent `TEAM_ROUTER_PLAN_REQUEST taskId=ctr-orchestrate-smoke-20260623-1125` to the selected manager thread and returned only `{ "threadId": ... }`.
- Real `read_thread` returned `page.order: newest_first`, user item `item-7`, and agent item `item-8` containing `TEAM_ROUTER_PLAN taskId=ctr-orchestrate-smoke-20260623-1125`.

### Task 3: Verification And Commit

**Files:**
- Modify: this plan file

- [x] Run `py -m unittest discover -s tests -p test_team_router.py`.
- [x] Run `py -m py_compile src\team_router.py tests\test_team_router.py`.
- [x] Run `git diff --check`.
- [x] Run full `py -m unittest discover -s tests`.
- [x] Commit the focused integration fix.
