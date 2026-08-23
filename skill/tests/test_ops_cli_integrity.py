from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import ops_cli
from runtime.control_flow import TrustedControlFlowScheduler
from runtime.human_gate import HumanGateStore
from runtime.workflow_ir import validate_workflow_ir
from test_ops_cli import gate_ir, limits


class RunStatusIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runs_root = self.root / "runs"
        self.runs_root.mkdir()
        self.run_dir = self.runs_root / "fixture"
        self.run_dir.mkdir()
        self.limits = limits()

        self.resolved = validate_workflow_ir(gate_ir())
        self.resolved["limits"] = self.limits.to_dict()
        self.ir_digest = ops_cli._workflow_ir_digest(self.resolved)
        (self.run_dir / "workflow-ir.resolved.json").write_text(
            json.dumps(self.resolved), encoding="utf-8"
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
            "ir_digest": self.ir_digest,
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
            "ir_digest": self.ir_digest,
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
            input_identity="b" * 64,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self) -> tuple[int, dict]:
        with mock.patch.dict(
            os.environ,
            {"DYNWF_RUNS_ROOT": str(self.runs_root)},
            clear=False,
        ):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = ops_cli.main(
                    ["run-status", "--run-dir", str(self.run_dir)]
                )
        return code, json.loads(output.getvalue())

    def test_ops_digest_matches_scheduler_contract(self) -> None:
        async def never_execute(task, results, prior_entry):
            raise AssertionError("digest contract must not execute an agent")

        digest_dir = self.root / "digest-only"
        scheduler = TrustedControlFlowScheduler(
            self.resolved,
            digest_dir,
            execute_agent=never_execute,
            limits=self.limits,
        )
        self.assertEqual(self.ir_digest, scheduler.ir_digest)
        self.assertFalse(digest_dir.exists())

    def test_resolved_ir_digest_mismatch_is_reported(self) -> None:
        ir_path = self.run_dir / "workflow-ir.resolved.json"
        raw = json.loads(ir_path.read_text(encoding="utf-8"))
        raw["objective"] = "tampered objective"
        ir_path.write_text(json.dumps(raw), encoding="utf-8")

        code, result = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(result["resolved_ir_digest_consistency"], "mismatch")
        self.assertEqual(result["ir_digest_consistency"], "match")

    def test_checkpoint_entry_status_mismatch_is_rejected(self) -> None:
        checkpoint_path = self.run_dir / "checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["entries"]["approval"]["status"] = "succeeded"
        checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

        with mock.patch.dict(
            os.environ,
            {"DYNWF_RUNS_ROOT": str(self.runs_root)},
            clear=False,
        ):
            with contextlib.redirect_stderr(io.StringIO()) as error:
                code = ops_cli.main(
                    ["run-status", "--run-dir", str(self.run_dir)]
                )
        self.assertEqual(code, 1)
        self.assertIn("entry status disagrees", error.getvalue())

    def test_duplicate_summary_node_is_malformed(self) -> None:
        summary_path = self.run_dir / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["nodes"].append(dict(summary["nodes"][0]))
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        code, result = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(result["summary_state_consistency"], "malformed")


if __name__ == "__main__":
    unittest.main()
