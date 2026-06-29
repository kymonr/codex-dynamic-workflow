# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: closeout recorded for `ctr-20260629-workbench-current-truth-doctor-ux`; review and verification gates accepted.
- Last package objective: make stale workbench/package current-state claims visible when live git/skill truth is clean/synced, and make `scripts/team_router_doctor.py --json` tell managers to refresh current-state text from fresh truth tools before claiming current truth.
- Current git truth must come from fresh commands, not this copied text: `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- Current boundary: no live orchestration, no module extraction, no push, no PR, no merge, no deploy, no publish/release. Global skill sync for `codex-team-router` is complete and reports `status: match`.
- Current next gate: after this local closeout commit, open `module extraction phase 1: policy/protocol split` only on explicit dispatch.

## Current Diff Surface

Current truth is command-derived. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

This file intentionally does not list a live diff surface. The closeout package files are recorded in the review package, and the exact current surface must be taken from fresh commands before any new claim.

`scripts/team_router_truth_check.py` is the stale-current-state gate for workbench/package text. It should focus on Current Task / Current Diff Surface style sections so historical package archives are not treated as live truth. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must remain read-only/evidence-only.

## Verification Record

Active package verification:

- Focused stale-current-state tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_truth_check_detects_stale_current_state_when_clean_synced tests.test_team_router.TestTeamRouterState.test_truth_check_does_not_flag_clean_synced_neutral_current_sections tests.test_team_router.TestTeamRouterState.test_truth_check_does_not_flag_historical_package_records_as_current tests.test_team_router.TestTeamRouterState.test_truth_check_reports_stale_claims_and_is_read_only tests.test_team_router.TestTeamRouterState.test_router_doctor_stale_next_action_names_truth_check_and_doctor tests.test_team_router.TestTeamRouterState.test_router_doctor_reports_plain_status_without_dispatch -v` -> Ran 6 tests OK.
- Rework synthetic clean/synced probe: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -c "... find_stale_state_claims(... ## Current Diff Surface ... Current next gate: none; no action required ...)"` -> `[]`.
- Focused docs contract tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_workbench_tracks_current_task_without_stale_diff_surface tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_name_truth_and_doctor_read_only_tools -v` -> Ran 2 tests OK.
- Full docs suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 46 tests OK.
- Compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m py_compile scripts\team_router_truth_check.py scripts\team_router_doctor.py tests\test_team_router.py` -> OK.
- Full relevant state suite attempt: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-current-truth-ux'; py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 47 tests; 46 OK, 1 unrelated existing failure in `test_protocol_contract_snapshot_includes_manager_orchestration_policy` because current runtime snapshot includes architect/QA direct-return markers while this assertion expects only executor/reviewer/verifier markers.
- Closeout check after global sync: `py -B scripts\team_router_closeout_check.py --json` -> `skillSync.status: match`; no global skill reference differences; package files still present in local diff before commit.
- Truth check after global sync: `py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`; package files still present in local diff before commit; `skillSync.status: match`.
- Doctor check after global sync: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: dirty` before commit; `orchestrationStatus: manual_only`; top-level `nextAction` present.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings only.

## Historical Records

Older entries are history only. They must not be treated as current git truth / current next gate unless rechecked in the current worktree.

- Previous `ctr-20260628-role-thread-readiness-status` completed read-only role-thread status UX in `scripts/team_router_doctor.py`; it added `--role-status-json` and `roleThreadStatus` from supplied snapshots only.
- Previous `ctr-20260628-live-capability-state-fix` clarified exposed app tools versus missing Python callable adapter/runtime orchestration. That remains the baseline boundary for this package.
- Previous `ctr-20260628-trust-and-modularity` is a completed historical package covering the current-state truth checker, module split plan, and initial doctor/status UX. Its recorded diff surface, verifier evidence, and sync state are not current git truth.
- Previous `ctr-20260628-team-router-optimization-1-6` is a completed historical package. Its recorded dirty surface, skill sync result, reviewer evidence, and P2 step labels are not current git truth.
- Previous `ctr-20260628-team-router-optimization-local-package` records are historical baseline only; they are not the current active package.
- Previous `ctr-20260628-anchor-and-closeout-freshness-fix` records: verifier accepted/pass; prior local closeout/commit language is historical and no longer the Current Task.
- Previous `ctr-20260628-role-request-direct-send-and-waiting-fix` records are accepted/pass at reviewer and verifier gates.
- Previous `ctr-20260628-workbench-tool-error-governance` records described a no-tools governance state. That wording is historical and must not be copied into the current state now that the Codex app thread tool surface is exposed.
- Older ahead/behind, stale current diff surface, isolated-worktree status, and old executor callback references are not current status. If a completed task still points at an old executor callback, collect fresh role-thread evidence or mark it historical instead of reusing it as current truth.
- Historical records may explain why a rule exists, but current status must come from fresh `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, the truth/doctor scripts, and latest role-thread marker evidence.

## Integration Boundary

- `src/team_router.py` remains a deterministic helper library.
- Runtime/docs/tests changes require an active package plus reviewer/verifier gates.
- Workbench current state must not claim old completed tasks as active work.
- Stale-current-state detection and doctor nextAction in this package are evidence-only UX; they do not modify dispatch, watcher cadence, registry, ledger, or protocol parsing.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- The stale-current-state detector is intentionally section-scoped. It should catch manager-facing current-state drift but avoid broad historical archive scans.
- `scripts/team_router_doctor.py` remains evidence-only; `nextAction` is guidance, not protocol acceptance.
- One broader `TestTeamRouterState` assertion unrelated to this package currently fails on architect/QA marker drift; this package records it as a validation blocker rather than changing runtime contract.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: reviewer and verifier passed for this package; global skill sync is complete.
- Next gated step: local closeout commit for this package. Push, PR, merge, deploy, publish/release, and module extraction remain separate explicit gates.