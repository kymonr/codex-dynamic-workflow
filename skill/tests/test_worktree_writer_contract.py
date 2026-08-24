from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import writer_contract


def valid_raw() -> dict:
    return {
        "version": 1,
        "name": "bounded-change",
        "objective": "Create one bounded UTF-8 document.",
        "base": {
            "repository_full_name": "owner/repo",
            "expected_head_sha": "a" * 40,
            "expected_tree_sha": "b" * 40,
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
            "required_verification_ids": ["unit"],
            "commands": [
                {
                    "id": "unit",
                    "argv": ["python", "-m", "unittest", "discover", "-s", "skill/tests"],
                    "timeout_seconds": 120,
                }
            ],
        },
    }


class WriterContractTests(unittest.TestCase):
    def test_valid_package_is_deterministic(self) -> None:
        first = writer_contract.validate_package(valid_raw())
        second = writer_contract.validate_package(json.loads(json.dumps(valid_raw())))
        self.assertEqual(first.value, second.value)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(len(first.digest), 64)

    def test_closed_schema_and_integer_types(self) -> None:
        raw = valid_raw()
        raw["extra"] = True
        with self.assertRaisesRegex(writer_contract.WriterContractError, "unknown"):
            writer_contract.validate_package(raw)
        raw = valid_raw()
        raw["version"] = True
        with self.assertRaises(writer_contract.WriterContractError):
            writer_contract.validate_package(raw)
        raw = valid_raw()
        raw["limits"]["max_changed_files"] = True
        with self.assertRaises(writer_contract.WriterContractError):
            writer_contract.validate_package(raw)

    def test_duplicate_json_nan_nul_and_bom_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = {
                "duplicate.json": b'{"version":1,"version":1}',
                "nan.json": b'{"value":NaN}',
                "nul.json": b'{"value":"a\x00b"}',
                "bom.json": b'\xef\xbb\xbf{}',
            }
            for name, payload in cases.items():
                path = root / name
                path.write_bytes(payload)
                with self.subTest(name=name):
                    with self.assertRaises(writer_contract.WriterContractError):
                        writer_contract.load_json_strict(path)

    def test_owned_paths_are_exact_and_windows_safe(self) -> None:
        for path in (
            "../escape.md", "/absolute.md", r"C:\\drive.md", r"a\\b.md",
            "a//b.md", "a/./b.md", ".git/config", "AUX.txt", "name. ",
        ):
            raw = valid_raw()
            raw["authority"]["owned_targets"] = [path]
            with self.subTest(path=path):
                with self.assertRaises(writer_contract.WriterContractError):
                    writer_contract.validate_package(raw)
        raw = valid_raw()
        raw["authority"]["owned_targets"] = ["Docs/A.md", "docs/a.md"]
        raw["limits"]["max_changed_files"] = 2
        with self.assertRaisesRegex(writer_contract.WriterContractError, "case-insensitively"):
            writer_contract.validate_package(raw)

    def test_actions_and_limits_are_bounded(self) -> None:
        raw = valid_raw()
        raw["authority"]["allowed_actions"] = ["create", "delete"]
        with self.assertRaises(writer_contract.WriterContractError):
            writer_contract.validate_package(raw)
        raw = valid_raw()
        raw["limits"]["max_changed_files"] = 2
        with self.assertRaisesRegex(writer_contract.WriterContractError, "owned target"):
            writer_contract.validate_package(raw)

    def test_verification_argv_is_exact_and_non_shell(self) -> None:
        forbidden = [
            ["bash", "-lc", "pytest"],
            ["python", "-c", "print(1)"],
            ["python", "-m", "pip", "install", "x"],
            ["python", "/tmp/test.py"],
            ["python", "../outside.py"],
        ]
        for argv in forbidden:
            raw = valid_raw()
            raw["verification"]["commands"][0]["argv"] = argv
            with self.subTest(argv=argv):
                with self.assertRaises(writer_contract.WriterContractError):
                    writer_contract.validate_package(raw)

    def test_contract_output_is_zero_authority(self) -> None:
        contract = writer_contract.package_contract()
        self.assertFalse(contract["model_generated_authority"])
        self.assertFalse(contract["automatic_apply"])
        self.assertEqual(contract["grantable_actions"], ["create", "modify"])


if __name__ == "__main__":
    unittest.main()
