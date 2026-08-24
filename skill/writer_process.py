"""Native Codex process adapter for one writer or one reviewer attempt."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from skill import runner as legacy
except ModuleNotFoundError:
    import runner as legacy

WRITER_MODEL = "gpt-5.6-luna"
WRITER_EFFORT = "max"
WRITER_TIER = "fast"
REVIEWER_MODEL = "gpt-5.6-sol"
REVIEWER_EFFORT = "xhigh"
MAX_PROMPT_BYTES = 512 * 1024
MAX_SCHEMA_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_LOG_BYTES = 8 * 1024 * 1024


class WriterProcessError(RuntimeError):
    """A native writer/reviewer process cannot be trusted or completed."""


@dataclass(frozen=True)
class ProcessRoute:
    role: str
    model: str
    effort: str
    tier: str | None
    sandbox: str


WRITER_ROUTE = ProcessRoute(
    "luna", WRITER_MODEL, WRITER_EFFORT, WRITER_TIER, "workspace-write"
)
REVIEWER_ROUTE = ProcessRoute(
    "dynamic_workflow_sol_reviewer",
    REVIEWER_MODEL,
    REVIEWER_EFFORT,
    None,
    "read-only",
)


def writer_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {
                "type": "string",
                "enum": ["completed", "needs_escalation"],
            },
            "summary": {"type": "string"},
            "reported_effects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string"},
                        "action": {
                            "type": "string",
                            "enum": ["create", "modify"],
                        },
                    },
                    "required": ["path", "action"],
                },
            },
            "verification_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "limitations": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "status",
            "summary",
            "reported_effects",
            "verification_notes",
            "limitations",
        ],
    }


def _write_utf8(path: Path, text: str, *, maximum: int, label: str) -> None:
    payload = text.encode("utf-8", errors="strict")
    if len(payload) > maximum:
        raise WriterProcessError(f"{label} exceeds {maximum} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _build_command(
    *,
    codex_prefix: Sequence[str],
    cwd: Path,
    route: ProcessRoute,
    schema_path: Path,
    output_path: Path,
) -> list[str]:
    command = list(codex_prefix) + [
        "exec",
        "-s",
        route.sandbox,
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--color",
        "never",
        "-C",
        str(cwd),
        "-m",
        route.model,
        "-c",
        f"model_reasoning_effort={route.effort}",
        "-c",
        "approval_policy=never",
        "-c",
        "features.multi_agent=false",
    ]
    if os.name == "nt":
        command += ["-c", "windows.sandbox=elevated"]
    if route.sandbox == "workspace-write":
        command += [
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            "sandbox_workspace_write.writable_roots=[]",
        ]
    if route.tier:
        command += ["-c", f"service_tier={route.tier}"]
    command += [
        "--output-schema",
        str(schema_path),
        "-o",
        str(output_path),
        "--",
        "-",
    ]
    return command


def _kill_tree(process: subprocess.Popen[bytes]) -> str | None:
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill.exe", "/F", "/T", "/PID", str(process.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
                env=legacy._sanitized_child_env(),
            )
            if completed.returncode not in {0, 128} and process.poll() is None:
                return completed.stderr.decode("utf-8", errors="replace")[-1000:]
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"process tree cleanup failed: {exc}"
    return None


def probe_codex_capabilities(codex_prefix: Sequence[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [*codex_prefix, "exec", "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
            env=legacy._sanitized_child_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WriterProcessError(
            f"cannot probe Codex exec capabilities: {exc}"
        ) from exc
    help_text = (result.stdout + b"\n" + result.stderr).decode(
        "utf-8", errors="replace"
    )
    required = [
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--output-schema",
        "--skip-git-repo-check",
    ]
    missing = [flag for flag in required if flag not in help_text]
    if result.returncode != 0 or missing:
        raise WriterProcessError(
            "Codex exec capability probe failed: "
            f"exit={result.returncode} missing={missing}"
        )
    return {
        "exit_code": result.returncode,
        "required_flags": required,
        "missing": [],
    }


def run_codex_attempt(
    *,
    attempt_dir: Path,
    cwd: Path,
    prompt: str,
    schema: Mapping[str, Any],
    route: ProcessRoute,
    timeout_seconds: int,
    codex_prefix: Sequence[str] | None = None,
    codex_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run exactly one native Codex attempt and retain host evidence."""

    attempt_dir.mkdir(parents=True, exist_ok=False)
    cwd = cwd.resolve(strict=True)
    if codex_prefix is None:
        resolved_prefix, resolved_identity = legacy.resolve_codex_prefix()
        codex_prefix = resolved_prefix
        codex_identity = resolved_identity
    else:
        codex_prefix = list(codex_prefix)
        codex_identity = dict(codex_identity or {})
    schema_path = attempt_dir / "schema.json"
    prompt_path = attempt_dir / "prompt.txt"
    output_path = attempt_dir / "out.json"
    log_path = attempt_dir / "agent.log"
    command_path = attempt_dir / "cmd.json"

    _write_utf8(
        prompt_path, prompt, maximum=MAX_PROMPT_BYTES, label="prompt"
    )
    _write_utf8(
        schema_path,
        json.dumps(schema, ensure_ascii=False, indent=2),
        maximum=MAX_SCHEMA_BYTES,
        label="output schema",
    )
    command = _build_command(
        codex_prefix=codex_prefix,
        cwd=cwd,
        route=route,
        schema_path=schema_path,
        output_path=output_path,
    )
    _write_utf8(
        command_path,
        json.dumps(command, ensure_ascii=False, indent=2),
        maximum=MAX_SCHEMA_BYTES,
        label="command record",
    )

    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        start_new_session = True
    started = time.monotonic()
    with log_path.open("wb") as log_handle:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=legacy._sanitized_child_env(),
                shell=False,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
        except OSError as exc:
            raise WriterProcessError(
                f"cannot start native Codex process: {exc}"
            ) from exc
        try:
            assert process.stdin is not None
            process.stdin.write(prompt.encode("utf-8"))
            process.stdin.close()
            deadline = time.monotonic() + timeout_seconds
            while process.poll() is None:
                if log_path.stat().st_size > MAX_LOG_BYTES:
                    cleanup = _kill_tree(process)
                    raise WriterProcessError(
                        f"Codex log exceeded {MAX_LOG_BYTES} bytes; "
                        f"cleanup={cleanup}"
                    )
                if (
                    output_path.exists()
                    and output_path.stat().st_size > MAX_OUTPUT_BYTES
                ):
                    cleanup = _kill_tree(process)
                    raise WriterProcessError(
                        f"Codex output exceeded {MAX_OUTPUT_BYTES} bytes; "
                        f"cleanup={cleanup}"
                    )
                if time.monotonic() >= deadline:
                    cleanup = _kill_tree(process)
                    raise WriterProcessError(
                        f"Codex attempt timed out after {timeout_seconds}s; "
                        f"cleanup={cleanup}"
                    )
                time.sleep(0.1)
        except BaseException:
            if process.poll() is None:
                _kill_tree(process)
            raise
    duration = round(time.monotonic() - started, 3)
    exit_code = process.returncode
    if exit_code != 0:
        tail = log_path.read_bytes()[-4000:].decode(
            "utf-8", errors="replace"
        )
        raise WriterProcessError(f"Codex exec exited {exit_code}: {tail}")
    try:
        raw = output_path.read_bytes()
    except OSError as exc:
        raise WriterProcessError(f"Codex output file is missing: {exc}") from exc
    if len(raw) > MAX_OUTPUT_BYTES:
        raise WriterProcessError("Codex output exceeds the result limit")
    try:
        output = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WriterProcessError(
            f"Codex output is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(output, dict):
        raise WriterProcessError("Codex structured output must be an object")
    return {
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
        "exit_code": exit_code,
        "duration_s": duration,
        "pid": process.pid,
        "command": command,
        "codex_identity": dict(codex_identity or {}),
        "output": output,
        "paths": {
            "attempt_dir": str(attempt_dir),
            "prompt": str(prompt_path),
            "schema": str(schema_path),
            "command": str(command_path),
            "log": str(log_path),
            "output": str(output_path),
        },
        "bytes": {
            "prompt": prompt_path.stat().st_size,
            "schema": schema_path.stat().st_size,
            "log": log_path.stat().st_size,
            "output": output_path.stat().st_size,
        },
    }
