from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_cli
import writer_contract
import writer_process
import writer_runtime
import skill.writer_runtime_candidate as writer_runtime_candidate

try:
    from skill.tests.test_worktree_writer_contract import valid_raw
    from skill.tests.test_worktree_writer_runtime import FakeProcessAdapter, Fixture, git
except ModuleNotFoundError:
    from test_worktree_writer_contract import valid_raw
    from test_worktree_writer_runtime import FakeProcessAdapter, Fixture, git


def valid_v2_raw() -> dict:
    raw = valid_raw()
    raw["version"] = 2
    raw["acceptance_criteria"] = [
        "The declared verification command passes.",
        "Only the owned UTF-8 text target changes.",
    ]
    raw["constraints"] = [
        "Preserve existing public behavior outside the owned targets."
    ]
    raw["non_goals"] = ["Do not refactor adjacent modules."]
    raw["behavior"] = {
        "before": "The bounded document does not exist.",
        "after": "The bounded document exists with deterministic content.",
    }
    raw["implementation_context"] = {
        "relevant_symbols": ["docs/new.md", "check.py"],
        "analysis_summary": (
            "The change is isolated to one text document and verified by check.py."
        ),
    }
    return raw


def install_v2_package(fixture: Fixture) -> writer_contract.WriterPackage:
    raw = valid_v2_raw()
    raw["name"] = "writer-fixture-v2"
    raw["objective"] = "Create docs/new.md with a short deterministic document."
    raw["base"] = {
        "repository_full_name": "owner/repo",
        "expected_head_sha": git(fixture.repo, "rev-parse", "HEAD"),
        "expected_tree_sha": git(fixture.repo, "rev-parse", "HEAD^{tree}"),
    }
    raw["verification"] = {
        "required_verification_ids": ["check"],
        "commands": [
            {
                "id": "check",
                "argv": ["python", "check.py"],
                "timeout_seconds": 60,
            }
        ],
    }
    package = writer_contract.validate_package(raw)
    fixture.package_path.write_text(json.dumps(raw), encoding="utf-8")
    fixture.package = package
    return package


