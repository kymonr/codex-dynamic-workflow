"""Read-only Git candidate capture for Agent Fleet v1."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Mapping

try:
    from skill.fleet_contract import FleetPackage, canonical_digest
except ModuleNotFoundError as exc:
    if exc.name != "skill":
        raise
    from fleet_contract import FleetPackage, canonical_digest

MAX_GIT_OUTPUT_BYTES = 16 * 1024 * 1024


class FleetCandidateError(RuntimeError):
    """The candidate repository is stale, ambiguous, binary, or out of scope."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _assert_no_link_components(
    path: Path, *, stop: Path | None = None, label: str = "path"
) -> None:
    lexical = path.expanduser().absolute()
    boundary = stop.expanduser().absolute() if stop is not None else None
    components: list[Path] = []
    current = lexical
    while True:
        components.append(current)
        if boundary is not None and current == boundary:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    for component in reversed(components):
        if component.exists() or component.is_symlink():
            if component.is_symlink() or _is_reparse(component):
                raise FleetCandidateError(
                    f"{label} contains symlink/reparse component: {component}"
                )


def _revision_basis(value: Mapping[str, Any]) -> dict[str, Any]:
    basis = dict(value)
    basis.pop("repository_root", None)
    return basis


def _git(
    repository: Path,
    args: list[str],
    *,
    maximum: int = MAX_GIT_OUTPUT_BYTES,
) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FleetCandidateError(f"git command failed to complete: {args}: {exc}") from exc
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise FleetCandidateError(f"git command failed ({completed.returncode}): {args}: {error}")
    if len(completed.stdout) > maximum:
        raise FleetCandidateError(f"git output exceeds {maximum} bytes: {args}")
    return completed.stdout


def repository_root(value: str | Path) -> Path:
    lexical = Path(value).expanduser().absolute()
    _assert_no_link_components(lexical, label="repository path")
    try:
        path = lexical.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FleetCandidateError(f"cannot resolve repository path: {exc}") from exc
    _assert_no_link_components(path, label="repository path")
    raw = _git(path, ["rev-parse", "--show-toplevel"], maximum=16 * 1024)
    try:
        root_lexical = Path(raw.decode("utf-8", errors="strict").strip())
        _assert_no_link_components(root_lexical, label="Git repository root")
        root = root_lexical.resolve(strict=True)
    except (UnicodeDecodeError, OSError, RuntimeError) as exc:
        raise FleetCandidateError(f"cannot resolve repository root: {exc}") from exc
    _assert_no_link_components(root, label="Git repository root")
    if root != path:
        raise FleetCandidateError(f"repository path must be the Git root: {root}")
    return root


