"""Manifest-scoped reversible installation; never edits Codex config or old roles.

Dry-run by default. Target CODEX_HOME must be explicitly supplied from observed
configuration. No discovery inference, network, Git or model calls occur here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat
import sys
import uuid

from validate_package import ROOT, SKILL, LEGACY_SKILL, PROFILE_NAMES, validate


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(root: Path) -> dict[str, bytes]:
    files = {f'skills/codex-dynamic-workflow/{p.relative_to(root / SKILL).as_posix()}': p.read_bytes()
             for p in sorted((root / SKILL).rglob('*')) if p.is_file()}
    files.update({f'skills/dispatching-native-agents/{p.relative_to(root / LEGACY_SKILL).as_posix()}': p.read_bytes()
                  for p in sorted((root / LEGACY_SKILL).rglob('*')) if p.is_file()})
    files.update({f'agents/{name}.toml': (root/'profiles'/f'{name}.toml').read_bytes() for name in PROFILE_NAMES})
    return files


def destination(home: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    parts = pure.parts
    allowed = ((len(parts) >= 3 and parts[0] == 'skills' and parts[1] in {'codex-dynamic-workflow', 'dispatching-native-agents'})
               or relative in {f'agents/{n}.toml' for n in PROFILE_NAMES})
    if not allowed or pure.is_absolute() or any(p in {'..', '.'} or ':' in p or '\\' in p for p in parts):
        raise ValueError(f'not an owned destination: {relative}')
    base = home.resolve(strict=True)
    current = base
    for part in parts:
        current = current / part
        if current.exists() or current.is_symlink():
            flags = getattr(current.lstat(), 'st_file_attributes', 0)
            if current.is_symlink() or flags & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
                raise ValueError(f'reparse/symlink destination refused: {current}')
    if not current.resolve().is_relative_to(base):
        raise ValueError('destination escaped the explicit home')
    return current


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.cwf-{uuid.uuid4().hex}.tmp')
    try:
        with temp.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()  # exact task-created temporary file only


def inplace_write(path: Path, data: bytes, expected: bytes) -> None:
    """Explicit ordinary write for an existing SKILL.md whose replacement is blocked.

    Does not change ACLs, privileges or other processes. A Windows byte-range lock
    protects the update where available. This is NOT crash-atomic: abrupt termination
    may leave a pending/conflicted receipt requiring inspected recovery from preimage.
    """
    if path.name != 'SKILL.md' or path.is_symlink() or path.stat().st_nlink != 1:
        raise ValueError('in-place update requires an existing single-link SKILL.md')
    with path.open('r+b') as stream:
        locked = False
        length = max(len(expected), len(data), 1)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, length)
            locked = True
        try:
            if stream.read() != expected:
                raise ValueError('in-place preimage drift')
            try:
                stream.seek(0); stream.write(data); stream.truncate()
                stream.flush(); os.fsync(stream.fileno())
            except BaseException:
                # Same task-held handle; compensate before releasing the Windows lock.
                stream.seek(0); stream.write(expected); stream.truncate()
                stream.flush(); os.fsync(stream.fileno())
                raise
        finally:
            if locked:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, length)


def read_if_file(path: Path) -> bytes | None:
    if path.exists() and not path.is_file():
        raise ValueError(f'destination is not a file: {path}')
    return path.read_bytes() if path.exists() else None


def checked_hashes(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be a path-to-SHA256 mapping')
    result = {}
    for path, sha in value.items():
        if (not isinstance(path, str) or not isinstance(sha, str)
                or re.fullmatch(r'[0-9a-fA-F]{64}', sha) is None):
            raise ValueError(f'invalid {label} path/hash')
        result[path] = sha.lower()
    return result


def parse_adoptions(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        path, sep, sha = item.partition('=')
        if not sep or path in result:
            raise ValueError('adoption requires unique PATH=SHA256 entries')
        result[path] = sha
    return checked_hashes(result, 'adoption')


def install(root: Path, home: Path, *, apply: bool = False,
            expected_skill_sha: str | None = None, inplace_skill: bool = False,
            adopt: dict[str, str] | None = None) -> dict:
    errors = validate(root)
    if errors:
        raise ValueError('source validation failed: ' + '; '.join(errors))
    home = home.resolve(strict=True)
    canonical_existing = (home / 'skills/codex-dynamic-workflow/SKILL.md').is_file()
    legacy_existing = (home / 'skills/dispatching-native-agents/SKILL.md').is_file()
    if not (canonical_existing or legacy_existing):
        raise ValueError('existing CODEX_HOME/skills layout not confirmed; no guessed first install')
    expected_rel = ('skills/codex-dynamic-workflow/SKILL.md' if canonical_existing
                    else 'skills/dispatching-native-agents/SKILL.md')
    payload = manifest(root)
    state_path = root / '.delivery/install-state.json'
    state_before = read_if_file(state_path)
    prior = json.loads(state_before.decode('utf-8')) if state_before is not None else {}
    if not isinstance(prior, dict):
        raise ValueError('invalid installation ownership state')
    if state_before is not None and prior.get('home') != str(home):
        raise ValueError('previous installation belongs to a different home')
    previous_hashes = checked_hashes(prior.get('hashes', {}) if state_before is None else prior.get('hashes'), 'ownership')
    adoptions = checked_hashes({} if adopt is None else adopt, 'adoption')
    for rel, sha in adoptions.items():
        if rel not in payload:
            raise ValueError(f'adoption path is not in the exact package manifest: {rel}')
        current = read_if_file(destination(home, rel))
        if current is None or digest(current) != sha:
            raise ValueError(f'adoption preimage mismatch: {rel}')
    plan = []
    for rel, after in payload.items():
        dest = destination(home, rel)
        before = read_if_file(dest)
        if rel == expected_rel and expected_skill_sha:
            if before is None or digest(before) != expected_skill_sha:
                raise ValueError('installed skill changed since baseline inspection')
        # The same ownership rule protects canonical, legacy, and profile files.
        # Exact adoption is the only explicit override; a generic expected SHA is not.
        if rel in adoptions:
            # Bind the actual planned preimage, not an earlier inspection read.
            if before is None or digest(before) != adoptions[rel]:
                raise ValueError(f'adoption preimage mismatch during planning: {rel}')
        else:
            if rel in previous_hashes:
                if before is None or digest(before) != previous_hashes[rel]:
                    raise ValueError(f'externally changed or missing owned destination: {rel}')
            elif before is not None:
                raise ValueError(f'unowned destination collision; exact adoption required: {rel}')
        if before != after:
            plan.append((rel, dest, before, after))
    if not apply:
        return {'status': 'DRY_RUN', 'home': str(home), 'inplace_skill': inplace_skill, 'changes': [r[0] for r in plan]}
    backup = root / 'reports' / f'install-backup-{uuid.uuid4().hex[:12]}'
    backup.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 2, 'home': str(home), 'project': str(root.resolve()),
               'status': 'prepared', 'entries': [], 'adoptions': adoptions,
               'state_before_file': 'install-state.before' if state_before is not None else None,
               'state_before_sha': digest(state_before) if state_before is not None else None}
    if state_before is not None:
        (backup / 'install-state.before').write_bytes(state_before)
    for i, (rel, dest, before, after) in enumerate(plan):
        image = f'{i:03d}.before' if before is not None else None
        if image:
            (backup / image).write_bytes(before)
        receipt['entries'].append({'path': rel, 'before_file': image,
                                  'before_sha': digest(before) if before is not None else None,
                                  'after_sha': digest(after), 'applied': False, 'pending': False,
                                  'write_mode': 'in-place' if inplace_skill and rel.endswith('/SKILL.md') and before is not None else 'atomic'})
    rp = backup / 'receipt.json'
    state_after = json.dumps({'home': str(home), 'receipt': str(rp),
                              'hashes': {r: digest(b) for r,b in payload.items()}}, indent=2).encode('utf-8')
    receipt['state_after_sha'] = digest(state_after)
    def save() -> None:
        atomic_write(rp, json.dumps(receipt, ensure_ascii=False, indent=2).encode('utf-8'))
    save()
    try:
        for entry, (rel, dest, before, after) in zip(receipt['entries'], plan):
            dest = destination(home, rel)  # recheck links at the write boundary
            if read_if_file(dest) != before:
                raise ValueError(f'external destination drift: {rel}')
            # Persist intent BEFORE replacement. Recovery reconciles pending entries
            # against exact before/after images after interruption at either boundary.
            entry['pending'] = True; save()
            if entry['write_mode'] == 'in-place':
                if before is None:
                    raise ValueError('in-place mode cannot create a skill')
                inplace_write(dest, after, before)
            else:
                atomic_write(dest, after)
            entry['applied'] = True; entry['pending'] = False; save()
            if dest.read_bytes() != after:
                raise OSError(f'post-write verification failed: {rel}')
        for rel, after in payload.items():
            if destination(home, rel).read_bytes() != after:
                raise OSError(f'final installed-content mismatch: {rel}')
        if read_if_file(state_path) != state_before:
            raise ValueError('installation ownership state changed concurrently')
        receipt['status'] = 'ownership-pending'; save()
        atomic_write(state_path, state_after)
        if state_path.read_bytes() != state_after:
            raise OSError('installation ownership state verification failed')
        receipt['status'] = 'installed'; save()
        return {'status': 'INSTALLED', 'changed_files': len(plan), 'verified_files': len(payload),
                'receipt': str(rp), 'home': str(home)}
    except BaseException:
        # The last atomic receipt still contains write intent if a new save fails.
        try:
            receipt['status'] = 'failed'; save()
        except Exception:
            pass
        try:
            rollback(root, home, rp)
        except BaseException as recovery_error:
            raise RuntimeError(f'installation failed; recovery incomplete, inspect {rp}: {recovery_error}') from recovery_error
        raise


def rollback(root: Path, home: Path, receipt_path: Path) -> dict:
    root, home = root.resolve(), home.resolve(strict=True)
    rp = receipt_path.resolve(strict=True)
    if not rp.is_relative_to((root / 'reports').resolve()):
        raise ValueError('receipt must be in this project reports directory')
    receipt = json.loads(rp.read_text(encoding='utf-8'))
    if receipt.get('schema') != 2 or receipt.get('home') != str(home) or receipt.get('project') != str(root):
        raise ValueError('receipt identity mismatch')
    state_path = root / '.delivery/install-state.json'
    state_current = read_if_file(state_path)
    current_state_sha = digest(state_current) if state_current is not None else None
    if current_state_sha not in {receipt.get('state_before_sha'), receipt.get('state_after_sha')}:
        raise RuntimeError('newer or externally changed installation ownership state preserved')
    conflicts = []
    for entry in reversed(receipt['entries']):
        if not entry.get('applied') and not entry.get('pending'):
            continue
        dest = destination(home, entry['path'])
        current = read_if_file(dest)
        if (current is None and entry.get('before_sha') is None) or (
                current is not None and digest(current) == entry.get('before_sha')):
            # Already restored, or interrupted after intent but before replacement.
            entry['applied'] = False; entry['pending'] = False
            continue
        if current is None or digest(current) != entry['after_sha']:
            conflicts.append(entry['path']); continue
        image = entry.get('before_file')
        if image:
            if Path(image).name != image or not image.endswith('.before'):
                raise ValueError('invalid preimage reference')
            before = (rp.parent / image).read_bytes()
            if digest(before) != entry['before_sha']:
                raise ValueError('preimage checksum mismatch')
            if entry.get('write_mode') == 'in-place':
                inplace_write(dest, before, current)
            else:
                atomic_write(dest, before)
            if dest.read_bytes() != before:
                raise OSError('restoration verification failed')
        else:
            dest.unlink()  # newly created file with matching task-owned afterimage only
        entry['applied'] = False; entry['pending'] = False
        atomic_write(rp, json.dumps(receipt, ensure_ascii=False, indent=2).encode('utf-8'))
    if not conflicts:
        # Restore the ownership ledger as well as the installed bytes.
        if read_if_file(state_path) != state_current:
            raise RuntimeError('installation ownership state changed during rollback')
        if current_state_sha != receipt.get('state_before_sha'):
            image = receipt.get('state_before_file')
            if image is not None:
                if image != 'install-state.before':
                    raise ValueError('invalid ownership preimage reference')
                before_state = (rp.parent / image).read_bytes()
                if digest(before_state) != receipt.get('state_before_sha'):
                    raise ValueError('ownership preimage checksum mismatch')
                atomic_write(state_path, before_state)
            else:
                state_path.unlink()  # exact state owned by this receipt only
            restored_state = read_if_file(state_path)
            if (digest(restored_state) if restored_state is not None else None) != receipt.get('state_before_sha'):
                raise OSError('ownership restoration verification failed')
    receipt['status'] = 'rollback-conflict' if conflicts else 'restored'
    receipt['conflicts'] = conflicts
    atomic_write(rp, json.dumps(receipt, ensure_ascii=False, indent=2).encode('utf-8'))
    if conflicts:
        raise RuntimeError('external drift preserved during rollback: ' + ', '.join(conflicts))
    return {'status': 'RESTORED', 'receipt': str(rp)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--in-place-skill', action='store_true',
                        help='Explicit ordinary-write mode for the existing SKILL.md only; not crash-atomic')
    parser.add_argument('--expected-skill-sha', help='Additional main-file drift guard; does not grant adoption')
    parser.add_argument('--adopt-file', action='append', default=[], metavar='PATH=SHA256',
                        help='Explicitly adopt/replace one inspected manifest path at its exact preimage')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if args.apply and args.rollback:
        parser.error('--apply and --rollback are mutually exclusive')
    try:
        result = (rollback(ROOT, args.codex_home, args.rollback) if args.rollback else
                  install(ROOT, args.codex_home, apply=args.apply, expected_skill_sha=args.expected_skill_sha, inplace_skill=args.in_place_skill,
                          adopt=parse_adoptions(args.adopt_file)))
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except Exception as exc:
        print(json.dumps({'status': 'FAIL', 'error': str(exc)}, ensure_ascii=False)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
