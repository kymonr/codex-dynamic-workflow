# 设计：为 dynamic-workflow 读模式增加 claude 后端

- 日期：2026-06-19
- 状态：已设计，待用户审阅
- 范围：仅**读模式**新增 `claude` 后端；写模式（`prepare`/`dispatch`/`collect`）不动。
- 涉及文件：`src/runner.py`（主要）、`tests/`（新增 mock 与用例）、`README.md`/`skill/SKILL.md`（文档，实现阶段最后改，注意不覆盖他人改动）。

---

## 1. 背景与范围收缩的依据

现有 runner 用 `codex exec` 编排只读/写两类子代理。目标是再支持用 Claude CLI（`claude.exe`，本机版本 2.1.183）做子代理。

设计评审发现 claude 写模式有两处不可接受的风险，因此 **v1 主动收缩为只做读模式**：

- **🔴 claude 写模式没有 OS 级沙箱。** codex 写模式靠 `-s workspace-write` 在操作系统层把写入限制在工作区内；claude `-p` 的官方说明是"Only use this in directories you trust"——它是"信任目录"模型，不是沙箱。即便限制工具不给 Bash，Edit/Write 仍能写绝对路径跳出 worktree 副本，而现有 `collect` 只检查副本内改动，看不见副本外的写入，会漏判成 clean。
- **🔴 `--permission-mode auto` 的真实放行范围未经实证。** 交接稿把写模式默认定为 `auto`，但没人验证过 `auto` 对"worktree 内/外写入"分别如何处理。

读模式不写文件，上述风险整体消失：读模式的隔离用 `--tools` 裁剪工具集实现，已被实测证实有效（见 §2）。claude 写模式留作以后单独一轮设计。

## 2. 已实测验证的事实（探针证据）

实现据此设计，避免凭记忆假设。探针均在本机真实跑过 `claude -p`：

| 事实 | 验证方式 | 结论 |
|---|---|---|
| claude 是原生 exe | `Get-Command claude` → `C:\Users\Orz\.local\bin\claude.exe`，CommandType=Application | Python 可直接 `Popen`，无 codex 那种 `.cmd` 垫片坑 |
| `--tools` 硬裁剪工具集 | `claude -p --tools "Read" ...` 让模型试图跑 Bash，模型答"I don't have a shell/Bash tool available"，`permission_denials:[]` | 工具不在 `--tools` 列表里，模型**够不到**，不是被拦；这是读模式隔离的依据 |
| 结构化输出有独立字段 | `claude -p --output-format json --json-schema '{...}'` → 信封含 `"structured_output":{...}`，`result` 为文本 | 取 `.structured_output`，比解析夹杂文本的 `result` 干净 |
| `--json-schema` 收内联 JSON | 探针直接传内联 JSON 字符串成功 | schema 序列化成一行 JSON 当 argv 传，**非**文件路径 |
| prompt 走 argv 位置参数 | `claude [options] [prompt]`；探针把 prompt 当位置参数成功 | 沿用 `-- <prompt>` 直传 |
| token/成本在信封里 | 信封含 `usage.output_tokens`、`total_cost_usd` | 直接解析，不刮日志 |
| `-p` 会等 stdin | 探针出现 `Warning: no stdin data received in 3s` | 必须 `stdin=DEVNULL`，否则每个子代理白等 3 秒 |
| 默认加载整套环境 | 探针单次约 \$0.13–0.51（opus），`cache_creation_input_tokens` 大头是自动加载的 CLAUDE.md/skills | 必带 `--strict-mcp-config`；其余环境开销作为已知成本记录 |

claude `-p --output-format json` 的信封形态（实测）：

```json
{"type":"result","subtype":"success","is_error":false,
 "result":"<文本回答>",
 "structured_output":{...},          // 仅在带 --json-schema 时出现
 "usage":{"output_tokens":345,"input_tokens":2401,...},
 "total_cost_usd":0.13,
 "permission_denials":[]}
```

## 3. 后端选取与持久化

优先级（高 → 低）：

```
CLI --backend  >  spec 的 "backend"  >  默认 "codex"
```

- 读 spec 新增可选字段 `"backend": "codex" | "claude"`。`ALLOWED_SPEC_KEYS` 加 `"backend"`；非法值在 `validate_spec` 里拒绝。`validate_spec` 返回的归一化 dict 增加 `"backend"`（缺省 `"codex"`）。
- CLI `_main_read` 新增 `--backend codex|claude`；解析后若提供则覆盖 `spec["backend"]`。
- 解析后的 backend **写入 `spec.resolved.json` 与读模式 `summary.json`**，留痕可查。
- **写模式不引入 backend 字段**：`ALLOWED_WRITE_SPEC_KEYS` 保持原样。写 spec 里出现 `backend` 会被现有"未知字段一律拒绝"挡掉并明确报错，无需额外代码。

