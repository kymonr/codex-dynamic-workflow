# Team Router Review Package: ctr-20260630-dispatch-prompt-path-handoff

## Package Metadata

- taskId: `ctr-20260630-dispatch-prompt-path-handoff`
- permission: `local-package`
- baseline: committed status-tools package `4dd5a95`
- objective: make executor dispatch prompts use stable path handoff instead of copying long `executorPrompt` text between role conversations.
- scope: `src/team_router.py`, `tests/test_team_router.py`, `docs/workbench.md`, `docs/team-router/module-map.md`, this package file.
- outOfScope: host adapter/scheduler implementation, watcher/runtime changes, parser/gate/direct-return semantics, push, PR, merge, deploy, publish/release, global skill sync.
- Commit: authorized by the user and completed as local closeout.

## Changed Files

- `src/team_router.py`: added `_executor_objective_prompt_lines()` and routed executor dispatch objective text through it. When readable `taskBriefPath` or `reviewPackagePath` metadata is present and `executorPrompt` is overlong or multiline, the dispatch prompt now emits `executorPrompt: <omitted; see taskBriefPath/reviewPackagePath>` instead of copying the long text. `inlineFallback: true`, no-path fallback, and executorReportPath-only handoff keep the executor prompt inline.
- `tests/test_team_router.py`: added a regression that builds an executor dispatch with a 2400-character prompt plus package paths, asserts the stable paths are present, and asserts the long prompt payload is absent. Added reviewer-required regressions proving inlineFallback-only, no-path, and executorReportPath-only cases keep the long executor prompt inline.
- `docs/workbench.md`: current task/gate state updated to this package.
- `docs/team-router/module-map.md`: prompt transport behavior documented under the facade/contract surface.

## Behavior Changes

- PACKAGE/STRICT-style path handoff can now keep initial executor dispatch messages short when the detailed task prompt is already available through `taskBriefPath` or `reviewPackagePath`.
- Short executor prompts, no-path inline fallback, `inlineFallback: true`, and executorReportPath-only handoff remain inline.
- The role prompt still includes protocol marker, permission, scope, stop condition, direct-return instructions, and return format.

## Verification

- RED: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists -v` -> failed before implementation because the full long prompt was copied under `目标：`.
- GREEN focused: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists -v` -> Ran 1 test OK.
- Reviewer rework RED: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_keeps_long_prompt_inline_without_task_or_review_path -v` -> failed before rework because inlineFallback-only and executorReportPath-only prompts were incorrectly omitted.
- Reviewer rework GREEN: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_keeps_long_prompt_inline_without_task_or_review_path tests.test_team_router.TestTeamRouterProtocol.test_executor_dispatch_omits_long_executor_prompt_when_path_handoff_exists -v` -> Ran 2 tests OK.
- Related prompt template regression: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterProtocol.test_path_handoff_omits_long_callback_raw_from_downstream_prompts tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_preserve_design_gates_but_compact_result_noise -v` -> Ran 3 tests OK.
- Full suite: `py -B -m unittest discover -s tests -p test_team_router.py` -> Ran 347 tests OK after reviewer-required rework.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `skillSync.status: match`; dirty surface limited to this package.
- Doctor check: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`, `underTarget: true`.
- Whitespace check: `git diff --check` -> exit 0 with CRLF/LF warnings only.

## Review And Gate State

- Reviewer: needs_rework by direct-send; required preserving inlineFallback-only/no-taskBriefPath/no-reviewPackagePath executor prompts inline. Rework implemented; reviewer re-review returned `pass` by direct-send with `requiredChanges: none`.
- Verifier: pass by direct-send; requiredChanges none; verified reviewer re-review gate documentation, path handoff omission boundary, and inline fallback behavior.
- Commit: authorized by the user and completed as local closeout.
- Push/PR/merge/deploy/publish/global skill sync: not authorized.
- Real live host integration: external host package gate.

## Risks

- This package changes prompt transport only. It does not generate package files automatically and does not make role threads able to read filesystem paths unless the host/workspace context already permits that.
- If no path handoff metadata is supplied, long inline prompts remain possible by design for inline fallback compatibility.