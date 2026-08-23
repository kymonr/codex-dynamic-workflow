from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterator


SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parent
SPEC_PATH = REPO_ROOT / "examples" / "reference-repository-audit.workflow-ir.json"
FAKE_IR_CODEX = Path(__file__).with_name("fake_ir_codex.py")
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import ir_runner
import ops_cli
from runtime.artifacts import ArtifactStore
from runtime.human_gate import HumanGateStore
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import validate_workflow_ir


def _load_raw_spec() -> dict[str, Any]:
    value = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("reference spec must be an object")
    return value


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _node(ir: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in ir["nodes"] if node["id"] == node_id)


def _summary_node(summary: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in summary["nodes"] if node["id"] == node_id)


def _task_dirs(run_dir: Path) -> set[str]:
    tasks = run_dir / "tasks"
    if not tasks.is_dir():
        return set()
    return {path.name for path in tasks.iterdir() if path.is_dir()}


def _agent_entries(entries: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield direct and map/verify child RunnerAgentExecutor records."""

    for entry in entries.values():
        direct = entry.get("agent_entry")
        if isinstance(direct, dict):
            yield direct
        children = entry.get("children", {})
        if isinstance(children, dict):
            for child in children.values():
                if not isinstance(child, dict):
                    continue
                child_entry = child.get("agent_entry")
                if isinstance(child_entry, dict):
                    yield child_entry


def _artifact_references(entries: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every node/child output artifact without trusting public output."""

    for entry in entries.values():
        for candidate in (entry, entry.get("agent_entry")):
            if isinstance(candidate, dict):
                reference = candidate.get("output_artifact")
                if isinstance(reference, dict):
                    yield reference
        children = entry.get("children", {})
        if isinstance(children, dict):
            for child in children.values():
                if not isinstance(child, dict):
                    continue
                reference = child.get("output_artifact")
                if isinstance(reference, dict):
                    yield reference
                child_entry = child.get("agent_entry")
                if isinstance(child_entry, dict):
                    reference = child_entry.get("output_artifact")
                    if isinstance(reference, dict):
                        yield reference


def _tracked_snapshot(root: Path) -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        snapshot[relative] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _prompt_has_task_reference(prompt: str, task_id: str) -> bool:
    return f'task_id="{task_id}"' in prompt


class ReferenceWorkflowContractTests(unittest.TestCase):
    def test_real_spec_contract_and_read_only_plan(self) -> None:
        raw = _load_raw_spec()
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            planned = dict(raw)
            planned["workdir"] = str(target)

            plan = ops_cli._plan_preview(planned)

            self.assertEqual(plan["model_calls"], 0)
            self.assertEqual(plan["writes"], [])
            self.assertFalse(plan["workdir_preflight"]["performed"])
            self.assertFalse(target.exists(), "plan-ir must not touch workdir")
            self.assertEqual(plan["agent_claim_projection"]["total_upper_bound"], 20)
            self.assertLessEqual(
                plan["agent_claim_projection"]["total_upper_bound"],
                plan["agent_claim_projection"]["max_agents"],
            )
            self.assertLessEqual(plan["agent_claim_projection"]["max_agents"], 24)

        normalized = validate_workflow_ir(raw)
        ids = [node["id"] for node in normalized["nodes"]]
        self.assertNotIn("finalize-report", ids)
        self.assertEqual(
            ids,
            [
                "discover-modules",
                "audit-modules",
                "verify-audits",
                "summarize-audit",
                "choose-verification-path",
                "prepare-clean-candidate",
                "prepare-blocker-report",
                "review-gate",
                "choose-gate-outcome",
                "record-accepted",
                "record-rejected",
                "finalize-accepted",
                "finalize-rejected",
            ],
        )

        self.assertEqual(_node(normalized, "review-gate")["dependency_policy"], "join")
        self.assertEqual(
            _node(normalized, "record-accepted")["depends_on"],
            ["choose-gate-outcome", "review-gate", "summarize-audit"],
        )
        self.assertEqual(
            _node(normalized, "record-rejected")["depends_on"],
            ["choose-gate-outcome", "review-gate", "summarize-audit"],
        )
        self.assertEqual(
            _node(normalized, "finalize-accepted")["depends_on"],
            ["record-accepted"],
        )
        self.assertEqual(
            _node(normalized, "finalize-rejected")["depends_on"],
            ["record-rejected"],
        )

        for record_id in ("record-accepted", "record-rejected"):
            record = _node(normalized, record_id)
            prompt = record["config"]["prompt"]
            self.assertIn("{{result:review-gate}}", prompt)
            self.assertIn("{{result:summarize-audit}}", prompt)
            schema = record["config"]["output_schema"]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(
                schema["properties"]["decision"]["enum"], ["approve", "reject"]
            )
            self.assertEqual(
                schema["required"],
                ["decision", "summary", "evidence", "next_actions"],
            )
            self.assertEqual(schema["properties"]["evidence"]["type"], "array")
            self.assertEqual(schema["properties"]["evidence"]["items"], {"type": "string"})
            self.assertEqual(schema["properties"]["next_actions"]["type"], "array")
            self.assertEqual(
                schema["properties"]["next_actions"]["items"], {"type": "string"}
            )

        for final_id, record_id in (
            ("finalize-accepted", "record-accepted"),
            ("finalize-rejected", "record-rejected"),
        ):
            final = _node(normalized, final_id)
            placeholders = [
                part
                for part in final["config"]["prompt"].split("{{result:")[1:]
            ]
            self.assertEqual(len(placeholders), 1)
            self.assertTrue(placeholders[0].startswith(record_id + "}}"))
            schema = final["config"]["output_schema"]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(
                schema["properties"]["status"]["enum"], ["accepted", "rejected"]
            )
            self.assertEqual(schema["properties"]["uncertainty"]["type"], "array")
            self.assertEqual(
                schema["required"],
                [
                    "status",
                    "decision",
                    "summary",
                    "evidence",
                    "next_actions",
                    "uncertainty",
                ],
            )

    def test_fake_codex_rejects_unknown_and_missing_closeout_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            child_env = dict(os.environ)
            child_env["PYTHONDONTWRITEBYTECODE"] = "1"
            child_env["PYTHONPYCACHEPREFIX"] = str(base / "pycache")

            unknown_output = base / "unknown.json"
            unknown = subprocess.run(
                [
                    sys.executable,
                    str(FAKE_IR_CODEX),
                    "-o",
                    str(unknown_output),
                    "--",
                    "-",
                ],
                input="REFERENCE_UNKNOWN_MARKER",
                text=True,
                capture_output=True,
                env=child_env,
                check=False,
            )
            self.assertNotEqual(unknown.returncode, 0)
            self.assertIn("unknown fake_ir_codex prompt marker", unknown.stderr)
            self.assertFalse(unknown_output.exists())

            raw = _load_raw_spec()
            cases = [
                ("record-accepted", "REFERENCE_RECORD_ACCEPTED", "review-gate"),
                ("record-accepted", "REFERENCE_RECORD_ACCEPTED", "summarize-audit"),
                ("record-rejected", "REFERENCE_RECORD_REJECTED", "review-gate"),
                ("record-rejected", "REFERENCE_RECORD_REJECTED", "summarize-audit"),
                ("finalize-accepted", "REFERENCE_FINALIZE_ACCEPTED", "record-accepted"),
                ("finalize-rejected", "REFERENCE_FINALIZE_REJECTED", "record-rejected"),
            ]
            for node_id, marker, missing_input in cases:
                with self.subTest(node_id=node_id, missing_input=missing_input):
                    prompt = _node(validate_workflow_ir(raw), node_id)["config"][
                        "prompt"
                    ]
                    required_inputs = {
                        "record-accepted": ("review-gate", "summarize-audit"),
                        "record-rejected": ("review-gate", "summarize-audit"),
                        "finalize-accepted": ("record-accepted",),
                        "finalize-rejected": ("record-rejected",),
                    }[node_id]
                    for task_id in required_inputs:
                        replacement = (
                            ""
                            if task_id == missing_input
                            else (
                                '<UPSTREAM_RESULT nonce="fixture" task_id="'
                                + task_id
                                + '">fixture</UPSTREAM_RESULT>'
                            )
                        )
                        prompt = prompt.replace(
                            "{{result:" + task_id + "}}", replacement
                        )
                    output = base / (node_id + "-" + missing_input + ".json")
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(FAKE_IR_CODEX),
                            "-o",
                            str(output),
                            "--",
                            "-",
                        ],
                        input=prompt,
                        text=True,
                        capture_output=True,
                        env=child_env,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0)
                    envelope = _json(output)
                    self.assertEqual(envelope["workflow_status"], "needs_escalation")
                    self.assertIn(missing_input, envelope["reason"])
                    for supplied_input in set(required_inputs) - {missing_input}:
                        self.assertNotIn(supplied_input, envelope["reason"])


