# Team Router Cost-Aware Role Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Native subagents are prohibited by this feature contract; visible Team Router role threads may be used only under an authorized dispatch package.

**Goal:** Replace fixed child-Manager/Executor/Verifier orchestration for new tasks with a manager-owned v2 flow that directly handles small work, dynamically routes visible role threads across Luna Medium, Terra Medium, and Sol High, reuses roles safely, and preserves all version 1 tasks.

**Architecture:** Keep the current version 1 path intact. Add the versioned v2 plan/orchestration path in `team_router_v2.py`, extend the existing `team_router_state.py` state primitives with manager-owned role-pool locking and claims, and reuse existing protocol parsing/direct-return helpers. The facade selects Manager direct before creating state, selects v1 for legacy ledgers, and selects delegated v2 only when the current parent provides a resolved manager plan and task authorization package.

**Tech Stack:** Python 3 standard library, JSON state files, Codex desktop thread-tool adapter, `unittest`, existing Team Router protocol/status modules.

## Global Constraints

- Do not modify `C:\Users\Orz\.codex\AGENTS.md`.
- Do not use native `spawn_agent` or collaboration subagents as Team Router fallback.
- New visible role bootstrap uses `gpt-5.6-luna` with `thinking: medium`.
- Default execution routing is mechanical -> Luna Medium, standard -> Terra Medium, high -> Sol High.
- Explicit role models are used only when the task authorization package contains `modelRoutingAuthorization` naming Luna Medium, Terra Medium, and Sol High, or the user explicitly authorizes a complete per-request override; plain `你作为管理者，完成 <目标>` alone does not supply that authorization.
- Reject every role request with `model: gpt-5.6-sol` and `thinking: ultra` before any thread-tool call.
- The current parent Manager model is unrestricted.
- Each task permits at most one automatic model upgrade and one automatic rework.
- FAST/NORMAL may end through structured Manager acceptance; STRICT/PACKAGE always require Reviewer and Verifier.
- Version 1 nonterminal ledgers keep the child Manager and old role registry until terminal.
- Review-only/explicit zero-write tasks must not create role threads or write registry/ledger state without separate thread-state authorization.
- No new runtime dependency; use Python standard library and existing modules.
- Keep `skills/codex-team-router/SKILL.md` below 8 KB and preferably below 7,200 bytes.
- Repo/global skill mismatch is expected after repo skill edits and before the separately authorized global sync gate.
- Each implementation task ends in a scoped commit only after the execution plan itself is authorized.

---

## File Structure

- `src/team_router_state.py`: schema versions, v1/v2 role constants, ledger normalization, manager-pool-compatible registry shape, lock, creation intent, and role claim/release.
- `src/team_router_policy.py`: pure effective-gate, route-closure, per-role model resolution, and Sol Ultra rejection.
- `src/team_router_v2.py` (new): task authorization package, resolved Manager plan, v2 state transitions, role requests, Manager acceptance.
- `src/team_router.py`: facade exports, existing adapter calls, workflow-version dispatch, parent entry wiring, v1 compatibility.
- `src/team_router_status.py`: v2 role-pool thread display and Manager-acceptance closeout formatting.
- `tests/test_team_router.py`: all pure policy, state, adapter, concurrency, v1 compatibility, and end-to-end regression tests.
- `skills/codex-team-router/SKILL.md`: short v2 Manager Mode entrypoint and links.
- `skills/codex-team-router/references/*.md`: detailed authorization, routing, lifecycle, direct-return, testing, and closeout contracts.
- `docs/runbooks/codex-team-router-live-orchestration.md`: live v1/v2 operator flow.
- `docs/team-router/module-map.md`: ownership of the new v2 module and expanded state responsibilities.

---

## Review Anchors

**What already exists:**

- `team_router_state.py` already owns atomic JSON writes, registry normalization, ledger normalization, and role-record validation; v2 pool state extends these primitives instead of adding a second state module.
- `team_router.py` already owns project-target resolution, role title normalization, adapter calls, parent title handling, direct return, and watcher integration; v2 reuses these paths through the facade.
- `team_router_policy.py` already owns the legacy v1 gate classifier. V2 adds a separate effective-gate path so legacy `local-package -> STRICT` behavior remains recoverable while v2 stops treating the permission name as risk by itself.
- `team_router_status.py` already owns handoff and closeout formatting; v2 extends its inputs instead of adding a second formatter.

**NOT in scope:**

- Native subagents, implicit model inheritance, automatic queues, role pre-creation, billing/token estimation, new dependencies, global `AGENTS.md`, push, PR, merge, and deploy.
- Refactoring unrelated v1 parser, protocol, watcher, or direct-return behavior.
- Updating reference files that contain no stale v2-invalid contract after targeted `rg` discovery.

**Execution and coverage map:**

```text
authorized parent request
  -> permission validation
  -> effective gate (v2 ignores local-package name as risk)
  -> execution mode
       -> manager_direct: no ledger, registry, title change, heartbeat, or role tool
       -> delegated:
            route closure -> complete roleRouting -> persist resolved plan
             -> derive and validate targetFingerprint
             -> claim/reuse or creation intent with parallelAllowed
                  -> one verified match: list_threads + read_thread identity recovery
                  -> zero/multiple verified matches: terminal tool_error, preserve recovery evidence, never auto-create again
            -> create with structured target when needed
            -> formal send with explicit model/thinking
            -> callback risk reclassification
                 -> one parent-approved model upgrade may carry only the failed delta
                 -> FAST/NORMAL: Manager acceptance
                 -> STRICT/PACKAGE: Reviewer -> Verifier
            -> terminal claim cleanup and routing receipt
legacy ledger -> unchanged v1 child-Manager flow
```

---

### Task 0: Execution Entry And Plan Baseline Commit

**Gate:** Do not execute this task until the user explicitly confirms execution of this reviewed plan. That execution confirmation opens this scoped docs commit; it does not authorize Task 1 implementation before Task 0 passes.

**Files:**
- Commit only:
  - `docs/superpowers/specs/2026-07-11-cost-aware-role-routing-design.md`
  - `docs/superpowers/plans/2026-07-11-cost-aware-role-routing.md`

- [ ] **Step 1: Reconfirm the design baseline and isolated plan diff**

```powershell
git status -s --untracked-files=all
git rev-parse --short HEAD
```

Expected: HEAD is `f484892`, and the only uncommitted paths are the reviewed design file plus this plan file. Any other path or a different HEAD requires a fresh scope review before execution.

- [ ] **Step 2: Validate and commit the reviewed plan**

```powershell
git add docs/superpowers/specs/2026-07-11-cost-aware-role-routing-design.md docs/superpowers/plans/2026-07-11-cost-aware-role-routing.md
git diff --cached --check
git diff --cached -- docs/superpowers/specs/2026-07-11-cost-aware-role-routing-design.md
git diff --cached -- docs/superpowers/plans/2026-07-11-cost-aware-role-routing.md
git commit -m "docs: plan cost-aware role routing implementation"
```

Expected: one docs-only commit containing exactly the reviewed design and plan. Record its hash as the implementation baseline; Tasks 1-8 must follow it without unrelated commits.

---

### Task 1: Versioned Role And Model Policy Primitives

**Files:**
- Modify: `src/team_router_state.py:19-80`
- Modify: `src/team_router_policy.py:1-280`
- Modify: `src/team_router.py:1042-1110`
- Test: `tests/test_team_router.py`

**Interfaces:**
- Produces: `LEGACY_CORE_ROLE_NAMES`, `V2_DELEGATED_BASE_ROLE_NAMES`, `V2_CONDITIONAL_ROLE_NAMES`.
- Produces: `resolve_role_model(execution_class, *, model=None, thinking=None, override_reason=None) -> dict[str, Any]`.
- Produces: `resolve_effective_gate(requested_gate_class, ledger, *, authorization) -> dict[str, Any]`.
- Produces: `resolve_v2_execution_mode(effective_gate_class, *, explicit_roles=(), requires_parallelism=False, requires_independent_context=False, requires_independent_review=False, lightweight_verification_available=True) -> str`.
- Produces: `resolve_v2_route(effective_gate_class, explicit_roles) -> tuple`, containing zero or more validated role-name strings in dispatch order.
- Preserves: current v1 `ROLE_NAMES`, parser markers, and `CORE_ROLE_NAMES` compatibility alias until all old callers are migrated.

