# -*- coding: utf-8 -*-
"""Check repo codex-team-router skill files against a global install copy.

Default behavior is read-only/check-only. The optional --sync flag is provided
for an explicitly authorized maintenance flow, but this task only exercises
--check.
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path


DEFAULT_GLOBAL_SKILL = Path.home() / ".codex" / "skills" / "codex-team-router"
DEFAULT_REPO_SKILL = Path(__file__).resolve().parents[1] / "skills" / "codex-team-router"


def _relative_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file()
    }


def compare_skill_trees(repo_skill: Path, global_skill: Path) -> dict[str, list[str]]:
    repo_files = _relative_files(repo_skill) if repo_skill.exists() else set()
    global_files = _relative_files(global_skill) if global_skill.exists() else set()
    common = repo_files & global_files
    changed = sorted(
        str(path).replace("\\", "/")
        for path in common
        if not filecmp.cmp(repo_skill / path, global_skill / path, shallow=False)
    )
    return {
        "missing_in_global": sorted(str(path).replace("\\", "/") for path in repo_files - global_files),
        "extra_in_global": sorted(str(path).replace("\\", "/") for path in global_files - repo_files),
        "changed": changed,
    }


def _has_drift(diff: dict[str, list[str]]) -> bool:
    return any(diff.values())


def _print_diff(diff: dict[str, list[str]]) -> None:
    for label in ("missing_in_global", "extra_in_global", "changed"):
        values = diff[label]
        if values:
            print("%s:" % label)
            for value in values:
                print("  - %s" % value)


def sync_skill_tree(repo_skill: Path, global_skill: Path) -> None:
    if not repo_skill.is_dir():
        raise SystemExit("repo skill path does not exist: %s" % repo_skill)
    global_skill.mkdir(parents=True, exist_ok=True)
    repo_files = _relative_files(repo_skill)
    global_files = _relative_files(global_skill) if global_skill.exists() else set()
    for relative_path in global_files - repo_files:
        (global_skill / relative_path).unlink()
    for relative_path in repo_files:
        target = global_skill / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_skill / relative_path, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Team Router skill global install drift.")
    parser.add_argument("--repo-skill", type=Path, default=DEFAULT_REPO_SKILL)
    parser.add_argument("--global-skill", type=Path, default=DEFAULT_GLOBAL_SKILL)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only drift check; this is the default")
    mode.add_argument("--sync", action="store_true", help="copy repo skill files into the global skill path")
    args = parser.parse_args(argv)

    repo_skill = args.repo_skill.resolve()
    global_skill = args.global_skill.resolve()
    if not repo_skill.is_dir():
        print("mode: check-only" if not args.sync else "mode: sync")
        print("status: blocked")
        print("repo skill path does not exist: %s" % repo_skill)
        return 2
    if args.sync:
        sync_skill_tree(repo_skill, global_skill)
        print("mode: sync")
    else:
        print("mode: check-only")
    diff = compare_skill_trees(repo_skill, global_skill)
    if _has_drift(diff):
        print("status: mismatch")
        _print_diff(diff)
        return 1
    print("status: match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())