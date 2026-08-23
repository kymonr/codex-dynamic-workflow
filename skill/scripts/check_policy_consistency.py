#!/usr/bin/env python3
"""Validate that role files and public routing surfaces match workflow-policy.toml."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROLE_FILES = {
    "spark": "config/agents/spark.toml",
    "luna": "config/agents/luna.toml",
    "sol": "config/agents/sol.toml",
    "reviewer": "config/agents/dynamic_workflow_sol_reviewer.toml",
}
PUBLIC_SURFACES = (
    "README.md",
    "skill/SKILL.md",
    "skill/references/routing.md",
    "integration/AGENTS.dynamic-workflow.md",
    "skill/agents/openai.yaml",
)
PERSONAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[/\\]Users[/\\][^/\\\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z]:[/\\](?:Node\.js|\.codex-tmp)(?:[/\\]|$)", re.IGNORECASE),
)
# runner.py keeps its historical constant for direct-import compatibility. The
# supported CLI entry point sets DYNWF_RUNS_ROOT before importing runner.py.
LEGACY_PATH_EXCEPTIONS = {"skill/runner.py"}


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _expected_tier(value: str) -> str | None:
    return None if value == "inherit" else value


def validate_repository(root: Path) -> tuple[list[str], list[str]]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    policy_path = root / "config" / "workflow-policy.toml"
    if not policy_path.is_file():
        return ([f"missing policy file: {policy_path}"], warnings)
    policy = _load_toml(policy_path)

    if policy.get("version") != 1:
        errors.append("config/workflow-policy.toml version must be 1")
    if policy.get("workflow_name") != "dynamic-workflow":
        errors.append("workflow_name must be dynamic-workflow")

    routes = policy.get("routes")
    if not isinstance(routes, dict):
        return (errors + ["policy routes table is missing"], warnings)

    for route_name, relative in ROLE_FILES.items():
        route_policy = routes.get(route_name)
        if not isinstance(route_policy, dict):
            errors.append(f"policy route is missing: {route_name}")
            continue
        role_path = root / relative
        if not role_path.is_file():
            errors.append(f"role file is missing: {relative}")
            continue
        role = _load_toml(role_path)
        expected = {
            "name": route_policy.get("agent_type"),
            "model": route_policy.get("model"),
            "model_reasoning_effort": route_policy.get("effort"),
            "service_tier": _expected_tier(str(route_policy.get("tier"))),
        }
        for key, value in expected.items():
            actual = role.get(key)
            if actual != value:
                errors.append(
                    f"{relative}: {key}={actual!r}, policy requires {value!r}"
                )

    enabled_grok = root / "config" / "agents" / "grok_writer.toml"
    disabled_grok = root / "config" / "agents" / "grok_writer.toml.disabled"
    if enabled_grok.exists():
        errors.append("grok_writer.toml must not be enabled as a native route")
    if not disabled_grok.is_file():
        errors.append("grok_writer.toml.disabled rollback reference is missing")

    openai_yaml = (root / "skill" / "agents" / "openai.yaml").read_text(
        encoding="utf-8"
    )
    implicit_value = str(bool(policy.get("allow_implicit_invocation"))).lower()
    if f"allow_implicit_invocation: {implicit_value}" not in openai_yaml:
        errors.append(
            "skill/agents/openai.yaml allow_implicit_invocation disagrees with policy"
        )

    route_tokens = {
        "spark": "Spark",
        "luna": "Luna",
        "sol": "Sol",
    }
    for relative in PUBLIC_SURFACES:
        path = root / relative
        if not path.is_file():
            errors.append(f"public routing surface is missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for route, token in route_tokens.items():
            if token not in text:
                errors.append(f"{relative} does not mention policy route {route}")
        if "Grok" not in text:
            errors.append(f"{relative} does not state the explicit Grok boundary")

    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() not in {
            ".md",
            ".py",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = [pattern.pattern for pattern in PERSONAL_PATH_PATTERNS if pattern.search(text)]
        if not matches:
            continue
        message = f"{relative} contains a machine-specific absolute path"
        if relative in LEGACY_PATH_EXCEPTIONS:
            warnings.append(message + "; use skill/cli.py so the portable env default wins")
        else:
            errors.append(message)

    readme = (root / "README.md").read_text(encoding="utf-8")
    if "skill/cli.py" not in readme and "skill\\cli.py" not in readme:
        errors.append("README.md must document skill/cli.py as the portable CLI entry point")

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    errors, warnings = validate_repository(args.root)
    payload = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for warning in warnings:
            print(f"WARNING: {warning}")
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"policy consistency: {'PASS' if not errors else 'FAIL'} "
            f"({len(errors)} errors, {len(warnings)} warnings)"
        )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
