# -*- coding: utf-8 -*-
"""测试公共件:把 src 加进 import 路径,提供 mock 前缀、spec 构造器和 run_wf。"""
import asyncio
import atexit
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

MOCK_PREFIX = [sys.executable, str(ROOT / "tests" / "mock_codex.py")]
MOCK_CLAUDE_PREFIX = [sys.executable, str(ROOT / "tests" / "mock_claude.py")]

import runner  # noqa: E402


def rmtree(path):
    """Windows 友好的 rmtree:git 的 loose object / pack 文件是只读的,
    shutil.rmtree 默认删不掉(ignore_errors=True 会静默残留临时仓库),这里遇错先清只读位再重删,
    清完仍删不掉才忽略。用于测试收尾,确保 %TEMP% 不堆 dynwf-* 残留。"""
    if not os.path.exists(path):
        return
    def _onexc(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    try:
        shutil.rmtree(path, onexc=_onexc)        # Python 3.12+
    except TypeError:
        shutil.rmtree(path, onerror=lambda f, p, e: _onexc(f, p, e))  # 旧版回退


_ATEXIT_DIRS = []


def mktemp(prefix):
    """建临时目录并登记「进程退出时 rmtree」,给"用完不便逐个 teardown"的测试兜底
    (run_wf 的运行目录、CLI 测试的 spec 目录等),避免 %TEMP% 跨轮累积。
    能 per-test 清的优先用 addCleanup/tearDown;这里是兜底。返回 Path。"""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    _ATEXIT_DIRS.append(d)
    return d


@atexit.register
def _cleanup_atexit_dirs():
    for d in _ATEXIT_DIRS:
        rmtree(d)


def spec_dict(stages, workdir=None, **over):
    d = {"version": 1, "name": "t", "workdir": workdir or str(ROOT), "stages": stages}
    d.update(over)
    return d


def stage(name, *tasks):
    return {"name": name, "tasks": list(tasks)}


def task(tid, prompt="干活", **kw):
    return {"id": tid, "prompt": prompt, **kw}


def run_wf(raw, prefix=None, **kw):
    """校验 spec 并在临时运行目录里用 mock 替身跑完整个 workflow。
    prefix 缺省 codex mock;claude 后端测试传 MOCK_CLAUDE_PREFIX。"""
    spec = runner.validate_spec(raw)
    rd = mktemp("dynwf-test-") / "run"
    summary = asyncio.run(runner.run_workflow(spec, rd, prefix or MOCK_PREFIX, **kw))
    return summary, rd


def _git_local(args, cwd):
    """在 cwd 里跑一条 git 命令(离线、不联网),返回 CompletedProcess。"""
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True)


def make_git_repo():
    """建一个真 git 仓库供写模式测试用:tempfile 临时目录 → git init →
    本地配置 user.email/user.name(-C 局部)→ 写 seed.txt → add+commit。返回仓库 Path。"""
    repo = Path(tempfile.mkdtemp(prefix="dynwf-gitrepo-"))
    init = _git_local(["init"], repo)
    if init.returncode != 0:
        raise RuntimeError("git init 失败: %s" % init.stderr)
    _git_local(["config", "user.email", "test@example.invalid"], repo)
    _git_local(["config", "user.name", "dynwf-test"], repo)
    _git_local(["config", "commit.gpgsign", "false"], repo)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    add = _git_local(["add", "seed.txt"], repo)
    if add.returncode != 0:
        raise RuntimeError("git add 失败: %s" % add.stderr)
    commit = _git_local(["commit", "-m", "seed"], repo)
    if commit.returncode != 0:
        raise RuntimeError("git commit 失败: %s" % commit.stderr)
    return repo


def write_spec_dict(tasks, workdir, **over):
    """构造写模式 spec dict(契约形状)。over 可覆盖任意顶层键。"""
    d = {"version": 1, "mode": "write", "name": "wt",
         "workdir": str(workdir), "tasks": tasks}
    d.update(over)
    return d


_SCOPE_DEFAULT = object()


def wtask(tid, prompt="改文件", scope=_SCOPE_DEFAULT, **kw):
    """构造一个写模式 task dict。默认显式 scope=['.'];scope=None 用于构造缺 scope 反例。"""
    if scope is _SCOPE_DEFAULT:
        scope = ["."]
    return {"id": tid, "prompt": prompt,
            **({} if scope is None else {"scope": scope}), **kw}
