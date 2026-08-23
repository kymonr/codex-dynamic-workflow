from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dynamic_workflow_runner", SKILL / "runner.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
FAKE = Path(__file__).with_name("fake_codex.py")


def role_configs():
    return {
        "spark": {"role":"spark","model":"gpt-5.3-codex-spark","effort":"high","tier":None,"source":"fixture"},
        "luna": {"role":"luna","model":"gpt-5.6-luna","effort":"max","tier":"fast","source":"fixture"},
        "sol": {"role":"sol","model":"gpt-5.6-sol","effort":"xhigh","tier":None,"source":"fixture"},
    }


class RunnerCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_small_dag_contract_still_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workdir = base / "work"
            workdir.mkdir()
            spec = {
                "version": 2,
                "name": "compat",
                "workdir": str(workdir),
                "max_concurrency": 2,
                "soft_timeout_seconds": 30,
                "hard_timeout_seconds": 60,
                "tasks": [
                    {"id":"one","prompt":"FAKE_OK","role":"luna","route_reason":"fixture","depends_on":[],"output_schema":None,"allow_escalation":False},
                    {"id":"two","prompt":"FAKE_ECHO_UPSTREAM {{result:one}}","role":"luna","route_reason":"fixture","depends_on":["one"],"output_schema":None,"allow_escalation":False},
                ],
                "legacy_spec_converted": False,
                "preflight": {
                    "ack_external_model_export": False,
                    "allowed_roots": [str(workdir)],
                    "allowed_sensitive_paths": [],
                    "codex_home": str(base / "codex-home"),
                    "codex_executable": None,
                    "codex_version": None,
                    "codex_signature_status": None,
                    "codex_signer_subject": None,
                },
            }
            summary = await runner.run_workflow(
                spec,
                base / "run",
                [sys.executable, str(FAKE)],
                role_configs(),
            )
            self.assertTrue(summary["all_succeeded"])
            self.assertEqual(summary["tasks"][1]["output"], "boundary-ok")
            self.assertTrue((base / "run" / "checkpoint.json").is_file())
            self.assertTrue((base / "run" / "events.jsonl").is_file())

    async def test_resume_requeues_checkpointed_pending_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workdir = base / "work"
            workdir.mkdir()
            task = {"id":"one","prompt":"FAKE_OK","role":"luna","route_reason":"fixture","depends_on":[],"output_schema":None,"allow_escalation":False}
            spec = {
                "version": 2, "name": "resume-compat", "workdir": str(workdir),
                "max_concurrency": 1, "soft_timeout_seconds": 30, "hard_timeout_seconds": 60,
                "tasks": [task], "legacy_spec_converted": False,
                "preflight": {"ack_external_model_export":False,"allowed_roots":[str(workdir)],"allowed_sensitive_paths":[],"codex_home":str(base / "codex-home"),"codex_executable":None,"codex_version":None,"codex_signature_status":None,"codex_signer_subject":None},
            }
            limits = runner.RuntimeLimits.from_mapping(None, env={})
            spec["limits"] = limits.to_dict()
            run_dir = base / "resume-run"
            (run_dir / "tasks").mkdir(parents=True)
            runner._atomic_write_json(run_dir / "spec.resolved.json", spec)
            entry = runner._base_entry(task, role_configs())
            store = runner.RunStateStore(run_dir, max_event_bytes=limits.max_event_bytes)
            store.append_event("run.created", {"name":"resume-compat"})
            store.write_checkpoint({"name":"resume-compat","spec_digest":runner.spec_digest(spec),"started":"now","finished":None,"states":{"one":"pending"},"entries":{"one":entry}})
            summary = await runner.run_workflow(spec, run_dir, [sys.executable, str(FAKE)], role_configs(), resume=True)
            self.assertTrue(summary["all_succeeded"])
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("run.resumed", events)

    async def test_oversized_log_is_failed_and_retained_at_the_hard_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workdir = base / "work"
            workdir.mkdir()
            task = {"id":"one","prompt":"FAKE_BIG_LOG","role":"luna","route_reason":"fixture","depends_on":[],"output_schema":None,"allow_escalation":False}
            spec = {
                "version":2,"name":"big-log","workdir":str(workdir),
                "max_concurrency":1,"soft_timeout_seconds":30,"hard_timeout_seconds":60,
                "limits":{"max_result_bytes":4096,"max_log_bytes":4096,"max_run_artifact_bytes":1048576,"max_upstream_inline_bytes":256,"max_event_bytes":4096},
                "tasks":[task],"legacy_spec_converted":False,
                "preflight":{"ack_external_model_export":False,"allowed_roots":[str(workdir)],"allowed_sensitive_paths":[],"codex_home":str(base / "codex-home"),"codex_executable":None,"codex_version":None,"codex_signature_status":None,"codex_signer_subject":None},
            }
            run_dir = base / "run"
            summary = await runner.run_workflow(spec, run_dir, [sys.executable, str(FAKE)], role_configs())
            self.assertEqual(summary["tasks"][0]["status"], "failed")
            log_path = next((run_dir / "tasks" / "one").glob("attempt-*/agent.log"))
            self.assertLessEqual(log_path.stat().st_size, 4096)
            self.assertIn("artifact limit exceeded", summary["tasks"][0]["error"])

    async def test_oversized_structured_output_is_deleted_and_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workdir = base / "work"
            workdir.mkdir()
            task = {"id":"one","prompt":"FAKE_BIG_OUTPUT","role":"luna","route_reason":"fixture","depends_on":[],"output_schema":None,"allow_escalation":False}
            spec = {
                "version":2,"name":"big-output","workdir":str(workdir),
                "max_concurrency":1,"soft_timeout_seconds":30,"hard_timeout_seconds":60,
                "limits":{"max_result_bytes":4096,"max_log_bytes":8192,"max_run_artifact_bytes":1048576,"max_upstream_inline_bytes":256,"max_event_bytes":4096},
                "tasks":[task],"legacy_spec_converted":False,
                "preflight":{"ack_external_model_export":False,"allowed_roots":[str(workdir)],"allowed_sensitive_paths":[],"codex_home":str(base / "codex-home"),"codex_executable":None,"codex_version":None,"codex_signature_status":None,"codex_signer_subject":None},
            }
            run_dir = base / "run"
            summary = await runner.run_workflow(spec, run_dir, [sys.executable, str(FAKE)], role_configs())
            self.assertEqual(summary["tasks"][0]["status"], "failed")
            output_path = next((run_dir / "tasks" / "one").glob("attempt-*/out.json"), None)
            self.assertIsNone(output_path)
            self.assertIn("artifact limit exceeded", summary["tasks"][0]["error"])


if __name__ == "__main__":
    unittest.main()
