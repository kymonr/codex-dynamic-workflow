# ctr-20260702-final-closeout-boundary

## Package Metadata

- taskId: `ctr-20260702-final-closeout-boundary`
- branch: `master`
- permission: final closeout package with one docs-only closeout note and local commit. Excludes runtime changes, test changes, live Codex thread-tool calls, broker/adapter/scheduler startup, global skill sync, push, PR, merge, deploy, and publish/release unless separately authorized.
- scope: record the usable boundary, acceptance path, and out-of-project boundary for the current Team Router milestone.

## Closeout Position

This milestone is complete as a manual/evidence-driven Team Router foundation.

Team Router is usable for:

- Manager-facing package flow, evidence handoff, reviewer/verifier gates, and closeout records.
- Deterministic local helper behavior in `src/team_router.py` and related extracted modules.
- Read-only current-truth checks through `scripts/team_router_truth_check.py`.
- Manager-facing status through `scripts/team_router_doctor.py`.
- Closeout checks through `scripts/team_router_closeout_check.py`.
- Manager polling UX based on supplied snapshots, without hidden live `read_thread` calls.
- Host adapter readiness smoke checks through `scripts/team_router_host_adapter_readiness_check.py`, using caller-supplied evidence and synthetic callable-shape validation.

The project should not be described as a production live orchestration broker. The current default runtime state remains manual orchestration unless a caller supplies a real host adapter snapshot and the host environment provides callable Codex thread tools plus scheduler support.

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

- Starting or shipping a production broker.
- Starting a live host adapter daemon.
- Scheduling real heartbeat reads.
- Calling real Codex desktop thread tools.
- Creating child role threads automatically from this local package.
- Replacing manual package handoff with background live orchestration.
- Adding account, token, secret, network, deployment, or production-data requirements.
- Changing Team Router runtime contracts beyond the already committed helper/readiness surfaces.

Future live orchestration work should start as a separate milestone with its own authorization, evidence package, reviewer/verifier gates, and explicit host-environment proof.
