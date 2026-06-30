# -*- coding: utf-8 -*-
"""State, registry, and task-ledger JSON primitives for Team Router."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import uuid
from typing import Any, Mapping

from team_router_protocol import _validate_task_id


class StateStoreError(ValueError):
    """Raised when registry or task ledger JSON cannot be read safely."""


REGISTRY_VERSION = 1
TASK_LEDGER_VERSION = 1
ROLE_NAMES = frozenset({"manager", "executor", "reviewer", "verifier", "architect", "qa"})
CORE_ROLE_NAMES = frozenset({"manager", "executor", "verifier"})
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
    projects = _as_mapping(registry.get("projects"), "registry.projects")
    project = _as_mapping(
        projects.get(project_id),
        "registry.projects.%s" % project_id,
    )
    roles = _as_mapping(project.get("roles"), "registry.projects.%s.roles" % project_id)

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


def _normalize_task_ledger(data: Mapping[str, Any], state_root: str | Path,
                           project_id: str, task_id: str) -> dict[str, Any]:
    _validate_task_id(project_id)
    _validate_task_id(task_id)
    ledger = dict(data)
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
