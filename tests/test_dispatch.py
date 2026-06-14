# -*- coding: utf-8 -*-
"""Task 5 + 复核加固 测试:dispatch 子命令 + mock_codex 写扩展(全离线,临时 git 仓库)。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  让 src 进 import 路径
import runner
from helpers import make_git_repo, write_spec_dict, wtask

# dispatch 用 mock 替身当 codex:argv 前缀 = [python, mock_codex.py]
MOCK_PREFIX = [sys.executable, str(Path(__file__).resolve().parent / "mock_codex.py")]


def _make_counter():
    n = 0
    while True:
        n += 1
        yield n


_counter = _make_counter()


class _FakeProc:
    """subprocess.Popen 的最小替身:wait() 立即返回(不卡死守卫),returncode=0。"""
    returncode = 0
    pid = 4321

    def wait(self, timeout=None):
        return 0


class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.repo = make_git_repo()
        # 把 WRITE_RUNS_ROOT monkeypatch 到临时目录,不写真实 D:\.codex-tmp、跑完即清
        self._orig_root = runner.WRITE_RUNS_ROOT
        self._root_parent = Path(tempfile.mkdtemp(prefix="dynwf-dispatchroot-"))
        runner.WRITE_RUNS_ROOT = self._root_parent / "workflows"
        self._run_dirs = []

    def tearDown(self):
        # 收尾:删 prepare 建的 worktree 副本,再还原根、删临时根目录和仓库
        for rd in self._run_dirs:
            wt_root = Path(rd) / "wt"
            if wt_root.is_dir():
                for wt in wt_root.iterdir():
                    runner._git_worktree_remove(self.repo, str(wt))
                runner._git_worktree_prune(self.repo)
        runner.WRITE_RUNS_ROOT = self._orig_root
        helpers.rmtree(self._root_parent)
        helpers.rmtree(self.repo)  # 用 Windows 友好的 rmtree 清只读 git 对象,不留残留

    def _prepare(self, tasks):
        spec = runner.validate_write_spec(write_spec_dict(tasks, self.repo))
        stamp = "dwf-test-%d-%s" % (os.getpid(), next(_counter))
        run_dir = runner.WRITE_RUNS_ROOT / stamp
        runner.prepare(spec, run_dir)
        self._run_dirs.append(run_dir)
        return run_dir

    def test_writes_appear_in_worktree(self):
        """[MOCK:writes=...] 指定的文件应出现在该任务的副本里;exit_code==0;agent.log 存在。"""
        run_dir = self._prepare([
            wtask("a", prompt="改文件 [MOCK:writes=new1.txt,sub/new2.txt]"),
        ])
        res = runner.dispatch(run_dir, "a", MOCK_PREFIX)
        self.assertEqual(res, {"id": "a", "exit_code": 0, "stalled": False})

        skel = json.loads((Path(run_dir) / "summary.json").read_text(encoding="utf-8"))
        wt = Path(next(t["worktree"] for t in skel["tasks"] if t["id"] == "a"))
        self.assertTrue((wt / "new1.txt").is_file())
        self.assertTrue((wt / "sub" / "new2.txt").is_file())
        self.assertTrue((Path(run_dir) / "tasks" / "a" / "agent.log").is_file())

    def test_unknown_task_id_raises(self):
        """run_dir 里没有这个 task_id → WorkflowError。"""
        run_dir = self._prepare([wtask("a", prompt="改文件 [MOCK:writes=x.txt]")])
        with self.assertRaises(runner.WorkflowError):
            runner.dispatch(run_dir, "nope", MOCK_PREFIX)

    def test_commit_changes_head(self):
        """[MOCK:commit] 后副本 HEAD 应不同于 base(子代理偷偷 commit 的场景)。"""
        run_dir = self._prepare([
            wtask("a", prompt="改文件 [MOCK:writes=c.txt] [MOCK:commit]"),
        ])
        skel = json.loads((Path(run_dir) / "summary.json").read_text(encoding="utf-8"))
        base = skel["base_head"]
        wt = next(t["worktree"] for t in skel["tasks"] if t["id"] == "a")

        self.assertEqual(runner._git_head(wt), base)  # dispatch 前副本 HEAD == base
        res = runner.dispatch(run_dir, "a", MOCK_PREFIX)
        self.assertEqual(res["exit_code"], 0)
        self.assertNotEqual(runner._git_head(wt), base)  # mock 偷偷 commit 后 HEAD 变化

    # ---- 复核加固:dispatch 写入侧防御(run-dir 归属 / 副本越界 / reasoning 消毒 /
    #      stdin=DEVNULL / -s workspace-write 真到 argv) ----

    def test_run_dir_outside_write_root_rejected(self):
        """run_dir 不在 WRITE_RUNS_ROOT 下(伪造/错项目)→ WorkflowError,绝不落笔写。"""
        bogus = Path(tempfile.mkdtemp(prefix="dynwf-bogus-disp-"))
        try:
            (bogus / "summary.json").write_text(
                json.dumps({"mode": "write", "base_head": "x",
                            "workdir": str(self.repo),
                            "tasks": [{"id": "a", "worktree": str(self.repo)}]}),
                encoding="utf-8")
            with self.assertRaises(runner.WorkflowError):
                runner.dispatch(bogus, "a", MOCK_PREFIX)
        finally:
            shutil.rmtree(bogus, ignore_errors=True)

    def test_worktree_outside_wt_dir_rejected(self):
        """骨架 worktree 字段被改指到 run-dir/wt 之外(如真实项目树)→ 拒绝派工。"""
        run_dir = self._prepare([wtask("a", prompt="改", scope=["."])])
        skel_p = Path(run_dir) / "summary.json"
        skel = json.loads(skel_p.read_text(encoding="utf-8"))
        skel["tasks"][0]["worktree"] = str(self.repo)  # 指到真实项目工作树
        skel_p.write_text(json.dumps(skel, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(runner.WorkflowError):
            runner.dispatch(run_dir, "a", MOCK_PREFIX)

    def test_devnull_stdin_and_workspace_write_in_argv(self):
        """落笔写必须 stdin=DEVNULL(不挂死)且 argv 含 -s workspace-write(硬编码沙箱)。"""
        run_dir = self._prepare([wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])])
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return _FakeProc()

        with mock.patch.object(runner.subprocess, "Popen", fake_popen):
            res = runner.dispatch(run_dir, "a", MOCK_PREFIX)
        self.assertEqual(res["exit_code"], 0)
        self.assertFalse(res["stalled"])
        self.assertIs(captured["kwargs"]["stdin"], runner.subprocess.DEVNULL)
        self.assertIn("-s", captured["cmd"])
        self.assertIn("workspace-write", captured["cmd"])

    def test_bad_reasoning_effort_sanitized(self):
        """骨架被手改塞入非法 reasoning_effort → 降级 None,绝不拼进 -c。"""
        run_dir = self._prepare([wtask("a", prompt="改", scope=["."])])
        skel_p = Path(run_dir) / "summary.json"
        skel = json.loads(skel_p.read_text(encoding="utf-8"))
        skel["tasks"][0]["reasoning_effort"] = "high -c sandbox_mode=danger-full-access"
        skel_p.write_text(json.dumps(skel, ensure_ascii=False), encoding="utf-8")
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            return _FakeProc()

        with mock.patch.object(runner.subprocess, "Popen", fake_popen):
            runner.dispatch(run_dir, "a", MOCK_PREFIX)
        self.assertNotIn("-c", captured["cmd"])  # 非法值被降级,不拼 -c

    def test_stall_detected_and_killed(self):
        """agent.log 连续无新增超过 stall_seconds → 判卡死、杀进程树、返回 stalled。"""
        run_dir = self._prepare([wtask("a", prompt="卡住不输出 [MOCK:sleep=5]")])
        res = runner.dispatch(run_dir, "a", MOCK_PREFIX,
                              stall_seconds=1, poll_interval=0.2)
        self.assertTrue(res["stalled"])
        self.assertNotEqual(res["exit_code"], 0)
        # dispatch.json 也记下 stalled,供 collect/人工诊断
        disp = json.loads(
            (Path(run_dir) / "tasks" / "a" / "dispatch.json").read_text(encoding="utf-8"))
        self.assertTrue(disp["stalled"])


if __name__ == "__main__":
    unittest.main()
