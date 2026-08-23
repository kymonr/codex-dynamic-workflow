from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
RUNNER_PATH = SKILL_DIR / "runner.py"
FAKE_CODEX = Path(__file__).with_name("fake_codex.py")
MODULE_SPEC = importlib.util.spec_from_file_location("dynamic_workflow_runner", RUNNER_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
runner = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(runner)


def task(
    task_id: str,
    prompt: str,
    *,
    role: str = "luna",
    depends_on: list[str] | None = None,
    output_schema: dict | None = None,
) -> dict:
    return {
        "id": task_id,
        "prompt": prompt,
        "role": role,
        "route_reason": "offline fixture",
        "depends_on": depends_on or [],
        "output_schema": output_schema,
        "allow_escalation": False,
    }


def role_configs() -> dict:
    return {
        "spark": {
            "role": "spark",
            "model": "gpt-5.3-codex-spark",
            "effort": "high",
            "tier": None,
            "source": "fixture",
        },
        "luna": {
            "role": "luna",
            "model": "gpt-5.6-luna",
            "effort": "max",
            "tier": "fast",
            "source": "fixture",
        },
        "sol": {
            "role": "sol",
            "model": "gpt-5.6-sol",
            "effort": "xhigh",
            "tier": None,
            "source": "fixture",
        },
    }


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.allowed_root = self.base / "allowed"
        self.workdir = self.allowed_root / "work"
        self.workdir.mkdir(parents=True)
        self.codex_home = self.base / "codex-home"
        (self.codex_home / "agents").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def raw(self, tasks: list[dict]) -> dict:
        return {
            "version": 2,
            "name": "offline-test",
            "workdir": str(self.workdir),
            "max_concurrency": 2,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
            "tasks": tasks,
        }

    def validate(self, raw: dict, allow: list[str] | None = None) -> dict:
        return runner.validate_spec(
            raw,
            allowed_roots=[str(self.allowed_root)],
            codex_home=self.codex_home,
            allowed_sensitive_paths=allow,
        )

    def test_rejects_unknown_fields_and_cycles(self) -> None:
        unknown = self.raw([task("one", "inspect")])
        unknown["surprise"] = True
        with self.assertRaises(runner.SpecError):
            self.validate(unknown)

        cycle = self.raw(
            [
                task("one", "inspect", depends_on=["two"]),
                task("two", "inspect", depends_on=["one"]),
            ]
        )
        with self.assertRaisesRegex(runner.SpecError, "含环"):
            self.validate(cycle)

    def test_placeholder_must_be_declared_dependency(self) -> None:
        raw = self.raw(
            [task("one", "inspect"), task("two", "use {{result:one}}")]
        )
        with self.assertRaisesRegex(runner.SpecError, "depends_on"):
            self.validate(raw)

    def test_legacy_stages_convert_to_dependencies(self) -> None:
        raw = {
            "version": 1,
            "name": "legacy-test",
            "workdir": str(self.workdir),
            "max_concurrency": 2,
            "timeout_seconds": 30,
            "stages": [
                {"name": "first", "tasks": [{"id": "one", "prompt": "inspect"}]},
                {
                    "name": "second",
                    "tasks": [
                        {"id": "two", "prompt": "use {{result:one}}", "reasoning_effort": "high"}
                    ],
                },
            ],
        }
        converted = self.validate(raw)
        self.assertTrue(converted["legacy_spec_converted"])
        self.assertEqual(converted["tasks"][1]["depends_on"], ["one"])
        self.assertEqual(converted["tasks"][1]["role"], "luna")
        self.assertFalse(converted["tasks"][1]["allow_escalation"])

    def test_escalation_true_is_rejected_before_execution(self) -> None:
        fixture = task("one", "inspect")
        fixture["allow_escalation"] = True
        with self.assertRaisesRegex(
            runner.SpecError,
            r"^v2 allow_escalation=true is no longer executable; choose the final role explicitly or use native Dynamic Workflow routing$",
        ):
            self.validate(self.raw([fixture]))

    def test_legacy_claude_is_rejected(self) -> None:
        raw = {
            "version": 1,
            "name": "legacy-test",
            "workdir": str(self.workdir),
            "backend": "claude",
            "stages": [{"name": "only", "tasks": [{"id": "one", "prompt": "inspect"}]}],
        }
        with self.assertRaisesRegex(runner.SpecError, "Claude"):
            self.validate(raw)

    def test_sensitive_file_requires_exact_cli_exception(self) -> None:
        (self.workdir / ".env").write_text("fixture=true", encoding="utf-8")
        raw = self.raw([task("one", "inspect")])
        with self.assertRaisesRegex(runner.SpecError, "allow-sensitive-path"):
            self.validate(raw)
        validated = self.validate(raw, [".env"])
        self.assertEqual(validated["workdir"], str(self.workdir.resolve()))

    def test_sensitive_scan_does_not_skip_build_directories(self) -> None:
        build = self.workdir / "build"
        build.mkdir()
        (build / ".env").write_text("fixture=true", encoding="utf-8")
        with self.assertRaisesRegex(runner.SpecError, "allow-sensitive-path"):
            self.validate(self.raw([task("one", "inspect")]))

    def test_rejects_schema_keywords_not_locally_enforced(self) -> None:
        raw = self.raw(
            [task("one", "inspect", output_schema={"type": "string", "pattern": "^SAFE$"})]
        )
        with self.assertRaisesRegex(runner.SpecError, "不支持"):
            self.validate(raw)

    def test_role_files_resolve_luna_fast(self) -> None:
        (self.codex_home / "agents" / "spark.toml").write_text(
            'model="gpt-5.3-codex-spark"\nmodel_reasoning_effort="high"\n',
            encoding="utf-8",
        )
        (self.codex_home / "agents" / "luna.toml").write_text(
            'model="gpt-5.6-luna"\nmodel_reasoning_effort="max"\nservice_tier="fast"\n',
            encoding="utf-8",
        )
        resolved = runner.resolve_role_configs(self.codex_home)
        self.assertEqual(resolved["luna"]["tier"], "fast")
        self.assertEqual(resolved["sol"]["effort"], "xhigh")

    def test_command_is_model_explicit_and_read_only(self) -> None:
        command = runner.build_cmd(
            ["codex.exe"],
            str(self.workdir),
            self.base / "out.json",
            self.base / "schema.json",
            role_configs()["luna"],
        )
        joined = " ".join(command)
        self.assertIn("-s read-only", joined)
        self.assertIn("-m gpt-5.6-luna", joined)
        self.assertIn("model_reasoning_effort=max", joined)
        self.assertIn("service_tier=fast", joined)
        self.assertIn("--ignore-user-config", command)
        self.assertNotIn("workspace-write", joined)
        self.assertNotIn("danger-full-access", joined)
        self.assertNotIn("claude", joined.casefold())
        self.assertEqual(command[-1], "-")
        self.assertNotIn("inspect", command)

    def test_windows_command_restores_sandbox_backend_after_ignoring_config(
        self,
    ) -> None:
        with mock.patch.object(runner.os, "name", "nt"):
            command = runner.build_cmd(
                ["codex.exe"],
                str(self.workdir),
                self.base / "out.json",
                self.base / "schema.json",
                role_configs()["luna"],
            )

        joined = " ".join(command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("-s read-only", joined)
        self.assertIn("windows.sandbox=elevated", command)
        self.assertNotIn("workspace-write", joined)
        self.assertNotIn("disk-full-read-access", joined)
        self.assertNotIn("danger-full-access", joined)
        self.assertNotIn("dangerously-bypass", joined)

    def test_non_windows_command_does_not_select_windows_sandbox_backend(
        self,
    ) -> None:
        with mock.patch.object(runner.os, "name", "posix"):
            command = runner.build_cmd(
                ["codex"],
                str(self.workdir),
                self.base / "out.json",
                self.base / "schema.json",
                role_configs()["luna"],
            )

        self.assertNotIn("windows.sandbox=elevated", command)

    def test_child_environment_is_an_allowlist(self) -> None:
        old_values = {
            key: os.environ.get(key)
            for key in ("LEAK_ME", "HTTPS_PROXY", "NODE_OPTIONS")
        }
        try:
            os.environ["LEAK_ME"] = "secret"
            os.environ["HTTPS_PROXY"] = "http://credential@example.invalid"
            os.environ["NODE_OPTIONS"] = "--require malicious.js"
            child = runner._sanitized_child_env()
            self.assertNotIn("LEAK_ME", child)
            self.assertNotIn("HTTPS_PROXY", child)
            self.assertNotIn("NODE_OPTIONS", child)
            self.assertIn("CODEX_HOME", child)
            self.assertIn("PATH", child)
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_empty_result_schema_is_not_rewritten_to_string(self) -> None:
        envelope = runner.build_envelope_schema({})
        self.assertEqual(envelope["properties"]["result"], {})

    def test_cli_has_no_arbitrary_command_override(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.build_parser().parse_args(
                    [
                        "run",
                        "--spec",
                        "fixture.json",
                        "--allowed-root",
                        str(self.allowed_root),
                        "--codex-cmd",
                        "malicious.exe",
                    ]
                )

    def test_artifact_root_cannot_overlap_workdir(self) -> None:
        normalized = self.validate(self.raw([task("one", "inspect")]))
        with self.assertRaisesRegex(runner.WorkflowError, "workdir 重叠"):
            runner._prepare_run_root(self.allowed_root, normalized, self.codex_home)


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workdir = self.base / "work"
        self.workdir.mkdir()
        self.prefix = [sys.executable, str(FAKE_CODEX)]

    async def test_defensive_escalation_gate_precedes_run_artifacts(self) -> None:
        fixture = task("guard", "FAKE_OK", role="spark")
        fixture["allow_escalation"] = True
        spec = self.spec([fixture], "defensive-escalation-gate")
        run_dir = self.base / "run-defensive-escalation-gate"

        with self.assertRaises(runner.SpecError) as raised:
            await runner.run_workflow(spec, run_dir, self.prefix, role_configs())

        self.assertEqual(
            str(raised.exception),
            "v2 allow_escalation=true is no longer executable; choose the final role explicitly or use native Dynamic Workflow routing",
        )
        self.assertFalse(run_dir.exists())

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_windows_cleanup_uses_absolute_system32_taskkill_file(self) -> None:
        system_directory = self.base / "System32"
        system_directory.mkdir()
        taskkill_path = system_directory / "taskkill.exe"
        taskkill_path.write_text("fixture", encoding="utf-8")

        class FakeProcess:
            pid = 321

            def __init__(self) -> None:
                self.killed = False

            def kill(self) -> None:
                self.killed = True

            async def wait(self) -> int:
                return 0

        class FakeTaskkill:
            async def wait(self) -> int:
                return 0

            def kill(self) -> None:
                return None

        calls: list[tuple[tuple, dict]] = []

        async def fake_create(*args, **kwargs):
            calls.append((args, kwargs))
            return FakeTaskkill()

        proc = FakeProcess()
        with (
            mock.patch.object(runner.sys, "platform", "win32"),
            mock.patch.object(
                runner, "_windows_system_directory", return_value=system_directory
            ),
            mock.patch.object(
                runner.asyncio, "create_subprocess_exec", side_effect=fake_create
            ),
        ):
            cleanup_error = await runner._kill_tree(proc)

        self.assertIsNone(cleanup_error)
        command, kwargs = calls[0]
        self.assertEqual(Path(command[0]), taskkill_path.resolve())
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertEqual(command[1:], ("/F", "/T", "/PID", "321"))
        self.assertEqual(kwargs["cwd"], str(system_directory))
        self.assertTrue(proc.killed)

    async def test_windows_cleanup_nonzero_taskkill_is_unconfirmed(self) -> None:
        system_directory = self.base / "System32"
        system_directory.mkdir()
        (system_directory / "taskkill.exe").write_text("fixture", encoding="utf-8")

        class FakeProcess:
            pid = 654

            def __init__(self) -> None:
                self.killed = False

            def kill(self) -> None:
                self.killed = True

            async def wait(self) -> int:
                return 0

        class FakeTaskkill:
            async def wait(self) -> int:
                return 7

            def kill(self) -> None:
                return None

        async def fake_create(*args, **kwargs):
            return FakeTaskkill()

        proc = FakeProcess()
        with (
            mock.patch.object(runner.sys, "platform", "win32"),
            mock.patch.object(
                runner, "_windows_system_directory", return_value=system_directory
            ),
            mock.patch.object(
                runner.asyncio, "create_subprocess_exec", side_effect=fake_create
            ),
        ):
            cleanup_error = await runner._kill_tree(proc)

        self.assertIsNotNone(cleanup_error)
        self.assertIn("process-tree cleanup unconfirmed", cleanup_error)
        self.assertIn("return code 7", cleanup_error)
        self.assertTrue(proc.killed)

    def spec(self, tasks: list[dict], name: str) -> dict:
        return {
            "version": 2,
            "name": name,
            "workdir": str(self.workdir),
            "max_concurrency": 3,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
            "tasks": tasks,
            "legacy_spec_converted": False,
            "preflight": {
                "ack_external_model_export": False,
                "allowed_roots": [str(self.workdir)],
                "allowed_sensitive_paths": [],
                "codex_home": str(self.base / "codex-home"),
                "codex_executable": None,
                "codex_version": None,
                "codex_signature_status": None,
                "codex_signer_subject": None,
            },
        }

    async def test_failure_blocks_descendants_but_not_independent_branches(self) -> None:
        tasks = [
            task("fail", "FAKE_FAIL_PERMANENT"),
            task("independent", "FAKE_OK"),
            task("blocked", "never runs", depends_on=["fail"]),
            task(
                "descendant",
                "FAKE_ECHO_UPSTREAM {{result:independent}}",
                depends_on=["independent"],
            ),
        ]
        summary = await runner.run_workflow(
            self.spec(tasks, "dag-isolation"),
            self.base / "run-isolation",
            self.prefix,
            role_configs(),
        )
        statuses = {entry["id"]: entry["status"] for entry in summary["tasks"]}
        self.assertEqual(statuses["fail"], "failed")
        self.assertEqual(statuses["blocked"], "blocked")
        self.assertEqual(statuses["independent"], "succeeded")
        self.assertEqual(statuses["descendant"], "succeeded")
        descendant = next(entry for entry in summary["tasks"] if entry["id"] == "descendant")
        self.assertEqual(descendant["output"], "boundary-ok")

    async def test_transient_failure_is_terminal_without_replay_or_upgrade(self) -> None:
        tasks = [
            task("retry", "FAKE_TRANSIENT_ONCE", role="spark"),
            task("upgrade", "FAKE_NEEDS_ESCALATION", role="spark"),
        ]
        summary = await runner.run_workflow(
            self.spec(tasks, "retry-upgrade"),
            self.base / "run-retry-upgrade",
            self.prefix,
            role_configs(),
        )
        entries = {entry["id"]: entry for entry in summary["tasks"]}
        self.assertEqual(entries["retry"]["status"], "failed")
        self.assertEqual(entries["retry"]["retry"], 0)
        self.assertIsNone(entries["retry"]["upgrade"])
        self.assertEqual(len(entries["retry"]["attempts"]), 1)
        self.assertEqual(entries["upgrade"]["status"], "needs_escalation")
        self.assertEqual(entries["upgrade"]["retry"], 0)
        self.assertIsNone(entries["upgrade"]["upgrade"])
        self.assertEqual(entries["upgrade"]["final_role"], "spark")
        self.assertEqual(len(entries["upgrade"]["attempts"]), 1)

    async def test_terminal_failure_does_not_replay_or_advance_descendants(self) -> None:
        tasks = [task("combo", "FAKE_RETRY_UPGRADE_COMBO", role="spark")]
        summary = await runner.run_workflow(
            self.spec(tasks, "retry-upgrade-combo"),
            self.base / "run-retry-upgrade-combo",
            self.prefix,
            role_configs(),
        )
        entry = summary["tasks"][0]
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["retry"], 0)
        self.assertIsNone(entry["upgrade"])
        self.assertEqual(entry["final_role"], "spark")
        self.assertEqual(len(entry["attempts"]), 1)

    async def test_cancellation_writes_terminal_summary(self) -> None:
        run_dir = self.base / "run-cancelled"
        async def successful_cleanup(proc) -> None:
            proc.kill()
            await proc.wait()
            return None

        with mock.patch.object(runner, "_kill_tree", new=successful_cleanup):
            workflow = asyncio.create_task(
                runner.run_workflow(
                    self.spec([task("sleep", "FAKE_SLEEP")], "cancelled-run"),
                    run_dir,
                    self.prefix,
                    role_configs(),
                )
            )
            await asyncio.sleep(0.5)
            workflow.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await workflow
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertIsNotNone(summary["finished"])
        self.assertEqual(summary["tasks"][0]["status"], "cancelled")

    async def test_cancellation_cleanup_failure_is_failed_in_summary(self) -> None:
        run_dir = self.base / "run-cancelled-cleanup-failure"

        async def failed_cleanup(proc) -> str:
            proc.kill()
            await proc.wait()
            return "process-tree cleanup unconfirmed: fixture"

        with mock.patch.object(runner, "_kill_tree", new=failed_cleanup):
            workflow = asyncio.create_task(
                runner.run_workflow(
                    self.spec([task("sleep", "FAKE_SLEEP")], "cancelled-cleanup-failure"),
                    run_dir,
                    self.prefix,
                    role_configs(),
                )
            )
            await asyncio.sleep(0.5)
            workflow.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await workflow

        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertIsNotNone(summary["finished"])
        self.assertEqual(summary["tasks"][0]["status"], "failed")
        self.assertIn("process-tree cleanup unconfirmed", summary["tasks"][0]["error"])


if __name__ == "__main__":
    unittest.main()
