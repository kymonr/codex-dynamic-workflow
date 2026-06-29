# Team Router Handoff Package: ctr-20260629-module-extraction-phase1-policy-protocol

## Task Summary / 任务摘要

- taskId: `ctr-20260629-module-extraction-phase1-policy-protocol`
- objective: Team Router module extraction phase 1: split protocol parsing and pure gate policy out of `src/team_router.py` while preserving `import team_router` compatibility.
- result: local implementation complete; reviewer gate still required before verifier.
- reviewPackagePath: `docs/team-router/packages/ctr-20260629-module-extraction-phase1-policy-protocol.md`

## Scope / 范围

Authorized and touched files:

- `src/team_router.py`
- `src/team_router_protocol.py`
- `src/team_router_policy.py`
- `tests/test_team_router.py`
- `docs/team-router/module-map.md`
- `docs/team-router/packages/ctr-20260629-module-extraction-phase1-policy-protocol.md`

No skill docs, registry/ledger runtime extraction, adapter runtime extraction, direct-return capture extraction, watcher/heartbeat extraction, closeout/status extraction, commit, stage, push, PR, release, deploy, publish, or global skill sync were performed.

## Architect Pass / 架构通过点

Architect pass allowed a conservative split with strict dependency direction:

- `team_router_protocol.py` -> Python standard library only.
- `team_router_policy.py` -> `team_router_protocol.ProtocolError` only.
- `team_router.py` -> protocol + policy as public facade/consumer.
- `protocol_contract_snapshot()` remains in `src/team_router.py` because it still aggregates marker schema, role/state/orchestration policy, side-effect taxonomy, closeout policy, and review-package policy.

## Protocol References / 协议引用

- Final callback marker: `TEAM_ROUTER_CALLBACK taskId=ctr-20260629-module-extraction-phase1-policy-protocol`
- Direct return target: `returnThreadId=019f12cc-f7b3-7633-947c-647fbc027dce`
- Role thread: `sourceRoleThreadId=019f1334-820b-7890-87e9-307bd7684c14`
- Permission: `local-package`

## Behavior Changes / 行为变化

- Protocol parsing implementation moved to `src/team_router_protocol.py`.
- Gate policy constants/classifiers moved to `src/team_router_policy.py`.
- `src/team_router.py` re-exports moved names so existing `import team_router` callers continue to use the same public/private symbol surface.
- `protocol_contract_snapshot()` output shape remains centralized in `src/team_router.py` and continues to expose sorted marker `allowedValues`.
- No runtime behavior change was intended for registry/ledger, adapter runtime, direct return, watcher/heartbeat, closeout/status, or scripts.

## Diff Summary / Diff 摘要

- Added `src/team_router_protocol.py` with `ProtocolError`, `ProtocolMessage`, marker regexes, parser tables, `_validate_task_id()`, `_iter_marker_blocks()`, `parse_message()`, `parse_plan()`, `parse_callback()`, `parse_verdict()`, and `parse_review()`.
- Added `src/team_router_policy.py` with reviewer/architect/QA gate terms, `GATE_CLASSES`, gate classifiers, route explanation helpers, and reviewer-required logic.
- Updated `src/team_router.py` to import/re-export moved protocol and policy names; left state/runtime/direct-return/watcher/status code in place.
- Updated `tests/test_team_router.py` to lock facade re-export identity and the current architect/QA direct-return marker map in `managerOrchestrationPolicy`.
- Updated `docs/team-router/module-map.md` from a future sketch to the implemented phase 1 dependency map.

## Verification / 验证

Passed:

- `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol -v` with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache`, `TMP=C:\tmp`, `TEMP=C:\tmp`: 30 tests OK.
- Focused architect/QA marker and gate tests: 5 tests OK.
- Required snapshot/policy state tests: 5 tests OK.
- `py -B -m py_compile src\team_router.py src\team_router_protocol.py src\team_router_policy.py tests\test_team_router.py` with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache`, `TMP=C:\tmp`, `TEMP=C:\tmp`: pass.
- `py -B -m unittest discover -s tests -p test_team_router.py -v` with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache`, `TMP=C:\tmp`, `TEMP=C:\tmp`: 332 tests OK.
- `py -B scripts\team_router_truth_check.py --json` with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache`, `TMP=C:\tmp`, `TEMP=C:\tmp`: pass; `staleClaims: []`; `skillSync.status: match`; unauthorized commit/push/PR/merge/deploy/globalSync all false.
- `py -B scripts\team_router_doctor.py --json` with `PYTHONPYCACHEPREFIX=C:\tmp\team-router-pycache`, `TMP=C:\tmp`, `TEMP=C:\tmp`: pass; `truthStatus: dirty` as expected for this local package; nextAction says reviewer pass then verifier pass; `orchestrationStatus: manual_only` because no host readiness snapshot was supplied.
- `git diff --check`: pass.

Initial environment-only note:

- The first `py -B -m py_compile ...` without `PYTHONPYCACHEPREFIX` failed with `[WinError 5] 拒绝访问: 'src\__pycache__\team_router.cpython-313.pyc.<temp>' -> 'src\__pycache__\team_router.cpython-313.pyc'`. Rerunning with the temp pycache prefix passed.

## Excluded Changes / 未纳入改动

- No changes to `skills/codex-team-router/SKILL.md` or reference skill docs.
- No extraction of registry/ledger state, adapter runtime, direct-return capture, watcher/heartbeat, closeout/status, scripts, or fixtures.
- No dependency installation, network access, real API access, commit, stage, push, PR, merge, deploy, publish/release, or global skill sync.

## Risks / 风险

- `gate_class_requires_reviewer()` now lives in `team_router_policy.py` and raises `ProtocolError` for a blank/non-string gate class instead of the old facade-local `StateStoreError`; current tests cover valid classes and invalid unknown strings, not this exact exception type for blank input.
- Remaining risk is review/verification judgment, not a known local validation failure.

## Remaining Todos / 剩余事项

- Reviewer gate required before verifier.
- No local commit/stage/push/PR/global sync has been done.
