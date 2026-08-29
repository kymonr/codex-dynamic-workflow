from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_contract
import fleet_integrity
import fleet_process
import fleet_runtime


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def decode_prompt_context(prompt: str, label: str):
    encoded = prompt.split(label + "\n", 1)[1].splitlines()[0]
    return json.loads(json.loads(encoded))


def rewrite_manifest(run_dir: Path, run_id: str) -> None:
    basis = {
        "manifest_version": 1,
        "runtime": "agent-fleet-v1",
        "run_id": run_id,
        "files": fleet_integrity.strict_run_manifest(run_dir),
    }
    manifest = {
        **basis,
        "manifest_digest": fleet_contract.canonical_digest(basis),
    }
    (run_dir / "evidence-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class Fixture:
    def __init__(
        self,
        *,
        agent_count: int = 6,
        risk_tags: list[str] | None = None,
        verification_exit: int = 0,
    ) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.runs = self.root / "runs"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "core.autocrlf", "false")
        git(self.repo, "remote", "add", "origin", "https://github.com/owner/repo.git")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        (self.repo / "check.py").write_text(
            f"raise SystemExit({verification_exit})\n", encoding="utf-8"
        )
        git(self.repo, "add", "base.txt", "check.py")
        git(self.repo, "commit", "-m", "base")
        raw = {
            "version": 1,
            "name": "fleet-runtime",
            "preset": "adversarial-review",
            "agent_count": agent_count,
            "objective": "Review the frozen candidate for material defects.",
            "acceptance_criteria": ["All material claims have concrete evidence."],
            "scope": ["The repository and frozen candidate."],
            "exclusions": ["No repository writes."],
            "candidate": {
                "repository_full_name": "owner/repo",
                "expected_head_sha": git(self.repo, "rev-parse", "HEAD"),
                "changed_files": [],
            },
            "risk_tags": risk_tags or [],
            "verification": {
                "required_ids": ["check"],
                "commands": [
                    {"id": "check", "argv": ["python", "check.py"], "timeout_seconds": 30}
                ],
            },
            "limits": {
                "max_patch_bytes": 524288,
                "max_untracked_file_bytes": 131072,
                "max_candidate_bytes": 1048576,
                "max_agent_output_bytes": 524288,
                "max_agent_log_bytes": 1048576,
            },
        }
        self.package = fleet_contract.validate_package(raw)
        self.package_path = self.root / "fleet.json"
        self.package_path.write_text(json.dumps(raw), encoding="utf-8")

    def environment(self):
        return mock.patch.dict(
            os.environ,
            {"DYNWF_RUNS_ROOT": str(self.runs)},
            clear=False,
        )

    def preflight(self):
        return mock.patch.object(
            fleet_runtime,
            "_codex_preflight",
            return_value=(
                ["fake-codex"],
                {"codex_executable": "fake-codex", "codex_version": "fixture"},
                {"missing": [], "command_policy": {"sandbox": "read-only"}},
            ),
        )

    def close(self) -> None:
        self.temp.cleanup()


