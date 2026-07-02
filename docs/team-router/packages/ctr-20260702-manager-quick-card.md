# Team Router Handoff Package: ctr-20260702-manager-quick-card

## Objective

Make real Manager Mode use start from a short operation card: short protocol, Markdown path handoff, reviewer/verifier direct-return, and separate commit/push/global-sync gates.

## Scope

- Update repo-local `skills/codex-team-router/SKILL.md` to point daily Manager Mode use at the quick card.
- Add repo-local `skills/codex-team-router/references/manager-quick-card.md`.
- Update focused skill documentation tests and the workbench current-state record.

## Out Of Scope

- Runtime/parser changes.
- Live thread-tool dispatch.
- Background broker/service work.
- Global skill sync.
- Commit, push, PR, merge, or deploy.

## Intended Daily Prompt Shape

```text
你作为管理者，使用 Team Router 管这个任务。
默认短协议 + md path。
长上下文写入 taskBriefPath / executorReportPath / reviewPackagePath。
reviewer/verifier 自动 direct-return。
commit、push、PR、merge、deploy、global sync 都单独授权。
出问题才展开 references。
```

## Acceptance

- The skill entrypoint remains under the 7200-byte guard.
- `manager-quick-card.md` is listed as a required reference and is linked from the entrypoint.
- The quick card does not claim new runtime, live orchestration, or global sync behavior.
- Workbench current-state text points at this active package and keeps commit/global sync/push as separate gates.

## Verification Log

- Focused skill doc checks: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-quick-card-tests2 py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_skill_entrypoint_uses_progressive_disclosure_references tests.test_team_router.TestTeamRouterSkillDoc.test_skill_doc_contains_required_boundaries tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 3 tests OK.
- Skill documentation suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-quick-card-docsuite2 py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -q` -> Ran 53 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-quick-card-compile2 py -B -m py_compile tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0 with CRLF/LF replacement warnings for existing text files.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; skill entrypoint 7172 bytes and under target; repo/global skillSync is `mismatch` because global sync is not authorized.
- `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; nextAction requires reviewer then verifier before closeout.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; reports dirty local package and repo/global skillSync `mismatch` under the separate global-sync gate.
- Reviewer thread `019f21ea-ba8b-7cd2-b1a3-88aeacdc9dd4` -> `pass`; accepted the existing dirty diff as an executor draft after reviewing the procedural violation and required no rework.
- Verifier thread `019f21ec-970e-7fb2-b005-3c6e104b0782` -> `pass`; requiredChanges none; local commit is the next gate, while global sync and push remain separate explicit gates.
