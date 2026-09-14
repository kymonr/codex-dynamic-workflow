"""Verify every declared source hash; --check-tracked also checks Git inventory.

Read-only, standard-library validation of exact bytes. This is not authentication,
installation ownership, model execution, or an automatic manifest repair command.
The manifest excludes itself to avoid a self-referential checksum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'SOURCE_MANIFEST.json'


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate manifest key: ' + key)
        result[key] = value
    return result


def source_path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative
            or any(c in relative for c in '\\:\x00*?')
            or PurePosixPath(relative).is_absolute()
            or PurePosixPath(relative).as_posix() != relative
            or any(p in {'.', '..', '.git'} or p.rstrip(' .') != p
                   for p in relative.split('/'))):
        raise ValueError('unsafe/noncanonical manifest path: ' + repr(relative))
    current = root
    for part in relative.split('/'):
        if re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part, re.I):
            raise ValueError('device path in manifest: ' + relative)
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
            raise ValueError('link/reparse manifest path: ' + relative)
    if not current.resolve().is_relative_to(root) or not current.is_file():
        raise ValueError('manifest source is not an in-root regular file: ' + relative)
    return current


def tracked_paths(root: Path) -> set[str]:
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8',
                              timeout=15).stdout
    if Path(git('rev-parse', '--show-toplevel').strip()).resolve() != root.resolve():
        raise ValueError('inventory check requires the repository root')
    return set(git('ls-files', '--cached', '-z').split('\x00')) - {''}


def validate(root: Path = ROOT, *, expected_paths: set[str] | None = None) -> list[str]:
    errors = []
    try:
        root = Path(root).resolve(strict=True)
        manifest = json.loads(source_path(root, MANIFEST).read_text(encoding='utf-8'),
                              object_pairs_hook=unique_pairs)
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError('manifest must be a nonempty path-to-SHA256 object')
    except (OSError, ValueError) as exc:
        return ['manifest: ' + str(exc)]
    if expected_paths is not None:
        expected = set(expected_paths) - {MANIFEST}
        for path in sorted(expected - set(manifest)):
            errors.append('missing manifest entry: ' + path)
        for path in sorted(set(manifest) - expected):
            errors.append('untracked manifest entry: ' + path)
    seen = set()
    for relative, expected_hash in manifest.items():
        try:
            if relative.casefold() == MANIFEST.casefold():
                raise ValueError('manifest must not hash itself')
            if relative.casefold() in seen:
                raise ValueError('case-aliased manifest path: ' + relative)
            seen.add(relative.casefold())
            if not isinstance(expected_hash, str) or re.fullmatch(r'[0-9a-f]{64}', expected_hash) is None:
                raise ValueError('invalid SHA256: ' + relative)
            with source_path(root, relative).open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != expected_hash:
                errors.append(f'SHA256 mismatch: {relative}: expected={expected_hash} actual={actual}')
        except (OSError, ValueError) as exc:
            errors.append(f'{relative}: {exc}')
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check-tracked', action='store_true',
                        help='Also require exactly all Git-tracked files except the manifest itself')
    args = parser.parse_args(argv)
    try:
        expected = tracked_paths(args.root) if args.check_tracked else None
        errors = validate(args.root, expected_paths=expected)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        errors = [str(exc)]
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'errors': errors},
                     ensure_ascii=False, indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
