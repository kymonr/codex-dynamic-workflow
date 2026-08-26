from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import ops_cli
from runtime.artifacts import ArtifactStore, substitute_upstream_results
from runtime.control_flow import (
    AgentBudgetError,
    ControlFlowError,
    LOOP_TEMPLATE_SKIP_REASON,
    TrustedControlFlowScheduler,
)
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import (
    VERIFICATION_RESULT_SCHEMA,
    WorkflowIRValidationError,
    bounded_loop_child_id,
    bounded_loop_state_id,
    project_agent_claims,
    validate_workflow_ir,
)


def bounded_ir(
    *,
    max_iterations: int = 2,
    no_progress_limit: int | None = 1,
    max_agents: int = 6,
) -> dict[str, Any]:
    loop_config: dict[str, Any] = {
        "max_iterations": max_iterations,
        "body": ["revise-template", "verify-template"],
        "stop_when": "verification_accept",
    }
    if no_progress_limit is not None:
        loop_config["no_progress_limit"] = no_progress_limit
    return {
        "version": 3,
        "name": "bounded-loop-test",
        "mode": "workflow",
        "objective": "exercise a finite trusted convergence loop",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": max_agents,
            "max_concurrency": 2,
            "max_iterations": max_iterations,
            "max_tokens": 100_000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
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
                "config": loop_config,
            },
            {
                "id": "revise-template",
                "kind": "agent",
                "depends_on": ["converge"],
                "config": {
                    "profile": "luna",
                    "prompt": "REVISE ITER={{iteration}} STATE={{loop_state}}",
                    "access": "read_only",
                    "output_schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "candidate": {"type": "string"},
                            "changes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["candidate", "changes"],
                    },
                },
            },
            {
                "id": "verify-template",
                "kind": "agent",
                "depends_on": ["converge"],
                "config": {
                    "profile": "luna",
                    "prompt": "VERIFY ITER={{iteration}} STATE={{loop_state}}",
                    "access": "read_only",
                    "output_schema": VERIFICATION_RESULT_SCHEMA,
                },
            },
            {
                "id": "final",
                "kind": "agent",
                "depends_on": ["converge"],
                "config": {
                    "profile": "sol",
                    "prompt": "FINAL {{result:converge}}",
                    "access": "read_only",
                },
            },
        ],
    }


class LoopExecutor:
    def __init__(
        self,
        verdicts: list[str],
        *,
        candidates: list[str] | None = None,
        step_status: str | None = None,
        interrupt_verifier_once: bool = False,
        invalid_verifier: bool = False,
        extra_outputs: dict[str, Any] | None = None,
    ) -> None:
        self.verdicts = verdicts
        self.candidates = candidates or [f"candidate-{index}" for index in range(1, 10)]
        self.step_status = step_status
        self.interrupt_verifier_once = interrupt_verifier_once
        self.invalid_verifier = invalid_verifier
        self.extra_outputs = extra_outputs or {}
        self.calls: list[str] = []
        self.tasks: list[dict[str, Any]] = []
        self.results_seen: list[dict[str, Any]] = []
        self.revision_count = 0
        self.verifier_count = 0

    async def __call__(self, task, results, prior_entry):
        self.calls.append(task["id"])
        self.tasks.append(task)
        self.results_seen.append(json.loads(json.dumps(results)))
        if task["id"] == "initial":
            output: Any = {"candidate": "initial"}
        elif task["id"] == "final":
            output = {"summary": "done"}
        elif task["id"] in self.extra_outputs:
            output = self.extra_outputs[task["id"]]
        elif (
            task["prompt"].startswith("VERIFY ITER=")
            and task["output_schema"] == VERIFICATION_RESULT_SCHEMA
        ):
            self.verifier_count += 1
            if self.interrupt_verifier_once:
                self.interrupt_verifier_once = False
                raise asyncio.CancelledError()
            if self.invalid_verifier:
                output = {"verdict": "accept", "summary": "missing evidence"}
            else:
                verdict = self.verdicts[self.verifier_count - 1]
                output = {
                    "verdict": verdict,
                    "summary": f"verifier-{self.verifier_count}",
                    "evidence": ["fixture"],
                }
        elif task["prompt"].startswith("REVISE ITER="):
            self.revision_count += 1
            if self.step_status is not None:
                return {
                    "id": task["id"],
                    "status": self.step_status,
                    "output": None,
                    "output_artifact": None,
                    "error": f"fixture {self.step_status}",
                    "attempts": [],
                }
            candidate = self.candidates[self.revision_count - 1]
            output = {
                "candidate": candidate,
                "changes": [f"change-{candidate}"],
            }
        else:
            raise AssertionError(
                f"unknown LoopExecutor prompt; refusing catch-all success: {task['prompt']}"
            )
        return {
            "id": task["id"],
            "status": "succeeded",
            "output": output,
            "output_artifact": None,
            "error": None,
            "attempts": [],
        }


