# Team Router Handoff Package: ctr-20260628-team-router-optimization-local-package

## Objective

Fix reviewer-required Team Router optimization issues in the local package scope.

## Required Changes Covered

- P1-A direct-return role request templates now prefer explicit `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)` wording for executor, reviewer, and verifier prompts. Legacy `send_message_to_thread(sourceThreadId, protocolBlock)` is asserted only in Compatibility anchor / Legacy wording contexts.
- P1-B `docs/workbench.md` now records idle clean state; `ctr-20260628-anchor-and-closeout-freshness-fix` is historical only.
- P1-C runtime role reuse now treats archived/broken/unavailable roles as unavailable for direct registry reuse and records replacement metadata when creating a replacement role.
- P2-D public watcher helper now suppresses repeated proactive reads before `firstCheckAt` / `nextAllowedReadAt`, with explicit user-triggered/status/stop/immediate and timeout/blocker bypass.
- Rework1 tightened contract tests so main role request/templates/docs cannot regress to legacy first-call wording while compatibility anchors remain covered.

## Diff Surface

Tracked diff at rework1 closeout is limited to:

- `docs/runbooks/codex-team-router-live-orchestration.md`
- `docs/workbench.md`
- `skills/codex-team-router/references/manager-polling-cadence.md`
- `src/team_router.py`
- `tests/test_team_router.py`

Untracked package artifact:

- `docs/team-router/packages/ctr-20260628-team-router-optimization-local-package.md`

`skills/codex-team-router/references/direct-return.md` is not in the current `git status -s --untracked-files=all` / `git diff --name-only` diff surface. It still appears in `py -B scripts\team_router_skill_sync_check.py --check` because the repo skill reference and global installed skill differ; global sync is explicitly out of scope for this package.

## Verification

Commands run by executor:

- `py -B -m py_compile src\team_router.py tests\test_team_router.py`: passed with `PYTHONPYCACHEPREFIX`, `TMP`, and `TEMP` pointed at `C:\tmp` because the default sandbox blocks local `__pycache__` writes.
- Focused tests for direct-return/docs/workbench/runtime replacement/watcher throttle: passed, 10 tests OK.
- Rework1 focused doc/contract tests: passed for `test_skill_doc_contains_parent_thread_operating_flow`, `test_team_router_docs_describe_active_role_return`, `test_direct_return_reference_matches_active_role_return_contract`, `test_live_orchestration_runbook_exists`, `test_manager_orchestration_policy_docs_cover_polling_reuse_and_verifier_return`, and `test_conditional_reviewer_docs_cover_role_policy_reuse_and_direct_return`.
- `py -B -m unittest tests.test_team_router`: passed in rework1, Ran 249 tests in 6.655s, OK.
- `git diff --check`: passed; Git may print CRLF/LF normalization warnings, but no whitespace errors.
- `py -B scripts\team_router_skill_sync_check.py --check`: expected `status: mismatch` because this package does not sync global `C:\Users\Orz\.codex\skills`.
- `git status -s --untracked-files=all`: tracked files listed above plus this untracked package artifact.

## Risks

- Global installed `codex-team-router` skill remains unsynced by design; this package is local-only and must not update `C:\Users\Orz\.codex\skills`.
- `references/direct-return.md` may continue to appear in sync-check mismatch even when it is not part of the current Git diff.
- Remaining risk for runtime behavior: none identified after focused and full unittest verification.

## remainingTodos

- none for local implementation.
- reviewer should confirm the tightened test assertions and package evidence shape.
- verifier remains the final acceptance gate after reviewer pass.

## Boundaries

No commit, push, PR, release, publish, or global `C:\Users\Orz\.codex\skills` sync is included in this package.