#!/usr/bin/env python3
"""Portable entry point for the explicit Dynamic Workflow CLI runner."""

from __future__ import annotations

from platform_paths import apply_runtime_defaults

apply_runtime_defaults()

from runner import main  # noqa: E402  (defaults must be applied before import)


if __name__ == "__main__":
    raise SystemExit(main())
