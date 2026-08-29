"""Deep read-only integrity validation for Agent Fleet v1 run evidence."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from skill.fleet_candidate import (
        FleetCandidateError,
        assert_candidate_stable,
        validate_candidate_package,
    )
    from skill.fleet_contract import (
        FleetPackage,
        canonical_digest,
        load_json_strict,
        validate_package,
    )
    from skill.fleet_escalation import decide_sol_escalation
    from skill.fleet_findings import (
        add_new_findings,
        apply_challenges,
        apply_reproductions,
        build_finding_graph,
        finalize_findings,
        finding_ids,
    )
    from skill.fleet_presets import build_schedule
    from skill.fleet_process import LUNA_ROUTE, SOL_ARBITER_ROUTE
    from skill.fleet_records import (
        validate_arbiter_record,
        validate_challenge_record,
        validate_discovery_record,
        validate_reproduction_record,
    )
except ModuleNotFoundError:
    from fleet_candidate import (
        FleetCandidateError,
        assert_candidate_stable,
        validate_candidate_package,
    )
    from fleet_contract import (
        FleetPackage,
        canonical_digest,
        load_json_strict,
        validate_package,
    )
    from fleet_escalation import decide_sol_escalation
    from fleet_findings import (
        add_new_findings,
        apply_challenges,
        apply_reproductions,
        build_finding_graph,
        finalize_findings,
        finding_ids,
    )
    from fleet_presets import build_schedule
    from fleet_process import LUNA_ROUTE, SOL_ARBITER_ROUTE
    from fleet_records import (
        validate_arbiter_record,
        validate_challenge_record,
        validate_discovery_record,
        validate_reproduction_record,
    )

RUNTIME_NAME = "agent-fleet-v1"
RUNTIME_VERSION = 1
SUCCESS_STATES = frozenset(
    {"accepted", "accepted_with_notes", "ship", "fix_first", "rethink"}
)
TERMINAL_STATES = SUCCESS_STATES | frozenset(
    {"verification_failed", "attention_required"}
)
MAX_EVIDENCE_FILE_BYTES = 32 * 1024 * 1024
MAX_EVENT_BYTES = 256 * 1024

SUMMARY_KEYS = frozenset(
    {
        "runtime",
        "runtime_version",
        "run_id",
        "run_dir",
        "state",
        "terminal",
        "created_at",
        "finished_at",
        "package_digest",
        "candidate_revision",
        "repository",
        "preset",
        "agent_count",
        "schedule_digest",
        "verification_results",
        "agent_records",
        "process_records",
        "findings",
        "aggregation",
        "sol_arbitration",
        "model_calls",
        "event_sequence",
        "error",
    }
)
PROCESS_RECORD_KEYS = frozenset(
    {
        "agent_id",
        "role_id",
        "phase",
        "status",
        "role",
        "model",
        "effort",
        "tier",
        "requested_sandbox",
        "observed_sandbox",
        "attempt_count",
        "retry",
        "upgrade",
        "nested_agents",
        "codex_identity",
        "output_digest",
    }
)
VERIFICATION_RESULT_KEYS = frozenset(
    {
        "id",
        "argv",
        "shell",
        "cwd",
        "exit_code",
        "timed_out",
        "duration_s",
        "stdout",
        "stderr",
        "passed",
    }
)
STREAM_KEYS = frozenset({"path", "bytes", "sha256"})


class FleetIntegrityError(RuntimeError):
    """Fleet evidence is malformed, stale, inconsistent, or tampered."""


def _closed(value: Any, *, where: str, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetIntegrityError(f"{where} must be an object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise FleetIntegrityError(
            f"{where} keys mismatch: missing={missing} unknown={unknown}"
        )
    return value


def _is_reparse(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _strict_regular_file(
    path: Path,
    *,
    root: Path,
    label: str,
    maximum: int = MAX_EVIDENCE_FILE_BYTES,
) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise FleetIntegrityError(f"cannot resolve {label}: {exc}") from exc
    if not resolved.is_relative_to(root):
        raise FleetIntegrityError(f"{label} escapes the fleet run directory")
    if path.is_symlink() or resolved.is_symlink() or _is_reparse(path) or _is_reparse(resolved):
        raise FleetIntegrityError(f"{label} cannot be a symlink or reparse point")
    if not resolved.is_file():
        raise FleetIntegrityError(f"{label} must be a regular file")
    if resolved.stat().st_size > maximum:
        raise FleetIntegrityError(f"{label} exceeds {maximum} bytes")
    return resolved


def _strict_json(
    root: Path,
    relative: str,
    *,
    required: bool = True,
    maximum: int = MAX_EVIDENCE_FILE_BYTES,
) -> Any:
    path = root / Path(*relative.split("/"))
    if not path.exists() and not path.is_symlink():
        if required:
            raise FleetIntegrityError(f"required evidence is missing: {relative}")
        return None
    regular = _strict_regular_file(path, root=root, label=relative, maximum=maximum)
    try:
        return load_json_strict(regular, maximum_bytes=maximum)
    except Exception as exc:
        raise FleetIntegrityError(f"cannot load {relative}: {exc}") from exc


def strict_run_manifest(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    stack = [run_dir]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise FleetIntegrityError(f"cannot enumerate fleet evidence: {exc}") from exc
        for path in children:
            relative = path.relative_to(run_dir).as_posix()
            if relative == "evidence-manifest.json":
                continue
            if path.is_symlink() or _is_reparse(path):
                raise FleetIntegrityError(
                    f"fleet evidence contains a link/reparse point: {relative}"
                )
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise FleetIntegrityError(f"cannot inspect {relative}: {exc}") from exc
            if path.is_dir():
                stack.append(path)
            elif path.is_file():
                payload = path.read_bytes()
                records.append(
                    {
                        "path": relative,
                        "bytes": metadata.st_size,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            else:
                raise FleetIntegrityError(
                    f"fleet evidence contains unsupported file type: {relative}"
                )
    records.sort(key=lambda item: item["path"].casefold())
    return records


def _validate_manifest(root: Path) -> tuple[dict[str, Any], str]:
    manifest = _closed(
        _strict_json(root, "evidence-manifest.json"),
        where="evidence manifest",
        keys=frozenset(
            {"manifest_version", "runtime", "run_id", "files", "manifest_digest"}
        ),
    )
    if manifest["manifest_version"] != 1 or manifest["runtime"] != RUNTIME_NAME:
        raise FleetIntegrityError("fleet evidence manifest identity is invalid")
    basis = dict(manifest)
    supplied = basis.pop("manifest_digest")
    if canonical_digest(basis) != supplied:
        raise FleetIntegrityError("fleet evidence manifest digest mismatch")
    observed = strict_run_manifest(root)
    if manifest["files"] != observed:
        raise FleetIntegrityError("fleet run evidence differs from the frozen manifest")
    return manifest, supplied


def _validate_events(root: Path, *, summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = _strict_regular_file(
        root / "events.jsonl",
        root=root,
        label="events.jsonl",
        maximum=16 * 1024 * 1024,
    )
    events: list[dict[str, Any]] = []
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
            raise FleetIntegrityError("events.jsonl is not strict UTF-8 JSONL")
        lines = raw.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise FleetIntegrityError("events.jsonl is not UTF-8") from exc
    for index, line in enumerate(lines, start=1):
        encoded = (line + "\n").encode("utf-8")
        if len(encoded) > MAX_EVENT_BYTES:
            raise FleetIntegrityError(f"fleet event {index} exceeds {MAX_EVENT_BYTES} bytes")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FleetIntegrityError(f"fleet event {index} is invalid JSON: {exc}") from exc
        event = _closed(
            event,
            where=f"fleet event[{index}]",
            keys=frozenset({"sequence", "timestamp", "type", "payload"}),
        )
        if event["sequence"] != index:
            raise FleetIntegrityError("fleet event sequence is not contiguous")
        if not isinstance(event["timestamp"], str) or not event["timestamp"]:
            raise FleetIntegrityError("fleet event timestamp is invalid")
        if not isinstance(event["type"], str) or not event["type"]:
            raise FleetIntegrityError("fleet event type is invalid")
        if not isinstance(event["payload"], dict):
            raise FleetIntegrityError("fleet event payload must be an object")
        events.append(event)
    if len(events) != summary["event_sequence"]:
        raise FleetIntegrityError("fleet event count disagrees with summary")
    if not events:
        raise FleetIntegrityError("fleet journal is empty")
    final = events[-1]
    expected_type = (
        "fleet.run.attention_required"
        if summary["state"] in {"verification_failed", "attention_required"}
        else "fleet.run.completed"
    )
    expected_payload = {
        "run_id": summary["run_id"],
        "state": summary["state"],
        "error": summary["error"],
    }
    if final["type"] != expected_type or final["payload"] != expected_payload:
        raise FleetIntegrityError("fleet terminal event disagrees with summary")
    return events


def _expected_validation_argv(argv: Sequence[str]) -> list[str]:
    first = argv[0].casefold()
    if first in {"python", "python3", "py"}:
        return [sys.executable, *argv[1:]]
    if first == "pytest":
        return [sys.executable, "-m", "pytest", *argv[1:]]
    raise FleetIntegrityError(f"unsupported validation executable: {argv[0]}")


def _validate_stream(
    root: Path,
    value: Any,
    *,
    command_id: str,
    stream: str,
) -> None:
    record = _closed(
        value,
        where=f"verification {command_id} {stream}",
        keys=STREAM_KEYS,
    )
    expected = root / "verification" / f"{command_id}.{stream}.txt"
    path = _strict_regular_file(
        expected,
        root=root,
        label=f"verification {command_id} {stream}",
        maximum=8 * 1024 * 1024,
    )
    if record["path"] != str(path):
        raise FleetIntegrityError(f"verification {command_id} {stream} path mismatch")
    payload = path.read_bytes()
    if record["bytes"] != len(payload):
        raise FleetIntegrityError(f"verification {command_id} {stream} byte mismatch")
    if record["sha256"] != hashlib.sha256(payload).hexdigest():
        raise FleetIntegrityError(f"verification {command_id} {stream} digest mismatch")


def _validate_verification(
    root: Path,
    *,
    package: FleetPackage,
    summary: Mapping[str, Any],
    required_success: bool,
) -> list[dict[str, Any]]:
    raw = _strict_json(
        root,
        "verification-results.json",
        required=bool(summary["verification_results"]),
    )
    if raw is None:
        values: list[dict[str, Any]] = []
    else:
        if not isinstance(raw, list):
            raise FleetIntegrityError("verification-results.json must be an array")
        values = raw
    if values != summary["verification_results"]:
        raise FleetIntegrityError("verification results disagree with summary")
    declared = package.verification["commands"]
    if len(values) > len(declared):
        raise FleetIntegrityError("verification results exceed declared commands")
    normalized: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        result = _closed(
            value,
            where=f"verification result[{index}]",
            keys=VERIFICATION_RESULT_KEYS,
        )
        command = declared[index]
        if result["id"] != command["id"]:
            raise FleetIntegrityError("verification results are not the declared prefix")
        if result["argv"] != _expected_validation_argv(command["argv"]):
            raise FleetIntegrityError(f"verification {command['id']} argv mismatch")
        if result["shell"] is not False or result["cwd"] != summary["repository"]:
            raise FleetIntegrityError(f"verification {command['id']} execution boundary mismatch")
        exit_code = result["exit_code"]
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise FleetIntegrityError(f"verification {command['id']} exit_code is invalid")
        if result["timed_out"] is not False:
            raise FleetIntegrityError(f"verification {command['id']} timed_out must be false")
        if result["passed"] != (exit_code == 0):
            raise FleetIntegrityError(f"verification {command['id']} passed mismatch")
        if isinstance(result["duration_s"], bool) or not isinstance(
            result["duration_s"], (int, float)
        ) or result["duration_s"] < 0:
            raise FleetIntegrityError(f"verification {command['id']} duration is invalid")
        _validate_stream(root, result["stdout"], command_id=command["id"], stream="stdout")
        _validate_stream(root, result["stderr"], command_id=command["id"], stream="stderr")
        normalized.append(result)
    if required_success:
        required = set(package.verification["required_ids"])
        passed = {item["id"] for item in normalized if item["passed"]}
        if not required <= passed:
            raise FleetIntegrityError(
                f"required verification evidence is incomplete: {sorted(required - passed)}"
            )
        if any(not item["passed"] for item in normalized):
            raise FleetIntegrityError("successful fleet state contains failed verification")
    return normalized


def _agent_maps(schedule: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    agents = schedule["agents"]
    if not isinstance(agents, list):
        raise FleetIntegrityError("schedule agents must be an array")
    by_id: dict[str, Any] = {}
    by_phase: dict[str, list[dict[str, Any]]] = {
        "discovery": [],
        "challenge": [],
        "reproduction": [],
    }
    for agent in agents:
        agent_id = agent.get("agent_id") if isinstance(agent, dict) else None
        phase = agent.get("phase") if isinstance(agent, dict) else None
        if not isinstance(agent_id, str) or agent_id in by_id:
            raise FleetIntegrityError("schedule agent ids are invalid or duplicated")
        if phase not in by_phase:
            raise FleetIntegrityError("schedule agent phase is invalid")
        by_id[agent_id] = agent
        by_phase[phase].append(agent)
    return by_id, by_phase


def _validate_process_record(
    value: Any,
    *,
    agent_id: str,
    role_id: str,
    phase: str,
    route: Any,
    output: Mapping[str, Any],
) -> dict[str, Any]:
    record = _closed(value, where=f"process record {agent_id}", keys=PROCESS_RECORD_KEYS)
    expected = {
        "agent_id": agent_id,
        "role_id": role_id,
        "phase": phase,
        "status": "succeeded",
        "role": route.role,
        "model": route.model,
        "effort": route.effort,
        "tier": route.tier,
        "requested_sandbox": route.sandbox,
        "attempt_count": 1,
        "retry": 0,
        "upgrade": None,
        "nested_agents": 0,
        "output_digest": canonical_digest(output),
    }
    for key, expected_value in expected.items():
        if record[key] != expected_value:
            raise FleetIntegrityError(
                f"process record {agent_id} {key} mismatch: "
                f"{record[key]!r} != {expected_value!r}"
            )
    if not isinstance(record["observed_sandbox"], str) or not record["observed_sandbox"]:
        raise FleetIntegrityError(f"process record {agent_id} observed_sandbox is invalid")
    if not isinstance(record["codex_identity"], dict):
        raise FleetIntegrityError(f"process record {agent_id} codex_identity is invalid")
    return record


def _validate_success_semantics(
    root: Path,
    *,
    package: FleetPackage,
    candidate: Mapping[str, Any],
    schedule: Mapping[str, Any],
    summary: Mapping[str, Any],
    verification: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_id, by_phase = _agent_maps(schedule)
    discovery_raw = _strict_json(root, "discovery-records.json")
    challenge_raw = _strict_json(root, "challenge-records.json")
    reproduction_raw = _strict_json(root, "reproduction-records.json")
    for label, value in (
        ("discovery records", discovery_raw),
        ("challenge records", challenge_raw),
        ("reproduction records", reproduction_raw),
    ):
        if not isinstance(value, list):
            raise FleetIntegrityError(f"{label} must be an array")
    if len(discovery_raw) != len(by_phase["discovery"]):
        raise FleetIntegrityError("discovery record count disagrees with schedule")
    if len(challenge_raw) != len(by_phase["challenge"]):
        raise FleetIntegrityError("challenge record count disagrees with schedule")
    if len(reproduction_raw) != len(by_phase["reproduction"]):
        raise FleetIntegrityError("reproduction record count disagrees with schedule")

    discovery = [
        validate_discovery_record(
            record,
            candidate_revision=candidate["candidate_revision"],
            agent=agent,
        )
        for agent, record in zip(by_phase["discovery"], discovery_raw, strict=True)
    ]
    graph = build_finding_graph(discovery)
    challenge_ids = finding_ids(graph)
    challenge = [
        validate_challenge_record(
            record,
            candidate_revision=candidate["candidate_revision"],
            agent=agent,
            finding_ids=challenge_ids,
        )
        for agent, record in zip(by_phase["challenge"], challenge_raw, strict=True)
    ]
    if challenge:
        apply_challenges(graph, challenge)
        add_new_findings(graph, challenge, phase="challenge")
    reproduction_ids = finding_ids(graph)
    reproduction = [
        validate_reproduction_record(
            record,
            candidate_revision=candidate["candidate_revision"],
            agent=agent,
            finding_ids=reproduction_ids,
        )
        for agent, record in zip(
            by_phase["reproduction"], reproduction_raw, strict=True
        )
    ]
    if reproduction:
        apply_reproductions(graph, reproduction)
        add_new_findings(graph, reproduction, phase="reproduction")
    agent_records = [*discovery, *challenge, *reproduction]
    recorded_agent_records = _strict_json(root, "agent-records.json")
    if recorded_agent_records != agent_records or summary["agent_records"] != agent_records:
        raise FleetIntegrityError("aggregate agent records do not match phase records")

    findings = finalize_findings(graph)
    recorded_findings = _strict_json(root, "findings.json")
    if recorded_findings != findings or summary["findings"] != findings:
        raise FleetIntegrityError("finding graph reconstruction mismatch")

    decision = decide_sol_escalation(
        package=package,
        findings=findings,
        records=agent_records,
        verification_passed=True,
        candidate_stable=True,
    )
    recorded_decision = _strict_json(root, "aggregation.json")
    if recorded_decision != decision or summary["aggregation"] != decision:
        raise FleetIntegrityError("host escalation decision reconstruction mismatch")

    process_records = _strict_json(root, "process-records.json")
    if not isinstance(process_records, list):
        raise FleetIntegrityError("process-records.json must be an array")
    record_by_agent = {item["agent_id"]: item for item in agent_records}
    expected_process_count = len(agent_records) + (1 if decision["requires_sol"] else 0)
    if len(process_records) != expected_process_count:
        raise FleetIntegrityError("process record count disagrees with schedule/arbitration")
    validated_process: list[dict[str, Any]] = []
    for agent in schedule["agents"]:
        output = record_by_agent.get(agent["agent_id"])
        if output is None:
            raise FleetIntegrityError(f"missing agent output for {agent['agent_id']}")
        matches = [item for item in process_records if item.get("agent_id") == agent["agent_id"]]
        if len(matches) != 1:
            raise FleetIntegrityError(f"process identity count mismatch for {agent['agent_id']}")
        validated_process.append(
            _validate_process_record(
                matches[0],
                agent_id=agent["agent_id"],
                role_id=agent["role_id"],
                phase=agent["phase"],
                route=LUNA_ROUTE,
                output=output,
            )
        )

    arbitration = None
    if decision["requires_sol"]:
        raw_arbiter = _strict_json(root, "sol-arbitration.json")
        severity = {item["finding_id"]: item["severity"] for item in findings}
        arbitration = validate_arbiter_record(
            raw_arbiter,
            candidate_revision=candidate["candidate_revision"],
            valid_finding_ids=[item["finding_id"] for item in findings],
            severity_by_id=severity,
        )
        matches = [item for item in process_records if item.get("agent_id") == "sol-arbiter"]
        if len(matches) != 1:
            raise FleetIntegrityError("Sol arbiter process identity is missing or duplicated")
        validated_process.append(
            _validate_process_record(
                matches[0],
                agent_id="sol-arbiter",
                role_id="fleet-sol-arbiter",
                phase="arbitration",
                route=SOL_ARBITER_ROUTE,
                output=arbitration,
            )
        )
        terminal = {
            "ship": "ship",
            "fix-first": "fix_first",
            "rethink": "rethink",
        }[arbitration["verdict"]]
    else:
        if (root / "sol-arbitration.json").exists():
            raise FleetIntegrityError("clean fleet unexpectedly contains Sol arbitration")
        terminal = (
            "accepted_with_notes"
            if decision["preliminary_verdict"] == "accept-with-notes"
            else "accepted"
        )
    if summary["state"] != terminal:
        raise FleetIntegrityError("terminal state disagrees with reconstructed decision")
    if summary["sol_arbitration"] != arbitration:
        raise FleetIntegrityError("summary Sol arbitration mismatch")
    if summary["process_records"] != validated_process:
        raise FleetIntegrityError("summary process records mismatch")
    if summary["model_calls"] != len(validated_process):
        raise FleetIntegrityError("summary model call count mismatch")
    if summary["verification_results"] != list(verification):
        raise FleetIntegrityError("summary verification results mismatch")
    return {
        "agent_records": agent_records,
        "process_records": validated_process,
        "findings": findings,
        "aggregation": decision,
        "sol_arbitration": arbitration,
    }


def validate_run_integrity(root: Path) -> dict[str, Any]:
    try:
        run_dir = root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise FleetIntegrityError(f"cannot resolve fleet run directory: {exc}") from exc
    if run_dir.is_symlink() or _is_reparse(run_dir) or not run_dir.is_dir():
        raise FleetIntegrityError("fleet run directory must be a regular directory")
    manifest, manifest_digest = _validate_manifest(run_dir)
    summary = _closed(
        _strict_json(run_dir, "summary.json"),
        where="fleet summary",
        keys=SUMMARY_KEYS,
    )
    if summary["runtime"] != RUNTIME_NAME or summary["runtime_version"] != RUNTIME_VERSION:
        raise FleetIntegrityError("fleet runtime identity is invalid")
    if summary["run_id"] != manifest["run_id"]:
        raise FleetIntegrityError("fleet run id disagrees with manifest")
    if summary["run_dir"] != str(run_dir):
        raise FleetIntegrityError("fleet run directory identity mismatch")
    if summary["state"] not in TERMINAL_STATES or summary["terminal"] is not True:
        raise FleetIntegrityError("fleet summary is not terminal")
    if not isinstance(summary["finished_at"], str) or not summary["finished_at"]:
        raise FleetIntegrityError("fleet finished_at is invalid")
    if isinstance(summary["model_calls"], bool) or not isinstance(summary["model_calls"], int) or summary["model_calls"] < 0:
        raise FleetIntegrityError("fleet model_calls is invalid")
    if isinstance(summary["event_sequence"], bool) or not isinstance(summary["event_sequence"], int) or summary["event_sequence"] < 1:
        raise FleetIntegrityError("fleet event_sequence is invalid")
    _validate_events(run_dir, summary=summary)

    package = validate_package(_strict_json(run_dir, "fleet-package.resolved.json"))
    if package.digest != summary["package_digest"]:
        raise FleetIntegrityError("fleet package digest mismatch")
    if package.preset != summary["preset"] or package.agent_count != summary["agent_count"]:
        raise FleetIntegrityError("fleet package routing fields disagree with summary")

    candidate = _strict_json(run_dir, "candidate-package.json")
    try:
        validate_candidate_package(candidate)
    except FleetCandidateError as exc:
        raise FleetIntegrityError(str(exc)) from exc
    if candidate["candidate_revision"] != summary["candidate_revision"]:
        raise FleetIntegrityError("fleet candidate revision mismatch")
    if candidate["repository_root"] != summary["repository"]:
        raise FleetIntegrityError("fleet candidate repository path mismatch")

    schedule = _strict_json(run_dir, "schedule.json")
    expected_schedule = build_schedule(package)
    if schedule != expected_schedule or schedule["schedule_digest"] != summary["schedule_digest"]:
        raise FleetIntegrityError("fleet schedule does not match the trusted registry")

    verification = _validate_verification(
        run_dir,
        package=package,
        summary=summary,
        required_success=summary["state"] in SUCCESS_STATES,
    )
    semantic = None
    if summary["state"] in SUCCESS_STATES:
        try:
            assert_candidate_stable(summary["repository"], package, candidate)
        except FleetCandidateError as exc:
            raise FleetIntegrityError(str(exc)) from exc
        semantic = _validate_success_semantics(
            run_dir,
            package=package,
            candidate=candidate,
            schedule=schedule,
            summary=summary,
            verification=verification,
        )
    else:
        if summary["state"] == "verification_failed" and summary["model_calls"] != 0:
            raise FleetIntegrityError("verification_failed run unexpectedly used a model")
        if summary["state"] == "verification_failed" and any(
            item["passed"] for item in verification[-1:]
        ):
            raise FleetIntegrityError("verification_failed run lacks failing evidence")
    return {
        "root": run_dir,
        "manifest_digest": manifest_digest,
        "summary": summary,
        "package": package,
        "candidate": candidate,
        "schedule": schedule,
        "verification": verification,
        "semantic": semantic,
    }


__all__ = ["FleetIntegrityError", "strict_run_manifest", "validate_run_integrity"]
