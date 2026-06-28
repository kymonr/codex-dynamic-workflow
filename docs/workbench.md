# Team Router Workbench

This is the project-level working record for the current Team Router task state. It is not the compounding ledger; reusable lessons belong in `docs/compounding.md`. Refresh this file whenever task state, diff surface, verification, or next gate changes.

## Current Task

- State: active local package implementation for `ctr-20260628-host-adapter-heartbeat-smoke`; scope is read-only doctor/status smoke evidence for host adapter readiness and heartbeat scheduler contract.
- Current git truth is sourced from `git status -sb --untracked-files=all`, `git status -s --untracked-files=all`, `git diff --name-only`, `py -B scripts\team_router_truth_check.py --json`, and `py -B scripts\team_router_doctor.py --json`.
- New status surface: `scripts/team_router_doctor.py --host-readiness-json <path> --json` reports `hostReadiness` from a caller-supplied evidence snapshot only. Default without that snapshot remains `orchestrationStatus: manual_only`.
- Current boundary: Codex App thread tools may be exposed to the model, but doctor does not treat model-side tool descriptors as Python callables. `host_contract_blocked` means host evidence is present but callable adapter, `parent_thread_id`, callable `set_thread_title`, or callable heartbeat scheduler evidence is missing. `adapter_smoke_ready` requires all of those in supplied evidence.
- Current next gate: reviewer/verifier focused acceptance for the sync-truth rework; global skill sync is complete and reports `status: match`.
- Not done: no commit, no stage, no push, no PR, no merge, no deploy, and no publish/release. Global skill sync is complete and reports `status: match`.

## Current Diff Surface

Current truth is command-derived, not a copied package list. Regenerate the current surface with:

- `git status -sb --untracked-files=all`
- `git status -s --untracked-files=all`
- `git diff --name-only`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`

During this package, expected touched areas are `scripts/team_router_doctor.py`, `tests/test_team_router.py`, `skills/codex-team-router/references/testing-and-quality-gates.md`, this workbench, and `docs/team-router/packages/ctr-20260628-host-adapter-heartbeat-smoke.md`. The exact list must be taken from fresh commands because the package is still active.

`scripts/team_router_truth_check.py` is the stale-claim gate for workbench/package current-state text. `scripts/team_router_doctor.py` is the plain manager-facing status summary and must not claim live role dispatch unless explicit readiness evidence exists.

## Verification Record

Active package verification so far:

- Focused doctor host readiness tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_host_readiness_snapshot -v` -> OK.
- Focused quality-gate docs test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_host_readiness_snapshots -v` -> OK.
- Default doctor check after code change: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B scripts\team_router_doctor.py --json` -> default `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`; `truthStatus: dirty` because this package is active.
- Focused state suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 43 tests OK.
- Focused docs suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 41 tests OK.
- Final compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> OK.
- Final full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router` -> Ran 277 tests OK.
- Host readiness blocked smoke: `py -B scripts\team_router_doctor.py --host-readiness-json C:\tmp\team-router-host-readiness-blocked.json --json` -> `orchestrationStatus: host_contract_blocked`, `hostReadiness.status: blocked`, `threadToolSurfaceExposed: true`, `parentThreadIdPresent: true`, missing callable adapter/tool methods and callable heartbeat scheduler.
- Truth check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, `truthStatus` inputs dirty because this package is active, `skillSync.status: match` after authorized global skill sync.
- Default doctor check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B scripts\team_router_doctor.py --json` -> `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`, `truthStatus: dirty`.
- Git status: `git status -sb --untracked-files=all` -> `master...origin/master [ahead 2]` with modified `docs/workbench.md`, `scripts/team_router_doctor.py`, `skills/codex-team-router/references/testing-and-quality-gates.md`, `tests/test_team_router.py`, and untracked package doc.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings for existing text files.

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
- Host readiness/status in this package is evidence-only UX; it does not modify dispatch, watcher cadence, registry, ledger, or protocol parsing.

## Addy Engineering Checklists Workbench Note

- Date: 2026-06-28.
- Scope: parent-thread workbench note only; this is not a Team Router runtime, protocol, package, or role-contract change.
- Complex Task Stack may reference selected `addyosmani/agent-skills` checklists as advisory second-layer checks after Superpowers selects the main flow.
- Selected checklist names: `code-review-and-quality`, `doubt-driven-development`, `api-and-interface-design`, `source-driven-development`, `frontend-ui-engineering`, `browser-testing-with-devtools`, `debugging-and-error-recovery`, `security-and-hardening`.
- Team Router impact: no change to manager/executor/reviewer/verifier roles, protocol markers, callback/verdict formats, side-effect taxonomy, closeout gates, or commit/publish authorization.
- Possible future mapping, only if explicitly formalized later: executor uses API/source/debugging checks; reviewer uses review/doubt/security checks; verifier or UI-focused roles use browser/frontend checks.
- This note does not install the full addy library, auto-enable slash commands, load agent personas, run hooks/scripts, commit, push, open PRs, merge, publish, release, or perform global skill sync.

## Current Risks

- This package still cannot prove live orchestration by itself; `adapter_smoke_ready` requires caller-supplied host evidence for Python callables, `parent_thread_id`, callable `set_thread_title`, and heartbeat scheduler.
- `host_contract_blocked` is status evidence, not an adapter implementation or daemon.
- Reviewer/verifier gates remain pending for this active local package; executor verification is complete.
- Git may print CRLF/LF replacement warnings for existing text files.

## Review And Verification Gate

- Current gate: send current diff and verification evidence to reviewer.
- Next gated step: reviewer/verifier focused acceptance. Commit, push, PR, merge, deploy, and publish/release remain unauthorized; global skill sync is already complete/match.