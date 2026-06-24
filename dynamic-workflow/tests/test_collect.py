# -*- coding: utf-8 -*-
"""写模式 collect 测试:prepare -> dispatch(mock 写文件) -> collect,全离线。
覆盖:patch 非空 + untracked + status=ok;空改动 -> no_changes;
两块撞同一文件 -> overlaps + clean=false;[MOCK:commit] -> head_changed + clean=false;
scope 外改动 -> out_of_scope 非空且 clean=false;run-dir 归属/骨架校验。
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import make_git_repo, write_spec_dict, wtask

runner = helpers.runner
MOCK_PREFIX = helpers.MOCK_PREFIX


def _prepare_run(spec_raw, *, allow_dirty=False):
    """validate -> 在 WRITE_RUNS_ROOT 下真实建 run-dir(prepare),返回 run_dir Path。"""
    spec = runner.validate_write_spec(spec_raw)
    stamp = "test-%s" % os.getpid()
    run_dir = runner.WRITE_RUNS_ROOT / ("collect-%s-%s" % (stamp, os.urandom(3).hex()))
    runner.prepare(spec, run_dir, allow_dirty=allow_dirty)
    return run_dir


def _dispatch_all(run_dir):
    """对骨架里每个 task 跑一次 dispatch(用 mock 替身),返回各任务 exit_code。"""
    skel = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    codes = {}
    for t in skel["tasks"]:
        res = runner.dispatch(run_dir, t["id"], MOCK_PREFIX)
        codes[t["id"]] = res["exit_code"]
    return codes


class CollectBase(unittest.TestCase):
    def setUp(self):
        self.repo = make_git_repo()
        # 把 WRITE_RUNS_ROOT monkeypatch 到临时目录,不写真实 D:\.codex-tmp、跑完即清
        self._orig_root = runner.WRITE_RUNS_ROOT
        self._root_parent = Path(tempfile.mkdtemp(prefix="dynwf-collectroot-"))
        runner.WRITE_RUNS_ROOT = self._root_parent / "workflows"
        self._run_dirs = []

    def tearDown(self):
        # 先用 git 把每个副本摘掉(避免 worktree 元数据残留),再还原根、删临时根与仓库
        for rd in self._run_dirs:
            try:
                skel_p = rd / "summary.json"
                if skel_p.exists():
                    skel = json.loads(skel_p.read_text(encoding="utf-8"))
                    for t in skel.get("tasks", []):
                        wt = t.get("worktree")
                        if wt:
                            runner._git_worktree_remove(skel["workdir"], wt)
                    runner._git_worktree_prune(skel["workdir"])
            except Exception:
                pass
        runner.WRITE_RUNS_ROOT = self._orig_root
        helpers.rmtree(self._root_parent)
        helpers.rmtree(self.repo)  # Windows 友好 rmtree:清只读 git 对象,临时仓库不残留

    def _prepare(self, spec_raw, *, allow_dirty=False):
        rd = _prepare_run(spec_raw, allow_dirty=allow_dirty)
        self._run_dirs.append(rd)
        return rd


class TestCollectHappyPath(CollectBase):
    def test_writes_produce_patch_untracked_and_ok(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改文件 [MOCK:writes=a.txt]")],
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)

        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "ok")
        # changes.patch 落盘且非空(a.txt 是 mock 新建的未跟踪文件,体现在 untracked)
        patch_p = rd / "tasks" / "a" / "changes.patch"
        self.assertTrue(patch_p.exists())
        self.assertIn("a.txt", ta["untracked_files"])
        self.assertFalse(ta["head_changed"])
        self.assertEqual(ta["out_of_scope"], [])

    def test_no_changes_when_task_writes_nothing(self):
        spec = write_spec_dict(
            [wtask("idle", prompt="什么都不写")],  # 不带 [MOCK:writes]
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)

        t = next(t for t in summary["tasks"] if t["id"] == "idle")
        self.assertEqual(t["status"], "no_changes")
        self.assertTrue(summary["clean"])


class TestCollectConflicts(CollectBase):
    def test_two_tasks_same_file_overlaps_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=shared.txt]"),
             wtask("b", prompt="改 [MOCK:writes=shared.txt]")],
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)

        self.assertIn("shared.txt", summary["overlaps"])
        self.assertFalse(summary["clean"])

    def test_secret_commit_marks_head_changed_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改并提交 [MOCK:writes=c.txt] [MOCK:commit]")],
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)

        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertTrue(ta["head_changed"])
        self.assertFalse(summary["clean"])
        # commit 后改动是已跟踪的,diff --binary 仍能拿到(patch 非空)
        patch_p = rd / "tasks" / "a" / "changes.patch"
        self.assertTrue(patch_p.read_text(encoding="utf-8").strip())


class TestCollectScope(CollectBase):
    def test_out_of_scope_marks_not_clean(self):
        # scope 限定 src,但 mock 在副本根写 outside.txt(落在 src 外)→ 越界 → clean=false
        # (CLAUDE.md:清单外的新增/产物文件一律判不通过;scope 不阻止写,但 collect 拦集成)
        spec = write_spec_dict(
            [wtask("a", prompt="越界 [MOCK:writes=outside.txt]", scope=["src"])],
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)

        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertIn("outside.txt", ta["out_of_scope"])
        self.assertFalse(summary["clean"])

    def test_scope_dot_means_whole_repo_no_violation(self):
        # scope=["."] 表示整个仓库根,任何改动都不算越界 → clean 仍 true
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=deep/x.txt]", scope=["."])],
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)

        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["out_of_scope"], [])
        self.assertTrue(summary["clean"])


class TestCollectGuards(CollectBase):
    def test_run_dir_outside_write_root_rejected(self):
        # 用一个不在 WRITE_RUNS_ROOT 下的临时目录(带伪骨架)应被拒
        import tempfile
        bogus = Path(tempfile.mkdtemp(prefix="bogus-collect-"))
        try:
            (bogus / "summary.json").write_text(
                json.dumps({"base_head": "x", "workdir": str(self.repo),
                            "mode": "write", "tasks": []}),
                encoding="utf-8")
            with self.assertRaises(runner.WorkflowError):
                runner.collect(bogus)
        finally:
            shutil.rmtree(bogus, ignore_errors=True)

    def test_missing_skeleton_rejected(self):
        # 在 WRITE_RUNS_ROOT 下建一个没有 summary.json 的目录
        d = runner.WRITE_RUNS_ROOT / ("noskel-%s" % os.urandom(3).hex())
        d.mkdir(parents=True, exist_ok=True)
        try:
            with self.assertRaises(runner.WorkflowError):
                runner.collect(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_malformed_task_entry_rejected(self):
        # 骨架的 task 条目缺 worktree → WorkflowError(而非 collect 直接下标裸 KeyError)
        d = runner.WRITE_RUNS_ROOT / ("malformed-%s" % os.urandom(3).hex())
        d.mkdir(parents=True, exist_ok=True)
        try:
            (d / "summary.json").write_text(json.dumps({
                "mode": "write", "base_head": "abc", "workdir": str(self.repo),
                "tasks": [{"id": "a"}],  # 缺 worktree
            }), encoding="utf-8")
            with self.assertRaises(runner.WorkflowError):
                runner.collect(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_worktree_outside_run_dir_wt_marks_error_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        skel_p = rd / "summary.json"
        skel = json.loads(skel_p.read_text(encoding="utf-8"))
        original_wt = skel["tasks"][0]["worktree"]
        skel["tasks"][0]["worktree"] = str(self.repo)
        skel_p.write_text(json.dumps(skel, ensure_ascii=False), encoding="utf-8")
        try:
            summary = runner.collect(rd)
            ta = next(t for t in summary["tasks"] if t["id"] == "a")
            self.assertEqual(ta["status"], "error")
            self.assertIn("wt/", ta["error"])
            self.assertFalse(summary["clean"])
        finally:
            skel["tasks"][0]["worktree"] = original_wt
            skel_p.write_text(json.dumps(skel, ensure_ascii=False), encoding="utf-8")


class TestCollectDrift(CollectBase):
    """主仓库自基线以来漂移 → main_drift True、clean False(红线:集成前主 HEAD/status 须一致)。"""

    def test_main_repo_new_commit_marks_drift_not_clean(self):
        # 覆盖 OR 子句一:HEAD 变(prepare 后主仓库新提交)
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        (self.repo / "newfile.txt").write_text("x", encoding="utf-8")
        runner._run_git(["git", "-C", str(self.repo), "add", "-A"])
        runner._run_git(["git", "-C", str(self.repo), "commit", "-m", "drift"])
        summary = runner.collect(rd)
        self.assertTrue(summary["main_drift"])
        self.assertFalse(summary["clean"])

    def test_main_repo_dirty_worktree_marks_drift_not_clean(self):
        # 覆盖 OR 子句二:HEAD 不变、只弄脏主仓库工作树(status 变 != status_raw)
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        (self.repo / "dirty-after.txt").write_text("WIP", encoding="utf-8")
        summary = runner.collect(rd)
        self.assertTrue(summary["main_drift"])
        self.assertFalse(summary["clean"])


class TestCollectError(CollectBase):
    """副本缺失/损坏 → 该块 status='error'、clean False(设计 §9 错误处理,非误判 no_changes)。"""

    def test_missing_worktree_copy_marks_error_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        skel = json.loads((rd / "summary.json").read_text(encoding="utf-8"))
        wt = skel["tasks"][0]["worktree"]
        # 注销并物理删掉副本,模拟「副本损坏/丢失」
        runner._git_worktree_remove(self.repo, wt)
        runner._git_worktree_prune(self.repo)
        shutil.rmtree(wt, ignore_errors=True)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "error")  # 不是 no_changes
        self.assertFalse(summary["clean"])


class TestCollectTrackedFile(CollectBase):
    """覆写已跟踪文件 → changes.patch 非空、含新内容(纯新增文件 patch 为空之外的真实路径)。"""

    def test_tracked_file_modification_produces_nonempty_patch(self):
        # seed.txt 由 make_git_repo 已提交;mock 覆写它 → 已跟踪改动进 git diff
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=seed.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "ok")
        self.assertIn("seed.txt", ta["touched_files"])
        patch = (rd / "tasks" / "a" / "changes.patch").read_text(encoding="utf-8")
        self.assertTrue(patch.strip())  # 已跟踪改动的 patch 非空
        self.assertIn("mock change for seed.txt", patch)  # 含新内容

    def test_tracked_file_out_of_scope_marks_not_clean(self):
        # 覆写已跟踪 seed.txt 但 scope 限定 src → seed.txt 越界(覆盖 out_of_scope 的 changed 半边)
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=seed.txt]", scope=["src"])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertIn("seed.txt", ta["out_of_scope"])
        self.assertFalse(summary["clean"])  # 越界改动让 collect 判 not clean


class TestCollectUntrackedBundle(CollectBase):
    """未跟踪新文件内容应被镜像进 tasks/<id>/untracked/(设计 §6/§7:打包未跟踪内容)。"""

    def test_untracked_content_bundled(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=newdir/n.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        bundled = rd / "tasks" / "a" / "untracked" / "newdir" / "n.txt"
        self.assertTrue(bundled.is_file())
        self.assertEqual(bundled.read_text(encoding="utf-8"),
                         "mock change for newdir/n.txt\n")
        recs = {r["file"]: r for r in ta["untracked_bundle"]}
        self.assertTrue(recs["newdir/n.txt"]["bundled"])

    def test_ignored_only_output_marks_not_clean(self):
        (self.repo / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
        runner._run_git(["git", "-C", str(self.repo), "add", ".gitignore"])
        runner._run_git(["git", "-C", str(self.repo), "commit", "-m", "ignore"])
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=ignored.log]", scope=["."])],
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "ok")
        self.assertEqual(ta["untracked_files"], [])
        self.assertIn("ignored.log", ta["ignored_files"])
        self.assertFalse(summary["clean"])


class TestCollectDispatchState(CollectBase):
    """collect 必须反映派工真相:没派工 / 派工失败 / 偷偷 git add 都不得判 clean。"""

    def test_collect_without_dispatch_not_clean(self):
        # 只 prepare、不 dispatch,直接 collect → not_dispatched、clean false(不是假绿 no_changes)
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "not_dispatched")
        self.assertFalse(ta["dispatched"])
        self.assertFalse(summary["clean"])

    def test_dispatch_failure_marks_not_clean(self):
        # dispatch 以非 0 退出(codex 报错)→ dispatch_failed、clean false
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:exit=3]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "dispatch_failed")
        self.assertEqual(ta["dispatch_exit_code"], 3)
        self.assertFalse(summary["clean"])

    def test_dispatch_nonce_mismatch_marks_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        disp_p = rd / "tasks" / "a" / "dispatch.json"
        disp = json.loads(disp_p.read_text(encoding="utf-8"))
        disp["dispatch_nonce"] = "0" * 32
        disp_p.write_text(json.dumps(disp, ensure_ascii=False), encoding="utf-8")

        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "dispatch_failed")
        self.assertIn("dispatch_nonce", ta["dispatch_error"])
        self.assertFalse(summary["clean"])

    def test_prompt_hash_mismatch_marks_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        (rd / "tasks" / "a" / "prompt.txt").write_text(
            "篡改后的 prompt", encoding="utf-8")

        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "dispatch_failed")
        self.assertIn("prompt_sha256", ta["dispatch_error"])
        self.assertFalse(summary["clean"])

    def test_dispatch_json_prompt_hash_mismatch_marks_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        disp_p = rd / "tasks" / "a" / "dispatch.json"
        disp = json.loads(disp_p.read_text(encoding="utf-8"))
        disp["prompt_sha256"] = "0" * 64
        disp_p.write_text(json.dumps(disp, ensure_ascii=False), encoding="utf-8")

        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "dispatch_failed")
        self.assertIn("prompt_sha256", ta["dispatch_error"])
        self.assertFalse(summary["clean"])

    def test_dispatch_json_worktree_mismatch_marks_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        disp_p = rd / "tasks" / "a" / "dispatch.json"
        disp = json.loads(disp_p.read_text(encoding="utf-8"))
        disp["worktree"] = str(self.repo)
        disp_p.write_text(json.dumps(disp, ensure_ascii=False), encoding="utf-8")

        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "dispatch_failed")
        self.assertIn("worktree", ta["dispatch_error"])
        self.assertFalse(summary["clean"])

    def test_dispatch_json_base_head_mismatch_marks_not_clean(self):
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt]", scope=["."])], self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        disp_p = rd / "tasks" / "a" / "dispatch.json"
        disp = json.loads(disp_p.read_text(encoding="utf-8"))
        disp["base_head"] = "0" * 40
        disp_p.write_text(json.dumps(disp, ensure_ascii=False), encoding="utf-8")

        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertEqual(ta["status"], "dispatch_failed")
        self.assertIn("base_head", ta["dispatch_error"])
        self.assertFalse(summary["clean"])

    def test_staged_changes_marks_index_changed_not_clean(self):
        # 子代理偷偷 git add(暂存未提交)→ index_changed、clean false(CLAUDE.md 禁 git add)
        spec = write_spec_dict(
            [wtask("a", prompt="改 [MOCK:writes=a.txt] [MOCK:stage]", scope=["."])],
            self.repo)
        rd = self._prepare(spec)
        _dispatch_all(rd)
        summary = runner.collect(rd)
        ta = next(t for t in summary["tasks"] if t["id"] == "a")
        self.assertTrue(ta["index_changed"])
        self.assertFalse(summary["clean"])


if __name__ == "__main__":
    unittest.main()
