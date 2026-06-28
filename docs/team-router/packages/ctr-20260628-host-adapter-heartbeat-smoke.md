# Team Router Handoff Package: ctr-20260628-host-adapter-heartbeat-smoke

## Task Summary / 任务摘要

- taskId: `ctr-20260628-host-adapter-heartbeat-smoke`
- objective: 推进 Team Router Host Adapter + heartbeat smoke 的确定性状态面，让 `scripts/team_router_doctor.py --json` 能在默认无证据时保持 `manual_only`，并在 caller-supplied host evidence 存在时明确表达 callable adapter / `parent_thread_id` / callable `set_thread_title` / heartbeat scheduler 的 smoke readiness 或 blocker。
- gateClass: `PACKAGE`
- permission: `local-package`
- execution mode: executor local implementation; no daemon, no live orchestration fabrication, no commit, no push, no PR, no release/publish. Global skill sync is complete and reports `status: match`.

## Current Truth / 当前事实

- `src/team_router.py` already contains deterministic readiness and watcher helpers including `assess_live_orchestration_readiness()`, `parent_entry_guard()`, `make_live_orchestration_host_context()`, `orchestrate_team_task_with_adapter()`, and `watch_team_task_with_adapter()`.
- Current change keeps `src/team_router.py` untouched. It adds a doctor/status smoke surface only.
- Default `py -B scripts\team_router_doctor.py --json` still reports `orchestrationStatus: manual_only` when no host readiness snapshot is supplied.
- New `--host-readiness-json <path>` accepts an evidence-only host adapter readiness snapshot. It reports `hostReadiness` and derives `orchestrationStatus` as:
  - `manual_only` when no snapshot is supplied.
  - `host_contract_blocked` when evidence is supplied but callable adapter, callable tool methods, explicit `parent_thread_id`, callable `set_thread_title`, or callable heartbeat scheduler evidence is missing.
  - `adapter_smoke_ready` only when supplied evidence proves callable thread tools, callable `set_thread_title`, explicit `parent_thread_id`, and callable heartbeat scheduler.
- Boundary remains explicit: model-side Codex app tool exposure is not a Python callable adapter.

## Touched Files / 触及文件

- `scripts/team_router_doctor.py`
- `tests/test_team_router.py`
- `skills/codex-team-router/references/testing-and-quality-gates.md`
- `docs/workbench.md`
- `docs/team-router/packages/ctr-20260628-host-adapter-heartbeat-smoke.md`

## Behavior Changes / 行为变化

- Added `classify_host_readiness_snapshot()` to `scripts/team_router_doctor.py`.
- Added `--host-readiness-json <path>` to `scripts/team_router_doctor.py`.
- Added `hostReadiness` to the doctor JSON report.
- Kept role-thread snapshot support (`--role-status-json`) and default manual-only behavior.
- Added tests for blocked host-contract evidence and ready adapter-heartbeat smoke evidence without calling real thread tools.
- Documented the new status surface in `skills/codex-team-router/references/testing-and-quality-gates.md` and `docs/workbench.md`.

## Verification / 验证

- Focused doctor host readiness tests: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_host_readiness_snapshot -v` -> OK.
- Focused quality-gate docs test: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc.test_quality_gates_document_host_readiness_snapshots -v` -> OK.
- Default doctor check after code change: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B scripts\team_router_doctor.py --json` -> `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`, `truthStatus: dirty` because this package is active.
- Focused state suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterState -v` -> Ran 43 tests OK.
- Focused docs suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router.TestTeamRouterSkillDoc -v` -> Ran 41 tests OK.
- Final compile: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m py_compile src\team_router.py tests\test_team_router.py scripts\team_router_closeout_check.py scripts\team_router_truth_check.py scripts\team_router_doctor.py` -> OK.
- Final full suite: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B -m unittest tests.test_team_router` -> Ran 277 tests OK.
- Host readiness blocked smoke: `py -B scripts\team_router_doctor.py --host-readiness-json C:\tmp\team-router-host-readiness-blocked.json --json` -> `orchestrationStatus: host_contract_blocked`, `hostReadiness.status: blocked`, `threadToolSurfaceExposed: true`, `parentThreadIdPresent: true`, missing callable adapter/tool methods and callable heartbeat scheduler.
- Truth check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B scripts\team_router_truth_check.py --json` -> `staleClaims: []`, dirty diff present for this active package, `skillSync.status: match` after authorized global skill sync.
- Default doctor check: `$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-smoke'; py -B scripts\team_router_doctor.py --json` -> `orchestrationStatus: manual_only`, `hostReadiness.status: not_supplied`, `truthStatus: dirty`.
- Git status: `git status -sb --untracked-files=all` -> `master...origin/master [ahead 2]` with modified `docs/workbench.md`, `scripts/team_router_doctor.py`, `skills/codex-team-router/references/testing-and-quality-gates.md`, `tests/test_team_router.py`, and untracked package doc.
- Whitespace check: `git diff --check` -> exit 0; Git printed CRLF/LF normalization warnings for existing text files.

## Not Done / 未纳入改动

- No live orchestration daemon.
- No production scheduler.
- No app-level callable adapter implementation inside this repo.
- No direct claim that model-side Codex tool descriptors are Python callables.
- No commit, stage, push, PR, merge, deploy, or publish/release. Global skill sync is complete and reports `status: match`.
- No project-local `AGENTS.md` changes.

## Risks / 风险

- `adapter_smoke_ready` is only as strong as the supplied host snapshot; this repo still cannot inspect Codex App tool descriptors as Python callables by itself.
- A real host must still supply actual Python callable wrapper methods and heartbeat scheduler wiring to execute `orchestrate_team_task_with_adapter()` / `watch_team_task_with_adapter()`.
- Reviewer/verifier gates are still required before accepting the package.

## Reviewer Placeholder / 审查者占位

- reviewerThreadId: `019f0ec5-fa08-7d30-ab7a-d641cd8e01d0`
- status: pending reviewer pass
- requiredChanges: pending

## Verifier Placeholder / 验证者占位

- verifierThreadId: `019f0ec6-07f0-7a31-890c-870923c81795`
- status: pending verifier pass after reviewer
- requiredChanges: pending