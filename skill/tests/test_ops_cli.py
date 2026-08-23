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

import ops_cli
from runtime.human_gate import HumanGateStore
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import validate_workflow_ir


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


def plan_ir() -> dict[str, Any]:
    return {
        "version": 3,
        "name": "ops-preview",
        "mode": "workflow",
        "objective": "preview a bounded plan",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 8,
            "max_concurrency": 2,
            "max_iterations": 3,
            "max_tokens": 10000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
        },
        "nodes": [
            agent("source", [], "SOURCE"),
            {
                "id": "mapped",
                "kind": "map",
                "depends_on": ["source"],
                "config": {
                    "over": "source",
                    "item_limit": 2,
                    "template": {
                        "profile": "luna",
                        "prompt": "MAP {{item}}",
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
                    "prompt": "VERIFY {{candidate}}",
                    "require_all": True,
                    "access": "read_only",
                },
            },
        ],
    }


def gate_ir() -> dict[str, Any]:
    return {
        "version": 3,
        "name": "ops-status",
        "mode": "workflow",
        "objective": "report a paused run",
        "workdir": "/bounded/work",
        "budgets": {
            "max_agents": 4,
            "max_concurrency": 2,
            "max_iterations": 3,
            "max_tokens": 10000,
            "soft_timeout_seconds": 30,
            "hard_timeout_seconds": 60,
        },
        "nodes": [
            agent("source", [], "SOURCE"),
            {
                "id": "approval",
                "kind": "human_gate",
                "depends_on": ["source"],
                "config": {
                    "prompt": "Accept?",
                    "options": ["approve", "reject"],
                },
            },
        ],
    }


class PlanPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_plan_preview_is_read_only_and_projects_agent_claims(self) -> None:
        spec = self.root / "plan.json"
        spec.write_text(json.dumps(plan_ir()), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = ops_cli.main(["plan-ir", "--spec", str(spec)])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["operation"], "plan-ir")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["writes"], [])
        self.assertFalse(result["workdir_preflight"]["performed"])
        self.assertTrue(result["execution_supported"])
        self.assertEqual(
            result["topological_order"], ["source", "mapped", "checked"]
        )
        projection = result["agent_claim_projection"]
        self.assertEqual(projection["static_agent_claims"], 1)
        self.assertEqual(projection["map_child_upper_bound"], 2)
        self.assertEqual(projection["verify_child_upper_bound"], 2)
        self.assertEqual(projection["total_upper_bound"], 5)
        self.assertTrue(projection["upper_bound_within_budget"])
        self.assertNotIn("prompt", result["nodes"][0])
        self.assertEqual(result["nodes"][0]["prompt_preview"], "SOURCE")

    def test_validated_only_loop_is_visible_but_not_executable(self) -> None:
        raw = plan_ir()
        raw["nodes"] = [
            raw["nodes"][0],
            {
                "id": "future-loop",
                "kind": "loop",
                "depends_on": ["source"],
                "config": {
                    "max_iterations": 2,
                    "body": ["source"],
                    "stop_when": "verified",
                },
            },
        ]
        result = ops_cli._plan_preview(raw)
        self.assertFalse(result["execution_supported"])
        self.assertEqual(
            result["execution"]["unsupported_node_kinds"], ["loop"]
        )

    def test_reference_workflow_is_valid_and_within_agent_budget(self) -> None:
        example = (
            SKILL_DIR.parent
            / "examples"
            / "reference-repository-audit.workflow-ir.json"
        )
        raw = json.loads(example.read_text(encoding="utf-8"))
        result = ops_cli._plan_preview(raw)
        self.assertTrue(result["execution_supported"])
        self.assertTrue(
            result["agent_claim_projection"]["upper_bound_within_budget"]
        )
        kinds = {node["kind"] for node in result["nodes"]}
        self.assertTrue(
            {"agent", "map", "verify", "reduce", "conditional", "human_gate"}
            <= kinds
        )


class RunStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runs_root = self.root / "runs"
        self.runs_root.mkdir()
        self.run_dir = self.runs_root / "fixture"
        self.run_dir.mkdir()
        self.limits = limits()
        resolved = validate_workflow_ir(gate_ir())
        resolved["limits"] = self.limits.to_dict()
        (self.run_dir / "workflow-ir.resolved.json").write_text(
            json.dumps(resolved), encoding="utf-8"
        )
        states = {"source": "succeeded", "approval": "waiting"}
        entries = {
            "source": {
                "id": "source",
                "status": "succeeded",
                "started": "2026-08-23T00:00:00Z",
                "finished": "2026-08-23T00:00:01Z",
                "resume_count": 0,
                "error": None,
            },
            "approval": {
                "id": "approval",
                "status": "waiting",
                "started": "2026-08-23T00:00:01Z",
                "finished": None,
                "resume_count": 0,
                "error": "explicit human decision required",
                "gate": {"status": "waiting"},
            },
        }
        checkpoint = {
            "runtime": "workflow-ir-v3",
            "ir_digest": "fixture-digest",
            "started": "2026-08-23T00:00:00Z",
            "finished": None,
            "states": states,
            "entries": entries,
            "claimed_agents": ["source"],
        }
        (self.run_dir / "checkpoint.json").write_text(
            json.dumps(checkpoint), encoding="utf-8"
        )
        summary = {
            "runtime": "workflow-ir-v3",
            "ir_digest": "fixture-digest",
            "started": "2026-08-23T00:00:00Z",
            "finished": None,
            "paused": True,
            "nodes": [
                {"id": "source", "status": "succeeded"},
                {"id": "approval", "status": "waiting"},
            ],
        }
        (self.run_dir / "summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        HumanGateStore(self.run_dir, self.limits).open_gate(
            "approval",
            prompt="Accept?",
            options=["approve", "reject"],
            input_identity="a" * 64,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, *extra: str) -> tuple[int, dict[str, Any]]:
        with mock.patch.dict(
            os.environ,
            {"DYNWF_RUNS_ROOT": str(self.runs_root)},
            clear=False,
        ):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = ops_cli.main(
                    ["run-status", "--run-dir", str(self.run_dir), *extra]
                )
        return code, json.loads(output.getvalue())

    def test_run_status_uses_checkpoint_without_advancing_run(self) -> None:
        before = {
            path.name: path.stat().st_mtime_ns
            for path in self.run_dir.iterdir()
            if path.is_file()
        }
        code, result = self._run()
        after = {
            path.name: path.stat().st_mtime_ns
            for path in self.run_dir.iterdir()
            if path.is_file()
        }
        self.assertEqual(code, 0)
        self.assertEqual(before, after)
        self.assertEqual(result["operation"], "run-status")
        self.assertEqual(result["source_of_truth"], "checkpoint.json")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["writes"], [])
        self.assertEqual(result["workflow_state"], "paused")
        self.assertTrue(result["paused"])
        self.assertEqual(result["summary_state_consistency"], "match")
        self.assertEqual(result["ir_digest_consistency"], "match")
        self.assertEqual(result["counts"], {"waiting": 1, "succeeded": 1})
        self.assertEqual(result["gates"][0]["status"], "waiting")
        self.assertNotIn("prompt", result["gates"][0])

    def test_node_filter_returns_only_requested_node(self) -> None:
        code, result = self._run("--node-id", "approval")
        self.assertEqual(code, 0)
        self.assertEqual([node["id"] for node in result["nodes"]], ["approval"])

    def test_summary_mismatch_is_reported_without_overriding_checkpoint(self) -> None:
        summary_path = self.run_dir / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["nodes"][1]["status"] = "succeeded"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        code, result = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(result["summary_state_consistency"], "mismatch")
        approval = next(node for node in result["nodes"] if node["id"] == "approval")
        self.assertEqual(approval["status"], "waiting")

    def test_run_directory_outside_runs_root_is_rejected(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        with mock.patch.dict(
            os.environ,
            {"DYNWF_RUNS_ROOT": str(self.runs_root)},
            clear=False,
        ):
            with contextlib.redirect_stderr(io.StringIO()) as error:
                code = ops_cli.main(
                    ["run-status", "--run-dir", str(outside)]
                )
        self.assertEqual(code, 1)
        self.assertIn("must be a child", error.getvalue())


if __name__ == "__main__":
    unittest.main()
