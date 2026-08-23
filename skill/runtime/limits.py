"""Resource limits for the explicit Dynamic Workflow runtime.

The defaults are intentionally conservative and every configurable value has a
non-negotiable hard ceiling.  A workflow may request a smaller or larger value
within that ceiling, but it cannot remove the limit.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

MIB = 1024 * 1024

DEFAULT_MAX_RESULT_BYTES = 2 * MIB
DEFAULT_MAX_LOG_BYTES = 8 * MIB
DEFAULT_MAX_RUN_ARTIFACT_BYTES = 64 * MIB
DEFAULT_MAX_UPSTREAM_INLINE_BYTES = 8 * 1024
DEFAULT_MAX_EVENT_BYTES = 256 * 1024

HARD_MAX_RESULT_BYTES = 64 * MIB
HARD_MAX_LOG_BYTES = 256 * MIB
HARD_MAX_RUN_ARTIFACT_BYTES = 1024 * MIB
HARD_MAX_UPSTREAM_INLINE_BYTES = 1 * MIB
HARD_MAX_EVENT_BYTES = 1 * MIB

ENV_KEYS = {
    "max_result_bytes": "DYNWF_MAX_RESULT_BYTES",
    "max_log_bytes": "DYNWF_MAX_LOG_BYTES",
    "max_run_artifact_bytes": "DYNWF_MAX_RUN_ARTIFACT_BYTES",
    "max_upstream_inline_bytes": "DYNWF_MAX_UPSTREAM_INLINE_BYTES",
    "max_event_bytes": "DYNWF_MAX_EVENT_BYTES",
}

HARD_CEILINGS = {
    "max_result_bytes": HARD_MAX_RESULT_BYTES,
    "max_log_bytes": HARD_MAX_LOG_BYTES,
    "max_run_artifact_bytes": HARD_MAX_RUN_ARTIFACT_BYTES,
    "max_upstream_inline_bytes": HARD_MAX_UPSTREAM_INLINE_BYTES,
    "max_event_bytes": HARD_MAX_EVENT_BYTES,
}


class ArtifactLimitError(RuntimeError):
    """A generated file or run directory exceeded a configured hard limit."""


@dataclass(frozen=True)
class RuntimeLimits:
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES
    max_log_bytes: int = DEFAULT_MAX_LOG_BYTES
    max_run_artifact_bytes: int = DEFAULT_MAX_RUN_ARTIFACT_BYTES
    max_upstream_inline_bytes: int = DEFAULT_MAX_UPSTREAM_INLINE_BYTES
    max_event_bytes: int = DEFAULT_MAX_EVENT_BYTES

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> "RuntimeLimits":
        """Resolve limits with precedence: explicit spec, environment, defaults."""

        values = values or {}
        env = os.environ if env is None else env
        unknown = sorted(set(values) - set(ENV_KEYS))
        if unknown:
            raise ValueError(f"unknown runtime limit keys: {unknown}")

        defaults = asdict(cls())
        resolved: dict[str, int] = {}
        for key, default in defaults.items():
            raw: Any
            if key in values:
                raw = values[key]
            elif ENV_KEYS[key] in env:
                raw = env[ENV_KEYS[key]]
            else:
                raw = default
            if isinstance(raw, bool):
                raise ValueError(f"{key} must be an integer")
            try:
                number = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be an integer") from exc
            if number <= 0:
                raise ValueError(f"{key} must be greater than zero")
            ceiling = HARD_CEILINGS[key]
            if number > ceiling:
                raise ValueError(f"{key} exceeds hard ceiling {ceiling}")
            resolved[key] = number

        if resolved["max_upstream_inline_bytes"] > resolved["max_result_bytes"]:
            raise ValueError(
                "max_upstream_inline_bytes cannot exceed max_result_bytes"
            )
        return cls(**resolved)

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def directory_size(root: Path, *, ceiling: int | None = None) -> int:
    """Return bytes below root without following symlinks.

    When ``ceiling`` is provided the scan stops as soon as the total exceeds it.
    """

    if not root.exists():
        return 0
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (FileNotFoundError, NotADirectoryError):
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    total += entry.lstat().st_size
                elif entry.is_dir():
                    stack.append(entry)
                else:
                    total += entry.stat().st_size
            except FileNotFoundError:
                continue
            if ceiling is not None and total > ceiling:
                return total
    return total


def enforce_file_limit(path: Path, limit: int, label: str) -> int:
    size = file_size(path)
    if size > limit:
        raise ArtifactLimitError(f"{label} exceeds {limit} bytes: {size}")
    return size


def enforce_run_limit(root: Path, limit: int) -> int:
    size = directory_size(root, ceiling=limit)
    if size > limit:
        raise ArtifactLimitError(
            f"run artifacts exceed {limit} bytes: at least {size}"
        )
    return size


def enforce_projected_write(
    root: Path,
    target: Path,
    new_bytes: int,
    limit: int,
    label: str,
    *,
    temporary_copy: bool = True,
) -> int:
    """Fail before a write whose peak retained bytes would exceed the run limit.

    Atomic replacement normally creates a temporary copy beside the old target,
    so the default check includes the full new payload in addition to the
    current directory size. Append-only writes set ``temporary_copy=False``.
    """

    current_total = directory_size(root)
    if temporary_copy:
        projected = current_total + new_bytes
    else:
        projected = current_total + new_bytes
    if projected > limit:
        raise ArtifactLimitError(
            f"{label} would exceed run limit {limit} bytes: projected={projected}"
        )
    return projected


def truncate_file(path: Path, limit: int) -> int:
    """Retain at most ``limit`` bytes from an oversized generated file."""

    size = file_size(path)
    if size <= limit:
        return size
    with path.open("r+b") as handle:
        handle.truncate(limit)
    return limit


def trim_file_to_run_limit(root: Path, preferred: Path, limit: int) -> int:
    """Trim one active generated file enough to restore the total run limit."""

    total = directory_size(root)
    if total <= limit:
        return total
    excess = total - limit
    size = file_size(preferred)
    if size:
        with preferred.open("r+b") as handle:
            handle.truncate(max(0, size - excess))
    total = directory_size(root)
    if total > limit:
        raise ArtifactLimitError(
            f"run artifacts remain above {limit} bytes after bounded cleanup: {total}"
        )
    return total