class BoundedLoopRuntimeTests(unittest.IsolatedAsyncioTestCase):
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

    async def run_loop(self, executor: LoopExecutor, **kwargs):
        scheduler = TrustedControlFlowScheduler(
            bounded_ir(**kwargs),
            self.base / f"run-{len(list(self.base.iterdir()))}",
            execute_agent=executor,
            limits=self.limits,
        )
        return await scheduler.run()

    async def test_first_iteration_accept_and_templates_are_skipped(self) -> None:
        executor = LoopExecutor(["accept"])
        summary = await self.run_loop(executor)
        nodes = {node["id"]: node for node in summary["nodes"]}
        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(nodes["converge"]["stop_reason"], "verification_accept")
        self.assertEqual(nodes["converge"]["completed_iterations"], 1)
        for template_id in ("revise-template", "verify-template"):
            self.assertEqual(nodes[template_id]["status"], "skipped")
            self.assertEqual(nodes[template_id]["reason"], LOOP_TEMPLATE_SKIP_REASON)
            self.assertFalse(Path(summary["run_dir"], "tasks", template_id).exists())
        loop_calls = [call for call in executor.calls if len(call) == 40]
        self.assertEqual(len(loop_calls), 2)
        self.assertTrue(all(call.islower() for call in loop_calls))
        self.assertTrue(
            all("{{loop_state}}" not in task["prompt"] for task in executor.tasks)
        )

    async def test_reject_then_accept_runs_exactly_two_iterations(self) -> None:
        executor = LoopExecutor(["reject", "accept"])
        summary = await self.run_loop(executor)
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["status"], "succeeded")
        self.assertEqual(loop["completed_iterations"], 2)
        self.assertEqual(len(loop["progress_digests"]), 2)
        self.assertEqual(executor.revision_count, 2)
        self.assertEqual(executor.verifier_count, 2)

    async def test_unknown_needs_escalation(self) -> None:
        summary = await self.run_loop(LoopExecutor(["unknown"]))
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["status"], "needs_escalation")
        self.assertEqual(loop["stop_reason"], "verification_unknown")

    async def test_iteration_limit_needs_escalation(self) -> None:
        summary = await self.run_loop(
            LoopExecutor(["reject", "reject"], candidates=["one", "two"])
        )
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["status"], "needs_escalation")
        self.assertEqual(loop["stop_reason"], "iteration_limit")

    async def test_repeated_candidate_digest_triggers_no_progress(self) -> None:
        summary = await self.run_loop(
            LoopExecutor(["reject", "reject"], candidates=["same", "same"])
        )
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["stop_reason"], "no_progress")
        self.assertEqual(loop["progress_digests"][0], loop["progress_digests"][1])

    async def test_step_non_success_is_propagated_without_verifier(self) -> None:
        for status in ("failed", "cancelled", "needs_escalation"):
            with self.subTest(status=status):
                executor = LoopExecutor(["accept"], step_status=status)
                summary = await self.run_loop(executor)
                loop = next(
                    node for node in summary["nodes"] if node["id"] == "converge"
                )
                self.assertEqual(loop["status"], status)
                self.assertEqual(loop["stop_reason"], f"step_{status}")
                self.assertEqual(executor.verifier_count, 0)

    async def test_manifest_contains_child_and_artifact_identities(self) -> None:
        summary = await self.run_loop(LoopExecutor(["accept"]))
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        manifest = ArtifactStore(
            Path(summary["run_dir"]), self.limits
        ).load_json(loop["output_artifact"], expected_task_id="converge")
        self.assertEqual(manifest["status"], "succeeded")
        self.assertEqual(manifest["stop_reason"], "verification_accept")
        self.assertTrue(manifest["converged"])
        self.assertEqual(manifest["final_candidate"]["candidate"], "candidate-1")
        self.assertEqual(manifest["final_feedback"]["verdict"], "accept")
        self.assertEqual(len(manifest["children"]), 2)
        for child in manifest["children"]:
            self.assertEqual(child["id"], child["task_id"])
            self.assertIsNotNone(child["input_artifact"])
            self.assertIsNotNone(child["output_artifact"])

    async def test_partial_resume_refuses_ambiguous_running_step_without_replay(
        self,
    ) -> None:
        raw = bounded_ir()
        run_dir = self.base / "resume"
        first = LoopExecutor(["accept"], interrupt_verifier_once=True)
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=first,
            limits=self.limits,
        )
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()
        checkpoint_path = run_dir / "checkpoint.json"
        events_path = run_dir / "events.jsonl"
        checkpoint_bytes = checkpoint_path.read_bytes()
        events_bytes = events_path.read_bytes()
        checkpoint = json.loads(checkpoint_bytes)
        interrupted_summary = json.loads(
            (run_dir / "summary.json").read_text(encoding="utf-8")
        )
        resolved_path = run_dir / "workflow-ir.resolved.json"
        resolved_bytes = resolved_path.read_bytes()
        resolved_digest = hashlib.sha256(resolved_bytes).hexdigest()
        resolved_mtime = resolved_path.stat().st_mtime_ns
        resolved_ir = json.loads(resolved_bytes)
        digest_payload = {
            key: resolved_ir[key]
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
            if key in resolved_ir
        }
        canonical_ir_digest = hashlib.sha256(
            json.dumps(
                digest_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            {
                canonical_ir_digest,
                scheduler.ir_digest,
                checkpoint["ir_digest"],
                interrupted_summary["ir_digest"],
            },
            {canonical_ir_digest},
        )
        interrupted_events = [
            json.loads(line)
            for line in events_bytes.decode("utf-8").splitlines()
        ]
        self.assertEqual(
            [event["sequence"] for event in interrupted_events],
            list(range(1, len(interrupted_events) + 1)),
        )
        self.assertEqual(checkpoint["event_sequence"], len(interrupted_events))
        children = checkpoint["entries"]["converge"]["children"]
        succeeded_id = next(
            child_id for child_id, child in children.items() if child["status"] == "succeeded"
        )
        running_id = next(
            child_id for child_id, child in children.items() if child["status"] == "running"
        )

        second = LoopExecutor(["accept"])
        resumed = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=second,
            limits=self.limits,
        )
        with self.assertRaisesRegex(ControlFlowError, "ambiguous.*replay"):
            await resumed.run(resume=True)
        self.assertEqual(second.calls, [])
        self.assertEqual(checkpoint_path.read_bytes(), checkpoint_bytes)
        self.assertEqual(events_path.read_bytes(), events_bytes)
        self.assertEqual(resolved_path.read_bytes(), resolved_bytes)
        self.assertEqual(
            hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
            resolved_digest,
        )
        self.assertEqual(resolved_path.stat().st_mtime_ns, resolved_mtime)
        current_children = json.loads(checkpoint_path.read_bytes())["entries"][
            "converge"
        ]["children"]
        self.assertEqual(current_children[succeeded_id]["status"], "succeeded")
        self.assertEqual(current_children[running_id]["status"], "running")

    async def test_loop_substitution_exposes_only_host_selected_results(self) -> None:
        raw = bounded_ir(max_iterations=2, max_agents=7)
        raw["budgets"]["max_concurrency"] = 1
        raw["nodes"].insert(
            1,
            {
                "id": "unrelated",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "UNRELATED",
                    "access": "read_only",
                },
            },
        )
        secret = "SECRET-SENTINEL-MUST-NOT-LEAK"
        executor = LoopExecutor(
            ["reject", "accept"],
            candidates=["x" * 4000, "y" * 4000],
            extra_outputs={"unrelated": {"secret": secret}},
        )
        run_dir = self.base / "substitution"
        scheduler = TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=executor, limits=self.limits
        )
        await scheduler.run()

        loop_calls = [
            (task, results)
            for task, results in zip(executor.tasks, executor.results_seen)
            if len(task["id"]) == 40
        ]
        self.assertEqual(len(loop_calls), 4)
        expected_sizes = [2, 3, 4, 5]
        store = ArtifactStore(run_dir, self.limits)
        for (task, results), expected_size in zip(loop_calls, expected_sizes):
            with self.subTest(task=task["id"]):
                self.assertEqual(len(results), expected_size)
                self.assertNotIn("unrelated", results)
                self.assertIn("<BOUNDED_LOOP_HOST_RESULTS_V1>", task["prompt"])
                resolved, missing = substitute_upstream_results(
                    task["prompt"],
                    results,
                    placeholder_pattern=re.compile(
                        r"\{\{result:([A-Za-z0-9_-]+)\}\}"
                    ),
                    store=store,
                    max_inline_bytes=self.limits.max_upstream_inline_bytes,
                )
                self.assertEqual(missing, [])
                self.assertNotIn(secret, resolved)
        self.assertIn("<UPSTREAM_ARTIFACT_REFERENCE", resolved)

    async def test_invalid_verifier_output_fail_closed_with_one_stop(self) -> None:
        run_dir = self.base / "invalid-verifier"
        scheduler = TrustedControlFlowScheduler(
            bounded_ir(),
            run_dir,
            execute_agent=LoopExecutor(["accept"], invalid_verifier=True),
            limits=self.limits,
        )
        summary = await scheduler.run()
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["status"], "failed")
        self.assertEqual(loop["stop_reason"], "invalid_verifier_output")
        manifest = ArtifactStore(run_dir, self.limits).load_json(
            loop["output_artifact"], expected_task_id="converge"
        )
        self.assertFalse(manifest["converged"])
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.loop.stopped" for event in events), 1
        )

    async def test_iteration_completed_crash_resumes_without_replay(self) -> None:
        raw = bounded_ir()
        run_dir = self.base / "iteration-completed-crash"
        first = LoopExecutor(["accept"])
        scheduler = TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=first, limits=self.limits
        )
        original = scheduler._apply_loop_decision
        interrupted = False

        async def interrupt_once(node, entry, record):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise asyncio.CancelledError()
            return await original(node, entry, record)

        scheduler._apply_loop_decision = interrupt_once  # type: ignore[method-assign]
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()

        second = LoopExecutor(["accept"])
        resumed = TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=second, limits=self.limits
        )
        summary = await resumed.run(resume=True)
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["completed_iterations"], 1)
        self.assertEqual(len(loop["progress_digests"]), 1)
        self.assertEqual(second.calls, ["final"])
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(
                event["type"] == "workflow.loop.iteration.completed"
                for event in events
            ),
            1,
        )

    async def test_loop_stopped_crash_keeps_state_consistent_and_does_not_rerun(self) -> None:
        raw = bounded_ir()
        run_dir = self.base / "loop-stopped-crash"
        first = LoopExecutor(["accept"])
        scheduler = TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=first, limits=self.limits
        )
        original = scheduler._stop_loop
        interrupted = False

        async def interrupt_after_stop(node, entry, **kwargs):
            nonlocal interrupted
            result = await original(node, entry, **kwargs)
            if not interrupted:
                interrupted = True
                raise asyncio.CancelledError()
            return result

        scheduler._stop_loop = interrupt_after_stop  # type: ignore[method-assign]
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()
        checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["states"]["converge"], "succeeded")
        self.assertEqual(
            checkpoint["entries"]["converge"]["status"], "succeeded"
        )
        self.assertIsInstance(
            checkpoint["entries"]["converge"]["finished"], str
        )
        before_resume_events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(
                event["type"] == "workflow.node.completed"
                and event["payload"].get("node_id") == "converge"
                for event in before_resume_events
            ),
            1,
        )

        second = LoopExecutor(["accept"])
        final = await TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=second, limits=self.limits
        ).run(resume=True)
        self.assertTrue(final["all_succeeded"])
        self.assertEqual(second.calls, ["final"])
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(event["type"] == "workflow.loop.stopped" for event in events), 1
        )
        completed = [
            event["payload"]
            for event in events
            if event["type"] == "workflow.node.completed"
            and event["payload"].get("node_id") == "converge"
        ]
        self.assertEqual(
            completed,
            [
                {
                    "node_id": "converge",
                    "kind": "loop",
                    "status": "succeeded",
                    "error": None,
                }
            ],
        )

    async def test_resume_reconciles_stop_before_node_completion_exactly_once(self) -> None:
        scenarios = (
            ("succeeded", LoopExecutor(["accept"]), "succeeded", ["final"]),
            (
                "needs-escalation",
                LoopExecutor(["unknown"]),
                "needs_escalation",
                [],
            ),
            (
                "failed",
                LoopExecutor(["accept"], invalid_verifier=True),
                "failed",
                [],
            ),
        )
        for label, first, expected_status, expected_resume_calls in scenarios:
            with self.subTest(label=label):
                raw = bounded_ir()
                run_dir = self.base / f"stop-completion-gap-{label}"
                scheduler = TrustedControlFlowScheduler(
                    raw, run_dir, execute_agent=first, limits=self.limits
                )
                original = scheduler._record_node_completed
                interrupted = False

                async def interrupt_before_loop_completion(node, entry):
                    nonlocal interrupted
                    if node["id"] == "converge" and not interrupted:
                        interrupted = True
                        raise asyncio.CancelledError()
                    await original(node, entry)

                scheduler._record_node_completed = (  # type: ignore[method-assign]
                    interrupt_before_loop_completion
                )
                with self.assertRaises(asyncio.CancelledError):
                    await scheduler.run()

                checkpoint = json.loads(
                    (run_dir / "checkpoint.json").read_text(encoding="utf-8")
                )
                loop_entry = checkpoint["entries"]["converge"]
                self.assertEqual(checkpoint["states"]["converge"], expected_status)
                self.assertEqual(loop_entry["status"], expected_status)
                self.assertIsInstance(loop_entry["finished"], str)
                terminal_finished = loop_entry["finished"]
                before_events = [
                    json.loads(line)
                    for line in (run_dir / "events.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                self.assertEqual(
                    sum(
                        event["type"] == "workflow.loop.stopped"
                        for event in before_events
                    ),
                    1,
                )
                self.assertFalse(
                    any(
                        event["type"] == "workflow.node.completed"
                        and event["payload"].get("node_id") == "converge"
                        for event in before_events
                    )
                )

                second = LoopExecutor(["accept"])
                summary = await TrustedControlFlowScheduler(
                    raw, run_dir, execute_agent=second, limits=self.limits
                ).run(resume=True)
                resumed_loop = next(
                    node for node in summary["nodes"] if node["id"] == "converge"
                )
                self.assertEqual(resumed_loop["status"], expected_status)
                self.assertEqual(resumed_loop["finished"], terminal_finished)
                self.assertEqual(second.calls, expected_resume_calls)
                after_events = [
                    json.loads(line)
                    for line in (run_dir / "events.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                self.assertEqual(
                    sum(
                        event["type"] == "workflow.loop.stopped"
                        for event in after_events
                    ),
                    1,
                )
                completed = [
                    event["payload"]
                    for event in after_events
                    if event["type"] == "workflow.node.completed"
                    and event["payload"].get("node_id") == "converge"
                ]
                self.assertEqual(
                    completed,
                    [
                        {
                            "node_id": "converge",
                            "kind": "loop",
                            "status": expected_status,
                            "error": loop_entry["error"],
                        }
                    ],
                )

    async def test_terminal_child_crash_propagates_original_status_on_resume(self) -> None:
        raw = bounded_ir()
        run_dir = self.base / "terminal-child-crash"
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=LoopExecutor(["accept"], step_status="failed"),
            limits=self.limits,
        )
        original = scheduler._event
        interrupted = False

        async def interrupt_after_completed(event_type, payload):
            nonlocal interrupted
            await original(event_type, payload)
            if event_type == "workflow.loop.step.completed" and not interrupted:
                interrupted = True
                raise asyncio.CancelledError()

        scheduler._event = interrupt_after_completed  # type: ignore[method-assign]
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()
        second = LoopExecutor(["accept"])
        summary = await TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=second, limits=self.limits
        ).run(resume=True)
        loop = next(node for node in summary["nodes"] if node["id"] == "converge")
        self.assertEqual(loop["status"], "failed")
        self.assertEqual(loop["stop_reason"], "step_failed")
        self.assertEqual(second.calls, [])

    async def test_completion_snapshot_failure_keeps_terminal_payload_and_event(self) -> None:
        raw = bounded_ir()
        run_dir = self.base / "completion-snapshot-failure"
        first = LoopExecutor(["accept"])
        scheduler = TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=first, limits=self.limits
        )
        original_snapshot = scheduler._snapshot_locked
        failed_once = False

        def fail_final_completion_snapshot_once():
            nonlocal failed_once
            if "final" in scheduler.completed_node_events and not failed_once:
                failed_once = True
                raise OSError("completion snapshot fixture failed")
            original_snapshot()

        scheduler._snapshot_locked = (  # type: ignore[method-assign]
            fail_final_completion_snapshot_once
        )
        summary = await scheduler.run()
        final_entry = next(
            node for node in summary["nodes"] if node["id"] == "final"
        )
        self.assertTrue(failed_once)
        self.assertEqual(final_entry["status"], "succeeded")
        terminal_artifact = final_entry["output_artifact"]
        events_path = run_dir / "events.jsonl"
        before_resume_events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        final_completions = [
            event["payload"]
            for event in before_resume_events
            if event["type"] == "workflow.node.completed"
            and event["payload"].get("node_id") == "final"
        ]
        self.assertEqual(
            final_completions,
            [
                {
                    "node_id": "final",
                    "kind": "agent",
                    "status": "succeeded",
                    "error": None,
                }
            ],
        )

        second = LoopExecutor(["accept"])
        resumed = await TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=second, limits=self.limits
        ).run(resume=True)
        resumed_final = next(
            node for node in resumed["nodes"] if node["id"] == "final"
        )
        self.assertEqual(second.calls, [])
        self.assertEqual(resumed_final["status"], "succeeded")
        self.assertEqual(resumed_final["output_artifact"], terminal_artifact)
        after_resume_events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            sum(
                event["type"] == "workflow.node.completed"
                and event["payload"].get("node_id") == "final"
                for event in after_resume_events
            ),
            1,
        )

    async def test_resume_rejects_started_event_identity_tamper_without_rewrite(self) -> None:
        for label in ("node", "kind"):
            with self.subTest(label=label):
                raw = bounded_ir()
                run_dir = self.base / f"started-event-tamper-{label}"
                await TrustedControlFlowScheduler(
                    raw,
                    run_dir,
                    execute_agent=LoopExecutor(["accept"]),
                    limits=self.limits,
                ).run()
                events_path = run_dir / "events.jsonl"
                checkpoint_path = run_dir / "checkpoint.json"
                summary_path = run_dir / "summary.json"
                events = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                ]
                started = next(
                    event
                    for event in events
                    if event["type"] == "workflow.node.started"
                    and event["payload"]["node_id"] == "initial"
                )
                if label == "node":
                    started["payload"]["node_id"] = "attacker-controlled"
                else:
                    started["payload"]["kind"] = "human_gate"
                events_path.write_text(
                    "".join(
                        json.dumps(event, ensure_ascii=False, sort_keys=True)
                        + "\n"
                        for event in events
                    ),
                    encoding="utf-8",
                )
                evidence_paths = (events_path, checkpoint_path, summary_path)
                before = {path: path.read_bytes() for path in evidence_paths}
                executor = LoopExecutor(["accept"])
                with self.assertRaisesRegex(
                    ControlFlowError,
                    "workflow node started event evidence is invalid",
                ):
                    await TrustedControlFlowScheduler(
                        raw,
                        run_dir,
                        execute_agent=executor,
                        limits=self.limits,
                    ).run(resume=True)
                self.assertEqual(executor.calls, [])
                self.assertEqual(
                    {path: path.read_bytes() for path in evidence_paths},
                    before,
                )

    async def test_runtime_paths_are_portable_under_space_unicode_nesting(self) -> None:
        raw = bounded_ir()
        with tempfile.TemporaryDirectory(prefix="bounded loop 路径 ") as temporary:
            run_dir = Path(temporary) / "nested space" / "子目录" / "run"
            fixture = LoopExecutor(["accept"])
            recorded_task_paths: dict[str, Path] = {}

            async def portable_executor(task, results, prior_entry):
                task_path = run_dir / "tasks" / task["id"]
                task_path.mkdir(parents=True, exist_ok=False)
                recorded_task_paths[task["id"]] = task_path
                return await fixture(task, results, prior_entry)

            summary = await TrustedControlFlowScheduler(
                raw,
                run_dir,
                execute_agent=portable_executor,
                limits=self.limits,
            ).run()
            checkpoint_path = run_dir / "checkpoint.json"
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            loop_entry = checkpoint["entries"]["converge"]
            child_ids = loop_entry["iteration_records"][0]["child_ids"]
            self.assertEqual(set(child_ids), set(loop_entry["children"]))
            store = ArtifactStore(run_dir, self.limits)
            for child_id in child_ids:
                child = loop_entry["children"][child_id]
                state_id = child["state_input_id"]
                self.assertRegex(child_id, r"\A[0-9a-f]{40}\Z")
                self.assertRegex(state_id, r"\A[0-9a-f]{40}\Z")
                self.assertEqual(child["task_id"], child_id)
                self.assertEqual(
                    child["input_artifact"]["$artifact"]["task_id"],
                    state_id,
                )
                self.assertEqual(
                    child["output_artifact"]["$artifact"]["task_id"],
                    child_id,
                )
                for reference in (
                    child["input_artifact"],
                    child["output_artifact"],
                ):
                    relative = Path(reference["$artifact"]["path"])
                    self.assertFalse(relative.is_absolute())
                    resolved = (run_dir / relative).resolve()
                    self.assertTrue(resolved.is_relative_to(run_dir.resolve()))
                    self.assertTrue(resolved.is_file())
                    store.load_json(
                        reference,
                        expected_task_id=reference["$artifact"]["task_id"],
                    )
                task_path = run_dir / "tasks" / child_id
                self.assertTrue(task_path.is_relative_to(run_dir / "tasks"))
                self.assertRegex(task_path.name, r"\A[0-9a-f]{40}\Z")
                self.assertEqual(recorded_task_paths[child_id], task_path)
                self.assertTrue(task_path.is_dir())
            self.assertTrue(checkpoint_path.resolve().is_relative_to(run_dir.resolve()))
            self.assertEqual(Path(summary["run_dir"]), run_dir.resolve())

    async def test_resume_rejects_progress_tampering_before_dispatch(self) -> None:
        raw = bounded_ir()
        run_dir = self.base / "tamper"
        first = LoopExecutor(["reject", "reject"], candidates=["one", "two"])
        scheduler = TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=first, limits=self.limits
        )
        await scheduler.run()
        checkpoint_path = run_dir / "checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["entries"]["converge"]["progress_digests"][0] = "0" * 64
        checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
        second = LoopExecutor(["accept"])
        resumed = TrustedControlFlowScheduler(
            raw, run_dir, execute_agent=second, limits=self.limits
        )
        with self.assertRaisesRegex(
            ControlFlowError, "summary|progress digest|event evidence"
        ):
            await resumed.run(resume=True)
        self.assertEqual(second.calls, [])

    async def test_resume_rejects_identity_artifact_summary_event_and_count_tamper(self) -> None:
        for label in (
            "top-artifact",
            "child-identity",
            "child-artifact",
            "resume-count",
            "summary-entry",
            "loop-event",
        ):
            with self.subTest(label=label):
                raw = bounded_ir()
                run_dir = self.base / f"tamper-{label}"
                await TrustedControlFlowScheduler(
                    raw,
                    run_dir,
                    execute_agent=LoopExecutor(["accept"]),
                    limits=self.limits,
                ).run()
                checkpoint_path = run_dir / "checkpoint.json"
                summary_path = run_dir / "summary.json"
                events_path = run_dir / "events.jsonl"
                checkpoint = json.loads(
                    checkpoint_path.read_text(encoding="utf-8")
                )
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                summary_by_id = {item["id"]: item for item in summary["nodes"]}
                loop_entry = checkpoint["entries"]["converge"]
                summary_loop = summary_by_id["converge"]
                first_child_id = loop_entry["iteration_records"][0]["child_ids"][0]
                if label == "top-artifact":
                    for entry in (
                        checkpoint["entries"]["initial"],
                        summary_by_id["initial"],
                    ):
                        entry["output_artifact"]["$artifact"]["task_id"] = "other"
                        entry["agent_entry"]["output_artifact"]["$artifact"][
                            "task_id"
                        ] = "other"
                elif label == "child-identity":
                    loop_entry["children"][first_child_id]["step_index"] = 99
                    summary_loop["children"][first_child_id]["step_index"] = 99
                elif label == "child-artifact":
                    for child in (
                        loop_entry["children"][first_child_id],
                        summary_loop["children"][first_child_id],
                    ):
                        child["output_artifact"]["$artifact"]["task_id"] = "other"
                        child["agent_entry"]["output_artifact"]["$artifact"][
                            "task_id"
                        ] = "other"
                elif label == "resume-count":
                    loop_entry["children"][first_child_id]["resume_count"] = "0"
                    summary_loop["children"][first_child_id]["resume_count"] = "0"
                elif label == "summary-entry":
                    summary_loop["completed_iterations"] = 99
                else:
                    events = [
                        json.loads(line)
                        for line in events_path.read_text(encoding="utf-8").splitlines()
                    ]
                    target = next(
                        event
                        for event in events
                        if event["type"] == "workflow.loop.iteration.completed"
                    )
                    target["payload"]["verdict"] = "unknown"
                    events_path.write_text(
                        "".join(
                            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
                            for event in events
                        ),
                        encoding="utf-8",
                    )
                checkpoint_path.write_text(
                    json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8"
                )
                summary_path.write_text(
                    json.dumps(summary, ensure_ascii=False), encoding="utf-8"
                )
                executor = LoopExecutor(["accept"])
                with self.assertRaises(ControlFlowError):
                    await TrustedControlFlowScheduler(
                        raw,
                        run_dir,
                        execute_agent=executor,
                        limits=self.limits,
                    ).run(resume=True)
                self.assertEqual(executor.calls, [])

    async def test_resume_rejects_all_summary_top_contract_tamper_before_rewrite(self) -> None:
        mutations = {
            "paused": lambda summary: summary.__setitem__("paused", True),
            "all_succeeded": lambda summary: summary.__setitem__(
                "all_succeeded", False
            ),
            "budget_semantics": lambda summary: summary["budget_semantics"].__setitem__(
                "max_tokens", "tampered"
            ),
            "limits": lambda summary: summary["limits"].__setitem__(
                "max_event_bytes", summary["limits"]["max_event_bytes"] + 1
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                raw = bounded_ir()
                run_dir = self.base / f"summary-top-tamper-{label}"
                await TrustedControlFlowScheduler(
                    raw,
                    run_dir,
                    execute_agent=LoopExecutor(["accept"]),
                    limits=self.limits,
                ).run()
                summary_path = run_dir / "summary.json"
                checkpoint_path = run_dir / "checkpoint.json"
                events_path = run_dir / "events.jsonl"
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                mutate(summary)
                summary_path.write_text(
                    json.dumps(summary, ensure_ascii=False), encoding="utf-8"
                )
                before = {
                    path: path.read_bytes()
                    for path in (summary_path, checkpoint_path, events_path)
                }
                executor = LoopExecutor(["accept"])
                with self.assertRaisesRegex(
                    ControlFlowError, "summary does not match checkpoint state"
                ):
                    await TrustedControlFlowScheduler(
                        raw,
                        run_dir,
                        execute_agent=executor,
                        limits=self.limits,
                    ).run(resume=True)
                self.assertEqual(executor.calls, [])
                self.assertEqual(
                    {
                        path: path.read_bytes()
                        for path in (summary_path, checkpoint_path, events_path)
                    },
                    before,
                )


class BoundedLoopValidationTests(unittest.TestCase):
    def test_example_is_executable_and_projects_eight_claims(self) -> None:
        example = SKILL_DIR.parent / "examples" / "bounded-design-convergence.workflow-ir.json"
        raw = json.loads(example.read_text(encoding="utf-8"))
        plan = ops_cli._plan_preview(raw)
        self.assertTrue(plan["execution_supported"])
        self.assertEqual(plan["execution"]["unsupported_node_kinds"], [])
        self.assertEqual(plan["agent_claim_projection"]["static_agent_claims"], 2)
        self.assertEqual(plan["agent_claim_projection"]["loop_child_upper_bound"], 6)
        self.assertEqual(plan["agent_claim_projection"]["total_upper_bound"], 8)
        self.assertEqual(plan["agent_claim_projection"]["max_agents"], 8)
        loop = next(node for node in plan["nodes"] if node["kind"] == "loop")
        self.assertEqual(loop["executable_contract"], "bounded-loop-v1")
        self.assertEqual(loop["initial_source"], "initial-design")
        self.assertEqual(loop["loop_claim_upper_bound"], 6)
        self.assertEqual(plan["model_calls"], 0)
        self.assertEqual(plan["writes"], [])
        self.assertFalse(plan["workdir_preflight"]["performed"])

    def test_legacy_loop_remains_validated_only_and_shape_is_unchanged(self) -> None:
        raw = bounded_ir()
        raw["nodes"] = [
            raw["nodes"][0],
            {
                "id": "legacy-loop",
                "kind": "loop",
                "depends_on": ["initial"],
                "config": {
                    "max_iterations": 2,
                    "body": ["initial"],
                    "stop_when": "verified",
                },
            },
        ]
        normalized = validate_workflow_ir(raw)
        self.assertEqual(normalized["execution"]["unsupported_node_kinds"], ["loop"])
        self.assertNotIn("no_progress_limit", normalized["nodes"][1]["config"])

    def test_no_progress_limit_rejects_wrong_types_and_out_of_range(self) -> None:
        for value in (True, 0, 6, "1", 1.0, None):
            raw = bounded_ir()
            raw["nodes"][1]["config"]["no_progress_limit"] = value
            with self.subTest(value=value), self.assertRaises(WorkflowIRValidationError):
                validate_workflow_ir(raw)

    def test_loop_iterations_above_workflow_budget_remain_validated_only(self) -> None:
        raw = bounded_ir(max_iterations=3, max_agents=8)
        raw["budgets"]["max_iterations"] = 2
        normalized = validate_workflow_ir(raw)
        self.assertEqual(normalized["nodes"][1]["config"]["max_iterations"], 3)
        self.assertEqual(normalized["budgets"]["max_iterations"], 2)
        self.assertEqual(
            normalized["execution"]["unsupported_node_kinds"], ["loop"]
        )
        executor = LoopExecutor(["accept"])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ControlFlowError):
                TrustedControlFlowScheduler(
                    raw,
                    Path(temporary) / "run",
                    execute_agent=executor,
                    limits=RuntimeLimits.from_mapping({}),
                )
        self.assertEqual(executor.calls, [])

    def test_contract_violations_are_unsupported_with_zero_dispatch(self) -> None:
        cases = {}
        short_body = bounded_ir()
        short_body["nodes"][1]["config"]["body"] = ["verify-template"]
        cases["body-short"] = short_body
        long_body = bounded_ir(max_agents=64)
        extra_templates = []
        for index in range(7):
            template = json.loads(json.dumps(long_body["nodes"][2]))
            template["id"] = f"revise-extra-{index}"
            extra_templates.append(template)
        long_body["nodes"][1]["config"]["body"] = [
            "revise-template",
            *(template["id"] for template in extra_templates),
            "verify-template",
        ]
        long_body["nodes"][4:4] = extra_templates
        cases["body-long"] = long_body
        missing_body = bounded_ir()
        missing_body["nodes"][1]["config"]["body"][0] = "missing-template"
        cases["body-missing"] = missing_body
        non_agent = bounded_ir()
        non_agent["nodes"].append(
            {
                "id": "not-agent",
                "kind": "human_gate",
                "depends_on": ["converge"],
                "config": {"prompt": "gate", "options": ["yes", "no"]},
            }
        )
        non_agent["nodes"][1]["config"]["body"][0] = "not-agent"
        cases["body-non-agent"] = non_agent
        wrong_dependency = bounded_ir()
        wrong_dependency["nodes"][2]["depends_on"] = ["initial"]
        cases["depends-exact"] = wrong_dependency
        missing_placeholder = bounded_ir()
        missing_placeholder["nodes"][2]["config"]["prompt"] = "REVISE"
        cases["placeholder"] = missing_placeholder
        extra_placeholder = bounded_ir()
        extra_placeholder["nodes"][2]["config"]["prompt"] += " {{item}}"
        cases["extra-placeholder"] = extra_placeholder
        result_placeholder = bounded_ir()
        result_placeholder["nodes"][2]["config"]["prompt"] += " {{result:initial}}"
        cases["user-result-placeholder"] = result_placeholder
        wrong_schema = bounded_ir()
        wrong_schema["nodes"][3]["config"]["output_schema"] = {"type": "object"}
        cases["schema"] = wrong_schema
        external_dependent = bounded_ir()
        external_dependent["nodes"][4]["depends_on"] = ["revise-template"]
        external_dependent["nodes"][4]["config"]["prompt"] = "FINAL"
        cases["ownership"] = external_dependent
        source_use = bounded_ir(max_agents=64)
        source_use["nodes"].append(
            {
                "id": "map-template",
                "kind": "map",
                "depends_on": ["revise-template"],
                "config": {
                    "over": "revise-template",
                    "item_limit": 1,
                    "template": {
                        "profile": "luna",
                        "prompt": "ITEM {{item}}",
                        "access": "read_only",
                    },
                },
            }
        )
        cases["source-map"] = source_use
        verify_source = bounded_ir(max_agents=64)
        verify_source["nodes"].append(
            {
                "id": "verify-source",
                "kind": "verify",
                "depends_on": ["revise-template"],
                "config": {
                    "target": "revise-template",
                    "profile": "luna",
                    "prompt": "VERIFY {{candidate}}",
                    "require_all": True,
                    "access": "read_only",
                },
            }
        )
        cases["source-verify"] = verify_source
        reduce_source = bounded_ir(max_agents=64)
        reduce_source["nodes"].append(
            {
                "id": "reduce-source",
                "kind": "reduce",
                "depends_on": ["revise-template"],
                "config": {
                    "over": "revise-template",
                    "profile": "sol",
                    "prompt": "REDUCE {{source}}",
                    "access": "read_only",
                },
            }
        )
        cases["source-reduce"] = reduce_source
        wrong_stop = bounded_ir()
        wrong_stop["nodes"][1]["config"]["stop_when"] = "verified"
        cases["stop-when"] = wrong_stop
        zero_initial = bounded_ir()
        zero_initial["nodes"][1]["depends_on"] = []
        cases["initial-source-zero"] = zero_initial
        two_initial = bounded_ir(max_agents=7)
        two_initial["nodes"].insert(
            1,
            {
                "id": "initial-two",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "INITIAL TWO",
                    "access": "read_only",
                },
            },
        )
        two_initial["nodes"][2]["depends_on"] = ["initial", "initial-two"]
        cases["initial-source-two"] = two_initial
        duplicate_body = bounded_ir()
        duplicate_body["nodes"][1]["config"]["body"] = [
            "revise-template",
            "revise-template",
        ]
        cases["body-duplicate"] = duplicate_body
        for label, raw in cases.items():
            with self.subTest(label=label):
                executor = LoopExecutor(["accept"])
                if label in {"source-verify", "source-reduce"}:
                    with self.assertRaisesRegex(
                        WorkflowIRValidationError,
                        "cannot consume agent node revise-template",
                    ):
                        validate_workflow_ir(raw)
                    with tempfile.TemporaryDirectory() as temporary:
                        with self.assertRaises(WorkflowIRValidationError):
                            TrustedControlFlowScheduler(
                                raw,
                                Path(temporary) / "run",
                                execute_agent=executor,
                                limits=RuntimeLimits.from_mapping({}),
                            )
                    self.assertEqual(executor.calls, [])
                    continue
                normalized = validate_workflow_ir(raw)
                self.assertEqual(
                    normalized["execution"]["unsupported_node_kinds"], ["loop"]
                )
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaises(ControlFlowError):
                        TrustedControlFlowScheduler(
                            raw,
                            Path(temporary) / "run",
                            execute_agent=executor,
                            limits=RuntimeLimits.from_mapping({}),
                        )
                self.assertEqual(executor.calls, [])

    def test_deterministic_child_id_binds_the_complete_tuple(self) -> None:
        identity = bounded_loop_child_id("converge", 1, 0, "revise-template")
        self.assertEqual(len(identity), 40)
        self.assertTrue(identity.islower())
        self.assertEqual(
            identity,
            bounded_loop_child_id("converge", 1, 0, "revise-template"),
        )
        self.assertNotEqual(
            identity,
            bounded_loop_child_id("converge", 2, 0, "revise-template"),
        )
        for changed in (
            bounded_loop_child_id("other-loop", 1, 0, "revise-template"),
            bounded_loop_child_id("converge", 1, 1, "revise-template"),
            bounded_loop_child_id("converge", 1, 0, "verify-template"),
            bounded_loop_child_id("Converge", 1, 0, "revise-template"),
        ):
            self.assertNotEqual(identity, changed)
        state_identity = bounded_loop_state_id(
            "converge", 1, 0, "revise-template"
        )
        self.assertEqual(len(state_identity), 40)
        self.assertNotEqual(identity, state_identity)
        for generated in (identity, state_identity):
            self.assertRegex(generated, r"\A[0-9a-f]{40}\Z")
            for forbidden in ("/", "\\", ":", ".", " "):
                self.assertNotIn(forbidden, generated)

    def test_multi_loop_ownership_isolated_and_duplicate_ownership_rejected(self) -> None:
        isolated = bounded_ir(max_agents=10)
        loop_two = json.loads(json.dumps(isolated["nodes"][1]))
        loop_two["id"] = "converge-two"
        loop_two["config"]["body"] = ["revise-two", "verify-two"]
        revise_two = json.loads(json.dumps(isolated["nodes"][2]))
        revise_two["id"] = "revise-two"
        revise_two["depends_on"] = ["converge-two"]
        verify_two = json.loads(json.dumps(isolated["nodes"][3]))
        verify_two["id"] = "verify-two"
        verify_two["depends_on"] = ["converge-two"]
        isolated["nodes"].extend([loop_two, revise_two, verify_two])
        normalized = validate_workflow_ir(isolated)
        self.assertTrue(normalized["execution"]["trusted_runtime_executable"])
        self.assertEqual(project_agent_claims(normalized)["loop_child_upper_bound"], 8)

        duplicate = bounded_ir(max_agents=10)
        duplicate_loop = json.loads(json.dumps(duplicate["nodes"][1]))
        duplicate_loop["id"] = "converge-two"
        duplicate["nodes"].append(duplicate_loop)
        duplicate_normalized = validate_workflow_ir(duplicate)
        self.assertEqual(
            duplicate_normalized["execution"]["unsupported_node_kinds"], ["loop"]
        )

    def test_conditional_template_target_is_rejected(self) -> None:
        raw = bounded_ir(max_agents=10)
        raw["nodes"].append(
            {
                "id": "choose-template",
                "kind": "conditional",
                "depends_on": ["initial"],
                "config": {
                    "condition": {
                        "source": "initial",
                        "path": [],
                        "op": "exists",
                    },
                    "then": ["revise-template"],
                    "else": [],
                },
            }
        )
        with self.assertRaises(WorkflowIRValidationError):
            validate_workflow_ir(raw)

    def test_bounded_projection_over_budget_is_rejected_before_model(self) -> None:
        raw = bounded_ir(max_agents=5)
        self.assertFalse(project_agent_claims(validate_workflow_ir(raw))["upper_bound_within_budget"])
        plan = ops_cli._plan_preview(raw)
        self.assertFalse(plan["execution_supported"])
        self.assertEqual(
            plan["execution_blockers"],
            ["agent_claim_projection_exceeds_max_agents"],
        )
        self.assertTrue(
            any(
                "run-ir rejects the current plan before any dispatch" in warning
                for warning in plan["warnings"]
            )
        )
        executor = LoopExecutor(["accept"])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(AgentBudgetError):
                TrustedControlFlowScheduler(
                    raw,
                    Path(temporary) / "run",
                    execute_agent=executor,
                    limits=RuntimeLimits.from_mapping({}),
                )
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main()
