# Team Router Host Adapter Scheduler Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the repo-local Team Router host adapter/scheduler contract so a later Codex Desktop host bridge can prove strict automatic orchestration without manual create/read role handling.

**Architecture:** Keep true host bridging outside this repo. Add repo-local tests and small helpers that make the boundary explicit: doctor readiness must require runtime-probe evidence, scheduler payloads must be materializable into real `watch_team_task_with_adapter()` kwargs, adapter result schemas must stay locked, and role-specific delivery fields must cover Executor, Reviewer, Verifier, Architect, and QA.

**Tech Stack:** Python standard library, `unittest`, existing Team Router modules under `src/`, `scripts/team_router_doctor.py`.

## Global Constraints

- No Codex Desktop/plugin host bridge implementation in this package.
- No fake adapter wrapping model-side tool descriptors as real Python callables.
- No daemon or production heartbeat scheduler.
- No replacement of visible Team Router role threads with native subagents or `multi_agent_v1`.
- Preserve direct-send first, bounded `read_thread` fallback only.
- Preserve watcher timing: `FIRST_ROLE_CHECK_DELAY_SECONDS = 30`, `MIN_ROLE_POLL_INTERVAL_SECONDS = 300`.
- Current host state without supplied callable evidence remains `manual_only` or `host_contract_blocked`, never live automatic orchestration.
- Use Windows-safe verification when needed: set `PYTHONPYCACHEPREFIX`, `TMP`, and `TEMP` under `C:\tmp`.

---

## File Structure

- Modify `scripts/team_router_doctor.py`: require runtime readiness probe evidence before reporting `adapter_smoke_ready`.
- Modify `src/team_router_watcher_runtime.py`: add a pure helper that materializes scheduler heartbeat payloads into `watch_team_task_with_adapter()` call kwargs.
- Modify `src/team_router.py`: re-export the scheduler materializer through the public facade.
- Modify `src/team_router.py`: add a small role delivery-field map used by policy text and role prompt builders.
- Modify `tests/test_team_router.py`: add focused tests for host readiness parity, scheduler kwargs materialization, adapter result schemas, and Architect/QA delivery field coverage.
- Optional docs update if tests require it: `docs/team-router/module-map.md` only if new helper ownership needs explicit documentation.

---

### Task 1: Require Runtime Probe Evidence For Adapter Smoke Readiness

**Files:**
- Modify: `scripts/team_router_doctor.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: `classify_host_readiness_snapshot(snapshot: dict[str, object] | None) -> dict[str, object]`
- Produces: doctor `adapter_smoke_ready` only when callable evidence and `runtimeProbe.status == "ready"` are both present

- [ ] **Step 1: Write failing doctor parity test**

Add near existing host readiness doctor tests in `tests/test_team_router.py`:

```python
    def test_router_doctor_requires_runtime_probe_for_adapter_smoke_ready(self):
        spec = importlib.util.spec_from_file_location(
            "team_router_doctor_under_test",
            ROOT / "scripts" / "team_router_doctor.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        base_snapshot = {
            "adapterCallable": True,
            "callableTools": list(module.REQUIRED_THREAD_TOOLS),
            "parentThreadId": "parent-thread",
            "heartbeatSchedulerCallable": True,
        }

        blocked = module.classify_host_readiness_snapshot(base_snapshot)

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["orchestrationStatus"], "host_contract_blocked")
        self.assertIn("runtime readiness probe", blocked["missing"])
        self.assertFalse(blocked["evidence"]["runtimeProbeReady"])

        ready_snapshot = dict(base_snapshot)
        ready_snapshot["runtimeProbe"] = {"status": "ready", "missing": []}

        ready = module.classify_host_readiness_snapshot(ready_snapshot)

        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["orchestrationStatus"], "adapter_smoke_ready")
        self.assertEqual(ready["missing"], [])
        self.assertTrue(ready["evidence"]["runtimeProbeReady"])
```

- [ ] **Step 2: Run test and confirm it fails**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_requires_runtime_probe_for_adapter_smoke_ready -v
```

Expected: FAIL because `runtime readiness probe` is not required yet.

- [ ] **Step 3: Add runtime probe helper inside doctor script**

In `scripts/team_router_doctor.py`, add helper near `_heartbeat_scheduler_callable()`:

