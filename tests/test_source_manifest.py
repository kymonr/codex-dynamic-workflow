"""Full source-integrity regression and negative fixtures; no models or network."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import stat
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import validate_source_manifest as checks


class SourceManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.files = {'a.txt': b'one\n', 'nested/b.bin': b'\xff\x00two\r\n'}
        for relative, data in self.files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.manifest = {p: hashlib.sha256(data).hexdigest() for p, data in self.files.items()}
        self.save(self.manifest)

    def save(self, value):
        (self.root / checks.MANIFEST).write_text(json.dumps(value), encoding='utf-8')

    def test_repository_manifest_verifies_every_entry(self):
        self.assertEqual(checks.validate(ROOT), [])

    def test_exact_binary_bytes_and_inventory_pass_without_writes(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(checks.validate(self.root, expected_paths=set(before)), [])
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes()
                                  for p in self.root.rglob('*') if p.is_file()})

    def test_changed_or_missing_file_is_reported(self):
        (self.root / 'a.txt').write_bytes(b'changed\n')
        (self.root / 'nested/b.bin').unlink()
        errors = checks.validate(self.root)
        self.assertEqual(len(errors), 2)
        self.assertIn('SHA256 mismatch: a.txt', errors[0])
        self.assertIn('nested/b.bin', errors[1])

    def test_line_endings_are_not_normalized(self):
        (self.root / 'a.txt').write_bytes(b'one\r\n')
        self.assertIn('SHA256 mismatch', str(checks.validate(self.root)))

    def test_duplicate_key_is_not_silently_overwritten(self):
        h = self.manifest['a.txt']
        (self.root / checks.MANIFEST).write_text(
            '{"a.txt":"' + '0' * 64 + '","a.txt":"' + h + '"}', encoding='utf-8')
        self.assertIn('duplicate manifest key', str(checks.validate(self.root)))

    def test_empty_nonobject_and_invalid_hashes_fail(self):
        for value in ({}, [], {'a.txt': True}, {'a.txt': 'bad'}, {'a.txt': 'g' * 64}):
            with self.subTest(value=value):
                self.save(value)
                self.assertTrue(checks.validate(self.root))

    def test_unsafe_paths_and_self_reference_fail(self):
        for path in ('../outside', '/absolute', 'C:/absolute', 'a\\b', './a.txt',
                     'nested//b.bin', 'a.txt/', 'name:stream', 'bad\x00path',
                     'nul.txt', 'a.txt ', '.git/config', checks.MANIFEST):
            with self.subTest(path=path):
                self.save({path: '0' * 64})
                reason = ('must not hash itself' if path == checks.MANIFEST else
                          'device path' if path == 'nul.txt' else 'unsafe/noncanonical')
                self.assertIn(reason, str(checks.validate(self.root)))

    def test_case_aliases_and_directories_fail(self):
        self.save({**self.manifest, 'A.txt': self.manifest['a.txt']})
        self.assertIn('case-aliased', str(checks.validate(self.root)))
        self.save({'nested': '0' * 64})
        self.assertIn('regular file', str(checks.validate(self.root)))

    def test_missing_and_extra_inventory_entries_fail(self):
        expected = set(self.files) | {checks.MANIFEST, 'new.py'}
        self.assertIn('missing manifest entry: new.py',
                      checks.validate(self.root, expected_paths=expected))
        self.assertIn('untracked manifest entry: nested/b.bin',
                      checks.validate(self.root, expected_paths={'a.txt', checks.MANIFEST}))

    def test_symlink_and_reparse_paths_fail_before_read(self):
        # Synthetic stat flags also exercise this rule on Windows without link privileges.
        original = Path.lstat
        target = self.root / 'nested'
        def linked(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == target:
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
            return result
        for mode, attributes in ((stat.S_IFDIR, 1024), (stat.S_IFLNK, 0)):
            with self.subTest(mode=mode), patch.object(Path, 'lstat', linked):
                self.assertIn('link/reparse', str(checks.validate(self.root)))

    def test_cli_pass_fail_and_bad_json_exit_codes(self):
        for content, expected in ((json.dumps(self.manifest), 0), ('{', 1), ('{}', 1)):
            (self.root / checks.MANIFEST).write_text(content, encoding='utf-8')
            output = io.StringIO()
            with redirect_stdout(output):
                code = checks.main(['--root', str(self.root)])
            self.assertEqual(code, expected)
            self.assertEqual(json.loads(output.getvalue())['status'], 'FAIL' if expected else 'PASS')

    def test_requested_git_inventory_failure_is_not_a_pass(self):
        output = io.StringIO()
        with patch.object(checks, 'tracked_paths', side_effect=OSError('git unavailable')), redirect_stdout(output):
            self.assertEqual(checks.main(['--root', str(self.root), '--check-tracked']), 1)
        self.assertEqual(json.loads(output.getvalue())['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
