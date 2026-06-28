# Team Router Handoff Package: ctr-20260628-compact-role-templates

## Task Summary / 任务摘要

- taskId: `ctr-20260628-compact-role-templates`
- objective: Make executor/reviewer/verifier request templates default to compact path-based outputs without changing gate semantics.
- scope: `src/team_router.py`, `tests/test_team_router.py`, `skills/codex-team-router/references/role-handoff-and-review-package.md`, and this package.
- reviewPackagePath: `docs/team-router/packages/ctr-20260628-compact-role-templates.md`

## Protocol References / 协议引用

- Executor marker remains `TEAM_ROUTER_CALLBACK`.
- Reviewer marker remains `TEAM_ROUTER_REVIEW`.
- Verifier marker remains `TEAM_ROUTER_VERDICT`.
- Gate semantics are unchanged: FAST/NORMAL still use executor -> verifier; STRICT/PACKAGE still use executor -> reviewer -> verifier.

## Touched Files / 触及文件

- `src/team_router.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/references/role-handoff-and-review-package.md`
- `docs/team-router/packages/ctr-20260628-compact-role-templates.md`

## Behavior Changes / 行为变化

- Adds shared `roleCommunicationMode: concise-protocol-plus-paths` instructions to role handoff prompts.
- Adds `deltaSince` to executor callback, reviewer review, and verifier verdict templates.
- Adds `executorReportPath` to executor callback template and `reviewPackagePath` to reviewer/verifier templates.
- Instructs roles not to copy complete diffs, logs, background, or role reasoning into protocol replies.

## Diff Summary / Diff 摘要

- `src/team_router.py`: adds `ROLE_COMMUNICATION_ECONOMY_PROMPT_LINES` and includes it in `_role_handoff_prompt_lines()`; updates role output templates with compact path/delta fields.
- `tests/test_team_router.py`: adds `test_role_request_templates_default_to_compact_path_based_outputs`.
- `skills/codex-team-router/references/role-handoff-and-review-package.md`: documents the concrete template fields.

## Verification / 验证

- Red: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs` -> failed because templates lacked `roleCommunicationMode` and compact path/delta fields.
- Green focused: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs` -> `Ran 1 test` and `OK`.
- Protocol suite: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v` -> `Ran 17 tests` and `OK`.
- Boundary regression: `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_request_templates_default_to_compact_path_based_outputs tests.test_team_router.TestTeamRouterManagerIntegration.test_read_only_plain_low_risk_callback_still_routes_to_verifier -v` -> `Ran 2 tests` and `OK`.
- Full Team Router suite: `py -B -m unittest tests.test_team_router` -> `Ran 279 tests` and `OK`.
- Final compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-compact-templates'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> exit 0.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings for existing text files.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `skill.entrypointBytes: 7171`, `skill.underTarget: true`, `skillSync.status: mismatch` because global sync is not authorized in this package.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> read-only report, `skill.entrypointBytes: 7171`, `skill.underTarget: true`, unauthorized commit/push/globalSync gates false in the report.

## Excluded Changes / 未纳入改动

- No parser requirement change for optional compact fields.
- No runtime adapter, watcher, scheduler, registry, or ledger behavior change.
- No commit, push, PR, merge, deploy, release, or global skill sync in this package unless separately authorized.

## Risks / 风险

- Compact fields are template guidance and optional protocol fields; they must not become grounds to reject otherwise valid legacy role replies.
- Path-based evidence still depends on shared workspace access; inline fallback remains valid when explicitly marked.

## Remaining Todos / 剩余事项

- Commit/global skill sync remain separate unauthorized gates.
