# Claude 读模式后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 dynamic-workflow 的读模式增加一个 `claude` 后端，与现有 `codex` 后端并列，默认仍走 codex。

**Architecture:** 单 `runner.py` 内部按 `backend` 分发。读 spec 新增可选 `backend` 字段，CLI 新增 `--backend` 覆盖。claude 读子代理用 `claude -p --output-format json --strict-mcp-config --tools "Read,Grep,Glob"`，靠工具集裁剪实现只读（非 OS 沙箱）；输出经 stdout 的 JSON 信封，由 runner 捕获解析。写模式（prepare/dispatch/collect）完全不动。

**Tech Stack:** Python 3 标准库（无第三方依赖）、unittest、Windows、claude CLI 2.1.183、codex CLI。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-06-19-claude-read-backend-design.md`（每个任务的需求隐含包含该 spec）。
- 测试框架是 **unittest**（非 pytest）。测试从 `tests/` 内用 `from helpers import ...` 导入。
- 所有运行命令在项目根 `D:\codex\codex-dynamic-workflow` 下执行。
- 改动只限 `src/runner.py` 与 `tests/`；**写模式逻辑（prepare/dispatch/collect/validate_write_spec/build_write_cmd）一行不改**。
- 后端命令一律白名单拼装、不透传任意参数（沿用现有安全原则）。
- claude 读工具集**硬编码** `Read,Grep,Glob`，spec/CLI 无法放开；不得加入 Bash/WebFetch/WebSearch。
- `MAX_PROMPT_CHARS = 20000`（现有，prompt 字符上限，verbatim 不改）。
- claude 内联 schema 后 argv 合计上限：`MAX_CLAUDE_ARGV_CHARS = 28000`。
- **git commit 需用户单独授权**（见 `D:\codex\CLAUDE.md`）。各任务末尾的 commit 步骤在执行阶段须先获用户确认，不得自动提交。
- 现有 codex 测试必须全程保持绿（回归）。
- 单文件测试运行模板：`python -m unittest discover -s tests -t tests -p "test_xxx.py" -v`
- 全量回归：`python -m unittest discover -s tests -t tests -v`

---

### Task 1: validate_spec 支持 backend 字段

**Files:**
- Modify: `src/runner.py`（`ALLOWED_SPEC_KEYS` 常量；新增 `BACKENDS`；`validate_spec` 函数）
- Test: `tests/test_validate.py`（追加用例）

**Interfaces:**
- Produces: `runner.BACKENDS = {"codex", "claude"}`；`validate_spec(raw, allowed_roots=None)` 返回的 dict 新增键 `"backend"`（值 `"codex"` 或 `"claude"`，缺省 `"codex"`）。

- [ ] **Step 1: 写失败测试**

在 `tests/test_validate.py` 的 `TestValidateSpec` 类内追加：

```python
    def test_backend_defaults_codex(self):
        spec = runner.validate_spec(spec_dict([stage("s1", task("a"))]))
        self.assertEqual(spec["backend"], "codex")

    def test_backend_claude_accepted(self):
        spec = runner.validate_spec(
            spec_dict([stage("s1", task("a"))], backend="claude"))
        self.assertEqual(spec["backend"], "claude")

    def test_backend_invalid_rejected(self):
        d = spec_dict([stage("s1", task("a"))], backend="gpt")
        with self.assertRaises(runner.SpecError):
            runner.validate_spec(d)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest discover -s tests -t tests -p "test_validate.py" -v`
Expected: FAIL，`test_backend_defaults_codex` 报 `KeyError: 'backend'`，`test_backend_claude_accepted` 同；`test_backend_invalid_rejected` 因未拒绝而 fail。

- [ ] **Step 3: 最小实现**

在 `src/runner.py` 的 `ALLOWED_SPEC_KEYS` 定义处加入 `"backend"`：

```python
ALLOWED_SPEC_KEYS = {"version", "name", "workdir", "max_concurrency",
                     "timeout_seconds", "stages", "backend"}
```

在 `EFFORTS = {"low", "medium", "high"}` 这一行后新增：

```python
BACKENDS = {"codex", "claude"}
```

在 `validate_spec` 中，`stages_raw = raw.get("stages")` 之前插入 backend 校验：

```python
    backend = raw.get("backend", "codex")
    if backend not in BACKENDS:
        raise SpecError("backend 只能是 codex 或 claude: %r" % (backend,))
```

把 `validate_spec` 的 return 改为带上 backend：

```python
    return {"version": 1, "name": name, "workdir": str(Path(workdir)),
            "max_concurrency": mc, "timeout_seconds": timeout_s,
            "backend": backend, "stages": stages}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest discover -s tests -t tests -p "test_validate.py" -v`
Expected: PASS（含新 3 条与原有全部）。

- [ ] **Step 5: 提交（需用户授权）**

```bash
git add src/runner.py tests/test_validate.py
git commit -m "feat(read): validate_spec 支持 backend 字段(默认 codex)"
```

---

### Task 2: build_claude_read_cmd 命令构建

**Files:**
- Modify: `src/runner.py`（新增 `CLAUDE_READ_TOOLS` 常量与 `build_claude_read_cmd`）
- Test: `tests/test_claude_cmd.py`（新建）

**Interfaces:**
- Consumes: 无（纯函数）。
- Produces: `runner.CLAUDE_READ_TOOLS = "Read,Grep,Glob"`；`build_claude_read_cmd(claude_prefix, prompt, schema_inline=None, reasoning_effort=None) -> list[str]`。
  - 注：相对 spec §4.1 去掉了无用的 `workdir` 参数（spec 注明它"仅用于校验/记录、不进 argv"，实际无校验需求；工作目录由 `_run_task` 用 subprocess `cwd` 设置）。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_claude_cmd.py`：