```python
def _runtime_probe_ready(snapshot: dict[str, object]) -> bool:
    probe = _first_present(snapshot, ("runtimeProbe", "runtime_probe", "runtimeReadiness"))
    if not isinstance(probe, dict):
        return False
    status = str(probe.get("status") or "").strip().lower()
    missing = probe.get("missing")
    if missing is None:
        missing = []
    return status == "ready" and isinstance(missing, list) and not missing
```

- [ ] **Step 4: Require probe in `classify_host_readiness_snapshot()`**

In `classify_host_readiness_snapshot()`, after `heartbeat_callable` is computed, add:

```python
    runtime_probe_ready = _runtime_probe_ready(snapshot)
```

After the heartbeat missing check, add:

```python
    if not runtime_probe_ready:
        missing.append("runtime readiness probe")
```

Inside `evidence`, add:

```python
            "runtimeProbeReady": runtime_probe_ready,
```

- [ ] **Step 5: Run focused doctor tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_requires_runtime_probe_for_adapter_smoke_ready -v
```

Expected: FAIL in old ready snapshot tests until snapshots include `runtimeProbe`.

- [ ] **Step 6: Update existing ready snapshots only**

In existing ready host readiness tests, add this field to snapshots that expect `adapter_smoke_ready`:

```python
"runtimeProbe": {"status": "ready", "missing": []},
```

Do not add it to blocked snapshots unless the test explicitly needs runtime probe ready but another capability missing.

- [ ] **Step 7: Re-run focused doctor tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterState.test_router_doctor_classifies_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_includes_host_readiness_snapshot tests.test_team_router.TestTeamRouterState.test_router_doctor_requires_runtime_probe_for_adapter_smoke_ready -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

```powershell
git add scripts\team_router_doctor.py tests\test_team_router.py
git commit -m "test: require runtime probe for host readiness smoke"
```

---

### Task 2: Materialize Watcher Scheduler Payload Into Runtime Kwargs

**Files:**
- Modify: `src/team_router_watcher_runtime.py`
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Consumes: scheduler payload from `build_watcher_heartbeat_payload(...)`
- Produces: `materialize_watcher_call_kwargs(payload, *, thread_adapter, observed_at=None, heartbeat_scheduler=None, turn_limit=None) -> dict[str, Any]`

- [ ] **Step 1: Write failing materializer test**

Add near watcher/heartbeat integration tests in `tests/test_team_router.py`, inside `TestTeamRouterManagerIntegration`:

```python
    def test_watcher_runtime_materializes_scheduler_payload_kwargs(self):
        adapter = FakeThreadAdapter()
        scheduler = FakeHeartbeatScheduler()
        update = {
            "status": "awaiting_callback",
            "watcher": {
                "role": "executor",
                "threadId": "thread-executor",
                "expectedMarker": "TEAM_ROUTER_CALLBACK taskId=task-1",
                "firstCheckAt": "2026-07-01T10:00:30+08:00",
                "nextAllowedReadAt": "2026-07-01T10:05:00+08:00",
                "lastReadAt": None,
            },
        }
        payload = team_router_watcher_runtime.build_watcher_heartbeat_payload(
            update,
            state_root=self.root,
            project_id=self.project_id,
            task_id="task-1",
            permission="read-only",
            return_thread_id="parent-thread",
        )

        kwargs = team_router.materialize_watcher_call_kwargs(
            payload,
            thread_adapter=adapter,
            heartbeat_scheduler=scheduler,
            turn_limit=3,
        )

        self.assertEqual(kwargs["state_root"], str(Path(self.root)))
        self.assertEqual(kwargs["project_id"], self.project_id)
        self.assertEqual(kwargs["task_id"], "task-1")
        self.assertEqual(kwargs["permission"], "read-only")
        self.assertEqual(kwargs["return_thread_id"], "parent-thread")
        self.assertEqual(kwargs["read_reason"], "scheduled watcher heartbeat")
        self.assertEqual(kwargs["observed_at"], payload["runAt"])
        self.assertIs(kwargs["thread_adapter"], adapter)
        self.assertIs(kwargs["heartbeat_scheduler"], scheduler)
        self.assertEqual(kwargs["turn_limit"], 3)
