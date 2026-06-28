# Team Router Optimization 1-6 Review Package

## Objective

Implement `ctr-20260628-team-router-optimization-1-6` local package items 1-6 without push, PR, merge, deploy, release, or global skill sync.

## Scope

Current touched files:

- `README.md`
- `docs/workbench.md`
- `docs/superpowers/plans/2026-06-28-team-router-optimization-1-6.md`
- `docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md`
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/adapter-runtime.md`
- `skills/codex-team-router/references/testing-and-quality-gates.md`
- `src/team_router.py`
- `tests/test_team_router.py`
- `scripts/team_router_closeout_check.py`

Out of scope:

- `C:\Users\Orz\.codex\skills\codex-team-router`
- push, PR, merge, deploy, release, publish
- global skill sync
- extra write threads/subagents

## Diff Summary

- Slimmed `skills/codex-team-router/SKILL.md` to 7192 bytes while preserving hard entry rules, current Manager Mode trigger language, stable file/path handoff, Skill/rule/Superpowers write routing, and reference navigation.
- Added `explain_team_router_gate()` for readable FAST/NORMAL/STRICT/PACKAGE reasons while preserving `classify_team_router_gate()` compatibility.
- Added `assess_live_orchestration_readiness()` for pure host contract readiness reporting: callable adapter, `parent_thread_id`, callable `set_thread_title`, and heartbeat scheduler.
- Strengthened malformed direct-return telemetry for wrong/missing protocol `sourceThreadId`, `role`, and `sourceRoleThreadId` while keeping self-thread-marker fallback and no ledger advancement.
- Added read-only `scripts/team_router_closeout_check.py` to report git status, diff files, SKILL size, repo/global skill sync status, and unauthorized commit/push/global sync gates.
- Updated tests for gate explanations, readiness, malformed direct-return recovery, 7200-byte entrypoint target, closeout check, and active workbench state.
- Reworked test temp strategy to remove the global `tempfile.TemporaryDirectory` monkeypatch and use local `workspace_temp_dir()` calls only. On Windows it defaults to `C:\tmp\team-router-test-tmp` because workspace `test-tmp` blocks `os.replace`; `TEAM_ROUTER_TEST_TMP_ROOT` can override it.
- Updated `README.md`, adapter/testing references, and `docs/workbench.md` so current truth and historical records stay separated.

## TDD Evidence

RED:

- `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` failed as expected for missing `explain_team_router_gate`, missing `assess_live_orchestration_readiness`, and missing closeout check script.
- Parent full-suite verification later failed with 254 tests, 297 errors, 1 failure due broad `C:\tmp` temp usage and one missing Skill/docs contract phrase.
- Parent rework inspection rejected the global `tempfile.TemporaryDirectory = _WorkspaceTemporaryDirectory` monkeypatch as too broad.
- Non-escalated probe showed workspace `test-tmp` allows mkdir but blocks `os.replace`, while `C:\tmp` allows the atomic replace path used by JSON state tests.

GREEN / Current:

- Runtime helpers, closeout script, Skill/docs phrases, and local `workspace_temp_dir()` helper are implemented.
- No global stdlib monkeypatch remains in `tests/test_team_router.py`.
- Focused state, malformed direct-return, and Skill/workbench contract tests pass.
- Full non-escalated `tests.test_team_router` suite passes.

## Tests

Passed:

- `(Get-Item skills\codex-team-router\SKILL.md).Length` -> `7192`, below 7200.
- `py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py` with `PYTHONPYCACHEPREFIX=C:\tmp\pycache-team-router-parent` -> PASS.
- `py -B -m unittest tests.test_team_router.TestTeamRouterJsonState ... TestTeamRouterSkillDoc.test_team_router_docs_describe_active_role_return` with `PYTHONPYCACHEPREFIX=C:\tmp\pycache-team-router-parent` -> PASS, 16 tests.
- `py -B -m unittest tests.test_team_router` with `PYTHONPYCACHEPREFIX=C:\tmp\pycache-team-router-parent` -> PASS, 254 tests.

Pending manager/reviewer rerun after this package file update:

- `git diff --check`
- `py -B scripts\team_router_skill_sync_check.py --check`
- `py -B scripts\team_router_closeout_check.py`

## Temp Hygiene

- `tests/test_team_router.py` no longer assigns to `tempfile.TemporaryDirectory`.
- `workspace_temp_dir()` uses a local context manager with `Path.mkdir` and `shutil.rmtree(ignore_errors=True)`.
- Default Windows temp root is `C:\tmp\team-router-test-tmp`; this avoids repo-local `os.replace` denial and keeps generated state outside the git worktree.
- Safe cleanup removed task-created roots after path verification:
  - `D:\codex\Team Router\test-tmp`
  - `D:\codex\Team Router\.tmp\test_team_router`
  - `C:\tmp\team-router-test-tmp`

## Not Done

- no push
- no PR
- no merge
- no deploy
- no release/publish
- no global skill sync

## Risks

- `py -B scripts\team_router_skill_sync_check.py --check` is expected to report `status: mismatch` after repo skill changes because global sync is not authorized in this package.
- Git may print CRLF/LF replacement warnings for existing text files.
- The original executor thread became stuck around a sandbox escalation attempt; parent manager performed a narrow temp-helper rescue and will require reviewer/verifier scrutiny before any local commit.

## Global Sync / Commit / Push Status

- globalSyncStatus: not run with `--sync`; repo/global expected mismatch until separate authorization.
- commitStatus: not committed yet; local commit allowed only after reviewer and verifier pass for this Complex Task Stack package.
- pushStatus: not pushed / not authorized.