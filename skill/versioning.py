"""Strict semantic version handling for the personal Dynamic Workflow install."""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION_FILENAME = "VERSION"
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-rc\.(0|[1-9][0-9]*))?$"
)
BUMP_TYPES = ("prerelease", "release", "patch", "minor", "major")


class VersionError(ValueError):
    """The version file or requested bump is invalid."""


@dataclass(frozen=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    rc: int | None = None

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return base if self.rc is None else f"{base}-rc.{self.rc}"

    @property
    def prerelease(self) -> bool:
        return self.rc is not None


def parse_version(value: str, *, label: str = "version") -> SemanticVersion:
    if not isinstance(value, str):
        raise VersionError(f"{label} must be a string")
    match = SEMVER_RE.fullmatch(value)
    if match is None:
        raise VersionError(
            f"{label} must use MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-rc.N"
        )
    major, minor, patch, rc = match.groups()
    return SemanticVersion(
        major=int(major),
        minor=int(minor),
        patch=int(patch),
        rc=None if rc is None else int(rc),
    )


def version_path(source_root: Path | str) -> Path:
    return Path(source_root).expanduser().absolute() / "skill" / VERSION_FILENAME


def read_skill_version(source_root: Path | str) -> str:
    path = version_path(source_root)
    if path.is_symlink() or not path.is_file():
        raise VersionError(f"version file is missing or unsafe: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VersionError(f"cannot read version file {path}: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise VersionError("version file must be UTF-8 without BOM")
    if b"\x00" in raw:
        raise VersionError("version file cannot contain NUL")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VersionError("version file must be strict UTF-8") from exc

    if text.endswith("\r\n"):
        value = text[:-2]
    elif text.endswith("\n"):
        value = text[:-1]
    else:
        value = text
    if not value or "\r" in value or "\n" in value:
        raise VersionError("version file must contain exactly one version line")

    parse_version(value, label="skill version")
    return value


def next_version(
    current: SemanticVersion,
    bump_type: str | None = None,
) -> tuple[str, SemanticVersion]:
    selected = bump_type or ("prerelease" if current.prerelease else "patch")
    if selected not in BUMP_TYPES:
        raise VersionError(f"unsupported bump type: {selected!r}")
    if selected == "prerelease":
        if current.rc is not None:
            return selected, SemanticVersion(
                current.major, current.minor, current.patch, current.rc + 1
            )
        return selected, SemanticVersion(
            current.major, current.minor, current.patch + 1, 1
        )
    if selected == "release":
        if current.rc is None:
            raise VersionError("--release requires a current prerelease version")
        return selected, SemanticVersion(current.major, current.minor, current.patch)
    if selected == "patch":
        return selected, SemanticVersion(current.major, current.minor, current.patch + 1)
    if selected == "minor":
        return selected, SemanticVersion(current.major, current.minor + 1, 0)
    return selected, SemanticVersion(current.major + 1, 0, 0)


def _atomic_write_version(path: Path, value: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise VersionError(f"version file is missing or unsafe: {path}")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        os.set_inheritable(descriptor, False)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write((value + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise VersionError(f"cannot update version file {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def bump_skill_version(
    source_root: Path | str,
    *,
    bump_type: str | None = None,
) -> dict[str, Any]:
    path = version_path(source_root)
    current_text = read_skill_version(source_root)
    selected, updated = next_version(
        parse_version(current_text, label="skill version"), bump_type
    )
    new_text = str(updated)
    _atomic_write_version(path, new_text)
    if read_skill_version(source_root) != new_text:
        raise VersionError("version file verification failed after write")
    return {
        "operation": "version-bump",
        "bump_type": selected,
        "previous_version": current_text,
        "version": new_text,
        "version_file": str(path),
        "model_calls": 0,
        "writes": [str(path)],
    }
