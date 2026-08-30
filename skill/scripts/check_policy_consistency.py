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

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from platform_paths import configure_utf8_stdio

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
CAPABILITY_SURFACES = (
    "README.md",
    "skill/references/workflow-ir.md",
    "skill/references/cli-runner.md",
)
BOUNDED_LOOP_CAPABILITY_QUALIFIER = (
    "Only `loop` instances that fully satisfy the Bounded Loop v1 contract are "
    "executable. Legacy `loop` declarations remain instance-level validated-only "
    "and are explicitly rejected at execution."
)
REQUIRED_RUNTIME_FILES = (
    "skill/runtime/__init__.py",
    "skill/runtime/limits.py",
    "skill/runtime/schema_contract.py",
    "skill/runtime/artifacts.py",
    "skill/runtime/state_store.py",
    "skill/runtime/workflow_ir.py",
    "skill/runtime/control_flow.py",
    "skill/runtime/condition.py",
    "skill/runtime/human_gate.py",
    "skill/runtime/deadline.py",
    "skill/references/workflow-ir.md",
    "skill/references/bounded-loop-v1.md",
    "skill/references/agent-fleet.md",
)
PERSONAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[/\\]Users[/\\][^/\\\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z]:[/\\](?:Node\.js|\.codex-tmp)(?:[/\\]|$)", re.IGNORECASE),
)


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_module(name: str, path: Path):
    runtime_path = str(path.parent)
    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)
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


def _validate_writer_routing(policy: dict[str, Any], errors: list[str]) -> None:
    if policy.get("single_native_writer") is not True:
        errors.append("Dynamic Workflow must keep one native writer")
    if policy.get("default_native_writer_route") != "sol":
        errors.append("Dynamic Workflow default native writer route must be sol")
    if policy.get("explicit_native_model_precedence") is not True:
        errors.append("explicit supported native model selection must take precedence")
    if policy.get("native_grok_route") is not False:
        errors.append("Grok must remain outside native routing")

    routes = policy.get("routes")
    if not isinstance(routes, dict):
        return
    luna = routes.get("luna")
    sol = routes.get("sol")
    if (
        not isinstance(luna, dict)
        or luna.get("access") != "read_or_explicit_scoped_writer"
    ):
        errors.append("Luna route must allow only explicit scoped writing")
    if not isinstance(sol, dict) or sol.get("access") != "read_or_scoped_writer":
        errors.append("Sol route must own native delegated writes")

    grok = policy.get("explicit_grok_task")
    expected_grok = {
        "enabled": True,
        "native": False,
        "purpose": "second_review",
        "access": "read_only",
        "writer": False,
        "native_reviewer": False,
        "fallback": False,
        "recovery": False,
        "requires_explicit_user_request": True,
        "requires_separate_visible_task": True,
        "requires_frozen_candidate": True,
    }
    if not isinstance(grok, dict):
        errors.append("explicit Grok second-review policy is missing")
    else:
        for key, expected in expected_grok.items():
            if grok.get(key) != expected:
                errors.append(f"explicit Grok task {key} must be {expected!r}")


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
        if (
            not isinstance(policy_kinds, list)
            or policy_kinds != list(workflow_ir_module.NODE_KIND_ORDER)
            or set(policy_kinds) != workflow_ir_module.NODE_KINDS
        ):
            errors.append("policy Workflow IR node kinds disagree with runtime")
        executable = ir_policy.get("executable_node_kinds")
        if (
            not isinstance(executable, list)
            or executable != list(workflow_ir_module.EXECUTABLE_NODE_KIND_ORDER)
            or set(executable) != workflow_ir_module.EXECUTABLE_NODE_KINDS
        ):
            errors.append(
                "policy Workflow IR executable_node_kinds disagrees with runtime"
            )
        control_flow = ir_policy.get("control_flow")
        if not isinstance(control_flow, dict):
            errors.append("policy workflow_ir.control_flow table is missing")
        else:
            dependency_policies = control_flow.get("dependency_policies")
            if (
                not isinstance(dependency_policies, list)
                or set(dependency_policies)
                != workflow_ir_module.DEPENDENCY_POLICIES
            ):
                errors.append(
                    "policy dependency_policies disagrees with runtime"
                )
            if (
                control_flow.get("default_dependency_policy")
                != workflow_ir_module.DEFAULT_DEPENDENCY_POLICY
            ):
                errors.append(
                    "policy default_dependency_policy disagrees with runtime"
                )
            if (
                control_flow.get("token_budget_mode")
                != workflow_ir_module.TOKEN_BUDGET_MODE
            ):
                errors.append("policy token_budget_mode disagrees with runtime")
            if (
                control_flow.get("timeout_scope")
                != workflow_ir_module.TIMEOUT_SCOPE
            ):
                errors.append("policy timeout_scope disagrees with runtime")
        _validate_bounded_loop_contract(ir_policy, workflow_ir_module, errors)