## 4. 命令构建（核心）

codex 与 claude 读命令对照：

| 维度 | codex（现状，不变） | claude（新增） |
|---|---|---|
| 启动 | `codex exec -s read-only --skip-git-repo-check --color never` | `claude -p --output-format json --strict-mcp-config` |
| 工作目录 | `-C <workdir>` | 无 `-C` → 子进程 `cwd=<workdir>` |
| 隔离机制 | OS 沙箱（不可写、不可联网） | `--tools "Read,Grep,Glob"`（裁剪工具集）+ `--strict-mcp-config`（不加载 MCP） |
| 结构化输出 | `--output-schema <文件>` | `--json-schema '<内联JSON>'` |
| 思考力度 | `-c model_reasoning_effort=<X>` | `--effort <X>` |
| 输出落地 | `-o <文件>`（codex 自己写） | 无 → runner 捕获 stdout 自写 |

claude 读命令模板（参数顺序固定，variadic 的 `--tools` 后面必须紧跟另一个 `--` 选项，防止吞掉后续参数）：

```
claude.exe -p --output-format json --strict-mcp-config
           --tools "Read,Grep,Glob"
           [--effort <low|medium|high>]
           [--json-schema '<inline-json>']
           -- <prompt>
```

设计要点：

- **工具集 = 纯文件/搜索（`Read,Grep,Glob`），不含 Bash。** 这是经用户确认的取舍：claude 读子代理能读文件/grep/glob，但不能跑 `git diff`/`git log`/`tree` 等命令。需要只读 shell 的场景用 codex 后端（codex `-s read-only` 支持）。工具集是**精选最小集**而非"default 去掉 Bash"——必须显式排除联网工具（WebFetch/WebSearch），否则读到的敏感内容可被外泄。
- `--effort` 仅在 `reasoning_effort ∈ {low,medium,high}` 时附加，与 codex 共用同一 `EFFORTS` 白名单，直接映射。
- schema 走内联：`--json-schema` 接收 `json.dumps(_harden_schema(schema))` 的单行字符串。
- **argv 长度护栏**：prompt 上限 20000 字符已有校验；claude 路径额外校验 `prompt + 内联 schema` 合计不撑爆 Windows argv（约 32760）。超限标错，不开跑。

### 4.1 命令构建函数

读模式命令构建按后端分两个独立内部函数，由 `_run_task` 按 `backend` 调用对应的，各取所需、不强塞统一签名：

- codex：保留现有 `build_cmd(prefix, workdir, prompt, out_path, schema_path, reasoning_effort)`（含 `-C`、`-o`、`--output-schema <文件>`、`-c model_reasoning_effort`）。
- claude：新增 `build_claude_read_cmd(prefix, workdir, prompt, schema_inline, reasoning_effort)`——无 `out_path`/`-o`、无 `-C`（工作目录由 `_run_task` 用 `cwd` 设），schema 走 `--json-schema <内联字符串>`；`workdir` 仅用于校验/记录，不进 argv。
- schema 形态差异在 `_run_task` 里就绪后再传入：codex 仍先把 `_harden_schema` 结果写 `schema.json` 再传文件路径；claude 把同一结果 `json.dumps` 成单行字符串传入。
- 各后端命令仍是**白名单拼装、不透传任意参数**，沿用现有安全原则。

### 4.2 可执行解析

- 新增 `resolve_backend_cmd(backend, user_prefix)` 分发；两后端都先认显式 `user_prefix`（测试注入），无则按后端默认解析：
  - codex：保留现有 `resolve_codex_prefix`（含 `.cmd` 垫片报错逻辑），`user_prefix` 来自 `--codex-cmd`。
  - claude：`user_prefix` 来自 `--claude-cmd`；无则优先 `shutil.which("claude")`（解析到真 exe），找不到回退常量 `DEFAULT_CLAUDE_CMD = r"C:\Users\Orz\.local\bin\claude.exe"`，仍校验存在性。claude 是原生 exe，无 `.cmd` 垫片问题。

## 5. 输出捕获与解析

claude 没有 `-o`，由 runner 在 `_run_task` 内按后端分支处理：

- **子进程 IO**：
  - codex（不变）：`stdout=agent.log, stderr=STDOUT`。
  - claude：`stdout=raw.json`（纯信封）、`stderr=agent.log`（诊断/警告）、`stdin=DEVNULL`、`cwd=workdir`。
