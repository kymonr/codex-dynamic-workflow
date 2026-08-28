"""Git identity, containment and metadata snapshots for Worktree Writer v2."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from skill.writer_contract import WriterPackage, canonical_digest
except ModuleNotFoundError:
    from writer_contract import WriterPackage, canonical_digest

MAX_GIT_OUTPUT_BYTES = 8 * 1024 * 1024


class WriterEffectError(RuntimeError):
    """Repository identity or observed effects violate writer authority."""


@dataclass(frozen=True)
class GitResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes

    def stdout_text(self) -> str:
        try:
            return self.stdout.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WriterEffectError(
                f"Git output is not UTF-8 for {' '.join(self.argv)}"
            ) from exc


def _child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    allowed = (
        "SystemRoot", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
        "TMPDIR", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "LANG",
        "LC_ALL", "TZ",
    )
    env = {
        key: value
        for key in allowed
        if (value := os.environ.get(key)) is not None
    }
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
            "NO_COLOR": "1",
            "LC_ALL": "C.UTF-8" if os.name != "nt" else "C",
        }
    )
    if extra:
        env.update(extra)
    return env


def run_git(
    repository: str | Path,
    args: Sequence[str],
    *,
    check: bool = True,
    timeout: int = 60,
    max_output_bytes: int = MAX_GIT_OUTPUT_BYTES,
) -> GitResult:
    root = Path(repository)
    argv = ("git", "-c", "core.quotePath=false", "-C", str(root), *args)
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=_child_env(),
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WriterEffectError(f"Git command failed to launch: {argv}: {exc}") from exc
    if (
        len(completed.stdout) > max_output_bytes
        or len(completed.stderr) > max_output_bytes
    ):
        raise WriterEffectError(
            f"Git command output exceeds {max_output_bytes} bytes: {argv}"
        )
    result = GitResult(argv, completed.returncode, completed.stdout, completed.stderr)
    if check and completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise WriterEffectError(
            f"Git command exited {completed.returncode}: {' '.join(argv)}: {detail}"
        )
    return result


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def assert_no_link_components(
    path: Path, *, stop: Path | None = None, label: str = "path"
) -> None:
    """Reject symlink/reparse components on an existing path prefix."""

    lexical = path.expanduser().absolute()
    stop_resolved = stop.expanduser().absolute() if stop is not None else None
    parts: list[Path] = []
    current = lexical
    while True:
        parts.append(current)
        if stop_resolved is not None and current == stop_resolved:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    for component in reversed(parts):
        if component.exists() or component.is_symlink():
            if component.is_symlink() or _is_reparse(component):
                raise WriterEffectError(
                    f"{label} contains symlink/reparse component: {component}"
                )


def canonical_directory(
    path: str | Path, *, label: str, must_exist: bool = True
) -> Path:
    lexical = Path(path).expanduser()
    assert_no_link_components(lexical, label=label)
    try:
        resolved = lexical.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise WriterEffectError(f"cannot resolve {label}: {exc}") from exc
    assert_no_link_components(resolved, label=label)
    if must_exist and not resolved.is_dir():
        raise WriterEffectError(f"{label} must be a directory: {resolved}")
    return resolved


def paths_overlap(first: Path, second: Path) -> bool:
    try:
        return (
            first == second
            or first.is_relative_to(second)
            or second.is_relative_to(first)
        )
    except ValueError:
        return False


def repository_root(repository: str | Path) -> Path:
    candidate = canonical_directory(repository, label="canonical repository")
    root_text = run_git(candidate, ["rev-parse", "--show-toplevel"]).stdout_text().strip()
    root = canonical_directory(root_text, label="repository root")
    if root != candidate:
        raise WriterEffectError(
            "repository path must be its top-level worktree: "
            f"expected={candidate} actual={root}"
        )
    return root


def _git_path(repository: Path, name: str) -> Path:
    text = run_git(
        repository,
        ["rev-parse", "--path-format=absolute", "--git-path", name],
    ).stdout_text().strip()
    return Path(text).resolve(strict=False)


def _optional_file_record(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or _is_reparse(path) or not path.is_file():
        raise WriterEffectError(f"Git metadata path is not a regular file: {path}")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _directory_manifest(
    root: Path, *, limit_entries: int = 100_000
) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    if root.is_symlink() or _is_reparse(root) or not root.is_dir():
        raise WriterEffectError(f"manifest root is not a regular directory: {root}")
    records: list[dict[str, Any]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir(), key=lambda item: item.name.casefold()):
            if len(records) >= limit_entries:
                raise WriterEffectError(
                    f"manifest exceeds {limit_entries} entries: {root}"
                )
            relative = entry.relative_to(root).as_posix()
            if entry.is_symlink() or _is_reparse(entry):
                records.append(
                    {
                        "path": relative,
                        "type": "link",
                        "lstat_bytes": entry.lstat().st_size,
                    }
                )
            elif entry.is_dir():
                records.append({"path": relative, "type": "directory"})
                stack.append(entry)
            elif entry.is_file():
                records.append(
                    {
                        "path": relative,
                        "type": "file",
                        "bytes": entry.stat().st_size,
                        "sha256": sha256_file(entry),
                    }
                )
            else:
                records.append({"path": relative, "type": "other"})
    records.sort(key=lambda item: item["path"].casefold())
    return records


def repository_snapshot(
    repository: str | Path, *, include_worktree_registry: bool = True
) -> dict[str, Any]:
    root = repository_root(repository)
    head = run_git(root, ["rev-parse", "HEAD"]).stdout_text().strip()
    tree = run_git(root, ["rev-parse", "HEAD^{tree}"]).stdout_text().strip()
    status = run_git(
        root,
        [
            "status", "--porcelain=v2", "-z", "--untracked-files=all",
            "--no-renames",
        ],
    ).stdout
    refs = run_git(
        root, ["for-each-ref", "--format=%(refname)%00%(objectname)%00"]
    ).stdout
    config = run_git(root, ["config", "--local", "--null", "--list"]).stdout
    git_common_text = run_git(
        root, ["rev-parse", "--path-format=absolute", "--git-common-dir"]
    ).stdout_text().strip()
    git_common = Path(git_common_text).resolve(strict=True)
    assert_no_link_components(git_common, label="Git common directory")
    snapshot: dict[str, Any] = {
        "version": 1,
        "root": str(root),
        "head": head,
        "tree": tree,
        "status_sha256": sha256_bytes(status),
        "status_bytes": len(status),
        "refs_sha256": sha256_bytes(refs),
        "config_sha256": sha256_bytes(config),
        "index": _optional_file_record(_git_path(root, "index")),
        "head_file": _optional_file_record(_git_path(root, "HEAD")),
        "packed_refs": _optional_file_record(git_common / "packed-refs"),
        "objects_manifest_digest": canonical_digest(
            _directory_manifest(git_common / "objects")
        ),
    }
    if include_worktree_registry:
        registry = _directory_manifest(git_common / "worktrees")
        snapshot["worktree_registry"] = registry
        snapshot["worktree_registry_digest"] = canonical_digest(registry)
    snapshot["snapshot_digest"] = canonical_digest(snapshot)
    return snapshot


def remote_repository_identity(repository: str | Path) -> str:
    result = run_git(repository, ["remote", "get-url", "origin"]).stdout_text().strip()
    text = result.rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    if text.startswith("git@github.com:"):
        return text.split(":", 1)[1]
    marker = "github.com/"
    if marker in text:
        return text.split(marker, 1)[1]
    raise WriterEffectError(
        f"origin URL is not a supported GitHub identity: {result}"
    )


def validate_base(repository: str | Path, package: WriterPackage) -> dict[str, Any]:
    """Validate repository identity using metadata only.

    The zero-model writer-plan contract intentionally does not open owned-file
    content. UTF-8, NUL, LFS, binary and byte-limit checks happen after the
    isolated writer in candidate reconciliation.
    """

    root = repository_root(repository)
    snapshot = repository_snapshot(root)
    if snapshot["head"] != package.expected_head_sha:
        raise WriterEffectError(
            f"HEAD mismatch: expected={package.expected_head_sha} "
            f"actual={snapshot['head']}"
        )
    if snapshot["tree"] != package.expected_tree_sha:
        raise WriterEffectError(
            f"tree mismatch: expected={package.expected_tree_sha} "
            f"actual={snapshot['tree']}"
        )
    if snapshot["status_bytes"] != 0:
        raise WriterEffectError(
            "canonical repository must be clean, including untracked files"
        )
    observed_identity = remote_repository_identity(root)
    if observed_identity.casefold() != package.repository_full_name.casefold():
        raise WriterEffectError(
            "repository identity mismatch: "
            f"expected={package.repository_full_name} actual={observed_identity}"
        )
    for target in package.owned_targets:
        result = run_git(root, ["ls-tree", "-z", "HEAD", "--", target]).stdout
        if not result:
            continue
        record = result.rstrip(b"\x00")
        try:
            metadata, observed_path = record.split(b"\t", 1)
            mode, kind, _object_id = metadata.decode("ascii").split(" ", 2)
            path_text = observed_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise WriterEffectError(
                f"cannot parse base tree entry for {target}"
            ) from exc
        if (
            path_text != target
            or kind != "blob"
            or mode not in {"100644", "100755"}
        ):
            raise WriterEffectError(
                f"owned target has unsupported base type/mode: "
                f"{target}: {mode} {kind}"
            )
    return snapshot


def compare_snapshots(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    allow_worktree_registry_change: bool = False,
) -> list[str]:
    ignored = {"snapshot_digest"}
    if allow_worktree_registry_change:
        ignored.update({"worktree_registry", "worktree_registry_digest"})
    return [
        key
        for key in sorted((set(before) | set(after)) - ignored)
        if before.get(key) != after.get(key)
    ]