```

- [ ] **Step 2: Write failing invalid-payload test**

Add:

```python
    def test_watcher_runtime_rejects_non_watcher_scheduler_payload(self):
        with self.assertRaises(team_router.ProtocolError) as ctx:
            team_router.materialize_watcher_call_kwargs(
                {"callback": "other_callback", "kwargs": {}},
                thread_adapter=FakeThreadAdapter(),
            )

        self.assertIn("watch_team_task_with_adapter", str(ctx.exception))
```

- [ ] **Step 3: Run tests and confirm they fail**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watcher_runtime_materializes_scheduler_payload_kwargs tests.test_team_router.TestTeamRouterManagerIntegration.test_watcher_runtime_rejects_non_watcher_scheduler_payload -v
```

Expected: FAIL because `materialize_watcher_call_kwargs` does not exist.

- [ ] **Step 4: Implement helper in watcher runtime**

In `src/team_router_watcher_runtime.py`, add after `build_watcher_heartbeat_payload()`:

```python
def _watch_arg(payload_args: Mapping[str, Any], snake_name: str, camel_name: str) -> Any:
    if snake_name in payload_args:
        return payload_args[snake_name]
    return payload_args.get(camel_name)


def materialize_watcher_call_kwargs(payload: Mapping[str, Any],
                                    *,
                                    thread_adapter: Any,
                                    observed_at: str | None = None,
                                    heartbeat_scheduler: Any = None,
                                    turn_limit: int | None = None) -> dict[str, Any]:
    callback = payload.get("callback") or payload.get("managerAction")
    if callback != "watch_team_task_with_adapter":
        raise ProtocolError("scheduler payload callback must be watch_team_task_with_adapter")
    raw_args = payload.get("kwargs") if isinstance(payload.get("kwargs"), Mapping) else payload.get("watchArgs")
    if not isinstance(raw_args, Mapping):
        raise ProtocolError("scheduler payload requires kwargs or watchArgs")
    observed = observed_at or payload.get("runAt")
    if not isinstance(observed, str) or not observed:
        raise ProtocolError("scheduler payload requires runAt or explicit observed_at")
    out = {
        "state_root": _required_str(_watch_arg(raw_args, "state_root", "stateRoot"), "state_root"),
        "project_id": _required_str(_watch_arg(raw_args, "project_id", "projectId"), "project_id"),
        "task_id": _required_str(_watch_arg(raw_args, "task_id", "taskId"), "task_id"),
        "permission": _required_str(raw_args.get("permission"), "permission"),
        "thread_adapter": thread_adapter,
        "observed_at": observed,
        "read_reason": _required_str(_watch_arg(raw_args, "read_reason", "readReason"), "read_reason"),
    }
    return_thread_id = _watch_arg(raw_args, "return_thread_id", "returnThreadId")
    if isinstance(return_thread_id, str) and return_thread_id:
        out["return_thread_id"] = return_thread_id
    if heartbeat_scheduler is not None:
        out["heartbeat_scheduler"] = heartbeat_scheduler
    if turn_limit is not None:
        out["turn_limit"] = turn_limit
    return out
```

- [ ] **Step 5: Re-export through facade**

In `src/team_router.py`, extend the `team_router_watcher_runtime` import block with:

```python
    materialize_watcher_call_kwargs,
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_watcher_runtime_materializes_scheduler_payload_kwargs tests.test_team_router.TestTeamRouterManagerIntegration.test_watcher_runtime_rejects_non_watcher_scheduler_payload tests.test_team_router.TestTeamRouterState.test_watcher_runtime_builds_facade_watcher_ledger tests.test_team_router.TestTeamRouterState.test_watcher_runtime_does_not_call_heartbeat_scheduler -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add src\team_router.py src\team_router_watcher_runtime.py tests\test_team_router.py
git commit -m "feat: materialize watcher scheduler payloads"
```

---

### Task 3: Lock Adapter Result Schema Contracts

**Files:**
- Modify: `tests/test_team_router.py`
- Modify only if tests expose a gap: `src/team_router_runtime.py`

**Interfaces:**
- Consumes: `_thread_id_from_create_result(create_result: Any, role: str) -> str`, `thread_send_anchor(send_result: Any, fallback_sent_at: str) -> dict[str, Any]`, `normalize_thread_read_messages(read_result: Any) -> list[dict[str, Any]]`
- Produces: focused tests proving accepted and rejected adapter result shapes

