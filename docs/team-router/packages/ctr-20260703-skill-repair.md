# Team Router Handoff Package: ctr-20260703-skill-repair

## Objective

Refresh stale Team Router skill/docs expectations after compact path handoff and clean/synced repo truth:

- align the path-handoff test with `callbackContext` / `callbackRawLocation`;
- stop workbench tests from locking old active-package/current-gate prose;
- update README direct-return main wording to explicit `threadId=<returnThreadId>`;
- record focused and full local verification evidence for reviewer handoff.

## Scope

- `docs/workbench.md`
- `tests/test_team_router.py`
- `README.md`
- `docs/team-router/packages/ctr-20260703-skill-repair.md`

Out of scope: `src/team_router.py` unless tests prove implementation drift; project `AGENTS.md`; commit, push, PR, merge, deploy, global skill sync, live role dispatch beyond the required callback.

## Initial Evidence

- Fresh repo truth before edits: `git status -sb --untracked-files=all` -> `## master...origin/master`; `git status -s --untracked-files=all` and `git diff --name-only` -> no entries.
- RED path-handoff test: `py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts -v` -> 1 test, 3 subtest failures; all expected old `执行者 callback 摘要` while generated prompts used `callbackContext` / `callbackRawLocation`.
- Pre-refresh truth check: `py -X utf8 -B scripts\team_router_truth_check.py --json` -> exit 0 with stale claims for `docs/workbench.md` clean/synced state versus old active package/current evidence text.

## Diff Summary

- `README.md`: main Direct return rule now tells roles to call `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`; legacy `send_message_to_thread(sourceThreadId, protocolBlock)` is retained only in a compatibility note.
- `docs/workbench.md`: Current Task and Review And Verification Gate no longer claim `ctr-20260702-single-summary-count-only-return` is active or awaiting local commit closeout; the section records the fresh clean/synced pre-dispatch baseline and points package-specific evidence to this package file.
- `tests/test_team_router.py`: path-handoff test now asserts compact callback context/location fields and raw payload omission; workbench guard now locks command-derived baseline wording and absence of stale current-gate text; docs test now checks README main-versus-compatibility direct-return wording.
- `docs/team-router/packages/ctr-20260703-skill-repair.md`: this review package.

## Verification Evidence

- Focused repair suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-skill-repair-focused1 TMP=C:\tmp TEMP=C:\tmp py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_team_router_docs_describe_active_role_return -v` -> Ran 3 tests OK.
- Full suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-skill-repair-full TMP=C:\tmp TEMP=C:\tmp py -X utf8 -B -m unittest tests.test_team_router -v` -> Ran 423 tests OK.
- Truth check after final package evidence update: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-skill-repair-truth2 TMP=C:\tmp TEMP=C:\tmp py -X utf8 -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; dirty local package surface is `README.md`, `docs/workbench.md`, `tests/test_team_router.py`, and this untracked package doc.
- Closeout check after final package evidence update: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-skill-repair-closeout2 TMP=C:\tmp TEMP=C:\tmp py -X utf8 -B scripts\team_router_closeout_check.py --json` -> exit 0; commit/push/PR/merge/deploy/globalSync authorization all false; `skillSync.status: match`.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.

## Risks / Remaining Todos

- Remaining risk: none known inside this local package. Commit, push, PR, merge, deploy, and global skill sync remain outside this dispatch.
- remainingTodos: reviewer gate.