class FakeFleetAdapter:
    def __init__(self, scenario: str = "clean") -> None:
        self.scenario = scenario
        self.calls: list[tuple[str, str]] = []
        self.lock = threading.Lock()
        self.tampered = False

    def _entry(self, route, output, attempt_dir: Path):
        attempt_dir.mkdir(parents=True, exist_ok=False)
        (attempt_dir / "cmd.json").write_text("[]", encoding="utf-8")
        with self.lock:
            self.calls.append((route.role, output.get("phase", "arbitration")))
        return {
            "status": "succeeded",
            "role": route.role,
            "model": route.model,
            "effort": route.effort,
            "tier": route.tier,
            "requested_sandbox": route.sandbox,
            "observed_sandbox": "unknown",
            "attempt_count": 1,
            "retry": 0,
            "upgrade": None,
            "nested_agents": 0,
            "codex_identity": {"codex_version": "fixture"},
            "output": output,
        }

    def __call__(self, **kwargs):
        schema = kwargs["schema"]
        route = kwargs["route"]
        attempt_dir = kwargs["attempt_dir"]
        revision = schema["properties"]["candidate_revision"]["enum"][0]
        if route.role == "fleet_sol_arbiter":
            context = decode_prompt_context(
                kwargs["prompt"], "ARBITRATION_CONTEXT_JSON_STRING:"
            )
            blockers = [
                item["finding_id"]
                for item in context["findings"]
                if item["severity"] in {"P1", "P2"}
                and item["disposition"] in {"accepted", "conflict", "unresolved"}
            ]
            verdict = (
                "fix-first"
                if blockers
                else "rethink"
                if self.scenario == "unknown-rethink"
                else "ship"
            )
            return self._entry(
                route,
                {
                    "candidate_revision": revision,
                    "verdict": verdict,
                    "accepted_findings": blockers,
                    "rationale": "fixture arbitration",
                    "evidence": ["validated fleet evidence"],
                    "effects": [],
                },
                attempt_dir,
            )

        properties = schema["properties"]
        agent_id = properties["agent_id"]["enum"][0]
        role_id = properties["role_id"]["enum"][0]
        phase = properties["phase"]["enum"][0]
        if self.scenario == "process-error" and phase == "discovery" and role_id == "correctness-hunter":
            raise fleet_process.FleetProcessError("fixture process interruption")
        if self.scenario == "tamper" and phase == "discovery" and not self.tampered:
            with self.lock:
                if not self.tampered:
                    (kwargs["cwd"] / "intrusion.txt").write_text("changed\n", encoding="utf-8")
                    self.tampered = True
        if self.scenario == "stale" and phase == "discovery":
            revision = "sha256:" + "0" * 64

        if phase == "discovery":
            findings = []
            unknown = []
            verdict = "accept"
            if self.scenario in {"p1", "p3"} and role_id == "correctness-hunter":
                severity = "P1" if self.scenario == "p1" else "P3"
                findings = [
                    {
                        "category": "correctness",
                        "severity": severity,
                        "summary": "Fixture defect",
                        "evidence": ["base.txt:1 fixture evidence"],
                        "locations": ["base.txt:1"],
                        "confidence": "high",
                    }
                ]
                verdict = "findings"
            elif self.scenario in {"unknown", "unknown-rethink"} and role_id == "correctness-hunter":
                unknown = ["caller behavior cannot be established"]
                verdict = "unknown"
            output = {
                "candidate_revision": revision,
                "agent_id": agent_id,
                "role_id": role_id,
                "phase": phase,
                "verdict": verdict,
                "findings": findings,
                "unknown": unknown,
                "effects": [],
            }
        elif phase == "challenge":
            assigned = decode_prompt_context(
                kwargs["prompt"], "ASSIGNED_FINDINGS_JSON_STRING:"
            )
            assessments = []
            if self.scenario in {"p1", "p3"}:
                assessments = [
                    {
                        "finding_id": item["finding_id"],
                        "outcome": "support",
                        "evidence": ["independent challenge supports the claim"],
                    }
                    for item in assigned
                ]
            output = {
                "candidate_revision": revision,
                "agent_id": agent_id,
                "role_id": role_id,
                "phase": phase,
                "assessments": assessments,
                "new_findings": [],
                "unknown": [],
                "effects": [],
            }
        else:
            assigned = decode_prompt_context(
                kwargs["prompt"], "ASSIGNED_FINDINGS_JSON_STRING:"
            )
            reproductions = []
            if self.scenario in {"p1", "p3"}:
                reproductions = [
                    {
                        "finding_id": item["finding_id"],
                        "status": "reproduced",
                        "steps": ["exercise the fixture path"],
                        "evidence": ["fixture failure reproduced"],
                    }
                    for item in assigned
                ]
            output = {
                "candidate_revision": revision,
                "agent_id": agent_id,
                "role_id": role_id,
                "phase": phase,
                "reproductions": reproductions,
                "new_findings": [],
                "unknown": [],
                "effects": [],
            }
        entry = self._entry(route, output, attempt_dir)
        if self.scenario == "identity-mismatch" and phase == "discovery" and role_id == "correctness-hunter":
            entry["model"] = "gpt-5.6-sol"
        if self.scenario == "effect-record" and phase == "discovery" and role_id == "correctness-hunter":
            entry["output"]["effects"] = ["unexpected-write"]
        if self.scenario == "sandbox-mismatch" and phase == "discovery" and role_id == "correctness-hunter":
            entry["observed_sandbox"] = "workspace-write"
        return entry


