from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_cli
import skill.cli as portable_cli
import skill.writer_cli as packaged_writer_cli


class WriterCliTests(unittest.TestCase):
    def test_plan_and_status_route_without_fallback(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            writer_cli,
            "plan_writer",
            return_value={"operation": "writer-plan", "model_calls": 0, "writes": []},
        ), contextlib.redirect_stdout(output):
            code = writer_cli.main(
                [
                    "writer-plan",
                    "--package", "package.json",
                    "--repository", "repo",
                    "--expected-package-digest", "a" * 64,
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["operation"], "writer-plan")

    def test_run_requires_ack_and_maps_attention_to_exit_two(self) -> None:
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = writer_cli.main(
                [
                    "writer-run",
                    "--package", "package.json",
                    "--repository", "repo",
                    "--expected-package-digest", "a" * 64,
                    "--expected-head-sha", "b" * 40,
                ]
            )
        self.assertEqual(code, 1)
        output = io.StringIO()
        with mock.patch.object(
            writer_cli,
            "run_writer",
            return_value={"state": "attention_required"},
        ), contextlib.redirect_stdout(output):
            code = writer_cli.main(
                [
                    "writer-run",
                    "--package", "package.json",
                    "--repository", "repo",
                    "--expected-package-digest", "a" * 64,
                    "--expected-head-sha", "b" * 40,
                    "--ack-isolated-worktree-write",
                ]
            )
        self.assertEqual(code, 2)

    def test_portable_cli_routes_writer_commands(self) -> None:
        with mock.patch.object(packaged_writer_cli, "main", return_value=17) as routed:
            self.assertEqual(
                portable_cli.main(["writer-status", "--run-dir", "x"]), 17
            )
        routed.assert_called_once_with(["writer-status", "--run-dir", "x"])

    def test_unknown_arguments_fail_in_argparse(self) -> None:
        with self.assertRaises(SystemExit):
            writer_cli.main(["writer-status", "--run-dir", "x", "--commit"])


if __name__ == "__main__":
    unittest.main()
