# dynamic-workflow v0.1 完工报告

> 2026-06-13。给 codex 桌面版的「只读多子代理并行编排」技能。

## 这是什么
把一个大任务拆成多个**只读** `codex exec` 子代理并行执行，由确定性脚本 `src/runner.py`
调度，结果汇总在运行目录的 `summary.json`。安装在
`C:\Users\Orz\.codex\skills\dynamic-workflow\`，用户说「并行审查/调研 X」时触发。

## 怎么造出来的
- 计划经**三轮 codex 评审**定稿（P1 收敛 5→7→3，每轮新发现集中在上一轮新增的代码），
  存 `docs/plans/2026-06-13-dynamic-workflow-skill.md`。
- **M0+M2**（脚手架 + 调度器 + 全部离线测试）：Claude 盯着 codex 带网 workspace-write 派工
  跑出，逐项验收（回退沙箱妥协、清理 429 个测试残留）后主环境复跑全绿。
- **M1**（环境探针）/ **M3**（SKILL + 装技能 + 真实冒烟）：codex 桌面版执行。

## 文件清单
- `src/runner.py`：spec 白名单校验 / 子代理命令白名单拼装（prompt 前加 `--` 防选项注入）/
  带随机 nonce 的不可信数据注入边界 / 单任务执行（超时 `taskkill /F /T` 杀进程树）/
  并发上限 / 多阶段流水线 / schema 自动补 `additionalProperties:false` / CLI 入口与退出码
- `tests/`：9 个测试文件，**47 个离线用例**（全走 mock，不调真实 codex）
- `skill/SKILL.md`：技能正文（触发条件 / 硬性边界 / spec 格式 / 子代理身份写法）
- `README.md`：含任务 1 探针的环境结论

## 测试与验证
- **离线**：`py -m unittest discover -s tests -v` → **47 tests OK**（完整输出见 `docs/evidence/unittest-final.txt`）。
- **真实冒烟**（post-fix：`D:\.codex-tmp\workflows\smoke-review-runner-20260613-133032-989645-8407f4`）：3 个只读子代理
  （2 并行审查 runner.py + 1 汇总），并发 2，五条验收全过——退出码 0 / ok=3/3 /
  out.json 合法且过最小 schema / 注入带 `UNTRUSTED-<nonce>` 边界 / 并发 2 时序正确 / 项目零污染。
  证据见 `docs/evidence/`（smoke-spec.json + smoke-summary.json）。
- **意外收获**：冒烟子代理审出 runner.py 的后续边界问题；prompt 分隔、Windows 保留名、
  task id 大小写碰撞、run_dir 秒级碰撞已修，schema 深度校验仍记为已知限制。

## 环境结论（任务 1 探针）
- codex exec 在受限沙箱内会因写不了 `.codex` 状态库而失败，**runner 真实运行必须升级权限/沙箱外**。
- PATH 上的 codex 是 `.CMD` 垫片，Python 无法直接启动；`DEFAULT_CODEX_CMD` 已填真实
  `codex.exe` 绝对路径。
- 嵌套生子代理：结果 B（沙箱内失败、升级权限成功），本环境可运行。

## 冒烟后修复批次（2026-06-13）
1. `build_cmd` 给 prompt 前加 `--` 分隔符（挡 `-` 开头 prompt 被当选项、防护栏绕过）。
2. `validate_spec` 拒绝 Windows 保留设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）做 task id。
3. SKILL spec 示例补 `additionalProperties:false` + 文档说明。
4. runner 自动给 schema 的每个 `type:object` 补 `additionalProperties:false`
   （OpenAI 结构化输出 strict 的硬要求，让技能开箱即用）。
5. `validate_spec` 对 task id 按 Windows 大小写不敏感规则去重，避免 `a` / `A` 目录碰撞。
6. 默认 run_dir 加微秒和随机后缀；`run_workflow()` 遇到已存在 run_dir 直接失败，拒绝覆盖。
   均含新测试，47 全绿。

## 已知限制（v0.1）
- schema 校验只查顶层 object 与 required 存在，不验字段类型（标准库无 JSON Schema 校验器）。
- 真实运行需升级权限/沙箱外（codex 写状态库所限）。
- `DEFAULT_CODEX_CMD` 是本机 npm 深路径，codex 升级后 vendor 目录可能变，需按探针重填。
- `agent.log`/schema 大小无上限；同时多开 runner 可绕过单次总数上限（靠「用户手动触发、不无人值守」纪律兜）。
- junction/符号链接 reparse-point 时序越界属深度防御，未做。
- 只读 v0.1：不做并行写文件（写并行走 Claude Code 的 codex worktree）。

## 哪些没测
- 并发 8 的极限；真实冒烟只验了并发 2、单条两阶段流水线。
- `taskkill` 进程树清理只有逻辑、无自动化测试。
- Windows 保留名和大小写碰撞只测了校验拦截，没测「真用 CON / a+A 跑会崩」（已被校验挡在前面）。
