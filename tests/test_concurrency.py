# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path

from helpers import run_wf, spec_dict, stage, task


class TestConcurrencyCap(unittest.TestCase):
    def test_cap_two_honored(self):
        tasks = [task("t%d" % i, prompt="[MOCK:sleep=0.6] 任务%d" % i)
                 for i in range(5)]
        raw = spec_dict([stage("s1", *tasks)], max_concurrency=2)
        s, _ = run_wf(raw)
        self.assertEqual(s["ok"], 5)
        windows = []
        for t in s["tasks"]:
            tf = Path(t["task_dir"]) / "out.txt.times"
            windows.append(json.loads(tf.read_text(encoding="utf-8")))
        events = []
        for w in windows:
            events.append((w["start"], 1))
            events.append((w["end"], -1))
        # 同一时刻先处理 start(+1) 再 end(-1):宁可高估并发,也不漏报"瞬间超并发"
        events.sort(key=lambda e: (e[0], -e[1]))
        cur = peak = 0
        for _, d in events:
            cur += d
            peak = max(peak, cur)
        self.assertLessEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()
