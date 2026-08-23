from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import ir_runner
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import validate_workflow_ir

FAKE_IR_CODEX = Path(__file__).with_name("fake_ir_codex.py")


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


class WorkflowIRRunnerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workdir = self.base / "allowed" / "work"
        self.workdir.mkdir(parents=True)
        self.codex_home = self.base / "codex-home"
        self.codex_home.mkdir()
        self.run_dir = self.base / "runs" / "ir-run"
        self.limits = RuntimeLimits.from_mapping(
            {
                "max_result_bytes": 1024 * 1024,
                "max_log_bytes": 1024 * 1024,
                "max_run_artifact_bytes": 32 * 1024 * 1024,
                "max_upstream_inline_bytes": 128,
                "max_event_bytes": 64 * 1024,
            }
        )

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    def ir(self) -> dict:
        raw = {
            "version": 3,
            "name": "ir-adapter-test",
            "mode": "workflow",
            "objective": "exercise the v2 agent adapter",
            "workdir": str(self.workdir),
            "budgets": {
                "max_agents": 8,
                "max_concurrency": 2,
                "max_iterations": 3,
                "max_tokens": 100000,
                "soft_timeout_seconds": 30,
                "hard_timeout_seconds": 60,
            },
            "limits": self.limits.to_dict(),
            "nodes": [
                {
                    "id": "discover",
                    "kind": "agent",
                    "depends_on": [],
                    "config": {
                        "profile": "luna",
                        "prompt": "IR_DISCOVER",
                        "output_schema": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {"name": {"type": "string"}},
                                "required": ["name"],
                            },
                        },
                        "access": "read_only",
                    },
                },
                {
                    "id": "mapped",
                    "kind": "map",
                    "depends_on": ["discover"],
                    "config": {
                        "over": "discover",
                        "template": {
                            "profile": "luna",
                            "prompt": "IR_MAP item={{item}} index={{index}}",
                            "output_schema": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "finding": {"type": "string"}
                                },
                                "required": ["finding"],
                            },
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
                        "prompt": "IR_VERIFY candidate={{candidate}} index={{index}}",
                        "access": "read_only",
                    },
                },
                {
                    "id": "synthesize",
                    "kind": "reduce",
                    "depends_on": ["checked"],
                    "config": {
                        "over": "checked",
                        "profile": "sol",
                        "prompt": "IR_REDUCE source={{source}}",
                        "output_schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "summary": {"type": "string"}
                            },
                            "required": ["summary"],
                        },
                        "access": "read_only",
                    },
                },
            ],
        }
        return validate_workflow_ir(raw)

    async def test_full_ir_pipeline_uses_existing_agent_executor(self) -> None:
        ir = self.ir()
        preflight = {
            "ack_external_model_export": True,
            "allowed_roots": [str(self.workdir.parent)],
            "allowed_sensitive_paths": [],
            "codex_home": str(self.codex_home),
            "codex_executable": str(FAKE_IR_CODEX),
            "codex_version": "offline-fixture",
            "codex_signature_status": "not_applicable",
            "codex_signer_subject": None,
        }
        summary = await ir_runner._run(
            ir,
            self.run_dir,
            resume=False,
            codex_prefix=[sys.executable, str(FAKE_IR_CODEX)],
            role_configs=role_configs(),
            preflight=preflight,
            limits=self.limits,
        )
        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(summary["succeeded_count"], 4)
        self.assertEqual(summary["claimed_agent_count"], 6)
        self.assertTrue((self.run_dir / "summary.json").is_file())
        self.assertTrue((self.run_dir / "checkpoint.json").is_file())
        self.assertTrue((self.run_dir / "events.jsonl").is_file())
        self.assertTrue((self.run_dir / "artifacts").is_dir())
        task_dirs = list((self.run_dir / "tasks").iterdir())
        self.assertEqual(len(task_dirs), 6)


if __name__ == "__main__":
    unittest.main()