class WriterProfileTests(unittest.TestCase):
    def test_v2_quality_context_is_closed_and_digest_bound(self) -> None:
        raw = valid_v2_raw()
        first = writer_contract.validate_package(raw)
        self.assertEqual(first.version, 2)
        self.assertEqual(
            first.quality_context["acceptance_criteria"],
            raw["acceptance_criteria"],
        )
        changed = valid_v2_raw()
        changed["acceptance_criteria"][0] = "A different acceptance condition."
        self.assertNotEqual(
            first.digest, writer_contract.validate_package(changed).digest
        )

        missing = valid_v2_raw()
        del missing["acceptance_criteria"]
        with self.assertRaisesRegex(writer_contract.WriterContractError, "missing"):
            writer_contract.validate_package(missing)

        empty = valid_v2_raw()
        empty["acceptance_criteria"] = []
        with self.assertRaisesRegex(writer_contract.WriterContractError, "1..64"):
            writer_contract.validate_package(empty)

        nested_extra = valid_v2_raw()
        nested_extra["behavior"]["authorization"] = "expand"
        with self.assertRaisesRegex(writer_contract.WriterContractError, "unknown"):
            writer_contract.validate_package(nested_extra)

        duplicate = valid_v2_raw()
        duplicate["constraints"] = ["Keep behavior", "keep behavior"]
        with self.assertRaisesRegex(
            writer_contract.WriterContractError, "case-insensitively"
        ):
            writer_contract.validate_package(duplicate)

        oversized_quality = valid_v2_raw()
        oversized_quality["acceptance_criteria"] = [
            f"{index:02d}-" + "x" * 3997 for index in range(34)
        ]
        with self.assertRaisesRegex(
            writer_contract.WriterContractError, "quality context exceeds"
        ):
            writer_contract.validate_package(oversized_quality)

    def test_profile_gates_are_host_trusted_and_bounded(self) -> None:
        luna = writer_process.resolve_writer_profile("bounded-luna")
        sol = writer_process.resolve_writer_profile("complex-sol")
        package_v1 = writer_contract.validate_package(valid_raw())
        writer_process.validate_writer_profile_package(luna, package_v1)
        with self.assertRaisesRegex(
            writer_process.WriterProcessError, "does not accept package v1"
        ):
            writer_process.validate_writer_profile_package(sol, package_v1)

        package_v2 = writer_contract.validate_package(valid_v2_raw())
        writer_process.validate_writer_profile_package(luna, package_v2)
        writer_process.validate_writer_profile_package(sol, package_v2)

        wide = valid_raw()
        wide["authority"]["owned_targets"] = [
            "docs/a.md",
            "docs/b.md",
            "docs/c.md",
        ]
        wide["limits"]["max_changed_files"] = 3
        wide_package = writer_contract.validate_package(wide)
        with self.assertRaisesRegex(
            writer_process.WriterProcessError, "at most 2 owned targets"
        ):
            writer_process.validate_writer_profile_package(luna, wide_package)

        oversized = valid_v2_raw()
        oversized["limits"]["max_patch_bytes"] = 512 * 1024 + 1
        oversized_package = writer_contract.validate_package(oversized)
        with self.assertRaisesRegex(
            writer_process.WriterProcessError, "max_patch_bytes"
        ):
            writer_process.validate_writer_profile_package(luna, oversized_package)

        with self.assertRaisesRegex(
            writer_process.WriterProcessError, "unknown writer profile"
        ):
            writer_process.resolve_writer_profile("invented-writer")

    def test_profile_prompt_keeps_quality_context_untrusted(self) -> None:
        package = writer_contract.validate_package(valid_v2_raw())
        profile = writer_process.writer_profile_record(
            writer_process.resolve_writer_profile("complex-sol")
        )
        prompt = writer_runtime_candidate._writer_prompt(package, profile)
        self.assertIn("WRITER_PROFILE_ID=complex-sol", prompt)
        self.assertIn("WRITER_ROLE=sol", prompt)
        self.assertIn("acceptance_criteria", prompt)
        self.assertIn("untrusted data", prompt)
        self.assertIn("never expand targets or actions", prompt)

    def test_cli_forwards_explicit_profile(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            writer_cli,
            "plan_writer",
            return_value={
                "operation": "writer-plan",
                "model_calls": 0,
                "writes": [],
            },
        ) as routed, contextlib.redirect_stdout(output):
            code = writer_cli.main(
                [
                    "writer-plan",
                    "--package",
                    "package.json",
                    "--repository",
                    "repo",
                    "--expected-package-digest",
                    "a" * 64,
                    "--writer-profile",
                    "complex-sol",
                ]
            )
        self.assertEqual(code, 0)
        routed.assert_called_once_with(
            package_path="package.json",
            repository="repo",
            expected_package_digest="a" * 64,
            writer_profile="complex-sol",
        )
        with self.assertRaises(SystemExit):
            writer_cli.main(
                [
                    "writer-plan",
                    "--package",
                    "package.json",
                    "--repository",
                    "repo",
                    "--expected-package-digest",
                    "a" * 64,
                    "--writer-profile",
                    "invented-writer",
                ]
            )

    def test_plan_rejects_complex_sol_v1_before_capability_probe(self) -> None:
        fixture = Fixture()
        try:
            with fixture.environment(), mock.patch.object(
                writer_process,
                "probe_codex_capabilities",
            ) as probe:
                with self.assertRaisesRegex(
                    writer_runtime.WriterRuntimeError,
                    "does not accept package v1",
                ):
                    writer_runtime.plan_writer(
                        package_path=fixture.package_path,
                        repository=fixture.repo,
                        expected_package_digest=fixture.package.digest,
                        writer_profile="complex-sol",
                    )
            probe.assert_not_called()
        finally:
            fixture.close()

    def test_complex_sol_runtime_binds_profile_and_quality_context(self) -> None:
        fixture = Fixture()
        try:
            package = install_v2_package(fixture)
            adapter = FakeProcessAdapter()
            with fixture.environment(), fixture.preflight():
                plan = writer_runtime.plan_writer(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=package.digest,
                    writer_profile="complex-sol",
                )
                result = writer_runtime.run_writer(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=package.digest,
                    expected_head_sha=package.expected_head_sha,
                    ack_isolated_worktree_write=True,
                    writer_profile="complex-sol",
                    process_adapter=adapter,
                )
            self.assertEqual(plan["writer_route"]["role"], "sol")
            self.assertEqual(plan["writer_route"]["model"], "gpt-5.6-sol")
            self.assertEqual(result["state"], "ship_candidate")
            self.assertEqual(
                adapter.calls, ["sol", "dynamic_workflow_sol_reviewer"]
            )
            run_dir = Path(result["candidate"]["candidate_package_path"]).parent
            candidate = json.loads(
                (run_dir / "candidate-package.json").read_text(encoding="utf-8")
            )
            authorization = json.loads(
                (run_dir / "writer-authorization.json").read_text(encoding="utf-8")
            )
            checkpoint = json.loads(
                (run_dir / "checkpoint.json").read_text(encoding="utf-8")
            )
            self.assertEqual(candidate["candidate_package_version"], 2)
            self.assertEqual(candidate["package_version"], 2)
            self.assertEqual(candidate["quality_context"], package.quality_context)
            self.assertEqual(
                candidate["writer_profile"]["profile_id"], "complex-sol"
            )
            self.assertEqual(
                authorization["writer_profile"], candidate["writer_profile"]
            )
            self.assertEqual(
                checkpoint["writer_profile"], candidate["writer_profile"]
            )
            self.assertEqual(
                writer_runtime.status_writer(run_dir)["integrity"], "match"
            )
        finally:
            fixture.close()

    def test_profile_is_revision_bound_and_tamper_evident(self) -> None:
        fixture = Fixture()
        try:
            package = install_v2_package(fixture)
            first_adapter = FakeProcessAdapter()
            with fixture.environment(), fixture.preflight():
                first = writer_runtime.run_writer(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=package.digest,
                    expected_head_sha=package.expected_head_sha,
                    ack_isolated_worktree_write=True,
                    writer_profile="bounded-luna",
                    process_adapter=first_adapter,
                )
            first_run = Path(first["candidate"]["candidate_package_path"]).parent
            writer_runtime.cleanup_writer(
                run_dir=first_run,
                expected_run_id=first["run_id"],
                expected_package_digest=package.digest,
                ack_delete_isolated_worktree=True,
            )

            second_adapter = FakeProcessAdapter()
            with fixture.environment(), fixture.preflight():
                second = writer_runtime.run_writer(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=package.digest,
                    expected_head_sha=package.expected_head_sha,
                    ack_isolated_worktree_write=True,
                    writer_profile="complex-sol",
                    process_adapter=second_adapter,
                )
            self.assertNotEqual(
                first["candidate"]["candidate_revision"],
                second["candidate"]["candidate_revision"],
            )
            self.assertEqual(
                first_adapter.calls, ["luna", "dynamic_workflow_sol_reviewer"]
            )
            self.assertEqual(
                second_adapter.calls, ["sol", "dynamic_workflow_sol_reviewer"]
            )

            run_dir = Path(second["candidate"]["candidate_package_path"]).parent
            checkpoint_path = run_dir / "checkpoint.json"
            summary_path = run_dir / "summary.json"
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            tampered = dict(checkpoint["writer_profile"])
            tampered["profile_id"] = "bounded-luna"
            checkpoint["writer_profile"] = tampered
            summary["writer_profile"] = tampered
            checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(
                writer_runtime.WriterRuntimeError, "trusted registry"
            ):
                writer_runtime.status_writer(run_dir)
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
