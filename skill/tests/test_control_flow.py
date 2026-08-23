from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from runtime.artifacts import ArtifactStore
from runtime.control_flow import ControlFlowError, TrustedControlFlowScheduler
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import WorkflowIRValidationError, validate_workflow_ir


def workflow_ir(*, max_agents: int = 8, include_reduce: bool = True) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "discover",
            "kind": "agent",
            "depends_on": [],
            "config": {
                "profile": "luna",
                "prompt": "DISCOVER",
                "access": "read_only",
            },
        },
        {
            "id": "mapped",
            "kind": "map",
            "depends_on": ["discover"],
            "config": {
                "over": "discover",
                "item_limit": 8,
                "template": {
                    "profile": "luna",
                    "prompt": "MAP index={{index}} item={{item}}",
                    "access": "read_only",
                },
            },
        },
        {
            "id": "checked",
            "kind": "verify",
            "depends_on": ["mapped"],
            "config": {
                "target": "mapped",
                "profile": "luna",
                "prompt": "VERIFY index={{index}} candidate={{candidate}}",
                "require_all": True,
                "access": "read_only",
            },
        },
    ]
    if include_reduce:
        nodes.append(
            {
                "id": "synthesize",
                "kind": "reduce",
                "depends_on": ["checked"],
                "config": {
                    "over": "checked",
                    "profile": "sol",
                    "prompt": "REDUCE source={{source}}",
                    "output_schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    },
                    "access": "read_only",
                },
            }
        )
    return {
        "version": 3,
        "name": "trusted-control-flow",
        "mode": "workflow",
        "objective": "exercise map verify reduce",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": max_agents,
            "max_concurrency": 2,
            "max_iterations": 3,
            "max_tokens": 100000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
        },
        "nodes": nodes,
    }


