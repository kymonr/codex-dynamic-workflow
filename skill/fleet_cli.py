#!/usr/bin/env python3
"""Explicit CLI for Agent Fleet v1."""

from __future__ import annotations

import argparse
import io
import json
import sys

try:
    from skill.fleet_candidate import FleetCandidateError
    from skill.fleet_contract import FleetContractError
    from skill.fleet_findings import FleetFindingError
    from skill.fleet_process import FleetProcessError
    from skill.fleet_records import FleetRecordError
    from skill.fleet_runtime import (
        FLEET_ACK,
        FleetRuntimeError,
        plan_fleet,
        run_fleet,
        status_fleet,
    )
except ModuleNotFoundError as exc:
    if exc.name != "skill":
        raise
    from fleet_candidate import FleetCandidateError
    from fleet_contract import FleetContractError
    from fleet_findings import FleetFindingError
    from fleet_process import FleetProcessError
    from fleet_records import FleetRecordError
    from fleet_runtime import (
        FLEET_ACK,
        FleetRuntimeError,
        plan_fleet,
        run_fleet,
        status_fleet,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="read-only 4-12 subagent Agent Fleet v1 runtime"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser(
        "fleet-plan",
        help="zero-model, zero-write package/candidate/schedule preview",
    )
    plan.add_argument("--package", required=True)
    plan.add_argument("--repository", required=True)
    plan.add_argument("--expected-package-digest", required=True)

    run = subparsers.add_parser(
        "fleet-run",
        help="run one bounded read-only Luna fleet with conditional Sol arbitration",
    )
    run.add_argument("--package", required=True)
    run.add_argument("--repository", required=True)
    run.add_argument("--expected-package-digest", required=True)
    run.add_argument("--run-dir", default=None)
    run.add_argument(FLEET_ACK, action="store_true")

    status = subparsers.add_parser(
        "fleet-status", help="read-only validation of terminal fleet evidence"
    )
    status.add_argument("--run-dir", required=True)
    return parser


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.StringIO):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="strict")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fleet-plan":
            result = plan_fleet(
                package_path=args.package,
                repository=args.repository,
                expected_package_digest=args.expected_package_digest,
            )
        elif args.command == "fleet-run":
            result = run_fleet(
                package_path=args.package,
                repository=args.repository,
                expected_package_digest=args.expected_package_digest,
                ack_read_only_agent_fleet=args.ack_read_only_agent_fleet,
                requested_run_dir=args.run_dir,
            )
        else:
            result = status_fleet(args.run_dir)
    except (
        FleetCandidateError,
        FleetContractError,
        FleetFindingError,
        FleetProcessError,
        FleetRecordError,
        FleetRuntimeError,
        OSError,
        ValueError,
    ) as exc:
        print(f"Agent Fleet failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.command == "fleet-run":
        state = result.get("state")
        if state in {"accepted", "accepted_with_notes", "ship"}:
            return 0
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
