# -*- coding: utf-8 -*-
import unittest

from helpers import runner, spec_dict, stage, task


class TestValidateSpec(unittest.TestCase):
    def test_minimal_valid_fills_defaults(self):
        spec = runner.validate_spec(spec_dict([stage("s1", task("a"))]))
        self.assertEqual(spec["max_concurrency"], 2)
        self.assertEqual(spec["timeout_seconds"], 900)
        self.assertEqual(spec["stages"][0]["tasks"][0]["id"], "a")

    def test_unknown_top_key_rejected(self):
        d = spec_dict([stage("s1", task("a"))])
        d["sandbox"] = "danger-full-access"
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_unknown_task_key_rejected(self):
        d = spec_dict([stage("s1", task("a", extra_args=["--full-auto"]))])
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_duplicate_task_ids_rejected(self):
        d = spec_dict([stage("s1", task("a"), task("a"))])
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_duplicate_task_ids_case_insensitive_rejected(self):
        d = spec_dict([stage("s1", task("a"), task("A"))])
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_placeholder_must_reference_earlier_stage(self):
        same = spec_dict([stage("s1", task("a"), task("b", prompt="看 {{result:a}}"))])
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(same)
        earlier = spec_dict([stage("s1", task("a")),
                             stage("s2", task("b", prompt="看 {{result:a}}"))])
        runner.validate_spec(earlier)  # 不应抛错

    def test_concurrency_bounds(self):
        d = spec_dict([stage("s1", task("a"))], max_concurrency=5)
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_timeout_bounds(self):
        d = spec_dict([stage("s1", task("a"))], timeout_seconds=10)
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_agent_total_cap(self):
        tasks = [task("t%d" % i) for i in range(13)]
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(spec_dict([stage("s1", *tasks)]))

    def test_workdir_must_exist(self):
        d = spec_dict([stage("s1", task("a"))], workdir=r"D:\不存在的目录-dynwf-test")
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_bad_effort_rejected(self):
        d = spec_dict([stage("s1", task("a", reasoning_effort="max"))])
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_model_key_rejected(self):
        d = spec_dict([stage("s1", task("a", model="gpt-x"))])
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_prompt_too_long_rejected(self):
        d = spec_dict([stage("s1", task("a", prompt="x" * 20001))])
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_version_bool_rejected(self):
        d = spec_dict([stage("s1", task("a"))])
        d["version"] = True            # JSON true 不能冒充整数 1
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_workdir_home_rejected(self):
        import pathlib
        d = spec_dict([stage("s1", task("a"))], workdir=str(pathlib.Path.home()))
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_workdir_under_codex_rejected(self):
        import pathlib
        sub = pathlib.Path.home() / ".codex" / "skills"
        if not sub.is_dir():
            self.skipTest("本机无 ~/.codex/skills,跳过敏感子目录用例")
        # 敏感目录的子目录也要拒,不能只拦 .codex 本层
        d = spec_dict([stage("s1", task("a"))], workdir=str(sub))
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)

    def test_task_id_windows_reserved_rejected(self):
        # CON/NUL 等会拿去 mkdir,Windows 上必失败,必须在校验期拦下
        for bad in ("CON", "nul", "Com1", "LPT9"):
            d = spec_dict([stage("s1", task(bad))])
            with self.assertRaises(runner.SpecError):
                runner.validate_spec(d)


if __name__ == "__main__":
    unittest.main()