- **解析**：读 `raw.json` → `json.loads` 信封：
  - `is_error == true` 或 `subtype != "success"` → 状态 `error`。
  - 有 schema：取 `.structured_output`，写 `out.json`；过现有 `_check_schema_minimal`。
  - 无 schema：取 `.result`（字符串），写 `out.txt`。
  - 解析后产物结构与 codex 对齐，**下游 `substitute` 占位符注入逻辑完全复用、无感知**。
- **token/成本**：claude 从信封 `usage`（如 `output_tokens`）取；不调用 `_extract_tokens`。codex 仍走 `_extract_tokens`。

## 6. 成本与环境（已知局限，非阻断）

- 每个 claude 读子代理约 \$0.13 起（opus 实测），因 claude `-p` 默认加载 workdir 链上的 `CLAUDE.md` + 全局 skills。多子代理时固定开销显著高于 codex。
- v1 强制 `--strict-mcp-config` 砍掉 MCP（最大的副作用与挂起源，且本机配了 computer-use/fetch 等）。
- CLAUDE.md/skills 仍会被 claude 自动加载——作为已知成本记录。`--bare` 能彻底剥离，但会强制 `ANTHROPIC_API_KEY` 认证、破坏订阅/OAuth 登录，故 v1 不用。未来可作专门的成本/隔离优化轮。
- claude 子代理使用本机默认模型（实测为 opus，成本偏高）。是否钉死 `--model sonnet` 控成本留作后续决定，v1 不引入（与现有"读模式不选模型"一致）。

## 7. 安全边界（更新 docstring）

runner 顶部 docstring 现写"所有子代理强制 `-s read-only`"，加 claude 后端后不准确，需更新为分后端表述：

- codex 读子代理：OS 沙箱（`-s read-only`），不可写、不可联网。
- claude 读子代理：靠 `--tools "Read,Grep,Glob"` 裁剪工具集 + `--strict-mcp-config` 不加载 MCP 实现只读；**这是工具层约束、非 OS 沙箱**。其文件读取范围不受目录限制（能读绝对路径），安全依赖"工具集不含写/联网/执行工具"这一纪律——故工具白名单不得擅自加入 Bash/WebFetch/WebSearch。

其余硬护栏（并发上限、子代理总数上限、单任务超时、未知字段拒绝、prompt 长度上限、`{{result}}` 不可信边界注入）**后端无关，全部沿用**。

## 8. 测试计划

- 新增 `tests/mock_claude.py`：伪造 claude `-p --output-format json` 的信封到 stdout（`{"type":"result","subtype":"success","is_error":...,"result":...,"structured_output":...,"usage":...}`），退出码可控；可模拟 `is_error:true`、非零退出、无 `structured_output` 等分支。
- 测试注入旗标：新增 `--claude-cmd`（读模式，与现有 `--codex-cmd` 并列，按 backend 取用）。读模式低危，沿用 v0.1 对 `--codex-cmd` 的放行策略，不加 `DYNWF_TEST_MODE` 限制。
- 新增/补充用例：
  1. backend 选取优先级（CLI > spec > 默认）与持久化到 `spec.resolved.json`/`summary.json`。
  2. `validate_spec` 接受合法 `backend`、拒绝非法值。
  3. claude 命令构建：含/不含 schema、含/不含 effort，参数顺序与内联 schema 正确；`-- prompt` 分隔。
  4. claude 读模式在 spec `workdir` 下运行（验证用 `cwd` 而非 `-C`）。
  5. 信封解析：有 schema 取 `structured_output`、无 schema 取 `result`；`is_error`/非零退出 → error；信封不可解析 → error。
  6. token 来自信封而非日志刮取。
  7. argv 长度护栏：prompt+内联 schema 超限时拒绝。
- 现有 codex 测试保持通过（回归）。

## 9. 明确不做（YAGNI / 留待后续）

- claude **写模式**（无 OS 沙箱，需单独安全设计）。
- claude 读模式的 **Bash/只读 shell**（`-p` 无人模式行为不确定，复杂度高）。
- `--bare` 隔离、`--model` 钉死、`--setting-sources` 裁剪等成本/隔离优化。
- 写模式 spec 的 backend 字段。

## 10. 风险与已知局限

- **成本**：claude 读后端单价显著高于 codex（§6）。使用者需知情。
- **非完全可复现**：claude 子代理行为受 workdir 链 CLAUDE.md/skills 影响，v1 未完全隔离。
- **读取范围不受限**：claude 读子代理可读任意绝对路径文件（含敏感配置）；安全靠"工具集无写/联网/执行能力"。不得放宽工具白名单。
- **依赖本机 claude 登录态与版本**：基于 2.1.183 的 CLI 行为；信封字段名（`result`/`structured_output`/`usage`）若随版本漂移需复核。