def _origin_full_name(repository: Path) -> str:
    url = _git(repository, ["remote", "get-url", "origin"], maximum=16 * 1024)
    try:
        text = url.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise FleetCandidateError("origin URL is not UTF-8") from exc
    patterns = (
        r"^https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$",
        r"^ssh://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$",
        r"^[^@]+@[^:]+:([^/]+)/([^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    raise FleetCandidateError(f"cannot derive owner/repository from origin URL: {text!r}")


def _decode_path(raw: bytes) -> str:
    try:
        path = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FleetCandidateError("Git status contains a non-UTF-8 path") from exc
    if not path or "\x00" in path or "\\" in path:
        raise FleetCandidateError(f"Git status contains an unsafe path: {path!r}")
    return path.replace(os.sep, "/") if os.sep != "/" else path


def _status_entries(raw: bytes) -> list[dict[str, Any]]:
    tokens = raw.split(b"\x00")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    entries: list[dict[str, Any]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if len(token) < 4 or token[2:3] != b" ":
            raise FleetCandidateError("Git porcelain status has an invalid entry")
        try:
            status = token[:2].decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise FleetCandidateError("Git status code is invalid") from exc
        path = _decode_path(token[3:])
        paths = [path]
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index >= len(tokens):
                raise FleetCandidateError("Git rename/copy entry lacks its source path")
            paths.append(_decode_path(tokens[index]))
            index += 1
        entries.append({"status": status, "paths": paths})
    return entries


def _untracked_paths(entries: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for entry in entries:
        if entry["status"] == "??":
            result.extend(entry["paths"])
    return sorted(set(result), key=str.casefold)


def capture_candidate(repository: str | Path, package: FleetPackage) -> dict[str, Any]:
    root = repository_root(repository)
    head = _git(root, ["rev-parse", "HEAD"], maximum=256).decode("ascii").strip()
    tree = _git(root, ["rev-parse", "HEAD^{tree}"], maximum=256).decode("ascii").strip()
    if head != package.candidate["expected_head_sha"]:
        raise FleetCandidateError(
            f"candidate HEAD mismatch: expected={package.candidate['expected_head_sha']} actual={head}"
        )
    origin = _origin_full_name(root)
    if origin.casefold() != package.candidate["repository_full_name"].casefold():
        raise FleetCandidateError(
            f"candidate origin mismatch: expected={package.candidate['repository_full_name']} actual={origin}"
        )

    status_raw = _git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    entries = _status_entries(status_raw)
    observed_paths = sorted(
        {path for entry in entries for path in entry["paths"]},
        key=str.casefold,
    )
    for relative in observed_paths:
        _assert_no_link_components(
            root / Path(*relative.split("/")),
            stop=root,
            label=f"candidate path {relative}",
        )
    expected_paths = list(package.candidate["changed_files"])
    if {item.casefold() for item in observed_paths} != {
        item.casefold() for item in expected_paths
    }:
        raise FleetCandidateError(
            f"candidate changed-file set mismatch: expected={expected_paths} actual={observed_paths}"
        )

    patch = _git(
        root,
        ["diff", "--no-ext-diff", "--no-color", "--full-index", "--binary", "HEAD", "--"],
        maximum=package.limits["max_patch_bytes"],
    )
    if b"\x00" in patch or b"GIT binary patch" in patch or b"Binary files " in patch:
        raise FleetCandidateError("Agent Fleet v1 candidate patch must be UTF-8 text")
    try:
        patch.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise FleetCandidateError("candidate patch is not UTF-8") from exc

    untracked: list[dict[str, Any]] = []
    total_untracked = 0
    for relative in _untracked_paths(entries):
        lexical = root / Path(*relative.split("/"))
        _assert_no_link_components(
            lexical, stop=root, label=f"untracked candidate {relative}"
        )
        try:
            path = lexical.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise FleetCandidateError(
                f"cannot resolve untracked candidate {relative}: {exc}"
            ) from exc
        _assert_no_link_components(
            path, stop=root, label=f"untracked candidate {relative}"
        )
        if not path.is_relative_to(root) or not path.is_file():
            raise FleetCandidateError(
                f"untracked candidate is not a regular contained file: {relative}"
            )
        payload = path.read_bytes()
        if len(payload) > package.limits["max_untracked_file_bytes"]:
            raise FleetCandidateError(
                f"untracked candidate exceeds file limit: {relative}"
            )
        if b"\x00" in payload:
            raise FleetCandidateError(f"untracked candidate contains NUL: {relative}")
        try:
            payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise FleetCandidateError(
                f"untracked candidate is not UTF-8: {relative}"
            ) from exc
        total_untracked += len(payload)
        untracked.append(
            {
                "path": relative,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "content": payload.decode("utf-8"),
            }
        )
    total_candidate = len(patch) + total_untracked
    if total_candidate > package.limits["max_candidate_bytes"]:
        raise FleetCandidateError(
            f"candidate material exceeds {package.limits['max_candidate_bytes']} bytes"
        )

    material = {
        "candidate_package_version": 1,
        "fleet_package_digest": package.digest,
        "repository_full_name": package.candidate["repository_full_name"],
        "repository_root": str(root),
        "head": head,
        "tree": tree,
        "changed_files": observed_paths,
        "status": {
            "bytes": len(status_raw),
            "sha256": sha256_bytes(status_raw),
            "entries": entries,
        },
        "patch": {
            "bytes": len(patch),
            "sha256": sha256_bytes(patch),
            "content": patch.decode("utf-8"),
        },
        "untracked_files": untracked,
        "total_candidate_bytes": total_candidate,
    }
    basis_digest = canonical_digest(_revision_basis(material))
    return {
        **material,
        "candidate_revision": f"sha256:{basis_digest}",
        "revision_basis_digest": basis_digest,
    }


def validate_candidate_package(value: Mapping[str, Any]) -> None:
    if value.get("candidate_package_version") != 1:
        raise FleetCandidateError("candidate package version is invalid")
    basis = dict(value)
    revision = basis.pop("candidate_revision", None)
    recorded = basis.pop("revision_basis_digest", None)
    computed = canonical_digest(_revision_basis(basis))
    if recorded != computed or revision != f"sha256:{computed}":
        raise FleetCandidateError("candidate revision binding is invalid")


def assert_candidate_stable(
    repository: str | Path,
    package: FleetPackage,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    current = capture_candidate(repository, package)
    if current["candidate_revision"] != expected["candidate_revision"]:
        raise FleetCandidateError(
            "candidate changed during Agent Fleet execution: "
            f"expected={expected['candidate_revision']} actual={current['candidate_revision']}"
        )
    return current
