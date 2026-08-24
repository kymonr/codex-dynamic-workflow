from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import ir_runner
from runtime.control_flow import ControlFlowError, TrustedControlFlowScheduler
from runtime.human_gate import HumanGateStore
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import (
    VERIFICATION_RESULT_SCHEMA,
    WorkflowIRValidationError,
    validate_workflow_ir,
)


class ManualClock:
    def __init__(self, epoch_ms: int = 1_000) -> None:
        self.now = epoch_ms
        self.waiters: list[tuple[int, asyncio.Future[None]]] = []

    def epoch_ms(self) -> int:
        return self.now

    async def wait_until(self, deadline_epoch_ms: int) -> None:
        if self.now >= deadline_epoch_ms:
            return
        future = asyncio.get_running_loop().create_future()
        item = (deadline_epoch_ms, future)
        self.waiters.append(item)
        try:
            await future
        finally:
            if item in self.waiters:
                self.waiters.remove(item)

    def advance(self, milliseconds: int) -> None:
        self.now += milliseconds
        for deadline, future in list(self.waiters):
            if self.now >= deadline and not future.done():
                future.set_result(None)


def deadline_ir(*, gate: bool = False, independent: bool = False) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "first",
            "kind": "agent",
            "depends_on": [],
            "config": {
                "profile": "luna",
                "prompt": "FIRST",
                "access": "read_only",
            },
        }
    ]
    if gate:
        nodes.extend(
            [
                {
                    "id": "approval",
                    "kind": "human_gate",
                    "depends_on": ["first"],
                    "config": {
                        "prompt": "Continue?",
                        "options": ["approve", "reject"],
                    },
                },
                {
                    "id": "second",
                    "kind": "agent",
                    "depends_on": ["approval"],
                    "config": {
                        "profile": "luna",
                        "prompt": "SECOND",
                        "access": "read_only",
                    },
                },
            ]
        )
    else:
        nodes.append(
            {
                "id": "second",
                "kind": "agent",
                "depends_on": [] if independent else ["first"],
                "config": {
                    "profile": "luna",
                    "prompt": "SECOND",
                    "access": "read_only",
                },
            }
        )
    return {
        "version": 3,
        "name": "deadline-test",
        "mode": "workflow",
        "objective": "exercise an absolute whole-workflow deadline",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 4,
            "max_concurrency": 2,
            "max_iterations": 3,
            "max_tokens": 100_000,
            "soft_timeout_seconds": 900,
            "hard_timeout_seconds": 3600,
            "workflow_timeout_seconds": 60,
        },
        "nodes": nodes,
    }


class ImmediateExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.tasks: list[dict[str, Any]] = []

    async def __call__(self, task, results, prior_entry):
        self.calls.append(task["id"])
        self.tasks.append(task)
        return {
            "id": task["id"],
            "status": "succeeded",
            "output": {"value": task["id"]},
            "output_artifact": None,
            "error": None,
            "attempts": [],
        }


class BlockingExecutor:
    def __init__(self, expected_starts: int = 1) -> None:
        self.expected_starts = expected_starts
        self.calls: list[str] = []
        self.started = asyncio.Event()
        self.cleaned: set[str] = set()

    async def __call__(self, task, results, prior_entry):
        self.calls.append(task["id"])
        if len(self.calls) >= self.expected_starts:
            self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cleaned.add(task["id"])
            raise


class CleanupOutcomeExecutor:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls: list[str] = []
        self.started = asyncio.Event()

    async def __call__(self, task, results, prior_entry):
        self.calls.append(task["id"])
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            if self.mode == "raise":
                raise RuntimeError("cleanup fixture failed")
            return {
                "id": task["id"],
                "status": "succeeded",
                "output": {"late": True},
                "output_artifact": None,
                "error": None,
                "attempts": [],
            }


class JumpClock(ManualClock):
    def __init__(self) -> None:
        super().__init__(1_000)
        self.reads = 0

    def epoch_ms(self) -> int:
        self.reads += 1
        return 1_000 if self.reads == 1 else 61_000


class LoopDeadlineExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.child_started = asyncio.Event()
        self.cleaned = False

    async def __call__(self, task, results, prior_entry):
        self.calls.append(task["id"])
        if task["id"] == "initial":
            return {
                "id": "initial",
                "status": "succeeded",
                "output": "initial",
                "output_artifact": None,
                "error": None,
                "attempts": [],
            }
        self.child_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cleaned = True
            raise


