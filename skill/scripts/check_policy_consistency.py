#!/usr/bin/env python3
"""Validate repository roles, runtime limits, Workflow IR, and public docs."""

from __future__ import annotations

import argparse
import importlib.util
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
REQUIRED_RUNTIME_FILES = (
    "skill/runtime/__init__.py",
    "skill/runtime/limits.py",
    "skill/runtime/schema_contract.py",
    "skill/runtime/artifacts.py",
    "skill/runtime/state_store.py",
    "skill/runtime/workflow_ir.py",
    "skill/runtime/control_flow.py",
    "skill/references/workflow-ir.md",
)
PERSONAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[/\\]Users[/\\][^/\\\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z]:[/\\](?:Node\.js|\.codex-tmp)(?:[/\\]|$)", re.IGNORECASE),
)


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _expected_tier(value: Any) -> str | None:
    return None if value == "inherit" else value


def _validate_roles(root: Path, policy: dict[str, Any], errors: list[str]) -> None:
    routes = policy.get("routes")
    if not isinstance(routes, dict):
        errors.append("policy routes table is missing")
        return

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
            "service_tier": _expected_tier(route_policy.get("tier")),
        }
        for key, value in expected.items():
            actual = role.get(key)
            if actual != value:
                errors.append(
                    f"{relative}: {key}={actual!r}, policy requires {value!r}"
                )


def _validate_runtime_contract(root: Path, policy: dict[str, Any], errors: list[str]) -> None:
    for relative in REQUIRED_RUNTIME_FILES:
        if not (root / relative).is_file():
            errors.append(f"runtime foundation file is missing: {relative}")

    limits_path = root / "skill" / "runtime" / "limits.py"
    workflow_ir_path = root / "skill" / "runtime" / "workflow_ir.py"
    if not limits_path.is_file() or not workflow_ir_path.is_file():
        return

    try:
        limits_module = _load_module("dynamic_workflow_policy_limits", limits_path)
        workflow_ir_module = _load_module(
            "dynamic_workflow_policy_ir", workflow_ir_path
        )
    except Exception as exc:  # pragma: no cover - surfaced in CI diagnostics
        errors.append(f"cannot import runtime contract modules: {exc}")
        return

    limits_policy = policy.get("limits")
    if not isinstance(limits_policy, dict):
        errors.append("policy limits table is missing")
    else:
        defaults = limits_policy.get("defaults")
        ceilings = limits_policy.get("hard_ceiling")
        if not isinstance(defaults, dict):
            errors.append("policy limits.defaults table is missing")
        else:
            runtime_defaults = limits_module.RuntimeLimits().to_dict()
            if defaults != runtime_defaults:
                errors.append(
                    "policy limits.defaults disagrees with RuntimeLimits defaults: "
                    f"policy={defaults!r} runtime={runtime_defaults!r}"
                )
        if not isinstance(ceilings, dict):
            errors.append("policy limits.hard_ceiling table is missing")
        elif ceilings != limits_module.HARD_CEILINGS:
            errors.append(
                "policy limits.hard_ceiling disagrees with runtime ceilings: "
                f"policy={ceilings!r} runtime={limits_module.HARD_CEILINGS!r}"
            )

    ir_policy = policy.get("workflow_ir")
    if not isinstance(ir_policy, dict):
        errors.append("policy workflow_ir table is missing")
    else:
        if ir_policy.get("current_version") != workflow_ir_module.IR_VERSION:
            errors.append("policy Workflow IR current_version disagrees with runtime")
        policy_kinds = ir_policy.get("validated_node_kinds")
        if not isinstance(policy_kinds, list) or set(policy_kinds) != workflow_ir_module.NODE_KINDS:
            errors.append("policy Workflow IR node kinds disagree with runtime")
        executable = ir_policy.get("executable_node_kinds")
        if (
            not isinstance(executable, list)
            or len(executable) != len(set(executable))
            or set(executable) != workflow_ir_module.EXECUTABLE_NODE_KINDS
        ):
            errors.append(
                "policy Workflow IR executable_node_kinds disagrees with runtime"
            )


def _validate_public_surfaces(root: Path, policy: dict[str, Any], errors: list[str]) -> None:
    openai_path = root / "skill" / "agents" / "openai.yaml"
    if openai_path.is_file():
        openai_yaml = openai_path.read_text(encoding="utf-8")
        implicit_value = str(bool(policy.get("allow_implicit_invocation"))).lower()
        if f"allow_implicit_invocation: {implicit_value}" not in openai_yaml:
            errors.append(
                "skill/agents/openai.yaml allow_implicit_invocation disagrees with policy"
            )
    else:
        errors.append("skill/agents/openai.yaml is missing")

    route_tokens = {"spark": "Spark", "luna": "Luna", "sol": "Sol"}
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

    readme_path = root / "README.md"
    if readme_path.is_file():
        readme = readme_path.read_text(encoding="utf-8")
        for token in ("skill/cli.py", "checkpoint.json", "events.jsonl", "Workflow IR v3"):
            if token not in readme:
                errors.append(f"README.md must document {token}")

    cli_doc = root / "skill" / "references" / "cli-runner.md"
    if cli_doc.is_file():
        text = cli_doc.read_text(encoding="utf-8")
        for token in (
            "max_result_bytes",
            "UPSTREAM_ARTIFACT_REFERENCE",
            "checkpoint.json",
            "events.jsonl",
            "validate-ir",
        ):
            if token not in text:
                errors.append(f"skill/references/cli-runner.md must document {token}")


def _validate_repository_paths(root: Path, errors: list[str]) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() not in {
            ".md",
            ".py",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
        }:
            continue
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in PERSONAL_PATH_PATTERNS):
            errors.append(f"{relative} contains a machine-specific absolute path")


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

    _validate_roles(root, policy, errors)

    enabled_grok = root / "config" / "agents" / "grok_writer.toml"
    disabled_grok = root / "config" / "agents" / "grok_writer.toml.disabled"
    if enabled_grok.exists():
        errors.append("grok_writer.toml must not be enabled as a native route")
    if not disabled_grok.is_file():
        errors.append("grok_writer.toml.disabled rollback reference is missing")

    _validate_runtime_contract(root, policy, errors)
    _validate_public_surfaces(root, policy, errors)
    _validate_repository_paths(root, errors)
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
    payload = {"ok": not errors, "errors": errors, "warnings": warnings}
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
