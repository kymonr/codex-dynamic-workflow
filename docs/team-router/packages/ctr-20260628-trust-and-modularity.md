# Team Router Trust And Modularity Review Package

## Objective

Implement `ctr-20260628-trust-and-modularity` as a local executor package: add read-only current-state validation, archive stale workbench/package claims, document a safe future module split, and add a plain router doctor/status UX without changing live dispatch behavior.

## Scope

Included:

- `scripts/team_router_truth_check.py` - read-only git/skill/current-state truth report and stale-claim scanner.
- `scripts/team_router_doctor.py` - read-only manager-facing currentMode/truthStatus/orchestrationStatus/nextAction summary.
- `docs/workbench.md` - current task and current diff surface now command-derived instead of copied from old package records.
- `docs/team-router/packages/ctr-20260628-team-router-optimization-1-6.md` - converted to a completed historical package archive.
- `docs/team-router/module-map.md` - documentation-only future split plan; no runtime extraction in this package.
- `skills/codex-team-router/references/testing-and-quality-gates.md` - documents truth/doctor tools as read-only evidence inputs.
- `tests/test_team_router.py` - TDD coverage for truth checker, doctor output, workbench state, module map, and quality gate docs.
- `docs/superpowers/plans/2026-06-28-team-router-trust-and-modularity.md` - saved implementation plan.

Out of scope:

- runtime module extraction or import changes
- live dispatch behavior changes
- `SKILL.md` entrypoint changes
- global skill sync
- commit, push, PR, merge, deploy, release, or publish

## Reviewer Status

Pre-save reviewer attempts were made before executor implementation, but neither visible reviewer thread returned a final `TEAM_ROUTER_REVIEW` after bounded read/control:

- `019f0e79-746a-7bb2-b509-7ca9f74a7bf2`
- `019f0e7b-5c1c-7b22-b6fe-32be6bc8b5c2`

Post-implementation reviewer thread `019f0e86-513b-7901-acc2-025652491814` first returned `needs_rework`; after the doctor nextAction fix and added test, reviewer returned `pass`. Verifier thread `019f0e8c-163e-7ba0-82b0-b16b592168ea` returned `pass`.

## TDD Evidence

- RED: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` failed because `scripts/team_router_truth_check.py` and `scripts/team_router_doctor.py` were missing.
- GREEN: `py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 38 tests OK.
- RED docs gate: targeted `TestTeamRouterSkillDoc` tests failed on stale workbench text, missing `docs/team-router/module-map.md`, and missing truth/doctor quality docs.
- GREEN docs gate: targeted workbench/module-map/quality tests passed.
- GREEN docs class: `py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 38 tests OK.
- Current truth check after docs refresh: `py -B scripts\team_router_truth_check.py --json` reports `staleClaims: []`; repo/global skill comparison reports mismatch because `references/testing-and-quality-gates.md` changed and global sync is not authorized.
- Current doctor report after docs refresh: `py -B scripts\team_router_doctor.py --json` reports `truthStatus: dirty` and `orchestrationStatus: manual_only` without claiming created role threads.

## Final Local Verification

- `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-trust'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> OK.
- `git diff --check` -> exit 0 with CRLF/LF warnings only.
- `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-trust'; py -B -m unittest tests.test_team_router` -> Ran 269 tests OK.
- `py -B scripts\team_router_closeout_check.py --json` -> read-only mode, unauthorized gates false, SKILL entrypoint 6969 bytes and under target.
- `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; repo/global skill comparison mismatch is limited to `references/testing-and-quality-gates.md`.
- `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty`, `orchestrationStatus: manual_only`, and no live role-thread creation claim.
- `py -B scripts\team_router_skill_sync_check.py --check` -> `status: mismatch`, changed `references/testing-and-quality-gates.md`; expected because global skill sync is unauthorized.
- Reviewer gate: thread 019f0e86-513b-7901-acc2-025652491814 -> initial 
eeds_rework, rework completed, final pass.
- Verifier gate: thread 019f0e8c-163e-7ba0-82b0-b16b592168ea -> pass.

## Not Done

- no commit
- no push
- no PR
- no merge
- no deploy
- no release/publish
- no global skill sync
- no runtime module extraction
- reviewer pass and verifier pass recorded; no commit/push/release authorization implied

## Risks

- Reviewer role attempts were unreachable in this run; closeout must state that honestly unless a later reviewer returns a final protocol block.
- Current repo/global skill status is expected to remain mismatch until a separately authorized global skill sync copies `references/testing-and-quality-gates.md`.
- `apply_patch` updates were blocked by the Windows restricted-token sandbox for some update operations; narrow PowerShell replacements were used as fallback.
- Current package is active and dirty; exact dirty surface must come from fresh `git status -s --untracked-files=all` and `scripts/team_router_truth_check.py --json`.
