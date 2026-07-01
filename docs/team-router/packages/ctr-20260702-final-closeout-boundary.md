# ctr-20260702-final-closeout-boundary

## Package Metadata

- taskId: `ctr-20260702-final-closeout-boundary`
- branch: `master`
- permission: final closeout package with one docs-only closeout note and local commit. Excludes runtime changes, test changes, live Codex thread-tool calls, independent service work, global skill sync, push, PR, merge, deploy, and publish/release unless separately authorized.
- scope: record the usable boundary, acceptance path, and out-of-project boundary for the current Team Router milestone.

## Closeout Position

This milestone is complete as a manual/evidence-driven Team Router foundation.

Team Router is usable for:

- Manager-facing package flow, evidence handoff, reviewer/verifier gates, and closeout records.
- Codex desktop skill usage when the app exposes `create_thread`, `send_message_to_thread`, `read_thread`, and `set_thread_title`.
- Token-light role dispatch through `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` Markdown package files instead of copying large prompts or evidence into every message.
- Reviewer/verifier direct-return callbacks to the orchestrator via `send_message_to_thread(threadId=<returnThreadId>, prompt=<完整 TEAM_ROUTER_* block>)`, with self-thread marker fallback.
- Deterministic local helper behavior in `src/team_router.py` and related extracted modules.
- Read-only current-truth checks through `scripts/team_router_truth_check.py`.
- Manager-facing status through `scripts/team_router_doctor.py`.
- Closeout checks through `scripts/team_router_closeout_check.py`.
- Manager polling UX based on supplied snapshots, without hidden live `read_thread` calls.
- Host adapter readiness smoke checks through `scripts/team_router_host_adapter_readiness_check.py`, using caller-supplied evidence and synthetic callable-shape validation.

The project should not be described as an independent background service. The intended product shape is a Codex desktop skill plus local helper/readiness scripts. Role-thread creation and reviewer/verifier callback are driven by Codex app thread tools when those tools are available; without those tools, Team Router remains a manual/evidence-driven skill workflow.

## How To Accept This Milestone

Use this lightweight acceptance path from the repo root:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache-final-closeout-truth'
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
git status -sb --untracked-files=all
py -B scripts\team_router_truth_check.py --json
py -B scripts\team_router_doctor.py --json
py -B scripts\team_router_closeout_check.py --json
```

Acceptance criteria:

- `git status -sb --untracked-files=all` shows only the intentional final-closeout doc before commit, and a clean `master...origin/master` state after commit/push if a publish gate is separately opened.
- `team_router_truth_check.py --json` reports `staleClaims: []`.
- `team_router_doctor.py --json` reports `truthStatus` consistent with the worktree state and keeps default `orchestrationStatus: manual_only` when no host-readiness snapshot is supplied.
- `team_router_closeout_check.py --json` exits 0 and remains read-only.
- No live `read_thread`, `send_message_to_thread`, `create_thread`, `list_projects`, `list_threads`, or `set_thread_title` call is required for this acceptance path.

Optional host-adapter readiness smoke:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache-final-closeout-adapter'
$env:TMP='C:\tmp'
$env:TEMP='C:\tmp'
py -B scripts\team_router_host_adapter_readiness_check.py --adapter-snapshot-json tests\fixtures\team_router\host_adapter_callable_ready_snapshot.json --json
py -B scripts\team_router_host_adapter_readiness_check.py --adapter-snapshot-json tests\fixtures\team_router\host_adapter_model_descriptors_blocked_snapshot.json --json
```

Expected smoke result:

- Callable ready fixture reports `status: ready`, `orchestrationStatus: adapter_smoke_ready`, and zero thread-tool executions.
- Descriptor-only fixture reports `status: blocked` / `orchestrationStatus: host_contract_blocked`, proving model-side descriptors are not enough.

## Out Of Project

The following work is intentionally not part of this milestone:

- Building or shipping an independent background service.
- Starting a daemon outside Codex desktop.
- Adding a separate production scheduler.
- Calling real Codex desktop thread tools from local acceptance scripts.
- Replacing Markdown package handoff with copied long prompts or raw evidence blobs.
- Adding account, token, secret, network, deployment, or production-data requirements.
- Changing Team Router runtime contracts beyond the already committed helper/readiness surfaces.

Future work should focus on better prompt compression into Markdown package files and reliable direct-return callback handling for reviewer/verifier roles. It should stay inside the Codex desktop skill model unless a separate authorization explicitly changes that boundary.
