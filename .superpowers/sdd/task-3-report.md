## Task 3 - Normalize Broker Readiness Into Host Context Evidence
Date: 2026-07-01
Branch: codex/host-rpc-broker-implementation

### Scope followed
- Implemented only in `src/team_router_broker_adapter.py` and `tests/test_team_router.py`.
- Extended `BROKER_ALLOWED_PATHS` with `/readiness` only.
- Did not add `/scheduler/wake`, `BROKER_SCHEDULER_CALLBACKS`, or `BrokerHeartbeatScheduler`.
- No real Codex Desktop/plugin behavior and no external state changes.

### TDD log
1. Added Task 3 readiness tests:
   - `test_fetch_broker_readiness_requires_runtime_probe_ready`
   - `test_broker_host_context_kwargs_returns_adapter_parent_and_project`
   - `test_broker_host_context_kwargs_blocks_without_ready_runtime_probe`
2. Updated the prior Task 1 guard test so it still blocks `/scheduler/wake` while allowing Task 3 to introduce `/readiness`.
3. RED run result: failed with `AttributeError` because `fetch_broker_readiness` and `broker_host_context_kwargs` did not exist yet.
4. Implemented:
   - `_runtime_probe_ready(readiness)`
   - `fetch_broker_readiness(config)`
   - `broker_host_context_kwargs(config)`
5. GREEN run result: all three focused readiness tests passed.

### Implementation summary
- `fetch_broker_readiness(config)` issues `GET /readiness`, routes through `broker_request(...)`, and rejects readiness payloads that omit `runtimeProbe`.
- `broker_host_context_kwargs(config)` now returns:
  - `thread_adapter`
  - `parent_thread_id`
  - `codex_project_id`
  - `readiness`
- `broker_host_context_kwargs(config)` rejects non-ready readiness states, blocked runtime probes, and missing/blank `parentThreadId`.
- No heartbeat scheduler data is returned from the broker adapter in Task 3.

### Verification
- RED:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_fetch_broker_readiness_requires_runtime_probe_ready tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_returns_adapter_parent_and_project tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_blocks_without_ready_runtime_probe -v`
  - Result: expected failure, missing helpers.
- GREEN:
  - `py -B -m unittest tests.test_team_router.TestTeamRouterBrokerAdapter.test_fetch_broker_readiness_requires_runtime_probe_ready tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_returns_adapter_parent_and_project tests.test_team_router.TestTeamRouterBrokerAdapter.test_broker_host_context_kwargs_blocks_without_ready_runtime_probe -v`
  - Result: 3 tests passed.
- Compile:
  - `py -m py_compile src\team_router_broker_adapter.py tests\test_team_router.py`
  - Result: passed.
- Diff hygiene:
  - `git diff --check`
  - Result after newline cleanup: passed.

### Notes
- The sandboxed `apply_patch` path was unavailable in this Windows environment, so the file edits were applied with precise in-workspace PowerShell replacements instead.
