# -*- coding: utf-8 -*-
"""T0 smoke:确认 make_git_repo 建出真 git 仓库且有一次提交;
write_spec_dict / wtask 产出契约形状的写模式 spec。全程离线。"""
import shutil
import subprocess
import unittest
from pathlib import Path

import helpers


def _git(args, cwd):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True)


class TestMakeGitRepo(unittest.TestCase):
    def setUp(self):
        self.repo = helpers.make_git_repo()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_is_a_work_tree(self):
        cp = _git(["rev-parse", "--is-inside-work-tree"], self.repo)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(cp.stdout.strip(), "true")

    def test_has_one_commit_head_exists(self):
        cp = _git(["rev-parse", "HEAD"], self.repo)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue(cp.stdout.strip())
        cnt = _git(["rev-list", "--count", "HEAD"], self.repo)
        self.assertEqual(cnt.stdout.strip(), "1", cnt.stderr)

    def test_seed_file_committed(self):
        self.assertTrue((self.repo / "seed.txt").is_file())
        st = _git(["status", "--porcelain"], self.repo)
        self.assertEqual(st.stdout, "")


class TestWriteSpecBuilders(unittest.TestCase):
    def test_wtask_minimal(self):
        t = helpers.wtask("a")
        self.assertEqual(t, {"id": "a", "prompt": "改文件"})

    def test_wtask_with_scope_and_extra(self):
        t = helpers.wtask("b", prompt="p", scope=["src"], reasoning_effort="low")
        self.assertEqual(
            t, {"id": "b", "prompt": "p", "scope": ["src"], "reasoning_effort": "low"})

    def test_wtask_scope_none_omitted(self):
        t = helpers.wtask("c", scope=None)
        self.assertNotIn("scope", t)

    def test_write_spec_dict_shape(self):
        tasks = [helpers.wtask("a")]
        d = helpers.write_spec_dict(tasks, "D:\\some\\dir")
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["mode"], "write")
        self.assertEqual(d["name"], "wt")
        self.assertEqual(d["workdir"], "D:\\some\\dir")
        self.assertEqual(d["tasks"], tasks)

    def test_write_spec_dict_override(self):
        d = helpers.write_spec_dict([], "D:\\d", name="other", mode="write")
        self.assertEqual(d["name"], "other")


if __name__ == "__main__":
    unittest.main()