def _validate_bounded_loop_contract(
    ir_policy: dict[str, Any], workflow_ir_module: Any, errors: list[str]
) -> None:
    policy_contract = ir_policy.get("bounded_loop")
    runtime_contract = getattr(workflow_ir_module, "BOUNDED_LOOP_CONTRACT", None)
    if not isinstance(policy_contract, dict):
        errors.append("policy workflow_ir.bounded_loop table is missing")
        return
    if not isinstance(runtime_contract, dict):
        errors.append("runtime BOUNDED_LOOP_CONTRACT is missing")
        return
    if policy_contract != runtime_contract:
        errors.append(
            "policy workflow_ir.bounded_loop disagrees with runtime contract: "
            f"policy={policy_contract!r} runtime={runtime_contract!r}"
        )

    optional_ranges = getattr(workflow_ir_module, "OPTIONAL_BUDGET_RANGES", {})
    runtime_timeout_range = optional_ranges.get("workflow_timeout_seconds")
    policy_timeout_range = (
        policy_contract.get("workflow_timeout_min_seconds"),
        policy_contract.get("workflow_timeout_max_seconds"),
    )
    if policy_timeout_range != runtime_timeout_range:
        errors.append(
            "policy bounded-loop workflow timeout range disagrees with "
            "OPTIONAL_BUDGET_RANGES"
        )