class FleetRuntimeTests(unittest.TestCase):
    def test_plan_is_zero_model_and_has_fixed_routes(self) -> None:
        fixture = Fixture()
        try:
            with fixture.environment(), fixture.preflight():
                plan = fleet_runtime.plan_fleet(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=fixture.package.digest,
                )
            self.assertEqual(plan["model_calls"], 0)
            self.assertEqual(plan["writes"], [])
            self.assertEqual(len(plan["schedule"]["agents"]), 6)
            self.assertTrue(all(item["route"]["role"] == "luna" for item in plan["schedule"]["agents"]))
            self.assertEqual(plan["sol_route"]["model"], "gpt-5.6-sol")
            self.assertTrue(plan["sol_route"]["conditional"])
            self.assertFalse(plan["majority_vote"])
        finally:
            fixture.close()

    def run_fixture(self, fixture: Fixture, adapter: FakeFleetAdapter):
        with fixture.environment(), fixture.preflight():
            return fleet_runtime.run_fleet(
                package_path=fixture.package_path,
                repository=fixture.repo,
                expected_package_digest=fixture.package.digest,
                ack_read_only_agent_fleet=True,
                process_adapter=adapter,
            )

    def test_exact_four_and_twelve_agent_runs_complete_full_lifecycle(self) -> None:
        for count in (4, 12):
            fixture = Fixture(agent_count=count)
            try:
                adapter = FakeFleetAdapter("clean")
                result = self.run_fixture(fixture, adapter)
                with self.subTest(count=count):
                    self.assertEqual(result["state"], "accepted")
                    self.assertEqual(result["model_calls"], count)
                    self.assertEqual(len(adapter.calls), count)
                    phases = [phase for _, phase in adapter.calls]
                    self.assertIn("discovery", phases)
                    self.assertIn("challenge", phases)
                    self.assertIn("reproduction", phases)
                    self.assertFalse(result["aggregation"]["requires_sol"])
                    self.assertEqual(
                        fleet_runtime.status_fleet(result["run_dir"])["integrity"],
                        "match",
                    )
            finally:
                fixture.close()

    def test_clean_fleet_skips_sol_and_status_matches(self) -> None:
        fixture = Fixture()
        try:
            adapter = FakeFleetAdapter("clean")
            result = self.run_fixture(fixture, adapter)
            self.assertEqual(result["state"], "accepted")
            self.assertEqual(result["model_calls"], 6)
            self.assertEqual([role for role, _ in adapter.calls], ["luna"] * 6)
            self.assertFalse(result["aggregation"]["requires_sol"])
            self.assertTrue(
                all(
                    record["observed_sandbox"] == "unknown"
                    for record in result["process_records"]
                )
            )
            status = fleet_runtime.status_fleet(result["run_dir"])
            self.assertEqual(status["integrity"], "match")
        finally:
            fixture.close()

    def test_reproduced_p1_invokes_fresh_sol_and_blocks(self) -> None:
        fixture = Fixture()
        try:
            adapter = FakeFleetAdapter("p1")
            result = self.run_fixture(fixture, adapter)
            self.assertEqual(result["state"], "fix_first")
            self.assertEqual(result["model_calls"], 7)
            self.assertEqual([role for role, _ in adapter.calls].count("luna"), 6)
            self.assertEqual([role for role, _ in adapter.calls].count("fleet_sol_arbiter"), 1)
            self.assertTrue(result["aggregation"]["requires_sol"])
            self.assertEqual(result["sol_arbitration"]["verdict"], "fix-first")
        finally:
            fixture.close()

    def test_reproduced_p3_is_accepted_with_notes_without_sol(self) -> None:
        fixture = Fixture()
        try:
            adapter = FakeFleetAdapter("p3")
            result = self.run_fixture(fixture, adapter)
            self.assertEqual(result["state"], "accepted_with_notes")
            self.assertEqual(result["model_calls"], 6)
            self.assertFalse(result["aggregation"]["requires_sol"])
            self.assertEqual(result["findings"][0]["disposition"], "accepted")
        finally:
            fixture.close()

    def test_unknown_can_rethink_without_an_existing_finding(self) -> None:
        fixture = Fixture()
        try:
            adapter = FakeFleetAdapter("unknown-rethink")
            result = self.run_fixture(fixture, adapter)
            self.assertEqual(result["state"], "rethink")
            self.assertEqual(result["model_calls"], fixture.package.agent_count + 1)
            self.assertTrue(result["aggregation"]["requires_sol"])
            self.assertEqual(result["findings"], [])
            self.assertEqual(result["sol_arbitration"]["verdict"], "rethink")
            self.assertEqual(result["sol_arbitration"]["accepted_findings"], [])
            self.assertEqual(
                fleet_runtime.status_fleet(result["run_dir"])["integrity"],
                "match",
            )
        finally:
            fixture.close()

    def test_unknown_or_high_risk_invokes_sol_even_without_findings(self) -> None:
        fixture = Fixture()
        try:
            result = self.run_fixture(fixture, FakeFleetAdapter("unknown"))
            self.assertEqual(result["state"], "ship")
            self.assertTrue(result["aggregation"]["requires_sol"])
        finally:
            fixture.close()

        fixture = Fixture(risk_tags=["security"])
        try:
            result = self.run_fixture(fixture, FakeFleetAdapter("clean"))
            self.assertEqual(result["state"], "ship")
            self.assertTrue(result["aggregation"]["requires_sol"])
            self.assertIn(
                "high-risk-scope",
                {item["code"] for item in result["aggregation"]["triggers"]},
            )
        finally:
            fixture.close()

    def test_candidate_write_or_stale_record_fails_closed_without_sol_fallback(self) -> None:
        fixture = Fixture()
        try:
            adapter = FakeFleetAdapter("tamper")
            result = self.run_fixture(fixture, adapter)
            self.assertEqual(result["state"], "attention_required")
            self.assertEqual(result["model_calls"], 4)
            self.assertNotIn("fleet_sol_arbiter", [role for role, _ in adapter.calls])
        finally:
            fixture.close()

        fixture = Fixture()
        try:
            adapter = FakeFleetAdapter("stale")
            result = self.run_fixture(fixture, adapter)
            self.assertEqual(result["state"], "attention_required")
            self.assertEqual(result["model_calls"], 4)
            self.assertNotIn("fleet_sol_arbiter", [role for role, _ in adapter.calls])
        finally:
            fixture.close()

    def test_verification_failure_starts_no_agent(self) -> None:
        fixture = Fixture(verification_exit=1)
        try:
            adapter = FakeFleetAdapter("clean")
            result = self.run_fixture(fixture, adapter)
            self.assertEqual(result["state"], "verification_failed")
            self.assertEqual(adapter.calls, [])
            self.assertEqual(result["model_calls"], 0)
            self.assertFalse(result["verification_results"][-1]["passed"])
            self.assertEqual(
                fleet_runtime.status_fleet(result["run_dir"])["integrity"],
                "match",
            )
        finally:
            fixture.close()

    def test_manifest_rejects_link_or_reparse_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            root.mkdir()
            target = root / "target"
            target.mkdir()
            (target / "evidence.json").write_text("{}", encoding="utf-8")
            alias = root / "alias"
            if os.name == "nt":
                completed = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if completed.returncode != 0:
                    self.skipTest(
                        f"cannot create Windows junction: {completed.stderr}"
                    )
            else:
                alias.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(
                fleet_runtime.FleetRuntimeError, "link/reparse"
            ):
                fleet_runtime._manifest_files(root)

    def test_evidence_tamper_breaks_status(self) -> None:
        fixture = Fixture()
        try:
            result = self.run_fixture(fixture, FakeFleetAdapter("clean"))
            summary_path = Path(result["run_dir"]) / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["state"] = "ship"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(fleet_runtime.FleetRuntimeError, "differs"):
                fleet_runtime.status_fleet(result["run_dir"])
        finally:
            fixture.close()


    def test_semantic_identity_tamper_survives_manifest_rewrite_but_not_status(self) -> None:
        fixture = Fixture()
        try:
            result = self.run_fixture(fixture, FakeFleetAdapter("clean"))
            run_dir = Path(result["run_dir"])
            process_path = run_dir / "process-records.json"
            summary_path = run_dir / "summary.json"
            process_records = json.loads(process_path.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            process_records[0]["model"] = "gpt-5.6-sol"
            summary["process_records"] = process_records
            process_path.write_text(
                json.dumps(process_records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            rewrite_manifest(run_dir, result["run_id"])
            with self.assertRaisesRegex(
                fleet_runtime.FleetRuntimeError,
                "process record .* model mismatch",
            ):
                fleet_runtime.status_fleet(run_dir)
        finally:
            fixture.close()

    def test_semantic_finding_tamper_is_rebuilt_after_manifest_rewrite(self) -> None:
        fixture = Fixture()
        try:
            result = self.run_fixture(fixture, FakeFleetAdapter("p3"))
            run_dir = Path(result["run_dir"])
            findings_path = run_dir / "findings.json"
            summary_path = run_dir / "summary.json"
            findings = json.loads(findings_path.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            findings[0]["disposition"] = "discarded"
            summary["findings"] = findings
            findings_path.write_text(
                json.dumps(findings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            rewrite_manifest(run_dir, result["run_id"])
            with self.assertRaisesRegex(
                fleet_runtime.FleetRuntimeError,
                "finding graph reconstruction mismatch",
            ):
                fleet_runtime.status_fleet(run_dir)
        finally:
            fixture.close()

    def test_live_candidate_drift_breaks_terminal_status(self) -> None:
        fixture = Fixture()
        try:
            result = self.run_fixture(fixture, FakeFleetAdapter("clean"))
            (fixture.repo / "late-change.txt").write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(
                fleet_runtime.FleetRuntimeError,
                "changed-file set mismatch",
            ):
                fleet_runtime.status_fleet(result["run_dir"])
        finally:
            fixture.close()


    def test_keyboard_interrupt_is_recorded_and_re_raised(self) -> None:
        fixture = Fixture()
        try:
            def interrupting_adapter(**kwargs):
                raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                self.run_fixture(fixture, interrupting_adapter)
            fleet_root = fixture.runs / fleet_runtime.FLEET_RUNS_SUBDIR
            run_dirs = [item for item in fleet_root.iterdir() if item.is_dir()]
            self.assertEqual(len(run_dirs), 1)
            summary = json.loads(
                (run_dirs[0] / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["state"], "attention_required")
            self.assertEqual(summary["error"], "KeyboardInterrupt")
            self.assertEqual(
                fleet_runtime.status_fleet(run_dirs[0])["integrity"], "match"
            )
        finally:
            fixture.close()

    def test_process_identity_effect_and_interruption_return_root_without_sol(self) -> None:
        for scenario in (
            "process-error",
            "identity-mismatch",
            "sandbox-mismatch",
            "effect-record",
        ):
            fixture = Fixture()
            try:
                adapter = FakeFleetAdapter(scenario)
                result = self.run_fixture(fixture, adapter)
                self.assertEqual(result["state"], "attention_required", scenario)
                self.assertEqual(result["model_calls"], 4, scenario)
                self.assertNotIn(
                    "fleet_sol_arbiter",
                    [role for role, _ in adapter.calls],
                    scenario,
                )
            finally:
                fixture.close()


if __name__ == "__main__":
    unittest.main()