- [ ] **Step 1: Add failing tests for versioned role sets and snapshot output**

```python
def test_versioned_role_contract_keeps_legacy_manager_but_v2_does_not_create_it(self):
    self.assertEqual(
        team_router.LEGACY_CORE_ROLE_NAMES,
        frozenset({"manager", "executor", "verifier"}),
    )
    self.assertEqual(team_router.V2_DELEGATED_BASE_ROLE_NAMES, frozenset({"executor"}))
    self.assertNotIn("manager", team_router.V2_DELEGATED_BASE_ROLE_NAMES)
    snapshot = team_router.protocol_contract_snapshot()
    self.assertEqual(snapshot["workflowContracts"]["v1"]["coreRoles"], ["executor", "manager", "verifier"])
    self.assertEqual(snapshot["workflowContracts"]["v2"]["baseRoles"], ["executor"])
```

- [ ] **Step 2: Add failing tests for default routing, complete overrides, and Sol Ultra rejection**

```python
def test_resolve_role_model_defaults_and_rejects_sol_ultra(self):
    self.assertEqual(
        team_router.resolve_role_model("mechanical"),
        {"executionClass": "mechanical", "requestedModel": "gpt-5.6-luna", "requestedThinking": "medium"},
    )
    with self.assertRaisesRegex(team_router.StateStoreError, "model_override_invalid"):
        team_router.resolve_role_model("standard", model="gpt-5.5")
    with self.assertRaisesRegex(team_router.StateStoreError, "model_forbidden"):
        team_router.resolve_role_model(
            "high",
            model="gpt-5.6-sol",
            thinking="ultra",
            override_reason="manual override",
        )
```

- [ ] **Step 3: Add failing tests for Manager direct and v1/v2 `local-package` separation**

```python
def test_v2_manager_direct_is_decided_before_route_closure(self):
    mode = team_router.resolve_v2_execution_mode(
        "NORMAL",
        explicit_roles=(),
        requires_parallelism=False,
        requires_independent_context=False,
        requires_independent_review=False,
        lightweight_verification_available=True,
    )
    self.assertEqual(mode, "manager_direct")

def test_v2_local_package_permission_does_not_raise_risk_by_name(self):
    ledger = {"workflowVersion": 2, "objective": "ordinary local docs update", "permission": "local-package"}
    resolved = team_router.resolve_effective_gate(
        "NORMAL", ledger, authorization={"workspaceWrite": True}
    )
    self.assertEqual(resolved["effectiveGateClass"], "NORMAL")
    self.assertEqual(team_router.classify_team_router_gate(ledger), "STRICT")
```

Add table-driven assertions that any explicit role, required parallelism, independent context/review, absent lightweight verification, or `STRICT/PACKAGE` gate selects `delegated`. The final assertion above is a **CRITICAL v1 compatibility regression test**: the legacy classifier remains unchanged while only the v2 resolver removes permission-name escalation.

Model authorization is deliberately not part of `resolve_role_model()`: this pure helper only resolves a model after authorization. Task 4 must reject every delegated plan lacking `modelRoutingAuthorization` before this helper, state storage, title changes, heartbeat setup, or adapter calls.

- [ ] **Step 4: Run the focused tests and confirm RED**

Run:

```powershell
py -m unittest discover -s tests -p test_team_router.py -k versioned_role_contract -k resolve_role_model -k v2_manager_direct -k v2_local_package -v
```

Expected: FAIL because the versioned constants and resolver do not exist.

- [ ] **Step 5: Implement the minimal constants and model resolver**

```python
LEGACY_CORE_ROLE_NAMES = frozenset({"manager", "executor", "verifier"})
V2_DELEGATED_BASE_ROLE_NAMES = frozenset({"executor"})
V2_CONDITIONAL_ROLE_NAMES = frozenset({"reviewer", "verifier", "architect", "qa"})
CORE_ROLE_NAMES = LEGACY_CORE_ROLE_NAMES

DEFAULT_ROLE_MODELS = {
    "mechanical": ("gpt-5.6-luna", "medium"),
    "standard": ("gpt-5.6-terra", "medium"),
    "high": ("gpt-5.6-sol", "high"),
}
FORBIDDEN_ROLE_MODEL_COMBINATIONS = frozenset({("gpt-5.6-sol", "ultra")})

def resolve_role_model(execution_class, *, model=None, thinking=None, override_reason=None):
    if execution_class not in DEFAULT_ROLE_MODELS:
        raise StateStoreError("invalid executionClass: %s" % execution_class)
    supplied = (model is not None, thinking is not None, override_reason is not None)
    if any(supplied) and not all(supplied):
        raise StateStoreError("model_override_invalid: model, thinking, and modelOverrideReason are required together")
    requested_model, requested_thinking = DEFAULT_ROLE_MODELS[execution_class]
    result = {"executionClass": execution_class}
    if all(supplied):
        requested_model = str(model)
        requested_thinking = str(thinking)
        result["modelOverrideReason"] = str(override_reason)
    if (requested_model, requested_thinking) in FORBIDDEN_ROLE_MODEL_COMBINATIONS:
        raise StateStoreError("model_forbidden: gpt-5.6-sol ultra")
    result.update({"requestedModel": requested_model, "requestedThinking": requested_thinking})
    return result
```

- [ ] **Step 6: Implement effective-gate, execution-mode, and delegated route-closure helpers**

```python
def resolve_v2_route(effective_gate_class, explicit_roles=()):
    roles = set(explicit_roles)
    roles.add("executor")
    if effective_gate_class in {"STRICT", "PACKAGE"}:
        roles.update({"reviewer", "verifier"})
    if "reviewer" in roles or "qa" in roles:
        roles.add("verifier")
    order = ("architect", "executor", "reviewer", "qa", "verifier")
    return tuple(role for role in order if role in roles)
```

`resolve_effective_gate()` must validate authorization, preserve both `requestedGateClass` and `effectiveGateClass`, never lower the requested gate, and force Team Router runtime/policy/process/permission/safety/role-protocol changes to `STRICT` or `PACKAGE`. It must reuse existing term checks but must not call the legacy classifier in a way that turns v2 `local-package` into `STRICT`; `classify_team_router_gate()` and `reviewer_gate_required_for_ledger()` retain their current v1 behavior.

`resolve_v2_execution_mode()` runs after the effective gate and before `resolve_v2_route()`. Only FAST/NORMAL with no explicit role, parallelism, independent-context/review need, and with lightweight verification returns `manager_direct`. Every other case returns `delegated`. `resolve_v2_route()` is called only for delegated work and therefore continues to add Executor.

- [ ] **Step 7: Run focused tests and existing gate tests**

Run:

```powershell
py -m unittest discover -s tests -p test_team_router.py -k versioned_role_contract -k resolve_role_model -k v2_manager_direct -k v2_local_package -k classify_team_router_gate -k reviewer_gate_required -v
```

Expected: all selected tests PASS.

- [ ] **Step 8: Commit Task 1**

```powershell
git add src/team_router_state.py src/team_router_policy.py src/team_router.py tests/test_team_router.py
git commit -m "feat: add versioned routing policy primitives"
```

---

### Task 2: Registry V2 And Workflow-Version Compatibility

**Files:**
- Modify: `src/team_router_state.py:190-515`
- Modify: `src/team_router.py:1042-1110`
- Test: `tests/test_team_router.py`

