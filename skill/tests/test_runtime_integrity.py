from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from runtime.artifacts import ArtifactStore
from runtime.control_flow import ControlFlowError, TrustedControlFlowScheduler
from runtime.human_gate import HumanGateStore
from runtime.limits import ArtifactLimitError, RuntimeLimits, directory_size
from runtime.path_safety import (
    UnsafeRunPathError,
    assert_safe_run_tree,
    canonical_runtime_path,
)
from runtime.run_lease import RunLease, RunLeaseError
from runtime.state_store import RunStateStore


def limits() -> RuntimeLimits:
    return RuntimeLimits.from_mapping(
        {
            "max_result_bytes": 1024 * 1024,
            "max_log_bytes": 1024 * 1024,
            "max_run_artifact_bytes": 16 * 1024 * 1024,
            "max_upstream_inline_bytes": 128,
            "max_event_bytes": 64 * 1024,
        }
    )


def single_agent_ir() -> dict[str, Any]:
    return {
        "version": 3,
        "name": "runtime-integrity",
        "mode": "workflow",
        "objective": "prove run integrity",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 2,
            "max_concurrency": 1,
            "max_iterations": 2,
            "max_tokens": 1000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
        },
        "nodes": [
            {
                "id": "only",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "ONLY",
                    "access": "read_only",
                },
            }
        ],
    }


def gate_ir() -> dict[str, Any]:
    ir = single_agent_ir()
    ir["name"] = "lease-sequence-refresh"
    ir["nodes"].append(
        {
            "id": "approval",
            "kind": "human_gate",
            "depends_on": ["only"],
            "config": {
                "prompt": "Accept?",
                "options": ["approve", "reject"],
            },
        }
    )
    return ir


class BlockingExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[str] = []

    async def __call__(self, task, results, prior_entry):
        self.calls.append(task["id"])
        self.started.set()
        await self.release.wait()
        return {
            "id": task["id"],
            "status": "succeeded",
            "output": "ok",
            "output_artifact": None,
            "error": None,
            "attempts": [],
        }


async def successful_executor(task, results, prior_entry):
    return {
        "id": task["id"],
        "status": "succeeded",
        "output": "ok",
        "output_artifact": None,
        "error": None,
        "attempts": [],
    }


class RuntimeLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_resume_is_rejected_before_agent_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            first_executor = BlockingExecutor()
            first = TrustedControlFlowScheduler(
                single_agent_ir(),
                run_dir,
                execute_agent=first_executor,
                limits=limits(),
            )
            running = asyncio.create_task(first.run())
            await first_executor.started.wait()

            second_calls: list[str] = []

            async def second_executor(task, results, prior_entry):
                second_calls.append(task["id"])
                raise AssertionError("concurrent executor must not be dispatched")

            second = TrustedControlFlowScheduler(
                single_agent_ir(),
                run_dir,
                execute_agent=second_executor,
                limits=limits(),
            )
            with self.assertRaisesRegex(ControlFlowError, "already active"):
                await second.run(resume=True)
            self.assertEqual(second_calls, [])

            first_executor.release.set()
            summary = await running
            self.assertTrue(summary["all_succeeded"])

    async def test_lease_releases_after_normal_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            with RunLease(run_dir):
                with self.assertRaisesRegex(RunLeaseError, "already active"):
                    with RunLease(run_dir):
                        self.fail("second lease unexpectedly acquired")
            with RunLease(run_dir):
                pass

    async def test_lease_is_exclusive_across_processes(self) -> None:
        child = """
import sys
from pathlib import Path
from runtime.run_lease import RunLease

try:
    with RunLease(Path(sys.argv[1])):
        print("ACQUIRED")
except Exception as exc:
    print(type(exc).__name__)
    raise SystemExit(23)
"""
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            command = [sys.executable, "-B", "-c", child, str(run_dir)]
            with RunLease(run_dir):
                blocked = subprocess.run(
                    command,
                    cwd=SKILL_DIR,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            reacquired = subprocess.run(
                command,
                cwd=SKILL_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(blocked.returncode, 23)
            self.assertEqual(blocked.stdout.decode("utf-8").strip(), "RunLeaseError")
            self.assertEqual(
                reacquired.returncode,
                0,
                reacquired.stderr.decode("utf-8", errors="replace"),
            )
            self.assertEqual(reacquired.stdout.decode("utf-8").strip(), "ACQUIRED")

    async def test_scheduler_constructed_before_lease_refreshes_event_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            stale = TrustedControlFlowScheduler(
                gate_ir(),
                run_dir,
                execute_agent=successful_executor,
                limits=limits(),
            )
            paused = await TrustedControlFlowScheduler(
                gate_ir(),
                run_dir,
                execute_agent=successful_executor,
                limits=limits(),
            ).run()
            self.assertTrue(paused["paused"])
            store = HumanGateStore(run_dir, limits())
            waiting = store.load("approval")
            store.decide(
                "approval",
                decision="approve",
                actor="fixture",
                source="user",
                expected_input_identity=waiting["input_identity"],
            )
            completed = await stale.run(resume=True)
            self.assertTrue(completed["all_succeeded"])
            events = [
                json.loads(line)
                for line in (run_dir / "events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [event["sequence"] for event in events],
                list(range(1, len(events) + 1)),
            )


class RuntimeReparseTests(unittest.TestCase):
    def test_recursive_scan_rejects_simulated_reparse_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            unsafe = run_dir / "tasks" / "only"
            unsafe.mkdir(parents=True)
            unsafe = canonical_runtime_path(
                unsafe, label="simulated unsafe descendant"
            )
            with mock.patch(
                "runtime.path_safety.is_reparse",
                side_effect=lambda path: Path(path) == unsafe,
            ):
                with self.assertRaisesRegex(UnsafeRunPathError, "reparse point"):
                    assert_safe_run_tree(run_dir)

    def test_artifact_and_state_writes_recheck_reparse_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            artifacts = run_dir / "artifacts"
            artifacts.mkdir()
            store = ArtifactStore(run_dir, limits())
            with mock.patch(
                "runtime.path_safety.is_reparse",
                side_effect=lambda path: Path(path) == artifacts,
            ):
                with self.assertRaisesRegex(ArtifactLimitError, "reparse point"):
                    store.put_json("only", {"value": "blocked"})
            self.assertEqual(list(artifacts.iterdir()), [])

            state = RunStateStore(run_dir, max_event_bytes=4096)
            events = run_dir / "events.jsonl"
            events.write_bytes(b"")
            with mock.patch(
                "runtime.path_safety.is_reparse",
                side_effect=lambda path: Path(path) == events,
            ):
                with self.assertRaisesRegex(UnsafeRunPathError, "reparse point"):
                    state.append_event("blocked", {})
            self.assertEqual(events.read_bytes(), b"")

    def test_checkpoint_temporary_reparse_is_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            store = RunStateStore(run_dir, max_event_bytes=4096)
            temporary_path = run_dir / "checkpoint.json.tmp"
            temporary_path.write_bytes(b"unchanged")
            with mock.patch(
                "runtime.path_safety.is_reparse",
                side_effect=lambda path: Path(path) == temporary_path,
            ):
                with self.assertRaisesRegex(UnsafeRunPathError, "reparse point"):
                    store.write_checkpoint({"runtime": "fixture"})
            self.assertEqual(temporary_path.read_bytes(), b"unchanged")
            self.assertFalse((run_dir / "checkpoint.json").exists())

    def test_directory_size_rejects_reparse_root_before_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch(
                "runtime.path_safety.is_reparse",
                side_effect=lambda path: Path(path) == root,
            ):
                with self.assertRaisesRegex(ArtifactLimitError, "reparse point"):
                    directory_size(root)


class CompletionSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_snapshot_observes_matching_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scheduler = TrustedControlFlowScheduler(
                single_agent_ir(),
                Path(temporary) / "run",
                execute_agent=BlockingExecutor(),
                limits=limits(),
            )
            scheduler.run_dir.mkdir()
            scheduler.started = "fixture"
            node = scheduler.node_by_id["only"]
            entry = {
                "id": "only",
                "kind": "agent",
                "status": "succeeded",
                "depends_on": [],
                "dependency_policy": "all_succeeded",
                "started": "fixture",
                "finished": "fixture",
                "output": None,
                "output_artifact": None,
                "error": None,
                "resume_count": 0,
            }
            scheduler.entries = {"only": entry}
            scheduler.states = {"only": "running"}
            observed: list[tuple[str, str]] = []

            def inspect_snapshot() -> None:
                observed.append(
                    (
                        scheduler.states["only"],
                        scheduler.entries["only"]["status"],
                    )
                )

            scheduler._snapshot_locked = inspect_snapshot  # type: ignore[method-assign]
            await scheduler._record_node_completed(node, entry)
            self.assertEqual(observed, [("succeeded", "succeeded")])

    async def test_completion_event_append_failure_does_not_publish_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            scheduler = TrustedControlFlowScheduler(
                single_agent_ir(),
                run_dir,
                execute_agent=successful_executor,
                limits=limits(),
            )
            original_append = RunStateStore.append_event
            failed_once = False

            def fail_completion_once(store, event_type, payload):
                nonlocal failed_once
                if event_type == "workflow.node.completed" and not failed_once:
                    failed_once = True
                    raise RuntimeError("injected completion journal failure")
                return original_append(store, event_type, payload)

            with mock.patch.object(
                RunStateStore, "append_event", new=fail_completion_once
            ):
                summary = await scheduler.run()

            self.assertTrue(failed_once)
            self.assertEqual(scheduler.completed_node_events, set())
            self.assertEqual(scheduler.states["only"], "failed")
            self.assertEqual(scheduler.entries["only"]["status"], "failed")
            self.assertIn(
                "runtime internal error: RuntimeError: injected completion journal failure",
                scheduler.entries["only"]["error"],
            )
            self.assertEqual(summary["failed_count"], 1)
            events = [
                json.loads(line)
                for line in (run_dir / "events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertFalse(
                any(event["type"] == "workflow.node.completed" for event in events)
            )


class Utf8EntrypointTests(unittest.TestCase):
    @staticmethod
    def _cp936_env(runs_root: Path) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("PYTHONPYCACHEPREFIX", None)
        env["PYTHONIOENCODING"] = "cp936"
        env["PYTHONUTF8"] = "0"
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["DYNWF_RUNS_ROOT"] = str(runs_root)
        return env

    def test_top_level_cli_overrides_cp936_for_utf8_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            spec = single_agent_ir()
            spec["objective"] = "Windows UTF-8 验收 — 完整"
            spec_path = Path(temporary) / "workflow.json"
            spec_path.write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
            env = self._cp936_env(Path(temporary))
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SKILL_DIR / "cli.py"),
                    "plan-ir",
                    "--spec",
                    str(spec_path),
                ],
                cwd=SKILL_DIR,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("utf-8"),
            )
            output = completed.stdout.decode("utf-8")
            self.assertIn("Windows UTF-8 验收 — 完整", output)

    def test_public_entrypoints_emit_utf8_stdout_and_stderr_under_cp936(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "缺失🧪.json"
            env = self._cp936_env(root)
            cases = {
                "auto-planner": [
                    SKILL_DIR / "auto_planner.py",
                    "auto-plan-apply",
                    "--selection",
                    missing,
                    "--objective",
                    "fixture",
                    "--workdir",
                    root,
                ],
                "operations": [
                    SKILL_DIR / "ops_cli.py",
                    "plan-ir",
                    "--spec",
                    missing,
                ],
                "gate": [
                    SKILL_DIR / "gate_cli.py",
                    "gate-status",
                    "--run-dir",
                    root / "缺失🧪run",
                ],
                "workflow-ir": [
                    SKILL_DIR / "ir_runner.py",
                    "resume-ir",
                    "--run-dir",
                    root / "缺失🧪run",
                    "--allowed-root",
                    root,
                    "--ack-external-model-export",
                ],
                "legacy-runner": [
                    SKILL_DIR / "runner.py",
                    "validate-ir",
                    "--spec",
                    missing,
                ],
                "swarm-presets": [
                    SKILL_DIR / "swarm_presets.py",
                    "preset-ir",
                    "--preset",
                    "design-swarm",
                    "--objective",
                    "设计🧪✓",
                    "--workdir",
                    root,
                ],
                "policy-consistency": [
                    SKILL_DIR / "scripts" / "check_policy_consistency.py",
                    "--root",
                    root / "缺失🧪root",
                    "--json",
                ],
                "routing-smoke": [
                    SKILL_DIR / "scripts" / "routing_smoke.py",
                    "--case",
                    "root-plus-luna",
                    "--transcript",
                    missing,
                ],
            }
            for label, arguments in cases.items():
                with self.subTest(entrypoint=label):
                    completed = subprocess.run(
                        [sys.executable, "-B", *map(str, arguments)],
                        cwd=SKILL_DIR,
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=30,
                        check=False,
                    )
                    output = completed.stdout.decode("utf-8")
                    error = completed.stderr.decode("utf-8")
                    self.assertIn("🧪", output + error)


if __name__ == "__main__":
    unittest.main()
