# -*- coding: utf-8 -*-
"""测试替身:模拟 `codex exec`,绝不联网。
通过 prompt 里的指令控制行为:
  [MOCK:sleep=0.5]  启动后睡 0.5 秒
  [MOCK:exit=3]     不写输出文件,以退出码 3 退出
  [MOCK:badjson]    写入非法 JSON
  [MOCK:tokens=42]  向 stdout 打印一行用量 footer(模拟 codex 的 token 用量输出)
默认:带 --output-schema 时写 {"echo": <prompt>},否则写 "ECHO:<prompt>"。
无论成败都写 <out>.times 记录起止时间,供并发测试统计重叠。
"""
import json
import re
import sys
import time
from pathlib import Path


def main():
    argv = sys.argv[1:]          # 形如: exec -s read-only ... -o <out> ... <prompt>
    out = schema = None
    for i, a in enumerate(argv):
        if a == "-o":
            out = argv[i + 1]
        elif a == "--output-schema":
            schema = argv[i + 1]
    prompt = argv[-1]

    start = time.time()
    m = re.search(r"\[MOCK:sleep=([0-9.]+)\]", prompt)
    if m:
        time.sleep(float(m.group(1)))
    exit_code = 0
    m = re.search(r"\[MOCK:exit=(\d+)\]", prompt)
    if m:
        exit_code = int(m.group(1))
    end = time.time()

    if out:
        Path(out + ".times").write_text(
            json.dumps({"start": start, "end": end}), encoding="utf-8")
        if exit_code == 0:
            if "[MOCK:badjson]" in prompt:
                Path(out).write_text("{这不是JSON", encoding="utf-8")
            elif schema:
                Path(out).write_text(
                    json.dumps({"echo": prompt}, ensure_ascii=False), encoding="utf-8")
            else:
                Path(out).write_text("ECHO:" + prompt, encoding="utf-8")
    # 模拟 codex 把用量 footer 打到 stdout(runner 会把它重定向进 agent.log)
    m = re.search(r"\[MOCK:tokens=(\d+)\]", prompt)
    if m:
        print("tokens used: %s" % m.group(1))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