**Interfaces:**
- Produces: registry schema version 2 with legacy `roles` plus `managerPools`.
- Produces: `new_v2_task_ledger(state_root, project_id, task_id, *, objective, project_local_path, parent_thread_id, resolved_plan, task_authorization_package, created_at, max_rework=1) -> dict[str, Any]`.
- Produces: `task_workflow_version(ledger) -> int`.
- Preserves: `new_task_ledger()` and `create_team_task()` as version 1 entrypoints.

- [ ] **Step 1: Add failing registry/ledger compatibility tests**

```python
def test_registry_v2_preserves_legacy_roles_and_adds_manager_pools(self):
    registry = team_router.load_registry(self.root, self.project_id)
    project = registry["projects"][self.project_id]
    self.assertEqual(registry["version"], 2)
    self.assertEqual(project["roles"], {})
    self.assertEqual(project["managerPools"], {})

def test_missing_workflow_version_is_legacy_and_v2_is_explicit(self):
    legacy = team_router.new_task_ledger(
        self.root, self.project_id, "legacy-task",
        objective="legacy", project_local_path=self.root,
    )
    self.assertEqual(team_router.task_workflow_version(legacy), 1)
```

- [ ] **Step 2: Add a failing test that a version 1 awaiting-plan ledger stays on the legacy path after save/reload**

```python
def test_version_one_nonterminal_ledger_is_not_silently_upgraded(self):
    ledger = team_router.new_task_ledger(
        self.root, self.project_id, "legacy-awaiting-plan",
        objective="legacy", project_local_path=self.root,
    )
    ledger["status"] = "awaiting_plan"
    team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)
    reloaded = team_router.load_task_ledger(self.root, self.project_id, ledger["taskId"])
    self.assertEqual(team_router.task_workflow_version(reloaded), 1)
    self.assertEqual(reloaded["status"], "awaiting_plan")
```

- [ ] **Step 3: Run focused tests and confirm RED**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k registry_v2 -k workflow_version -k silently_upgraded -v
```

Expected: FAIL because schema v2 and workflow helpers do not exist.

- [ ] **Step 4: Implement schema v2 normalization without bulk migration**

```python
REGISTRY_VERSION = 2
TASK_LEDGER_VERSION = 2

def task_workflow_version(ledger):
    value = ledger.get("workflowVersion", 1)
    return _as_int(value, 1, "ledger.workflowVersion")
```

`_normalize_registry()` must preserve `project["roles"]`, add `project["managerPools"]`, and capture the raw version before assigning `REGISTRY_VERSION`. `_normalize_task_ledger()` must default missing `workflowVersion` to 1 and normalize v2-only `taskAuthorizationPackage`, `managerAcceptance`, and `resolvedPlan` as optional mappings.

- [ ] **Step 5: Implement the v2 ledger constructor**

```python
def new_v2_task_ledger(state_root, project_id, task_id, *, objective, project_local_path,
                       parent_thread_id, resolved_plan, task_authorization_package,
                       created_at, max_rework=1):
    ledger = new_task_ledger(
        state_root, project_id, task_id,
        objective=objective,
        project_local_path=project_local_path,
        max_rework=max_rework,
    )
    ledger.update({
        "workflowVersion": 2,
        "parentThreadId": parent_thread_id,
        "createdAt": created_at,
        "status": "planned",
        "plan": dict(resolved_plan),
        "taskAuthorizationPackage": dict(task_authorization_package),
        "managerAcceptance": None,
        "modelUpgradeCount": 0,
    })
    return ledger
```

- [ ] **Step 6: Run state tests**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k registry -k task_ledger -k workflow_version -k create_team_task -v
```

Expected: selected tests PASS, including all existing v1 round-trip tests.

- [ ] **Step 7: Commit Task 2**

```powershell
git add src/team_router_state.py src/team_router.py tests/test_team_router.py
git commit -m "feat: add workflow-versioned Team Router state"
```

---

### Task 3: Manager-Owned Role Pool Claims And Creation Intents

**Files:**
- Modify: `src/team_router_state.py:180-516`
- Modify: `src/team_router.py` facade imports
- Test: `tests/test_team_router.py`

**Interfaces:**
- Produces: `manager_pool_lock(state_root, project_id, parent_thread_id, *, task_id, request_id, acquired_at)` context manager.
- Produces: `recover_manager_pool_lock(state_root, project_id, parent_thread_id, *, task_id, request_id, recovered_at) -> bool`.
- Produces: `reserve_role_or_creation_intent(state_root, project_id, *, parent_thread_id, host_id, target_fingerprint, role, task_id, request_id, claimed_at, parallel_allowed=False) -> dict[str, Any]`.
- Produces: `finalize_created_role(state_root, project_id, *, parent_thread_id, role, request_id, thread_id, title, created_at) -> dict[str, Any]`.
- Produces: `release_role_claim(state_root, project_id, *, parent_thread_id, role, thread_id, task_id, request_id) -> dict[str, Any]`.
- Produces: `recover_creation_intent(state_root, project_id, *, parent_thread_id, role, request_id, recovered_at) -> dict[str, Any] | None`.
- Consumes: registry v2 shape from Task 2.

- [ ] **Step 1: Add failing tests for host/target/parent isolation and reusable idle role selection**

```python
def test_v2_role_pool_reuses_only_same_host_target_parent_and_role(self):
    first = team_router.reserve_role_or_creation_intent(
        self.root, self.project_id,
        parent_thread_id="parent-a", host_id="local", target_fingerprint="target-a",
        role="executor", task_id="task-a", request_id="req-a", claimed_at="2026-07-11T20:00:00+08:00",
    )
    self.assertEqual(first["outcome"], "creation_intent")
```

Extend the test by finalizing `thread-executor-a`, releasing its claim, confirming same-key reuse, and confirming `parent-b` or `target-b` yields a new creation intent.

- [ ] **Step 2: Add failing concurrency and release tests**

Use two Python threads synchronized by `threading.Barrier`. Both call `reserve_role_or_creation_intent()` for the same idle thread. Assert exactly one receives `outcome: reused`; the other receives `outcome: busy` or a distinct creation intent only when `parallel_allowed=True`.

Also assert final callback release keeps `preferredThreadId`, and terminal cleanup removes every residual claim/creation intent for the task after copying any `creation_outcome_unknown` identity into a ledger recovery observation. Pre-create an exclusive lock and assert `reserve_role_or_creation_intent()` catches `FileExistsError` and returns `outcome: busy` without retrying. Assert `recover_manager_pool_lock()` refuses age-only and nonterminal recovery, but removes the unchanged matching lock after the owning task is terminal/abandoned.

- [ ] **Step 3: Run focused tests and confirm RED**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k v2_role_pool -k role_claim -k creation_intent -v
```

Expected: FAIL because the manager-pool state helpers do not exist.

- [ ] **Step 4: Implement a stdlib exclusive lock**

```python
@contextmanager
def manager_pool_lock(state_root, project_id, parent_thread_id, *, task_id, request_id, acquired_at):
    lock_path = manager_pool_lock_path(state_root, project_id, parent_thread_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "projectId": project_id,
        "parentThreadId": parent_thread_id,
        "taskId": task_id,
        "requestId": request_id,
        "pid": os.getpid(),
        "acquiredAt": acquired_at,
    }, sort_keys=True).encode("utf-8")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, payload)
        yield
    finally:
        os.close(fd)
        if lock_path.exists() and lock_path.read_bytes() == payload:
            lock_path.unlink()
