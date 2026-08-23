from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import gate_cli
from runtime.condition import (
    ConditionValidationError,
    evaluate_condition,
    validate_condition,
)
from runtime.control_flow import TrustedControlFlowScheduler
from runtime.human_gate import HumanGateError, HumanGateStore
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import WorkflowIRValidationError, validate_workflow_ir


def limits() -> RuntimeLimits:
    return RuntimeLimits.from_mapping(
        {
            "max_result_bytes": 1024 * 1024,
            "max_log_bytes": 1024 * 1024,
            "max_run_artifact_bytes": 16 * 1024 * 1024,
            "max_upstream_inline_bytes": 256,
            "max_event_bytes": 64 * 1024,
        },
        env={},
    )


def conditional_ir(*, pointer: str = "/verification_passed") -> dict[str, Any]:
    return {
        "version": 3,
        "name": "conditional-flow",
        "mode": "workflow",
        "objective": "exercise bounded conditional branches",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 8,
            "max_concurrency": 3,
            "max_iterations": 3,
            "max_tokens": 100000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
        },
        "nodes": [
            {
                "id": "source",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "SOURCE",
                    "access": "read_only",
                },
            },
            {
                "id": "choose",
                "kind": "conditional",
                "depends_on": ["source"],
                "config": {
                    "condition": {
                        "source": "source",
                        "pointer": pointer,
                        "operator": "eq",
                        "value": True,
                    },
                    "then": ["then-task"],
                    "else": ["else-task"],
                },
            },
            {
                "id": "then-task",
                "kind": "agent",
                "depends_on": ["choose"],
                "config": {
                    "profile": "luna",
                    "prompt": "THEN",
                    "access": "read_only",
                },
            },
            {
                "id": "else-task",
                "kind": "agent",
                "depends_on": ["choose"],
                "config": {
                    "profile": "luna",
                    "prompt": "ELSE",
                    "access": "read_only",
                },
            },
            {
                "id": "join",
                "kind": "agent",
                "depends_on": ["then-task", "else-task"],
                "dependency_policy": "join",
                "config": {
                    "profile": "luna",
                    "prompt": "JOIN",
                    "access": "read_only",
                },
            },
            {
                "id": "independent",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "INDEPENDENT",
                    "access": "read_only",
                },
            },
        ],
    }


def gate_ir() -> dict[str, Any]:
    return {
        "version": 3,
        "name": "human-gate-flow",
        "mode": "workflow",
        "objective": "pause for an explicit human decision",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 4,
            "max_concurrency": 2,
            "max_iterations": 3,
            "max_tokens": 100000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
        },
        "nodes": [
            {
                "id": "candidate",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "CANDIDATE",
                    "access": "read_only",
                },
            },
            {
                "id": "approval",
                "kind": "human_gate",
                "depends_on": ["candidate"],
                "config": {
                    "prompt": "Accept this candidate?",
                    "options": ["approve", "reject"],
                },
            },
            {
                "id": "after",
                "kind": "agent",
                "depends_on": ["approval"],
                "config": {
                    "profile": "luna",
                    "prompt": "AFTER",
                    "access": "read_only",
                },
            },
        ],
    }


class FakeExecutor:
    def __init__(self, *, verification_passed: bool = True) -> None:
        self.verification_passed = verification_passed
        self.calls: list[str] = []

    async def __call__(self, task, results, prior_entry):
        task_id = task["id"]
        self.calls.append(task_id)
        if task_id == "source":
            output: Any = {
                "verification_passed": self.verification_passed,
                "score": 7,
            }
        elif task_id == "candidate":
            output = {"candidate": "v1", "tests": "passed"}
        else:
            output = f"ok:{task_id}"
        return {
            "id": task_id,
            "status": "succeeded",
            "output": output,
            "output_artifact": None,
            "error": None,
            "attempts": [],
        }


class ConditionPrimitiveTests(unittest.TestCase):
    def test_bounded_condition_true_false_and_unknown(self) -> None:
        condition = validate_condition(
            {
                "source": "node-a",
                "pointer": "/score",
                "operator": "gte",
                "value": 5,
            }
        )
        self.assertEqual(
            evaluate_condition(condition, {"node-a": {"score": 7}})["state"],
            "true",
        )
        self.assertEqual(
            evaluate_condition(condition, {"node-a": {"score": 3}})["state"],
            "false",
        )
        self.assertEqual(
            evaluate_condition(condition, {"node-a": {}})["state"],
            "unknown",
        )

    def test_condition_rejects_expression_and_invalid_pointer(self) -> None:
        with self.assertRaises(ConditionValidationError):
            validate_condition(
                {
                    "source": "node-a",
                    "pointer": "/score",
                    "operator": "python",
                    "value": "x > 1",
                }
            )
        with self.assertRaises(ConditionValidationError):
            validate_condition(
                {
                    "source": "node-a",
                    "pointer": "/bad~2escape",
                    "operator": "exists",
                }
            )


class ConditionalSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.limits = limits()

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_true_branch_skips_else_and_join_runs(self) -> None:
        executor = FakeExecutor(verification_passed=True)
        run_dir = self.base / "true-run"
        scheduler = TrustedControlFlowScheduler(
            conditional_ir(),
            run_dir,
            execute_agent=executor,
            limits=self.limits,
        )
        summary = await scheduler.run()
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(states["choose"], "succeeded")
        self.assertEqual(states["then-task"], "succeeded")
        self.assertEqual(states["else-task"], "skipped")
        self.assertEqual(states["join"], "succeeded")
        self.assertEqual(summary["skipped_count"], 1)
        self.assertTrue(summary["all_succeeded"])
        self.assertIn("then-task", executor.calls)
        self.assertNotIn("else-task", executor.calls)
        self.assertIn("join", executor.calls)

        events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("workflow.conditional.evaluated", events)
        self.assertIn("workflow.node.skipped", events)
        checkpoint = json.loads(
            (run_dir / "checkpoint.json").read_text(encoding="utf-8")
        )
        self.assertEqual(checkpoint["states"]["else-task"], "skipped")

    async def test_unknown_condition_escalates_and_independent_branch_survives(self) -> None:
        executor = FakeExecutor()
        scheduler = TrustedControlFlowScheduler(
            conditional_ir(pointer="/missing"),
            self.base / "unknown-run",
            execute_agent=executor,
            limits=self.limits,
        )
        summary = await scheduler.run()
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(states["choose"], "needs_escalation")
        self.assertEqual(states["then-task"], "blocked")
        self.assertEqual(states["else-task"], "blocked")
        self.assertEqual(states["join"], "blocked")
        self.assertEqual(states["independent"], "succeeded")

    def test_conditional_references_are_explicit_and_disjoint(self) -> None:
        raw = conditional_ir()
        raw["nodes"][1]["depends_on"] = []
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "condition.source"
        ):
            validate_workflow_ir(raw)

        raw = conditional_ir()
        raw["nodes"][1]["config"]["else"] = ["then-task"]
        with self.assertRaisesRegex(WorkflowIRValidationError, "disjoint"):
            validate_workflow_ir(raw)

        raw = conditional_ir()
        raw["nodes"][2]["depends_on"] = []
        with self.assertRaisesRegex(WorkflowIRValidationError, "branch target"):
            validate_workflow_ir(raw)


class HumanGateSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.limits = limits()

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_gate_pauses_then_explicit_decision_and_resume_continue(self) -> None:
        run_dir = self.base / "gate-run"
        first_executor = FakeExecutor()
        first = TrustedControlFlowScheduler(
            gate_ir(),
            run_dir,
            execute_agent=first_executor,
            limits=self.limits,
        )
        paused = await first.run()
        states = {node["id"]: node["status"] for node in paused["nodes"]}
        self.assertTrue(paused["paused"])
        self.assertEqual(paused["waiting_count"], 1)
        self.assertIsNone(paused["finished"])
        self.assertEqual(states["approval"], "waiting")
        self.assertEqual(states["after"], "pending")
        self.assertNotIn("after", first_executor.calls)

        store = HumanGateStore(run_dir, self.limits)
        waiting = store.load("approval")
        self.assertEqual(waiting["status"], "waiting")
        store.decide(
            "approval",
            decision="approve",
            actor="fixture-user",
            source="user",
            expected_input_identity=waiting["input_identity"],
            note="reviewed tests",
        )

        second_executor = FakeExecutor()
        resumed = TrustedControlFlowScheduler(
            gate_ir(),
            run_dir,
            execute_agent=second_executor,
            limits=self.limits,
        )
        completed = await resumed.run(resume=True)
        states = {node["id"]: node["status"] for node in completed["nodes"]}
        self.assertFalse(completed["paused"])
        self.assertTrue(completed["all_succeeded"])
        self.assertEqual(states["approval"], "succeeded")
        self.assertEqual(states["after"], "succeeded")
        self.assertNotIn("candidate", second_executor.calls)
        self.assertIn("after", second_executor.calls)

    async def test_waiting_gate_resume_without_decision_pauses_again(self) -> None:
        run_dir = self.base / "still-waiting"
        executor = FakeExecutor()
        await TrustedControlFlowScheduler(
            gate_ir(), run_dir, execute_agent=executor, limits=self.limits
        ).run()
        resumed = await TrustedControlFlowScheduler(
            gate_ir(),
            run_dir,
            execute_agent=FakeExecutor(),
            limits=self.limits,
        ).run(resume=True)
        self.assertTrue(resumed["paused"])
        self.assertEqual(resumed["waiting_count"], 1)

    def test_gate_identity_and_terminal_decision_are_fail_closed(self) -> None:
        run_dir = self.base / "records"
        run_dir.mkdir()
        store = HumanGateStore(run_dir, self.limits)
        identity = "a" * 64
        record = store.open_gate(
            "approval",
            prompt="Accept?",
            options=["approve", "reject"],
            input_identity=identity,
        )
        with self.assertRaisesRegex(HumanGateError, "identity"):
            store.decide(
                "approval",
                decision="approve",
                actor="user",
                source="user",
                expected_input_identity="b" * 64,
            )
        decided = store.decide(
            "approval",
            decision="approve",
            actor="user",
            source="user",
            expected_input_identity=record["input_identity"],
        )
        self.assertEqual(
            store.decide(
                "approval",
                decision="approve",
                actor="user",
                source="user",
                expected_input_identity=record["input_identity"],
            ),
            decided,
        )
        with self.assertRaisesRegex(HumanGateError, "immutable"):
            store.decide(
                "approval",
                decision="reject",
                actor="user",
                source="user",
                expected_input_identity=record["input_identity"],
            )

    def test_gate_record_rejects_authority_injection(self) -> None:
        run_dir = self.base / "tamper"
        run_dir.mkdir()
        store = HumanGateStore(run_dir, self.limits)
        store.open_gate(
            "approval",
            prompt="Accept?",
            options=["approve", "reject"],
            input_identity="c" * 64,
        )
        path = store.path_for("approval")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["authorization"] = "push-and-deploy"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(HumanGateError, "unknown keys"):
            store.load("approval")


class GateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_condition_preview_requires_declared_dependency(self) -> None:
        condition_path = self.root / "condition.json"
        sources_path = self.root / "sources.json"
        condition_path.write_text(
            json.dumps(
                {
                    "source": "source",
                    "pointer": "/ok",
                    "operator": "eq",
                    "value": True,
                }
            ),
            encoding="utf-8",
        )
        sources_path.write_text(
            json.dumps({"source": {"ok": True}}), encoding="utf-8"
        )
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = gate_cli.main(
                [
                    "condition-evaluate",
                    "--condition",
                    str(condition_path),
                    "--sources",
                    str(sources_path),
                    "--dependency",
                    "source",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["state"], "true")

    def test_gate_status_and_decide_are_explicit(self) -> None:
        run_dir = self.root / "runs" / "fixture"
        run_dir.mkdir(parents=True)
        resolved = gate_ir()
        resolved["limits"] = limits().to_dict()
        (run_dir / "workflow-ir.resolved.json").write_text(
            json.dumps(resolved), encoding="utf-8"
        )
        (run_dir / "checkpoint.json").write_text("{}", encoding="utf-8")
        store = HumanGateStore(run_dir, limits())
        waiting = store.open_gate(
            "approval",
            prompt="Accept this candidate?",
            options=["approve", "reject"],
            input_identity="d" * 64,
        )
        with mock.patch.dict(
            os.environ, {"DYNWF_RUNS_ROOT": str(self.root / "runs")}, clear=False
        ):
            with contextlib.redirect_stdout(io.StringIO()) as status_output:
                status_code = gate_cli.main(
                    [
                        "gate-status",
                        "--run-dir",
                        str(run_dir),
                        "--node-id",
                        "approval",
                    ]
                )
            self.assertEqual(status_code, 0)
            self.assertEqual(
                json.loads(status_output.getvalue())["status"], "waiting"
            )
            with contextlib.redirect_stdout(io.StringIO()) as decision_output:
                decision_code = gate_cli.main(
                    [
                        "gate-decide",
                        "--run-dir",
                        str(run_dir),
                        "--node-id",
                        "approval",
                        "--decision",
                        "approve",
                        "--actor",
                        "fixture-user",
                        "--source",
                        "user",
                        "--expected-input-identity",
                        waiting["input_identity"],
                    ]
                )
            self.assertEqual(decision_code, 0)
            self.assertEqual(
                json.loads(decision_output.getvalue())["decision"], "approve"
            )


if __name__ == "__main__":
    unittest.main()
