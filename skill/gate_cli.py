#!/usr/bin/env python3
"""Explicit condition preview and human-gate record commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:  # Package import from repository root.
    from skill.platform_paths import configure_utf8_stdio
    from skill import runner as legacy
    from skill.runtime.condition import (
        ConditionValidationError,
        evaluate_condition,
        validate_condition,
    )
    from skill.runtime.human_gate import HumanGateError, HumanGateStore
    from skill.runtime.limits import ArtifactLimitError, RuntimeLimits
    from skill.runtime.path_safety import assert_safe_run_tree
except ModuleNotFoundError:  # Installed skill directory.
    from platform_paths import configure_utf8_stdio
    import runner as legacy
    from runtime.condition import (
        ConditionValidationError,
        evaluate_condition,
        validate_condition,
    )
    from runtime.human_gate import HumanGateError, HumanGateStore
    from runtime.limits import ArtifactLimitError, RuntimeLimits
    from runtime.path_safety import assert_safe_run_tree

MAX_INPUT_BYTES = 2 * 1024 * 1024


def _load_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        if source.stat().st_size > MAX_INPUT_BYTES:
            raise HumanGateError(
                f"JSON input exceeds {MAX_INPUT_BYTES} bytes: {source}"
            )
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HumanGateError(f"cannot read JSON input {source}: {exc}") from exc


def _run_context(run_dir: str | Path) -> tuple[Path, HumanGateStore]:
    candidate = Path(run_dir).expanduser().absolute()
    runs_root = legacy._runs_root().resolve()
    if not candidate.is_relative_to(runs_root):
        raise HumanGateError(f"gate run directory must be below {runs_root}")
    if not candidate.is_dir():
        raise HumanGateError(f"gate run directory does not exist: {candidate}")
    assert_safe_run_tree(candidate)
    if not (candidate / "workflow-ir.resolved.json").is_file():
        raise HumanGateError("gate run directory lacks workflow-ir.resolved.json")
    if not (candidate / "checkpoint.json").is_file():
        raise HumanGateError("gate run directory lacks checkpoint.json")
    raw_ir = _load_json(candidate / "workflow-ir.resolved.json")
    if not isinstance(raw_ir, dict):
        raise HumanGateError("resolved Workflow IR must be an object")
    try:
        limits = RuntimeLimits.from_mapping(raw_ir.get("limits"))
    except ValueError as exc:
        raise HumanGateError(f"invalid resolved runtime limits: {exc}") from exc
    return candidate, HumanGateStore(candidate, limits)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="bounded Workflow IR condition and human-gate commands"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    condition = subparsers.add_parser(
        "condition-evaluate",
        help="evaluate one bounded condition without advancing a workflow",
    )
    condition.add_argument("--condition", required=True, help="condition JSON file")
    condition.add_argument("--sources", required=True, help="node-id source JSON map")
    condition.add_argument(
        "--dependency",
        action="append",
        default=[],
        help="declared source dependency; repeatable",
    )

    status = subparsers.add_parser(
        "gate-status", help="show one or every run-scoped human gate record"
    )
    status.add_argument("--run-dir", required=True)
    status.add_argument("--node-id", default=None)

    decide = subparsers.add_parser(
        "gate-decide", help="write one explicit immutable human gate decision"
    )
    decide.add_argument("--run-dir", required=True)
    decide.add_argument("--node-id", required=True)
    decide.add_argument("--decision", required=True)
    decide.add_argument(
        "--actor",
        required=True,
        help="unauthenticated audit label for the decision submitter",
    )
    decide.add_argument(
        "--source",
        required=True,
        choices=["user", "host"],
        help="audit provenance label; this is not authentication",
    )
    decide.add_argument("--expected-input-identity", required=True)
    decide.add_argument("--note", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "condition-evaluate":
            condition = validate_condition(_load_json(args.condition))
            sources = _load_json(args.sources)
            if not isinstance(sources, dict):
                raise ConditionValidationError("sources must be an object")
            dependencies = set(args.dependency)
            if condition["source"] not in dependencies:
                raise ConditionValidationError(
                    "condition source must be supplied as --dependency"
                )
            result = evaluate_condition(condition, sources)
        elif args.command == "gate-status":
            _, store = _run_context(args.run_dir)
            result = (
                store.load(args.node_id)
                if args.node_id
                else {"gates": store.list_records()}
            )
        else:
            _, store = _run_context(args.run_dir)
            result = store.decide(
                args.node_id,
                decision=args.decision,
                actor=args.actor,
                source=args.source,
                expected_input_identity=args.expected_input_identity,
                note=args.note,
            )
    except (
        HumanGateError,
        ConditionValidationError,
        ArtifactLimitError,
        legacy.WorkflowError,
        ValueError,
    ) as exc:
        print(f"gate command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