```

`manager_pool_lock()` deliberately lets `FileExistsError` escape; every public pool mutation catches it once and returns a deterministic `outcome: busy` without retrying. `recover_manager_pool_lock()` reads and validates the lock JSON, loads the owning task ledger itself, requires exact project/parent/task/request identity plus a terminal/abandoned status, rereads the bytes unchanged, and only then unlinks it. It never trusts a caller-supplied status, removes a lock because of age alone, or removes a lock while the task is nonterminal. `recover_creation_intent()` applies the same ledger-owned terminal check; `creation_outcome_unknown` first preserves request identity as a ledger recovery observation, then uses this cleanup path.

- [ ] **Step 5: Implement creation-intent and claim mutation under the lock**

The stored role record shape is:

```python
{
    "threadId": "thread-id",
    "hostId": "local",
    "targetFingerprint": "fingerprint",
    "title": "执行者-任务名",
    "createdAt": "2026-07-11T20:00:00+08:00",
    "lastObservedAt": "2026-07-11T20:00:05+08:00",
    "claim": {
        "taskId": "task",
        "requestId": "request",
        "claimedAt": "2026-07-11T20:00:05+08:00",
    },
}
```

Creation intent uses the same pool and request identity but has no `threadId`. Never hold the filesystem lock while calling `create_thread`, `list_threads`, or `set_thread_title`. Because the host has no idempotent create key, intent recovery may bind one uniquely verified candidate but may never automatically issue a second `create_thread` for an uncertain outcome.

- [ ] **Step 6: Run focused and existing registry tests**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k v2_role_pool -k role_claim -k creation_intent -k registry -v
```

Expected: selected tests PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/team_router_state.py src/team_router.py tests/test_team_router.py
git commit -m "feat: add manager-owned role pool claims"
```

---

### Task 4: V2 Authorization Package And Resolved Manager Plan

**Files:**
- Create: `src/team_router_v2.py`
- Modify: `src/team_router.py` facade imports
- Test: `tests/test_team_router.py`

**Interfaces:**
- Produces: `make_task_authorization_package(*, package_id, task_id, parent_thread_id, objective, scope, permission, stop_condition, created_at, model_routing_authorization=None) -> dict[str, Any]`.
- Produces: `resolve_v2_manager_plan(*, objective, scope, permission, stop_condition, requested_gate_class, authorization_package, explicit_roles=(), requested_role_routing=None, requires_parallelism=False, parallel_conflicts=(), requires_independent_context=False, requires_independent_review=False, lightweight_verification_available=True, ledger_input=None) -> dict[str, Any]`.
- Produces: `prepare_v2_manager_task(state_root, project_id, task_id, *, objective, project_local_path, parent_thread_id, requested_plan, authorization_package, created_at) -> dict[str, Any]`.
- Produces: `v2_continuation_allowed(ledger, *, parent_thread_id, requested_task_id, requested_scope, requested_permission, requested_stop_condition, requested_external_gates=()) -> bool`.
- Consumes: Task 1 gate/model helpers and Task 2 `new_v2_task_ledger()`.

- [ ] **Step 1: Add failing tests for sticky completion authorization and bare Manager Mode**

```python
def test_completion_package_allows_in_scope_terse_continuation_only(self):
    package = team_router.make_task_authorization_package(
        package_id="auth-1", task_id="task-1", parent_thread_id="parent-1",
        objective="完成 X", scope="src/x.py", permission="local-package",
        stop_condition="tests pass", created_at="2026-07-11T20:00:00+08:00",
    )
    ledger = {"taskId": "task-1", "status": "planned", "taskAuthorizationPackage": package}
    continuation = {
        "requested_task_id": "task-1", "requested_scope": "src/x.py",
        "requested_permission": "local-package", "requested_stop_condition": "tests pass",
    }
    self.assertTrue(team_router.v2_continuation_allowed(ledger, parent_thread_id="parent-1", **continuation))
    self.assertFalse(team_router.v2_continuation_allowed(ledger, parent_thread_id="parent-2", **continuation))
```

Add separate assertions that bare Manager Mode without a package remains proposal-only and cannot create threads or state, and that task-id mismatch, scope expansion, permission change, stop-condition change, or non-empty `requested_external_gates` returns false before state/thread calls.

- [ ] **Step 2: Add failing tests for the fixed planning pipeline and route closure**

```python
def test_v2_plan_resolves_effective_gate_before_route_and_models(self):
    package = team_router.make_task_authorization_package(
        package_id="auth-1", task_id="task-1", parent_thread_id="parent-1",
        objective="Team Router permission policy change",
        scope="src/team_router_policy.py", permission="local-package",
        stop_condition="focused tests pass", created_at="2026-07-11T20:00:00+08:00",
        model_routing_authorization={
            "allowedDefaults": ["gpt-5.6-luna:medium", "gpt-5.6-terra:medium", "gpt-5.6-sol:high"],
            "authorizedBy": "explicit_cost_aware_entry",
        },
    )
    plan = team_router.resolve_v2_manager_plan(
        objective="Team Router permission policy change",
        scope="src/team_router_policy.py",
        permission="local-package",
        stop_condition="focused tests pass",
        requested_gate_class="NORMAL",
        explicit_roles=(),
        requested_role_routing={
            "executor": {"executionClass": "standard"},
            "reviewer": {"executionClass": "high"},
            "verifier": {"executionClass": "standard"},
        },
        authorization_package=package,
        requires_independent_review=True,
    )
    self.assertEqual(plan["effectiveGateClass"], "STRICT")
    self.assertEqual(plan["routeRoles"], ("executor", "reviewer", "verifier"))
```

Add a test that missing `roleRouting["verifier"]` raises `plan_invalid` before any adapter call. Add a delegated-plan test without `modelRoutingAuthorization` that returns `model_authorization_required` before state, title, heartbeat, or adapter calls. Add table-driven `parallelAllowed` assertions: requested parallelism with no conflicts is true; any ordering/shared-write/permission conflict forces false and is retained in the resolved plan audit fields. Add a Manager-direct test whose resolved plan has `executionMode: manager_direct`, empty `routeRoles/roleRouting`, and whose `prepare_v2_manager_task()` result has `ledger: None`; patch the state writer and adapter to prove neither is called.

- [ ] **Step 3: Run focused tests and confirm RED**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k completion_package -k v2_plan -k plan_invalid -k manager_direct -v
```

Expected: FAIL because `team_router_v2.py` and its functions do not exist.

- [ ] **Step 4: Implement package identity and continuation checks**

The package must store `packageId`, `taskId`, `parentThreadId`, `objective`, `scope`, `permission`, `stopCondition`, `createdAt`, `status: active`, and optional `modelRoutingAuthorization`. `v2_continuation_allowed()` compares the complete structured continuation request with the stored package and returns false for every terminal ledger, task/parent mismatch, scope expansion, permission or stop-condition change, non-empty new external gate set, or absent package. A terse action string is not sufficient input for this trust-boundary check.

- [ ] **Step 5: Implement the ordered plan resolver**

```python
def resolve_v2_manager_plan(
    *, objective, scope, permission, stop_condition, requested_gate_class,
    authorization_package, explicit_roles=(), requested_role_routing=None,
    requires_parallelism=False, parallel_conflicts=(), requires_independent_context=False,
    requires_independent_review=False, lightweight_verification_available=True,
    ledger_input=None,
):
    ledger_input = dict(ledger_input or {})
    ledger_input.update({"objective": objective, "permission": permission, "workflowVersion": 2})
    authorization_result = validate_v2_authorization(
        authorization_package=authorization_package,
        ledger_input=ledger_input,
        scope=scope,
        permission=permission,
        stop_condition=stop_condition,
    )
    parallel_allowed = bool(requires_parallelism and not tuple(parallel_conflicts))
    gate = resolve_effective_gate(requested_gate_class, ledger_input, authorization=authorization_result)
    execution_mode = resolve_v2_execution_mode(
        gate["effectiveGateClass"],
        explicit_roles=explicit_roles,
        requires_parallelism=requires_parallelism,
        requires_independent_context=requires_independent_context,
        requires_independent_review=requires_independent_review,
        lightweight_verification_available=lightweight_verification_available,
    )
    if execution_mode == "manager_direct":
        return {
            "objective": objective,
            "executionMode": "manager_direct",
            "requestedGateClass": gate["requestedGateClass"],
            "effectiveGateClass": gate["effectiveGateClass"],
            "gateReason": gate["gateReason"],
            "routeRoles": (),
            "roleRouting": {},
            "parallelAllowed": False,
            "parallelConflicts": tuple(parallel_conflicts),
            "scope": scope,
            "permission": permission,
            "stopCondition": stop_condition,
        }
    route_roles = resolve_v2_route(gate["effectiveGateClass"], explicit_roles)
    validate_model_routing_authorization(
        authorization_package.get("modelRoutingAuthorization"),
        route_roles=route_roles,
    )
    requested_role_routing = dict(requested_role_routing or {})
    resolved_routing = {}
    for role in route_roles:
        if role not in requested_role_routing:
            raise StateStoreError("plan_invalid: missing roleRouting.%s" % role)
        request = requested_role_routing[role]
        resolved_routing[role] = resolve_role_model(
            request["executionClass"],
            model=request.get("model"),
            thinking=request.get("thinking"),
            override_reason=request.get("modelOverrideReason"),
        )
    return {
        "objective": objective,
        "executionMode": "delegated",
        "requestedGateClass": gate["requestedGateClass"],
        "effectiveGateClass": gate["effectiveGateClass"],
        "gateReason": gate["gateReason"],
        "routeRoles": route_roles,
        "roleRouting": resolved_routing,
        "parallelAllowed": parallel_allowed,
        "parallelConflicts": tuple(parallel_conflicts),
        "scope": scope,
        "permission": permission,
        "stopCondition": stop_condition,
    }
```

