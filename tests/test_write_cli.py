# -*- coding: utf-8 -*-
"""Task 7 + 复核加固 测试:写模式 CLI 子命令分发 + 读模式向后兼容。
全程用 runner.main(argv=[...]) 直接调,不起真实 codex;
写模式 run_dir 根用 monkeypatch 把 runner.WRITE_RUNS_ROOT 指到临时目录。
所有临时仓库/spec/run 根都登记 addCleanup,测试结束不在 %TEMP% 留残留。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import (runner, ROOT, make_git_repo, write_spec_dict, wtask,
                     spec_dict, stage, task, rmtree)

MOCK = str(ROOT / "tests" / "mock_codex.py")


class _TempTracking(unittest.TestCase):
    """统一的临时资源登记:仓库 + spec 目录都在 tearDown 后被清掉。"""

    def _mk_repo(self):
        repo = make_git_repo()
        self.addCleanup(rmtree, repo)  # Windows 友好 rmtree:清只读 git 对象,不残留
        return repo

    def _spec_json(self, obj, prefix="dynwf-wcli-"):
        d = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(rmtree, d)
        p = d / "spec.json"
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p

    def _mk_tempdir(self, prefix):
        d = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(rmtree, d)
        return d


class WriteCliBase(_TempTracking):
    """把 WRITE_RUNS_ROOT 临时指到 tempdir,避免写真实 D:\\.codex-tmp。"""

    def setUp(self):
        self._orig_root = runner.WRITE_RUNS_ROOT
        self._wroot_parent = Path(tempfile.mkdtemp(prefix="dynwf-wroot-"))
        self._tmp_root = self._wroot_parent / "workflows"
        runner.WRITE_RUNS_ROOT = self._tmp_root
        # 写模式 dispatch 的 --codex-cmd 仅测试模式放行,测试里显式开
        os.environ["DYNWF_TEST_MODE"] = "1"

    def tearDown(self):
        # 先注销可能残留的 worktree 副本,再还原根、删临时根目录
        if self._tmp_root.is_dir():
            for run_dir in self._tmp_root.iterdir():
                wt_root = run_dir / "wt"
                if wt_root.is_dir():
                    skel_p = run_dir / "summary.json"
                    try:
                        skel = json.loads(skel_p.read_text(encoding="utf-8"))
                        workdir = skel.get("workdir")
                        for wt in wt_root.iterdir():
                            runner._git_worktree_remove(workdir, str(wt))
                        runner._git_worktree_prune(workdir)
                    except Exception:
                        pass
        runner.WRITE_RUNS_ROOT = self._orig_root
        os.environ.pop("DYNWF_TEST_MODE", None)
        rmtree(self._wroot_parent)

    def _only_run_dir(self):
        """prepare 在 WRITE_RUNS_ROOT 下建唯一一个 run_dir,取它的 Path。"""
        kids = [p for p in self._tmp_root.iterdir() if p.is_dir()]
        self.assertEqual(len(kids), 1, "应恰好生成一个 run_dir")
        return kids[0]


class TestPrepareSubcommand(WriteCliBase):
    def test_prepare_creates_run_dir_under_write_runs_root(self):
        repo = self._mk_repo()
        raw = write_spec_dict([wtask("a", scope=["."])], workdir=repo)
        spec_path = self._spec_json(raw)
        code = runner.main(["prepare", str(spec_path)])
        self.assertEqual(code, 0)
        run_dir = self._only_run_dir()
        self.assertTrue(run_dir.is_relative_to(self._tmp_root))
        self.assertTrue((run_dir / "summary.json").exists())
        self.assertTrue(run_dir.name.startswith("wt-"))

    def test_prepare_writes_worktree_and_prompt(self):
        repo = self._mk_repo()
        raw = write_spec_dict([wtask("a", prompt="改文件 X", scope=["."])],
                              workdir=repo)
        code = runner.main(["prepare", str(self._spec_json(raw))])
        self.assertEqual(code, 0)
        run_dir = self._only_run_dir()
        self.assertTrue((run_dir / "wt" / "a").is_dir())
        prompt_txt = (run_dir / "tasks" / "a" / "prompt.txt").read_text(
            encoding="utf-8")
        self.assertIn("改文件 X", prompt_txt)

    def test_prepare_non_git_workdir_exit_1(self):
        plain = self._mk_tempdir("dynwf-nogit-")
        raw = write_spec_dict([wtask("a")], workdir=plain)
        code = runner.main(["prepare", str(self._spec_json(raw))])
        self.assertEqual(code, 1)
        self.assertFalse(self._tmp_root.exists()
                         and any(self._tmp_root.iterdir()))

    def test_prepare_dirty_repo_default_rejected(self):
        repo = self._mk_repo()
        (repo / "dirty.txt").write_text("WIP", encoding="utf-8")  # 未提交改动
        raw = write_spec_dict([wtask("a")], workdir=repo)
        code = runner.main(["prepare", str(self._spec_json(raw))])
        self.assertEqual(code, 1)

    def test_prepare_dirty_repo_allow_dirty_ok(self):
        repo = self._mk_repo()
        (repo / "dirty.txt").write_text("WIP", encoding="utf-8")
        raw = write_spec_dict([wtask("a", scope=["."])], workdir=repo)
        code = runner.main(["prepare", str(self._spec_json(raw)), "--allow-dirty"])
        self.assertEqual(code, 0)

    def test_prepare_too_many_tasks_exit_1(self):
        repo = self._mk_repo()
        tasks = [wtask("t%d" % i) for i in range(9)]  # 9 > HARD_MAX_WRITE_TASKS=8
        raw = write_spec_dict(tasks, workdir=repo)
        code = runner.main(["prepare", str(self._spec_json(raw))])
        self.assertEqual(code, 1)

    def test_prepare_missing_spec_file_exit_1(self):
        code = runner.main(["prepare", r"D:\不存在的-spec-xyz.json"])
        self.assertEqual(code, 1)

    def test_prepare_leftover_worktree_rejected(self):
        """红线:仓库已有本工具的遗留副本(WRITE_RUNS_ROOT 下)→ prepare 拒、不留新 run_dir。"""
        repo = self._mk_repo()
        base = runner._git_head(str(repo))
        leftover = self._tmp_root / "old-run" / "wt" / "x"
        leftover.parent.mkdir(parents=True, exist_ok=True)
        runner._git_worktree_add(str(repo), leftover, base)
        raw = write_spec_dict([wtask("a", scope=["."])], workdir=repo)
        code = runner.main(["prepare", str(self._spec_json(raw))])
        self.assertEqual(code, 1)
        # 不留新 run_dir:WRITE_RUNS_ROOT 下只有那个遗留的 old-run
        kids = sorted(p.name for p in self._tmp_root.iterdir() if p.is_dir())
        self.assertEqual(kids, ["old-run"])


class TestDispatchSubcommand(WriteCliBase):
    def _prepared(self, tasks):
        repo = self._mk_repo()
        raw = write_spec_dict(tasks, workdir=repo)
        self.assertEqual(runner.main(["prepare", str(self._spec_json(raw))]), 0)
        return self._only_run_dir()

    def test_dispatch_runs_mock_and_returns_0(self):
        run_dir = self._prepared([wtask("a", prompt="[MOCK:writes=a.txt] 改",
                                        scope=["."])])
        code = runner.main(["dispatch", str(run_dir), "a",
                            "--codex-cmd", sys.executable, "--codex-cmd", MOCK])
        self.assertEqual(code, 0)
        self.assertTrue((run_dir / "wt" / "a" / "a.txt").exists())

    def test_dispatch_unknown_task_id_exit_1(self):
        run_dir = self._prepared([wtask("a")])
        code = runner.main(["dispatch", str(run_dir), "nope",
                            "--codex-cmd", sys.executable, "--codex-cmd", MOCK])
        self.assertEqual(code, 1)

    def test_dispatch_passes_through_codex_nonzero(self):
        run_dir = self._prepared([wtask("a", prompt="[MOCK:exit=3] 改")])
        code = runner.main(["dispatch", str(run_dir), "a",
                            "--codex-cmd", sys.executable, "--codex-cmd", MOCK])
        self.assertEqual(code, 1)  # codex 非 0 → CLI 失败码 1

    def test_dispatch_codex_cmd_rejected_in_production(self):
        # 生产模式(无 DYNWF_TEST_MODE)拒绝 --codex-cmd:写命令必须定死,不接受任意前缀
        run_dir = self._prepared([wtask("a", prompt="改", scope=["."])])
        os.environ.pop("DYNWF_TEST_MODE", None)
        code = runner.main(["dispatch", str(run_dir), "a",
                            "--codex-cmd", sys.executable, "--codex-cmd", MOCK])
        self.assertEqual(code, 1)


class TestCollectSubcommand(WriteCliBase):
    def _prepare_dispatch(self, tasks):
        repo = self._mk_repo()
        raw = write_spec_dict(tasks, workdir=repo)
        self.assertEqual(runner.main(["prepare", str(self._spec_json(raw))]), 0)
        run_dir = self._only_run_dir()
        for t in tasks:
            runner.main(["dispatch", str(run_dir), t["id"],
                         "--codex-cmd", sys.executable, "--codex-cmd", MOCK])
        return repo, run_dir

    def test_collect_clean_exit_0(self):
        _, run_dir = self._prepare_dispatch(
            [wtask("a", prompt="[MOCK:writes=a.txt] 改", scope=["."])])
        code = runner.main(["collect", str(run_dir)])
        self.assertEqual(code, 0)
        summary = json.loads((run_dir / "summary.json").read_text(
            encoding="utf-8"))
        self.assertTrue(summary["clean"])

    def test_collect_overlap_not_clean_exit_2(self):
        _, run_dir = self._prepare_dispatch([
            wtask("a", prompt="[MOCK:writes=same.txt] 改 A", scope=["."]),
            wtask("b", prompt="[MOCK:writes=same.txt] 改 B", scope=["."]),
        ])
        code = runner.main(["collect", str(run_dir)])
        self.assertEqual(code, 2)
        summary = json.loads((run_dir / "summary.json").read_text(
            encoding="utf-8"))
        self.assertFalse(summary["clean"])
        self.assertIn("same.txt", summary["overlaps"])

    def test_collect_main_drift_exit_2(self):
        # prepare+dispatch 后主仓库新提交 → main_drift → clean false → 退出码 2
        repo, run_dir = self._prepare_dispatch(
            [wtask("a", prompt="[MOCK:writes=a.txt] 改", scope=["."])])
        (repo / "drift.txt").write_text("x", encoding="utf-8")
        runner._run_git(["git", "-C", str(repo), "add", "-A"])
        runner._run_git(["git", "-C", str(repo), "commit", "-m", "drift"])
        code = runner.main(["collect", str(run_dir)])
        self.assertEqual(code, 2)
        summary = json.loads((run_dir / "summary.json").read_text(
            encoding="utf-8"))
        self.assertTrue(summary["main_drift"])

    def test_collect_bad_run_dir_exit_1(self):
        bogus = self._mk_tempdir("dynwf-bogus-")
        code = runner.main(["collect", str(bogus)])
        self.assertEqual(code, 1)


class TestReadModeBackCompat(_TempTracking):
    """无子命令(python runner.py <spec>)仍走读模式 run_workflow,退出码不受写模式影响。"""

    def _cli_read(self, raw, *extra):
        spec_path = self._spec_json(raw, prefix="dynwf-rcli-")
        runs_root = spec_path.parent / "runs"
        runs_root.mkdir(exist_ok=True)
        os.environ["DYNWF_RUNS_ROOT"] = str(runs_root)
        self.addCleanup(os.environ.pop, "DYNWF_RUNS_ROOT", None)
        run_dir = runs_root / "run"
        argv = [str(spec_path), "--run-dir", str(run_dir),
                "--codex-cmd", sys.executable, "--codex-cmd", MOCK,
                "--timeout-override", "5"]
        argv += list(extra)
        return runner.main(argv), run_dir

    def test_read_mode_all_ok_exit_0(self):
        code, run_dir = self._cli_read(spec_dict([stage("s1", task("a"))]))
        self.assertEqual(code, 0)
        self.assertTrue((run_dir / "summary.json").exists())

    def test_read_mode_partial_fail_exit_2(self):
        raw = spec_dict([stage("s1", task("a"),
                               task("b", prompt="[MOCK:exit=3] 干活"))])
        code, _ = self._cli_read(raw)
        self.assertEqual(code, 2)

    def test_read_mode_invalid_spec_exit_1(self):
        raw = spec_dict([stage("s1", task("a"))])
        raw["sandbox"] = "danger-full-access"  # 未知字段 → 读模式校验拒
        code, _ = self._cli_read(raw)
        self.assertEqual(code, 1)


class TestSubcommandArgErrors(WriteCliBase):
    def test_prepare_without_spec_arg_exit_1(self):
        try:
            code = runner.main(["prepare"])
        except SystemExit as e:
            self.assertNotEqual(e.code, 0)
        else:
            self.assertEqual(code, 1)

    def test_dispatch_without_task_id_exit_1(self):
        try:
            code = runner.main(["dispatch", r"D:\some\run"])
        except SystemExit as e:
            self.assertNotEqual(e.code, 0)
        else:
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
