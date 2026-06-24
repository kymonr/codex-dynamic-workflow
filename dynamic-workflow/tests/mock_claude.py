# -*- coding: utf-8 -*-
"""测试替身:模拟 `claude -p --output-format json`,绝不联网。
解析 argv 取 --json-schema 与 prompt(-- 之后),把结果信封打到 stdout。
prompt 里的指令控制行为:
  [MOCK:exit=N]   以退出码 N 退出
  [MOCK:iserror]  信封 is_error=true
  [MOCK:badjson]  stdout 打印非法 JSON
  [MOCK:empty]    stdout 不打印任何东西(空)
  [MOCK:tokens=N] 信封 usage.output_tokens=N(默认 7)
  [MOCK:cwdfile]  在当前工作目录(cwd)下写 claude_cwd_marker.txt(验证 cwd 生效)
默认:带 --json-schema 时信封含 structured_output={"echo":<prompt>};否则 result="ECHO:"+prompt。
"""
import json
import os
import re
import sys
from pathlib import Path


def main():
    # Windows: 强制 stdout 使用 UTF-8,避免默认 GBK 乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    argv = sys.argv[1:]
    schema = None
    prompt = ""
    for i, a in enumerate(argv):
        if a == "--json-schema":
            schema = argv[i + 1]
        elif a == "--":
            prompt = argv[i + 1] if i + 1 < len(argv) else ""
            break

    if "[MOCK:cwdfile]" in prompt:
        try:
            (Path(os.getcwd()) / "claude_cwd_marker.txt").write_text(
                "here", encoding="utf-8")
        except OSError:
            pass

    m = re.search(r"\[MOCK:exit=(\d+)\]", prompt)
    exit_code = int(m.group(1)) if m else 0

    if "[MOCK:empty]" in prompt:
        sys.exit(exit_code)
    if "[MOCK:badjson]" in prompt:
        sys.stdout.write("{不是合法JSON")
        sys.exit(exit_code)

    tok = 7
    m = re.search(r"\[MOCK:tokens=(\d+)\]", prompt)
    if m:
        tok = int(m.group(1))

    env = {"type": "result", "subtype": "success",
           "is_error": "[MOCK:iserror]" in prompt,
           "result": "ECHO:" + prompt,
           "usage": {"output_tokens": tok}}
    if schema is not None:
        env["structured_output"] = {"echo": prompt}
    sys.stdout.write(json.dumps(env, ensure_ascii=False))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