The function must perform no filesystem or thread-tool side effects. `validate_model_routing_authorization()` accepts only the three explicitly named default combinations or a complete per-request user override; missing authorization raises `model_authorization_required`. `parallelAllowed` is true only when parallelism is requested and `parallel_conflicts` is empty; conflict values name ordering, shared-write, or permission boundaries and are persisted for audit. CamelCase plan fields are mapped explicitly into the snake_case Python helper parameters; do not forward plan dictionaries with `**`.

- [ ] **Step 6: Implement `prepare_v2_manager_task()` with a stateless direct branch**

It first calls `resolve_v2_manager_plan()` with the exact fields in `requested_plan`. For `manager_direct`, it returns the resolved decision with `ledger: None` and never calls the state store, title setter, heartbeat scheduler, or any role tool. For `delegated`, it calls `new_v2_task_ledger(state_root, project_id, task_id, objective=objective, project_local_path=project_local_path, parent_thread_id=parent_thread_id, resolved_plan=resolved_plan, task_authorization_package=authorization_package, created_at=created_at, max_rework=1)`, saves the ledger once, and still does not create a role. Explicit zero-write tasks return a stateless decision before this function and never call the state store.

- [ ] **Step 7: Run focused tests**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k completion_package -k v2_plan -k authorization -k route -k manager_direct -v
```

Expected: selected tests PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add src/team_router_v2.py src/team_router.py tests/test_team_router.py
git commit -m "feat: add manager-owned v2 planning"
```

---

### Task 5: Low-Cost Bootstrap, Dynamic Model Dispatch, And Role Reuse

**Files:**
- Modify: `src/team_router_v2.py`
- Modify: `src/team_router.py:1119-1705,3645-4125`
- Modify: `tests/test_team_router.py:65-130`
- Test: `tests/test_team_router.py`

**Interfaces:**
- Produces: `target_fingerprint_for(target, host_id) -> str`.
- Produces: `make_v2_role_bootstrap_prompt(*, request_id, project_id, parent_thread_id, role) -> str`.
- Produces: `recover_v2_creation_intent_with_adapter(thread_adapter, state_root, project_id, *, parent_thread_id, host_id, target_fingerprint, role, task_id, request_id, title, observed_at) -> dict[str, Any]`.
- Produces: `resolve_or_create_v2_role_with_adapter(thread_adapter, state_root, project_id, *, parent_thread_id, host_id, target, target_fingerprint=None, role, task_id, request_id, title, requested_at, parallel_allowed=False) -> dict[str, Any]`.
- Produces: `send_v2_role_request_with_adapter(thread_adapter, state_root, project_id, *, parent_thread_id, host_id, target, target_fingerprint=None, role, task_id, request_id, title, prompt, requested_model, requested_thinking, requested_at, parallel_allowed=False) -> dict[str, Any]`.
- Consumes: Task 3 role-pool claims and Task 4 resolved role routing.

- [ ] **Step 1: Extend `FakeThreadAdapter` to retain model/thinking and inject create/send failures**

```python
# Add to the existing __init__ without replacing its counters/messages/title support.
self.create_error = None
self.send_error = None

# Add as the first branch of the existing adapter methods.
if self.create_error is not None:
    raise self.create_error
if self.send_error is not None:
    raise self.send_error
```

Keep the existing role parsing, unique thread ids, message recording, `read_thread()`, and `set_thread_title()` behavior intact.

- [ ] **Step 2: Add failing tests for Luna bootstrap and task-model dispatch**

```python
def test_new_v2_executor_uses_luna_bootstrap_then_terra_dispatch(self):
    adapter = FakeThreadAdapter()
    result = team_router.send_v2_role_request_with_adapter(
        adapter, self.root, self.project_id,
        parent_thread_id="parent-1", host_id="local",
        target={
            "type": "project", "projectId": "project-1",
            "environment": {"type": "local"},
        },
        role="executor",
        task_id="task-1", request_id="request-1",
        title="执行者-成本感知路由", prompt="实现已确认的成本感知路由任务",
        requested_model="gpt-5.6-terra", requested_thinking="medium",
        requested_at="2026-07-11T20:00:00+08:00",
    )
    self.assertEqual(adapter.created[0]["kwargs"]["model"], "gpt-5.6-luna")
    self.assertEqual(adapter.created[0]["kwargs"]["thinking"], "medium")
    self.assertIn("requestId:", adapter.created[0]["kwargs"]["prompt"])
    self.assertEqual(adapter.sent[0]["kwargs"]["model"], "gpt-5.6-terra")
    self.assertEqual(adapter.sent[0]["kwargs"]["thinking"], "medium")
```

- [ ] **Step 3: Add failing tests for reuse, title refresh, failure closing, and no native fallback**

Cover:

- reused role does not call `create_thread` and still sends explicit `model + thinking`;
- `target_fingerprint_for()` is stable for equivalent canonical target mappings, differs across target or host, rejects empty host/invalid target, and rejects a caller-provided fingerprint that does not equal the Runtime result;
- `parallel_allowed=True` reaches `reserve_role_or_creation_intent()` and creates a distinct intent only when the plan recorded no ordering, shared-write, or permission conflict;
- `set_thread_title` refreshes the concrete title `执行者-成本感知路由` in the fixture;
- unsupported model send records `dispatchAccepted: false`, releases the claim, and does not advance to an awaiting state;
- new thread created but formal send failed remains unclaimed idle;
- Sol Ultra is rejected before `create_thread` or `send_message_to_thread`;
- no code path references `spawn_agent` as fallback.

Add crash-recovery cases for an existing creation intent:

- `list_threads(query=request_id)` returns one candidate and `read_thread(threadId=candidate_id, hostId=host_id)` proves exact `requestId/projectId/parentThreadId/role` bootstrap identity: finalize and reuse it without `create_thread`;
- no verified candidate after one bounded recovery check: persist a recovery observation, transition terminal `tool_error` with `creation_outcome_unknown`, clean the active intent, and do not create or bind a thread;
- multiple verified candidates or identity mismatch: persist recovery evidence, return terminal `tool_error`, and do not create or bind a thread;
- terminal/abandoned task: clean the intent through Task 3 state helpers.

- [ ] **Step 4: Run focused tests and confirm RED**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k v2_executor -k luna_bootstrap -k dynamic_model -k dispatch_accepted -k sol_ultra -k creation_intent_recovery -k bootstrap_identity -v
```

Expected: FAIL because v2 adapter functions do not exist.

- [ ] **Step 5: Implement bootstrap and request dispatch**

```python
import hashlib
import json
from collections.abc import Mapping

