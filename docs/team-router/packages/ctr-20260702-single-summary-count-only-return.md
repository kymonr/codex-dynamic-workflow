# ctr-20260702-single-summary-count-only-return

## Objective

Tighten package-path pass/done return templates so `TEAM_ROUTER_REVIEW` and `TEAM_ROUTER_VERDICT` return exactly one `summary` field and count-only evidence:

`<reviewPackagePath>; tests: N OK; checks: M OK`

This prevents pass returns from copying long command strings, duplicated summaries, full logs, checklists, transcripts, or raw evidence bodies back into role/parent chat.

## Scope

- `src/team_router.py`
- `tests/test_team_router.py`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260702-single-summary-count-only-return.md`

## Boundary

- No parser required-field changes.
- No runtime ledger, broker, watcher, host adapter, direct-return capture, or global skill sync changes.
- No push, PR, merge, deploy, publish/release, or production/service action.

## Changes

- Added a focused package-path prompt test requiring pass/done reply policy to say exactly one `summary` field and the fixed evidence/count format.
- Updated compact reviewer/verifier package-path `replyPolicy` text to use the fixed evidence format.
- Updated role communication economy policy text and prompt lines so pass/done results use one summary field and count-only evidence.
- Kept parser fields unchanged: reviewer still lists `result,summary,findings,requiredChanges,evidenceChecked,risks,next`; verifier still lists `result,summary,requiredChanges,evidenceChecked,risks,next`.

## Verification

- RED: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-single-summary-red TMP=C:\tmp TEMP=C:\tmp py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_package_path_pass_returns_require_single_summary_and_count_only_evidence -v` first failed on the old `replyPolicy: pass 1-2 lines; evidence path+counts; rework actionable; logs in path`.
- GREEN: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-single-summary-green2 TMP=C:\tmp TEMP=C:\tmp py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_package_path_pass_returns_require_single_summary_and_count_only_evidence tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_compact_reply_examples_accept_path_valued_evidence_checked tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterSkillDoc.test_role_communication_economy_policy_keeps_gates_but_limits_chat -v` -> Ran 6 tests OK.
- Count-only reviewer re-check evidence: `docs/team-router/packages/ctr-20260702-single-summary-count-only-return.md; tests: 7 OK; checks: 4 OK`.
- Reviewer re-check: pass; verifier re-check: pass; current gate is local commit closeout.

## Current Gate

Reviewer and verifier gates passed. Current gate: local commit closeout only. Push, PR, merge, deploy, publish/release, live role dispatch, thread-tool expansion, and global skill sync remain outside this package.