def _expected_capability_matrix(policy: dict[str, Any]) -> str:
    ir_policy = policy.get("workflow_ir")
    if not isinstance(ir_policy, dict):
        return ""
    validated = ir_policy.get("validated_node_kinds")
    executable = ir_policy.get("executable_node_kinds")
    if not isinstance(validated, list) or not isinstance(executable, list):
        return ""
    executable_set = set(executable)
    validated_only = [item for item in validated if item not in executable_set]
    executable_text = ", ".join(f"`{item}`" for item in executable)
    validated_only_text = (
        ", ".join(f"`{item}`" for item in validated_only)
        if validated_only
        else "none"
    )
    return (
        f"Executable node kinds: {executable_text}.\n"
        f"Validated-only node kinds: {validated_only_text}."
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

    _validate_capability_surfaces(root, policy, errors)

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


def _validate_capability_surfaces(
    root: Path, policy: dict[str, Any], errors: list[str]
) -> None:
    capability_matrix = _expected_capability_matrix(policy)
    for relative in CAPABILITY_SURFACES:
        path = root / relative
        if not path.is_file():
            errors.append(f"capability surface is missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if not capability_matrix or capability_matrix not in text:
            errors.append(
                f"{relative} lacks the policy-derived Workflow IR capability matrix"
            )
        if BOUNDED_LOOP_CAPABILITY_QUALIFIER not in text:
            errors.append(
                f"{relative} lacks the bounded-loop instance-level qualifier"
            )
        for stale in (
            "`loop`、`conditional` 和 `human_gate` 仍会被严格校验",
            "`loop`、`conditional` 和 `human_gate` 仍只验证、不执行",
            "在 v3 控制流 runtime 完成前不会被静默执行或降级",
        ):
            if stale in text:
                errors.append(f"{relative} contains stale capability text")




def _validate_native_agent_fleet_policy(
    policy: dict[str, Any], errors: list[str]
) -> None:
    fleet = policy.get("agent_fleet")
    if not isinstance(fleet, dict):
        errors.append("native Agent Fleet policy is missing")
        return

    expected_root = {
        "implementation": "native_subagents",
        "supported_sizes": [4, 6, 8],
        "default_size": 6,
        "disclose_before_start": True,
        "confirmation_after_disclosure": False,
        "visible_top_level": True,
        "fork_turns": "none",
        "read_only": True,
        "nested_delegation": False,
        "direct_agent_messages": False,
        "majority_vote": False,
        "root_final_decision": True,
        "root_must_address_sol": True,
        "reproduced_severe_cannot_be_outvoted": True,
        "unresolved_conflict": "unknown",
        "exact_unsupported_count": "conflict",
        "candidate_check": "phase_boundary",
        "candidate_drift": "unknown_stop",
        "technical_failure_replacement_limit": 1,
    }
    for key, expected in expected_root.items():
        if fleet.get(key) != expected:
            errors.append(
                f"native Agent Fleet {key}={fleet.get(key)!r}, requires {expected!r}"
            )

    expected_allocations = {
        "size_4": {
            "discovery_luna": 1,
            "challenge_luna": 1,
            "reproduction_luna": 1,
            "sol_final_review": 1,
        },
        "size_6": {
            "discovery_luna": 3,
            "challenge_luna": 1,
            "reproduction_luna": 1,
            "sol_final_review": 1,
        },
        "size_8": {
            "discovery_luna": 4,
            "challenge_luna": 1,
            "reproduction_luna": 1,
            "sol_evidence_review": 1,
            "sol_system_review": 1,
        },
    }
    expected_mixes = {4: (3, 1), 6: (5, 1), 8: (6, 2)}
    for table_name, expected in expected_allocations.items():
        actual = fleet.get(table_name)
        if actual != expected:
            errors.append(
                f"native Agent Fleet {table_name}={actual!r}, requires {expected!r}"
            )
            continue
        size = int(table_name.removeprefix("size_"))
        total = sum(actual.values())
        luna = sum(value for key, value in actual.items() if key.endswith("_luna"))
        sol = sum(value for key, value in actual.items() if key.startswith("sol_"))
        if total != size:
            errors.append(f"native Agent Fleet {table_name} totals {total}, not {size}")
        if (luna, sol) != expected_mixes[size]:
            errors.append(
                f"native Agent Fleet {table_name} mix={(luna, sol)!r}, "
                f"requires {expected_mixes[size]!r}"
            )

    routes = policy.get("routes")
    if not isinstance(routes, dict):
        return
    for route_name, model, effort in (
        ("luna", "gpt-5.6-luna", "max"),
        ("sol", "gpt-5.6-sol", "xhigh"),
    ):
        route = routes.get(route_name)
        if not isinstance(route, dict):
            errors.append(f"native Agent Fleet route is missing: {route_name}")
            continue
        if route.get("model") != model or route.get("effort") != effort:
            errors.append(
                f"native Agent Fleet {route_name} identity disagrees with route policy"
            )


def _validate_worktree_writer_policy(root: Path, errors: list[str]) -> None:
    path = root / "config" / "worktree-writer-policy.toml"
    if not path.is_file():
        errors.append("config/worktree-writer-policy.toml is missing")
        return
    try:
        policy = _load_toml(path)["worktree_writer"]
        import writer_contract
        import writer_process
        import writer_review
        import writer_runtime_base
    except Exception as exc:
        errors.append(f"cannot load Worktree Writer policy/runtime: {exc}")
        return

    if policy.get("runtime_version") != writer_runtime_base.WRITER_RUNTIME_VERSION:
        errors.append("Worktree Writer runtime_version disagrees with runtime")
    if policy.get("writer_route_binding_version") != (
        writer_process.WRITER_BINDING_VERSION
    ):
        errors.append("Worktree Writer binding version disagrees with runtime")
    for key in ("explicit_cli_only", "single_active_writer_per_repository"):
        if policy.get(key) is not True:
            errors.append(f"Worktree Writer {key} must be true")
    for key in (
        "auto_planner_activation",
        "workflow_ir_activation",
        "automatic_resume",
        "automatic_retry",
        "automatic_apply",
        "automatic_commit",
        "automatic_push",
        "automatic_merge",
        "automatic_release",
        "automatic_deploy",
    ):
        if policy.get(key) is not False:
            errors.append(f"Worktree Writer {key} must be false")

    package = policy.get("package")
    if not isinstance(package, dict):
        errors.append("Worktree Writer package policy is missing")
    else:
        if set(package.get("allowed_actions", [])) != set(
            writer_contract.GRANTABLE_ACTIONS
        ):
            errors.append("Worktree Writer allowed actions disagree with runtime")
        if set(package.get("supported_versions", [])) != set(
            writer_contract.SUPPORTED_PACKAGE_VERSIONS
        ):
            errors.append("Worktree Writer package versions disagree with runtime")
        if package.get("max_v2_quality_context_bytes") != (
            writer_contract.MAX_QUALITY_CONTEXT_BYTES
        ):
            errors.append("Worktree Writer quality-context budget disagrees with runtime")

    writer = policy.get("writer")
    if not isinstance(writer, dict):
        errors.append("Worktree Writer fixed writer policy is missing")
    else:
        binding = writer_process.writer_binding_record()
        route = binding["route"]
        limits = binding["limits"]
        expected_writer = {
            "selection": binding["selection"],
            "role": route["role"],
            "model": route["model"],
            "effort": route["effort"],
            "tier": "inherit" if route["tier"] is None else route["tier"],
            "package_version": binding["package_version"],
            **limits,
            "requires_quality_context": binding["requires_quality_context"],
            "attempts": 1,
            "retry": 0,
            "upgrade": "none",
            "sandbox": writer_process.WRITER_ROUTE.sandbox,
            "network": False,
            "shell_tool": False,
            "code_mode": False,
            "multi_agent": False,
            "edit_tool": "apply_patch-only",
        }
        for key, expected in expected_writer.items():
            if writer.get(key) != expected:
                errors.append(
                    f"Worktree Writer fixed writer {key} disagrees with runtime"
                )

    reviewer = policy.get("reviewer")
    if not isinstance(reviewer, dict):
        errors.append("Worktree Writer reviewer policy is missing")
    else:
        expected_reviewer = {
            "agent_type": writer_review.REVIEWER_AGENT_TYPE,
            "model": writer_process.REVIEWER_ROUTE.model,
            "effort": writer_process.REVIEWER_ROUTE.effort,
            "sandbox": writer_process.REVIEWER_ROUTE.sandbox,
            "attempts": 1,
            "retry": 0,
            "upgrade": "none",
            "fresh_process": True,
            "write_authority": False,
        }
        for key, expected in expected_reviewer.items():
            if reviewer.get(key) != expected:
                errors.append(
                    f"Worktree Writer reviewer {key} disagrees with runtime"
                )

    candidate = policy.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("bind_writer_route") is not True:
        errors.append("Worktree Writer candidate must bind the fixed writer route")

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

    _validate_writer_routing(policy, errors)
    _validate_roles(root, policy, errors)

    enabled_grok = root / "config" / "agents" / "grok_writer.toml"
    disabled_grok = root / "config" / "agents" / "grok_writer.toml.disabled"
    if enabled_grok.exists():
        errors.append("grok_writer.toml must not be enabled as a native route")
    if not disabled_grok.is_file():
        errors.append("grok_writer.toml.disabled rollback reference is missing")

    _validate_runtime_contract(root, policy, errors)
    _validate_native_agent_fleet_policy(policy, errors)
    _validate_worktree_writer_policy(root, errors)
    _validate_public_surfaces(root, policy, errors)
    _validate_repository_paths(root, errors)
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
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