```python
# -*- coding: utf-8 -*-
import unittest

from helpers import runner


class TestBuildClaudeReadCmd(unittest.TestCase):
    def test_full_argv_with_schema_and_effort(self):
        cmd = runner.build_claude_read_cmd(
            ["claude"], "审查代码",
            schema_inline='{"type":"object"}', reasoning_effort="high")
        self.assertEqual(cmd, [
            "claude", "-p",
            "--output-format", "json",
            "--strict-mcp-config",
            "--tools", "Read,Grep,Glob",
            "--effort", "high",
            "--json-schema", '{"type":"object"}',
            "--", "审查代码",
        ])

    def test_minimal_no_schema_no_effort(self):
        cmd = runner.build_claude_read_cmd(["claude"], "p")
        self.assertEqual(cmd, [
            "claude", "-p",
            "--output-format", "json",
            "--strict-mcp-config",
            "--tools", "Read,Grep,Glob",
            "--", "p",
        ])
        self.assertNotIn("--json-schema", cmd)
        self.assertNotIn("--effort", cmd)
        self.assertNotIn("-C", cmd)
        self.assertNotIn("-o", cmd)

    def test_tools_locked_to_readonly(self):
        cmd = runner.build_claude_read_cmd(["claude"], "p")
        i = cmd.index("--tools")
        self.assertEqual(cmd[i + 1], "Read,Grep,Glob")

    def test_prompt_after_separator(self):
        cmd = runner.build_claude_read_cmd(["claude"], "--help 其实是 prompt")
        self.assertEqual(cmd[-2:], ["--", "--help 其实是 prompt"])

    def test_prefix_can_be_multi_token(self):
        cmd = runner.build_claude_read_cmd(["python", "mock_claude.py"], "p")
        self.assertEqual(cmd[:2], ["python", "mock_claude.py"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest discover -s tests -t tests -p "test_claude_cmd.py" -v`
Expected: FAIL，`AttributeError: module 'runner' has no attribute 'build_claude_read_cmd'`。

- [ ] **Step 3: 最小实现**

在 `src/runner.py` 中 `build_cmd` 函数定义之后，新增常量与函数：

```python
CLAUDE_READ_TOOLS = "Read,Grep,Glob"   # claude 读模式工具集,硬编码,spec 无法放开


def build_claude_read_cmd(claude_prefix, prompt, schema_inline=None,
                          reasoning_effort=None):
    """白名单拼装 claude 读子代理命令。--tools 钉死只读集(Read,Grep,Glob),
    spec 无法放开;--strict-mcp-config 不加载 MCP。无 -C(工作目录由调用方用 cwd 设)、
    无 -o(输出经 stdout 的 JSON 信封,runner 自捕获)。schema 走 --json-schema 内联字符串。
    variadic 的 --tools 后必跟另一个 -- 选项,防吞后续参数;prompt 前插 -- 分隔符。"""
    cmd = list(claude_prefix) + [
        "-p",
        "--output-format", "json",
        "--strict-mcp-config",
        "--tools", CLAUDE_READ_TOOLS,
    ]
    if reasoning_effort:
        cmd += ["--effort", reasoning_effort]
    if schema_inline is not None:
        cmd += ["--json-schema", schema_inline]
    cmd += ["--", prompt]
    return cmd
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest discover -s tests -t tests -p "test_claude_cmd.py" -v`
Expected: PASS（5 条）。

- [ ] **Step 5: 提交（需用户授权）**

```bash
git add src/runner.py tests/test_claude_cmd.py
git commit -m "feat(read): 新增 build_claude_read_cmd(工具集钉死 Read,Grep,Glob)"
```

---

### Task 3: resolve_backend_cmd 可执行解析

**Files:**
- Modify: `src/runner.py`（新增 `DEFAULT_CLAUDE_CMD`、`resolve_claude_prefix`、`resolve_backend_cmd`）
- Test: `tests/test_resolve_backend.py`（新建）

**Interfaces:**
- Consumes: 现有 `resolve_codex_prefix(user_prefix)`。
- Produces: `runner.DEFAULT_CLAUDE_CMD`（字符串路径）；`resolve_claude_prefix(user_prefix) -> list[str]`；`resolve_backend_cmd(backend, user_prefix) -> list[str]`（backend 未知抛 `WorkflowError`）。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_resolve_backend.py`：

```python
# -*- coding: utf-8 -*-
import unittest

from helpers import runner


