"""Host-owned Git and filesystem reconciliation for Worktree Writer v1."""

from __future__ import annotations

import hashlib
import json
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
LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"


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
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TZ",
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
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
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
        payload = run_git(
            root,
            ["show", f"HEAD:{target}"],
            max_output_bytes=package.limits["max_total_candidate_bytes"],
        ).stdout
        _decode_candidate(payload, target=target)
    return snapshot


def _parse_status(payload: bytes) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for raw in payload.split(b"\x00"):
        if not raw:
            continue
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WriterEffectError("Git status contains a non-UTF-8 path") from exc
        prefix = text[:1]
        if prefix == "?":
            if not text.startswith("? "):
                raise WriterEffectError(
                    f"malformed untracked status record: {text!r}"
                )
            records.append({"path": text[2:], "action": "create", "xy": "??"})
        elif prefix == "1":
            fields = text.split(" ", 8)
            if len(fields) != 9:
                raise WriterEffectError(
                    f"malformed ordinary status record: {text!r}"
                )
            xy = fields[1]
            path = fields[8]
            if len(xy) != 2:
                raise WriterEffectError(f"malformed XY status for {path!r}")
            if xy[0] != "." or xy[1] != "M":
                raise WriterEffectError(
                    f"forbidden staged/delete/type effect for {path}: XY={xy}"
                )
            records.append({"path": path, "action": "modify", "xy": xy})
        elif prefix in {"2", "u"}:
            raise WriterEffectError(
                f"rename/copy/unmerged effect is forbidden: {text!r}"
            )
        elif prefix == "!":
            continue
        else:
            raise WriterEffectError(f"unknown Git status record: {text!r}")
    return records


def _decode_candidate(payload: bytes, *, target: str) -> str:
    if b"\x00" in payload:
        raise WriterEffectError(
            f"candidate file contains NUL/binary content: {target}"
        )
    if payload.startswith(LFS_PREFIX):
        raise WriterEffectError(f"candidate file is a Git LFS pointer: {target}")
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WriterEffectError(
            f"candidate file is not UTF-8 text: {target}"
        ) from exc


