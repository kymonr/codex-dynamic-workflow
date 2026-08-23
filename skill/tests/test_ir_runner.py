from __future__ import annotations

import contextlib
import hashlib
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

import ir_runner
from runtime.limits import RuntimeLimits
from runtime.human_gate import HumanGateStore
from runtime.workflow_ir import validate_workflow_ir

WorkflowIRValidationError = ir_runner.WorkflowIRValidationError

FAKE_IR_CODEX = Path(__file__).with_name("fake_ir_codex.py")


def gate_cli_ir(workdir: Path) -> dict:
    return {
        "version": 3,
        "name": "ir-resume-gate-test",
        "mode": "workflow",
        "objective": "exercise CLI resume through a rejected human gate",
        "workdir": str(workdir),
        "budgets": {
            "max_agents": 6,
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
                    "prompt": "IR_GATE_CANDIDATE",
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
                "id": "choose",
                "kind": "conditional",
                "depends_on": ["approval"],
                "config": {
                    "condition": {
                        "source": "approval",
                        "pointer": "/decision",
                        "operator": "eq",
                        "value": "approve",
                    },
                    "then": ["accept"],
                    "else": ["reject"],
                },
            },
            {
                "id": "accept",
                "kind": "agent",
                "depends_on": ["choose"],
                "config": {
                    "profile": "luna",
                    "prompt": "IR_GATE_ACCEPT",
                    "access": "read_only",
                },
            },
            {
                "id": "reject",
                "kind": "agent",
                "depends_on": ["choose"],
                "config": {
                    "profile": "luna",
                    "prompt": "IR_GATE_REJECT",
                    "access": "read_only",
                },
            },
            {
                "id": "join",
                "kind": "agent",
                "depends_on": ["accept", "reject"],
                "dependency_policy": "join",
                "config": {
                    "profile": "luna",
                    "prompt": "IR_GATE_JOIN",
                    "access": "read_only",
                },
            },
        ],
    }


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

    def _normalize_resolved(self, raw: dict) -> tuple[dict, RuntimeLimits]:
        return ir_runner._normalize_resolved_ir_for_resume(
            raw,
            allowed_roots=[str(self.workdir.parent)],
            allowed_sensitive_paths=[],
            codex_home=self.codex_home,
        )

    def test_declared_execution_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "unknown Workflow IR keys"
        ):
            ir_runner._normalize_declared_ir(
                self.ir(),
                allowed_roots=[str(self.workdir.parent)],
                allowed_sensitive_paths=[],
                codex_home=self.codex_home,
            )

    def test_valid_persisted_execution_is_recomputed_and_accepted(self) -> None:
        resolved = self.ir()
        normalized, limits = self._normalize_resolved(resolved)

        self.assertEqual(normalized["execution"], resolved["execution"])
        self.assertEqual(limits.to_dict(), self.limits.to_dict())
        self.assertEqual(normalized["workdir"], str(self.workdir.resolve()))

    def test_resume_execution_must_be_present_and_exact(self) -> None:
        resolved = self.ir()
        cases = {
            "missing": {
                key: value for key, value in resolved.items() if key != "execution"
            },
            "malformed": {**resolved, "execution": ["not-an-object"]},
            "extra": {
                **resolved,
                "execution": {
                    **resolved["execution"],
                    "unexpected": False,
                },
            },
            "tampered": {
                **resolved,
                "execution": {
                    **resolved["execution"],
                    "runtime_version_required": 99,
                },
            },
            "type-mismatch": {
                **resolved,
                "execution": {
                    **resolved["execution"],
                    "static_v2_compilable": 1,
                },
            },
        }
        for label, candidate in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(WorkflowIRValidationError):
                    self._normalize_resolved(candidate)

    def test_resume_other_unknown_top_level_key_is_rejected(self) -> None:
        resolved = self.ir()
        resolved["unexpected"] = "must reject"
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "unknown Workflow IR keys"
        ):
            self._normalize_resolved(resolved)

    def test_cli_tampered_resume_fails_before_identity_and_scheduler(self) -> None:
        runs_root = self.base / "runs"
        run_dir = runs_root / "tampered"
        run_dir.mkdir(parents=True)
        resolved_path = run_dir / "workflow-ir.resolved.json"
        resolved = self.ir()
        resolved["execution"]["runtime_version_required"] = 99
        resolved_path.write_text(
            json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        before_bytes = resolved_path.read_bytes()
        before_hash = hashlib.sha256(before_bytes).hexdigest()
        before_mtime = resolved_path.stat().st_mtime_ns

        with mock.patch.dict(
            os.environ, {"DYNWF_RUNS_ROOT": str(runs_root)}, clear=False
        ):
            with mock.patch.object(
                ir_runner.legacy,
                "resolve_codex_home",
                return_value=self.codex_home,
            ), mock.patch.object(
                ir_runner.legacy,
                "resolve_role_configs",
                side_effect=AssertionError("role configs must not resolve"),
            ), mock.patch.object(
                ir_runner.legacy,
                "resolve_codex_prefix",
                side_effect=AssertionError("Codex identity must not resolve"),
            ), mock.patch.object(
                ir_runner.legacy,
                "_prepare_run_root",
                side_effect=AssertionError("run root must not prepare"),
            ), mock.patch.object(
                ir_runner,
                "_run",
                side_effect=AssertionError("scheduler must not run"),
            ):
                with contextlib.redirect_stdout(
                    io.StringIO()
                ), contextlib.redirect_stderr(io.StringIO()):
                    code = ir_runner.main(
                        [
                            "resume-ir",
                            "--run-dir",
                            str(run_dir),
                            "--allowed-root",
                            str(self.workdir.parent),
                            "--ack-external-model-export",
                        ]
                    )

        self.assertEqual(code, 1)
        self.assertEqual(resolved_path.read_bytes(), before_bytes)
        self.assertEqual(
            hashlib.sha256(resolved_path.read_bytes()).hexdigest(), before_hash
        )
        self.assertEqual(resolved_path.stat().st_mtime_ns, before_mtime)
        self.assertFalse((run_dir / "tasks").exists())
        self.assertFalse((run_dir / "events.jsonl").exists())

    def test_cli_resume_consumes_reject_gate_and_completes_terminal_join(self) -> None:
        runs_root = self.base / "runs"
        run_dir = runs_root / "gate-flow"
        spec_path = self.base / "gate-spec.json"
        spec_path.write_text(
            json.dumps(gate_cli_ir(self.workdir), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        codex_identity = {
            "codex_executable": str(FAKE_IR_CODEX),
            "codex_version": "offline-fixture",
            "codex_signature_status": "not_applicable",
            "codex_signer_subject": None,
        }
        cli_args = [
            "run-ir",
            "--spec",
            str(spec_path),
            "--run-dir",
            str(run_dir),
            "--allowed-root",
            str(self.workdir.parent),
            "--ack-external-model-export",
        ]
        resume_args = [
            "resume-ir",
            "--run-dir",
            str(run_dir),
            "--allowed-root",
            str(self.workdir.parent),
            "--ack-external-model-export",
        ]
        with mock.patch.dict(
            os.environ, {"DYNWF_RUNS_ROOT": str(runs_root)}, clear=False
        ), mock.patch.object(
            ir_runner.legacy,
            "resolve_codex_home",
            return_value=self.codex_home,
        ), mock.patch.object(
            ir_runner.legacy,
            "resolve_role_configs",
            return_value=role_configs(),
        ), mock.patch.object(
            ir_runner.legacy,
            "resolve_codex_prefix",
            return_value=([sys.executable, str(FAKE_IR_CODEX)], codex_identity),
        ):
            with contextlib.redirect_stdout(
                io.StringIO()
            ), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ir_runner.main(cli_args), 3)

            resolved_path = run_dir / "workflow-ir.resolved.json"
            resolved_bytes = resolved_path.read_bytes()
            resolved_hash = hashlib.sha256(resolved_bytes).hexdigest()
            resolved_mtime = resolved_path.stat().st_mtime_ns
            paused_summary = json.loads(
                (run_dir / "summary.json").read_text(encoding="utf-8")
            )
            paused_checkpoint = json.loads(
                (run_dir / "checkpoint.json").read_text(encoding="utf-8")
            )
            self.assertEqual(paused_summary["ir_digest"], paused_checkpoint["ir_digest"])
            paused_states = {
                node["id"]: node["status"] for node in paused_summary["nodes"]
            }
            self.assertEqual(paused_states["candidate"], "succeeded")
            self.assertEqual(paused_states["approval"], "waiting")
            self.assertEqual(paused_states["accept"], "pending")
            self.assertEqual(paused_states["reject"], "pending")
            self.assertEqual(paused_states["join"], "pending")
            self.assertEqual(
                len(list((run_dir / "tasks" / "candidate").glob("attempt-*"))),
                1,
            )
            self.assertFalse((run_dir / "tasks" / "reject").exists())

            store = HumanGateStore(run_dir, self.limits)
            waiting = store.load("approval")
            store.decide(
                "approval",
                decision="reject",
                actor="fixture-user",
                source="user",
                expected_input_identity=waiting["input_identity"],
                note="reject branch selected",
            )

            with contextlib.redirect_stdout(
                io.StringIO()
            ), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ir_runner.main(resume_args), 0)

        final_summary = json.loads(
            (run_dir / "summary.json").read_text(encoding="utf-8")
        )
        final_checkpoint = json.loads(
            (run_dir / "checkpoint.json").read_text(encoding="utf-8")
        )
        final_states = {
            node["id"]: node["status"] for node in final_summary["nodes"]
        }
        self.assertEqual(final_states["approval"], "succeeded")
        self.assertEqual(final_states["choose"], "succeeded")
        self.assertEqual(final_states["accept"], "skipped")
        self.assertEqual(final_states["reject"], "succeeded")
        self.assertEqual(final_states["join"], "succeeded")
        self.assertTrue(final_summary["all_succeeded"])
        self.assertFalse(final_summary["paused"])
        self.assertEqual(final_summary["ir_digest"], paused_summary["ir_digest"])
        self.assertEqual(final_summary["ir_digest"], final_checkpoint["ir_digest"])
        self.assertTrue(
            all(status in {"succeeded", "skipped"} for status in final_states.values())
        )
        self.assertEqual(
            len(list((run_dir / "tasks" / "candidate").glob("attempt-*"))),
            1,
        )
        self.assertEqual(
            len(list((run_dir / "tasks" / "reject").glob("attempt-*"))), 1
        )
        self.assertEqual(
            len(list((run_dir / "tasks" / "join").glob("attempt-*"))), 1
        )
        self.assertFalse((run_dir / "tasks" / "accept").exists())
        self.assertEqual(resolved_path.read_bytes(), resolved_bytes)
        self.assertEqual(
            hashlib.sha256(resolved_path.read_bytes()).hexdigest(), resolved_hash
        )
        self.assertEqual(resolved_path.stat().st_mtime_ns, resolved_mtime)

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
