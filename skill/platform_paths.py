"""Cross-platform local paths for Dynamic Workflow.

The runtime keeps all generated state outside the repository by default. Every
location can be overridden explicitly through environment variables so callers
can place artifacts on a controlled volume.
"""

from __future__ import annotations

import os
import tempfile
import sys
from pathlib import Path
from typing import Mapping, MutableMapping

APP_DIR_NAME = "codex-dynamic-workflow"
STATE_HOME_ENV = "DYNWF_HOME"
RUNS_ROOT_ENV = "DYNWF_RUNS_ROOT"
WORKTREE_ROOT_ENV = "DYNWF_WORKTREE_ROOT"


def _expanded(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser()


def default_state_root(
    env: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
    platform: str | None = None,
) -> Path:
    """Return the platform-appropriate state directory without creating it."""

    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    platform = sys.platform if platform is None else platform

    if configured := env.get(STATE_HOME_ENV):
        return _expanded(configured)

    if platform in {"nt", "win32"}:
        base = env.get("LOCALAPPDATA")
        return _expanded(base) / APP_DIR_NAME if base else home / "AppData" / "Local" / APP_DIR_NAME

    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME

    if configured := env.get("XDG_STATE_HOME"):
        return _expanded(configured) / APP_DIR_NAME
    return home / ".local" / "state" / APP_DIR_NAME


def default_runs_root(
    env: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
    platform: str | None = None,
) -> Path:
    env = os.environ if env is None else env
    if configured := env.get(RUNS_ROOT_ENV):
        return _expanded(configured)
    return default_state_root(env, home=home, platform=platform) / "workflows"


def default_worktree_root(
    env: Mapping[str, str] | None = None,
    *,
    temp_dir: Path | None = None,
) -> Path:
    env = os.environ if env is None else env
    if configured := env.get(WORKTREE_ROOT_ENV):
        return _expanded(configured)
    base = Path(tempfile.gettempdir()) if temp_dir is None else temp_dir
    return base / APP_DIR_NAME / "worktrees"


def apply_runtime_defaults(env: MutableMapping[str, str] | None = None) -> dict[str, str]:
    """Populate missing runtime path variables and return the effective values."""

    env = os.environ if env is None else env
    env.setdefault(RUNS_ROOT_ENV, str(default_runs_root(env)))
    env.setdefault(WORKTREE_ROOT_ENV, str(default_worktree_root(env)))
    return {
        RUNS_ROOT_ENV: env[RUNS_ROOT_ENV],
        WORKTREE_ROOT_ENV: env[WORKTREE_ROOT_ENV],
    }


def configure_utf8_stdio() -> None:
    """Make real CLI streams UTF-8 without replacing captured test streams."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="strict")
        except (OSError, ValueError):
            # Embedded hosts and captured streams may forbid reconfiguration.
            continue
