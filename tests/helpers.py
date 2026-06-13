# -*- coding: utf-8 -*-
"""测试公共件:把 src 加进 import 路径,提供 mock 前缀、spec 构造器和 run_wf。"""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

MOCK_PREFIX = [sys.executable, str(ROOT / "tests" / "mock_codex.py")]

import runner  # noqa: E402


def spec_dict(stages, workdir=None, **over):
    d = {"version": 1, "name": "t", "workdir": workdir or str(ROOT), "stages": stages}
    d.update(over)
    return d


def stage(name, *tasks):
    return {"name": name, "tasks": list(tasks)}


def task(tid, prompt="干活", **kw):
    return {"id": tid, "prompt": prompt, **kw}


def run_wf(raw, **kw):
    """校验 spec 并在临时运行目录里用 mock 替身跑完整个 workflow。"""
    spec = runner.validate_spec(raw)
    rd = Path(tempfile.mkdtemp(prefix="dynwf-test-")) / "run"
    summary = asyncio.run(runner.run_workflow(spec, rd, MOCK_PREFIX, **kw))
    return summary, rd
