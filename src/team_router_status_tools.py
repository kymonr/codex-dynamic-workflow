# -*- coding: utf-8 -*-
"""Read-only Team Router status tool helpers."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLOBAL_SKILL = Path.home() / ".codex" / "skills" / "codex-team-router"
SKILL_RELATIVE = Path("skills") / "codex-team-router"
ENTRYPOINT_RELATIVE = SKILL_RELATIVE / "SKILL.md"
DEFAULT_SCAN_FILES = (
    Path("docs") / "workbench.md",
    Path("docs") / "team-router" / "module-map.md",
)
HARD_CAP_BYTES = 8192
TARGET_BYTES = 7200
OLD_OPTIMIZATION_PACKAGE = "ctr-20260628-team-router-optimization-1-6"
PACKAGE_ID_RE = re.compile(r"ctr-\d{8}[a-z0-9-]*")
PACKAGE_DATE_RE = re.compile(r"ctr-(\d{8})")
CURRENT_STATE_HEADINGS = {
    "current task",
    "current state",
    "current status",
    "current truth",
    "current diff surface",
    "current next gate",
    "review and verification gate",
}
ACTIVE_CURRENT_STATE_MARKERS = (
    "State: active",
    "active local package implementation",
    "active local package",
    "implementation in progress",
    "package is still active",
    "because this package is active",
)
PENDING_GATE_MARKERS = (
    "reviewer/verifier",
    "reviewer gate required",
    "verifier gate required",
    "reviewer re-review",
    "verifier re-check",
    "pending reviewer",
    "pending verifier",
)
NEUTRAL_GATE_MARKERS = (
    "current next gate: none",
    "current gate: none",
    "no action required",
    "no current gate",
    "no reviewer gate",
    "no verifier gate",
    "not pending reviewer",
    "not pending verifier",
)
DIRTY_DIFF_MARKERS = (
    "dirty because this package is active",
    "`M ",
    "`A ",
    "`D ",
    "`?? ",
    "modified `",
    "untracked package",
)


def run_git(repo_root: Path, args: list[str]) -> dict[str, object]:
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


def lines(value: str) -> list[str]:
    return [line for line in value.splitlines() if line.strip()]


def _relative_files(root: Path) -> set[Path]:
    if not root.is_dir():
        return set()
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def compare_skill(repo_skill: Path, global_skill: Path) -> dict[str, object]:
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


def default_scan_paths(repo_root: Path) -> list[Path]:
    paths = [repo_root / relative for relative in DEFAULT_SCAN_FILES]
    package_dir = repo_root / "docs" / "team-router" / "packages"
    if package_dir.is_dir():
        paths.extend(sorted(package_dir.glob("*.md")))
    return paths


def load_scan_texts(repo_root: Path, scan_files: list[Path] | None) -> dict[str, str]:
    paths = scan_files if scan_files else default_scan_paths(repo_root)
    texts: dict[str, str] = {}
    for path in paths:
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.is_file():
            continue
        key = str(resolved)
        try:
            texts[key] = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            texts[key] = resolved.read_text(encoding="utf-8-sig", errors="replace")
    return texts


def _claim(path: str, reason: str, evidence: str) -> dict[str, str]:
    return {"path": path, "reason": reason, "evidence": evidence}


def _heading_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    return stripped.lstrip("#").strip().lower()


def current_state_lines(text: str) -> list[str]:
    lines_ = text.splitlines()
    sections: list[str] = []
    in_current_section = False
    saw_heading = False
    saw_current_heading = False
    for line in lines_:
        heading = _heading_name(line)
        if heading is not None:
            saw_heading = True
            in_current_section = heading in CURRENT_STATE_HEADINGS
            saw_current_heading = saw_current_heading or in_current_section
        if in_current_section:
            sections.append(line)
    if saw_current_heading:
        return sections
    if saw_heading:
        return []
    return lines_


def _first_marker_line(lines_: list[str], markers: tuple[str, ...]) -> str | None:
    for line in lines_:
        stripped = line.strip()
        if _heading_name(stripped) is not None:
            continue
        if any(marker in stripped for marker in markers):
            return stripped
    return None


def _first_pending_gate_line(lines_: list[str]) -> str | None:
    for line in lines_:
        stripped = line.strip()
        if _heading_name(stripped) is not None:
            continue
        normalized = stripped.lower()
        if any(marker in normalized for marker in NEUTRAL_GATE_MARKERS):
            continue
        if any(marker in stripped for marker in PENDING_GATE_MARKERS):
            return stripped
    return None


def normalized_scan_path(path: str) -> str:
    return path.replace("\\", "/")


def is_workbench_path(path: str) -> bool:
    return normalized_scan_path(path).endswith("docs/workbench.md")


def is_package_path(path: str) -> bool:
    normalized = normalized_scan_path(path)
    return "/docs/team-router/packages/" in normalized or normalized.startswith("docs/team-router/packages/")


def is_module_map_path(path: str) -> bool:
    return normalized_scan_path(path).endswith("docs/team-router/module-map.md")


def package_ids(value: str) -> set[str]:
    return set(PACKAGE_ID_RE.findall(value))


def package_date(package_id: str) -> str | None:
    match = PACKAGE_DATE_RE.search(package_id)
    return match.group(1) if match else None


def latest_package_date(scan_texts: dict[str, str]) -> str | None:
    dates: list[str] = []
    for path, text in scan_texts.items():
        if not is_package_path(path):
            continue
        ids = package_ids(path) | package_ids(text[:240])
        for package_id in ids:
            date = package_date(package_id)
            if date is not None:
                dates.append(date)
    return max(dates) if dates else None


def module_map_marks_phase1_complete(scan_texts: dict[str, str]) -> bool:
    for path, text in scan_texts.items():
        if not is_module_map_path(path):
            continue
        normalized = text.lower()
        if "phase 1 completed" in normalized and "remaining safe extraction order" in normalized:
            return True
    return False


def find_stale_state_claims(report: dict[str, object], scan_texts: dict[str, str]) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    actual_skill_status = str(report["skillSync"]["status"])
    actual_dirty = bool(report["gitStatusShort"] or report["diffFiles"])
    actual_clean_synced = not actual_dirty and actual_skill_status == "match"
    latest_package = latest_package_date(scan_texts)
    phase1_completed = module_map_marks_phase1_complete(scan_texts)

    for path, text in scan_texts.items():
        current_lines_ = current_state_lines(text)
        current_text = "\n".join(current_lines_)
        stale_active_lines = [
            line.strip()
            for line in current_lines_
            if (
                ("State: active local package implementation" in line or "active local package implementation for" in line)
                and OLD_OPTIMIZATION_PACKAGE in line
            )
        ]
        if stale_active_lines:
            claims.append(
                _claim(
                    path,
                    "old optimization package is not the current task",
                    stale_active_lines[0],
                )
            )

        if "`skillSync.status: mismatch`" in current_text and actual_skill_status != "mismatch":
            claims.append(
                _claim(
                    path,
                    "skillSync.status mismatch",
                    "document says mismatch but live comparison reports %s" % actual_skill_status,
                )
            )

        if (
            not actual_dirty
            and "Latest `git status -s --untracked-files=all` reports:" in current_text
            and "M docs/workbench.md" in current_text
        ):
            claims.append(
                _claim(
                    path,
                    "documented current diff surface does not match live git status",
                    "live git status has no short-status entries",
                )
            )
        if actual_clean_synced:
            active_line = _first_marker_line(current_lines_, ACTIVE_CURRENT_STATE_MARKERS)
            if active_line:
                claims.append(
                    _claim(
                        path,
                        "current-state claims active package while live git/skill truth is clean/synced",
                        active_line,
                    )
                )
            pending_gate_line = _first_pending_gate_line(current_lines_)
            if pending_gate_line:
                claims.append(
                    _claim(
                        path,
                        "current-state claims pending reviewer/verifier gate while live git/skill truth is clean/synced",
                        pending_gate_line,
                    )
                )
            dirty_line = _first_marker_line(current_lines_, DIRTY_DIFF_MARKERS)
            if dirty_line:
                claims.append(
                    _claim(
                        path,
                        "current-state claims dirty diff surface while live git/skill truth is clean/synced",
                        dirty_line,
                    )
                )
            if is_workbench_path(path) and latest_package is not None:
                current_dates = [
                    date
                    for date in (package_date(package_id) for package_id in package_ids(current_text))
                    if date is not None
                ]
                if current_dates and max(current_dates) < latest_package:
                    claims.append(
                        _claim(
                            path,
                            "workbench current task is behind latest package record",
                            "latest package date: %s; current package date: %s" % (latest_package, max(current_dates)),
                        )
                    )
            if is_workbench_path(path) and phase1_completed and "module extraction phase 1" in current_text.lower():
                claims.append(
                    _claim(
                        path,
                        "workbench next gate points at completed module extraction phase",
                        "module-map marks phase 1 complete; current workbench still names module extraction phase 1",
                    )
                )
    return claims


def _base_git_skill_report(repo_root: Path, global_skill: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    repo_skill = repo_root / SKILL_RELATIVE
    entrypoint = repo_root / ENTRYPOINT_RELATIVE
    status = run_git(repo_root, ["status", "-s", "--untracked-files=all"])
    branch = run_git(repo_root, ["status", "-sb", "--untracked-files=all"])
    diff_files = run_git(repo_root, ["diff", "--name-only"])
    entrypoint_bytes = entrypoint.stat().st_size if entrypoint.is_file() else None
    return {
        "mode": "read-only",
        "repoRoot": str(repo_root),
        "gitStatusShort": lines(str(status["stdout"])),
        "gitStatusBranch": lines(str(branch["stdout"])),
        "diffFiles": lines(str(diff_files["stdout"])),
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
        "skillSync": compare_skill(repo_skill, global_skill.resolve()),
        "authorization": {
            "commit": False,
            "push": False,
            "pullRequest": False,
            "merge": False,
            "deploy": False,
            "globalSync": False,
        },
    }


def build_truth_report(
    repo_root: Path = DEFAULT_REPO_ROOT,
    global_skill: Path = DEFAULT_GLOBAL_SKILL,
    scan_files: list[Path] | None = None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    scan_texts = load_scan_texts(repo_root, scan_files)
    report = _base_git_skill_report(repo_root, global_skill)
    report["scanFiles"] = sorted(scan_texts)
    report["readOnlyGuarantee"] = "reports only; does not stage, commit, push, PR, merge, deploy, or sync"
    report["gitErrors"] = [item for item in report["gitErrors"] if item is not None]
    report["staleClaims"] = find_stale_state_claims(report, scan_texts)
    return report


def build_closeout_report(repo_root: Path, global_skill: Path) -> dict[str, object]:
    report = _base_git_skill_report(repo_root, global_skill)
    report["readOnlyGuarantee"] = "reports only; does not stage, commit, push, or sync"
    return report


def truth_status(truth: dict[str, object]) -> str:
    dirty = bool(truth["gitStatusShort"] or truth["diffFiles"])
    stale = bool(truth["staleClaims"])
    if dirty and stale:
        return "dirty_or_stale"
    if dirty:
        return "dirty"
    if stale:
        return "stale"
    if truth["skillSync"]["status"] == "match":
        return "clean_synced"
    return "needs_attention"


def next_action(truth_status: str, truth: dict[str, object]) -> str:
    if truth_status in {"dirty_or_stale", "stale"}:
        return "refresh workbench/package current-state text from truth_check/doctor before claiming current truth"
    if truth_status == "dirty":
        return "review the local diff, run the required reviewer pass, then run the required verifier pass before closeout"
    if truth["skillSync"]["status"] != "match":
        return "decide whether global skill sync is explicitly authorized; do not sync by default"
    return "no action required unless the manager opens a new package"