- [ ] **Step 1: Add create-thread schema tests**

Add near existing adapter normalization tests in `TestTeamRouterManagerIntegration`:

```python
    def test_create_thread_result_schema_accepts_common_thread_id_shapes(self):
        cases = [
            ({"threadId": "thread-a"}, "thread-a"),
            ({"thread_id": "thread-b"}, "thread-b"),
            ({"id": "thread-c"}, "thread-c"),
            ({"thread": {"id": "thread-d"}}, "thread-d"),
            ({"data": {"threadId": "thread-e"}}, "thread-e"),
            ({"result": {"thread_id": "thread-f"}}, "thread-f"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(team_router._thread_id_from_create_result(raw, "executor"), expected)

    def test_create_thread_result_schema_rejects_missing_thread_id(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router._thread_id_from_create_result({"thread": {"title": "Executor"}}, "executor")

        self.assertIn("create_thread result missing thread id", str(ctx.exception))
```

- [ ] **Step 2: Add read-thread schema rejection test**

Add:

```python
    def test_read_thread_result_schema_rejects_missing_messages_array(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.normalize_thread_read_messages({"thread": {"title": "Executor"}})

        self.assertIn("messages array", str(ctx.exception))
```

- [ ] **Step 3: Run schema tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterManagerIntegration.test_create_thread_result_schema_accepts_common_thread_id_shapes tests.test_team_router.TestTeamRouterManagerIntegration.test_create_thread_result_schema_rejects_missing_thread_id tests.test_team_router.TestTeamRouterManagerIntegration.test_read_thread_result_schema_rejects_missing_messages_array tests.test_team_router.TestTeamRouterManagerIntegration.test_thread_send_anchor_normalizes_common_tool_shapes -v
```

Expected: PASS if existing parser already satisfies the contract. If a test fails, change only `src/team_router_runtime.py` normalization helpers to satisfy the exact schema above.

- [ ] **Step 4: Commit Task 3**

```powershell
git add tests\test_team_router.py src\team_router_runtime.py
git commit -m "test: lock adapter result schemas"
```

If `src/team_router_runtime.py` is unchanged, omit it from `git add`.

---

### Task 4: Centralize Role Delivery Field Names

**Files:**
- Modify: `src/team_router.py`
- Modify: `tests/test_team_router.py`

**Interfaces:**
- Produces: `ROLE_DELIVERY_FIELDS: dict[str, tuple[str, str]]`
- Consumes: role prompt builders and policy snapshot

- [ ] **Step 1: Write failing role delivery field map test**

Add near policy snapshot tests:

```python
    def test_role_delivery_fields_cover_all_direct_return_roles(self):
        expected = {
            "executor": ("callbackDelivery", "callbackFallback"),
            "reviewer": ("reviewDelivery", "reviewFallback"),
            "verifier": ("verdictDelivery", "verdictFallback"),
            "architect": ("architectReviewDelivery", "architectReviewFallback"),
            "qa": ("qaReviewDelivery", "qaReviewFallback"),
        }

        self.assertEqual(team_router.ROLE_DELIVERY_FIELDS, expected)
```

- [ ] **Step 2: Extend policy snapshot test for Architect/QA fields**

In the existing `callbackDeliveryModel` policy test, add assertions:

```python
        self.assertIn("architectReviewDelivery: direct-send", model["requiredDispatchFields"])
        self.assertIn("architectReviewFallback: self-thread-marker", model["requiredDispatchFields"])
        self.assertIn("qaReviewDelivery: direct-send", model["requiredDispatchFields"])
        self.assertIn("qaReviewFallback: self-thread-marker", model["requiredDispatchFields"])
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_delivery_fields_cover_all_direct_return_roles tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_includes_active_role_return_model -v
```

Expected: FAIL because `ROLE_DELIVERY_FIELDS` does not exist or policy snapshot omits Architect/QA fields.

- [ ] **Step 4: Add field map in `src/team_router.py`**

Near role constants/policy definitions, add:

```python
ROLE_DELIVERY_FIELDS = {
    "executor": ("callbackDelivery", "callbackFallback"),
    "reviewer": ("reviewDelivery", "reviewFallback"),
    "verifier": ("verdictDelivery", "verdictFallback"),
    "architect": ("architectReviewDelivery", "architectReviewFallback"),
    "qa": ("qaReviewDelivery", "qaReviewFallback"),
}
```

- [ ] **Step 5: Add Architect/QA fields to policy snapshot**

In `MANAGER_ORCHESTRATION_POLICY["callbackDeliveryModel"]["requiredDispatchFields"]`, include:

```python
            "architectReviewDelivery: direct-send",
            "architectReviewFallback: self-thread-marker",
            "qaReviewDelivery: direct-send",
            "qaReviewFallback: self-thread-marker",
