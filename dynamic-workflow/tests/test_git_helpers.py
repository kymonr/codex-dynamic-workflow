# -*- coding: utf-8 -*-
"""Task3: git 辅助函数的离线测试(本地 git 临时仓库,不联网)。"""
import shutil
import unittest
from pathlib import Path

import helpers  # noqa: F401  保证 src 进 sys.path
import runner
from helpers import make_git_repo


class GitHelpersTest(unittest.TestCase):
    def setUp(self):
        self.repo = make_git_repo()
        self._cleanup = [self.repo]

    def tearDown(self):
        # worktree 副本可能在 repo 外,逐个尽力删除
        for p in self._cleanup:
            helpers.rmtree(p)

    # ---- _is_git_repo ----
    def test_is_git_repo_true(self):
        self.assertTrue(runner._is_git_repo(str(self.repo)))

    def test_is_git_repo_false_on_plain_dir(self):
        plain = self.repo.parent / (self.repo.name + "-plain")
        plain.mkdir()
        self._cleanup.append(plain)
        self.assertFalse(runner._is_git_repo(str(plain)))

    def test_is_git_repo_false_on_missing_dir(self):
        missing = self.repo / "does-not-exist"
        self.assertFalse(runner._is_git_repo(str(missing)))

    # ---- _git_head ----
    def test_git_head_is_full_hash(self):
        head = runner._git_head(str(self.repo))
        self.assertEqual(len(head), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in head))

    # ---- _git_status_porcelain ----
    def test_status_clean_then_dirty(self):
        self.assertEqual(runner._git_status_porcelain(str(self.repo)), "")
        (self.repo / "seed.txt").write_text("changed", encoding="utf-8")
        self.assertNotEqual(runner._git_status_porcelain(str(self.repo)), "")

    # ---- _run_git 直查 returncode ----
    def test_run_git_returns_completed_process(self):
        cp = runner._run_git(["git", "rev-parse", "--is-inside-work-tree"],
                             cwd=str(self.repo))
        self.assertEqual(cp.returncode, 0)
        self.assertEqual(cp.stdout.strip(), "true")

    # ---- worktree 全流程 ----
    def test_worktree_lifecycle(self):
        base = runner._git_head(str(self.repo))
        wt = self.repo.parent / (self.repo.name + "-wt")
        self._cleanup.append(wt)

        # add --detach
        runner._git_worktree_add(str(self.repo), str(wt), base)
        self.assertTrue(wt.is_dir())
        self.assertTrue(runner._is_git_repo(str(wt)))

        # worktree list 含该副本(按 resolve 后路径比对,绕过大小写/短名差异)
        paths = [Path(p).resolve() for p in
                 runner._git_worktree_paths(str(self.repo))]
        self.assertIn(wt.resolve(), paths)

        # 在副本里改已跟踪文件 + 加未跟踪文件
        (wt / "seed.txt").write_text("hello from worktree", encoding="utf-8")
        (wt / "newfile.txt").write_text("brand new", encoding="utf-8")

        changed = runner._git_changed_names(str(wt), base)
        self.assertIn("seed.txt", changed)

        diff = runner._git_diff_binary(str(wt), base)
        self.assertIn("seed.txt", diff)
        self.assertIn("hello from worktree", diff)

        untracked = runner._git_untracked(str(wt))
        self.assertIn("newfile.txt", untracked)

        # remove + prune 后副本目录消失
        runner._git_worktree_remove(str(self.repo), str(wt))
        runner._git_worktree_prune(str(self.repo))
        self.assertFalse(wt.exists())

    def test_worktree_add_bad_base_raises(self):
        wt = self.repo.parent / (self.repo.name + "-wtbad")
        self._cleanup.append(wt)
        with self.assertRaises(runner.WorkflowError):
            runner._git_worktree_add(str(self.repo), str(wt),
                                     "0000000000000000000000000000000000000000")


if __name__ == "__main__":
    unittest.main()
