from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import versioning


class VersionFileNewlineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "skill").mkdir()
        self.version_file = self.root / "skill" / "VERSION"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_accepts_no_newline_lf_and_crlf(self) -> None:
        cases = (
            (b"1.0.0-rc.2", "1.0.0-rc.2"),
            (b"1.0.0-rc.2\n", "1.0.0-rc.2"),
            (b"1.0.0-rc.2\r\n", "1.0.0-rc.2"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.version_file.write_bytes(raw)
                self.assertEqual(versioning.read_skill_version(self.root), expected)

    def test_rejects_empty_multiple_or_bare_carriage_return_lines(self) -> None:
        cases = (
            b"",
            b"\n",
            b"\r\n",
            b"1.0.0\n\n",
            b"1.0.0\r\n\r\n",
            b"1.0.0\r",
            b"1.0.0\r1.0.1",
            b"1.0.0\n1.0.1",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.version_file.write_bytes(raw)
                with self.assertRaisesRegex(
                    versioning.VersionError,
                    "exactly one version line",
                ):
                    versioning.read_skill_version(self.root)

    def test_rejects_bom_nul_and_surrounding_whitespace(self) -> None:
        cases = (
            b"\xef\xbb\xbf1.0.0\n",
            b"1.0.0\x00\n",
            b" 1.0.0\n",
            b"1.0.0 \n",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.version_file.write_bytes(raw)
                with self.assertRaises(versioning.VersionError):
                    versioning.read_skill_version(self.root)

    def test_bump_normalizes_crlf_to_lf(self) -> None:
        self.version_file.write_bytes(b"1.0.0-rc.2\r\n")
        result = versioning.bump_skill_version(self.root)
        self.assertEqual(result["version"], "1.0.0-rc.3")
        self.assertEqual(self.version_file.read_bytes(), b"1.0.0-rc.3\n")


if __name__ == "__main__":
    unittest.main()