def _file_mode(path: Path) -> str:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(path):
        raise WriterEffectError(
            f"candidate path is a symlink/reparse point: {path}"
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise WriterEffectError(f"candidate path is not a regular file: {path}")
    if os.name != "nt" and metadata.st_mode & 0o111:
        return "100755"
    return "100644"


def _base_blob(
    repository: Path, target: str, *, limit: int
) -> tuple[bytes, str] | None:
    record = run_git(repository, ["ls-tree", "-z", "HEAD", "--", target]).stdout
    if not record:
        return None
    metadata, observed = record.rstrip(b"\x00").split(b"\t", 1)
    mode, kind, _oid = metadata.decode("ascii").split(" ", 2)
    if observed.decode("utf-8") != target or kind != "blob":
        raise WriterEffectError(f"base target is not a regular blob: {target}")
    payload = run_git(
        repository, ["show", f"HEAD:{target}"], max_output_bytes=limit
    ).stdout
    return payload, mode


def _diff_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.splitlines(keepends=True)


def _one_patch(
    target: str, base: str | None, current: str, *, mode: str
) -> bytes:
    import difflib

    header = [f"diff --git a/{target} b/{target}\n"]
    if base is None:
        header.extend(
            [f"new file mode {mode}\n", "--- /dev/null\n", f"+++ b/{target}\n"]
        )
        old_lines: list[str] = []
    else:
        header.extend([f"--- a/{target}\n", f"+++ b/{target}\n"])
        old_lines = _diff_lines(base)
    body = list(
        difflib.unified_diff(
            old_lines,
            _diff_lines(current),
            fromfile="",
            tofile="",
            n=3,
            lineterm="\n",
        )
    )
    if (
        len(body) >= 2
        and body[0].startswith("--- ")
        and body[1].startswith("+++ ")
    ):
        body = body[2:]
    return "".join(header + body).encode("utf-8")


def reconcile_candidate(
    worktree: str | Path, package: WriterPackage
) -> dict[str, Any]:
    root = repository_root(worktree)
    head = run_git(root, ["rev-parse", "HEAD"]).stdout_text().strip()
    tree = run_git(root, ["rev-parse", "HEAD^{tree}"]).stdout_text().strip()
    if head != package.expected_head_sha or tree != package.expected_tree_sha:
        raise WriterEffectError("detached worktree HEAD/tree changed")
    staged = run_git(root, ["diff", "--cached", "--quiet"], check=False)
    if staged.returncode not in {0, 1}:
        raise WriterEffectError("cannot inspect isolated worktree index")
    if staged.returncode == 1:
        raise WriterEffectError("writer modified the Git index")
    summary = run_git(
        root, ["diff", "--summary", "--no-renames"]
    ).stdout_text()
    if summary.strip():
        raise WriterEffectError(
            f"mode/delete/rename summary is forbidden: {summary.strip()}"
        )
    status_bytes = run_git(
        root,
        [
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--no-renames",
        ],
    ).stdout
    changes = _parse_status(status_bytes)
    if not changes:
        raise WriterEffectError("writer produced no candidate change")
    if len(changes) > package.limits["max_changed_files"]:
        raise WriterEffectError(
            f"candidate changed {len(changes)} files; "
            f"limit={package.limits['max_changed_files']}"
        )
    owned = {target.casefold(): target for target in package.owned_targets}
    observed_folded: set[str] = set()
    files: list[dict[str, Any]] = []
    patch_parts: list[bytes] = []
    total_bytes = 0
    for change in sorted(changes, key=lambda item: item["path"].casefold()):
        target = change["path"].replace("\\", "/")
        expected = owned.get(target.casefold())
        if expected is None or expected != target:
            raise WriterEffectError(
                f"changed path is not an exact owned target: {target}"
            )
        if target.casefold() in observed_folded:
            raise WriterEffectError(
                f"duplicate changed path under Windows semantics: {target}"
            )
        observed_folded.add(target.casefold())
        action = change["action"]
        if action not in package.allowed_actions:
            raise WriterEffectError(
                f"action {action} is not authorized for {target}"
            )
        candidate = (root / Path(*target.split("/"))).resolve(strict=True)
        if not candidate.is_relative_to(root):
            raise WriterEffectError(f"candidate path escapes worktree: {target}")
        assert_no_link_components(
            candidate, stop=root, label=f"candidate {target}"
        )
        mode = _file_mode(candidate)
        payload = candidate.read_bytes()
        if (
            action == "create"
            and len(payload) > package.limits["max_created_file_bytes"]
        ):
            raise WriterEffectError(f"created file exceeds limit: {target}")
        total_bytes += len(payload)
        if total_bytes > package.limits["max_total_candidate_bytes"]:
            raise WriterEffectError(
                "candidate files exceed max_total_candidate_bytes"
            )
        current_text = _decode_candidate(payload, target=target)
        base_record = _base_blob(
            root,
            target,
            limit=package.limits["max_total_candidate_bytes"],
        )
        if action == "create" and base_record is not None:
            raise WriterEffectError(
                f"create action conflicts with existing base file: {target}"
            )
        if action == "modify" and base_record is None:
            raise WriterEffectError(f"modify action has no base file: {target}")
        base_text: str | None = None
        base_sha: str | None = None
        if base_record is not None:
            base_payload, base_mode = base_record
            if base_mode != mode:
                raise WriterEffectError(
                    f"file mode changed for {target}: {base_mode} -> {mode}"
                )
            base_text = _decode_candidate(base_payload, target=target)
            base_sha = sha256_bytes(base_payload)
            if base_payload == payload:
                raise WriterEffectError(
                    f"modified file has no content change: {target}"
                )
        patch_parts.append(
            _one_patch(target, base_text, current_text, mode=mode)
        )
        files.append(
            {
                "path": target,
                "action": action,
                "mode": mode,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "base_sha256": base_sha,
                "mtime_ns": candidate.stat().st_mtime_ns,
            }
        )
    patch = b"".join(patch_parts)
    if len(patch) > package.limits["max_patch_bytes"]:
        raise WriterEffectError(
            f"candidate patch exceeds {package.limits['max_patch_bytes']} bytes"
        )
    result = {
        "manifest_version": 1,
        "package_digest": package.digest,
        "base_head": package.expected_head_sha,
        "base_tree": package.expected_tree_sha,
        "worktree_head": head,
        "worktree_tree": tree,
        "files": files,
        "changed_paths": [item["path"] for item in files],
        "patch_bytes": len(patch),
        "patch_sha256": sha256_bytes(patch),
        "total_candidate_bytes": total_bytes,
        "unauthorized_effects": [],
    }
    result["manifest_digest"] = canonical_digest(result)
    return {"manifest": result, "patch": patch}


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
