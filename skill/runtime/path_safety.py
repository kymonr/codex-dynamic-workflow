"""Fail-closed checks for runtime-owned paths below one run directory."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class UnsafeRunPathError(ValueError):
    """A runtime path is outside its run or traverses a reparse point."""


def lexists(path: Path) -> bool:
    """Return whether a path entry exists without following reparse targets."""

    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise UnsafeRunPathError(f"cannot inspect runtime path {path}: {exc}") from exc


def is_reparse(path: Path) -> bool:
    """Return whether *path* is a symlink, junction, or reparse point."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(flag and attributes & flag)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise UnsafeRunPathError(f"cannot inspect runtime path {path}: {exc}") from exc


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_existing_components_are_not_reparse(
    path: Path,
    *,
    label: str,
) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if not lexists(current):
            break
        if is_reparse(current):
            raise UnsafeRunPathError(
                f"{label} traverses a symlink, junction, or reparse point: "
                f"{current}"
            )


def canonical_runtime_path(path: Path, *, label: str) -> Path:
    """Return one alias-normalized identity without trusting reparse paths.

    Existing components are checked before and after ``resolve(strict=False)``.
    On Windows this expands 8.3 aliases such as ``RUNNER~1`` to the same long
    identity used by ``Path.resolve()``, while the pre-check prevents
    canonicalization from silently following an existing reparse component.
    """

    lexical = _absolute(path)
    _assert_existing_components_are_not_reparse(lexical, label=label)
    try:
        canonical = lexical.resolve(strict=False)
    except OSError as exc:
        raise UnsafeRunPathError(
            f"cannot canonicalize {label} {lexical}: {exc}"
        ) from exc
    _assert_existing_components_are_not_reparse(canonical, label=label)
    return canonical


def assert_safe_descendant(
    run_dir: Path,
    candidate: Path,
    *,
    label: str,
) -> None:
    """Reject existing reparse components without resolving through them."""

    root = canonical_runtime_path(
        run_dir, label="run directory"
    )
    path = canonical_runtime_path(candidate, label=label)
    if path != root and not path.is_relative_to(root):
        raise UnsafeRunPathError(f"{label} escapes run directory: {path}")

    current = Path(root.anchor)
    for part in root.parts[1:]:
        current = current / part
        if not lexists(current):
            break
        if is_reparse(current):
            raise UnsafeRunPathError(
                "run directory traverses a symlink, junction, or reparse "
                f"point: {current}"
            )

    if lexists(root):
        if not root.is_dir() or is_reparse(root):
            raise UnsafeRunPathError(
                f"run directory is not a safe directory: {root}"
            )

    current = root
    relative = path.relative_to(root)
    for part in relative.parts:
        current = current / part
        if not lexists(current):
            break
        if is_reparse(current):
            raise UnsafeRunPathError(
                f"{label} traverses a symlink, junction, or reparse point: {current}"
            )


def assert_safe_run_tree(run_dir: Path) -> None:
    """Reject every existing reparse descendant of *run_dir*."""

    root = canonical_runtime_path(
        run_dir, label="run directory"
    )
    assert_safe_descendant(root, root, label="run directory")
    if not root.is_dir():
        raise UnsafeRunPathError(f"run directory does not exist: {root}")

    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if is_reparse(path):
                        raise UnsafeRunPathError(
                            "run directory contains a symlink, junction, or "
                            f"reparse point: {path}"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
        except UnsafeRunPathError:
            raise
        except OSError as exc:
            raise UnsafeRunPathError(
                f"cannot inspect run directory tree {directory}: {exc}"
            ) from exc
