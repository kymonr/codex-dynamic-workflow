# Team Router Handoff Package: ctr-20260703-manager-request-compression

## Objective

Compress orchestrator-emitted package-path role requests so reviewer/verifier prompts pass stable paths and short deltas instead of embedding executor callback or reviewer result blocks.

Required contract:

- `TEAM_ROUTER_REVIEW_REQUEST` with `reviewPackagePath` keeps marker, permission, scope, role/return metadata, concise action, reply marker/fields, and `executorCallback: see reviewPackagePath`.
- `TEAM_ROUTER_VERIFY` with `reviewPackagePath` keeps marker, permission, scope, role/return metadata, concise action, reply marker/fields, `executorCallback: see reviewPackagePath`, and `reviewerResult: see reviewPackagePath`.
- No-path or explicit `inlineFallback: true` request templates keep detailed inline context where raw context is still required.

## Scope

- `src/team_router.py`
- `tests/test_team_router.py`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260703-manager-request-compression.md`

Preserved existing dirty/untracked work from `ctr-20260703-skill-repair`:

- `README.md`
- prior edits in `docs/workbench.md`
- prior edits in `tests/test_team_router.py`
- `docs/team-router/packages/ctr-20260703-skill-repair.md`

Out of scope: project `AGENTS.md`, commit, push, PR, merge, deploy, global skill sync, live role dispatch beyond the required callback.

## Behavior Changes

- Compact callback context now includes `executorCallback: see reviewPackagePath` before the existing compact callback location hints.
- Compact reviewer-result context now starts with `reviewerResult: see reviewPackagePath` and omits the verbose `reviewRaw` shape.
- Package-path reviewer/verifier requests add one concise `action:` line and keep direct-return metadata plus parser-compatible reply fields.
- Package-path reviewer prompts omit the redundant reviewer responsibility sentence to stay within compact prompt length budgets; inline/no-path prompts keep the existing detailed template.

## Diff Summary

- `src/team_router.py`: tightened compact helper output for callback/reviewer-result references and added package-path action lines to reviewer/verifier request generation.
- `tests/test_team_router.py`: added a failing-then-passing regression for package-path manager requests that rejects raw callback/review payloads and requires path pointers.
- `docs/workbench.md`: current task/gate now points at this package and records focused RED/GREEN evidence.
- `docs/team-router/packages/ctr-20260703-manager-request-compression.md`: this package evidence.

## Verification

- RED focused test: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-red TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B -m unittest tests.test_team_router -k package_path_manager_requests_reference_callback -v` -> 1 test failed as expected because reviewer/verifier compact package-path requests lacked `action:`, `executorCallback: see reviewPackagePath`, and `reviewerResult: see reviewPackagePath`.
- GREEN focused test: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-green-focused TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B -m unittest tests.test_team_router -k package_path_manager_requests_reference_callback -v` -> Ran 1 test OK.
- Protocol regression: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-protocol2 TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v` -> Ran 58 tests OK.
- Focused prompt/docs suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-prompt-focused TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_package_path_manager_requests_reference_callback_and_review_results_by_path tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template -v` -> Ran 5 tests OK.
- Workbench guard: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-doc-focused TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 1 test OK.
- Affected skill/doc suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-skilldoc TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 53 tests OK.
- Full suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-full TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B -m unittest tests.test_team_router -v` -> Ran 424 tests OK.
- Truth check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-truth TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; dirty surface includes `README.md`, `docs/workbench.md`, `src/team_router.py`, `tests/test_team_router.py`, this package, and preserved `ctr-20260703-skill-repair.md`.
- Closeout check: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-request-compression\pycache-closeout TMP=C:\tmp\team-router-request-compression TEMP=C:\tmp\team-router-request-compression py -X utf8 -B scripts\team_router_closeout_check.py` -> exit 0; authorization remains no commit, no push, no PR, no merge, no deploy, no global sync.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.

## Excluded Changes

- Existing `README.md` dirty change from `ctr-20260703-skill-repair` was preserved and not edited in this package.
- Existing untracked `docs/team-router/packages/ctr-20260703-skill-repair.md` was preserved and not edited.

## Risks

- Compact prompt wording can still drift if future role-template changes add verbose prose after path pointers; the new regression locks the concrete package-path request shape.
- Path-only requests assume reviewer/verifier can access `reviewPackagePath`; no-path and explicit inline fallback remain available for inaccessible shared paths.

## Remaining Todos

- Send reviewer gate after executor callback.
