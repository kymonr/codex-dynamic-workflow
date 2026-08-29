from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
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

    def test_cli_has_no_model_effort_or_direct_message_surface(self) -> None:
        for option in ("--model", "--effort", "--message-agent"):
            with self.subTest(option=option), self.assertRaises(SystemExit):
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
