#!/usr/bin/env python3
"""Explicit CLI for personal Dynamic Workflow installation management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from installation import (
        InstallManagerError,
        apply_install,
        install_status,
        plan_install,
        rollback_install,
    )
    from platform_paths import configure_utf8_stdio
except ModuleNotFoundError:
    from skill.installation import (
        InstallManagerError,
        apply_install,
        install_status,
        plan_install,
        rollback_install,
    )
    from skill.platform_paths import configure_utf8_stdio


def _default_source_root() -> Path:
    module_candidate = Path(__file__).resolve().parents[1]
    for candidate in (module_candidate, Path.cwd()):
        if (candidate / "skill" / "SKILL.md").is_file() and (
            candidate / "config" / "agents"
        ).is_dir():
            return candidate
    return module_candidate


DEFAULT_SOURCE_ROOT = _default_source_root()


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--codex-home", default=None)
    parser.add_argument("--state-root", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="plan, apply, inspect, and roll back one personal installation"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser(
        "install-plan",
        help="zero-write source/target diff with an exact apply digest",
    )
    plan.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    _add_common_paths(plan)

    apply = subparsers.add_parser(
        "install-apply",
        help="back up changed targets, install exact payload, and publish a manifest",
    )
    apply.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    apply.add_argument("--expected-plan-digest", required=True)
    apply.add_argument("--ack-install", action="store_true")
    _add_common_paths(apply)

    status = subparsers.add_parser(
        "install-status",
        help="read-only installed identity and drift report",
    )
    _add_common_paths(status)

    rollback = subparsers.add_parser(
        "install-rollback",
        help="restore the exact target state from before the active installation",
    )
    rollback.add_argument("--expected-install-id", required=True)
    rollback.add_argument("--ack-rollback", action="store_true")
    _add_common_paths(rollback)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install-plan":
            result = plan_install(
                args.source_root,
                codex_home=args.codex_home,
                state_root=args.state_root,
            )
        elif args.command == "install-apply":
            result = apply_install(
                args.source_root,
                expected_plan_digest=args.expected_plan_digest,
                ack_install=args.ack_install,
                codex_home=args.codex_home,
                state_root=args.state_root,
            )
        elif args.command == "install-status":
            result = install_status(
                codex_home=args.codex_home,
                state_root=args.state_root,
            )
        else:
            result = rollback_install(
                expected_install_id=args.expected_install_id,
                ack_rollback=args.ack_rollback,
                codex_home=args.codex_home,
                state_root=args.state_root,
            )
    except (InstallManagerError, OSError, ValueError) as exc:
        print(f"Install manager failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
