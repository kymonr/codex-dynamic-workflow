from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_cli
import skill.cli as portable_cli
import skill.fleet_cli as packaged_fleet_cli


class FleetCliTests(unittest.TestCase):
    def test_plan_routes_exact_arguments(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            fleet_cli,
            "plan_fleet",
            return_value={"operation": "fleet-plan", "model_calls": 0, "writes": []},
        ) as routed, contextlib.redirect_stdout(output):
            code = fleet_cli.main(
                [
                    "fleet-plan",
                    "--package",
                    "fleet.json",
                    "--repository",
                    "repo",
                    "--expected-package-digest",
                    "a" * 64,
                ]
            )
        self.assertEqual(code, 0)
        routed.assert_called_once_with(
            package_path="fleet.json",
            repository="repo",
            expected_package_digest="a" * 64,
        )

    def test_run_forwards_ack_and_maps_terminal_state(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            fleet_cli,
            "run_fleet",
            return_value={"operation": "fleet-run", "state": "accepted"},
        ) as routed, contextlib.redirect_stdout(output):
            code = fleet_cli.main(
                [
                    "fleet-run",
                    "--package",
                    "fleet.json",
                    "--repository",
                    "repo",
                    "--expected-package-digest",
                    "b" * 64,
                    "--ack-read-only-agent-fleet",
                ]
            )
        self.assertEqual(code, 0)
        routed.assert_called_once_with(
            package_path="fleet.json",
            repository="repo",
            expected_package_digest="b" * 64,
            ack_read_only_agent_fleet=True,
            requested_run_dir=None,
        )

        with mock.patch.object(
            fleet_cli,
            "run_fleet",
            return_value={"operation": "fleet-run", "state": "fix_first"},
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                fleet_cli.main(
                    [
                        "fleet-run",
                        "--package",
                        "fleet.json",
                        "--repository",
                        "repo",
                        "--expected-package-digest",
                        "b" * 64,
                        "--ack-read-only-agent-fleet",
                    ]
                ),
                2,
            )

    def test_direct_script_and_package_module_help_are_import_safe(self) -> None:
        commands = (
            ([sys.executable, str(SKILL / "cli.py"), "fleet-plan", "--help"], "fleet-plan"),
            ([sys.executable, "-m", "skill.cli", "fleet-plan", "--help"], "fleet-plan"),
            ([sys.executable, str(SKILL / "cli.py"), "plan-ir", "--help"], "plan-ir"),
            ([sys.executable, "-m", "skill.cli", "plan-ir", "--help"], "plan-ir"),
            ([sys.executable, str(SKILL / "cli.py"), "writer-plan", "--help"], "writer-plan"),
            ([sys.executable, "-m", "skill.cli", "writer-plan", "--help"], "writer-plan"),
        )
        for command, expected_command in commands:
            with self.subTest(command=command):
                child_env = os.environ.copy()
                child_env.pop("PYTHONPYCACHEPREFIX", None)
                child_env.update(
                    {
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONNOUSERSITE": "1",
                        "NO_COLOR": "1",
                    }
                )
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=child_env,
                    timeout=30,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stdout + completed.stderr,
                )
                self.assertIn(expected_command, completed.stdout)

    def test_cli_has_no_model_effort_or_direct_message_surface(self) -> None:
        for option in ("--model", "--effort", "--message-agent"):
            with (
                self.subTest(option=option),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                fleet_cli.main(
                    [
                        "fleet-plan",
                        "--package",
                        "fleet.json",
                        "--repository",
                        "repo",
                        "--expected-package-digest",
                        "c" * 64,
                        option,
                        "value",
                    ]
                )

    def test_status_is_read_only_route(self) -> None:
        with mock.patch.object(
            fleet_cli,
            "status_fleet",
            return_value={"operation": "fleet-status", "writes": [], "integrity": "match"},
        ) as routed, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                fleet_cli.main(["fleet-status", "--run-dir", "run"]), 0
            )
        routed.assert_called_once_with("run")


    def test_portable_cli_routes_fleet_commands(self) -> None:
        with mock.patch.object(
            packaged_fleet_cli,
            "main",
            return_value=0,
        ) as routed:
            self.assertEqual(
                portable_cli.main(
                    [
                        "fleet-plan",
                        "--package",
                        "fleet.json",
                        "--repository",
                        "repo",
                        "--expected-package-digest",
                        "d" * 64,
                    ]
                ),
                0,
            )
        routed.assert_called_once_with(
            [
                "fleet-plan",
                "--package",
                "fleet.json",
                "--repository",
                "repo",
                "--expected-package-digest",
                "d" * 64,
            ]
        )


if __name__ == "__main__":
    unittest.main()
