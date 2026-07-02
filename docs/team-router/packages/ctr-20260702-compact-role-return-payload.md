# Team Router Handoff Package: ctr-20260702-compact-role-return-payload

## Task Summary

- taskId: `ctr-20260702-compact-role-return-payload`
- objective: make executor/reviewer/verifier pass/done return payloads compact by default.
- permission: `local-package`
- scope: prompt/template/tests/docs only.
- excluded: runtime broker/service behavior, live thread-tool behavior, parser required-field changes, watcher cadence, registry/ledger transitions, commit, push, PR, merge, deploy, publish/release, and global skill sync.

## Contract

Role final pass/done blocks should carry short human summaries plus durable path pointers:

- executor `TEAM_ROUTER_CALLBACK`: `summary` is 1-2 lines; `evidence` points to `executorReportPath` or `reviewPackagePath` and may add short test counts.
- reviewer `TEAM_ROUTER_REVIEW`: `summary` is 1-2 lines; `evidenceChecked` points to `reviewPackagePath` or a result path and may add short test counts.
- verifier `TEAM_ROUTER_VERDICT`: `summary` is 1-2 lines; `evidenceChecked` points to `reviewPackagePath` or a result path and may add short test counts.

For `needs_rework`, `fail`, or `blocked`, findings and required changes must stay actionable. Long logs, full checklists, transcripts, and full evidence belong in the package/report path.

The compact reviewer/verifier examples remain parser-compatible with existing `parse_review()` and `parse_verdict()` behavior. No new parser-required fields are introduced.

## Files

- `src/team_router.py`
- `tests/test_team_router.py`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260702-compact-role-return-payload.md`

## Verification

- Focused prompt/parser/workbench suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-compact-return TMP=C:\tmp TEMP=C:\tmp py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_compact_reply_examples_accept_path_valued_evidence_checked tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_role_request_prompts_without_return_thread_id_are_self_thread_marker_only tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 7 tests OK.
- `git status -sb --untracked-files=all` -> dirty local package surface: `docs/workbench.md`, `src/team_router.py`, `tests/test_team_router.py`, and this package doc.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-compact-return TMP=C:\tmp TEMP=C:\tmp py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-compact-return TMP=C:\tmp TEMP=C:\tmp py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: mismatch` is existing repo/global skill drift and global sync is not authorized in this package.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-compact-return TMP=C:\tmp TEMP=C:\tmp py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `nextAction` says reviewer then verifier before closeout; commit/push/PR/merge/deploy/global skill sync remain unauthorized.

## Gate

Reviewer and verifier gates passed. Current gate: local commit only for this package; push, PR, merge, deploy, publish/release, and global skill sync remain outside this gate.
