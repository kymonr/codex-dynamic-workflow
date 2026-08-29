from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_candidate
import fleet_contract


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def valid_raw(*, head: str = "a" * 40, agent_count: int = 6) -> dict:
    return {
        "version": 1,
        "name": "adversarial-check",
        "preset": "adversarial-review",
        "agent_count": agent_count,
        "objective": "Review the frozen candidate for material defects.",
        "acceptance_criteria": ["Every material claim has concrete evidence."],
        "scope": ["Review the declared candidate and verification evidence."],
        "exclusions": ["Do not modify the repository."],
        "candidate": {
            "repository_full_name": "owner/repo",
            "expected_head_sha": head,
            "changed_files": [],
        },
        "risk_tags": [],
        "verification": {"required_ids": [], "commands": []},
        "limits": {
            "max_patch_bytes": 524288,
            "max_untracked_file_bytes": 131072,
            "max_candidate_bytes": 1048576,
            "max_agent_output_bytes": 524288,
            "max_agent_log_bytes": 1048576,
        },
    }


class FleetContractTests(unittest.TestCase):
    def test_agent_count_boundary_is_exactly_four_to_twelve(self) -> None:
        self.assertEqual(fleet_contract.validate_package(valid_raw(agent_count=4)).agent_count, 4)
        self.assertEqual(fleet_contract.validate_package(valid_raw(agent_count=12)).agent_count, 12)
        for count in (3, 13):
            with self.assertRaisesRegex(fleet_contract.FleetContractError, "between 4 and 12"):
                fleet_contract.validate_package(valid_raw(agent_count=count))

    def test_all_presets_validate_and_digest_is_deterministic(self) -> None:
        for preset in sorted(fleet_contract.PRESETS):
            raw = valid_raw()
            raw["preset"] = preset
            first = fleet_contract.validate_package(raw)
            second = fleet_contract.validate_package(json.loads(json.dumps(raw)))
            self.assertEqual(first.value, second.value)
            self.assertEqual(first.digest, second.digest)

    def test_closed_schema_paths_risks_and_commands_fail_closed(self) -> None:
        raw = valid_raw()
        raw["extra"] = True
        with self.assertRaisesRegex(fleet_contract.FleetContractError, "unknown"):
            fleet_contract.validate_package(raw)

        raw = valid_raw()
        raw["candidate"]["changed_files"] = ["../escape.py"]
        with self.assertRaises(fleet_contract.FleetContractError):
            fleet_contract.validate_package(raw)

        raw = valid_raw()
        raw["risk_tags"] = ["invented-risk"]
        with self.assertRaises(fleet_contract.FleetContractError):
            fleet_contract.validate_package(raw)

        raw = valid_raw()
        raw["verification"] = {
            "required_ids": ["bad"],
            "commands": [
                {"id": "bad", "argv": ["python", "-c", "print(1)"], "timeout_seconds": 10}
            ],
        }
        with self.assertRaisesRegex(fleet_contract.FleetContractError, "inline"):
            fleet_contract.validate_package(raw)

    def test_worst_case_inline_context_is_bounded(self) -> None:
        raw = valid_raw(agent_count=12)
        raw["limits"]["max_candidate_bytes"] = 1024 * 1024
        raw["limits"]["max_agent_output_bytes"] = 1024 * 1024
        with self.assertRaisesRegex(
            fleet_contract.FleetContractError,
            "inline context budget",
        ):
            fleet_contract.validate_package(raw)

    def test_strict_json_rejects_duplicate_nan_bom_and_nul(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = {
                "duplicate.json": b'{"version":1,"version":1}',
                "nan.json": b'{"value":NaN}',
                "bom.json": b'\xef\xbb\xbf{}',
                "nul.json": b'{"value":"a\x00b"}',
            }
            for name, payload in cases.items():
                path = root / name
                path.write_bytes(payload)
                with self.subTest(name=name), self.assertRaises(fleet_contract.FleetContractError):
                    fleet_contract.load_json_strict(path)


class FleetCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "core.autocrlf", "false")
        git(self.repo, "remote", "add", "origin", "https://github.com/owner/repo.git")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "base.txt")
        git(self.repo, "commit", "-m", "base")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def package(self, changed: list[str]) -> fleet_contract.FleetPackage:
        raw = valid_raw(head=git(self.repo, "rev-parse", "HEAD"))
        raw["candidate"]["changed_files"] = changed
        return fleet_contract.validate_package(raw)

    def test_clean_candidate_revision_is_deterministic(self) -> None:
        package = self.package([])
        first = fleet_candidate.capture_candidate(self.repo, package)
        second = fleet_candidate.capture_candidate(self.repo, package)
        self.assertEqual(first, second)
        self.assertTrue(first["candidate_revision"].startswith("sha256:"))
        fleet_candidate.validate_candidate_package(first)

    def test_untracked_text_is_captured_and_changed_set_is_exact(self) -> None:
        (self.repo / "new.txt").write_text("candidate\n", encoding="utf-8")
        package = self.package(["new.txt"])
        candidate = fleet_candidate.capture_candidate(self.repo, package)
        self.assertEqual(candidate["changed_files"], ["new.txt"])
        self.assertEqual(candidate["untracked_files"][0]["content"], "candidate\n")

        wrong = self.package([])
        with self.assertRaisesRegex(fleet_candidate.FleetCandidateError, "changed-file set"):
            fleet_candidate.capture_candidate(self.repo, wrong)

    def test_binary_candidate_is_rejected(self) -> None:
        (self.repo / "binary.bin").write_bytes(b"bad\x00data")
        package = self.package(["binary.bin"])
        with self.assertRaisesRegex(fleet_candidate.FleetCandidateError, "NUL"):
            fleet_candidate.capture_candidate(self.repo, package)


if __name__ == "__main__":
    unittest.main()
