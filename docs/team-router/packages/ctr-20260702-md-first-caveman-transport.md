# Team Router Handoff Package: ctr-20260702-md-first-caveman-transport

## Task Summary

- taskId: `ctr-20260702-md-first-caveman-transport`
- objective: implement md-first + caveman transport prompt/policy rules.
- permission: `local-package`
- scope: `src/team_router.py`, `tests/test_team_router.py`, `docs/workbench.md`, and this package record.
- excluded: runtime broker/service behavior, live thread-tool behavior, parser required-field changes, watcher cadence, registry/ledger transitions, push, PR, merge, deploy, publish/release, and global skill sync.

## Contract

Role transport is Markdown-first:

- important facts, decisions, evidence, full logs, checklists, and transcripts go to `taskBriefPath`, `executorReportPath`, or `reviewPackagePath`;
- parent/role chat carries only `TEAM_ROUTER_*` marker blocks, path pointers, result, short counts, risks, and next;
- full logs, full checklists, and transcripts must not be pasted into the parent thread when a package/report path is available.

Caveman transport is limited to ordinary prose compression. It may compress fluff, repetition, and already-supplied background, but it must preserve `TEAM_ROUTER_*` schema, field names, enum values, paths, commands, errors, and `requiredChanges` exactly.

This package only changes prompt/policy wording and tests. It does not add parser-required fields and does not change runtime dispatch, watcher, broker, ledger, registry, or live thread-tool behavior.

## Files

- `src/team_router.py`
- `tests/test_team_router.py`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260702-md-first-caveman-transport.md`

## Implementation Summary

- Added `mdFirstPolicy`, `parentRoleChatPolicy`, and `cavemanTransportPolicy` to `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY["roleCommunicationEconomy"]`.
- Added matching role prompt lines for normal and package handoff prompts.
- Preserved compact transport pointers in reviewer/verifier package-path prompts without re-bloating the minimal template.
- Added a focused TDD test that locks the policy snapshot and generated executor/reviewer/verifier prompts.

## Verification

- RED: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-md-first-red TMP=C:\tmp TEMP=C:\tmp py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_codify_md_first_caveman_transport -v` first failed with `KeyError: 'mdFirstPolicy'`.
- GREEN: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-md-first-green1 TMP=C:\tmp TEMP=C:\tmp py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_codify_md_first_caveman_transport -v` -> Ran 1 test OK.
- Focused prompt/policy regression: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-md-first-focused8 TMP=C:\tmp TEMP=C:\tmp py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_codify_md_first_caveman_transport tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_compact_reply_examples_accept_path_valued_evidence_checked tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise tests.test_team_router.TestTeamRouterManagerIntegration.test_role_prompts_include_risk_boundary_and_review_package_metadata tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface -v` -> Ran 8 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-md-first-compile TMP=C:\tmp TEMP=C:\tmp py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for touched text files only.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-md-first-truth TMP=C:\tmp TEMP=C:\tmp py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; dirty local package surface includes `docs/workbench.md`, `src/team_router.py`, `tests/test_team_router.py`, and this package doc; `skillSync.status: mismatch` remains outside this package because global sync is not authorized.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-md-first-doctor TMP=C:\tmp TEMP=C:\tmp py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `nextAction` says reviewer then verifier before closeout.

## Gate

Reviewer and verifier gates passed. Current gate: local commit closeout only. Push, PR, merge, deploy, publish/release, live role dispatch, thread-tool calls, and global skill sync remain outside this package.
