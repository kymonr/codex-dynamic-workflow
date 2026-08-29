"""Agent Fleet v1 planning, execution, aggregation, and status runtime."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from skill import platform_paths
    from skill import runner as legacy
    from skill.fleet_candidate import (
        FleetCandidateError,
        assert_candidate_stable,
        capture_candidate,
        repository_root,
        validate_candidate_package,
    )
    from skill.fleet_contract import (
        FleetContractError,
        FleetPackage,
        canonical_digest,
        load_package,
        validate_package,
    )
    from skill.fleet_escalation import FleetEscalationError, decide_sol_escalation
    from skill.fleet_findings import (
        FleetFindingError,
        add_new_findings,
        apply_challenges,
        apply_reproductions,
        assign_findings,
        build_finding_graph,
        finalize_findings,
        finding_ids,
    )
    from skill.fleet_presets import build_schedule
    from skill.fleet_process import (
        LUNA_ROUTE,
        SOL_ARBITER_ROUTE,
        FleetProcessError,
        arbiter_prompt,
        challenge_prompt,
        discovery_prompt,
        probe_codex_capabilities,
        reproduction_prompt,
        run_codex_attempt,
    )
    from skill.fleet_records import (
        FleetRecordError,
        arbiter_schema,
        challenge_schema,
        discovery_schema,
        reproduction_schema,
        validate_arbiter_record,
        validate_challenge_record,
        validate_discovery_record,
        validate_reproduction_record,
    )
except ModuleNotFoundError as exc:
    if exc.name != "skill":
        raise
    import platform_paths
    import runner as legacy
    from fleet_candidate import (
        FleetCandidateError,
        assert_candidate_stable,
        capture_candidate,
        repository_root,
        validate_candidate_package,
    )
    from fleet_contract import (
        FleetContractError,
        FleetPackage,
        canonical_digest,
        load_package,
        validate_package,
    )
    from fleet_escalation import FleetEscalationError, decide_sol_escalation
    from fleet_findings import (
        FleetFindingError,
        add_new_findings,
        apply_challenges,
        apply_reproductions,
        assign_findings,
        build_finding_graph,
        finalize_findings,
        finding_ids,
    )
    from fleet_presets import build_schedule
    from fleet_process import (
        LUNA_ROUTE,
        SOL_ARBITER_ROUTE,
        FleetProcessError,
        arbiter_prompt,
        challenge_prompt,
        discovery_prompt,
        probe_codex_capabilities,
        reproduction_prompt,
        run_codex_attempt,
    )
    from fleet_records import (
        FleetRecordError,
        arbiter_schema,
        challenge_schema,
        discovery_schema,
        reproduction_schema,
        validate_arbiter_record,
        validate_challenge_record,
        validate_discovery_record,
        validate_reproduction_record,
    )

FLEET_RUNTIME_VERSION = 1
FLEET_RUNTIME_NAME = "agent-fleet-v1"
FLEET_ACK = "--ack-read-only-agent-fleet"
FLEET_RUNS_SUBDIR = "fleets"
MAX_AGENT_TIMEOUT_SECONDS = 7200
MAX_SOL_TIMEOUT_SECONDS = 7200
TERMINAL_STATES = frozenset(
    {
        "accepted",
        "accepted_with_notes",
        "ship",
        "fix_first",
        "rethink",
        "verification_failed",
        "attention_required",
    }
)

ProcessAdapter = Callable[..., dict[str, Any]]


class FleetRuntimeError(RuntimeError):
    """The Agent Fleet host runtime cannot continue safely."""


class FleetVerificationError(FleetRuntimeError):
    """A fixed verification command failed or changed the candidate."""

    def __init__(
        self,
        message: str,
        *,
        results: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.results = [dict(item) for item in (results or [])]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _timestamp_slug() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def _runs_root() -> Path:
    return Path(platform_paths.default_runs_root()) / FLEET_RUNS_SUBDIR


def _atomic_bytes(path: Path, payload: bytes, *, maximum: int, label: str) -> None:
    if len(payload) > maximum:
        raise FleetRuntimeError(f"{label} exceeds {maximum} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _atomic_json(path: Path, value: Any, *, maximum: int = 32 * 1024 * 1024) -> None:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise FleetRuntimeError(f"cannot encode {path.name}: {exc}") from exc
    _atomic_bytes(path, payload, maximum=maximum, label=path.name)


def _append_event(run_dir: Path, sequence: int, event_type: str, payload: Mapping[str, Any]) -> int:
    next_sequence = sequence + 1
    record = {
        "sequence": next_sequence,
        "timestamp": now_iso(),
        "type": event_type,
        "payload": dict(payload),
    }
    encoded = (json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > 256 * 1024:
        raise FleetRuntimeError("fleet event exceeds 256 KiB")
    path = run_dir / "events.jsonl"
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return next_sequence


def _codex_preflight() -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    try:
        prefix, identity = legacy.resolve_codex_prefix()
        capabilities = probe_codex_capabilities(prefix)
    except (legacy.WorkflowError, FleetProcessError) as exc:
        raise FleetRuntimeError(str(exc)) from exc
    return list(prefix), dict(identity), capabilities


def _candidate_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_revision": candidate["candidate_revision"],
        "repository_full_name": candidate["repository_full_name"],
        "head": candidate["head"],
        "tree": candidate["tree"],
        "changed_files": list(candidate["changed_files"]),
        "patch_bytes": candidate["patch"]["bytes"],
        "patch_sha256": candidate["patch"]["sha256"],
        "untracked_files": [
            {key: item[key] for key in ("path", "bytes", "sha256")}
            for item in candidate["untracked_files"]
        ],
        "total_candidate_bytes": candidate["total_candidate_bytes"],
    }


def plan_fleet(
    *,
    package_path: str | Path,
    repository: str | Path,
    expected_package_digest: str,
) -> dict[str, Any]:
    package = load_package(package_path)
    if package.digest != expected_package_digest:
        raise FleetRuntimeError(
            f"package digest mismatch: expected={expected_package_digest} actual={package.digest}"
        )
    root = repository_root(repository)
    candidate = capture_candidate(root, package)
    schedule = build_schedule(package)
    prefix, identity, capabilities = _codex_preflight()
    return {
        "operation": "fleet-plan",
        "runtime": FLEET_RUNTIME_NAME,
        "runtime_version": FLEET_RUNTIME_VERSION,
        "model_calls": 0,
        "writes": [],
        "run_directory_created": False,
        "package": package.value,
        "package_digest": package.digest,
        "repository": str(root),
        "candidate": _candidate_summary(candidate),
        "schedule": schedule,
        "codex_prefix": prefix,
        "codex_identity": identity,
        "codex_capabilities": capabilities,
        "sol_route": {
            **SOL_ARBITER_ROUTE.record(),
            "conditional": True,
            "fresh": True,
            "attempts": 1,
            "retry": 0,
        },
        "automatic_retry": False,
        "automatic_write": False,
        "majority_vote": False,
    }


def _validation_argv(argv: Sequence[str]) -> list[str]:
    first = argv[0].casefold()
    if first in {"python", "python3", "py"}:
        return [sys.executable, *argv[1:]]
    if first == "pytest":
        return [sys.executable, "-m", "pytest", *argv[1:]]
    raise FleetVerificationError(f"unsupported validation executable: {argv[0]}")


def _validation_env(temp_root: Path) -> dict[str, str]:
    temp_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "PYTHONPYCACHEPREFIX": temp_root / "pycache",
        "XDG_CACHE_HOME": temp_root / "cache",
        "HOME": temp_root / "home",
        "TEMP": temp_root / "temp",
        "TMP": temp_root / "temp",
        "TMPDIR": temp_root / "temp",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    env = legacy._sanitized_child_env()
    env.update({key: str(value) for key, value in paths.items()})
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_COLOR": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    return env


def _run_verification(
    *,
    package: FleetPackage,
    repository: Path,
    candidate: Mapping[str, Any],
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    output_dir = run_dir / "verification"
    temp_root = run_dir / "verification-temp"
    for command in package.verification["commands"]:
        argv = _validation_argv(command["argv"])
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=str(repository),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=command["timeout_seconds"],
                env=_validation_env(temp_root / command["id"]),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FleetVerificationError(
                f"verification {command['id']} failed to complete: {exc}"
            ) from exc
        max_log = package.limits["max_agent_log_bytes"]
        if len(completed.stdout) > max_log or len(completed.stderr) > max_log:
            raise FleetVerificationError(
                f"verification {command['id']} output exceeds the log limit"
            )
        stdout_path = output_dir / f"{command['id']}.stdout.txt"
        stderr_path = output_dir / f"{command['id']}.stderr.txt"
        _atomic_bytes(
            stdout_path,
            completed.stdout,
            maximum=max_log,
            label=f"verification {command['id']} stdout",
        )
        _atomic_bytes(
            stderr_path,
            completed.stderr,
            maximum=max_log,
            label=f"verification {command['id']} stderr",
        )
        result = {
            "id": command["id"],
            "argv": argv,
            "shell": False,
            "cwd": str(repository),
            "exit_code": completed.returncode,
            "timed_out": False,
            "duration_s": round(time.monotonic() - started, 3),
            "stdout": {
                "path": str(stdout_path),
                "bytes": len(completed.stdout),
                "sha256": hashlib.sha256(completed.stdout).hexdigest(),
            },
            "stderr": {
                "path": str(stderr_path),
                "bytes": len(completed.stderr),
                "sha256": hashlib.sha256(completed.stderr).hexdigest(),
            },
            "passed": completed.returncode == 0,
        }
        results.append(result)
        assert_candidate_stable(repository, package, candidate)
        if not result["passed"]:
            raise FleetVerificationError(
                f"verification {command['id']} exited {completed.returncode}",
                results=results,
            )
    required = set(package.verification["required_ids"])
    passed = {item["id"] for item in results if item["passed"]}
    if not required <= passed:
        raise FleetVerificationError(
            f"required verification evidence is incomplete: {sorted(required - passed)}",
            results=results,
        )
    return results


def _validate_process_entry(
    entry: Mapping[str, Any],
    *,
    route: Any,
) -> dict[str, Any]:
    expected = {
        "status": "succeeded",
        "role": route.role,
        "model": route.model,
        "effort": route.effort,
        "tier": route.tier,
        "requested_sandbox": route.sandbox,
        "observed_sandbox": "unknown",
        "attempt_count": 1,
        "retry": 0,
        "upgrade": None,
        "nested_agents": 0,
    }
    for key, value in expected.items():
        if entry.get(key) != value:
            raise FleetRuntimeError(
                f"process identity mismatch for {key}: expected={value!r} actual={entry.get(key)!r}"
            )
    if not isinstance(entry.get("codex_identity"), dict):
        raise FleetRuntimeError("process codex_identity must be an object")
    if not isinstance(entry.get("output"), dict):
        raise FleetRuntimeError("process output must be an object")
    return dict(entry)


def _persisted_process_record(
    entry: Mapping[str, Any],
    *,
    agent_id: str,
    role_id: str,
    phase: str,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "role_id": role_id,
        "phase": phase,
        "status": entry.get("status"),
        "role": entry.get("role"),
        "model": entry.get("model"),
        "effort": entry.get("effort"),
        "tier": entry.get("tier"),
        "requested_sandbox": entry.get("requested_sandbox"),
        "observed_sandbox": entry.get("observed_sandbox"),
        "attempt_count": entry.get("attempt_count"),
        "retry": entry.get("retry"),
        "upgrade": entry.get("upgrade"),
        "nested_agents": entry.get("nested_agents"),
        "codex_identity": entry.get("codex_identity"),
        "output_digest": canonical_digest(entry.get("output")),
    }


def _run_parallel(
    *,
    agents: Sequence[Mapping[str, Any]],
    run_one: Callable[[Mapping[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    if not agents:
        return []
    results: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as executor:
        futures = {executor.submit(run_one, agent): agent for agent in agents}
        for future in concurrent.futures.as_completed(futures):
            agent = futures[future]
            try:
                results[agent["agent_id"]] = future.result()
            except Exception as exc:
                for other in futures:
                    other.cancel()
                raise FleetRuntimeError(
                    f"fleet agent {agent['agent_id']} failed: {type(exc).__name__}: {exc}"
                ) from exc
    return [results[agent["agent_id"]] for agent in agents]


def _is_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _manifest_files(root: Path) -> list[dict[str, Any]]:
    if root.is_symlink() or _is_reparse(root):
        raise FleetRuntimeError("fleet run directory cannot be a link/reparse point")
    files: list[dict[str, Any]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise FleetRuntimeError(f"cannot enumerate fleet evidence: {exc}") from exc
        for path in children:
            relative = path.relative_to(root).as_posix()
            if relative == "evidence-manifest.json":
                continue
            if path.is_symlink() or _is_reparse(path):
                raise FleetRuntimeError(
                    f"run evidence contains a link/reparse point: {relative}"
                )
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise FleetRuntimeError(f"cannot inspect run evidence {relative}: {exc}") from exc
            if path.is_dir():
                stack.append(path)
            elif path.is_file():
                payload = path.read_bytes()
                files.append(
                    {
                        "path": relative,
                        "bytes": metadata.st_size,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            else:
                raise FleetRuntimeError(
                    f"run evidence contains unsupported file type: {relative}"
                )
    files.sort(key=lambda item: item["path"].casefold())
    return files


def _write_summary_and_manifest(run_dir: Path, state: Mapping[str, Any]) -> None:
    _atomic_json(run_dir / "summary.json", state)
    files = _manifest_files(run_dir)
    basis = {
        "manifest_version": 1,
        "runtime": FLEET_RUNTIME_NAME,
        "run_id": state["run_id"],
        "files": files,
    }
    _atomic_json(
        run_dir / "evidence-manifest.json",
        {**basis, "manifest_digest": canonical_digest(basis)},
    )


def _terminal_state(
    *,
    state: dict[str, Any],
    run_dir: Path,
    terminal: str,
    error: str | None = None,
) -> dict[str, Any]:
    if terminal not in TERMINAL_STATES:
        raise FleetRuntimeError(f"invalid fleet terminal state: {terminal}")
    state["state"] = terminal
    state["terminal"] = True
    state["finished_at"] = now_iso()
    state["error"] = error
    state["event_sequence"] = _append_event(
        run_dir,
        state["event_sequence"],
        "fleet.run.completed" if terminal not in {"verification_failed", "attention_required"} else "fleet.run.attention_required",
        {"run_id": state["run_id"], "state": terminal, "error": error},
    )
    _write_summary_and_manifest(run_dir, state)
    return dict(state)


def run_fleet(
    *,
    package_path: str | Path,
    repository: str | Path,
    expected_package_digest: str,
    ack_read_only_agent_fleet: bool,
    requested_run_dir: str | Path | None = None,
    process_adapter: ProcessAdapter = run_codex_attempt,
) -> dict[str, Any]:
    if not ack_read_only_agent_fleet:
        raise FleetRuntimeError(f"fleet-run requires {FLEET_ACK}")
    plan = plan_fleet(
        package_path=package_path,
        repository=repository,
        expected_package_digest=expected_package_digest,
    )
    package = FleetPackage(plan["package"], plan["package_digest"])
    root = Path(plan["repository"])
    candidate = capture_candidate(root, package)
    if candidate["candidate_revision"] != plan["candidate"]["candidate_revision"]:
        raise FleetRuntimeError("candidate changed between fleet-plan and fleet-run")
    schedule = plan["schedule"]
    runs_root = _runs_root().expanduser().resolve(strict=False)
    runs_root.mkdir(parents=True, exist_ok=True)
    run_id = f"{package.name}-{_timestamp_slug()}-{uuid.uuid4().hex[:12]}"
    if requested_run_dir is None:
        run_dir = runs_root / run_id
    else:
        run_dir = Path(requested_run_dir).expanduser().resolve(strict=False)
        if not run_dir.is_relative_to(runs_root):
            raise FleetRuntimeError(f"requested run directory must be below {runs_root}")
    if run_dir.exists() or run_dir.is_symlink():
        raise FleetRuntimeError(f"fleet run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)

    state: dict[str, Any] = {
        "runtime": FLEET_RUNTIME_NAME,
        "runtime_version": FLEET_RUNTIME_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": "running",
        "terminal": False,
        "created_at": now_iso(),
        "finished_at": None,
        "package_digest": package.digest,
        "candidate_revision": candidate["candidate_revision"],
        "repository": str(root),
        "preset": package.preset,
        "agent_count": package.agent_count,
        "schedule_digest": schedule["schedule_digest"],
        "verification_results": [],
        "agent_records": [],
        "process_records": [],
        "findings": [],
        "aggregation": None,
        "sol_arbitration": None,
        "model_calls": 0,
        "event_sequence": 0,
        "error": None,
    }
    try:
        _atomic_json(run_dir / "fleet-package.resolved.json", package.value)
        _atomic_json(run_dir / "candidate-package.json", candidate)
        _atomic_json(run_dir / "schedule.json", schedule)
        state["event_sequence"] = _append_event(
            run_dir,
            state["event_sequence"],
            "fleet.run.created",
            {
                "run_id": run_id,
                "package_digest": package.digest,
                "candidate_revision": candidate["candidate_revision"],
                "agent_count": package.agent_count,
            },
        )

        verification = _run_verification(
            package=package,
            repository=root,
            candidate=candidate,
            run_dir=run_dir,
        )
        state["verification_results"] = verification
        _atomic_json(run_dir / "verification-results.json", verification)
        state["event_sequence"] = _append_event(
            run_dir,
            state["event_sequence"],
            "fleet.verification.completed",
            {"count": len(verification), "passed": True},
        )

        agents = schedule["agents"]
        discovery_agents = [item for item in agents if item["phase"] == "discovery"]

        def run_discovery(agent: Mapping[str, Any]) -> dict[str, Any]:
            entry = process_adapter(
                attempt_dir=run_dir / "tasks" / agent["agent_id"] / "attempt-01-luna",
                cwd=root,
                prompt=discovery_prompt(
                    package=package,
                    candidate=candidate,
                    verification=verification,
                    agent=agent,
                ),
                schema=discovery_schema(
                    candidate_revision=candidate["candidate_revision"], agent=agent
                ),
                route=LUNA_ROUTE,
                timeout_seconds=MAX_AGENT_TIMEOUT_SECONDS,
                max_output_bytes=package.limits["max_agent_output_bytes"],
                max_log_bytes=package.limits["max_agent_log_bytes"],
                codex_prefix=plan["codex_prefix"],
                codex_identity=plan["codex_identity"],
            )
            entry = _validate_process_entry(entry, route=LUNA_ROUTE)
            record = validate_discovery_record(
                entry["output"],
                candidate_revision=candidate["candidate_revision"],
                agent=agent,
            )
            entry["output"] = record
            return entry

        state["model_calls"] += len(discovery_agents)
        discovery_entries = _run_parallel(agents=discovery_agents, run_one=run_discovery)
        discovery_records = [item["output"] for item in discovery_entries]
        state["agent_records"].extend(discovery_records)
        state["process_records"].extend(
            _persisted_process_record(
                entry,
                agent_id=agent["agent_id"],
                role_id=agent["role_id"],
                phase="discovery",
            )
            for agent, entry in zip(discovery_agents, discovery_entries, strict=True)
        )
        _atomic_json(run_dir / "discovery-records.json", discovery_records)
        _atomic_json(run_dir / "process-records.json", state["process_records"])
        assert_candidate_stable(root, package, candidate)
        graph = build_finding_graph(discovery_records)
        state["event_sequence"] = _append_event(
            run_dir,
            state["event_sequence"],
            "fleet.discovery.completed",
            {"agents": len(discovery_records), "findings": len(graph)},
        )

        challenge_agents = [item for item in agents if item["phase"] == "challenge"]
        challenge_assignments = assign_findings(
            finding_ids(graph), [item["agent_id"] for item in challenge_agents]
        )

        def run_challenge(agent: Mapping[str, Any]) -> dict[str, Any]:
            assigned = challenge_assignments[agent["agent_id"]]
            assigned_findings = [graph[item] for item in assigned]
            entry = process_adapter(
                attempt_dir=run_dir / "tasks" / agent["agent_id"] / "attempt-01-luna",
                cwd=root,
                prompt=challenge_prompt(
                    package=package,
                    candidate=candidate,
                    verification=verification,
                    agent=agent,
                    findings=assigned_findings,
                ),
                schema=challenge_schema(
                    candidate_revision=candidate["candidate_revision"], agent=agent
                ),
                route=LUNA_ROUTE,
                timeout_seconds=MAX_AGENT_TIMEOUT_SECONDS,
                max_output_bytes=package.limits["max_agent_output_bytes"],
                max_log_bytes=package.limits["max_agent_log_bytes"],
                codex_prefix=plan["codex_prefix"],
                codex_identity=plan["codex_identity"],
            )
            entry = _validate_process_entry(entry, route=LUNA_ROUTE)
            record = validate_challenge_record(
                entry["output"],
                candidate_revision=candidate["candidate_revision"],
                agent=agent,
                finding_ids=assigned,
            )
            entry["output"] = record
            return entry

        state["model_calls"] += len(challenge_agents)
        challenge_entries = _run_parallel(agents=challenge_agents, run_one=run_challenge)
        challenge_records = [item["output"] for item in challenge_entries]
        state["agent_records"].extend(challenge_records)
        state["process_records"].extend(
            _persisted_process_record(
                entry,
                agent_id=agent["agent_id"],
                role_id=agent["role_id"],
                phase="challenge",
            )
            for agent, entry in zip(challenge_agents, challenge_entries, strict=True)
        )
        _atomic_json(run_dir / "process-records.json", state["process_records"])
        if challenge_records:
            apply_challenges(graph, challenge_records)
            add_new_findings(graph, challenge_records, phase="challenge")
        _atomic_json(run_dir / "challenge-records.json", challenge_records)
        assert_candidate_stable(root, package, candidate)
        state["event_sequence"] = _append_event(
            run_dir,
            state["event_sequence"],
            "fleet.challenge.completed",
            {"agents": len(challenge_records), "findings": len(graph)},
        )

        reproduction_agents = [
            item for item in agents if item["phase"] == "reproduction"
        ]
        reproduction_assignments = assign_findings(
            finding_ids(graph), [item["agent_id"] for item in reproduction_agents]
        )

        def run_reproduction(agent: Mapping[str, Any]) -> dict[str, Any]:
            assigned = reproduction_assignments[agent["agent_id"]]
            assigned_findings = [graph[item] for item in assigned]
            entry = process_adapter(
                attempt_dir=run_dir / "tasks" / agent["agent_id"] / "attempt-01-luna",
                cwd=root,
                prompt=reproduction_prompt(
                    package=package,
                    candidate=candidate,
                    verification=verification,
                    agent=agent,
                    findings=assigned_findings,
                ),
                schema=reproduction_schema(
                    candidate_revision=candidate["candidate_revision"], agent=agent
                ),
                route=LUNA_ROUTE,
                timeout_seconds=MAX_AGENT_TIMEOUT_SECONDS,
                max_output_bytes=package.limits["max_agent_output_bytes"],
                max_log_bytes=package.limits["max_agent_log_bytes"],
                codex_prefix=plan["codex_prefix"],
                codex_identity=plan["codex_identity"],
            )
            entry = _validate_process_entry(entry, route=LUNA_ROUTE)
            record = validate_reproduction_record(
                entry["output"],
                candidate_revision=candidate["candidate_revision"],
                agent=agent,
                finding_ids=assigned,
            )
            entry["output"] = record
            return entry

        state["model_calls"] += len(reproduction_agents)
        reproduction_entries = _run_parallel(
            agents=reproduction_agents, run_one=run_reproduction
        )
        reproduction_records = [item["output"] for item in reproduction_entries]
        state["agent_records"].extend(reproduction_records)
        state["process_records"].extend(
            _persisted_process_record(
                entry,
                agent_id=agent["agent_id"],
                role_id=agent["role_id"],
                phase="reproduction",
            )
            for agent, entry in zip(
                reproduction_agents, reproduction_entries, strict=True
            )
        )
        _atomic_json(run_dir / "process-records.json", state["process_records"])
        if reproduction_records:
            apply_reproductions(graph, reproduction_records)
            add_new_findings(graph, reproduction_records, phase="reproduction")
        _atomic_json(run_dir / "reproduction-records.json", reproduction_records)
        assert_candidate_stable(root, package, candidate)
        state["event_sequence"] = _append_event(
            run_dir,
            state["event_sequence"],
            "fleet.reproduction.completed",
            {"agents": len(reproduction_records), "findings": len(graph)},
        )

        findings = finalize_findings(graph)
        state["findings"] = findings
        _atomic_json(run_dir / "findings.json", findings)
        decision = decide_sol_escalation(
            package=package,
            findings=findings,
            records=state["agent_records"],
            verification_passed=True,
            candidate_stable=True,
        )
        state["aggregation"] = decision
        _atomic_json(run_dir / "aggregation.json", decision)

        if decision["requires_sol"]:
            assert_candidate_stable(root, package, candidate)
            state["model_calls"] += 1
            entry = process_adapter(
                attempt_dir=run_dir / "tasks" / "sol-arbiter" / "attempt-01-sol",
                cwd=root,
                prompt=arbiter_prompt(
                    package=package,
                    candidate=candidate,
                    verification=verification,
                    findings=findings,
                    decision=decision,
                ),
                schema=arbiter_schema(
                    candidate_revision=candidate["candidate_revision"]
                ),
                route=SOL_ARBITER_ROUTE,
                timeout_seconds=MAX_SOL_TIMEOUT_SECONDS,
                max_output_bytes=package.limits["max_agent_output_bytes"],
                max_log_bytes=package.limits["max_agent_log_bytes"],
                codex_prefix=plan["codex_prefix"],
                codex_identity=plan["codex_identity"],
            )
            entry = _validate_process_entry(entry, route=SOL_ARBITER_ROUTE)
            state["process_records"].append(
                _persisted_process_record(
                    entry,
                    agent_id="sol-arbiter",
                    role_id="fleet-sol-arbiter",
                    phase="arbitration",
                )
            )
            _atomic_json(run_dir / "process-records.json", state["process_records"])
            severity_by_id = {item["finding_id"]: item["severity"] for item in findings}
            arbitration = validate_arbiter_record(
                entry["output"],
                candidate_revision=candidate["candidate_revision"],
                valid_finding_ids=[item["finding_id"] for item in findings],
                severity_by_id=severity_by_id,
            )
            state["sol_arbitration"] = arbitration
            _atomic_json(run_dir / "sol-arbitration.json", arbitration)
            assert_candidate_stable(root, package, candidate)
            terminal = {
                "ship": "ship",
                "fix-first": "fix_first",
                "rethink": "rethink",
            }[arbitration["verdict"]]
        else:
            terminal = (
                "accepted_with_notes"
                if decision["preliminary_verdict"] == "accept-with-notes"
                else "accepted"
            )

        _atomic_json(run_dir / "agent-records.json", state["agent_records"])
        state["event_sequence"] = _append_event(
            run_dir,
            state["event_sequence"],
            "fleet.aggregation.completed",
            {
                "requires_sol": decision["requires_sol"],
                "terminal": terminal,
                "findings": len(findings),
            },
        )
        return _terminal_state(state=state, run_dir=run_dir, terminal=terminal)
    except FleetVerificationError as exc:
        state["verification_results"] = list(exc.results)
        if exc.results:
            _atomic_json(run_dir / "verification-results.json", exc.results)
        return _terminal_state(
            state=state,
            run_dir=run_dir,
            terminal="verification_failed",
            error=str(exc),
        )
    except (
        FleetCandidateError,
        FleetContractError,
        FleetEscalationError,
        FleetFindingError,
        FleetProcessError,
        FleetRecordError,
        FleetRuntimeError,
    ) as exc:
        return _terminal_state(
            state=state,
            run_dir=run_dir,
            terminal="attention_required",
            error=str(exc),
        )
    except KeyboardInterrupt:
        _terminal_state(
            state=state,
            run_dir=run_dir,
            terminal="attention_required",
            error="KeyboardInterrupt",
        )
        raise
    except Exception as exc:
        return _terminal_state(
            state=state,
            run_dir=run_dir,
            terminal="attention_required",
            error=f"{type(exc).__name__}: {exc}",
        )


def _load_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
            raise FleetRuntimeError(f"{path.name} is not strict UTF-8 JSON")
        return json.loads(raw.decode("utf-8", errors="strict"))
    except FleetRuntimeError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FleetRuntimeError(f"cannot read {path}: {exc}") from exc


def status_fleet(run_dir: str | Path) -> dict[str, Any]:
    try:
        from skill.fleet_integrity import FleetIntegrityError, validate_run_integrity
    except ModuleNotFoundError as exc:
        if exc.name != "skill":
            raise
        from fleet_integrity import FleetIntegrityError, validate_run_integrity

    try:
        integrity = validate_run_integrity(Path(run_dir))
    except FleetIntegrityError as exc:
        raise FleetRuntimeError(str(exc)) from exc
    return {
        "operation": "fleet-status",
        "model_calls": 0,
        "writes": [],
        "run_dir": str(integrity["root"]),
        "integrity": "match",
        "manifest_digest": integrity["manifest_digest"],
        "summary": integrity["summary"],
    }


__all__ = ["plan_fleet", "run_fleet", "status_fleet"]
