from __future__ import annotations

import concurrent.futures
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

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


def agent(node_id: str, depends_on: list[str], prompt: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "agent",
        "depends_on": depends_on,
        "config": {
            "profile": "luna",
            "prompt": prompt,
            "access": "read_only",
        },
    }


def conditional_flow(*, explicit_join: bool = True) -> dict[str, Any]:
    join = agent("join", ["then-leaf", "else-leaf"], "JOIN")
    if explicit_join:
        join["dependency_policy"] = "join"
    return {
        "version": 3,
        "name": "conditional-hardening",
        "mode": "workflow",
        "objective": "verify skipped branch closure",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 12,
            "max_concurrency": 3,
            "max_iterations": 3,
            "max_tokens": 100000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
        },
        "nodes": [
            agent("source", [], "SOURCE"),
            {
                "id": "choose",
                "kind": "conditional",
                "depends_on": ["source"],
                "config": {
                    "condition": {
                        "source": "source",
                        "pointer": "/ok",
                        "operator": "eq",
                        "value": True,
                    },
                    "then": ["then-entry"],
                    "else": ["else-entry"],
                },
            },
            agent("then-entry", ["choose"], "THEN ENTRY"),
            agent("then-leaf", ["then-entry"], "THEN LEAF"),
            agent("else-entry", ["choose"], "ELSE ENTRY"),
            agent("else-leaf", ["else-entry"], "ELSE LEAF"),
            join,
        ],
    }


class FakeExecutor:
    def __init__(self, *, source_ok: bool = True) -> None:
        self.source_ok = source_ok
        self.calls: list[str] = []

    async def __call__(self, task, results, prior_entry):
        task_id = task["id"]
        self.calls.append(task_id)
        output: Any = {"ok": self.source_ok} if task_id == "source" else task_id
        return {
            "id": task_id,
            "status": "succeeded",
            "output": output,
            "output_artifact": None,
            "error": None,
            "attempts": [],
        }


class ConditionalHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.limits = limits()

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_unselected_branch_descendants_never_execute(self) -> None:
        executor = FakeExecutor(source_ok=True)
        summary = await TrustedControlFlowScheduler(
            conditional_flow(),
            self.base / "branch-closure",
            execute_agent=executor,
            limits=self.limits,
        ).run()
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(states["then-entry"], "succeeded")
        self.assertEqual(states["then-leaf"], "succeeded")
        self.assertEqual(states["else-entry"], "skipped")
        self.assertEqual(states["else-leaf"], "skipped")
        self.assertEqual(states["join"], "succeeded")
        self.assertNotIn("else-entry", executor.calls)
        self.assertNotIn("else-leaf", executor.calls)
        self.assertIn("join", executor.calls)

    async def test_strict_descendant_propagates_skipped(self) -> None:
        raw = conditional_flow(explicit_join=False)
        executor = FakeExecutor(source_ok=True)
        summary = await TrustedControlFlowScheduler(
            raw,
            self.base / "strict",
            execute_agent=executor,
            limits=self.limits,
        ).run()
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(states["join"], "skipped")
        self.assertNotIn("join", executor.calls)

    async def test_join_with_only_skipped_dependencies_is_skipped(self) -> None:
        raw = conditional_flow()
        raw["nodes"][-1]["depends_on"] = ["else-entry", "else-leaf"]
        executor = FakeExecutor(source_ok=True)
        summary = await TrustedControlFlowScheduler(
            raw,
            self.base / "all-skipped-join",
            execute_agent=executor,
            limits=self.limits,
        ).run()
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(states["else-entry"], "skipped")
        self.assertEqual(states["else-leaf"], "skipped")
        self.assertEqual(states["join"], "skipped")
        self.assertNotIn("join", executor.calls)

    async def test_nested_conditional_inside_skipped_branch_never_runs(self) -> None:
        raw = conditional_flow()
        raw["nodes"] = raw["nodes"][:4]
        raw["nodes"][1]["config"]["else"] = ["inner-source"]
        raw["nodes"].extend(
            [
                agent("inner-source", ["choose"], "INNER SOURCE"),
                {
                    "id": "inner-choice",
                    "kind": "conditional",
                    "depends_on": ["inner-source"],
                    "config": {
                        "condition": {
                            "source": "inner-source",
                            "pointer": "/ok",
                            "operator": "eq",
                            "value": True,
                        },
                        "then": ["inner-then"],
                        "else": ["inner-else"],
                    },
                },
                agent("inner-then", ["inner-choice"], "INNER THEN"),
                agent("inner-else", ["inner-choice"], "INNER ELSE"),
            ]
        )
        executor = FakeExecutor(source_ok=True)
        summary = await TrustedControlFlowScheduler(
            raw,
            self.base / "nested-skipped",
            execute_agent=executor,
            limits=self.limits,
        ).run()
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        for node_id in ("inner-source", "inner-choice", "inner-then", "inner-else"):
            self.assertEqual(states[node_id], "skipped")
            self.assertNotIn(node_id, executor.calls)

    async def test_scheduler_internal_exception_records_failure(self) -> None:
        raw = {
            "version": 3,
            "name": "internal-fallback",
            "mode": "workflow",
            "objective": "exercise scheduler fallback",
            "workdir": "/bounded/work",
            "budgets": {
                "max_agents": 2,
                "max_concurrency": 1,
                "max_iterations": 1,
                "max_tokens": 1000,
                "soft_timeout_seconds": 30,
                "hard_timeout_seconds": 60,
            },
            "nodes": [agent("only", [], "ONLY")],
        }
        scheduler = TrustedControlFlowScheduler(
            raw,
            self.base / "internal",
            execute_agent=FakeExecutor(),
            limits=self.limits,
        )

        async def explode(node_id: str):
            raise RuntimeError("injected scheduler failure")

        scheduler._execute_node = explode  # type: ignore[method-assign]
        summary = await scheduler.run()
        self.assertEqual(summary["failed_count"], 1)
        self.assertIn("injected scheduler failure", summary["nodes"][0]["error"])

    def test_join_policy_requires_two_dependencies(self) -> None:
        raw = conditional_flow()
        raw["nodes"][-1]["depends_on"] = ["then-leaf"]
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "requires at least two dependencies"
        ):
            validate_workflow_ir(raw)

    def test_branch_entry_cannot_bypass_skip_with_join_policy(self) -> None:
        raw = conditional_flow()
        raw["nodes"][2]["dependency_policy"] = "join"
        raw["nodes"][2]["depends_on"].append("source")
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "branch target.*cannot use"
        ):
            validate_workflow_ir(raw)


class HumanGateAtomicityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp.name) / "run"
        self.run_dir.mkdir()
        self.store = HumanGateStore(self.run_dir, limits())
        self.identity = "a" * 64
        self.store.open_gate(
            "approval",
            prompt="Accept?",
            options=["approve", "reject"],
            input_identity=self.identity,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _decide(self, decision: str) -> str:
        record = self.store.decide(
            "approval",
            decision=decision,
            actor=f"actor-{decision}",
            source="user",
            expected_input_identity=self.identity,
        )
        return record["decision"]

    def test_conflicting_concurrent_decisions_only_one_wins(self) -> None:
        outcomes: list[str] = []
        errors: list[Exception] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self._decide, "approve"),
                executor.submit(self._decide, "reject"),
            ]
            for future in futures:
                try:
                    outcomes.append(future.result())
                except Exception as exc:  # expected for the loser
                    errors.append(exc)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], HumanGateError)
        self.assertIn("immutable", str(errors[0]))
        self.assertEqual(self.store.load("approval")["decision"], outcomes[0])

    def test_same_concurrent_decision_is_idempotent(self) -> None:
        def approve() -> str:
            return self.store.decide(
                "approval",
                decision="approve",
                actor="same-actor",
                source="user",
                expected_input_identity=self.identity,
            )["decision"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(lambda _: approve(), range(4)))
        self.assertEqual(outcomes, ["approve"] * 4)
        self.assertTrue(
            self.store.decision_path_for("approval").is_file()
        )

    def test_contract_cannot_be_rewritten_as_decided(self) -> None:
        path = self.store.path_for("approval")
        raw = __import__("json").loads(path.read_text(encoding="utf-8"))
        raw.update(
            {
                "status": "decided",
                "decision": "approve",
                "actor": "tamper",
                "source": "user",
            }
        )
        path.write_text(__import__("json").dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(HumanGateError, "must remain in waiting form"):
            self.store.load("approval")

    def test_reparse_gate_root_is_rejected(self) -> None:
        unsafe = Path(self.temp.name) / "unsafe-run"
        unsafe.mkdir()
        target = Path(self.temp.name) / "target"
        target.mkdir()
        store = HumanGateStore(unsafe, limits())
        with mock.patch("runtime.human_gate._is_reparse") as is_reparse:
            is_reparse.side_effect = lambda path: path == store.root
            store.root.mkdir()
            with self.assertRaisesRegex(HumanGateError, "symlink, junction"):
                store.open_gate(
                    "approval",
                    prompt="Accept?",
                    options=["approve", "reject"],
                    input_identity="b" * 64,
                )


if __name__ == "__main__":
    unittest.main()
