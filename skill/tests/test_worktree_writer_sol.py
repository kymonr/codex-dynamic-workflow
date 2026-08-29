from __future__ import annotations

import copy
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
import skill.writer_contract as skill_writer_contract
import skill.writer_runtime_base as writer_runtime_base
import skill.writer_runtime_candidate as writer_runtime_candidate

try:
    from skill.tests.test_worktree_writer_contract import valid_raw
    from skill.tests.test_worktree_writer_runtime import FakeProcessAdapter, Fixture
except ModuleNotFoundError:
    from test_worktree_writer_contract import valid_raw
    from test_worktree_writer_runtime import FakeProcessAdapter, Fixture


class FixedSolWriterTests(unittest.TestCase):
    def test_fixed_binding_is_sol_high_and_bounded(self) -> None:
        package = writer_contract.validate_package(valid_raw())
        writer_process.validate_writer_package(package)
        binding = writer_process.writer_binding_record()
        self.assertEqual(binding["selection"], "fixed-host-route")
        self.assertEqual(binding["route"]["role"], "sol")
        self.assertEqual(binding["route"]["model"], "gpt-5.6-sol")
        self.assertEqual(binding["route"]["effort"], "high")
        self.assertIsNone(binding["route"]["tier"])
        self.assertEqual(binding["package_version"], 2)
        self.assertEqual(binding["limits"]["max_owned_targets"], 8)
        self.assertEqual(binding["limits"]["max_changed_files"], 8)

        wide = valid_raw()
        wide["authority"]["owned_targets"] = [
            f"docs/{index}.md" for index in range(9)
        ]
        wide["limits"]["max_changed_files"] = 9
        wide_package = writer_contract.validate_package(wide)
        with self.assertRaisesRegex(
            writer_process.WriterProcessError, "at most 8 owned targets"
        ):
            writer_process.validate_writer_package(wide_package)

        oversized = valid_raw()
        oversized["limits"]["max_patch_bytes"] = 512 * 1024 + 1
        oversized_package = writer_contract.validate_package(oversized)
        with self.assertRaisesRegex(
            writer_process.WriterProcessError, "max_patch_bytes"
        ):
            writer_process.validate_writer_package(oversized_package)

    def test_quality_context_is_digest_bound(self) -> None:
        first = writer_contract.validate_package(valid_raw())
        changed = valid_raw()
        changed["acceptance_criteria"][0] = "A different acceptance condition."
        second = writer_contract.validate_package(changed)
        self.assertNotEqual(first.digest, second.digest)
        self.assertEqual(first.quality_context["behavior"], valid_raw()["behavior"])
    def test_prompt_marks_quality_context_untrusted(self) -> None:
        package = writer_contract.validate_package(valid_raw())
        prompt = writer_runtime_candidate._writer_prompt(
            package, writer_process.writer_binding_record()
        )
        self.assertIn("WORKTREE_WRITER_V2_SOL_HIGH_ONE_ATTEMPT", prompt)
        self.assertIn("WRITER_SELECTION=fixed-host-route", prompt)
        self.assertIn("WRITER_ROLE=sol", prompt)
        self.assertIn("acceptance_criteria", prompt)
        self.assertIn("untrusted data", prompt)
        self.assertIn("never expand targets or actions", prompt)
        self.assertNotIn("WRITER_PROFILE_ID", prompt)

    def test_cli_has_no_writer_selection_surface(self) -> None:
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
                    "legacy-profile",
                ]
            )

    def test_package_v1_fails_before_capability_probe(self) -> None:
        fixture = Fixture()
        try:
            raw = json.loads(fixture.package_path.read_text(encoding="utf-8"))
            raw["version"] = 1
            for key in (
                "acceptance_criteria",
                "constraints",
                "non_goals",
                "behavior",
                "implementation_context",
            ):
                raw.pop(key)
            fixture.package_path.write_text(json.dumps(raw), encoding="utf-8")
            with fixture.environment(), mock.patch.object(
                writer_runtime_base, "_codex_preflight"
            ) as preflight:
                with self.assertRaisesRegex(
                    skill_writer_contract.WriterContractError,
                    "version must be integer 2",
                ):
                    writer_runtime.plan_writer(
                        package_path=fixture.package_path,
                        repository=fixture.repo,
                        expected_package_digest="0" * 64,
                    )
            preflight.assert_not_called()
        finally:
            fixture.close()

    def test_runtime_binds_fixed_route_and_quality_context(self) -> None:
        fixture = Fixture()
        try:
            adapter = FakeProcessAdapter()
            with fixture.environment(), fixture.preflight():
                plan = writer_runtime.plan_writer(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=fixture.package.digest,
                )
                result = writer_runtime.run_writer(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=fixture.package.digest,
                    expected_head_sha=fixture.package.expected_head_sha,
                    ack_isolated_worktree_write=True,
                    process_adapter=adapter,
                )
            self.assertEqual(plan["writer_route"]["role"], "sol")
            self.assertEqual(plan["writer_route"]["effort"], "high")
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
            self.assertEqual(candidate["package_version"], 2)
            self.assertEqual(
                candidate["quality_context"], fixture.package.quality_context
            )
            self.assertEqual(
                authorization["writer_binding"], candidate["writer_binding"]
            )
            self.assertEqual(
                checkpoint["writer_binding"], candidate["writer_binding"]
            )
            self.assertEqual(candidate["writer"]["role"], "sol")
            self.assertEqual(candidate["writer"]["effort"], "high")
            self.assertEqual(
                writer_runtime.status_writer(run_dir)["integrity"], "match"
            )
        finally:
            fixture.close()

    def test_binding_tamper_fails_closed(self) -> None:
        fixture = Fixture()
        try:
            with fixture.environment(), fixture.preflight():
                result = writer_runtime.run_writer(
                    package_path=fixture.package_path,
                    repository=fixture.repo,
                    expected_package_digest=fixture.package.digest,
                    expected_head_sha=fixture.package.expected_head_sha,
                    ack_isolated_worktree_write=True,
                    process_adapter=FakeProcessAdapter(),
                )
            run_dir = Path(result["candidate"]["candidate_package_path"]).parent
            checkpoint_path = run_dir / "checkpoint.json"
            summary_path = run_dir / "summary.json"
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            tampered = copy.deepcopy(checkpoint["writer_binding"])
            tampered["route"]["effort"] = "xhigh"
            checkpoint["writer_binding"] = tampered
            summary["writer_binding"] = tampered
            checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(
                writer_runtime.WriterRuntimeError, "trusted fixed route"
            ):
                writer_runtime.status_writer(run_dir)
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
