"""Candidate effect reconciliation and deterministic patch capture."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

try:
    from skill.writer_contract import WriterPackage, canonical_digest
    from skill.writer_git_state import (
        WriterEffectError,
        _is_reparse,
        assert_no_link_components,
        repository_root,
        run_git,
        sha256_bytes,
    )
except ModuleNotFoundError:
    from writer_contract import WriterPackage, canonical_digest
    from writer_git_state import (
        WriterEffectError,
        _is_reparse,
        assert_no_link_components,
        repository_root,
        run_git,
        sha256_bytes,
    )

LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"


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
    summary = run_git(root, ["diff", "--summary", "--no-renames"]).stdout_text()
    if summary.strip():
        raise WriterEffectError(
            f"mode/delete/rename summary is forbidden: {summary.strip()}"
        )
    status_bytes = run_git(
        root,
        [
            "status", "--porcelain=v2", "-z", "--untracked-files=all",
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
