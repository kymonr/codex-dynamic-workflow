from __future__ import annotations

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
