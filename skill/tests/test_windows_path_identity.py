from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import runner
from runtime.path_safety import (
    UnsafeRunPathError,
    assert_safe_run_tree,
    canonical_runtime_path,
)
from runtime.run_lease import lease_path_for


def short_alias(path: Path) -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(
        str(path), buffer, len(buffer)
    )
    if length == 0 or length >= len(buffer):
        raise unittest.SkipTest(
            "Windows short-name alias is unavailable for this fixture"
        )
    short = Path(buffer.value)
    if os.path.normcase(str(short)) == os.path.normcase(str(path)):
        raise unittest.SkipTest(
            "fixture did not produce a distinct Windows short-name alias"
        )
    return short


@unittest.skipUnless(os.name == "nt", "Windows 8.3 path identity regression")
class WindowsPathIdentityTests(unittest.TestCase):
    def test_short_and_long_paths_share_one_runtime_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runtime path identity ") as raw:
            long_path = Path(raw).resolve()
            short_path = short_alias(long_path)
            self.assertEqual(
                canonical_runtime_path(
                    short_path, label="short-path fixture"
                ),
                long_path,
            )
            self.assertEqual(
                lease_path_for(short_path / "run"),
                lease_path_for(long_path / "run"),
            )

    def test_run_root_overlap_is_detected_across_aliases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runtime overlap identity ") as raw:
            long_parent = Path(raw).resolve()
            short_parent = short_alias(long_parent)
            workdir = long_parent / "runs" / "workdir"
            workdir.mkdir(parents=True)
            codex_home = long_parent / "codex-home"
            codex_home.mkdir()
            with self.assertRaisesRegex(runner.WorkflowError, "重叠"):
                runner._prepare_run_root(
                    short_parent / "runs",
                    {"workdir": str(workdir)},
                    codex_home,
                )

    def test_recursive_reparse_scan_uses_canonical_alias_identity(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="runtime reparse identity "
        ) as raw:
            long_root = Path(raw).resolve()
            short_root = short_alias(long_root)
            unsafe = long_root / "tasks" / "only"
            unsafe.mkdir(parents=True)
            observed: list[Path] = []

            def simulated_reparse(path: Path) -> bool:
                candidate = Path(path)
                observed.append(candidate)
                return candidate == unsafe

            with mock.patch(
                "runtime.path_safety.is_reparse",
                side_effect=simulated_reparse,
            ):
                with self.assertRaisesRegex(
                    UnsafeRunPathError, "reparse point"
                ):
                    assert_safe_run_tree(short_root)

            self.assertIn(unsafe, observed)
            self.assertNotIn(short_root / "tasks" / "only", observed)


if __name__ == "__main__":
    unittest.main()
