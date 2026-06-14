# -*- coding: utf-8 -*-
"""测试替身:模拟 `codex exec`,绝不联网。
通过 prompt 里的指令控制行为:
  [MOCK:sleep=0.5]          启动后睡 0.5 秒
  [MOCK:exit=3]             不写输出文件,以退出码 3 退出
  [MOCK:badjson]            写入非法 JSON
  [MOCK:tokens=42]          向 stdout 打印一行用量 footer(模拟 codex 的 token 用量输出)
  [MOCK:writes=a.txt,b/c]   在 -C 指定的工作目录下建/改这些文件(写点内容);写模式用
  [MOCK:stage]              在 -C 工作目录只跑 git add -A(模拟偷偷暂存、未 commit)
  [MOCK:commit]             在 -C 工作目录额外跑 git add -A + git commit -m mock(模拟偷偷 commit)
默认:带 --output-schema 时写 {"echo": <prompt>},否则写 "ECHO:<prompt>"。
无论成败都写 <out>.times 记录起止时间,供并发测试统计重叠。
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path


def main():
    argv = sys.argv[1:]          # 读模式: exec -s read-only ... -o <out> ... <prompt>
    #                              写模式: exec -s workspace-write ... -C <wt> ... -- <prompt>
    out = schema = workdir = None
    for i, a in enumerate(argv):
        if a == "-o":
            out = argv[i + 1]
        elif a == "--output-schema":
            schema = argv[i + 1]
        elif a == "-C":
            workdir = argv[i + 1]
    prompt = argv[-1]

    start = time.time()
    m = re.search(r"\[MOCK:sleep=([0-9.]+)\]", prompt)
    if m:
        time.sleep(float(m.group(1)))
    exit_code = 0
    m = re.search(r"\[MOCK:exit=(\d+)\]", prompt)
    if m:
        exit_code = int(m.group(1))

    # 写模式:在 -C 指定的副本目录里真建/改文件(独立于 -o 输出文件)
    if workdir and exit_code == 0:
        m = re.search(r"\[MOCK:writes=([^\]]+)\]", prompt)
        if m:
            base = Path(workdir)
            for rel in m.group(1).split(","):
                rel = rel.strip()
                if not rel:
                    continue
                target = base / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("mock change for %s\n" % rel, encoding="utf-8")
        if "[MOCK:stage]" in prompt and "[MOCK:commit]" not in prompt:
            # 模拟子代理偷偷 git add(暂存未提交),让 collect 的 index_changed 能抓到
            subprocess.run(["git", "-C", workdir, "add", "-A"],
                           capture_output=True, text=True)
        if "[MOCK:commit]" in prompt:
            # 模拟子代理偷偷 commit:在副本里 add + commit,让 collect 能看出 HEAD 变化
            subprocess.run(["git", "-C", workdir, "add", "-A"],
                           capture_output=True, text=True)
            subprocess.run(["git", "-C", workdir, "commit", "-m", "mock"],
                           capture_output=True, text=True)

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
