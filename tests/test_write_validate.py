# -*- coding: utf-8 -*-
"""Task 1: validate_write_spec —— 写模式 spec 白名单校验。全部离线,不联网。"""
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  把 src 加进 sys.path
import runner
from helpers import make_git_repo, write_spec_dict, wtask


class ValidateWriteSpecTest(unittest.TestCase):
    def setUp(self):
        # 正例:一个真实的临时 git 仓库当 workdir
        self.repo = make_git_repo()
        self._cleanup = [self.repo]

    def tearDown(self):
        for p in self._cleanup:
            helpers.rmtree(p)

    def _spec(self, tasks, **over):
        return write_spec_dict(tasks, self.repo, **over)

    # ---- 最小合法 + 默认归一化 ----
    def test_minimal_ok_fills_defaults(self):
        raw = self._spec([wtask("a")])
        out = runner.validate_write_spec(raw)
        self.assertEqual(out["version"], 1)
        self.assertEqual(out["mode"], "write")
        self.assertEqual(out["name"], "wt")
        self.assertEqual(out["workdir"], str(Path(self.repo).resolve()))
        self.assertEqual(len(out["tasks"]), 1)
        t = out["tasks"][0]
        self.assertEqual(t["id"], "a")
        self.assertEqual(t["prompt"], "改文件")
        # scope 缺省归一化为 []
        self.assertEqual(t["scope"], [])
        # reasoning_effort 缺省为 None
        self.assertIsNone(t["reasoning_effort"])

    def test_scope_and_effort_preserved(self):
        raw = self._spec([wtask("a", scope=["src/x", "docs"],
                                 reasoning_effort="high")])
        out = runner.validate_write_spec(raw)
        t = out["tasks"][0]
        self.assertEqual(t["scope"], ["src/x", "docs"])
        self.assertEqual(t["reasoning_effort"], "high")

    # ---- mode ----
    def test_mode_must_be_write(self):
        raw = self._spec([wtask("a")], mode="read")
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_mode_missing_rejected(self):
        raw = self._spec([wtask("a")])
        del raw["mode"]
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    # ---- 白名单:未知字段 ----
    def test_unknown_top_key_rejected(self):
        raw = self._spec([wtask("a")], max_concurrency=2)
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_unknown_task_key_rejected(self):
        raw = self._spec([wtask("a", output_schema={"type": "object"})])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_stages_key_rejected(self):
        # 写模式不允许 stages(它是读模式的键)
        raw = self._spec([wtask("a")], stages=[])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    # ---- version ----
    def test_version_must_be_int_one(self):
        raw = self._spec([wtask("a")], version=True)  # bool 不算 int 1
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)
        raw2 = self._spec([wtask("a")], version=2)
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw2)

    # ---- name ----
    def test_bad_name_rejected(self):
        raw = self._spec([wtask("a")], name="Bad_Name")  # 大写/下划线非法
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    # ---- tasks 列表 ----
    def test_empty_tasks_rejected(self):
        raw = self._spec([])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_tasks_not_list_rejected(self):
        raw = self._spec([wtask("a")])
        raw["tasks"] = {"id": "a"}
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_too_many_tasks_rejected(self):
        tasks = [wtask("t%d" % i) for i in range(runner.HARD_MAX_WRITE_TASKS + 1)]
        raw = self._spec(tasks)
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_exactly_max_tasks_ok(self):
        tasks = [wtask("t%d" % i) for i in range(runner.HARD_MAX_WRITE_TASKS)]
        raw = self._spec(tasks)
        out = runner.validate_write_spec(raw)
        self.assertEqual(len(out["tasks"]), runner.HARD_MAX_WRITE_TASKS)

    # ---- task id ----
    def test_duplicate_id_casefold_rejected(self):
        raw = self._spec([wtask("Mod"), wtask("mod")])  # casefold 撞
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_bad_id_rejected(self):
        raw = self._spec([wtask("has space")])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_win_reserved_id_rejected(self):
        raw = self._spec([wtask("CON")])  # Windows 保留设备名
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)
        raw2 = self._spec([wtask("com1")])  # 大小写不敏感
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw2)

    # ---- prompt ----
    def test_empty_prompt_rejected(self):
        raw = self._spec([wtask("a", prompt="   ")])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_prompt_too_long_rejected(self):
        raw = self._spec([wtask("a", prompt="x" * (runner.MAX_PROMPT_CHARS + 1))])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_prompt_with_placeholder_rejected(self):
        # 写模式无跨引用,prompt 含 {{result:x}} 直接拒
        raw = self._spec([wtask("a", prompt="改 {{result:b}} 的产物")])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_prompt_non_utf8_rejected(self):
        # lone surrogate 无法 UTF-8 编码,必须拒绝
        raw = write_spec_dict([wtask("a", prompt="x\ud800")], self.repo)
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    # ---- scope ----
    def test_scope_not_list_rejected(self):
        raw = self._spec([wtask("a", scope="src/x")])  # 必须是列表
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_scope_empty_list_rejected(self):
        # 若给 scope,必须非空列表;直接内联构造确保 scope:[] 真的出现在 dict 中
        raw = write_spec_dict([{"id": "a", "prompt": "改文件", "scope": []}], self.repo)
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_scope_with_empty_string_rejected(self):
        raw = self._spec([wtask("a", scope=["src/x", "  "])])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_scope_with_non_string_rejected(self):
        raw = self._spec([wtask("a", scope=["src/x", 3])])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    # ---- reasoning_effort ----
    def test_bad_effort_rejected(self):
        raw = self._spec([wtask("a", reasoning_effort="extreme")])
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    # ---- workdir ----
    def test_workdir_must_be_git_repo(self):
        # 反例:一个存在但不是 git 仓库的临时目录
        non_git = Path(tempfile.mkdtemp(prefix="dynwf-nongit-"))
        self._cleanup.append(non_git)
        raw = write_spec_dict([wtask("a")], non_git)
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(raw)

    def test_workdir_git_repo_ok(self):
        # 正例:make_git_repo 建的仓库通过(也回归覆盖 _is_git_repo 真路径)
        raw = self._spec([wtask("a")])
        out = runner.validate_write_spec(raw)
        self.assertEqual(out["workdir"], str(Path(self.repo).resolve()))

    def test_not_dict_rejected(self):
        with self.assertRaises(runner.SpecError):
            runner.validate_write_spec(["not", "a", "dict"])


if __name__ == "__main__":
    unittest.main()
