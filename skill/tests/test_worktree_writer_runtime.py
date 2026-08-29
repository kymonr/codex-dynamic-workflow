from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_contract
import writer_process
import writer_runtime
import skill.writer_runtime_base as writer_runtime_base


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


class Fixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.runs = self.root / "runs"
        self.worktrees = self.root / "worktrees"
        self.codex_home = self.root / "codex-home"
        for path in (self.repo, self.worktrees, self.codex_home):
            path.mkdir(parents=True)
        git(self.repo, "init")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "core.autocrlf", "false")
        git(self.repo, "config", "core.eol", "lf")
        git(self.repo, "remote", "add", "origin", "https://github.com/owner/repo.git")
        (self.repo / "check.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        git(self.repo, "add", "check.py")
        git(self.repo, "commit", "-m", "base")
        self.package_path = self.root / "package.json"
        self.package = self.write_package()

    def write_package(self, *, validation_script: str = "check.py") -> writer_contract.WriterPackage:
        raw = {
            "version": 2,
            "name": "writer-fixture",
            "objective": "Create docs/new.md with a short deterministic document.",
            "acceptance_criteria": [
                "The declared verification command passes.",
                "Only the owned UTF-8 text target changes.",
            ],
            "constraints": [
                "Preserve public behavior outside the owned targets."
            ],
            "non_goals": ["Do not refactor adjacent modules."],
            "behavior": {
                "before": "The target document does not exist.",
                "after": "The deterministic target document exists.",
            },
            "implementation_context": {
                "relevant_symbols": ["docs/new.md", "check.py"],
                "analysis_summary": "The change is bounded and verified locally.",
            },
            "base": {
                "repository_full_name": "owner/repo",
                "expected_head_sha": git(self.repo, "rev-parse", "HEAD"),
                "expected_tree_sha": git(self.repo, "rev-parse", "HEAD^{tree}"),
            },
            "authority": {
                "owned_targets": ["docs/new.md"],
                "allowed_actions": ["create"],
            },
            "limits": {
                "max_changed_files": 1,
                "max_patch_bytes": 262144,
                "max_created_file_bytes": 131072,
                "max_total_candidate_bytes": 524288,
            },
            "verification": {
                "required_verification_ids": ["check"],
                "commands": [
                    {"id": "check", "argv": ["python", validation_script], "timeout_seconds": 60}
                ],
            },
        }
        package = writer_contract.validate_package(raw)
        self.package_path.write_text(json.dumps(raw), encoding="utf-8")
        return package

    def environment(self):
        return mock.patch.dict(
            os.environ,
            {
                "DYNWF_RUNS_ROOT": str(self.runs),
                "DYNWF_WORKTREE_ROOT": str(self.worktrees),
                "CODEX_HOME": str(self.codex_home),
            },
            clear=False,
        )

    def preflight(self):
        return mock.patch.object(
            writer_runtime_base,
            "_codex_preflight",
            return_value=(
                ["fake-codex"],
                {"codex_executable": "fake-codex", "codex_version": "codex-cli fixture"},
                {"exit_code": 0, "required_flags": [], "missing": []},
            ),
        )

    def close(self) -> None:
        self.temp.cleanup()


class FakeProcessAdapter:
    def __init__(self, *, writer_effect: str = "allowed", verdict: str = "ship", writer_error: bool = False) -> None:
        self.writer_effect = writer_effect
        self.verdict = verdict
        self.writer_error = writer_error
        self.calls: list[str] = []

    def __call__(self, **kwargs):
        route = kwargs["route"]
        self.calls.append(route.role)
        attempt_dir = kwargs["attempt_dir"]
        attempt_dir.mkdir(parents=True, exist_ok=False)
        (attempt_dir / "cmd.json").write_text("[]", encoding="utf-8")
        if route.role == "sol":
            if self.writer_error:
                raise writer_process.WriterProcessError("fixture interruption")
            cwd = kwargs["cwd"]
            if self.writer_effect == "allowed":
                (cwd / "docs").mkdir()
                (cwd / "docs" / "new.md").write_text("# Candidate\n", encoding="utf-8")
                effects = [{"path": "docs/new.md", "action": "create"}]
            elif self.writer_effect == "unowned":
                (cwd / "unowned.txt").write_text("bad\n", encoding="utf-8")
                effects = []
            else:
                effects = []
            return {
                "status": "succeeded",
                "role": route.role,
                "model": route.model,
                "effort": route.effort,
                "tier": route.tier,
                "requested_sandbox": "workspace-write",
                "observed_sandbox": "fixture",
                "attempt_count": 1,
                "retry": 0,
                "upgrade": None,
                "nested_agents": 0,
                "codex_identity": {"codex_version": "fixture"},
                "output": {
                    "status": "completed",
                    "summary": "created candidate",
                    "reported_effects": effects,
                    "verification_notes": [],
                    "limitations": [],
                },
            }
        revision = json.loads(
            kwargs["prompt"].split("<CANDIDATE_PACKAGE_JSON>\n", 1)[1].split(
                "\n</CANDIDATE_PACKAGE_JSON>", 1
            )[0]
        )["candidate_revision"]
        findings = []
        if self.verdict == "fix-first":
            findings = [{"priority": "P1", "summary": "blocking fixture", "evidence": ["patch"]}]
        elif self.verdict == "rethink":
            findings = [{"priority": "P2", "summary": "reconsider fixture design", "evidence": ["patch"]}]
        return {
            "status": "succeeded",
            "role": "dynamic_workflow_sol_reviewer",
            "model": "gpt-5.6-sol",
            "effort": "xhigh",
            "tier": None,
            "requested_sandbox": "read-only",
            "observed_sandbox": "fixture",
            "attempt_count": 1,
            "retry": 0,
            "upgrade": None,
            "nested_agents": 0,
            "codex_identity": {"codex_version": "fixture"},
            "output": {
                "CANDIDATE_REVISION": revision,
                "VERDICT": self.verdict,
                "FINDINGS": findings,
                "EVIDENCE": ["fixture evidence"],
                "EFFECTS": [],
            },
        }


class WriterRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def _run(self, adapter: FakeProcessAdapter):
        with self.fixture.environment(), self.fixture.preflight():
            return writer_runtime.run_writer(
                package_path=self.fixture.package_path,
                repository=self.fixture.repo,
                expected_package_digest=self.fixture.package.digest,
                expected_head_sha=self.fixture.package.expected_head_sha,
                ack_isolated_worktree_write=True,
                process_adapter=adapter,
            )

    def test_plan_is_zero_model_zero_write_and_bound(self) -> None:
        with self.fixture.environment(), self.fixture.preflight():
            result = writer_runtime.plan_writer(
                package_path=self.fixture.package_path,
                repository=self.fixture.repo,
                expected_package_digest=self.fixture.package.digest,
            )
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["writes"], [])
        self.assertFalse(self.fixture.runs.exists())
        self.assertEqual(result["base_identity"]["head"], self.fixture.package.expected_head_sha)

    def test_ship_candidate_status_export_and_cleanup(self) -> None:
        before_head = git(self.fixture.repo, "rev-parse", "HEAD")
        before_status = git(self.fixture.repo, "status", "--porcelain")
        adapter = FakeProcessAdapter(verdict="ship")
        result = self._run(adapter)
        self.assertEqual(result["state"], "ship_candidate")
        self.assertEqual(adapter.calls, ["sol", "dynamic_workflow_sol_reviewer"])
        self.assertEqual(git(self.fixture.repo, "rev-parse", "HEAD"), before_head)
        self.assertEqual(git(self.fixture.repo, "status", "--porcelain"), before_status)
        run_dir = Path(result["candidate"]["candidate_package_path"]).parent
        first = writer_runtime.status_writer(run_dir)
        second = writer_runtime.status_writer(run_dir)
        self.assertEqual(first["run_fingerprint"], second["run_fingerprint"])
        exported = writer_runtime.export_writer(run_dir)
        self.assertEqual(exported["candidate_package"]["candidate_revision"], result["candidate"]["candidate_revision"])
        self.assertIn("docs/new.md", exported["patch"])
        cleaned = writer_runtime.cleanup_writer(
            run_dir=run_dir,
            expected_run_id=result["run_id"],
            expected_package_digest=self.fixture.package.digest,
            ack_delete_isolated_worktree=True,
        )
        self.assertTrue(cleaned["worktree_deleted"])
        self.assertTrue(run_dir.exists())

    def test_fix_first_and_rethink_are_terminal_without_apply(self) -> None:
        for verdict, state in (("fix-first", "fix_first"), ("rethink", "rethink")):
            with self.subTest(verdict=verdict):
                fixture = self.fixture if verdict == "fix-first" else Fixture()
                try:
                    adapter = FakeProcessAdapter(verdict=verdict)
                    with fixture.environment(), fixture.preflight():
                        result = writer_runtime.run_writer(
                            package_path=fixture.package_path,
                            repository=fixture.repo,
                            expected_package_digest=fixture.package.digest,
                            expected_head_sha=fixture.package.expected_head_sha,
                            ack_isolated_worktree_write=True,
                            process_adapter=adapter,
                        )
                    self.assertEqual(result["state"], state)
                    self.assertEqual(git(fixture.repo, "status", "--porcelain"), "")
                finally:
                    if fixture is not self.fixture:
                        fixture.close()
                if verdict == "fix-first":
                    self.fixture.close()
                    self.fixture = Fixture()

    def test_unowned_effect_fails_closed_without_reviewer(self) -> None:
        adapter = FakeProcessAdapter(writer_effect="unowned")
        result = self._run(adapter)
        self.assertEqual(result["state"], "effect_violation")
        self.assertEqual(adapter.calls, ["sol"])
        self.assertTrue(Path(result["worktree_path"]).exists())

    def test_interrupted_writer_is_not_replayed_and_worktree_is_preserved(self) -> None:
        adapter = FakeProcessAdapter(writer_error=True)
        result = self._run(adapter)
        self.assertEqual(result["state"], "attention_required")
        self.assertEqual(adapter.calls, ["sol"])
        self.assertTrue(Path(result["worktree_path"]).exists())
        with self.fixture.environment(), self.fixture.preflight():
            with self.assertRaisesRegex(writer_runtime.WriterRuntimeError, "lock"):
                writer_runtime.plan_writer(
                    package_path=self.fixture.package_path,
                    repository=self.fixture.repo,
                    expected_package_digest=self.fixture.package.digest,
                )

    def test_validation_failure_does_not_start_reviewer(self) -> None:
        (self.fixture.repo / "fail.py").write_text("raise SystemExit(4)\n", encoding="utf-8")
        git(self.fixture.repo, "add", "fail.py")
        git(self.fixture.repo, "commit", "-m", "failure fixture")
        self.fixture.package = self.fixture.write_package(validation_script="fail.py")
        adapter = FakeProcessAdapter()
        result = self._run(adapter)
        self.assertEqual(result["state"], "validation_failed")
        self.assertEqual(adapter.calls, ["sol"])


if __name__ == "__main__":
    unittest.main()