def loop_deadline_ir() -> dict[str, Any]:
    return {
        "version": 3,
        "name": "loop-deadline-test",
        "mode": "workflow",
        "objective": "cancel one active bounded loop child at the deadline",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 3,
            "max_concurrency": 1,
            "max_iterations": 1,
            "max_tokens": 100_000,
            "soft_timeout_seconds": 900,
            "hard_timeout_seconds": 3600,
            "workflow_timeout_seconds": 60,
        },
        "nodes": [
            {
                "id": "initial",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "INITIAL",
                    "access": "read_only",
                },
            },
            {
                "id": "converge",
                "kind": "loop",
                "depends_on": ["initial"],
                "config": {
                    "max_iterations": 1,
                    "body": ["revise-template", "verify-template"],
                    "stop_when": "verification_accept",
                },
            },
            {
                "id": "revise-template",
                "kind": "agent",
                "depends_on": ["converge"],
                "config": {
                    "profile": "luna",
                    "prompt": "REVISE {{loop_state}}",
                    "access": "read_only",
                },
            },
            {
                "id": "verify-template",
                "kind": "agent",
                "depends_on": ["converge"],
                "config": {
                    "profile": "luna",
                    "prompt": "VERIFY {{loop_state}}",
                    "access": "read_only",
                    "output_schema": VERIFICATION_RESULT_SCHEMA,
                },
            },
        ],
    }


class WorkflowDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.limits = RuntimeLimits.from_mapping(
            {
                "max_result_bytes": 1024 * 1024,
                "max_log_bytes": 1024 * 1024,
                "max_run_artifact_bytes": 32 * 1024 * 1024,
                "max_upstream_inline_bytes": 256,
                "max_event_bytes": 64 * 1024,
            }
        )

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_deadline_cancels_current_call_and_blocks_following_call(self) -> None:
        clock = ManualClock()
        executor = BlockingExecutor()
        run_dir = self.base / "cancel"
        scheduler = TrustedControlFlowScheduler(
            deadline_ir(),
            run_dir,
            execute_agent=executor,
            limits=self.limits,
            clock=clock,
        )
        running = asyncio.create_task(scheduler.run())
        await executor.started.wait()
        clock.advance(60_000)
        summary = await running
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(states["first"], "needs_escalation")
        self.assertEqual(states["second"], "blocked")
        self.assertEqual(executor.calls, ["first"])
        self.assertEqual(executor.cleaned, {"first"})
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.deadline.exceeded" for event in events),
            1,
        )

    async def test_concurrent_deadline_records_one_event_and_waits_for_cleanup(self) -> None:
        clock = ManualClock()
        executor = BlockingExecutor(expected_starts=2)
        run_dir = self.base / "concurrent"
        scheduler = TrustedControlFlowScheduler(
            deadline_ir(independent=True),
            run_dir,
            execute_agent=executor,
            limits=self.limits,
            clock=clock,
        )
        running = asyncio.create_task(scheduler.run())
        await executor.started.wait()
        clock.advance(60_000)
        summary = await running
        self.assertEqual(summary["needs_escalation_count"], 2)
        self.assertEqual(executor.cleaned, {"first", "second"})
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.deadline.exceeded" for event in events),
            1,
        )

    async def test_resume_reuses_absolute_deadline_and_gate_pause_counts(self) -> None:
        clock = ManualClock()
        first = ImmediateExecutor()
        raw = deadline_ir(gate=True)
        run_dir = self.base / "pause"
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=first,
            limits=self.limits,
            clock=clock,
        )
        paused = await scheduler.run()
        self.assertTrue(paused["paused"])
        self.assertEqual(paused["workflow_deadline"]["deadline_epoch_ms"], 61_000)
        gate = next(node for node in paused["nodes"] if node["id"] == "approval")
        HumanGateStore(run_dir, self.limits).decide(
            "approval",
            decision="approve",
            actor="fixture",
            source="user",
            expected_input_identity=gate["gate"]["input_identity"],
        )
        clock.advance(30_000)
        second = ImmediateExecutor()
        resumed = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=second,
            limits=self.limits,
            clock=clock,
        )
        final = await resumed.run(resume=True)
        self.assertTrue(final["all_succeeded"])
        self.assertEqual(final["workflow_deadline"]["deadline_epoch_ms"], 61_000)
        self.assertEqual(second.calls, ["second"])
        runtime = second.tasks[0]["_runtime"]
        self.assertEqual(runtime["soft_timeout_seconds"], 30)
        self.assertEqual(runtime["hard_timeout_seconds"], 30)

    async def test_expired_gate_resume_does_not_dispatch_pending_agent(self) -> None:
        clock = ManualClock()
        raw = deadline_ir(gate=True)
        run_dir = self.base / "expired-pause"
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=ImmediateExecutor(),
            limits=self.limits,
            clock=clock,
        )
        paused = await scheduler.run()
        gate = next(node for node in paused["nodes"] if node["id"] == "approval")
        HumanGateStore(run_dir, self.limits).decide(
            "approval",
            decision="approve",
            actor="fixture",
            source="user",
            expected_input_identity=gate["gate"]["input_identity"],
        )
        clock.advance(60_001)
        executor = ImmediateExecutor()
        resumed = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=executor,
            limits=self.limits,
            clock=clock,
        )
        final = await resumed.run(resume=True)
        second = next(node for node in final["nodes"] if node["id"] == "second")
        approval = next(node for node in final["nodes"] if node["id"] == "approval")
        self.assertEqual(approval["status"], "needs_escalation")
        self.assertEqual(second["status"], "needs_escalation")
        self.assertEqual(executor.calls, [])
        self.assertEqual(final["claimed_agent_count"], 1)
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.deadline.exceeded" for event in events),
            1,
        )

    async def test_deadline_pre_dispatch_creates_no_claim_or_task_artifact(self) -> None:
        executor = ImmediateExecutor()
        run_dir = self.base / "pre-dispatch"
        summary = await TrustedControlFlowScheduler(
            deadline_ir(),
            run_dir,
            execute_agent=executor,
            limits=self.limits,
            clock=JumpClock(),
        ).run()
        self.assertEqual(executor.calls, [])
        self.assertEqual(summary["claimed_agent_count"], 0)
        self.assertEqual(summary["needs_escalation_count"], 2)
        self.assertEqual(list((run_dir / "tasks").iterdir()), [])
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.deadline.exceeded" for event in events),
            1,
        )

    async def test_deadline_preserves_cancellation_cleanup_outcome(self) -> None:
        for mode, expected in (
            ("raise", "failed"),
            ("return", "returned_after_deadline"),
        ):
            with self.subTest(mode=mode):
                clock = ManualClock()
                executor = CleanupOutcomeExecutor(mode)
                run_dir = self.base / f"cleanup-{mode}"
                scheduler = TrustedControlFlowScheduler(
                    deadline_ir(),
                    run_dir,
                    execute_agent=executor,
                    limits=self.limits,
                    clock=clock,
                )
                running = asyncio.create_task(scheduler.run())
                await executor.started.wait()
                clock.advance(60_000)
                summary = await running
                first = next(
                    node for node in summary["nodes"] if node["id"] == "first"
                )
                self.assertEqual(first["status"], "needs_escalation")
                self.assertEqual(
                    first["agent_entry"]["cancellation_cleanup"]["status"],
                    expected,
                )
                if mode == "raise":
                    self.assertIn(
                        "cleanup fixture failed",
                        first["agent_entry"]["cancellation_cleanup"]["error"],
                    )

    async def test_deadline_snapshot_failure_does_not_duplicate_event(self) -> None:
        clock = ManualClock()
        executor = BlockingExecutor()
        run_dir = self.base / "snapshot-failure"
        scheduler = TrustedControlFlowScheduler(
            deadline_ir(),
            run_dir,
            execute_agent=executor,
            limits=self.limits,
            clock=clock,
        )
        original = scheduler._snapshot_locked
        failed_once = False

        def fail_after_deadline_event_once():
            nonlocal failed_once
            if scheduler.deadline_exceeded_recorded and not failed_once:
                failed_once = True
                raise OSError("snapshot fixture failed")
            original()

        scheduler._snapshot_locked = fail_after_deadline_event_once  # type: ignore[method-assign]
        running = asyncio.create_task(scheduler.run())
        await executor.started.wait()
        clock.advance(60_000)
        await running
        await scheduler._record_deadline_exceeded("second-attempt")
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.deadline.exceeded" for event in events),
            1,
        )

    async def test_deadline_cancels_loop_child_and_never_starts_verifier(self) -> None:
        clock = ManualClock()
        executor = LoopDeadlineExecutor()
        run_dir = self.base / "loop-child"
        running = asyncio.create_task(
            TrustedControlFlowScheduler(
                loop_deadline_ir(),
                run_dir,
                execute_agent=executor,
                limits=self.limits,
                clock=clock,
            ).run()
        )
        await executor.child_started.wait()
        clock.advance(60_000)
        summary = await running
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["status"], "needs_escalation")
        self.assertEqual(loop["stop_reason"], "step_needs_escalation")
        self.assertTrue(executor.cleaned)
        self.assertEqual(len(executor.calls), 2)
        self.assertEqual(summary["claimed_agent_count"], 2)
        manifest = loop["output"]
        if isinstance(manifest, dict) and "$artifact" in manifest:
            from runtime.artifacts import ArtifactStore

            manifest = ArtifactStore(run_dir, self.limits).load_json(
                manifest, expected_task_id="converge"
            )
        self.assertFalse(manifest["converged"])
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.deadline.exceeded" for event in events),
            1,
        )
        self.assertEqual(
            sum(event["type"] == "workflow.loop.stopped" for event in events), 1
        )

    async def test_loop_step_boundary_deadline_crash_resumes_without_dispatch(self) -> None:
        clock = ManualClock()
        raw = loop_deadline_ir()
        run_dir = self.base / "loop-step-boundary-crash"
        first = LoopDeadlineExecutor()
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=first,
            limits=self.limits,
            clock=clock,
        )
        original_event = scheduler._event

        async def advance_after_iteration_started(event_type, payload):
            await original_event(event_type, payload)
            if event_type == "workflow.loop.iteration.started":
                clock.advance(60_000)

        scheduler._event = advance_after_iteration_started  # type: ignore[method-assign]
        original_deadline = scheduler._record_deadline_exceeded
        interrupted = False

        async def interrupt_before_deadline_event(context_id):
            nonlocal interrupted
            if context_id == "converge" and not interrupted:
                interrupted = True
                raise asyncio.CancelledError()
            await original_deadline(context_id)

        scheduler._record_deadline_exceeded = (  # type: ignore[method-assign]
            interrupt_before_deadline_event
        )
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()

        checkpoint = json.loads(
            (run_dir / "checkpoint.json").read_text(encoding="utf-8")
        )
        loop_entry = checkpoint["entries"]["converge"]
        self.assertEqual(loop_entry["status"], "needs_escalation")
        self.assertEqual(loop_entry["stop_reason"], "workflow_deadline")
        self.assertEqual(
            {child["status"] for child in loop_entry["children"].values()},
            {"pending"},
        )
        child_ids = set(loop_entry["children"])
        self.assertTrue(child_ids.isdisjoint(checkpoint["claimed_agents"]))
        for child_id, child in loop_entry["children"].items():
            self.assertNotIn("agent_entry", child)
            self.assertIsNone(child["input_artifact"])
            self.assertFalse((run_dir / "tasks" / child_id).exists())

        second = ImmediateExecutor()
        final = await TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=second,
            limits=self.limits,
            clock=clock,
        ).run(resume=True)
        resumed_loop = next(
            node for node in final["nodes"] if node["id"] == "converge"
        )
        self.assertEqual(resumed_loop["status"], "needs_escalation")
        self.assertEqual(resumed_loop["stop_reason"], "workflow_deadline")
        self.assertEqual(second.calls, [])
        self.assertEqual(final["claimed_agent_count"], 1)
        events_path = run_dir / "events.jsonl"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        deadline_events = [
            event
            for event in events
            if event["type"] == "workflow.deadline.exceeded"
        ]
        self.assertEqual(len(deadline_events), 1)
        self.assertEqual(deadline_events[0]["payload"]["agent_id"], "converge")
        self.assertEqual(
            sum(event["type"] == "workflow.loop.stopped" for event in events),
            1,
        )

        evidence_paths = (
            run_dir / "summary.json",
            run_dir / "checkpoint.json",
            events_path,
        )
        before_validation = {
            path: path.read_bytes() for path in evidence_paths
        }
        validator_executor = ImmediateExecutor()
        validator = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=validator_executor,
            limits=self.limits,
            clock=clock,
        )
        validator._restore()
        self.assertEqual(validator_executor.calls, [])
        self.assertEqual(
            {path: path.read_bytes() for path in evidence_paths},
            before_validation,
        )

    async def test_scheduler_boundary_loop_deadline_resume_is_self_consistent(self) -> None:
        raw = loop_deadline_ir()
        run_dir = self.base / "scheduler-boundary-loop"
        first = LoopDeadlineExecutor()
        clock = JumpClock()
        summary = await TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=first,
            limits=self.limits,
            clock=clock,
        ).run()
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["status"], "needs_escalation")
        self.assertEqual(loop["stop_reason"], "workflow_deadline")
        self.assertIsNone(loop["started"])
        self.assertEqual(loop["children"], {})
        self.assertEqual(loop["iteration_records"], [])
        self.assertEqual(first.calls, [])
        self.assertEqual(summary["claimed_agent_count"], 0)
        self.assertEqual(list((run_dir / "tasks").iterdir()), [])

        checkpoint_path = run_dir / "checkpoint.json"
        summary_path = run_dir / "summary.json"
        events_path = run_dir / "events.jsonl"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["claimed_agents"], [])
        self.assertIsNone(checkpoint["entries"]["initial"]["output_artifact"])
        self.assertIsNotNone(checkpoint["entries"]["converge"]["output_artifact"])
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.deadline.exceeded" for event in events),
            1,
        )
        self.assertEqual(
            sum(event["type"] == "workflow.loop.stopped" for event in events),
            1,
        )
        self.assertFalse(
            any(
                event["type"] in {
                    "workflow.node.started",
                    "workflow.node.completed",
                }
                and event["payload"].get("node_id") == "converge"
                for event in events
            )
        )

        second = ImmediateExecutor()
        final = await TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=second,
            limits=self.limits,
            clock=clock,
        ).run(resume=True)
        final_loop = next(
            node for node in final["nodes"] if node["id"] == "converge"
        )
        self.assertEqual(final_loop["status"], "needs_escalation")
        self.assertEqual(final_loop["stop_reason"], "workflow_deadline")
        self.assertEqual(second.calls, [])
        after_resume = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(
                event["type"] == "workflow.deadline.exceeded"
                for event in after_resume
            ),
            1,
        )
        self.assertEqual(
            sum(event["type"] == "workflow.loop.stopped" for event in after_resume),
            1,
        )
        self.assertFalse(
            any(
                event["type"] == "workflow.node.completed"
                and event["payload"].get("node_id") == "converge"
                for event in after_resume
            )
        )

        evidence_paths = (summary_path, checkpoint_path, events_path)
        before_validation = {
            path: path.read_bytes() for path in evidence_paths
        }
        validator_executor = ImmediateExecutor()
        validator = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=validator_executor,
            limits=self.limits,
            clock=clock,
        )
        validator._restore()
        self.assertEqual(validator_executor.calls, [])
        self.assertEqual(
            {path: path.read_bytes() for path in evidence_paths},
            before_validation,
        )

    async def test_resume_rejects_deadline_tamper_and_clock_rollback(self) -> None:
        raw = deadline_ir(gate=True)
        for label in ("tamper", "rollback"):
            with self.subTest(label=label):
                clock = ManualClock()
                run_dir = self.base / label
                scheduler = TrustedControlFlowScheduler(
                    raw,
                    run_dir,
                    execute_agent=ImmediateExecutor(),
                    limits=self.limits,
                    clock=clock,
                )
                await scheduler.run()
                if label == "tamper":
                    checkpoint_path = run_dir / "checkpoint.json"
                    summary_path = run_dir / "summary.json"
                    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    checkpoint["workflow_deadline_epoch_ms"] += 1
                    summary["workflow_deadline"]["deadline_epoch_ms"] += 1
                    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
                    summary_path.write_text(json.dumps(summary), encoding="utf-8")
                else:
                    clock.now = 999
                executor = ImmediateExecutor()
                resumed = TrustedControlFlowScheduler(
                    raw,
                    run_dir,
                    execute_agent=executor,
                    limits=self.limits,
                    clock=clock,
                )
                with self.assertRaises(ControlFlowError):
                    await resumed.run(resume=True)
                self.assertEqual(executor.calls, [])

    async def test_resume_rejects_deadline_event_payload_tamper_before_rewrite(self) -> None:
        def mutate_deadline(payload: dict[str, Any]) -> None:
            payload["workflow_deadline_epoch_ms"] += 1

        def mutate_agent_type(payload: dict[str, Any]) -> None:
            payload["agent_id"] = 1

        def mutate_agent_identity(payload: dict[str, Any]) -> None:
            payload["agent_id"] = "unknown-agent"

        def add_key(payload: dict[str, Any]) -> None:
            payload["extra"] = True

        def remove_key(payload: dict[str, Any]) -> None:
            payload.pop("agent_id")

        mutations = {
            "deadline": mutate_deadline,
            "agent-type": mutate_agent_type,
            "agent-identity": mutate_agent_identity,
            "extra-key": add_key,
            "missing-key": remove_key,
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                raw = deadline_ir()
                run_dir = self.base / f"deadline-event-{label}"
                await TrustedControlFlowScheduler(
                    raw,
                    run_dir,
                    execute_agent=ImmediateExecutor(),
                    limits=self.limits,
                    clock=JumpClock(),
                ).run()
                events_path = run_dir / "events.jsonl"
                checkpoint_path = run_dir / "checkpoint.json"
                summary_path = run_dir / "summary.json"
                events = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                ]
                deadline_event = next(
                    event
                    for event in events
                    if event["type"] == "workflow.deadline.exceeded"
                )
                mutate(deadline_event["payload"])
                events_path.write_text(
                    "".join(
                        json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
                        for event in events
                    ),
                    encoding="utf-8",
                )
                before = {
                    path: path.read_bytes()
                    for path in (events_path, checkpoint_path, summary_path)
                }
                executor = ImmediateExecutor()
                with self.assertRaisesRegex(
                    ControlFlowError,
                    "workflow deadline event payload does not match checkpoint",
                ):
                    await TrustedControlFlowScheduler(
                        raw,
                        run_dir,
                        execute_agent=executor,
                        limits=self.limits,
                        clock=ManualClock(61_000),
                    ).run(resume=True)
                self.assertEqual(executor.calls, [])
                self.assertEqual(
                    {
                        path: path.read_bytes()
                        for path in (events_path, checkpoint_path, summary_path)
                    },
                    before,
                )

    async def test_resume_rejects_missing_typed_extended_and_rollback_deadline_evidence(self) -> None:
        for label in ("missing", "typed", "extended", "rollback-after-start"):
            with self.subTest(label=label):
                raw = deadline_ir(gate=True)
                clock = ManualClock()
                run_dir = self.base / f"deadline-evidence-{label}"
                await TrustedControlFlowScheduler(
                    raw,
                    run_dir,
                    execute_agent=ImmediateExecutor(),
                    limits=self.limits,
                    clock=clock,
                ).run()
                checkpoint_path = run_dir / "checkpoint.json"
                summary_path = run_dir / "summary.json"
                checkpoint = json.loads(
                    checkpoint_path.read_text(encoding="utf-8")
                )
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if label == "missing":
                    checkpoint.pop("workflow_last_observed_epoch_ms")
                elif label == "typed":
                    checkpoint["workflow_last_observed_epoch_ms"] = "1000"
                    summary["workflow_deadline"]["last_observed_epoch_ms"] = "1000"
                elif label == "extended":
                    checkpoint["workflow_deadline_epoch_ms"] += 1_000
                    summary["workflow_deadline"]["deadline_epoch_ms"] += 1_000
                else:
                    checkpoint["workflow_last_observed_epoch_ms"] = 30_000
                    summary["workflow_deadline"]["last_observed_epoch_ms"] = 30_000
                    clock.now = 20_000
                checkpoint_path.write_text(
                    json.dumps(checkpoint), encoding="utf-8"
                )
                summary_path.write_text(json.dumps(summary), encoding="utf-8")
                executor = ImmediateExecutor()
                with self.assertRaises(ControlFlowError):
                    await TrustedControlFlowScheduler(
                        raw,
                        run_dir,
                        execute_agent=executor,
                        limits=self.limits,
                        clock=clock,
                    ).run(resume=True)
                self.assertEqual(executor.calls, [])

    async def test_ir_runner_strips_private_metadata_before_legacy_boundary(self) -> None:
        clock = ManualClock()
        raw = deadline_ir()
        raw["nodes"] = raw["nodes"][:1]
        captured: dict[str, Any] = {}

        async def fake_execute(task, **kwargs):
            captured["task"] = task
            captured["soft_timeout"] = kwargs["soft_timeout"]
            captured["hard_timeout"] = kwargs["hard_timeout"]
            return {
                "id": task["id"],
                "status": "succeeded",
                "output": {"ok": True},
                "output_artifact": None,
                "error": None,
                "attempts": [],
            }

        with mock.patch.object(ir_runner.legacy, "_execute_task", side_effect=fake_execute):
            summary = await ir_runner._run(
                validate_workflow_ir(raw),
                self.base / "adapter",
                resume=False,
                codex_prefix=["codex"],
                role_configs={"luna": {}},
                preflight={},
                limits=self.limits,
                clock=clock,
            )
        self.assertTrue(summary["all_succeeded"])
        self.assertNotIn("_runtime", captured["task"])
        self.assertEqual(captured["soft_timeout"], 60)
        self.assertEqual(captured["hard_timeout"], 60)


