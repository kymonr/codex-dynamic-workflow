from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = ROOT / "skill" / "scripts" / "check_policy_consistency.py"
PLATFORM_PATH = ROOT / "skill" / "platform_paths.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("dynamic_workflow_policy_checker", CHECKER_PATH)
platform_paths = _load("dynamic_workflow_platform_paths", PLATFORM_PATH)


class PolicyConsistencyTests(unittest.TestCase):
    def test_repository_policy_is_consistent(self) -> None:
        errors, warnings = checker.validate_repository(ROOT)
        self.assertEqual(errors, [], "\n".join(errors))
        self.assertTrue(
            all("skill/runner.py" in warning for warning in warnings),
            warnings,
        )

    def test_empty_validated_only_capability_is_rendered_as_none(self) -> None:
        policy = checker._load_toml(ROOT / "config" / "workflow-policy.toml")
        self.assertEqual(
            checker._expected_capability_matrix(policy),
            "Executable node kinds: `agent`, `map`, `verify`, `loop`, `reduce`, "
            "`conditional`, `human_gate`.\n"
            "Validated-only node kinds: none.",
        )

    def test_bounded_loop_policy_drift_fails_machine_contract_check(self) -> None:
        policy = checker._load_toml(ROOT / "config" / "workflow-policy.toml")
        drifted = copy.deepcopy(policy)
        drifted["workflow_ir"]["bounded_loop"]["body_max"] = 7
        runtime = checker._load_module(
            "dynamic_workflow_policy_ir_drift_test",
            ROOT / "skill" / "runtime" / "workflow_ir.py",
        )
        errors: list[str] = []
        checker._validate_bounded_loop_contract(
            drifted["workflow_ir"], runtime, errors
        )
        self.assertTrue(
            any("bounded_loop disagrees with runtime contract" in item for item in errors),
            errors,
        )

    def test_capability_surfaces_require_instance_level_loop_qualifier(self) -> None:
        policy = checker._load_toml(ROOT / "config" / "workflow-policy.toml")
        matrix = checker._expected_capability_matrix(policy)
        content = (
            matrix + "\n\n" + checker.BOUNDED_LOOP_CAPABILITY_QUALIFIER + "\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in checker.CAPABILITY_SURFACES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            errors: list[str] = []
            checker._validate_capability_surfaces(root, policy, errors)
            self.assertEqual(errors, [])

            (root / checker.CAPABILITY_SURFACES[0]).write_text(
                matrix + "\n", encoding="utf-8"
            )
            errors = []
            checker._validate_capability_surfaces(root, policy, errors)
            self.assertIn(
                "README.md lacks the bounded-loop instance-level qualifier",
                errors,
            )

    def test_explicit_path_overrides_win(self) -> None:
        env = {
            "DYNWF_HOME": "/state-root",
            "DYNWF_RUNS_ROOT": "/run-root",
            "DYNWF_WORKTREE_ROOT": "/worktree-root",
        }
        self.assertEqual(
            platform_paths.default_state_root(env, home=Path("/home/test"), platform="linux"),
            Path("/state-root"),
        )
        self.assertEqual(
            platform_paths.default_runs_root(env, home=Path("/home/test"), platform="linux"),
            Path("/run-root"),
        )
        self.assertEqual(
            platform_paths.default_worktree_root(env, temp_dir=Path("/tmp")),
            Path("/worktree-root"),
        )

    def test_linux_and_windows_defaults_are_user_scoped(self) -> None:
        linux = platform_paths.default_state_root(
            {}, home=Path("/home/alice"), platform="linux"
        )
        windows = platform_paths.default_state_root(
            {"LOCALAPPDATA": "C:" + r"\Users\Alice\AppData\Local"},
            home=Path("C:" + r"\Users\Alice"),
            platform="win32",
        )
        self.assertEqual(
            linux, Path("/home/alice/.local/state/codex-dynamic-workflow")
        )
        self.assertEqual(windows.name, "codex-dynamic-workflow")
        self.assertNotIn("Orz", str(windows))

    def test_apply_defaults_preserves_caller_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = {
                "DYNWF_HOME": temp,
                "DYNWF_RUNS_ROOT": str(Path(temp) / "custom-runs"),
            }
            values = platform_paths.apply_runtime_defaults(env)
            self.assertEqual(values["DYNWF_RUNS_ROOT"], env["DYNWF_RUNS_ROOT"])
            self.assertIn("DYNWF_WORKTREE_ROOT", env)
            self.assertTrue(
                Path(env["DYNWF_WORKTREE_ROOT"]).name == "worktrees"
            )


if __name__ == "__main__":
    unittest.main()
