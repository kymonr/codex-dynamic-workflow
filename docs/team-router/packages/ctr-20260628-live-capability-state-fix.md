# Team Router Handoff Package: ctr-20260628-live-capability-state-fix

## Task Summary / 任务摘要

- taskId: `ctr-20260628-live-capability-state-fix`
- objective: 修正 Team Router 当前能力状态漂移，区分 Codex app thread tool surface、Python callable adapter boundary、live orchestration readiness。
- gateClass: `PACKAGE`
- permission: `local-package`
- execution mode: minimal rework; docs/tests only; no runtime daemon, no commit, no push, no PR, no release.

## Three-Layer Capability State / 三层能力状态

1. tool surface available: Codex app thread tool surface available / exposed: `list_projects/create_thread/read_thread/send_message_to_thread/list_threads/set_thread_title`.
2. callable adapter unavailable: `src/team_router.py` still needs an in-process Python callable adapter wrapper. Model-side app tool exposure is not the same as callable Python functions passed into `probe_thread_adapter_capabilities()` / `orchestrate_team_task_with_adapter()`.
3. live orchestration not ready: end-to-end live orchestration still needs explicit `parent_thread_id` injection plus a host `scheduler/heartbeat` that calls `watch_team_task_with_adapter()` at `firstCheckAt` / `nextAllowedReadAt`.

## Scope / 范围

This package only updates the workbench/package state and tests that lock that state. It does not change `src/team_router.py` runtime behavior.

## Touched Files / 触及文件

- `tests/test_team_router.py`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260628-live-capability-state-fix.md`

## Behavior Changes / 行为变化

- `docs/workbench.md` no longer claims the current state is missing the app-level thread tool surface.
- The current state now says the tool surface is available while the Python callable adapter wrapper, `parent_thread_id`, and host `scheduler/heartbeat` remain the blockers for live orchestration.
- `tests/test_team_router.py` locks the workbench/package wording so future closeouts do not collapse these layers again.

## Verification / 验证

- RED: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_live_capability_state_without_tool_surface_drift -v` failed before docs/package updates because this package file did not exist.
- GREEN focused check: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_live_capability_state_without_tool_surface_drift -v`: pass.
- `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v`: pass, 34 tests.
- `git diff --check`: pass; Git printed CRLF/LF normalization warnings for existing working-copy files, with no whitespace errors.

## Excluded Changes / 未纳入改动

- No runtime behavior changes.
- No edits to `src/team_router.py`.
- No edits to references or `docs/compounding.md` in this rework.
- No commit, push, PR, merge, publish, or release.

## Risks / 风险

- This package is a state/documentation/test fix only. Real live orchestration still requires a host adapter implementation that can call the exposed tools from Python and provide parent thread identity plus scheduler/heartbeat.

## Remaining Todos / 剩余事项

- verifier accepted/pass; remainingTodos: none for this local rework. No commit, push, PR, merge, publish, or release was done.