```

- [ ] **Step 6: Run role delivery tests**

Run:

```powershell
py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_role_delivery_fields_cover_all_direct_return_roles tests.test_team_router.TestTeamRouterProtocol.test_protocol_contract_snapshot_includes_active_role_return_model tests.test_team_router.TestTeamRouterManagerIntegration.test_architect_review_request_prompt_contains_direct_return_contract tests.test_team_router.TestTeamRouterManagerIntegration.test_qa_review_request_prompt_contains_direct_return_contract -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```powershell
git add src\team_router.py tests\test_team_router.py
git commit -m "docs: lock role delivery field map"
```

---

### Task 5: Full Contract Verification And Closeout

**Files:**
- Modify only if previous tasks require: `docs/team-router/module-map.md`
- No runtime change expected in this task

**Interfaces:**
- Consumes: all previous task changes
- Produces: verified repo-local contract hardening package, still no host bridge claim

- [ ] **Step 1: Run compile check**

Run:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-bridge-contract'; py -B -m py_compile src\team_router.py src\team_router_host_runtime.py src\team_router_watcher_runtime.py src\team_router_runtime.py scripts\team_router_doctor.py tests\test_team_router.py
```

Expected: exit 0, no syntax errors.

- [ ] **Step 2: Run focused host bridge contract tests**

Run:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-bridge-contract'; py -B -m unittest tests.test_team_router -k host_readiness -k watcher_runtime -k heartbeat -k direct_return -k delivery_fields -v
```

Expected: all selected tests PASS.

If `-k delivery_fields` selects zero tests because unittest substring behavior differs, run the exact method command from Task 4 Step 6.

- [ ] **Step 3: Run full Team Router test file**

Run:

```powershell
$env:PYTHONPYCACHEPREFIX='C:\tmp\pycache-team-router-host-bridge-contract'; py -B -m unittest discover -s tests -p test_team_router.py -v
```

Expected: full suite PASS.

- [ ] **Step 4: Run truth and doctor checks**

Run:

```powershell
py -B scripts\team_router_truth_check.py --json
py -B scripts\team_router_doctor.py --json
```

Expected:

```text
truth_check staleClaims: []
doctor without host readiness snapshot: orchestrationStatus manual_only, hostReadiness.status not_supplied
```

- [ ] **Step 5: Run whitespace and status checks**

Run:

```powershell
git diff --check
git status -sb --untracked-files=all
```

Expected: whitespace check exit 0. Status shows only files intentionally changed by this implementation package.

- [ ] **Step 6: Commit final verification/doc adjustment if needed**

If Task 5 changed docs or tests, commit them:

```powershell
git add docs\team-router\module-map.md tests\test_team_router.py
git commit -m "test: verify host bridge contract hardening"
```

If no files changed in Task 5, skip commit.

## Self-Review Notes

Spec coverage:

- Host callable blocker: Task 1.
- Scheduler runtime injection contract: Task 2.
- Adapter result schema: Task 3.
- Architect/QA delivery fields: Task 4.
- No false live orchestration claim: Task 1 and Task 5 doctor checks.
- 30 second first check and 300 second cadence: Task 2 and existing watcher tests.
- Direct-send and fallback boundaries: Task 4 plus existing direct-return tests in focused/full verification.

Placeholder scan: no banned placeholder phrases remain in this plan.

Type consistency: `materialize_watcher_call_kwargs(...)`, `ROLE_DELIVERY_FIELDS`, `runtimeProbe`, `watchArgs`, and `kwargs` names are consistent across tasks.

## Execution Choice

Plan complete. Execute later with one of two modes:

1. Subagent-Driven: fresh worker per task, review between tasks.
2. Inline Execution: execute tasks in this session with checkpoints.