class FakeExecutor:
    def __init__(self, *, reject_index: int | None = None, discover_count: int = 2):
        self.reject_index = reject_index
        self.discover_count = discover_count
        self.calls: list[str] = []
        self.prompts: dict[str, str] = {}

    async def __call__(
        self,
        task: dict[str, Any],
        results: dict[str, Any],
        prior_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        task_id = task["id"]
        self.calls.append(task_id)
        self.prompts[task_id] = task["prompt"]
        if task_id == "discover":
            output: Any = [
                {"name": f"item-{index}"}
                for index in range(self.discover_count)
            ]
        elif "_map_" in task_id:
            output = {"finding": task_id}
        elif "_verify_" in task_id:
            verdict = "accept"
            if self.reject_index is not None and f"index={self.reject_index}" in task["prompt"]:
                verdict = "reject"
            output = {
                "verdict": verdict,
                "summary": f"{verdict}:{task_id}",
                "evidence": ["fixture"],
            }
        elif task_id == "synthesize":
            output = {"summary": "aggregate complete"}
        elif task_id == "unrelated":
            output = "unrelated-ok"
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


class InterruptingExecutor(FakeExecutor):
    def __init__(self) -> None:
        super().__init__(discover_count=2)
        self.map_calls = 0

    async def __call__(self, task, results, prior_entry):
        if "_map_" in task["id"]:
            self.map_calls += 1
            if self.map_calls == 2:
                raise asyncio.CancelledError()
        return await super().__call__(task, results, prior_entry)


class TrustedControlFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.limits = RuntimeLimits.from_mapping(
            {
                "max_result_bytes": 1024 * 1024,
                "max_log_bytes": 1024 * 1024,
                "max_run_artifact_bytes": 16 * 1024 * 1024,
                "max_upstream_inline_bytes": 128,
                "max_event_bytes": 64 * 1024,
            }
        )

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_map_verify_reduce_pipeline_is_artifact_backed(self) -> None:
        executor = FakeExecutor()
        run_dir = self.base / "run"
        scheduler = TrustedControlFlowScheduler(
            workflow_ir(),
            run_dir,
            execute_agent=executor,
            limits=self.limits,
        )
        summary = await scheduler.run()

        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(summary["succeeded_count"], 4)
        self.assertEqual(summary["claimed_agent_count"], 6)
        self.assertTrue((run_dir / "events.jsonl").is_file())
        self.assertTrue((run_dir / "checkpoint.json").is_file())
        self.assertTrue((run_dir / "workflow-ir.resolved.json").is_file())

        store = ArtifactStore(run_dir, self.limits)
        checked_entry = next(
            node for node in summary["nodes"] if node["id"] == "checked"
        )
        checked = store.load_json(checked_entry["output_artifact"])
        self.assertEqual(checked["verdict_counts"]["accept"], 2)
        self.assertTrue(checked["verification_passed"])
        reduce_prompt = executor.prompts["synthesize"]
        self.assertIn("{{result:checked}}", reduce_prompt)
        self.assertNotIn("{{source}}", reduce_prompt)

    async def test_reject_is_semantic_data_and_reduce_still_runs(self) -> None:
        executor = FakeExecutor(reject_index=1)
        scheduler = TrustedControlFlowScheduler(
            workflow_ir(),
            self.base / "reject-run",
            execute_agent=executor,
            limits=self.limits,
        )
        summary = await scheduler.run()
        self.assertTrue(summary["all_succeeded"])
        checked_entry = next(
            node for node in summary["nodes"] if node["id"] == "checked"
        )
        checked = ArtifactStore(
            Path(summary["run_dir"]), self.limits
        ).load_json(checked_entry["output_artifact"])
        self.assertEqual(checked["verdict_counts"]["reject"], 1)
        self.assertFalse(checked["verification_passed"])
        self.assertIn("synthesize", executor.calls)

    async def test_agent_budget_failure_blocks_only_dependents(self) -> None:
        raw = workflow_ir(max_agents=5)
        raw["nodes"].append(
            {
                "id": "unrelated",
                "kind": "agent",
                "depends_on": [],
                "config": {
                    "profile": "luna",
                    "prompt": "UNRELATED",
                    "access": "read_only",
                },
            }
        )
        executor = FakeExecutor(discover_count=4)
        scheduler = TrustedControlFlowScheduler(
            raw,
            self.base / "budget-run",
            execute_agent=executor,
            limits=self.limits,
        )
        summary = await scheduler.run()
        statuses = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(statuses["unrelated"], "succeeded")
        self.assertEqual(statuses["mapped"], "failed")
        self.assertEqual(statuses["checked"], "blocked")
        self.assertEqual(statuses["synthesize"], "blocked")
        self.assertLessEqual(summary["claimed_agent_count"], 5)

    async def test_resume_reuses_completed_map_child(self) -> None:
        raw = workflow_ir(max_agents=4, include_reduce=False)
        raw["nodes"] = raw["nodes"][:2]
        raw["budgets"]["max_concurrency"] = 1
        run_dir = self.base / "resume-run"
        first = InterruptingExecutor()
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=first,
            limits=self.limits,
        )
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()

        checkpoint = json.loads(
            (run_dir / "checkpoint.json").read_text(encoding="utf-8")
        )
        mapped = checkpoint["entries"]["mapped"]
        succeeded_children = [
            child["id"]
            for child in mapped["children"].values()
            if child["status"] == "succeeded"
        ]
        self.assertEqual(len(succeeded_children), 1)

        second = FakeExecutor(discover_count=2)
        resumed = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=second,
            limits=self.limits,
        )
        summary = await resumed.run(resume=True)
        self.assertTrue(summary["all_succeeded"])
        self.assertNotIn("discover", second.calls)
        self.assertEqual(
            len([task_id for task_id in second.calls if "_map_" in task_id]),
            1,
        )
        self.assertNotIn(succeeded_children[0], second.calls)


class WorkflowIRControlFlowValidationTests(unittest.TestCase):
    def test_dynamic_source_must_be_declared_dependency(self) -> None:
        raw = workflow_ir()
        raw["nodes"][1]["depends_on"] = []
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "must list config.over"
        ):
            validate_workflow_ir(raw)

    def test_verify_target_must_be_a_map_node(self) -> None:
        raw = workflow_ir()
        raw["nodes"][2]["config"]["target"] = "discover"
        raw["nodes"][2]["depends_on"] = ["discover"]
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "cannot consume agent"
        ):
            validate_workflow_ir(raw)

    def test_required_placeholders_are_enforced(self) -> None:
        raw = workflow_ir()
        raw["nodes"][1]["config"]["template"]["prompt"] = "no item"
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "must contain"
        ):
            validate_workflow_ir(raw)

    def test_reserved_loop_is_validated_but_not_executable(self) -> None:
        raw = workflow_ir(include_reduce=False)
        raw["nodes"] = [
            raw["nodes"][0],
            {
                "id": "future-loop",
                "kind": "loop",
                "depends_on": ["discover"],
                "config": {
                    "max_iterations": 2,
                    "body": ["discover"],
                    "stop_when": "verified",
                },
            },
        ]
        normalized = validate_workflow_ir(raw)
        self.assertEqual(
            normalized["execution"]["unsupported_node_kinds"], ["loop"]
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ControlFlowError, "non-executable"):
                TrustedControlFlowScheduler(
                    normalized,
                    Path(directory) / "run",
                    execute_agent=FakeExecutor(),
                    limits=RuntimeLimits.from_mapping({}),
                )


if __name__ == "__main__":
    unittest.main()
