# -*- coding: utf-8 -*-
"""State, registry, and task-ledger JSON primitives for Team Router."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
import json
import os
import uuid
from typing import Any, Mapping

from team_router_protocol import _validate_task_id


class StateStoreError(ValueError):
    """Raised when registry or task ledger JSON cannot be read safely."""


REGISTRY_VERSION = 2
PROJECT_ROLE_POOL_KEY = "__project__"
TASK_LEDGER_VERSION = 2
ROLE_NAMES = frozenset({"manager", "executor", "reviewer", "verifier", "architect", "qa"})
LEGACY_CORE_ROLE_NAMES = frozenset({"manager", "executor", "verifier"})
V2_DELEGATED_BASE_ROLE_NAMES = frozenset({"executor"})
V2_CONDITIONAL_ROLE_NAMES = frozenset({"reviewer", "verifier", "architect", "qa"})
CORE_ROLE_NAMES = LEGACY_CORE_ROLE_NAMES
CONDITIONAL_ROLE_NAMES = frozenset({"reviewer", "architect", "qa"})
ROLE_DISPLAY_NAMES = {
    "manager": "规划者",
    "executor": "执行者",
    "reviewer": "审查者",
    "verifier": "验证者",
    "architect": "架构师",
    "qa": "QA",
}
ROLE_ALIASES = {
    "manager": "Manager",
    "executor": "Executor",
    "reviewer": "Reviewer",
    "verifier": "Verifier",
    "architect": "Architect",
    "qa": "QA",
}
THREAD_PERMISSIONS = frozenset({"read-only", "design-only", "local-package"})
_FORBIDDEN_STATE_ROOT_PARTS = {".codex-tmp"}

TERMINAL_STATUSES = frozenset({
    "done",
    "blocked",
    "malformed_callback",
    "tool_error",
    "missing_role",
    "abandoned",
})
RECOVERABLE_STATUSES = {
    "plan_unreachable": "planned",
    "callback_unreachable": "verifying",
    "review_unreachable": "reviewing",
    "architect_review_unreachable": "awaiting_architect_review",
    "qa_review_unreachable": "awaiting_qa_review",
}
STATE_MACHINE_SNAPSHOT = {
    "main": (
        "created",
        "roles_ready",
        "planning",
        "awaiting_plan",
        "planned",
        "dispatched",
        "awaiting_callback",
        "awaiting_architect_review",
        "architect_rework_pending",
        "reviewing",
        "awaiting_qa_review",
        "verifying",
        "needs_feedback",
        "done",
    ),
    "rework": ("verifying", "needs_rework", "dispatched"),
    "manual_recovery": {
        "plan_unreachable": "planned",
        "callback_unreachable": "verifying",
        "review_unreachable": "reviewing",
        "architect_review_unreachable": "awaiting_architect_review",
        "qa_review_unreachable": "awaiting_qa_review",
    },
    "terminal": (
        "blocked",
        "malformed_callback",
        "tool_error",
        "missing_role",
        "abandoned",
    ),
}

def _resolve_persistent_state_root(root: str | Path) -> Path:
    resolved = Path(root).resolve()
    parts = {part.lower() for part in resolved.parts}
    if parts.intersection(_FORBIDDEN_STATE_ROOT_PARTS):
        raise StateStoreError("stateRoot must not be under .codex-tmp: %s" % resolved)
    return resolved


def manual_recovery_target(status: str) -> str:
    try:
        return RECOVERABLE_STATUSES[status]
    except KeyError as exc:
        raise ValueError("status is not manually recoverable: %s" % status) from exc


def next_rework_dispatch(rework_count: int, max_rework: int) -> tuple[str, int]:
    if not isinstance(rework_count, int) or not isinstance(max_rework, int):
        raise ValueError("rework counters must be integers")
    if rework_count < 0 or max_rework < 0:
        raise ValueError("rework counters must be non-negative")
    if rework_count >= max_rework:
        return "blocked", rework_count
    return "dispatched", rework_count + 1


def resolve_state_root(current_root: str | Path,
                       *,
                       canonical_root: str | Path | None = None,
                       explicit_state_root: str | Path | None = None) -> Path:
    if explicit_state_root is not None:
        return _resolve_persistent_state_root(explicit_state_root)
    root = Path(canonical_root if canonical_root is not None else current_root)
    return _resolve_persistent_state_root(root / ".codex-team-router")


def registry_path(state_root: str | Path, project_id: str) -> Path:
    _validate_task_id(project_id)
    return (
        _resolve_persistent_state_root(state_root)
        / "projects" / project_id / "registry.json"
    )


def task_path(state_root: str | Path, project_id: str, task_id: str) -> Path:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    return (
        _resolve_persistent_state_root(state_root)
        / "projects" / project_id / "tasks" / (task_id + ".json")
    )


def _as_mapping(value: Any, field: str, *, default_empty: bool = True) -> dict[str, Any]:
    if value is None and default_empty:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise StateStoreError("%s must be a JSON object" % field)


def _as_list(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    raise StateStoreError("%s must be a JSON array" % field)


def _as_int(value: Any, default: int, field: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateStoreError("%s must be an integer" % field)
    return value


def task_workflow_version(ledger: Mapping[str, Any]) -> int:
    version = _as_int(ledger.get("workflowVersion"), 1, "ledger.workflowVersion")
    if version not in {1, 2}:
        raise StateStoreError("unsupported ledger.workflowVersion: %s" % version)
    return version


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise StateStoreError("missing JSON file: %s" % path) from exc
    except PermissionError as exc:
        raise StateStoreError("cannot read JSON file: %s: %s" % (path, exc)) from exc
    except json.JSONDecodeError as exc:
        raise StateStoreError("invalid JSON in %s: %s" % (path, exc.msg)) from exc
    return _as_mapping(data, str(path), default_empty=False)


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name("%s.%s.tmp" % (path.name, uuid.uuid4().hex))
    try:
        with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _normalize_registry(data: Mapping[str, Any], state_root: str | Path,
                        project_id: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    root = str(_resolve_persistent_state_root(state_root))
    registry = dict(data)
    raw_version = _as_int(registry.get("version"), 1, "registry.version")
    if raw_version not in {1, REGISTRY_VERSION}:
        raise StateStoreError("unsupported registry.version: %s" % raw_version)
    projects = _as_mapping(registry.get("projects"), "registry.projects")
    project = _as_mapping(
        projects.get(project_id),
        "registry.projects.%s" % project_id,
    )
    roles = _as_mapping(project.get("roles"), "registry.projects.%s.roles" % project_id)
    manager_pools = _as_mapping(
        project.get("managerPools"),
        "registry.projects.%s.managerPools" % project_id,
    )

    registry["version"] = REGISTRY_VERSION
    registry["stateRoot"] = root
    project.setdefault("projectName", "")
    project.setdefault("canonicalRoot", "")
    project.setdefault("localPathHash", "")
    project.setdefault("target", {})
    project.setdefault("targetFingerprint", "")
    project.setdefault("hostId", "")
    project["projectId"] = project_id
    project["roles"] = roles
    project["managerPools"] = manager_pools
    projects[project_id] = project
    registry["projects"] = projects
    return registry


def load_registry(state_root: str | Path, project_id: str) -> dict[str, Any]:
    path = registry_path(state_root, project_id)
    if path.exists():
        data = _read_json_object(path)
    else:
        data = {}
    return _normalize_registry(data, state_root, project_id)


def save_registry(state_root: str | Path, project_id: str,
                  registry: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_registry(registry, state_root, project_id)
    _atomic_write_json(registry_path(state_root, project_id), normalized)
    return normalized


def manager_pool_lock_path(state_root: str | Path,
                           project_id: str,
                           parent_thread_id: str) -> Path:
    _validate_task_id(project_id)
    _required_str(parent_thread_id, "parentThreadId")
    return (
        _resolve_persistent_state_root(state_root)
        / "projects" / project_id / "manager-pools" / "project.lock"
    )


@contextmanager
def manager_pool_lock(state_root: str | Path,
                      project_id: str,
                      parent_thread_id: str,
                      *,
                      task_id: str,
                      request_id: str,
                      acquired_at: str):
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    parent_thread_id = _required_str(parent_thread_id, "parentThreadId")
    request_id = _required_str(request_id, "requestId")
    acquired_at = _required_str(acquired_at, "acquiredAt")
    lock_path = manager_pool_lock_path(state_root, project_id, parent_thread_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "projectId": project_id,
        "parentThreadId": parent_thread_id,
        "taskId": task_id,
        "requestId": request_id,
        "pid": os.getpid(),
        "acquiredAt": acquired_at,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, payload)
        yield
    finally:
        os.close(fd)
        try:
            if lock_path.read_bytes() == payload:
                lock_path.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def task_dispatch_lock(state_root: str | Path, project_id: str, task_id: str, *, acquired_at: str):
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    lock_path = task_path(state_root, project_id, task_id).with_suffix(".dispatch.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"taskId": task_id, "pid": os.getpid(), "acquiredAt": _required_str(acquired_at, "acquiredAt")}, sort_keys=True).encode("utf-8")
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise StateStoreError("task dispatch lock is held: %s" % task_id) from exc
    try:
        os.write(fd, payload)
        yield
    finally:
        os.close(fd)
        try:
            if lock_path.read_bytes() == payload:
                lock_path.unlink()
        except FileNotFoundError:
            pass


def _manager_pool(registry: dict[str, Any], project_id: str,
                  parent_thread_id: str) -> dict[str, Any]:
    projects = _as_mapping(registry.get("projects"), "registry.projects")
    project = _as_mapping(
        projects.get(project_id),
        "registry.projects.%s" % project_id,
        default_empty=False,
    )
    manager_pools = _as_mapping(
        project.get("managerPools"),
        "registry.projects.%s.managerPools" % project_id,
    )
    pool = _as_mapping(manager_pools.get(PROJECT_ROLE_POOL_KEY), "managerPool")
    if PROJECT_ROLE_POOL_KEY not in manager_pools:
        roles: dict[str, list[Any]] = {}
        intents: list[Any] = []
        for legacy_pool in manager_pools.values():
            legacy = _as_mapping(legacy_pool, "legacyManagerPool", default_empty=False)
            for role, records in _as_mapping(legacy.get("roles"), "legacyManagerPool.roles").items():
                roles.setdefault(role, []).extend(_as_list(records, "legacyManagerPool.roles.%s" % role))
            intents.extend(_as_list(legacy.get("creationIntents"), "legacyManagerPool.creationIntents"))
        pool = {"roles": roles, "creationIntents": intents}
        manager_pools = {PROJECT_ROLE_POOL_KEY: pool}
    pool["roles"] = _as_mapping(pool.get("roles"), "managerPool.roles")
    pool["creationIntents"] = _as_list(
        pool.get("creationIntents"),
        "managerPool.creationIntents",
    )
    manager_pools[PROJECT_ROLE_POOL_KEY] = pool
    project["managerPools"] = manager_pools
    projects[project_id] = project
    registry["projects"] = projects
    return pool


def _pool_role_records(pool: dict[str, Any], role: str) -> list[dict[str, Any]]:
    _validate_v2_pool_role(role)
    roles = _as_mapping(pool.get("roles"), "managerPool.roles")
    records = _as_list(roles.get(role), "managerPool.roles.%s" % role)
    normalized: list[dict[str, Any]] = []
    for record in records:
        normalized.append(_as_mapping(record, "managerPool.roles.%s[]" % role, default_empty=False))
    roles[role] = normalized
    pool["roles"] = roles
    return normalized


def _pool_creation_intents(pool: dict[str, Any]) -> list[dict[str, Any]]:
    intents = _as_list(pool.get("creationIntents"), "managerPool.creationIntents")
    normalized: list[dict[str, Any]] = []
    for intent in intents:
        normalized.append(_as_mapping(intent, "managerPool.creationIntents[]", default_empty=False))
    pool["creationIntents"] = normalized
    return normalized


def _creation_intent_matches(intent: Mapping[str, Any], *, parent_thread_id: str,
                             host_id: str, target_fingerprint: str, role: str,
                             task_id: str | None = None,
                             request_id: str | None = None) -> bool:
    if (
        intent.get("parentThreadId") != parent_thread_id
        or intent.get("hostId") != host_id
        or intent.get("targetFingerprint") != target_fingerprint
        or intent.get("role") != role
    ):
        return False
    return (
        (task_id is None or intent.get("taskId") == task_id)
        and (request_id is None or intent.get("requestId") == request_id)
    )


def _find_creation_intent(pool: dict[str, Any], *, parent_thread_id: str,
                          role: str, request_id: str) -> dict[str, Any] | None:
    for intent in _pool_creation_intents(pool):
        if (
            intent.get("parentThreadId") == parent_thread_id
            and intent.get("role") == role
            and intent.get("requestId") == request_id
        ):
            return intent
    return None


def _pool_busy(role: str, request_id: str) -> dict[str, Any]:
    return {"outcome": "busy", "role": role, "requestId": request_id}


def _role_record_is_reusable(record: Mapping[str, Any]) -> bool:
    if record.get("archived") is True:
        return False
    for key in ("status", "state", "threadStatus", "availability"):
        value = record.get(key)
        if value is None:
            continue
        status = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        if status in {"archived", "blocked", "broken", "invalid", "unavailable"}:
            return False
    claim = record.get("claim")
    if claim is None:
        return True
    if not isinstance(claim, Mapping):
        return False
    return all(
        isinstance(claim.get(field), str) and claim[field]
        for field in ("taskId", "requestId", "claimedAt")
    )


def _validate_v2_pool_role(role: str) -> None:
    _validate_role(role)
    if role not in V2_DELEGATED_BASE_ROLE_NAMES | V2_CONDITIONAL_ROLE_NAMES:
        raise StateStoreError("invalid V2 manager pool role: %s" % role)


def reserve_role_or_creation_intent(state_root: str | Path,
                                    project_id: str,
                                    *,
                                    parent_thread_id: str,
                                    host_id: str,
                                    target_fingerprint: str,
                                    role: str,
                                    task_id: str,
                                    request_id: str,
                                    claimed_at: str,
                                    parallel_allowed: bool = False,
                                    preferred_thread_id: str | None = None) -> dict[str, Any]:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    parent_thread_id = _required_str(parent_thread_id, "parentThreadId")
    host_id = _required_str(host_id, "hostId")
    target_fingerprint = _required_str(target_fingerprint, "targetFingerprint")
    _validate_v2_pool_role(role)
    request_id = _required_str(request_id, "requestId")
    claimed_at = _required_str(claimed_at, "claimedAt")
    if not isinstance(parallel_allowed, bool):
        raise StateStoreError("parallelAllowed must be a boolean")
    if preferred_thread_id is not None:
        preferred_thread_id = _required_str(preferred_thread_id, "preferredThreadId")
    try:
        with manager_pool_lock(
            state_root,
            project_id,
            parent_thread_id,
            task_id=task_id,
            request_id=request_id,
            acquired_at=claimed_at,
        ):
            registry = load_registry(state_root, project_id)
            pool = _manager_pool(registry, project_id, parent_thread_id)
            records = _pool_role_records(pool, role)
            intents = _pool_creation_intents(pool)

            same_request = _find_creation_intent(
                pool,
                parent_thread_id=parent_thread_id,
                role=role,
                request_id=request_id,
            )
            if same_request is not None:
                if _creation_intent_matches(
                    same_request,
                    parent_thread_id=parent_thread_id,
                    host_id=host_id,
                    target_fingerprint=target_fingerprint,
                    role=role,
                    task_id=task_id,
                    request_id=request_id,
                ):
                    return {
                        "outcome": "creation_intent",
                        "role": role,
                        "requestId": request_id,
                        "creationIntent": dict(same_request),
                        "existing": True,
                    }
                return _pool_busy(role, request_id)

            matching_records = [
                record for record in records
                if record.get("hostId") == host_id
                and record.get("targetFingerprint") == target_fingerprint
                and isinstance(record.get("threadId"), str)
                and record["threadId"]
                and _role_record_is_reusable(record)
            ]
            if preferred_thread_id is not None:
                matching_records.sort(key=lambda record: record.get("threadId") != preferred_thread_id)
            for record in matching_records:
                claim = record.get("claim")
                if not isinstance(claim, Mapping):
                    record["claim"] = {
                        "taskId": task_id,
                        "requestId": request_id,
                        "claimedAt": claimed_at,
                    }
                    save_registry(state_root, project_id, registry)
                    return {
                        "outcome": "reused",
                        "role": role,
                        "threadId": record["threadId"],
                        "roleRecord": dict(record),
                    }
                if claim.get("taskId") == task_id and claim.get("requestId") == request_id:
                    return {
                        "outcome": "reused",
                        "role": role,
                        "threadId": record["threadId"],
                        "roleRecord": dict(record),
                    }

            matching_intents = [
                intent for intent in intents
                if intent.get("hostId") == host_id
                and intent.get("targetFingerprint") == target_fingerprint
                and intent.get("role") == role
            ]
            if matching_records and not parallel_allowed:
                return _pool_busy(role, request_id)
            if matching_intents and not parallel_allowed:
                return _pool_busy(role, request_id)
            if len(matching_records) + len(matching_intents) >= 2:
                return _pool_busy(role, request_id)

            intent = {
                "parentThreadId": parent_thread_id,
                "hostId": host_id,
                "targetFingerprint": target_fingerprint,
                "role": role,
                "taskId": task_id,
                "requestId": request_id,
                "claimedAt": claimed_at,
                "temporary": bool(matching_records or matching_intents),
            }
            intents.append(intent)
            pool["creationIntents"] = intents
            save_registry(state_root, project_id, registry)
            return {
                "outcome": "creation_intent",
                "role": role,
                "requestId": request_id,
                "creationIntent": dict(intent),
                "existing": False,
            }
    except FileExistsError:
        return _pool_busy(role, request_id)


def finalize_created_role(state_root: str | Path,
                          project_id: str,
                          *,
                          parent_thread_id: str,
                          role: str,
                          request_id: str,
                          thread_id: str,
                          title: str,
                          created_at: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    parent_thread_id = _required_str(parent_thread_id, "parentThreadId")
    _validate_v2_pool_role(role)
    request_id = _required_str(request_id, "requestId")
    thread_id = _required_str(thread_id, "threadId")
    title = _required_str(title, "title")
    created_at = _required_str(created_at, "createdAt")
    registry = load_registry(state_root, project_id)
    intent = _find_creation_intent(
        _manager_pool(registry, project_id, parent_thread_id),
        parent_thread_id=parent_thread_id,
        role=role,
        request_id=request_id,
    )
    if intent is None:
        return {"outcome": "missing_creation_intent", "role": role, "requestId": request_id}
    task_id = _required_str(intent.get("taskId"), "creationIntent.taskId")
    try:
        with manager_pool_lock(
            state_root,
            project_id,
            parent_thread_id,
            task_id=task_id,
            request_id=request_id,
            acquired_at=created_at,
        ):
            registry = load_registry(state_root, project_id)
            pool = _manager_pool(registry, project_id, parent_thread_id)
            intent = _find_creation_intent(
                pool,
                parent_thread_id=parent_thread_id,
                role=role,
                request_id=request_id,
            )
            if intent is None:
                return {"outcome": "missing_creation_intent", "role": role, "requestId": request_id}
            records = _pool_role_records(pool, role)
            for record in records:
                if record.get("threadId") == thread_id:
                    if record.get("creationRequestId") != request_id:
                        return {"outcome": "conflict", "role": role, "requestId": request_id}
                    _pool_creation_intents(pool).remove(intent)
                    save_registry(state_root, project_id, registry)
                    return {"outcome": "created", "role": role, "threadId": thread_id, "roleRecord": dict(record)}
            claim = {
                "taskId": _required_str(intent.get("taskId"), "creationIntent.taskId"),
                "requestId": request_id,
                "claimedAt": _required_str(intent.get("claimedAt"), "creationIntent.claimedAt"),
            }
            record = {
                "threadId": thread_id,
                "hostId": _required_str(intent.get("hostId"), "creationIntent.hostId"),
                "targetFingerprint": _required_str(
                    intent.get("targetFingerprint"), "creationIntent.targetFingerprint",
                ),
                "title": title,
                "createdAt": created_at,
                "lastObservedAt": created_at,
                "creationRequestId": request_id,
                "claim": claim,
                "temporary": intent.get("temporary") is True,
            }
            records.append(record)
            _pool_creation_intents(pool).remove(intent)
            save_registry(state_root, project_id, registry)
            return {"outcome": "created", "role": role, "threadId": thread_id, "roleRecord": dict(record)}
    except FileExistsError:
        return _pool_busy(role, request_id)


def release_role_claim(state_root: str | Path,
                       project_id: str,
                       *,
                       parent_thread_id: str,
                       role: str,
                       thread_id: str,
                       task_id: str,
                       request_id: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    parent_thread_id = _required_str(parent_thread_id, "parentThreadId")
    _validate_v2_pool_role(role)
    thread_id = _required_str(thread_id, "threadId")
    request_id = _required_str(request_id, "requestId")
    released_at = datetime.now(timezone.utc).isoformat()
    try:
        with manager_pool_lock(
            state_root,
            project_id,
            parent_thread_id,
            task_id=task_id,
            request_id=request_id,
            acquired_at=released_at,
        ):
            registry = load_registry(state_root, project_id)
            pool = _manager_pool(registry, project_id, parent_thread_id)
            released = False
            for record in _pool_role_records(pool, role):
                claim = record.get("claim")
                if (
                    record.get("threadId") == thread_id
                    and isinstance(claim, Mapping)
                    and claim.get("taskId") == task_id
                    and claim.get("requestId") == request_id
                ):
                    record.pop("claim", None)
                    released = True
                    break
            if not released:
                return {"outcome": "not_claimed", "role": role, "threadId": thread_id}
            ledger_file = task_path(state_root, project_id, task_id)
            if ledger_file.exists():
                ledger = load_task_ledger(state_root, project_id, task_id)
                if ledger.get("status") in TERMINAL_STATUSES:
                    _cleanup_terminal_pool_task(
                        state_root,
                        project_id,
                        parent_thread_id,
                        pool,
                        task_id,
                        ledger,
                        released_at,
                    )
                else:
                    ledger["preferredThreadId"] = thread_id
                    save_task_ledger(state_root, project_id, task_id, ledger)
            save_registry(state_root, project_id, registry)
            return {"outcome": "released", "role": role, "threadId": thread_id}
    except FileExistsError:
        return _pool_busy(role, request_id)


def _load_existing_task_ledger(state_root: str | Path, project_id: str,
                               task_id: str) -> dict[str, Any] | None:
    path = task_path(state_root, project_id, task_id)
    return load_task_ledger(state_root, project_id, task_id) if path.exists() else None


def _ledger_matches_pool_identity(ledger: Mapping[str, Any], *, project_id: str,
                                  parent_thread_id: str, task_id: str) -> bool:
    return (
        task_workflow_version(ledger) == 2
        and ledger.get("projectId") == project_id
        and ledger.get("taskId") == task_id
        and ledger.get("parentThreadId") == parent_thread_id
    )


def _ledger_has_creation_outcome_unknown(ledger: Mapping[str, Any]) -> bool:
    candidates = [ledger]
    for key in ("closeout", "failure", "toolError"):
        value = ledger.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
    return any(
        candidate.get(key) == "creation_outcome_unknown"
        for candidate in candidates
        for key in ("reason", "failureReason", "creationOutcome")
    )


def _record_creation_outcome_unknown(ledger: dict[str, Any], *,
                                     project_id: str, parent_thread_id: str,
                                     intent: Mapping[str, Any],
                                     recovered_at: str) -> bool:
    request_id = _required_str(intent.get("requestId"), "creationIntent.requestId")
    observations = _as_list(ledger.get("observations"), "ledger.observations")
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        fields = observation.get("parsedFields")
        if (
            observation.get("type") == "system_event"
            and isinstance(fields, Mapping)
            and fields.get("reason") == "creation_outcome_unknown"
            and fields.get("requestId") == request_id
        ):
            return False
    observations.append({
        "type": "system_event",
        "role": "system",
        "threadId": parent_thread_id,
        "capturedAt": recovered_at,
        "content": "creation_outcome_unknown",
        "parsedFields": {
            "reason": "creation_outcome_unknown",
            "projectId": project_id,
            "parentThreadId": parent_thread_id,
            "taskId": _required_str(intent.get("taskId"), "creationIntent.taskId"),
            "requestId": request_id,
            "role": _required_str(intent.get("role"), "creationIntent.role"),
            "hostId": _required_str(intent.get("hostId"), "creationIntent.hostId"),
            "targetFingerprint": _required_str(
                intent.get("targetFingerprint"), "creationIntent.targetFingerprint",
            ),
        },
    })
    ledger["observations"] = observations
    return True


def _cleanup_terminal_pool_task(state_root: str | Path, project_id: str,
                                parent_thread_id: str, pool: dict[str, Any],
                                task_id: str, ledger: dict[str, Any],
                                recovered_at: str) -> bool:
    if (
        not _ledger_matches_pool_identity(
            ledger,
            project_id=project_id,
            parent_thread_id=parent_thread_id,
            task_id=task_id,
        )
        or ledger.get("status") not in TERMINAL_STATUSES
    ):
        return False
    changed = False
    roles = _as_mapping(pool.get("roles"), "managerPool.roles")
    for role, raw_records in roles.items():
        records = _as_list(raw_records, "managerPool.roles.%s" % role)
        normalized: list[dict[str, Any]] = []
        for raw_record in records:
            record = _as_mapping(raw_record, "managerPool.roles.%s[]" % role, default_empty=False)
            claim = record.get("claim")
            if isinstance(claim, Mapping) and claim.get("taskId") == task_id:
                record.pop("claim", None)
                changed = True
            normalized.append(record)
        roles[role] = normalized
    pool["roles"] = roles

    unknown = _ledger_has_creation_outcome_unknown(ledger)
    kept_intents: list[dict[str, Any]] = []
    observation_changed = False
    for intent in _pool_creation_intents(pool):
        if intent.get("taskId") != task_id:
            kept_intents.append(intent)
            continue
        if unknown:
            observation_changed = _record_creation_outcome_unknown(
                ledger,
                project_id=project_id,
                parent_thread_id=parent_thread_id,
                intent=intent,
                recovered_at=recovered_at,
            ) or observation_changed
        changed = True
    pool["creationIntents"] = kept_intents
    if observation_changed:
        save_task_ledger(state_root, project_id, task_id, ledger)
    return changed


def cleanup_terminal_manager_pool_task(state_root: str | Path,
                                       project_id: str,
                                       *,
                                       parent_thread_id: str,
                                       task_id: str,
                                       cleaned_at: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    parent_thread_id = _required_str(parent_thread_id, "parentThreadId")
    cleaned_at = _required_str(cleaned_at, "cleanedAt")
    ledger = _load_existing_task_ledger(state_root, project_id, task_id)
    if ledger is None:
        return {"outcome": "missing_task_ledger", "taskId": task_id}
    if not _ledger_matches_pool_identity(
        ledger,
        project_id=project_id,
        parent_thread_id=parent_thread_id,
        task_id=task_id,
    ):
        return {"outcome": "identity_mismatch", "taskId": task_id}
    if ledger.get("status") not in TERMINAL_STATUSES:
        return {"outcome": "not_terminal", "taskId": task_id}
    try:
        with manager_pool_lock(
            state_root,
            project_id,
            parent_thread_id,
            task_id=task_id,
            request_id=task_id,
            acquired_at=cleaned_at,
        ):
            ledger = load_task_ledger(state_root, project_id, task_id)
            if not _ledger_matches_pool_identity(
                ledger,
                project_id=project_id,
                parent_thread_id=parent_thread_id,
                task_id=task_id,
            ):
                return {"outcome": "identity_mismatch", "taskId": task_id}
            if ledger.get("status") not in TERMINAL_STATUSES:
                return {"outcome": "not_terminal", "taskId": task_id}
            registry = load_registry(state_root, project_id)
            pool = _manager_pool(registry, project_id, parent_thread_id)
            changed = _cleanup_terminal_pool_task(
                state_root,
                project_id,
                parent_thread_id,
                pool,
                task_id,
                ledger,
                cleaned_at,
            )
            if changed:
                save_registry(state_root, project_id, registry)
            return {"outcome": "cleaned", "taskId": task_id, "changed": changed}
    except FileExistsError:
        return {"outcome": "busy", "taskId": task_id}


def recover_manager_pool_lock(state_root: str | Path,
                              project_id: str,
                              parent_thread_id: str,
                              *,
                              task_id: str,
                              request_id: str,
                              recovered_at: str) -> bool:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    parent_thread_id = _required_str(parent_thread_id, "parentThreadId")
    request_id = _required_str(request_id, "requestId")
    _required_str(recovered_at, "recoveredAt")
    lock_path = manager_pool_lock_path(state_root, project_id, parent_thread_id)
    try:
        payload = lock_path.read_bytes()
        data = json.loads(payload.decode("utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, Mapping):
        return False
    if (
        data.get("projectId") != project_id
        or data.get("parentThreadId") != parent_thread_id
        or data.get("taskId") != task_id
        or data.get("requestId") != request_id
        or not isinstance(data.get("pid"), int)
        or not isinstance(data.get("acquiredAt"), str)
        or not data["acquiredAt"]
    ):
        return False
    ledger = _load_existing_task_ledger(state_root, project_id, task_id)
    if ledger is None or not _ledger_matches_pool_identity(
        ledger,
        project_id=project_id,
        parent_thread_id=parent_thread_id,
        task_id=task_id,
    ) or ledger.get("status") not in TERMINAL_STATUSES:
        return False
    try:
        if lock_path.read_bytes() != payload:
            return False
        lock_path.unlink()
    except (FileNotFoundError, OSError):
        return False
    return True


def recover_creation_intent(state_root: str | Path,
                            project_id: str,
                            *,
                            parent_thread_id: str,
                            role: str,
                            request_id: str,
                            recovered_at: str) -> dict[str, Any] | None:
    _validate_task_id(project_id)
    parent_thread_id = _required_str(parent_thread_id, "parentThreadId")
    _validate_v2_pool_role(role)
    request_id = _required_str(request_id, "requestId")
    recovered_at = _required_str(recovered_at, "recoveredAt")
    registry = load_registry(state_root, project_id)
    intent = _find_creation_intent(
        _manager_pool(registry, project_id, parent_thread_id),
        parent_thread_id=parent_thread_id,
        role=role,
        request_id=request_id,
    )
    if intent is None:
        return None
    task_id = _required_str(intent.get("taskId"), "creationIntent.taskId")
    try:
        with manager_pool_lock(
            state_root,
            project_id,
            parent_thread_id,
            task_id=task_id,
            request_id=request_id,
            acquired_at=recovered_at,
        ):
            registry = load_registry(state_root, project_id)
            pool = _manager_pool(registry, project_id, parent_thread_id)
            intent = _find_creation_intent(
                pool,
                parent_thread_id=parent_thread_id,
                role=role,
                request_id=request_id,
            )
            if intent is None:
                return None
            ledger = _load_existing_task_ledger(state_root, project_id, task_id)
            if ledger is None:
                return {"outcome": "missing_task_ledger", "requestId": request_id}
            if not _ledger_matches_pool_identity(
                ledger,
                project_id=project_id,
                parent_thread_id=parent_thread_id,
                task_id=task_id,
            ):
                return {"outcome": "identity_mismatch", "requestId": request_id}
            if ledger.get("status") not in TERMINAL_STATUSES:
                return dict(intent)
            if _cleanup_terminal_pool_task(
                state_root,
                project_id,
                parent_thread_id,
                pool,
                task_id,
                ledger,
                recovered_at,
            ):
                save_registry(state_root, project_id, registry)
            return None
    except FileExistsError:
        return _pool_busy(role, request_id)


def _normalize_task_ledger(data: Mapping[str, Any], state_root: str | Path,
                           project_id: str, task_id: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    ledger = dict(data)
    ledger["workflowVersion"] = task_workflow_version(ledger)
    ledger["version"] = TASK_LEDGER_VERSION
    ledger["taskId"] = task_id
    ledger["projectId"] = project_id
    ledger["stateRoot"] = str(_resolve_persistent_state_root(state_root))
    ledger["projectLocalPath"] = str(ledger.get("projectLocalPath") or "")
    ledger["objective"] = str(ledger.get("objective") or "")
    ledger["status"] = str(ledger.get("status") or "created")
    ledger["reworkCount"] = _as_int(ledger.get("reworkCount"), 0, "ledger.reworkCount")
    ledger["maxRework"] = _as_int(ledger.get("maxRework"), 3, "ledger.maxRework")
    ledger["dispatches"] = _as_list(ledger.get("dispatches"), "ledger.dispatches")
    ledger["observations"] = _as_list(ledger.get("observations"), "ledger.observations")
    plan_request = ledger.get("planRequest")
    ledger["planRequest"] = None if plan_request is None else _as_mapping(plan_request, "ledger.planRequest", default_empty=False)
    plan = ledger.get("plan")
    ledger["plan"] = None if plan is None else _as_mapping(plan, "ledger.plan", default_empty=False)
    review = ledger.get("review")
    ledger["review"] = None if review is None else _as_mapping(review, "ledger.review", default_empty=False)
    architecture_review = ledger.get("architectureReview")
    ledger["architectureReview"] = None if architecture_review is None else _as_mapping(
        architecture_review,
        "ledger.architectureReview",
        default_empty=False,
    )
    qa_review = ledger.get("qaReview")
    ledger["qaReview"] = None if qa_review is None else _as_mapping(qa_review, "ledger.qaReview", default_empty=False)
    verification = ledger.get("verification")
    ledger["verification"] = None if verification is None else _as_mapping(verification, "ledger.verification", default_empty=False)
    review_package = ledger.get("reviewPackage")
    ledger["reviewPackage"] = None if review_package is None else _as_mapping(review_package, "ledger.reviewPackage", default_empty=False)
    authorization_package = ledger.get("taskAuthorizationPackage")
    ledger["taskAuthorizationPackage"] = None if authorization_package is None else _as_mapping(
        authorization_package,
        "ledger.taskAuthorizationPackage",
        default_empty=False,
    )
    manager_acceptance = ledger.get("managerAcceptance")
    ledger["managerAcceptance"] = None if manager_acceptance is None else _as_mapping(
        manager_acceptance,
        "ledger.managerAcceptance",
        default_empty=False,
    )
    resolved_plan = ledger.get("resolvedPlan")
    ledger["resolvedPlan"] = None if resolved_plan is None else _as_mapping(
        resolved_plan,
        "ledger.resolvedPlan",
        default_empty=False,
    )
    ledger.setdefault("closeout", None)
    return ledger


def new_task_ledger(state_root: str | Path,
                    project_id: str,
                    task_id: str,
                    *,
                    objective: str,
                    project_local_path: str | Path,
                    max_rework: int = 3) -> dict[str, Any]:
    if not isinstance(objective, str) or not objective:
        raise StateStoreError("objective must be a non-empty string")
    if not isinstance(max_rework, int) or isinstance(max_rework, bool) or max_rework < 0:
        raise StateStoreError("maxRework must be a non-negative integer")
    return _normalize_task_ledger({
        "projectLocalPath": str(Path(project_local_path).resolve()),
        "objective": objective,
        "status": "created",
        "reworkCount": 0,
        "maxRework": max_rework,
        "dispatches": [],
        "observations": [],
        "review": None,
        "architectureReview": None,
        "qaReview": None,
        "verification": None,
        "closeout": None,
    }, state_root, project_id, task_id)


def new_v2_task_ledger(state_root: str | Path,
                       project_id: str,
                       task_id: str,
                       *,
                       objective: str,
                       project_local_path: str | Path,
                       parent_thread_id: str,
                       resolved_plan: Mapping[str, Any],
                       task_authorization_package: Mapping[str, Any],
                       created_at: str,
                       max_rework: int = 1) -> dict[str, Any]:
    ledger = new_task_ledger(
        state_root,
        project_id,
        task_id,
        objective=objective,
        project_local_path=project_local_path,
        max_rework=max_rework,
    )
    ledger.update({
        "workflowVersion": 2,
        "parentThreadId": _required_str(parent_thread_id, "parentThreadId"),
        "createdAt": _required_str(created_at, "createdAt"),
        "status": "planned",
        "plan": _as_mapping(resolved_plan, "resolvedPlan", default_empty=False),
        "taskAuthorizationPackage": _as_mapping(
            task_authorization_package,
            "taskAuthorizationPackage",
            default_empty=False,
        ),
        "managerAcceptance": None,
        "modelUpgradeCount": 0,
    })
    return _normalize_task_ledger(ledger, state_root, project_id, task_id)


def load_task_ledger(state_root: str | Path, project_id: str,
                     task_id: str) -> dict[str, Any]:
    data = _read_json_object(task_path(state_root, project_id, task_id))
    return _normalize_task_ledger(data, state_root, project_id, task_id)


def save_task_ledger(state_root: str | Path,
                     project_id: str,
                     task_id: str,
                     ledger: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_task_ledger(ledger, state_root, project_id, task_id)
    _atomic_write_json(task_path(state_root, project_id, task_id), normalized)
    return normalized




def create_task_id(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    return "ctr-%s-%s" % (now.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])


def _validate_role(role: str) -> None:
    if role not in ROLE_NAMES:
        raise StateStoreError("invalid role: %s" % role)


def _validate_permission(permission: str) -> None:
    if permission not in THREAD_PERMISSIONS:
        raise StateStoreError("invalid Team Router permission: %s" % permission)


def _raise_if_terminal(ledger: Mapping[str, Any], action: str) -> None:
    status = ledger.get("status")
    if status in TERMINAL_STATUSES:
        raise StateStoreError(
            "cannot %s terminal task status: %s" % (action, status)
        )


def _required_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise StateStoreError("%s must be a non-empty string" % field)
    return value


def _search_anchor(message_id: str | None, sent_at: str) -> dict[str, Any]:
    return {"messageId": message_id, "sentAt": _required_str(sent_at, "sentAt")}

def _has_observation_content(ledger: Mapping[str, Any],
                             obs_type: str,
                             role: str,
                             thread_id: str,
                             content: str) -> bool:
    observations = ledger.get("observations") if isinstance(ledger.get("observations"), list) else []
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        if (
            observation.get("type") == obs_type
            and observation.get("role") == role
            and observation.get("threadId") == thread_id
            and observation.get("content") == content
        ):
            return True
    return False


def _latest_executor_callback_observation(ledger: Mapping[str, Any]) -> Mapping[str, Any] | None:
    observations = ledger.get("observations") if isinstance(ledger.get("observations"), list) else []
    for observation in reversed(observations):
        if (
            isinstance(observation, Mapping)
            and observation.get("role") == "executor"
            and observation.get("type") == "callback_raw"
        ):
            return observation
    return None


def _latest_executor_dispatch(ledger: Mapping[str, Any]) -> Mapping[str, Any] | None:
    dispatches = ledger.get("dispatches") if isinstance(ledger.get("dispatches"), list) else []
    return dispatches[-1] if dispatches and isinstance(dispatches[-1], Mapping) else None


def _latest_reviewer_request(ledger: Mapping[str, Any]) -> Mapping[str, Any] | None:
    review = ledger.get("review") if isinstance(ledger.get("review"), Mapping) else None
    request = review.get("request") if isinstance(review, Mapping) else None
    return request if isinstance(request, Mapping) else None


def _return_thread_id_from_record(record: Mapping[str, Any] | None,
                                  fallback: str | None) -> str | None:
    if isinstance(record, Mapping):
        value = record.get("returnThreadId")
        return value if isinstance(value, str) and value else fallback
    return fallback


def _inherited_reviewer_return_thread_id(ledger: Mapping[str, Any],
                                         fallback: str | None) -> str | None:
    return _return_thread_id_from_record(_latest_executor_dispatch(ledger), fallback)


def _inherited_verifier_return_thread_id(ledger: Mapping[str, Any],
                                         fallback: str | None) -> str | None:
    reviewer_return = _return_thread_id_from_record(_latest_reviewer_request(ledger), None)
    if reviewer_return is not None:
        return reviewer_return
    return _return_thread_id_from_record(_latest_executor_dispatch(ledger), fallback)


def _role_review_request_record(
    *,
    role: str,
    thread_id: str,
    marker: str,
    task_id: str,
    sent_at: str,
    message_id: str | None,
    return_thread_id: str | None,
    delivery_key: str,
    fallback_key: str,
) -> dict[str, Any]:
    thread_id = _required_str(thread_id, "%sThreadId" % role)
    sent_at = _required_str(sent_at, "sentAt")
    search_anchor = _search_anchor(message_id, sent_at)
    request: dict[str, Any] = {
        "role": role,
        "threadId": thread_id,
        "roleThreadId": thread_id,
        "sourceRoleThreadId": thread_id,
        "messageId": message_id,
        "sentAt": sent_at,
        "expectedMarker": marker,
        "expectedCallback": "%s taskId=%s" % (marker, task_id),
        "searchAnchor": search_anchor,
        "fallbackSearchAnchor": dict(search_anchor),
        "returnSearchAnchor": {"messageId": None, "sentAt": sent_at},
        fallback_key: "self-thread-marker",
    }
    if return_thread_id is not None:
        request["returnThreadId"] = _required_str(return_thread_id, "returnThreadId")
        request["orchestratorThreadId"] = request["returnThreadId"]
        request[delivery_key] = "direct-send"
        request["callbackMode"] = "direct-return runtime"
        request["deliveryStatus"] = "direct_return_requested"
    else:
        request["returnThreadId"] = None
        request["orchestratorThreadId"] = None
        request[delivery_key] = "fallback_only"
        request["callbackMode"] = "manual orchestration fallback"
        request["deliveryStatus"] = "fallback_only"
        request["deliveryError"] = "returnThreadId unavailable; direct-return runtime not established"
    return request
def _normalize_role_record(role: str, data: Mapping[str, Any],
                           observed_at: str) -> dict[str, Any]:
    _validate_role(role)
    record = dict(_as_mapping(data, "roles.%s" % role, default_empty=False))
    record["threadId"] = _required_str(record.get("threadId"), "roles.%s.threadId" % role)
    record["title"] = str(record.get("title") or "TeamRouter %s" % role)
    record["status"] = str(record.get("status") or "active")
    record.setdefault("createdAt", observed_at)
    record["lastObservedAt"] = observed_at
    return record


def update_registry_roles(state_root: str | Path,
                          project_id: str,
                          roles: Mapping[str, Mapping[str, Any]],
                          observed_at: str) -> dict[str, Any]:
    registry = load_registry(state_root, project_id)
    project = registry["projects"][project_id]
    project_roles = _as_mapping(project.get("roles"), "registry.project.roles")
    for role, data in roles.items():
        project_roles[role] = _normalize_role_record(role, data, observed_at)
    project["roles"] = project_roles
    registry["projects"][project_id] = project
    return save_registry(state_root, project_id, registry)


def create_team_task(state_root: str | Path,
                     project_id: str,
                     task_id: str,
                     *,
                     objective: str,
                     project_local_path: str | Path,
                     roles: Mapping[str, Mapping[str, Any]],
                     observed_at: str,
                     max_rework: int = 3) -> dict[str, Any]:
    missing = sorted(CORE_ROLE_NAMES.difference(roles.keys()))
    if missing:
        raise StateStoreError("missing role bindings: %s" % ", ".join(missing))
    update_registry_roles(state_root, project_id, roles, observed_at)
    ledger = new_task_ledger(
        state_root,
        project_id,
        task_id,
        objective=objective,
        project_local_path=project_local_path,
        max_rework=max_rework,
    )
    ledger["status"] = "roles_ready"
    return save_task_ledger(state_root, project_id, task_id, ledger)

def _project_roles_from_registry(registry: Mapping[str, Any], project_id: str) -> dict[str, Any]:
    projects = _as_mapping(registry.get("projects"), "registry.projects")
    project = _as_mapping(projects.get(project_id), "registry.project", default_empty=False)
    return _as_mapping(project.get("roles"), "registry.project.roles")
