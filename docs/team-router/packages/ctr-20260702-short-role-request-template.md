# ctr-20260702-short-role-request-template

## Package Metadata

- taskId: `ctr-20260702-short-role-request-template`
- branch: `master`
- permission: Complex Task local package. Includes narrowly scoped role-request template code, focused tests, package/workbench records, verification, and local commit. Excludes push, PR, merge, deploy, global skill sync, live role dispatch, thread-tool calls, and independent service work unless separately authorized.
- scope: make reviewer/verifier package-path prompts default to short protocol plus Markdown paths instead of inlining checklist/schema text.

## Objective

Reduce the actual Team Router role prompts seen during dogfood. When `reviewPackagePath` / `taskBriefPath` / `executorReportPath` are present, reviewer and verifier requests should trust the skill defaults and package files instead of repeating long scope checklists, direct-return explanations, and full response schemas.

## Behavior

Package-path reviewer/verifier requests now keep:

- required protocol markers and permission/scope fields;
- `roleCommunicationMode`, short `defaultRules`, `packageEvidenceBoundary`, and package paths;
- direct-return metadata plus one short `returnContract`;
- compact callback/reviewer-result references pointing back to package paths;
- short `replyMarker` and parser-compatible `replyFields`.

They omit in the compact path:

- verbose direct-return how-to lines;
- full reply schema;
- `evidenceChecked` schema prompts;
- verifier checklist prose;
- expanded evidence-only fast-path prose.

No-path fallback keeps the older detailed prompt shape. `inlineFallback: true` by itself is not a package-path signal; reviewer/verifier only use the compact template when at least one of `taskBriefPath`, `executorReportPath`, or `reviewPackagePath` is present.

## Verification Record

- RED: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-red py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template -v` first failed because generated prompts still lacked `returnContract` and included verbose direct-return/schema lines.
- GREEN: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-green3 py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template -v` -> Ran 2 tests OK.
- Focused regression: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-focused4 py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise tests.test_team_router.TestTeamRouterManagerIntegration.test_role_prompts_include_risk_boundary_and_review_package_metadata tests.test_team_router.TestTeamRouterManagerIntegration.test_reviewer_request_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterManagerIntegration.test_verifier_request_supports_direct_return_delivery_metadata -v` -> Ran 8 tests OK.
- Reviewer v1: thread `019f1f23-8d8c-7512-9124-5a8bf984d68b` -> `needs_rework`; required change was to avoid compacting reviewer/verifier prompts when package metadata only says `inlineFallback: true` and no real path is present.
- Rework RED: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-red2 py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template -v` -> Ran 2 tests, both failed because inline fallback was incorrectly using `returnContract`/`replyFields` and `packageEvidenceBoundary: path metadata only`.
- Rework GREEN: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-green4 py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise tests.test_team_router.TestTeamRouterManagerIntegration.test_role_prompts_include_risk_boundary_and_review_package_metadata -v` -> Ran 8 tests OK.
- Reviewer v2: thread `019f1f23-8d8c-7512-9124-5a8bf984d68b` -> `pass`; requiredChanges: none.
- Verifier v1: thread `019f1f2a-50dd-70b3-950d-333cb5bdef40` -> `needs_rework`; required change was to keep compact `replyFields` compatible with existing `parse_review` / `parse_verdict` required fields.
- Parser compatibility RED: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-red3 py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_compact_reviewer_reply_fields_match_parser_required_fields tests.test_team_router.TestTeamRouterProtocol.test_compact_verifier_reply_fields_match_parser_required_fields -v` -> Ran 2 tests, both failed because compact `replyFields` omitted parser-required fields.
- Parser compatibility GREEN: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-green5 py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_compact_reviewer_reply_fields_match_parser_required_fields tests.test_team_router.TestTeamRouterProtocol.test_compact_verifier_reply_fields_match_parser_required_fields -v` -> Ran 2 tests OK.
- Expanded focused suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-rework-focused5 py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_compact_reviewer_reply_fields_match_parser_required_fields tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_compact_verifier_reply_fields_match_parser_required_fields tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise tests.test_team_router.TestTeamRouterManagerIntegration.test_role_prompts_include_risk_boundary_and_review_package_metadata tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 11 tests OK.
- Reviewer v3: thread `019f1f23-8d8c-7512-9124-5a8bf984d68b` -> `pass`; requiredChanges: none.
- Verifier v2: thread `019f1f2a-50dd-70b3-950d-333cb5bdef40` -> `needs_rework`; required change was to refresh `docs/workbench.md` `Review And Verification Gate`, which still named the previous host-adapter package as the current gate.
- Gate rework: updated the workbench gate to the current short-role-request package and tightened `test_workbench_tracks_current_task_without_stale_diff_surface` so stale host-adapter closeout text cannot pass in the current gate section.
- Verifier v3: thread `019f1f2a-50dd-70b3-950d-333cb5bdef40` direct-returned to the manager thread -> `pass`; requiredChanges: none; accepted for local commit under the authorized Complex Task package.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-compile py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.
- Final focused suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-short-template-final-focused py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_uses_path_first_handoff_without_raw_callback tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_uses_path_first_handoff_without_raw_review_or_callback tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise tests.test_team_router.TestTeamRouterManagerIntegration.test_role_prompts_include_risk_boundary_and_review_package_metadata tests.test_team_router.TestTeamRouterManagerIntegration.test_reviewer_request_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterManagerIntegration.test_verifier_request_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 9 tests OK.
- `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty local package surface includes `docs/workbench.md`, `src/team_router.py`, `tests/test_team_router.py`, and this package doc.
- `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `nextAction` says reviewer then verifier before closeout.
- `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`.

## Gate

Local closeout: committed under the authorized Complex Task package. Push remains separate.
