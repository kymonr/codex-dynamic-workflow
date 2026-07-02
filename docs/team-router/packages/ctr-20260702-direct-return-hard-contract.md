# Team Router Handoff Package: ctr-20260702-direct-return-hard-contract

## Task Summary / 任务摘要

- taskId: `ctr-20260702-direct-return-hard-contract`
- objective: 收紧 executor/reviewer/verifier role request prompt 的 direct-return 合同；当 manager 提供 `returnThreadId` 时，prompt 必须硬性要求 direct-return 三行；当没有 `returnThreadId` 时，prompt 必须明确 `self-thread-marker only`，不暗示 direct-return。
- gateClass: `PACKAGE`
- permission: `local-package`
- execution mode: focused runtime prompt helper + tests + package/workbench records only; no broker/service expansion, no commit, no push, no PR, no merge, no deploy, no global skill sync.

## Hard Contract / 硬合同

When `returnThreadId` is present, executor/reviewer/verifier role request prompts must all include:

- `returnThreadId: <manager-thread-id>`
- `MUST call send_message_to_thread(threadId=<returnThreadId>, prompt=<full TEAM_ROUTER_* block>)`
- `Then print the same full TEAM_ROUTER_* block in this thread as fallback.`

When `returnThreadId` is absent, the prompt must say `returnContract: self-thread-marker only` and must not tell the role to call `send_message_to_thread(...)`.

This package keeps the compact path-first reviewer/verifier templates parser-compatible. `replyFields` stay:

- reviewer: `result,summary,findings,requiredChanges,evidenceChecked,risks,next`
- verifier: `result,summary,requiredChanges,evidenceChecked,risks,next`

## Scope / 范围

Touched files for this package:

- `src/team_router.py`
- `tests/test_team_router.py`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260702-direct-return-hard-contract.md`

## Verification / 验证

- RED focused suite first failed because compact reviewer/verifier prompts still used the old `returnContract: direct-send ... then same block fallback` summary, detailed executor/reviewer/verifier prompts lacked the new hard English lines, and the no-`returnThreadId` path did not say `self-thread-marker only`.
- Reviewer rework: legacy direct-return metadata tests in `tests/test_team_router.py` still asserted the old Chinese direct-return wording and same-protocol-body phrasing for reviewer/verifier; this rework updates those assertions to the hard three-line contract.
- Reviewer rework legacy suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-rework-legacy py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_reviewer_request_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterManagerIntegration.test_verifier_request_supports_direct_return_delivery_metadata -v` -> Ran 2 tests OK.
- GREEN focused suite: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-green2 py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_executor_dispatch_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_role_request_prompts_without_return_thread_id_are_self_thread_marker_only -v` -> Ran 6 tests OK.
- Reviewer rework focused suite rerun: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-rework-focused py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_executor_dispatch_supports_direct_return_delivery_metadata tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_reviewer_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_package_paths_uses_minimal_protocol_template tests.test_team_router.TestTeamRouterProtocol.test_verifier_request_with_inline_fallback_without_paths_keeps_detailed_template tests.test_team_router.TestTeamRouterProtocol.test_role_request_prompts_without_return_thread_id_are_self_thread_marker_only -v` -> Ran 6 tests OK.
- Compile: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-compile py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- Reviewer rework compile rerun: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-rework-compile py -B -m py_compile src\team_router.py tests\test_team_router.py` -> exit 0.
- `git diff --check` -> exit 0; Git printed CRLF/LF replacement warnings for `docs/workbench.md`, `src/team_router.py`, and `tests/test_team_router.py` only.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-truth py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; dirty surface is `docs/workbench.md`, `src/team_router.py`, `tests/test_team_router.py`, plus this package doc; `skillSync.status: mismatch` remains historical/unrelated because global sync is not authorized in this package.
- `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-doctor py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `nextAction` remains reviewer then verifier before closeout.
- Reviewer rework truth/doctor rerun: `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-rework-truth py -B scripts\team_router_truth_check.py --json` -> exit 0 with `staleClaims: []`; `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache-direct-return-rework-doctor py -B scripts\team_router_doctor.py --json` -> exit 0 with `truthStatus: dirty` and `orchestrationStatus: manual_only`.

## Excluded Changes / 未纳入改动

- No parser/runtime ledger changes.
- No watcher/scheduler changes.
- No broker/service or live thread-tool expansion.
- No commit, push, PR, merge, deploy, publish/release, or global skill sync.

## Risks / 风险

- Compact path prompts are slightly denser after adding the hard direct-return lines; focused tests keep them under the current template size caps and preserve parser-compatible reply fields.

## Remaining Todos / 剩余事项

- Reviewer/verifier gates remain external; no commit authorization is included in this package.
