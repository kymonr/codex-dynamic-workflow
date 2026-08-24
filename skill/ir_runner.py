#!/usr/bin/env python3
"""CLI adapter for the trusted Workflow IR v3 control-flow runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

try:  # Package import from repository root.
    from skill import runner as legacy
    from skill.runtime.artifacts import ArtifactStore
    from skill.runtime.control_flow import (
        ControlFlowError,
        TrustedControlFlowScheduler,
    )
    from skill.runtime.deadline import DeadlineClock
    from skill.runtime.limits import ArtifactLimitError, RuntimeLimits
    from skill.runtime.workflow_ir import (
        WorkflowIRValidationError,
        validate_workflow_ir,
    )
except ModuleNotFoundError:  # Executed from the installed skill directory.
    import runner as legacy
    from runtime.artifacts import ArtifactStore
    from runtime.control_flow import ControlFlowError, TrustedControlFlowScheduler
    from runtime.deadline import DeadlineClock
    from runtime.limits import ArtifactLimitError, RuntimeLimits
    from runtime.workflow_ir import WorkflowIRValidationError, validate_workflow_ir


def _load_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlFlowError(f"cannot read Workflow IR {path}: {exc}") from exc


def _add_safety_args(parser: argparse.ArgumentParser, *, include_spec: bool) -> None:
    if include_spec:
        parser.add_argument("--spec", required=True, help="Workflow IR v3 JSON file")
    parser.add_argument(
        "--allowed-root",
        action="append",
        required=True,
        help="IR workdir must be inside this root; repeatable",
    )
    parser.add_argument(
        "--allow-sensitive-path",
        action="append",
        default=[],
        help="exact workdir-relative false-positive exception; repeatable",
    )
    parser.add_argument(
        "--ack-external-model-export",
        action="store_true",
        help="root agent already evaluated this explicit CLI export boundary",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "trusted Dynamic Workflow IR v3 read-only runtime with Bounded Loop "
            "v1 and an optional absolute whole-workflow deadline"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run-ir",
        help=(
            "execute trusted agent/map/verify/bounded-loop/reduce/conditional/"
            "human_gate IR with an optional absolute workflow deadline"
        ),
    )
    _add_safety_args(run, include_spec=True)
    run.add_argument("--run-dir", default=None, help="test/custom-root run directory")

    resume = subparsers.add_parser(
        "resume-ir",
        help=(
            "resume a trusted Workflow IR run from checkpoint without resetting "
            "its absolute workflow deadline"
        ),
    )
    _add_safety_args(resume, include_spec=False)
    resume.add_argument("--run-dir", required=True, help="existing IR run directory")
    return parser


def _normalize_runtime_ir(
    ir: dict[str, Any],
    *,
    allowed_roots: list[str],
    allowed_sensitive_paths: list[str],
    codex_home: Path,
) -> tuple[dict[str, Any], RuntimeLimits]:
    normalized_workdir = legacy._check_workdir_safe(
        ir["workdir"],
        allowed_roots,
        codex_home=codex_home,
        allowed_sensitive_paths=allowed_sensitive_paths,
    )
    ir["workdir"] = normalized_workdir
    try:
        limits = RuntimeLimits.from_mapping(ir.get("limits"))
    except ValueError as exc:
        raise ControlFlowError(f"invalid Workflow IR limits: {exc}") from exc
    # Persist the fully resolved values so resume cannot silently inherit a
    # different environment budget.
    ir["limits"] = limits.to_dict()
    return ir, limits


def _execution_matches(left: Any, right: Any) -> bool:
    """Compare JSON values without treating booleans as integers."""

    try:
        return json.dumps(
            left,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ) == json.dumps(
            right,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return False


def _normalize_declared_ir(
    raw: Any,
    *,
    allowed_roots: list[str],
    allowed_sensitive_paths: list[str],
    codex_home: Path,
) -> tuple[dict[str, Any], RuntimeLimits]:
    """Validate and normalize a user-declared Workflow IR."""

    return _normalize_runtime_ir(
        validate_workflow_ir(raw),
        allowed_roots=allowed_roots,
        allowed_sensitive_paths=allowed_sensitive_paths,
        codex_home=codex_home,
    )


def _normalize_resolved_ir_for_resume(
    raw: Any,
    *,
    allowed_roots: list[str],
    allowed_sensitive_paths: list[str],
    codex_home: Path,
) -> tuple[dict[str, Any], RuntimeLimits]:
    """Validate a scheduler-resolved IR and recompute its runtime metadata."""

    if not isinstance(raw, dict):
        raise WorkflowIRValidationError(
            "resolved Workflow IR must be an object"
        )
    if "execution" not in raw:
        raise WorkflowIRValidationError(
            "resolved Workflow IR must contain top-level execution"
        )

    persisted_execution = raw["execution"]
    declared = dict(raw)
    declared.pop("execution")
    normalized = validate_workflow_ir(declared)
    if not _execution_matches(persisted_execution, normalized["execution"]):
        raise WorkflowIRValidationError(
            "resolved Workflow IR execution does not match recomputed execution"
        )
    return _normalize_runtime_ir(
        normalized,
        allowed_roots=allowed_roots,
        allowed_sensitive_paths=allowed_sensitive_paths,
        codex_home=codex_home,
    )


async def _run(
    ir: dict[str, Any],
    run_dir: Path,
    *,
    resume: bool,
    codex_prefix: list[str],
    role_configs: dict[str, dict[str, Any]],
    preflight: dict[str, Any],
    limits: RuntimeLimits,
    clock: DeadlineClock | None = None,
) -> dict[str, Any]:
    adapter_store = ArtifactStore(run_dir, limits)
    cancel_path = run_dir / "CANCEL"

    async def execute_agent(
        task: dict[str, Any],
        results: dict[str, Any],
        prior_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        legacy_task = dict(task)
        runtime = legacy_task.pop("_runtime", None)
        soft_timeout = ir["budgets"]["soft_timeout_seconds"]
        hard_timeout = ir["budgets"]["hard_timeout_seconds"]
        if runtime is not None:
            if (
                not isinstance(runtime, dict)
                or set(runtime)
                != {"soft_timeout_seconds", "hard_timeout_seconds"}
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value <= 0
                    for value in runtime.values()
                )
            ):
                raise ControlFlowError("invalid private agent runtime metadata")
            soft_timeout = runtime["soft_timeout_seconds"]
            hard_timeout = runtime["hard_timeout_seconds"]
        return await legacy._execute_task(
            legacy_task,
            run_dir=run_dir,
            workdir=ir["workdir"],
            results=results,
            role_configs=role_configs,
            codex_prefix=codex_prefix,
            preflight=preflight,
            cancel_path=cancel_path,
            soft_timeout=soft_timeout,
            hard_timeout=hard_timeout,
            artifact_store=adapter_store,
            limits=limits,
            prior_entry=prior_entry,
        )

    scheduler = TrustedControlFlowScheduler(
        ir,
        run_dir,
        execute_agent=execute_agent,
        limits=limits,
        clock=clock,
    )
    return await scheduler.run(resume=resume)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.ack_external_model_export:
        print(
            "无法开跑: 缺少 --ack-external-model-export；仅在明确选择 CLI runtime 后添加",
            file=sys.stderr,
        )
        return 1

    try:
        resume = args.command == "resume-ir"
        run_dir = Path(args.run_dir).expanduser().resolve() if resume else None
        raw = _load_json(
            run_dir / "workflow-ir.resolved.json" if resume else args.spec
        )
        codex_home = legacy.resolve_codex_home()
        normalize = (
            _normalize_resolved_ir_for_resume
            if resume
            else _normalize_declared_ir
        )
        ir, limits = normalize(
            raw,
            allowed_roots=args.allowed_root,
            allowed_sensitive_paths=args.allow_sensitive_path,
            codex_home=codex_home,
        )
        role_configs = legacy.resolve_role_configs(codex_home)
        codex_prefix, codex_identity = legacy.resolve_codex_prefix()
        preflight = {
            "ack_external_model_export": True,
            "allowed_roots": [
                str(Path(root).expanduser().resolve()) for root in args.allowed_root
            ],
            "allowed_sensitive_paths": list(args.allow_sensitive_path),
            "codex_home": str(codex_home),
            **codex_identity,
        }
        runs_root = legacy._runs_root()
        legacy._prepare_run_root(runs_root, ir, codex_home)
        if resume:
            assert run_dir is not None
            if not run_dir.is_relative_to(runs_root):
                raise ControlFlowError(
                    f"resume run directory must be below {runs_root}"
                )
        else:
            run_dir = legacy._select_run_dir(
                runs_root, ir["name"], args.run_dir
            )
        summary = asyncio.run(
            _run(
                ir,
                run_dir,
                resume=resume,
                codex_prefix=codex_prefix,
                role_configs=role_configs,
                preflight=preflight,
                limits=limits,
            )
        )
    except (
        ControlFlowError,
        WorkflowIRValidationError,
        ArtifactLimitError,
        legacy.WorkflowError,
        ValueError,
    ) as exc:
        print(f"Workflow IR runtime failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "已中断；运行目录会保留，可检查 checkpoint.json 后显式 resume-ir",
            file=sys.stderr,
        )
        return 2

    if summary.get("paused"):
        waiting = [
            node["id"]
            for node in summary.get("nodes", [])
            if node.get("status") == "waiting"
        ]
        print(
            "== 已暂停: human gate waiting; "
            f"nodes={','.join(waiting)}; "
            f"详情 {Path(summary['run_dir']) / 'summary.json'} =="
        )
        return 3

    print(
        f"== 完成: {summary['succeeded_count']}/{summary['total']} nodes succeeded; "
        f"skipped={summary.get('skipped_count', 0)}; "
        f"agents={summary['claimed_agent_count']}/{summary['max_agents']}; "
        f"详情 {Path(summary['run_dir']) / 'summary.json'} =="
    )
    return 0 if summary["all_succeeded"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
