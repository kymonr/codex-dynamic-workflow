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

    async def _interrupt_after_child_aggregation(
        self,
        raw: dict[str, Any],
        run_dir: Path,
        *,
        node_id: str,
    ) -> None:
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=FakeExecutor(discover_count=2),
            limits=self.limits,
        )
        original_set_node_output = scheduler._set_node_output
        interrupted = False

        def interrupt_aggregation(entry: dict[str, Any], value: Any) -> None:
            nonlocal interrupted
            if entry["id"] == node_id and not interrupted:
                interrupted = True
                raise asyncio.CancelledError()
            original_set_node_output(entry, value)

        scheduler._set_node_output = interrupt_aggregation
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()

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

    async def test_direct_scheduler_enforces_declared_output_schema(self) -> None:
        for discover_count in (6, 8):
            with self.subTest(discover_count=discover_count):
                raw = workflow_ir(max_agents=20, include_reduce=False)
                raw["nodes"] = raw["nodes"][:2]
                raw["nodes"][0]["config"]["output_schema"] = {
                    "type": "array",
                    "minItems": 7,
                    "maxItems": 7,
                    "items": {"type": "object"},
                }
                executor = FakeExecutor(discover_count=discover_count)
                scheduler = TrustedControlFlowScheduler(
                    raw,
                    self.base / f"schema-{discover_count}",
                    execute_agent=executor,
                    limits=self.limits,
                )

                summary = await scheduler.run()

                statuses = {
                    node["id"]: node["status"] for node in summary["nodes"]
                }
                self.assertEqual(statuses["discover"], "failed")
                self.assertEqual(statuses["mapped"], "blocked")
                self.assertFalse(
                    any("_map_" in task_id for task_id in executor.calls)
                )

    async def test_resume_refuses_ambiguous_running_map_child_without_dispatch(
        self,
    ) -> None:
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

        async def legacy_gather(work, *, entry, phase):
            del entry, phase
            await asyncio.gather(*(coroutine for _, coroutine in work))

        scheduler._gather_child_tasks = legacy_gather
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()

        checkpoint_path = run_dir / "checkpoint.json"
        events_path = run_dir / "events.jsonl"
        checkpoint_before = checkpoint_path.read_bytes()
        events_before = events_path.read_bytes()
        checkpoint = json.loads(checkpoint_before)
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
        with self.assertRaisesRegex(ControlFlowError, "ambiguous.*replay"):
            await resumed.run(resume=True)
        self.assertEqual(second.calls, [])
        self.assertEqual(checkpoint_path.read_bytes(), checkpoint_before)
        self.assertEqual(events_path.read_bytes(), events_before)

    async def test_resume_reuses_completed_map_children_after_aggregation_interrupt(
        self,
    ) -> None:
        raw = workflow_ir(max_agents=4, include_reduce=False)
        raw["nodes"] = raw["nodes"][:2]
        run_dir = self.base / "resume-after-map-aggregation"
        first = FakeExecutor(discover_count=2)
        scheduler = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=first,
            limits=self.limits,
        )
        original_set_node_output = scheduler._set_node_output
        interrupted = False

        def interrupt_map_aggregation(entry: dict[str, Any], value: Any) -> None:
            nonlocal interrupted
            if entry["id"] == "mapped" and not interrupted:
                interrupted = True
                raise asyncio.CancelledError()
            original_set_node_output(entry, value)

        scheduler._set_node_output = interrupt_map_aggregation
        with self.assertRaises(asyncio.CancelledError):
            await scheduler.run()

        checkpoint = json.loads(
            (run_dir / "checkpoint.json").read_text(encoding="utf-8")
        )
        mapped = checkpoint["entries"]["mapped"]
        completed_ids = {
            child["id"]
            for child in mapped["children"].values()
            if child["status"] == "succeeded"
        }
        self.assertEqual(len(completed_ids), 2)

        second = FakeExecutor(discover_count=2)
        resumed = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=second,
            limits=self.limits,
        )
        summary = await resumed.run(resume=True)

        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(second.calls, [])
        mapped_summary = next(
            node for node in summary["nodes"] if node["id"] == "mapped"
        )
        self.assertIsNotNone(mapped_summary["output_artifact"])

    async def test_resume_revalidates_recovered_map_child_schema_before_dispatch(
        self,
    ) -> None:
        raw = workflow_ir(max_agents=4, include_reduce=False)
        raw["nodes"] = raw["nodes"][:2]
        raw["nodes"][1]["config"]["template"]["output_schema"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"finding": {"type": "string"}},
            "required": ["finding"],
        }
        run_dir = self.base / "resume-map-schema"
        await self._interrupt_after_child_aggregation(
            raw, run_dir, node_id="mapped"
        )

        class TamperedRecoveredMapScheduler(TrustedControlFlowScheduler):
            def _restore(inner_self) -> None:
                super()._restore()
                child = next(
                    iter(inner_self.entries["mapped"]["children"].values())
                )
                invalid = {"unexpected": "schema"}
                reference = inner_self.store.put_json(child["id"], invalid)
                child["output"] = invalid
                child["output_artifact"] = reference
                child["agent_entry"]["output"] = invalid
                child["agent_entry"]["output_artifact"] = reference

        executor = FakeExecutor(discover_count=2)
        resumed = TamperedRecoveredMapScheduler(
            raw,
            run_dir,
            execute_agent=executor,
            limits=self.limits,
        )

        summary = await resumed.run(resume=True)

        mapped = next(node for node in summary["nodes"] if node["id"] == "mapped")
        self.assertEqual(mapped["status"], "failed")
        self.assertIn("output schema mismatch", mapped["error"])
        self.assertEqual(executor.calls, [])

    async def test_resume_revalidates_recovered_verify_child_schema_before_dispatch(
        self,
    ) -> None:
        raw = workflow_ir(max_agents=8, include_reduce=False)
        run_dir = self.base / "resume-verify-schema"
        await self._interrupt_after_child_aggregation(
            raw, run_dir, node_id="checked"
        )

        class TamperedRecoveredVerifyScheduler(TrustedControlFlowScheduler):
            def _restore(inner_self) -> None:
                super()._restore()
                child = next(
                    iter(inner_self.entries["checked"]["children"].values())
                )
                invalid = {"verdict": "accept", "summary": "missing evidence"}
                reference = inner_self.store.put_json(child["id"], invalid)
                child["output"] = invalid
                child["output_artifact"] = reference
                child["agent_entry"]["output"] = invalid
                child["agent_entry"]["output_artifact"] = reference

        executor = FakeExecutor(discover_count=2)
        resumed = TamperedRecoveredVerifyScheduler(
            raw,
            run_dir,
            execute_agent=executor,
            limits=self.limits,
        )

        summary = await resumed.run(resume=True)

        checked = next(node for node in summary["nodes"] if node["id"] == "checked")
        self.assertEqual(checked["status"], "failed")
        self.assertIn("output schema mismatch", checked["error"])
        self.assertEqual(executor.calls, [])

    async def test_resume_revalidates_recovered_child_input_before_dispatch(
        self,
    ) -> None:
        cases = {
            "map": ("mapped", workflow_ir(max_agents=4, include_reduce=False)),
            "verify": ("checked", workflow_ir(max_agents=8, include_reduce=False)),
        }
        cases["map"][1]["nodes"] = cases["map"][1]["nodes"][:2]

        for phase, (node_id, raw) in cases.items():
            with self.subTest(phase=phase):
                run_dir = self.base / f"resume-{phase}-input"
                await self._interrupt_after_child_aggregation(
                    raw, run_dir, node_id=node_id
                )

                class TamperedRecoveredInputScheduler(TrustedControlFlowScheduler):
                    def _restore(inner_self) -> None:
                        super()._restore()
                        child = next(
                            iter(inner_self.entries[node_id]["children"].values())
                        )
                        input_id = child["input_artifact"]["$artifact"]["task_id"]
                        replacement: Any
                        if phase == "map":
                            replacement = {"name": "different-source-item"}
                        else:
                            replacement = {
                                "index": child["index"],
                                "source_child_id": child["source_child_id"],
                                "candidate_output": {"forged": True},
                                "candidate_artifact": None,
                            }
                        child["input_artifact"] = inner_self.store.put_json(
                            input_id, replacement
                        )

                executor = FakeExecutor(discover_count=2)
                resumed = TamperedRecoveredInputScheduler(
                    raw,
                    run_dir,
                    execute_agent=executor,
                    limits=self.limits,
                )

                summary = await resumed.run(resume=True)

                recovered = next(
                    node for node in summary["nodes"] if node["id"] == node_id
                )
                self.assertEqual(recovered["status"], "failed")
                self.assertIn("input artifact", recovered["error"])
                self.assertEqual(executor.calls, [])

    async def test_resume_reuses_completed_verify_children_after_aggregation_interrupt(
        self,
    ) -> None:
        raw = workflow_ir(max_agents=8, include_reduce=False)
        run_dir = self.base / "resume-after-verify-aggregation"
        await self._interrupt_after_child_aggregation(
            raw, run_dir, node_id="checked"
        )

        executor = FakeExecutor(discover_count=2)
        resumed = TrustedControlFlowScheduler(
            raw,
            run_dir,
            execute_agent=executor,
            limits=self.limits,
        )

        summary = await resumed.run(resume=True)

        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(executor.calls, [])
        checked = next(node for node in summary["nodes"] if node["id"] == "checked")
        self.assertEqual(checked["status"], "succeeded")

    async def test_verify_rejects_noncanonical_map_manifest_before_dispatch(
        self,
    ) -> None:
        cases = {
            "version": lambda manifest: manifest.__setitem__(
                "manifest_version", 1.0
            ),
            "item_count": lambda manifest: manifest.__setitem__("item_count", 3),
            "unique": lambda manifest: manifest["items"][1].__setitem__("index", 0),
            "child identity": lambda manifest: manifest["items"][1].__setitem__(
                "child_id", "forged-map-child"
            ),
            "persisted map child evidence": lambda manifest: manifest[
                "items"
            ][0].__setitem__("input_artifact", None),
        }

        for expected_error, mutate in cases.items():
            with self.subTest(expected_error=expected_error):
                executor = FakeExecutor(discover_count=2)

                class TamperedManifestScheduler(TrustedControlFlowScheduler):
                    def _load_result_value(self, node_id: str) -> Any:
                        value = super()._load_result_value(node_id)
                        if node_id == "mapped":
                            value = json.loads(json.dumps(value))
                            mutate(value)
                        return value

                scheduler = TamperedManifestScheduler(
                    workflow_ir(include_reduce=False),
                    self.base / f"manifest-{expected_error.replace(' ', '-')}",
                    execute_agent=executor,
                    limits=self.limits,
                )

                summary = await scheduler.run()

                checked = next(
                    node for node in summary["nodes"] if node["id"] == "checked"
                )
                self.assertEqual(checked["status"], "failed")
                self.assertIn(expected_error, checked["error"])
                self.assertEqual(checked["children"], {})
                self.assertFalse(
                    any("_verify_" in task_id for task_id in executor.calls)
                )

    async def test_verify_rejects_truncated_manifest_against_source_before_dispatch(
        self,
    ) -> None:
        class TruncatedManifestScheduler(TrustedControlFlowScheduler):
            def _load_result_value(inner_self, node_id: str) -> Any:
                value = super()._load_result_value(node_id)
                if node_id == "mapped":
                    value = json.loads(json.dumps(value))
                    value["items"].pop()
                    value["item_count"] = len(value["items"])
                return value

        executor = FakeExecutor(discover_count=2)
        scheduler = TruncatedManifestScheduler(
            workflow_ir(include_reduce=False),
            self.base / "truncated-manifest",
            execute_agent=executor,
            limits=self.limits,
        )

        summary = await scheduler.run()

        checked = next(node for node in summary["nodes"] if node["id"] == "checked")
        self.assertEqual(checked["status"], "failed")
        self.assertIn("source", checked["error"])
        self.assertFalse(any("_verify_" in task_id for task_id in executor.calls))

    async def test_verify_rejects_persisted_map_child_set_mismatch_before_dispatch(
        self,
    ) -> None:
        def add_child(children: dict[str, Any]) -> None:
            children["unexpected-map-child"] = {
                "id": "unexpected-map-child",
                "index": 2,
                "status": "succeeded",
            }

        def remove_child(children: dict[str, Any]) -> None:
            children.pop(next(reversed(children)))

        def forge_identity(children: dict[str, Any]) -> None:
            next(iter(children.values()))["id"] = "forged-map-child"

        for label, mutate in {
            "extra": add_child,
            "missing": remove_child,
            "identity": forge_identity,
        }.items():
            with self.subTest(label=label):
                class TamperedMapChildrenScheduler(TrustedControlFlowScheduler):
                    def _load_result_value(inner_self, node_id: str) -> Any:
                        value = super()._load_result_value(node_id)
                        if node_id == "mapped" and not hasattr(
                            inner_self, "_map_children_tampered"
                        ):
                            inner_self._map_children_tampered = True
                            mutate(inner_self.entries["mapped"]["children"])
                        return value

                executor = FakeExecutor(discover_count=2)
                scheduler = TamperedMapChildrenScheduler(
                    workflow_ir(include_reduce=False),
                    self.base / f"map-child-set-{label}",
                    execute_agent=executor,
                    limits=self.limits,
                )

                summary = await scheduler.run()

                checked = next(
                    node for node in summary["nodes"] if node["id"] == "checked"
                )
                self.assertEqual(checked["status"], "failed")
                self.assertIn("map child", checked["error"])
                self.assertFalse(
                    any("_verify_" in task_id for task_id in executor.calls)
                )

    async def test_verify_accepts_semantically_reordered_map_manifest(self) -> None:
        class ReorderedManifestScheduler(TrustedControlFlowScheduler):
            def _load_result_value(self, node_id: str) -> Any:
                value = super()._load_result_value(node_id)
                if node_id != "mapped":
                    return value
                manifest = json.loads(json.dumps(value))
                manifest["items"] = [
                    {key: item[key] for key in reversed(list(item))}
                    for item in reversed(manifest["items"])
                ]
                return {
                    key: manifest[key]
                    for key in reversed(list(manifest))
                }

        executor = FakeExecutor(discover_count=2)
        scheduler = ReorderedManifestScheduler(
            workflow_ir(include_reduce=False),
            self.base / "reordered-manifest",
            execute_agent=executor,
            limits=self.limits,
        )

        summary = await scheduler.run()

        self.assertTrue(summary["all_succeeded"])
        checked = next(
            node for node in summary["nodes"] if node["id"] == "checked"
        )
        self.assertEqual(checked["status"], "succeeded")
        checked_manifest = ArtifactStore(
            Path(summary["run_dir"]), self.limits
        ).load_json(checked["output_artifact"])
        self.assertEqual(checked_manifest["item_count"], 2)
        self.assertEqual(
            len([task_id for task_id in executor.calls if "_verify_" in task_id]),
            2,
        )

    async def test_map_setup_failure_cancels_and_drains_sibling(self) -> None:
        sibling_started = asyncio.Event()
        sibling_cancelled = asyncio.Event()
        sibling_completed = asyncio.Event()
        release_sibling = asyncio.Event()

        async def executor(task, results, prior_entry):
            del results, prior_entry
            task_id = task["id"]
            if task_id == "discover":
                output: Any = [{"name": "slow"}, {"name": "setup-failure"}]
            elif "_map_0000_" in task_id:
                sibling_started.set()
                try:
                    await release_sibling.wait()
                except asyncio.CancelledError:
                    sibling_cancelled.set()
                    raise
                sibling_completed.set()
                output = {"finding": task_id}
            else:
                self.fail(f"unexpected executor call: {task_id}")
            return {
                "id": task_id,
                "status": "succeeded",
                "output": output,
                "output_artifact": None,
                "error": None,
                "attempts": [],
            }

        raw = workflow_ir(max_agents=8, include_reduce=False)
        raw["nodes"] = raw["nodes"][:2]
        scheduler = TrustedControlFlowScheduler(
            raw,
            self.base / "fanout-setup-failure",
            execute_agent=executor,
            limits=self.limits,
        )
        original_put_json = scheduler.store.put_json

        def fail_second_map_input(task_id: str, value: Any):
            if "mapped_mapin_0001_" in task_id:
                raise RuntimeError("fixture setup failure")
            return original_put_json(task_id, value)

        scheduler.store.put_json = fail_second_map_input

        summary = await scheduler.run()
        try:
            self.assertTrue(sibling_started.is_set())
            self.assertTrue(sibling_cancelled.is_set())
            self.assertFalse(sibling_completed.is_set())
            mapped = next(
                node for node in summary["nodes"] if node["id"] == "mapped"
            )
            self.assertEqual(mapped["status"], "failed")
            self.assertEqual(
                sorted(child["status"] for child in mapped["children"].values()),
                ["cancelled", "failed"],
            )
        finally:
            release_sibling.set()
            await asyncio.sleep(0.01)
        self.assertFalse(sibling_completed.is_set())

    async def test_verify_setup_failure_cancels_and_drains_sibling(self) -> None:
        sibling_started = asyncio.Event()
        sibling_cancelled = asyncio.Event()
        sibling_completed = asyncio.Event()
        release_sibling = asyncio.Event()

        async def executor(task, results, prior_entry):
            del results, prior_entry
            task_id = task["id"]
            if task_id == "discover":
                output: Any = [{"name": "slow"}, {"name": "setup-failure"}]
            elif "_map_" in task_id:
                output = {"finding": task_id}
            elif "_verify_0000_" in task_id:
                sibling_started.set()
                try:
                    await release_sibling.wait()
                except asyncio.CancelledError:
                    sibling_cancelled.set()
                    raise
                sibling_completed.set()
                output = {
                    "verdict": "accept",
                    "summary": f"accept:{task_id}",
                    "evidence": ["fixture"],
                }
            else:
                self.fail(f"unexpected executor call: {task_id}")
            return {
                "id": task_id,
                "status": "succeeded",
                "output": output,
                "output_artifact": None,
                "error": None,
                "attempts": [],
            }

        scheduler = TrustedControlFlowScheduler(
            workflow_ir(max_agents=8, include_reduce=False),
            self.base / "verify-fanout-setup-failure",
            execute_agent=executor,
            limits=self.limits,
        )
        original_put_json = scheduler.store.put_json

        def fail_second_verify_input(task_id: str, value: Any):
            if "checked_verifyin_0001_" in task_id:
                raise RuntimeError("fixture verify setup failure")
            return original_put_json(task_id, value)

        scheduler.store.put_json = fail_second_verify_input

        summary = await scheduler.run()
        try:
            self.assertTrue(sibling_started.is_set())
            self.assertTrue(sibling_cancelled.is_set())
            self.assertFalse(sibling_completed.is_set())
            checked = next(
                node for node in summary["nodes"] if node["id"] == "checked"
            )
            self.assertEqual(checked["status"], "failed")
            self.assertEqual(
                sorted(child["status"] for child in checked["children"].values()),
                ["cancelled", "failed"],
            )
        finally:
            release_sibling.set()
            await asyncio.sleep(0.01)
        self.assertFalse(sibling_completed.is_set())

    async def test_executor_failure_does_not_cancel_map_sibling(self) -> None:
        async def executor(task, results, prior_entry):
            del results, prior_entry
            task_id = task["id"]
            if task_id == "discover":
                output: Any = [{"name": "failure"}, {"name": "success"}]
            elif "_map_0000_" in task_id:
                raise RuntimeError("fixture executor failure")
            elif "_map_0001_" in task_id:
                output = {"finding": task_id}
            else:
                self.fail(f"unexpected executor call: {task_id}")
            return {
                "id": task_id,
                "status": "succeeded",
                "output": output,
                "output_artifact": None,
                "error": None,
                "attempts": [],
            }

        raw = workflow_ir(max_agents=8, include_reduce=False)
        raw["nodes"] = raw["nodes"][:2]
        scheduler = TrustedControlFlowScheduler(
            raw,
            self.base / "executor-child-failure",
            execute_agent=executor,
            limits=self.limits,
        )

        summary = await scheduler.run()

        mapped = next(
            node for node in summary["nodes"] if node["id"] == "mapped"
        )
        self.assertEqual(mapped["status"], "failed")
        self.assertEqual(
            sorted(child["status"] for child in mapped["children"].values()),
            ["failed", "succeeded"],
        )


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