class WorkflowDeadlineValidationTests(unittest.TestCase):
    def test_optional_budget_is_strict_and_omission_preserves_old_shape(self) -> None:
        legacy_raw = {
            "version": 3,
            "name": "deadline-test",
            "mode": "workflow",
            "objective": "exercise an absolute whole-workflow deadline",
            "workdir": "/bounded/work",
            "budgets": {
                "max_agents": 4,
                "max_concurrency": 2,
                "max_iterations": 3,
                "max_tokens": 100_000,
                "soft_timeout_seconds": 900,
                "hard_timeout_seconds": 3600,
            },
            "nodes": [
                {
                    "id": "first",
                    "kind": "agent",
                    "depends_on": [],
                    "config": {
                        "profile": "luna",
                        "prompt": "FIRST",
                        "access": "read_only",
                    },
                },
                {
                    "id": "second",
                    "kind": "agent",
                    "depends_on": ["first"],
                    "config": {
                        "profile": "luna",
                        "prompt": "SECOND",
                        "access": "read_only",
                    },
                },
            ],
        }
        expected_normalized = {
            "version": 3,
            "name": "deadline-test",
            "mode": "workflow",
            "objective": "exercise an absolute whole-workflow deadline",
            "workdir": "/bounded/work",
            "budgets": {
                "max_agents": 4,
                "max_concurrency": 2,
                "max_iterations": 3,
                "max_tokens": 100_000,
                "soft_timeout_seconds": 900,
                "hard_timeout_seconds": 3600,
            },
            "limits": {},
            "nodes": [
                {
                    "id": "first",
                    "kind": "agent",
                    "depends_on": [],
                    "dependency_policy": "all_succeeded",
                    "config": {
                        "profile": "luna",
                        "prompt": "FIRST",
                        "access": "read_only",
                        "route_reason": "Workflow IR v3 trusted agent node",
                        "output_schema": None,
                    },
                },
                {
                    "id": "second",
                    "kind": "agent",
                    "depends_on": ["first"],
                    "dependency_policy": "all_succeeded",
                    "config": {
                        "profile": "luna",
                        "prompt": "SECOND",
                        "access": "read_only",
                        "route_reason": "Workflow IR v3 trusted agent node",
                        "output_schema": None,
                    },
                },
            ],
            "execution": {
                "static_v2_compilable": True,
                "trusted_runtime_executable": True,
                "dynamic_node_kinds": [],
                "unsupported_node_kinds": [],
                "runtime_version_required": 2,
            },
        }
        normalized = validate_workflow_ir(legacy_raw)
        self.assertEqual(normalized, expected_normalized)
        digest_payload = {
            key: normalized[key]
            for key in (
                "version",
                "name",
                "mode",
                "objective",
                "workdir",
                "budgets",
                "limits",
                "nodes",
            )
        }
        digest = hashlib.sha256(
            json.dumps(
                digest_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            digest,
            "a815695de2fe7c15f4066c302272ff4343b60abd630a41e3ce29299f16b5d099",
        )
        for value in (True, 59, 172_801):
            raw = deadline_ir()
            raw["budgets"]["workflow_timeout_seconds"] = value
            with self.subTest(value=value), self.assertRaises(WorkflowIRValidationError):
                validate_workflow_ir(raw)


if __name__ == "__main__":
    unittest.main()