class ReferenceWorkflowRunnerE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workdir = self.base / "allowed" / "target"
        self.workdir.mkdir(parents=True)
        (self.workdir / "tracked-fixture.py").write_text(
            "# offline tracked target\n", encoding="utf-8"
        )
        self.codex_home = self.base / "codex-home"
        self.codex_home.mkdir()
        raw = _load_raw_spec()
        raw["workdir"] = str(self.workdir)
        self.ir = validate_workflow_ir(raw)
        self.limits = RuntimeLimits.from_mapping(self.ir["limits"])
        self.preflight = {
            "ack_external_model_export": True,
            "allowed_roots": [str(self.workdir.parent)],
            "allowed_sensitive_paths": [],
            "codex_home": str(self.codex_home),
            "codex_executable": str(FAKE_IR_CODEX),
            "codex_version": "offline-fixture",
            "codex_signature_status": "not_applicable",
            "codex_signer_subject": None,
        }
        self.role_configs = {
            "spark": {
                "role": "spark",
                "model": "fake-spark",
                "effort": "high",
                "tier": None,
                "source": "fixture",
            },
            "luna": {
                "role": "luna",
                "model": "fake-luna",
                "effort": "max",
                "tier": "fast",
                "source": "fixture",
            },
            "sol": {
                "role": "sol",
                "model": "fake-sol",
                "effort": "xhigh",
                "tier": None,
                "source": "fixture",
            },
        }

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def _run_flow(self, decision: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        run_dir = self.base / ("run-" + decision)
        # This is the real ir_runner._run -> legacy._execute_task subprocess
        # boundary (the RunnerAgentExecutor path). It deliberately does not
        # claim coverage for master resume-ir's PR18 CLI parser seam; the
        # combined branch owns that CLI RC.
        paused = await ir_runner._run(
            self.ir,
            run_dir,
            resume=False,
            codex_prefix=[sys.executable, str(FAKE_IR_CODEX)],
            role_configs=self.role_configs,
            preflight=self.preflight,
            limits=self.limits,
        )
        self.assertTrue(paused["paused"])
        self.assertEqual(paused["waiting_count"], 1)
        waiting_states = {node["id"]: node["status"] for node in paused["nodes"]}
        self.assertEqual(waiting_states["review-gate"], "waiting")
        self.assertEqual(waiting_states["choose-gate-outcome"], "pending")

        checkpoint_before = _json(run_dir / "checkpoint.json")
        entries_before = checkpoint_before["entries"]
        attempts_before = {
            entry["id"]: len(entry.get("attempts", []))
            for entry in _agent_entries(entries_before)
        }
        task_dirs_before = _task_dirs(run_dir)
        target_before = _tracked_snapshot(self.workdir)
        resolved_path = run_dir / "workflow-ir.resolved.json"
        resolved_bytes = resolved_path.read_bytes()
        resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
        resolved_mtime_ns = resolved_path.stat().st_mtime_ns

        gate_store = HumanGateStore(run_dir, self.limits)
        waiting = gate_store.load("review-gate")
        self.assertEqual(waiting["status"], "waiting")
        gate_store.decide(
            "review-gate",
            decision=decision,
            actor="reference-workflow-test",
            source="user",
            expected_input_identity=waiting["input_identity"],
            note="fixture closeout decision",
        )

        completed = await ir_runner._run(
            self.ir,
            run_dir,
            resume=True,
            codex_prefix=[sys.executable, str(FAKE_IR_CODEX)],
            role_configs=self.role_configs,
            preflight=self.preflight,
            limits=self.limits,
        )
        self.assertTrue(completed["all_succeeded"])
        self.assertFalse(completed["paused"])
        self.assertEqual(completed["needs_escalation_count"], 0)
        statuses = {node["id"]: node["status"] for node in completed["nodes"]}
        selected_record = "record-accepted" if decision == "approve" else "record-rejected"
        unselected_record = "record-rejected" if decision == "approve" else "record-accepted"
        selected_final = "finalize-accepted" if decision == "approve" else "finalize-rejected"
        unselected_final = "finalize-rejected" if decision == "approve" else "finalize-accepted"
        self.assertEqual(statuses[selected_record], "succeeded")
        self.assertEqual(statuses[selected_final], "succeeded")
        self.assertEqual(statuses[unselected_record], "skipped")
        self.assertEqual(statuses[unselected_final], "skipped")

        task_dirs_after = _task_dirs(run_dir)
        self.assertEqual(
            task_dirs_after - task_dirs_before,
            {selected_record, selected_final},
        )
        self.assertNotIn(unselected_record, task_dirs_after)
        self.assertNotIn(unselected_final, task_dirs_after)
        for node_id in (unselected_record, unselected_final):
            self.assertIsNone(_summary_node(completed, node_id)["output_artifact"])

        checkpoint_after = _json(run_dir / "checkpoint.json")
        entries_after = checkpoint_after["entries"]
        attempts_after = {
            entry["id"]: len(entry.get("attempts", []))
            for entry in _agent_entries(entries_after)
        }
        self.assertTrue(set(attempts_before).issubset(attempts_after))
        for task_id, count in attempts_before.items():
            self.assertEqual(attempts_after[task_id], count, task_id)
        self.assertEqual(
            {task_id for task_id in attempts_after if task_id not in attempts_before},
            {selected_record, selected_final},
        )
        for entry in _agent_entries(entries_after):
            self.assertEqual(len(entry.get("attempts", [])), 1, entry.get("id"))
            self.assertEqual(entry.get("retry"), 0, entry.get("id"))
            self.assertIsNone(entry.get("upgrade"), entry.get("id"))

        record_value = ArtifactStore(run_dir, self.limits).load_json(
            _summary_node(completed, selected_record)["output_artifact"]
        )
        final_value = ArtifactStore(run_dir, self.limits).load_json(
            _summary_node(completed, selected_final)["output_artifact"]
        )
        self.assertEqual(record_value["decision"], decision)
        self.assertEqual(
            final_value["status"], "accepted" if decision == "approve" else "rejected"
        )

        for node_id, required_inputs in (
            (selected_record, ("review-gate", "summarize-audit")),
            (selected_final, (selected_record,)),
        ):
            task_dir = run_dir / "tasks" / node_id
            prompt_files = list(task_dir.glob("attempt-*/prompt.txt"))
            self.assertEqual(len(prompt_files), 1)
            prompt = prompt_files[0].read_text(encoding="utf-8")
            for required_input in required_inputs:
                self.assertTrue(_prompt_has_task_reference(prompt, required_input))
            if node_id == selected_final:
                self.assertNotIn(
                    'task_id="' + unselected_record + '"',
                    prompt,
                )

        artifact_paths: set[str] = set()
        for reference in _artifact_references(entries_after):
            metadata = reference["$artifact"]
            self.assertEqual(metadata["id"], "sha256:" + metadata["sha256"])
            self.assertFalse(Path(metadata["path"]).is_absolute())
            self.assertTrue(metadata["path"].startswith("artifacts/"))
            artifact_path = run_dir / Path(metadata["path"])
            self.assertTrue(artifact_path.is_file())
            payload = artifact_path.read_bytes()
            self.assertEqual(metadata["bytes"], len(payload))
            self.assertEqual(metadata["sha256"], hashlib.sha256(payload).hexdigest())
            artifact_paths.add(metadata["path"])
        self.assertTrue(artifact_paths)

        resolved_after = resolved_path.read_bytes()
        self.assertEqual(resolved_after, resolved_bytes)
        self.assertEqual(hashlib.sha256(resolved_after).hexdigest(), resolved_sha)
        self.assertEqual(resolved_path.stat().st_mtime_ns, resolved_mtime_ns)
        self.assertEqual(_tracked_snapshot(self.workdir), target_before)

        ir_digest = ops_cli._workflow_ir_digest(self.ir)
        self.assertEqual(completed["ir_digest"], ir_digest)
        self.assertEqual(checkpoint_after["ir_digest"], ir_digest)
        self.assertEqual(_json(run_dir / "summary.json")["ir_digest"], ir_digest)
        events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [event["sequence"] for event in events],
            list(range(1, len(events) + 1)),
        )
        self.assertEqual(completed["needs_escalation_count"], 0)
        return run_dir, paused, completed

    async def test_approve_flow_pauses_decides_and_resumes_selected_closeout(self) -> None:
        _, _, completed = await self._run_flow("approve")
        self.assertEqual(_summary_node(completed, "finalize-accepted")["status"], "succeeded")

    async def test_reject_flow_pauses_decides_and_resumes_selected_closeout(self) -> None:
        _, _, completed = await self._run_flow("reject")
        self.assertEqual(_summary_node(completed, "finalize-rejected")["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
