# Broker Host Readiness Injection Implementation Plan

**Goal:** Let an already-running localhost Codex Desktop/plugin broker inject host-readiness evidence into Team Router doctor/status, without starting a production daemon or treating model-side app tools as Python callables.

**Architecture:** Reuse `team_router_broker_adapter.BrokerConfig`, `fetch_broker_readiness()`, `CodexAppThreadAdapter`, and `BrokerHeartbeatScheduler`. Add a pure mapper from broker `/readiness` to the doctor host-readiness snapshot schema, expose it through the feasibility script, and let `team_router_doctor.py` optionally fetch broker readiness when `--broker-url` and `--session-token` are supplied.

**Constraints:** localhost-only broker, read-only readiness fetch for doctor/feasibility, no live role dispatch, no production daemon, no push/PR/merge/deploy/global sync.

### Task 1: Package State

- [x] Create package record and workbench/plan entries.

### Task 2: Tests First

- [x] Add tests for broker readiness -> host-readiness snapshot ready path.
- [x] Add tests for broker readiness blocked path preserving missing runtime evidence, including blocked top-level broker readiness with otherwise-ready tools/runtime.
- [x] Add tests for `team_router_doctor.py --broker-url --session-token --json` injection.
- [x] Add tests for `team_router_broker_feasibility_check.py --json` including `hostReadinessSnapshot`.

### Task 3: Implementation

- [x] Add broker readiness snapshot mapper in `src/team_router_broker_adapter.py`.
- [x] Update feasibility script output.
- [x] Update doctor CLI to fetch broker readiness and merge with explicit `--host-readiness-json` rules.
- [x] Preserve localhost URL and token requirements.

### Task 4: Verification And Gates

- [x] Run focused broker/doctor tests.
- [x] Run full Team Router test module if focused tests pass.
- [x] Run `truth_check`, `doctor`, `closeout_check`, and `git diff --check`.
- [x] Generate review package, reviewer pass, verifier accepted.
- [ ] Local commit only after acceptance. Reviewer v2 pass and verifier accepted; commit pending final clean checks.
