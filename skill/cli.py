#!/usr/bin/env python3
"""Portable entry point for Dynamic Workflow CLI runtimes."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

try:
    from skill.platform_paths import apply_runtime_defaults, configure_utf8_stdio
except ModuleNotFoundError as exc:
    if exc.name != "skill":
        raise
    from platform_paths import apply_runtime_defaults, configure_utf8_stdio

apply_runtime_defaults()


def _main(package_module: str, direct_module: str) -> Callable[[list[str]], int]:
    primary, fallback = (
        (package_module, direct_module)
        if __package__
        else (direct_module, package_module)
    )
    try:
        module = importlib.import_module(primary)
    except ModuleNotFoundError as exc:
        if exc.name not in {"skill", primary}:
            raise
        module = importlib.import_module(fallback)
    return module.main


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    arguments = list(sys.argv[1:] if argv is None else argv)

    if arguments and arguments[0] in {"fleet-plan", "fleet-run", "fleet-status"}:
        return _main("skill.fleet_cli", "fleet_cli")(arguments)
    if arguments and arguments[0] in {"run-ir", "resume-ir"}:
        return _main("skill.ir_runner", "ir_runner")(arguments)
    if arguments and arguments[0] in {
        "condition-evaluate",
        "gate-status",
        "gate-decide",
    }:
        return _main("skill.gate_cli", "gate_cli")(arguments)
    if arguments and arguments[0] in {"plan-ir", "run-status"}:
        return _main("skill.ops_cli", "ops_cli")(arguments)
    if arguments and arguments[0] in {"preset-list", "preset-ir"}:
        return _main("skill.swarm_presets", "swarm_presets")(arguments)
    if arguments and arguments[0] in {
        "auto-plan-contract",
        "auto-plan-apply",
        "auto-plan",
    }:
        return _main("skill.auto_planner", "auto_planner")(arguments)
    if arguments and arguments[0] in {
        "writer-plan",
        "writer-run",
        "writer-status",
        "writer-export",
        "writer-cleanup",
    }:
        return _main("skill.writer_cli", "writer_cli")(arguments)

    if arguments and arguments[0] in {
        "version-bump",
        "install-plan",
        "install-apply",
        "install-status",
        "install-rollback",
    }:
        return _main("skill.install_cli", "install_cli")(arguments)

    return _main("skill.runner", "runner")(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
