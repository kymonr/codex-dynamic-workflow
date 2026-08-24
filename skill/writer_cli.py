#!/usr/bin/env python3
"""Explicit CLI for the isolated Worktree Writer v1 runtime."""

from __future__ import annotations

import argparse
import io
import json
import sys

try:
    from skill.writer_contract import WriterContractError
    from skill.writer_effects import WriterEffectError
    from skill.writer_process import WriterProcessError
    from skill.writer_review import WriterReviewError
    from skill.writer_runtime import (
        WriterRuntimeError,
        cleanup_writer,
        export_writer,
        plan_writer,
        run_writer,
        status_writer,
    )
except ModuleNotFoundError:
    from writer_contract import WriterContractError
    from writer_effects import WriterEffectError
    from writer_process import WriterProcessError
    from writer_review import WriterReviewError
    from writer_runtime import (
        WriterRuntimeError,
        cleanup_writer,
        export_writer,
        plan_writer,
        run_writer,
        status_writer,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="isolated Worktree Writer v1 candidate runtime"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser(
        "writer-plan",
        help="zero-model, zero-write package/base/capability preview",
    )
    plan.add_argument("--package", required=True)
    plan.add_argument("--repository", required=True)
    plan.add_argument("--expected-package-digest", required=True)

    run = subparsers.add_parser(
        "writer-run",
        help="create one detached worktree and run one writer plus one reviewer",
    )
    run.add_argument("--package", required=True)
    run.add_argument("--repository", required=True)
    run.add_argument("--expected-package-digest", required=True)
    run.add_argument("--expected-head-sha", required=True)
    run.add_argument("--run-dir", default=None)
    run.add_argument("--ack-isolated-worktree-write", action="store_true")

    status = subparsers.add_parser(
        "writer-status", help="read-only integrity and terminal-state query"
    )
    status.add_argument("--run-dir", required=True)

    export = subparsers.add_parser(
        "writer-export", help="emit the immutable candidate package and patch"
    )
    export.add_argument("--run-dir", required=True)

    cleanup = subparsers.add_parser(
        "writer-cleanup", help="explicit host cleanup of one terminal isolated worktree"
    )
    cleanup.add_argument("--run-dir", required=True)
    cleanup.add_argument("--expected-run-id", required=True)
    cleanup.add_argument("--expected-package-digest", required=True)
    cleanup.add_argument("--ack-delete-isolated-worktree", action="store_true")
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
        if args.command == "writer-plan":
            result = plan_writer(
                package_path=args.package,
                repository=args.repository,
                expected_package_digest=args.expected_package_digest,
            )
        elif args.command == "writer-run":
            result = run_writer(
                package_path=args.package,
                repository=args.repository,
                expected_package_digest=args.expected_package_digest,
                expected_head_sha=args.expected_head_sha,
                ack_isolated_worktree_write=args.ack_isolated_worktree_write,
                requested_run_dir=args.run_dir,
            )
        elif args.command == "writer-status":
            result = status_writer(args.run_dir)
        elif args.command == "writer-export":
            result = export_writer(args.run_dir)
        else:
            result = cleanup_writer(
                run_dir=args.run_dir,
                expected_run_id=args.expected_run_id,
                expected_package_digest=args.expected_package_digest,
                ack_delete_isolated_worktree=args.ack_delete_isolated_worktree,
            )
    except (
        WriterContractError,
        WriterEffectError,
        WriterProcessError,
        WriterReviewError,
        WriterRuntimeError,
        OSError,
        ValueError,
    ) as exc:
        print(f"Worktree Writer failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "writer-run":
        state = result.get("state")
        if state in {"ship_candidate", "fix_first", "rethink"}:
            return 0
        if state == "cancelled":
            return 130
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
