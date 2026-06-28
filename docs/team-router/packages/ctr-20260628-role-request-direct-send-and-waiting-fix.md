# Team Router Handoff Package: ctr-20260628-role-request-direct-send-and-waiting-fix

## Task Summary / 任务摘要

- taskId: `ctr-20260628-role-request-direct-send-and-waiting-fix`
- objective: 修复 role request direct-send 指令缺口，并收紧 manager waiting，避免 `inProgress` 或 CONTROL 后短间隔连续 `read_thread` 轮询。
- gateClass: `PACKAGE`
- permission: `local-package`
- execution mode: docs/tests only; no runtime edit, no commit, no push, no PR, no release.

## Direct-Send Template Contract / 模板契约

Role request templates must include all role-specific delivery fields:

- executor: `callbackDelivery: direct-send` and `callbackFallback: self-thread-marker`.
- reviewer: `reviewDelivery: direct-send` and `reviewFallback: self-thread-marker`.
- verifier: `verdictDelivery: direct-send` and `verdictFallback: self-thread-marker`.

protocol direct-send is allowed and is not a workspace/file write. It is a protocol delivery action back to the parent/orchestrator thread.

Roles must first call `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`, then output the same protocol block body as the self-thread-marker fallback in the role thread. The fallback body must remain the same protocol block body; fallback-only metadata is only for degraded delivery.

## Waiting Contract / 等待契约

Manager waiting must use one short observation-only first check, then stop proactive reads until firstCheckAt or nextAllowedReadAt. `inProgress` is not polling permission. CONTROL after bounded wait/read is not permission for immediate continuous read_thread polling.

The manager must wait for direct-send, user-triggered status/stop/immediate, firstCheckAt, nextAllowedReadAt, known expected completion window, or timeout/blocker handling before reading again.

## Scope / 范围

Touched files for this package:

- `tests/test_team_router.py`
- `docs/workbench.md`
- `skills/codex-team-router/references/manager-mode.md`
- `skills/codex-team-router/references/manual-orchestration.md`
- `skills/codex-team-router/references/testing-and-quality-gates.md`
- `skills/codex-team-router/references/direct-return.md`
- `docs/team-router/packages/ctr-20260628-role-request-direct-send-and-waiting-fix.md`

## Verification / 验证

- RED: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_role_requests_require_direct_send_and_bounded_waiting_contract -v` failed before docs/package updates because this package file did not exist.
- GREEN focused check: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_role_requests_require_direct_send_and_bounded_waiting_contract -v`: pass.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 35 tests.
- `git diff --check`: pass; Git printed CRLF/LF normalization warnings for existing working-copy files, with no whitespace errors.

## Excluded Changes / 未纳入改动

- No runtime behavior changes.
- No edits to `src/team_router.py`.
- No edits to old package files.
- No commit, push, PR, merge, publish, or release.

## Risks / 风险

- This is a documentation/test contract fix. Runtime prompt generators may still need a later implementation pass if they do not yet include these exact fields in generated role prompts.

## Remaining Todos / 剩余事项

- verifier accepted/pass; remainingTodos: none for this local package. No commit, push, PR, merge, publish, or release was done.
