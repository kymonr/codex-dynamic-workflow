# -*- coding: utf-8 -*-
"""Read-only Team Router local closeout status check."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLOBAL_SKILL = Path.home() / ".codex" / "skills" / "codex-team-router"
SKILL_RELATIVE = Path("skills") / "codex-team-router"
ENTRYPOINT_RELATIVE = SKILL_RELATIVE / "SKILL.md"
HARD_CAP_BYTES = 8192
TARGET_BYTES = 7200


def _run_git(repo_root: Path, args: list[str]) -> dict[str, object]:
    command = ["git", "-C", str(repo_root), *args]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": 127}
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def _lines(value: str) -> list[str]:
    return [line for line in value.splitlines() if line.strip()]


def _relative_files(root: Path) -> set[Path]:
    if not root.is_dir():
        return set()
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def _compare_skill(repo_skill: Path, global_skill: Path) -> dict[str, object]:
    if not repo_skill.is_dir():
        return {"status": "blocked", "reason": "repo skill path missing", "differences": {}}
    if not global_skill.is_dir():
        return {"status": "blocked", "reason": "global skill path missing", "differences": {}}
    repo_files = _relative_files(repo_skill)
    global_files = _relative_files(global_skill)
    common = repo_files & global_files
    changed = []
    for relative_path in sorted(common):
        repo_bytes = (repo_skill / relative_path).read_bytes()
        global_bytes = (global_skill / relative_path).read_bytes()
        if repo_bytes != global_bytes:
            changed.append(str(relative_path).replace("\\", "/"))
    differences = {
        "missingInGlobal": sorted(str(path).replace("\\", "/") for path in repo_files - global_files),
        "extraInGlobal": sorted(str(path).replace("\\", "/") for path in global_files - repo_files),
        "changed": changed,
    }
    status = "mismatch" if any(differences.values()) else "match"
    return {"status": status, "reason": "repo/global skill comparison", "differences": differences}


def build_report(repo_root: Path, global_skill: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    repo_skill = repo_root / SKILL_RELATIVE
    entrypoint = repo_root / ENTRYPOINT_RELATIVE
    status = _run_git(repo_root, ["status", "-s", "--untracked-files=all"])
    branch = _run_git(repo_root, ["status", "-sb", "--untracked-files=all"])
    diff_files = _run_git(repo_root, ["diff", "--name-only"])
    entrypoint_bytes = entrypoint.stat().st_size if entrypoint.is_file() else None
    return {
        "mode": "read-only",
        "repoRoot": str(repo_root),
        "gitStatusShort": _lines(str(status["stdout"])),
        "gitStatusBranch": _lines(str(branch["stdout"])),
        "diffFiles": _lines(str(diff_files["stdout"])),
        "gitErrors": [
            {"command": "status -s --untracked-files=all", "stderr": status["stderr"], "returncode": status["returncode"]}
            if not status["ok"] else None,
            {"command": "status -sb --untracked-files=all", "stderr": branch["stderr"], "returncode": branch["returncode"]}
            if not branch["ok"] else None,
            {"command": "diff --name-only", "stderr": diff_files["stderr"], "returncode": diff_files["returncode"]}
            if not diff_files["ok"] else None,
        ],
        "skill": {
            "entrypoint": str(entrypoint),
            "entrypointBytes": entrypoint_bytes,
            "hardCapBytes": HARD_CAP_BYTES,
            "targetBytes": TARGET_BYTES,
            "underHardCap": entrypoint_bytes is not None and entrypoint_bytes < HARD_CAP_BYTES,
            "underTarget": entrypoint_bytes is not None and entrypoint_bytes < TARGET_BYTES,
        },
        "skillSync": _compare_skill(repo_skill, global_skill.resolve()),
        "authorization": {
            "commit": False,
            "push": False,
            "pullRequest": False,
            "merge": False,
            "deploy": False,
            "globalSync": False,
        },
        "readOnlyGuarantee": "reports only; does not stage, commit, push, or sync",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Team Router closeout status check.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--global-skill", type=Path, default=DEFAULT_GLOBAL_SKILL)
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    report = build_report(args.repo_root, args.global_skill)
    report["gitErrors"] = [item for item in report["gitErrors"] if item is not None]
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("mode: %s" % report["mode"])
        print("repoRoot: %s" % report["repoRoot"])
        print("gitStatusShort:")
        for line in report["gitStatusShort"]:
            print("  %s" % line)
        print("diffFiles:")
        for line in report["diffFiles"]:
            print("  %s" % line)
        print("skill.entrypointBytes: %s" % report["skill"]["entrypointBytes"])
        print("skill.underTarget: %s" % report["skill"]["underTarget"])
        print("skillSync.status: %s" % report["skillSync"]["status"])
        print("authorization: no commit, no push, no PR, no merge, no deploy, no global sync")
        print("readOnlyGuarantee: %s" % report["readOnlyGuarantee"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())