class TestResolveBackendCmd(unittest.TestCase):
    def test_user_prefix_wins_codex(self):
        self.assertEqual(
            runner.resolve_backend_cmd("codex", ["x", "y"]), ["x", "y"])

    def test_user_prefix_wins_claude(self):
        self.assertEqual(
            runner.resolve_backend_cmd("claude", ["x", "y"]), ["x", "y"])

    def test_unknown_backend_raises(self):
        with self.assertRaises(runner.WorkflowError):
            runner.resolve_backend_cmd("gpt", None)

    def test_claude_prefix_user_override(self):
        # 给定 user_prefix 时直接返回,不触碰真实 PATH 解析
        self.assertEqual(
            runner.resolve_claude_prefix(["python", "mock_claude.py"]),
            ["python", "mock_claude.py"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest discover -s tests -t tests -p "test_resolve_backend.py" -v`
Expected: FAIL，`AttributeError: module 'runner' has no attribute 'resolve_backend_cmd'`。

- [ ] **Step 3: 最小实现**

在 `src/runner.py` 顶部常量区（`DEFAULT_CODEX_CMD = ...` 之后）新增：

```python
# claude 是原生 exe(C:\Users\Orz\.local\bin\claude.exe),Python 可直接 Popen,无 codex 的 .cmd 垫片坑。
# 优先用 PATH 上的 claude;找不到再回退此绝对路径。版本/安装位置变动时按实际重填。
DEFAULT_CLAUDE_CMD = r"C:\Users\Orz\.local\bin\claude.exe"
```

在 `resolve_codex_prefix` 函数之后新增：

```python
def resolve_claude_prefix(user_prefix):
    """决定 claude 子代理用什么命令启动。优先 --claude-cmd(测试注入);
    否则优先 PATH 上的 claude,找不到回退 DEFAULT_CLAUDE_CMD。claude 是原生 exe,无 .cmd 垫片问题。"""
    if user_prefix:
        return list(user_prefix)
    exe = shutil.which("claude")
    if not exe and Path(DEFAULT_CLAUDE_CMD).exists():
        exe = DEFAULT_CLAUDE_CMD
    if not exe:
        raise WorkflowError(
            "找不到 claude 命令(PATH 无 claude 且默认路径不存在): %s" % DEFAULT_CLAUDE_CMD)
    return [str(exe)]


def resolve_backend_cmd(backend, user_prefix):
    """按 backend 分发到对应的命令前缀解析器。两后端都先认显式 user_prefix。"""
    if backend == "codex":
        return resolve_codex_prefix(user_prefix)
    if backend == "claude":
        return resolve_claude_prefix(user_prefix)
    raise WorkflowError("未知 backend: %r" % (backend,))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest discover -s tests -t tests -p "test_resolve_backend.py" -v`
Expected: PASS（4 条）。

- [ ] **Step 5: 提交（需用户授权）**

```bash
git add src/runner.py tests/test_resolve_backend.py
git commit -m "feat(read): 新增 resolve_backend_cmd / resolve_claude_prefix"
```

---

### Task 4: _parse_claude_result 信封解析

**Files:**
- Modify: `src/runner.py`（新增 `_parse_claude_result`）
- Test: `tests/test_claude_envelope.py`（新建）

**Interfaces:**
- Consumes: 无（纯函数，标准库 json）。
- Produces: `_parse_claude_result(raw_text, has_schema) -> (status, output, tokens, error)`：
  - `status`：`"ok"` | `"error"` | `"parse_error"`
  - `output`：成功时结果（has_schema 取 `structured_output`，否则 `result` 文本）；失败 `None`
  - `tokens`：`usage.output_tokens`（int）或 `None`
  - `error`：失败原因字符串或 `None`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_claude_envelope.py`：

```python
# -*- coding: utf-8 -*-
import json
import unittest

from helpers import runner


def env(**kw):
    base = {"type": "result", "subtype": "success", "is_error": False}
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


class TestParseClaudeResult(unittest.TestCase):
    def test_success_text(self):
        st, out, tok, err = runner._parse_claude_result(
            env(result="答案", usage={"output_tokens": 12}), has_schema=False)
        self.assertEqual(st, "ok")
        self.assertEqual(out, "答案")
        self.assertEqual(tok, 12)
        self.assertIsNone(err)

    def test_success_structured(self):
        st, out, tok, err = runner._parse_claude_result(
            env(result="x", structured_output={"k": 1},
                usage={"output_tokens": 5}), has_schema=True)
        self.assertEqual(st, "ok")
        self.assertEqual(out, {"k": 1})
        self.assertEqual(tok, 5)

    def test_is_error_true(self):
        st, out, tok, err = runner._parse_claude_result(
            env(is_error=True, result=""), has_schema=False)
        self.assertEqual(st, "error")
        self.assertIsNone(out)

    def test_subtype_not_success(self):
        st, out, tok, err = runner._parse_claude_result(
            env(subtype="error_max_turns"), has_schema=False)
        self.assertEqual(st, "error")

    def test_empty_is_parse_error(self):
        st, out, tok, err = runner._parse_claude_result("", has_schema=False)
        self.assertEqual(st, "parse_error")

    def test_bad_json_is_parse_error(self):
        st, out, tok, err = runner._parse_claude_result("{不是json", has_schema=False)
        self.assertEqual(st, "parse_error")

    def test_schema_missing_structured_output(self):
        st, out, tok, err = runner._parse_claude_result(
            env(result="x"), has_schema=True)
        self.assertEqual(st, "error")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest discover -s tests -t tests -p "test_claude_envelope.py" -v`
Expected: FAIL，`AttributeError: module 'runner' has no attribute '_parse_claude_result'`。

- [ ] **Step 3: 最小实现**

在 `src/runner.py` 的 `_extract_tokens` 函数之后新增：

```python
def _parse_claude_result(raw_text, has_schema):
    """解析 claude -p --output-format json 的 stdout 信封。
    返回 (status, output, tokens, error)。
    空/非法 JSON → parse_error;is_error 或 subtype!=success → error;
    has_schema 时取 structured_output(缺则 error),否则取 result 文本。"""
    if not raw_text or not raw_text.strip():
        return "parse_error", None, None, "claude 输出为空"
    try:
        env = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return "parse_error", None, None, "claude 信封不是合法 JSON: %s" % e
    if not isinstance(env, dict):
        return "parse_error", None, None, "claude 信封不是 JSON 对象"
    tokens = None
    usage = env.get("usage")
    if isinstance(usage, dict) and isinstance(usage.get("output_tokens"), int):
        tokens = usage["output_tokens"]
    if env.get("is_error") is True or env.get("subtype") != "success":
        return ("error", None, tokens,
                "claude 信封报告失败: subtype=%s is_error=%s"
                % (env.get("subtype"), env.get("is_error")))
    if has_schema:
        if "structured_output" not in env:
            return "error", None, tokens, "claude 信封缺 structured_output"
        return "ok", env["structured_output"], tokens, None
    return "ok", env.get("result", ""), tokens, None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest discover -s tests -t tests -p "test_claude_envelope.py" -v`
Expected: PASS（7 条）。

- [ ] **Step 5: 提交（需用户授权）**

```bash
git add src/runner.py tests/test_claude_envelope.py
git commit -m "feat(read): 新增 _parse_claude_result 信封解析"
```

---

### Task 5: mock_claude 测试替身 + helpers 接入

**Files:**
- Create: `tests/mock_claude.py`
- Modify: `tests/helpers.py`（新增 `MOCK_CLAUDE_PREFIX`；`run_wf` 加 `prefix` 参数）
- Test: `tests/test_mock_claude.py`（新建，smoke 验证 mock 输出格式）

**Interfaces:**
- Consumes: `runner`（间接，经 run_wf）。
- Produces: `helpers.MOCK_CLAUDE_PREFIX = [sys.executable, <tests/mock_claude.py>]`；`run_wf(raw, prefix=None, **kw)`（prefix 缺省 `MOCK_PREFIX`）；`mock_claude.py` 模拟 `claude -p --output-format json`，支持 `[MOCK:exit=N] / [MOCK:iserror] / [MOCK:badjson] / [MOCK:empty] / [MOCK:tokens=N] / [MOCK:cwdfile]`。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_mock_claude.py`：

```python
# -*- coding: utf-8 -*-
import json
import subprocess
import unittest

from helpers import MOCK_CLAUDE_PREFIX


def run_mock(prompt, schema=None):
    cmd = list(MOCK_CLAUDE_PREFIX) + [
        "-p", "--output-format", "json", "--strict-mcp-config",
        "--tools", "Read,Grep,Glob"]
    if schema:
        cmd += ["--json-schema", schema]
    cmd += ["--", prompt]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


class TestMockClaude(unittest.TestCase):
    def test_text_envelope(self):
        r = run_mock("你好")
        env = json.loads(r.stdout)
        self.assertEqual(env["result"], "ECHO:你好")
        self.assertFalse(env["is_error"])
        self.assertEqual(env["subtype"], "success")

    def test_schema_structured(self):
        r = run_mock("你好", schema='{"type":"object"}')
        env = json.loads(r.stdout)
        self.assertEqual(env["structured_output"]["echo"], "你好")

    def test_exit_code(self):
        r = run_mock("[MOCK:exit=3][MOCK:empty] x")
        self.assertEqual(r.returncode, 3)

    def test_tokens(self):
        r = run_mock("你好[MOCK:tokens=88]")
        env = json.loads(r.stdout)
        self.assertEqual(env["usage"]["output_tokens"], 88)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest discover -s tests -t tests -p "test_mock_claude.py" -v`
Expected: FAIL，`ImportError: cannot import name 'MOCK_CLAUDE_PREFIX' from 'helpers'`。

- [ ] **Step 3: 实现 mock_claude.py**

新建 `tests/mock_claude.py`：

```python
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
```

- [ ] **Step 4: 改 helpers.py 接入**

在 `tests/helpers.py` 的 `MOCK_PREFIX = [...]` 一行之后新增：

```python
MOCK_CLAUDE_PREFIX = [sys.executable, str(ROOT / "tests" / "mock_claude.py")]
```

把 `run_wf` 改为支持 prefix（默认仍用 codex mock，保证现有测试不受影响）：

```python
def run_wf(raw, prefix=None, **kw):
    """校验 spec 并在临时运行目录里用 mock 替身跑完整个 workflow。
    prefix 缺省 codex mock;claude 后端测试传 MOCK_CLAUDE_PREFIX。"""
    spec = runner.validate_spec(raw)
    rd = mktemp("dynwf-test-") / "run"
    summary = asyncio.run(runner.run_workflow(spec, rd, prefix or MOCK_PREFIX, **kw))
    return summary, rd
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m unittest discover -s tests -t tests -p "test_mock_claude.py" -v`
Expected: PASS（4 条）。

- [ ] **Step 6: 回归确认 run_wf 改动没破坏现有读模式测试**

Run: `python -m unittest discover -s tests -t tests -p "test_run.py" -v`
Expected: PASS（原有全部）。

- [ ] **Step 7: 提交（需用户授权）**

```bash
git add tests/mock_claude.py tests/helpers.py tests/test_mock_claude.py
git commit -m "test(read): 新增 mock_claude 替身与 helpers 接入"
```

---

### Task 6: _run_task claude 分支 + run_workflow 传 backend

**Files:**
- Modify: `src/runner.py`（新增 `MAX_CLAUDE_ARGV_CHARS`、`_run_claude_task`；改 `_run_task` 签名与分派；改 `run_workflow` 取 backend、改参数名）
- Test: `tests/test_claude_run.py`（新建）

**Interfaces:**
- Consumes: `build_claude_read_cmd`（Task 2）、`_parse_claude_result`（Task 4）、`_harden_schema`、`_check_schema_minimal`、`_kill_tree`（现有）、`MOCK_CLAUDE_PREFIX`、`run_wf(prefix=...)`（Task 5）。
- Produces: `_run_task(task, stage_name, *, sem, run_dir, workdir, timeout_s, backend, prefix, results)`（codex_prefix 改名 prefix、新增 backend）；`_run_claude_task(...)`；`run_workflow(spec, run_dir, prefix, timeout_override=None)`（第三位置参数名 codex_prefix→prefix，语义=命令前缀）。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_claude_run.py`：

```python
# -*- coding: utf-8 -*-
import unittest
from pathlib import Path

from helpers import (MOCK_CLAUDE_PREFIX, run_wf, spec_dict, stage, task,
                     mktemp, runner)


def claude_raw(*tasks_, **over):
    return spec_dict([stage("s1", *tasks_)], backend="claude", **over)


class TestClaudeRun(unittest.TestCase):
    def test_text_ok(self):
        s, _ = run_wf(claude_raw(task("a", prompt="你好")),
                      prefix=MOCK_CLAUDE_PREFIX)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["output"], "ECHO:你好")

    def test_schema_ok(self):
        s, _ = run_wf(claude_raw(task("a", prompt="你好",
                                      output_schema={"type": "object"})),
                      prefix=MOCK_CLAUDE_PREFIX)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["output"]["echo"], "你好")

    def test_is_error_envelope_is_error(self):
        s, _ = run_wf(claude_raw(task("a", prompt="[MOCK:iserror] x")),
                      prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "error")

    def test_nonzero_exit_is_error(self):
        s, _ = run_wf(claude_raw(task("a", prompt="[MOCK:exit=4][MOCK:empty] x")),
                      prefix=MOCK_CLAUDE_PREFIX)
        t = s["tasks"][0]
        self.assertEqual(t["status"], "error")
        self.assertEqual(t["exit_code"], 4)

    def test_bad_json_is_parse_error(self):
        s, _ = run_wf(claude_raw(task("a", prompt="[MOCK:badjson] x")),
                      prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "parse_error")

    def test_tokens_from_envelope(self):
        s, _ = run_wf(claude_raw(task("a", prompt="你好[MOCK:tokens=99]")),
                      prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["tokens"], 99)
        self.assertEqual(s["total_tokens"], 99)

    def test_runs_in_workdir_cwd(self):
        wd = mktemp("dynwf-claude-cwd-")
        raw = spec_dict([stage("s1", task("a", prompt="[MOCK:cwdfile] x"))],
                        backend="claude", workdir=str(wd))
        s, _ = run_wf(raw, prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "ok")
        self.assertTrue((wd / "claude_cwd_marker.txt").exists())

    def test_argv_guard_rejects_oversized(self):
        # schema 内联后约 3 万字符,加 prompt 超过 MAX_CLAUDE_ARGV_CHARS(28000)→ 拒
        big_schema = {"type": "object",
                      "properties": {"x": {"type": "string",
                                           "description": "d" * 30000}}}
        raw = claude_raw(task("a", prompt="你好", output_schema=big_schema))
        s, _ = run_wf(raw, prefix=MOCK_CLAUDE_PREFIX)
        self.assertEqual(s["tasks"][0]["status"], "prompt_too_long")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest discover -s tests -t tests -p "test_claude_run.py" -v`
Expected: FAIL（claude 走了 codex 路径或 `_run_task` 不认 backend，状态非预期 / TypeError）。

- [ ] **Step 3: 改 _run_task 签名并接入分派**

在 `src/runner.py` 中，将 `_run_task` 的签名行改为（把 `codex_prefix` 改名 `prefix`、新增 `backend`）：

```python
async def _run_task(task, stage_name, *, sem, run_dir, workdir,
                    timeout_s, backend, prefix, results):
```

在 `_run_task` 内，prompt 长度检查（`return entry` 的 `prompt_too_long` 分支）之后、`schema_path = None` 之前，插入 claude 分派：

```python
    if backend == "claude":
        return await _run_claude_task(task, stage_name, tdir, workdir, prompt,
                                      timeout_s, prefix, sem, entry)
```

把 `_run_task` 原 codex 路径里那一行 `cmd = build_cmd(codex_prefix, ...)` 改为用新参数名 `prefix`：

```python
    cmd = build_cmd(prefix, workdir, prompt, out_path, schema_path,
                    task["reasoning_effort"])
```

（codex 路径其余代码——子进程 IO、超时、解析、token——保持不变。）

- [ ] **Step 4: 新增 _run_claude_task 与常量**

在 `_run_task` 函数之后新增常量与函数：

```python
# claude 内联 schema 后,prompt + schema 合计 argv 上限(防撑爆 Windows 命令行 ~32760,留余量给固定参数)
MAX_CLAUDE_ARGV_CHARS = 28000


async def _run_claude_task(task, stage_name, tdir, workdir, prompt,
                           timeout_s, prefix, sem, entry):
    """claude 读路径:stdout 收信封到 raw.json、stderr 进 agent.log、stdin=DEVNULL、
    cwd=workdir;跑完解析信封填 entry(entry 已含 id/stage 等公共字段)。"""
    schema_inline = None
    if task["output_schema"] is not None:
        schema_inline = json.dumps(_harden_schema(task["output_schema"]),
                                   ensure_ascii=False)
    if len(prompt) + (len(schema_inline) if schema_inline else 0) > MAX_CLAUDE_ARGV_CHARS:
        entry["status"] = "prompt_too_long"
        entry["error"] = "claude prompt+schema 合计超过 argv 上限 %d" % MAX_CLAUDE_ARGV_CHARS
        print("[%s] PROMPT_TOO_LONG %s (claude argv)" % (_now(), task["id"]),
              flush=True)
        return entry

    cmd = build_claude_read_cmd(prefix, prompt, schema_inline,
                                task["reasoning_effort"])
    (tdir / "cmd.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    raw_path = tdir / "raw.json"

    async with sem:
        print("[%s] START %s (stage=%s, claude)" % (_now(), task["id"], stage_name),
              flush=True)
        t0 = time.monotonic()
        log_f = open(tdir / "agent.log", "wb")
        raw_f = open(raw_path, "wb")
        try:
            try:
                # claude 无 -C:用 cwd 设工作目录;stdin=DEVNULL 避免等 3 秒 stdin;
                # stdout=信封→raw.json,stderr=诊断→agent.log(两路分离,信封不被噪音污染)
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=raw_f, stderr=log_f,
                    stdin=asyncio.subprocess.DEVNULL, cwd=str(workdir))
            except (FileNotFoundError, OSError) as e:
                entry["status"] = "spawn_error"
                entry["error"] = "启动失败: %s" % e
                print("[%s] SPAWN_ERROR %s: %s" % (_now(), task["id"], e),
                      flush=True)
                return entry
            try:
                rc = await asyncio.wait_for(proc.wait(), timeout=timeout_s)
            except asyncio.TimeoutError:
                await _kill_tree(proc)
                entry["status"] = "timeout"
                entry["duration_s"] = round(time.monotonic() - t0, 1)
                print("[%s] TIMEOUT %s (%ds)" % (_now(), task["id"], timeout_s),
                      flush=True)
                return entry
        finally:
            log_f.close()
            raw_f.close()
        entry["exit_code"] = rc
        entry["duration_s"] = round(time.monotonic() - t0, 1)

    raw_text = (raw_path.read_text(encoding="utf-8", errors="replace")
                if raw_path.exists() else "")
    has_schema = task["output_schema"] is not None
    status, output, tokens, err = _parse_claude_result(raw_text, has_schema)
    entry["tokens"] = tokens
    if rc != 0:
        entry["status"] = "error"
        entry["error"] = "claude 退出码 %s" % rc
        print("[%s] FAIL  %s exit=%s (%.1fs)" % (_now(), task["id"], rc,
                                                 entry["duration_s"]), flush=True)
        return entry
    if status != "ok":
        entry["status"] = status
        entry["error"] = err
        print("[%s] %s %s" % (_now(), status.upper(), task["id"]), flush=True)
        return entry
    if has_schema:
        problems = _check_schema_minimal(output, task["output_schema"])
        if problems:
            entry["status"] = "schema_mismatch"
            entry["error"] = "输出不满足 schema 最小检查: %s" % "; ".join(problems)
            print("[%s] SCHEMA_MISMATCH %s" % (_now(), task["id"]), flush=True)
            return entry
    entry["output"] = output
    entry["status"] = "ok"
    print("[%s] OK    %s (%.1fs)" % (_now(), task["id"], entry["duration_s"]),
          flush=True)
    return entry
```

- [ ] **Step 5: 改 run_workflow 取 backend 并传入**

在 `src/runner.py` 中，将 `run_workflow` 签名 `async def run_workflow(spec, run_dir, codex_prefix, timeout_override=None):` 改为：

```python
async def run_workflow(spec, run_dir, prefix, timeout_override=None):
```

在 `run_workflow` 内 `sem = asyncio.Semaphore(...)` 之前取出 backend：

```python
    backend = spec.get("backend", "codex")
```

把 stage 循环里构造 coros 的 `_run_task(...)` 调用改为传 backend 与新参数名 prefix：

```python
        coros = [_run_task(t, stage["name"], sem=sem, run_dir=run_dir,
                           workdir=spec["workdir"], timeout_s=timeout_s,
                           backend=backend, prefix=prefix, results=results)
                 for t in stage["tasks"]]
```

- [ ] **Step 6: 跑测试确认通过 + 回归**

Run: `python -m unittest discover -s tests -t tests -p "test_claude_run.py" -v`
Expected: PASS（8 条）。

Run: `python -m unittest discover -s tests -t tests -p "test_run.py" -v`
Expected: PASS（codex 路径回归全绿）。

- [ ] **Step 7: 提交（需用户授权）**

```bash
git add src/runner.py tests/test_claude_run.py
git commit -m "feat(read): _run_task 接入 claude 分支与 run_workflow backend 分派"
```

---

### Task 7: CLI 接入 --backend/--claude-cmd + backend 持久化

**Files:**
- Modify: `src/runner.py`（`_main_read` 加参数与分派；`run_workflow` 的 summary 加 backend 字段）
- Test: `tests/test_cli.py`（追加用例）

**Interfaces:**
- Consumes: `resolve_backend_cmd`（Task 3）、`run_workflow`（Task 6）。
- Produces: CLI 新增 `--backend codex|claude` 与 `--claude-cmd`（可重复）；读模式 `summary.json` 与 `spec.resolved.json` 均含 `"backend"`；优先级 CLI > spec > 默认 codex。

- [ ] **Step 1: 写失败测试**

在 `tests/test_cli.py` 末尾、`if __name__` 之前，新增独立的 claude CLI 测试类：

```python
class TestCliClaude(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("DYNWF_RUNS_ROOT", None)

    def _run(self, raw, *extra):
        spec_path = write_spec(raw)
        runs_root = spec_path.parent / "runs"
        runs_root.mkdir(exist_ok=True)
        os.environ["DYNWF_RUNS_ROOT"] = str(runs_root)
        run_dir = runs_root / "run"
        mock = str(ROOT / "tests" / "mock_claude.py")
        argv = [str(spec_path), "--run-dir", str(run_dir),
                "--claude-cmd", sys.executable, "--claude-cmd", mock,
                "--timeout-override", "5", "--ack-external-model-export"]
        argv += list(extra)
        return runner.main(argv), run_dir

    def test_backend_claude_persisted(self):
        raw = spec_dict([stage("s1", task("a", prompt="你好"))], backend="claude")
        code, run_dir = self._run(raw)
        self.assertEqual(code, 0)
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["backend"], "claude")
        resolved = json.loads((run_dir / "spec.resolved.json").read_text(encoding="utf-8"))
        self.assertEqual(resolved["backend"], "claude")

    def test_cli_backend_overrides_spec(self):
        # spec 写 codex,CLI --backend claude 覆盖 → 用 mock_claude,退出 0
        raw = spec_dict([stage("s1", task("a", prompt="你好"))], backend="codex")
        code, run_dir = self._run(raw, "--backend", "claude")
        self.assertEqual(code, 0)
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["backend"], "claude")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest discover -s tests -t tests -p "test_cli.py" -v`
Expected: FAIL，`test_backend_claude_persisted` 报 `KeyError: 'backend'`（summary 无该字段）或因仍用 codex 解析而非 0 退出。

- [ ] **Step 3: 改 _main_read 加参数与分派**

在 `src/runner.py` 的 `_main_read` 中，`--codex-cmd` 参数定义之前新增：

```python
    ap.add_argument("--backend", choices=["codex", "claude"], default=None,
                    help="覆盖 spec 的 backend;CLI 优先于 spec(默认随 spec,spec 默认 codex)")
```

在 `--codex-cmd` 定义之后新增：

```python
    ap.add_argument("--claude-cmd", action="append", default=None,
                    help="claude 子代理命令前缀,可重复传多段(测试用,默认解析本机 claude)")
```

把原 `spec = validate_spec(...)` 与 `codex_prefix = resolve_codex_prefix(args.codex_cmd)` 两行所在的 try 块改为按 backend 解析（注意 backend 优先级在 validate 之后覆盖）：

```python
    try:
        spec = validate_spec(raw, allowed_roots=args.allowed_root)
        if args.backend:
            spec["backend"] = args.backend          # CLI 优先于 spec
        backend = spec["backend"]
        user_prefix = args.claude_cmd if backend == "claude" else args.codex_cmd
        prefix = resolve_backend_cmd(backend, user_prefix)
    except WorkflowError as e:
        print("无法开跑: %s" % e, file=sys.stderr)
        return 1
```

把后面 `asyncio.run(run_workflow(spec, run_dir, codex_prefix, ...))` 里的 `codex_prefix` 改为 `prefix`：

```python
        summary = asyncio.run(run_workflow(spec, run_dir, prefix,
                                           timeout_override=args.timeout_override))
```

- [ ] **Step 4: run_workflow 的 summary 加 backend 字段**

在 `src/runner.py` 的 `run_workflow` 内，构造 `summary = {...}` 处加入 `"backend"`（`backend` 已在 Task 6 Step 5 取出）：

```python
    summary = {
        "name": spec["name"],
        "run_dir": str(run_dir),
        "backend": backend,
        "started": started,
        "finished": _dt.datetime.now().isoformat(timespec="seconds"),
        "ok": sum(1 for e in entries if e["status"] == "ok"),
        "total": len(entries),
        "total_tokens": sum(tok_vals) if tok_vals else None,
        "tasks": entries,
    }
```

（`spec.resolved.json` 在 run_workflow 开头已整体写出 spec，含 backend，无需额外改动。）

- [ ] **Step 5: 跑测试确认通过 + 回归**

Run: `python -m unittest discover -s tests -t tests -p "test_cli.py" -v`
Expected: PASS（含原有 codex CLI 用例与新 claude 用例）。

- [ ] **Step 6: 提交（需用户授权）**

```bash
git add src/runner.py tests/test_cli.py
git commit -m "feat(read): CLI --backend/--claude-cmd 接入与 backend 持久化"
```

---

### Task 8: 更新顶部 docstring 安全边界表述 + 全量回归

**Files:**
- Modify: `src/runner.py`（模块顶部 docstring）
- Test: 全量回归（无新增测试）

**Interfaces:**
- Consumes: 无。
- Produces: 无（仅文档）。

- [ ] **Step 1: 更新 docstring**

把 `src/runner.py` 顶部模块 docstring 中"并行编排多个 `codex exec` 只读子代理"及其后的安全护栏段，更新为分后端表述。将开头两行与第一条护栏改为：

```python
"""dynamic-workflow runner v0.1
并行编排只读子代理,支持两个后端:codex(默认)与 claude(读模式)。

安全护栏(硬编码,spec 无法放开):
- 隔离机制按后端不同:codex 子代理强制 -s read-only(OS 沙箱,不可写/不可联网);
  claude 读子代理靠 --tools "Read,Grep,Glob" 裁剪工具集 + --strict-mcp-config 不加载 MCP
  实现只读——这是工具层约束、非 OS 沙箱,故工具白名单不得加入 Bash/WebFetch/WebSearch。
- 两后端命令均白名单拼装,不透传任何参数
- 并发上限 8(默认 2);单次运行子代理总数上限 12
- 单任务超时 60..1800 秒(默认 900),超时强杀
- 失败不自动重试;spec 含未知字段直接拒绝
"""
```

（保留原 docstring 中写模式相关说明，若有；仅替换上述读模式/隔离段落。）

- [ ] **Step 2: 全量回归**

Run: `python -m unittest discover -s tests -t tests -v`
Expected: PASS（全部测试，含 codex 与 claude 两路、写模式不受影响）。

- [ ] **Step 3: 提交（需用户授权）**

```bash
git add src/runner.py
git commit -m "docs(read): 顶部 docstring 更新为分后端隔离表述"
```

---

## Self-Review

**Spec coverage（设计 §逐条对照）：**
- §1 范围（只读模式、写模式不动）→ Global Constraints + 全程不碰写模式。
- §2 已验证事实 → Task 2/4/5/6 落地（信封字段、--tools、--json-schema 内联、stdin、token）。
- §3 backend 选取与持久化 → Task 1（字段）+ Task 7（CLI 优先级、summary/resolved 持久化）。
- §4 命令构建（对照表、模板、工具集、effort、argv 护栏）→ Task 2 + Task 6（MAX_CLAUDE_ARGV_CHARS）。
- §4.1 命令构建函数 → Task 2（build_claude_read_cmd，注明去掉 workdir 参数）。
- §4.2 可执行解析 → Task 3（resolve_backend_cmd/resolve_claude_prefix）。
- §5 输出捕获与解析（stdout=raw.json/stderr=agent.log/stdin=DEVNULL/cwd、信封解析、token 来自信封）→ Task 4 + Task 6。
- §6 成本/环境（--strict-mcp-config）→ Task 2 命令含 --strict-mcp-config。
- §7 安全边界 docstring → Task 8。
- §8 测试计划（mock_claude、--claude-cmd、7 类用例）→ Task 5 + 各任务测试覆盖 1-7 条。
- §9 明确不做 → 计划未引入写模式/Bash/--bare/--model/写 spec backend 字段。
- §10 风险 → 已在设计文档记录,实现按其约束(工具集不放开)。

**Placeholder scan：** 无 TBD/TODO；每个代码步骤含完整代码；测试含真实断言。

**Type consistency：**
- `build_claude_read_cmd(claude_prefix, prompt, schema_inline=None, reasoning_effort=None)` — Task 2 定义、Task 6 调用一致。
- `_parse_claude_result(raw_text, has_schema) -> (status, output, tokens, error)` — Task 4 定义、Task 6 解构一致。
- `_run_task(..., backend, prefix, ...)` 与 `run_workflow(spec, run_dir, prefix, ...)` — Task 6 改名一致；helpers.run_wf 传位置参数不受影响。
- `resolve_backend_cmd(backend, user_prefix)` — Task 3 定义、Task 7 调用一致。
- spec/summary 的 `"backend"` 键 — Task 1 产出、Task 7 读取/写入一致。

---

## Execution Handoff

计划完成。两种执行方式：

1. **Subagent-Driven（推荐）** — 每个任务派一个全新 subagent，任务间两段式 review，迭代快。REQUIRED SUB-SKILL: superpowers:subagent-driven-development。
2. **Inline Execution** — 在本会话内按 executing-plans 批量执行，带检查点 review。REQUIRED SUB-SKILL: superpowers:executing-plans。

注意：执行涉及改代码与（每任务末）git commit；commit 须先获你授权（D:\codex\CLAUDE.md）。
