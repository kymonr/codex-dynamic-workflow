#!/usr/bin/env python3
"""Portable entry point for Dynamic Workflow CLI runtimes."""

from __future__ import annotations

import sys

from platform_paths import apply_runtime_defaults, configure_utf8_stdio

apply_runtime_defaults()


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"run-ir", "resume-ir"}:
        from ir_runner import main as ir_main

        return ir_main(arguments)
    if arguments and arguments[0] in {
        "condition-evaluate",
        "gate-status",
        "gate-decide",
    }:
        from gate_cli import main as gate_main

        return gate_main(arguments)
    if arguments and arguments[0] in {"plan-ir", "run-status"}:
        from ops_cli import main as ops_main

        return ops_main(arguments)
    if arguments and arguments[0] in {"preset-list", "preset-ir"}:
        from swarm_presets import main as preset_main

        return preset_main(arguments)
    if arguments and arguments[0] in {
        "auto-plan-contract",
        "auto-plan-apply",
        "auto-plan",
    }:
        from auto_planner import main as auto_plan_main

        return auto_plan_main(arguments)
    if arguments and arguments[0] in {
        "writer-plan",
        "writer-run",
        "writer-status",
        "writer-export",
        "writer-cleanup",
    }:
        from writer_cli import main as writer_main

        return writer_main(arguments)

    from runner import main as legacy_main

    return legacy_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
