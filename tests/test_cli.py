# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import runner, spec_dict, stage, task, ROOT


def write_spec(raw):
    p = Path(tempfile.mkdtemp(prefix="dynwf-cli-")) / "spec.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return p


def cli(raw, *extra):
    spec_path = write_spec(raw)
    # 把运行根指到本测试的临时目录,这样 --run-dir 能通过 runner 的"必须在根下"包含检查
    runs_root = spec_path.parent / "runs"
    runs_root.mkdir(exist_ok=True)
    os.environ["DYNWF_RUNS_ROOT"] = str(runs_root)
    run_dir = runs_root / "run"
    mock = str(ROOT / "tests" / "mock_codex.py")
    argv = [str(spec_path), "--run-dir", str(run_dir),
            "--codex-cmd", sys.executable, "--codex-cmd", mock,
            "--timeout-override", "5"]
    argv += list(extra)
    return runner.main(argv), run_dir


class TestCli(unittest.TestCase):
    def test_all_ok_exit_0(self):
        code, run_dir = cli(spec_dict([stage("s1", task("a"))]))
        self.assertEqual(code, 0)
        self.assertTrue((run_dir / "summary.json").exists())

    def test_partial_fail_exit_2(self):
        raw = spec_dict([stage("s1", task("a"),
                               task("b", prompt="[MOCK:exit=3] 干活"))])
        code, _ = cli(raw)
        self.assertEqual(code, 2)

    def test_invalid_spec_exit_1(self):
        raw = spec_dict([stage("s1", task("a"))])
        raw["sandbox"] = "danger-full-access"
        code, _ = cli(raw)
        self.assertEqual(code, 1)

    def test_timeout_override_out_of_range_exit_1(self):
        # argparse 同名参数后者生效:基础 argv 里的 5 被 9999 覆盖
        code, _ = cli(spec_dict([stage("s1", task("a"))]),
                      "--timeout-override", "9999")
        self.assertEqual(code, 1)

    def test_run_dir_outside_root_exit_1(self):
        spec_path = write_spec(spec_dict([stage("s1", task("a"))]))
        runs_root = spec_path.parent / "runs"
        runs_root.mkdir(exist_ok=True)
        os.environ["DYNWF_RUNS_ROOT"] = str(runs_root)
        mock = str(ROOT / "tests" / "mock_codex.py")
        # run-dir 指到运行根之外(spec 同级的 evil),应被拒、exit 1
        argv = [str(spec_path), "--run-dir", str(spec_path.parent / "evil"),
                "--codex-cmd", sys.executable, "--codex-cmd", mock]
        self.assertEqual(runner.main(argv), 1)

    def test_run_dir_in_production_rejected(self):
        os.environ.pop("DYNWF_RUNS_ROOT", None)   # 模拟生产:未设运行根
        spec_path = write_spec(spec_dict([stage("s1", task("a"))]))
        mock = str(ROOT / "tests" / "mock_codex.py")
        # 生产模式不接受 --run-dir(避免越界/junction),应被拒、exit 1
        argv = [str(spec_path), "--run-dir", str(spec_path.parent / "run"),
                "--codex-cmd", sys.executable, "--codex-cmd", mock]
        self.assertEqual(runner.main(argv), 1)


if __name__ == "__main__":
    unittest.main()
