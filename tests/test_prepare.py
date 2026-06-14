# -*- coding: utf-8 -*-
"""Task 4: prepare —— 建隔离 worktree 副本、写 prompt、写 summary 骨架、失败回滚。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  把 src 加进 import 路径
import runner
from helpers import make_git_repo, write_spec_dict, wtask


def _vspec(repo, tasks):
    """构造并校验一份写 spec(workdir=临时 git 仓库)。"""
    raw = write_spec_dict(tasks, repo)
    return runner.validate_write_spec(raw)


def _fresh_run_dir():
    """tempfile 下一个尚不存在的子路径,交给 prepare 原子创建。"""
    base = Path(tempfile.mkdtemp(prefix="dynwf-prep-"))
    return base / "run"


class PrepareSuccessTest(unittest.TestCase):
    def setUp(self):
        self.repo = make_git_repo()
        self.run_dir = _fresh_run_dir()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        # 收尾:移除可能残留的 worktree,再删临时目录(忽略已不存在)
        try:
            runner._git_worktree_prune(str(self.repo))
        except Exception:
            pass
        helpers.rmtree(self.repo)
        shutil.rmtree(self.run_dir.parent, ignore_errors=True)

    def test_creates_worktrees_prompts_and_skeleton(self):
        spec = _vspec(self.repo, [
            wtask("alpha", prompt="改 alpha", scope=["src/alpha"]),
            wtask("beta", prompt="改 beta"),
        ])
        manifest = runner.prepare(spec, self.run_dir)

        # run_dir 已建,manifest 自洽
        self.assertTrue(self.run_dir.is_dir())
        self.assertEqual(manifest["run_dir"], str(self.run_dir))
        self.assertEqual(len(manifest["dispatch"]), 2)
        # 两个任务 → warn 为 None(>2 才警告)
        self.assertIsNone(manifest["warn"])

        # 每个 task:worktree 真建出来、prompt.txt 写了且含禁 git 提示
        for tid, prompt_body in (("alpha", "改 alpha"), ("beta", "改 beta")):
            wt = self.run_dir / "wt" / tid
            self.assertTrue(wt.is_dir(), "worktree 未建: %s" % wt)
            self.assertTrue(runner._is_git_repo(str(wt)))
            ptxt = (self.run_dir / "tasks" / tid / "prompt.txt").read_text(
                encoding="utf-8")
            self.assertIn(prompt_body, ptxt)
            self.assertIn("git", ptxt)  # 含「不要跑任何 git 命令」边界提示

        # summary.json 骨架:base_head 是 40 位、mode/workdir 自洽、每 task 有 worktree
        skel = json.loads(
            (self.run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(skel["mode"], "write")
        self.assertEqual(skel["workdir"], str(self.repo))
        self.assertEqual(skel["run_dir"], str(self.run_dir))
        self.assertEqual(len(skel["base_head"]), 40)
        ids = {t["id"]: t for t in skel["tasks"]}
        self.assertEqual(set(ids), {"alpha", "beta"})
        self.assertEqual(ids["alpha"]["scope"], ["src/alpha"])
        self.assertEqual(ids["beta"]["scope"], [])
        self.assertEqual(
            ids["alpha"]["worktree"], str(self.run_dir / "wt" / "alpha"))

    def test_warn_when_more_than_two_tasks(self):
        spec = _vspec(self.repo, [
            wtask("a"), wtask("b"), wtask("c"),
        ])
        manifest = runner.prepare(spec, self.run_dir)
        self.assertEqual(len(manifest["dispatch"]), 3)
        self.assertIsNotNone(manifest["warn"])

    def test_dispatch_cmds_have_double_dash(self):
        # 打印的派工命令含 -- 分隔,防 task id 以 - 开头被当选项
        spec = _vspec(self.repo, [wtask("a")])
        manifest = runner.prepare(spec, self.run_dir)
        self.assertTrue(all(" -- " in line for line in manifest["dispatch"]))

    def test_oversized_final_prompt_rejected_no_residue(self):
        # scope 极长 → 加边界后最终 prompt 超上限 → prepare 拒、不留 run_dir
        spec = _vspec(self.repo, [
            wtask("a", prompt="改", scope=["x" * (runner.MAX_PROMPT_CHARS + 100)])])
        with self.assertRaises(runner.WorkflowError):
            runner.prepare(spec, self.run_dir)
        self.assertFalse(self.run_dir.exists())


class PrepareRunDirExistsTest(unittest.TestCase):
    def setUp(self):
        self.repo = make_git_repo()
        self.run_dir = _fresh_run_dir()
        self.run_dir.mkdir(parents=True)  # 预先建好,触发 exist_ok=False 冲突
        self.addCleanup(helpers.rmtree, self.repo)
        self.addCleanup(shutil.rmtree, self.run_dir.parent, ignore_errors=True)

    def test_existing_run_dir_rejected(self):
        spec = _vspec(self.repo, [wtask("a")])
        with self.assertRaises(runner.WorkflowError):
            runner.prepare(spec, self.run_dir)


class PrepareDirtyRepoTest(unittest.TestCase):
    def setUp(self):
        self.repo = make_git_repo()
        # 弄脏工作树:新增一个未跟踪文件
        (self.repo / "dirty.txt").write_text("WIP", encoding="utf-8")
        self.run_dir = _fresh_run_dir()
        self.addCleanup(helpers.rmtree, self.repo)
        self.addCleanup(shutil.rmtree, self.run_dir.parent, ignore_errors=True)

    def test_dirty_default_rejected_and_no_residue(self):
        spec = _vspec(self.repo, [wtask("a")])
        with self.assertRaises(runner.WorkflowError):
            runner.prepare(spec, self.run_dir)
        # 默认拒 dirty:run_dir 不得残留
        self.assertFalse(self.run_dir.exists())

    def test_allow_dirty_succeeds(self):
        spec = _vspec(self.repo, [wtask("a")])
        manifest = runner.prepare(spec, self.run_dir, allow_dirty=True)
        self.assertTrue((self.run_dir / "wt" / "a").is_dir())
        skel = json.loads(
            (self.run_dir / "summary.json").read_text(encoding="utf-8"))
        # dirty 原文进 status_raw 骨架(非空)
        self.assertNotEqual(skel["status_raw"].strip(), "")


class PrepareRollbackTest(unittest.TestCase):
    def setUp(self):
        self.repo = make_git_repo()
        self.run_dir = _fresh_run_dir()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            runner._git_worktree_prune(str(self.repo))
        except Exception:
            pass
        helpers.rmtree(self.repo)
        shutil.rmtree(self.run_dir.parent, ignore_errors=True)

    def test_worktree_add_failure_rolls_back(self):
        spec = _vspec(self.repo, [wtask("a"), wtask("b")])

        real_add = runner._git_worktree_add
        removed = []  # 记录被回滚 remove 的副本路径

        def fake_add(repo, wt_path, base):
            # 第一个(a)正常建;第二个(b)模拟失败
            if str(wt_path).endswith("b"):
                raise runner.WorkflowError("模拟 worktree add 失败")
            return real_add(repo, wt_path, base)

        real_remove = runner._git_worktree_remove

        def spy_remove(repo, wt_path):
            removed.append(str(wt_path))
            return real_remove(repo, wt_path)

        with mock.patch.object(runner, "_git_worktree_add", fake_add), \
                mock.patch.object(runner, "_git_worktree_remove", spy_remove):
            with self.assertRaises(runner.WorkflowError):
                runner.prepare(spec, self.run_dir)

        # 已建的 a 副本被 remove 回滚;run_dir 被删,无半成品残留
        self.assertIn(str(self.run_dir / "wt" / "a"), removed)
        self.assertFalse(self.run_dir.exists())


if __name__ == "__main__":
    unittest.main()
