# Team Router Handoff Package: ctr-20260628-role-communication-economy

## Task Summary / 任务摘要

- taskId: `ctr-20260628-role-communication-economy`
- objective: Add a tested Team Router contract for saving role-thread tokens without weakening executor/reviewer/verifier accuracy gates.
- scope: `src/team_router.py`, `tests/test_team_router.py`, `skills/codex-team-router/SKILL.md`, `skills/codex-team-router/references/role-handoff-and-review-package.md`, `docs/compounding.md`, this package, and the implementation plan.
- reviewPackagePath: `docs/team-router/packages/ctr-20260628-role-communication-economy.md`

## Protocol References / 协议引用

- Expected executor marker: `TEAM_ROUTER_CALLBACK`
- Expected reviewer marker for policy/process change: `TEAM_ROUTER_REVIEW`
- Expected verifier marker: `TEAM_ROUTER_VERDICT`
- Gate class: PACKAGE/STRICT semantics because this changes Team Router role communication policy.

## Touched Files / 触及文件

- `src/team_router.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/SKILL.md`
- `skills/codex-team-router/references/role-handoff-and-review-package.md`
- `docs/compounding.md`
- `docs/superpowers/plans/2026-06-28-team-router-role-communication-economy.md`
- `docs/team-router/packages/ctr-20260628-role-communication-economy.md`

## Behavior Changes / 行为变化

- Adds `roleCommunicationEconomy` under `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY`, exposed through `protocol_contract_snapshot()`.
- Makes the contract explicit: save tokens by using protocol blocks, stable path references, and delta-only follow-up; do not remove executor/reviewer/verifier gates.
- Documents manager closeout as a compact summary of `acceptedBy`, changed, verified, remainingRisk, nextGate, and `compoundingDecision` rather than copied role reasoning.
- Adds non-authoritative token budget hints for dispatch, executor callback, reviewer, and verifier messages.

## Diff Summary / Diff 摘要

- `tests/test_team_router.py`: added a focused contract test that initially failed with `KeyError: 'roleCommunicationEconomy'`.
- `src/team_router.py`: added the new policy object inside the existing handoff/review-package policy.
- `skills/codex-team-router/SKILL.md`: added a short entrypoint paragraph.
- `skills/codex-team-router/references/role-handoff-and-review-package.md`: added the detailed `Role Communication Economy` section.
- `docs/compounding.md`: records the durable process lesson.

## Verification / 验证

- Red: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_role_communication_economy_policy_keeps_gates_but_limits_chat` -> failed with `KeyError: 'roleCommunicationEconomy'`.
- Green focused: `py -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_role_communication_economy_policy_keeps_gates_but_limits_chat` -> `Ran 1 test` and `OK`.
- Focused docs suite: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> `Ran 42 tests` and `OK`.
- Full Team Router suite: `py -B -m unittest tests.test_team_router` -> `Ran 278 tests` and `OK`.

- Final compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-role-economy'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> exit 0.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings for existing text files.
- Truth check: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `skill.entrypointBytes: 7171`, `skill.underTarget: true`, `skillSync.status: mismatch` because global sync is not authorized in this package.
- Closeout check: `py -B scripts\team_router_closeout_check.py --json` -> read-only report, `skill.entrypointBytes: 7171`, `skill.underTarget: true`, unauthorized commit/push/globalSync gates false in the report.

## Excluded Changes / 未纳入改动

- No runtime adapter, watcher, scheduler, registry, ledger, or parser behavior changes.
- No push, PR, merge, deploy, release, or global skill sync.
- No workbench truth refresh in this package; current workbench hardcoded tests are left for a separate focused refresh if requested.

## Risks / 风险

- Token budget hints are guidance only. They must not become a parser requirement or a reason to omit evidence.
- Path-based handoff still depends on role access to the same workspace; inline fallback remains allowed when explicitly marked.

## Remaining Todos / 剩余事项

- Commit only this task's accepted files after final diff/status checks.
- Global skill sync remains a separate unauthorized gate; current repo/global skill status is expected `mismatch` until explicitly authorized.