BOOTSTRAP_MODEL = "gpt-5.6-luna"
BOOTSTRAP_THINKING = "medium"

def target_fingerprint_for(target, host_id):
    if not isinstance(target, Mapping) or not str(host_id or "").strip():
        raise StateStoreError("invalid target fingerprint input")
    payload = json.dumps(
        {"hostId": str(host_id).strip(), "target": dict(target)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def make_v2_role_bootstrap_prompt(*, request_id, project_id, parent_thread_id, role):
    return "\n".join((
        "TEAM_ROUTER_ROLE_BOOTSTRAP",
        "requestId: %s" % request_id,
        "projectId: %s" % project_id,
        "parentThreadId: %s" % parent_thread_id,
        "role: %s" % role,
        "action: wait_for_formal_dispatch",
        "doNotExecuteTask: true",
    ))
```

Keep the structured Codex project target separate from the string identity used by the reuse pool. Resolve `computed_fingerprint = target_fingerprint_for(target, host_id)` before any pool/ledger mutation; when the caller supplies `target_fingerprint`, reject it unless it exactly matches. Call `create_thread(prompt=bootstrap_prompt, target=dict(target), model=BOOTSTRAP_MODEL, thinking=BOOTSTRAP_THINKING)`. After obtaining `created_thread_id` and normalizing the title, call `send_message_to_thread(threadId=created_thread_id, hostId=host_id, prompt=formal_prompt, model=requested_model, thinking=requested_thinking)`. Never pass `target_fingerprint` to a thread tool. Pass `parallel_allowed` unchanged into `reserve_role_or_creation_intent()`.

Before any new `create_thread`, handle a matching creation intent through `recover_v2_creation_intent_with_adapter()`: call `list_threads(query=request_id)`, read candidate threads, accept only one thread whose bootstrap contains all four exact identity fields, then call `finalize_created_role()`. Zero or ambiguous verified candidates fail closed as described in Step 3; they never fall through to another create call. The current host has no create idempotency key, so automatic zero-candidate retry is explicitly out of scope.

- [ ] **Step 6: Normalize adapter failures without advancing state**

Create failure records `creationAccepted: false`; send failure records `dispatchAccepted: false`. The tool error text is evidence, not permission to substitute a model. Release claim/intent through Task 3 helpers. Only a task independently eligible for Manager direct may continue without thread tools.

- [ ] **Step 7: Run focused adapter and role-reuse tests**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k v2_ -k create_role_threads -k role_thread_title -k archived -k discovery -k adapter -k creation_intent_recovery -v
```

Expected: selected tests PASS; existing v1 adapter tests remain unchanged.

- [ ] **Step 8: Commit Task 5**

```powershell
git add src/team_router_v2.py src/team_router.py tests/test_team_router.py
git commit -m "feat: route reusable roles by model"
```

---

### Task 6: Callback Reclassification, Model Upgrade, Manager Acceptance, And Closeout

**Files:**
- Modify: `src/team_router_v2.py`
- Modify: `src/team_router_status.py:1-190`
- Modify: `src/team_router.py:2525-2615,3444-3575`
- Test: `tests/test_team_router.py`

**Interfaces:**
- Produces: `next_v2_route_after_evidence(ledger, evidence) -> dict[str, Any]`.
- Produces: `record_v2_model_upgrade(state_root, project_id, task_id, *, parent_thread_id, role, failed_request_id, execution_class, model=None, thinking=None, override_reason=None, completed_results, read_files, exact_failure, unresolved, requested_at) -> dict[str, Any]`.
- Produces: `build_v2_routing_receipt(ledger) -> dict[str, Any]`.
- Produces: `record_manager_acceptance(state_root, project_id, task_id, *, result, accepted_at, callback_receipt, scope_checked, evidence_checked, risk_boundary_checked, remaining_risks, reason=None) -> dict[str, Any]`.
- Produces: `make_manager_acceptance_closeout(ledger, *, completed_at) -> dict[str, Any]`.
- Consumes: current callback/reviewer/QA/verifier parsers and Task 4 plan resolver.

- [ ] **Step 1: Add failing tests for FAST/NORMAL Manager acceptance**

```python
def test_v2_normal_executor_callback_enters_manager_acceptance_and_can_finish(self):
    ledger = self.make_v2_ledger(effective_gate="NORMAL", route_roles=("executor",))
    ledger = self.capture_v2_executor_done(ledger)
    self.assertEqual(ledger["status"], "manager_acceptance_pending")
    accepted = team_router.record_manager_acceptance(
        self.root, self.project_id, ledger["taskId"],
        result="pass",
        accepted_at="2026-07-11T21:00:00+08:00",
        callback_receipt="direct-send",
        scope_checked="src/x.py",
        evidence_checked="1 focused test OK",
        risk_boundary_checked="FAST/NORMAL",
        remaining_risks="none",
    )
    self.assertEqual(accepted["status"], "done")
    self.assertEqual(accepted["closeout"]["acceptedBy"], "manager")
```

- [ ] **Step 2: Add failing tests for callback risk escalation and dependency closure**

When callback evidence raises the effective gate from NORMAL to STRICT, assert:

- status does not become `manager_acceptance_pending`;
- route becomes `executor -> reviewer -> verifier`;
- missing Reviewer/Verifier `roleRouting` returns `plan_invalid` without creating threads;
- after Manager supplies routing, Reviewer is the next request.

- [ ] **Step 3: Add failing tests for one model upgrade and a complete routing receipt**

```python
def test_v2_model_upgrade_is_once_only_and_carries_failed_delta(self):
    upgraded = team_router.record_v2_model_upgrade(
        self.root, self.project_id, self.task_id,
        parent_thread_id="parent-1", role="executor",
        failed_request_id="request-1", execution_class="high",
        completed_results=["parsed existing registry"],
        read_files=["src/team_router_state.py"],
        exact_failure="Terra callback could not resolve the concurrency invariant",
        unresolved=["prove claim release ordering"],
        requested_at="2026-07-11T21:05:00+08:00",
    )
    self.assertEqual(upgraded["modelUpgradeCount"], 1)
    self.assertEqual(upgraded["pendingModelUpgrade"]["requestedModel"], "gpt-5.6-sol")
    self.assertEqual(upgraded["pendingModelUpgrade"]["upgradedFrom"], "gpt-5.6-terra")
```

Assert the upgrade request must match the latest failed request for the same role and parent, all four carry-forward fields are required, the new resolved model differs from the failed model, and Sol Ultra is rejected before save/adapter calls. A second upgrade attempt persists `status: blocked` with `model_upgrade_limit`, preserves prior evidence, and performs no thread call. Consuming the first pending upgrade writes `upgradedFrom` on the next dispatch without resetting completed work or incrementing `modelUpgradeCount` again.

Build fixture ledgers covering `new`, `reused`, and `replacement` bindings, one failed create/send, one override, one upgrade, and one rework. Assert `build_v2_routing_receipt()` returns dispatch-order role entries containing `role`, `binding`, optional `threadId`, requested model/thinking, `dispatchAccepted`, optional bootstrap model/thinking and `creationAccepted` only when create was attempted, override reason, `upgradedFrom`, and rework count plus top-level `solUltraDispatched: false`. Assert it never emits `actualModel`, price, tokens, or cost. A corrupted ledger containing Sol Ultra must raise `model_forbidden` instead of printing a false negative receipt.

- [ ] **Step 4: Add failing tests for closeout parity and heartbeat stop**

Assert Manager and Verifier closeouts contain the identical `routingReceipt` returned by `build_v2_routing_receipt()` plus `acceptedBy`, `changed`, `verified`, `notDone`, `risks`, `nextGate`, `remainingTodos`, `compoundingDecision`, `reason`, `watcherAction: stop_and_delete_heartbeat`, and no automatic lesson-file write.

- [ ] **Step 5: Run focused tests and confirm RED**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k manager_acceptance -k callback_risk_escalation -k model_upgrade -k routing_receipt -k closeout_parity -v
```

Expected: FAIL because Manager acceptance flow is not implemented.

- [ ] **Step 6: Implement post-evidence reclassification**

Re-run authorization validation, effective gate, route closure, and role-routing validation before Manager acceptance or the next role. The function may raise risk but must never expand permission. Persist both previous and new effective gates in an observation for audit.

- [ ] **Step 7: Implement the once-only model upgrade record**

`record_v2_model_upgrade()` validates parent/task/role/request identity, resolves the complete target model through `resolve_role_model()`, rejects an unchanged model and incomplete carry-forward evidence, and persists one `pendingModelUpgrade` plus `modelUpgradeCount: 1`. It does not dispatch. The next eligible role request consumes the pending record, prefers the failed role's `preferredThreadId`, carries completed results/read files/exact failure/unresolved work, and records `upgradedFrom`. A second call fails closed as `blocked`; there is no Luna -> Terra -> Sol retry ladder.

- [ ] **Step 8: Implement the structured routing receipt**

`build_v2_routing_receipt()` is a pure projection over resolved role requests, binding outcomes, create/send results, upgrade records, and rework count. It preserves dispatch order and returns:

```python
{
    "roles": [
        {
            "role": "executor",
            "binding": "reused",
            "threadId": "thread-executor",
            "requestedModel": "gpt-5.6-sol",
            "requestedThinking": "high",
            "dispatchAccepted": True,
            "upgradedFrom": "gpt-5.6-terra",
            "reworkCount": 1,
        },
    ],
    "solUltraDispatched": False,
}
```

New-role entries also include `bootstrapModel/bootstrapThinking`; override/replacement fields appear only when present. Validate the forbidden model invariant before returning. Both Manager-acceptance and Verifier closeout builders call this one function.

- [ ] **Step 9: Implement Manager acceptance and shared rework budget**

`result: pass` is allowed only for FAST/NORMAL with no Reviewer/QA/Verifier in the route and a valid final Executor callback. `needs_rework` calls `next_rework_dispatch()` with `maxRework=1`; `blocked` terminates. Release the Executor active claim after its final callback and retain `preferredThreadId` for rework.

- [ ] **Step 10: Implement closeout formatting parity**

Extend `role_thread_lines()` to read manager-owned v2 pools, then make `format_closeout_for_user()` print `acceptedBy`, changed/verified/notDone, nextGate, routing receipt, and existing compounding fields without breaking v1 output.

- [ ] **Step 11: Run focused and existing closeout/rework tests**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k manager_acceptance -k closeout -k rework -k verifier_pass -k format_task_update -k model_upgrade -k routing_receipt -v
```

Expected: selected tests PASS.

- [ ] **Step 12: Commit Task 6**

```powershell
git add src/team_router_v2.py src/team_router_status.py src/team_router.py tests/test_team_router.py
git commit -m "feat: add v2 escalation and closeout"
```

---

### Task 7: Facade Orchestration And Version 1 Compatibility

**Files:**
- Modify: `src/team_router.py:4990-5295`
- Modify: `src/team_router_watcher_runtime.py`
- Modify: `src/team_router_direct_return.py`
- Test: `tests/test_team_router.py`
- Test: `tests/fixtures/team_router/*.json`

**Interfaces:**
- Produces: `run_v2_team_task_with_adapter(state_root, project_id, task_id, *, objective, project_local_path, thread_adapter, permission, observed_at, target, target_fingerprint, host_id, parent_thread_id, manager_plan, task_authorization_package, turn_limit=None, confirm_rework=False, return_thread_id=None) -> dict[str, Any]` through `team_router_v2.py`.
- Extends the existing facade signature with keyword-only `manager_plan=None`, `task_authorization_package=None`, `host_id="local"`, and `target_fingerprint=None`; all existing positional and keyword parameters remain unchanged.
- Preserves: existing v1 entry when the ledger is version 1 or no v2 resolved plan is supplied.

- [ ] **Step 1: Add failing v1/v2 selection tests**

```python
def test_orchestrator_uses_v1_for_legacy_ledger_and_v2_for_resolved_parent_plan(self):
    legacy = self.make_legacy_awaiting_plan_ledger()
    self.assertEqual(team_router.task_workflow_version(legacy), 1)
    v2 = self.make_v2_planned_ledger()
    self.assertEqual(team_router.task_workflow_version(v2), 2)
```

The legacy call must still send `TEAM_ROUTER_PLAN_REQUEST` to the child Manager. The v2 call must never create or message a Manager role. Add a collision regression: when an existing nonterminal v1 ledger and a newly supplied Manager-direct plan share a task id, the existing v1 ledger wins and is never bypassed by the stateless branch.

- [ ] **Step 2: Add failing v2 route-matrix end-to-end tests**

Cover:

- Manager direct: no ledger or role.
- Plain Manager entry that resolves to delegated without `modelRoutingAuthorization`: `model_authorization_required` before readiness, title, heartbeat, state, or role calls.
- NORMAL delegated: Executor -> Manager acceptance -> done.
- explicit Architect: Architect -> Executor -> Manager acceptance.
- explicit QA: Executor -> QA -> Verifier.
- STRICT: Executor -> Reviewer -> Verifier.
- STRICT + Architect + QA: Architect -> Executor -> Reviewer -> QA -> Verifier.

The Manager-direct case patches `assess_live_orchestration_readiness`, `set_thread_title`, the heartbeat scheduler, state writers, and every adapter method, then asserts zero calls. The delegated cases assert the structured `target` reaches `create_thread`, Runtime computes `targetFingerprint` from that target plus `hostId` before pool state, a supplied mismatch fails closed, and the fingerprint appears only in pool identity/state. Add a busy-role case proving `requiresParallelism` becomes `parallel_allowed=True` through the full facade path; a shared-write-conflict plan must keep it false.

- [ ] **Step 3: Add failing sticky continuation and terminal-expiry tests**

An active `taskAuthorizationPackage` accepts `continue` for the same parent/task/scope. A terminal ledger, parent mismatch, scope expansion, or new external gate rejects continuation before thread/state calls.

- [ ] **Step 4: Run focused tests and confirm RED**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k orchestrator_uses_v1 -k v2_route_matrix -k sticky_continuation -k manager_direct -v
```

Expected: FAIL because the facade does not dispatch by workflow version.

- [ ] **Step 5: Branch orchestration by ledger workflow version**

Keep `run_team_task_with_adapter()` as the v1 implementation. In `orchestrate_team_task_with_adapter()`, an existing version 1 ledger always wins and stays on v1. For a new task or an explicitly version 2 ledger, resolve and return an authorized Manager-direct result before live-thread readiness, parent-title normalization, project-target resolution, heartbeat setup, or v2 state creation. If the resolved route is delegated but model authorization is missing, return `model_authorization_required` at the same pre-side-effect boundary. For authorized delegated work, resolve the structured target, compute/validate the fingerprint, then call `run_v2_team_task_with_adapter()`; never pass an unchecked `None` fingerprint into pool state. Do not reinterpret v1 `roles_ready/planning/awaiting_plan` states.

- [ ] **Step 6: Integrate parent title and heartbeat behavior**

In the cost-aware routing fixture, V2 authorized dispatch renames the parent to `管理者-Team Router 成本感知路由`. The equivalent v1 fixture retains `调度者-Team Router 成本感知路由`. Manager direct and explicit zero-write review paths do not rename or schedule heartbeat. `manager_acceptance_pending` is parent-local and must not poll a role thread.

- [ ] **Step 7: Run all Team Router unit tests**

```powershell
py -m unittest discover -s tests -p test_team_router.py -v
```

Expected: all tests PASS, including existing v1 fixtures.

- [ ] **Step 8: Commit Task 7**

```powershell
git add src/team_router.py src/team_router_watcher_runtime.py src/team_router_direct_return.py tests/test_team_router.py tests/fixtures/team_router
git commit -m "feat: integrate manager-owned Team Router v2"
```

---

### Task 8: Skill, Reference, Runbook, And Module-Map Contracts

**Files:**
- Modify: `skills/codex-team-router/SKILL.md`
- Modify: `skills/codex-team-router/references/manager-mode.md`
- Modify: `skills/codex-team-router/references/manager-quick-card.md`
- Modify: `skills/codex-team-router/references/adapter-runtime.md`
- Modify: `skills/codex-team-router/references/conditional-roles.md`
- Modify: `skills/codex-team-router/references/manual-orchestration.md`
- Modify: `skills/codex-team-router/references/reviewer-gate.md`
- Modify: `skills/codex-team-router/references/role-closeout.md`
- Modify: `skills/codex-team-router/references/side-effect-taxonomy.md`
- Modify: `skills/codex-team-router/references/testing-and-quality-gates.md`
- Modify: `docs/runbooks/codex-team-router-live-orchestration.md`
- Modify: `docs/team-router/module-map.md`
- Modify: `README.md`
- Test: `tests/test_team_router.py`

**Interfaces:**
- Documents: standard entry `你作为管理者，完成 <目标>`, explicit cost-aware model entry, and Complex Task Stack combination.
- Documents: Manager direct, dynamic models, role reuse, v1 compatibility, Manager acceptance, and separate global sync gate.
- Preserves: SKILL short-entrypoint pattern and detailed references.

- [ ] **Step 1: Add failing docs-contract tests**

Assert the short skill and references contain:

- parent Manager owns v2 plan;
- no fixed child Manager in v2;
- plain Manager entry does not imply a concrete model choice; explicit cost-aware entry authorizes Luna/Terra/Sol role routing;
- Luna/Terra/Sol defaults and Sol Ultra prohibition;
- visible threads only, no native subagent fallback;
- sticky completion package vs bare proposal-only Manager Mode;
- FAST/NORMAL Manager acceptance and STRICT/PACKAGE Reviewer/Verifier;
- version 1 compatibility;
- crash-safe creation-intent discovery, terminal unknown-outcome handling, and no automatic duplicate create;
- canonical target + host fingerprinting and end-to-end `parallelAllowed` propagation;
- one automatic model upgrade with preserved evidence and a hard second-attempt stop;
- structured routing receipt fields and no `actualModel`/cost claim;
- requested model is not actual billing evidence;
- repo/global mismatch before sync is expected.

- [ ] **Step 2: Run docs tests and confirm RED**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k skill_doc -k runbook -k quality_gates -k module_map -v
```

Expected: FAIL on old fixed-three-role and child-Manager wording.

- [ ] **Step 3: Update `SKILL.md` minimally**

Keep the entrypoint under 8 KB. Put detailed routing/state tables in references. The short skill must state only the trigger, Manager-direct rule, explicit cost-aware model opt-in, visible-thread-only boundary, default model mapping, Sol Ultra prohibition, reuse rule, FAST/NORMAL vs STRICT/PACKAGE gate, and lifecycle authorization boundary.

- [ ] **Step 4: Update references and runbook**

Use targeted `rg` discovery first, then replace v2-invalid statements such as “FAST/NORMAL always executor -> verifier,” “local-package always reviewer,” and “all new tasks create manager/executor/verifier.” Preserve those statements only inside explicitly labeled version 1 compatibility sections. Do not edit a listed reference if the search proves it has no stale contract.

- [ ] **Step 5: Update module map and README**

Add an ownership entry for `team_router_v2.py` and record manager-pool state ownership under existing `team_router_state.py`; keep the main test command literal:

```powershell
py -m unittest discover -s tests -p test_team_router.py -v
```

- [ ] **Step 6: Run docs tests and size check**

```powershell
py -m unittest discover -s tests -p test_team_router.py -k skill_doc -k runbook -k quality_gates -k module_map -v
$bytes = [Text.Encoding]::UTF8.GetByteCount((Get-Content -Raw -LiteralPath 'skills\codex-team-router\SKILL.md'))
if ($bytes -ge 8192) { throw "SKILL.md exceeds 8 KB: $bytes" }
```

Expected: selected tests PASS and SKILL size is below 8192 bytes.

- [ ] **Step 7: Commit Task 8**

```powershell
git add README.md skills/codex-team-router docs/runbooks/codex-team-router-live-orchestration.md docs/team-router/module-map.md tests/test_team_router.py
git commit -m "docs: document cost-aware Team Router routing"
```

---

### Task 9: Full Verification And Pre-Sync Closeout

**Files:**
- Modify only if verification exposes a defect in files already authorized by Tasks 1-8.
- Do not modify: `C:\Users\Orz\.codex\skills\codex-team-router` in this task.

**Interfaces:**
- Produces: repo verification evidence and an expected pre-sync drift report.
- Does not perform: global skill sync, push, PR, merge, deploy.

- [ ] **Step 1: Run the complete unit suite**

```powershell
py -m unittest discover -s tests -p test_team_router.py -v
```

Expected: all tests PASS with zero failures/errors.

- [ ] **Step 2: Run runtime/truth/readiness checks**

```powershell
py -B scripts\team_router_runtime_wiring_check.py
py -B scripts\team_router_host_adapter_readiness_check.py
py -B scripts\team_router_doctor.py
py -B scripts\team_router_truth_check.py
```

Expected: no unauthorized external action; runtime wiring and local readiness report no new contract failure.

- [ ] **Step 3: Run diff and scope checks**

```powershell
git diff --check
git status -s --untracked-files=all
git merge-base --is-ancestor f484892 HEAD
git diff --stat f484892..HEAD
```

Expected: the design baseline is an ancestor; the diff contains the Task 0 reviewed design-and-plan commit plus only planned source/tests/docs changes; no global config, temporary artifacts, or unrelated user changes are staged.

- [ ] **Step 4: Verify expected repo/global skill drift without syncing**

```powershell
py -B scripts\team_router_skill_sync_check.py --check
```

Expected before authorized sync: exit code 1 with `status: mismatch`, and every listed path belongs to the repo skill changes in Task 8. Any extra/unrelated path is a blocker.

- [ ] **Step 5: Run the read-only closeout check**

```powershell
py -B scripts\team_router_closeout_check.py
```

Expected: implementation and tests are reportable; global sync remains an explicit next gate; no push/PR/merge/deploy was performed.

- [ ] **Step 6: Return any verification failure to its owning task**

If Steps 1-5 expose a defect, stop Task 9, return to the owning Task 1-8, add or tighten the failing test there, make the smallest correction, rerun that task's focused checks, and use that task's scoped commit step. When Steps 1-5 pass without changes, Task 9 creates no commit.

---

### Task 10: Separately Authorized Global Skill Sync

**Gate:** Do not execute this task unless the user explicitly authorizes writing `C:\Users\Orz\.codex\skills\codex-team-router` in the current turn.

**Files:**
- Sync target: `C:\Users\Orz\.codex\skills\codex-team-router`
- Source: `skills/codex-team-router`

**Interfaces:**
- Produces: byte-matching repo/global Team Router skill trees.
- Does not modify: global `AGENTS.md`, repo source, commits, or external services.

- [ ] **Step 1: Reconfirm the explicit global-sync gate and clean repo source**

```powershell
git status -s --untracked-files=all
py -B scripts\team_router_skill_sync_check.py --check
```

Expected: the Task 0 reviewed design and plan files plus Tasks 1-8 implementation are clean/committed, and check reports only the expected skill mismatch.

- [ ] **Step 2: Run the authorized sync**

```powershell
py -B scripts\team_router_skill_sync_check.py --sync
```

Expected: `mode: sync` followed by `status: match`.

- [ ] **Step 3: Re-run check-only verification**

```powershell
py -B scripts\team_router_skill_sync_check.py --check
```

Expected: exit code 0 and `status: match`.

- [ ] **Step 4: Report the routing receipt and stop**

Report source commit, synced global path, check result, no global `AGENTS.md` modification, and no push/PR/merge/deploy. Do not create a repo commit for the global copy.
