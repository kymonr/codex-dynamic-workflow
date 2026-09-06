# Codex Dynamic Workflow v3.0.0 — 本机交付报告

日期：2026-09-06。源码和安装副本已升级至 3.0.0；原生兼容入口为 3.0.0-compat。
工程交付与 readonly exec 集成已验证。**原生 Runtime 的真实端到端验收被工具安全检查阻止，本轮不标记“双后端全部收口”。** 这不等于原生桥接代码缺失，也不能用模拟回执或旧版 Skill 原生可用性代替新桥接验收。
没有执行 commit、push、merge、git init、发布、依赖安装、ACL 修改或保存的全局配置修改。专属 RDC 会话 PID 8916 保留供该项目使用；未混用其他项目终端。

## 实际位置
- 源码：`D:\codex\projects\codex-dynamic-workflow`。
- 正式 Skill：`D:\CodexData\.codex\skills\codex-dynamic-workflow`。
- 安装 Runtime：上述 Skill 内的 `scripts/cwf_runtime/`，入口 `scripts/cwf.py`。
- 项目内入口：`scripts/workflow.py`；正式调用仍为 `$codex-dynamic-workflow`。
- 旧入口 `dispatching-native-agents` 仍为 explicit-only compatibility alias，不运行第二套工作流。
- 恢复回执：`reports/install-backup-f4f91ed8bf82/receipt.json`。

## 实际实现
Runtime 显式启用后，以 SQLite 统一管理动态图、依赖、尝试记录、预算与事件。图扩展、准入扣账和事件写入在事务中执行；根代理提出任务，但不能绕过 Runtime 对该 run 再维护一套派工额度。
原生与 exec 两个执行接口共享任务、预算、来源与结果合同；每个 run 的后端固定。原生接口是可信宿主桥接，不是 Python 伪造 spawn_agent；exec 是真实前台只读执行器，不是原生工具缺失时的静默替代。
必要检查预留总调用和强模型额度；并发准入不能超额占用。失败、重试和不确定派工保留消耗；缺失 usage 记 UNKNOWN，不记零。没有硬 Token 或费用封顶。
原始来源绑定字节指纹，直接读取原文件；派生 claim 不覆盖原始证据。结果绑定 attempt fencing token；重复相同结果幂等，旧或冲突结果拒绝。高风险/写入验收需要适当的非作者、同候选原始来源核验。
支持显式只读 retry/resume：先确认旧任务终结，再验证来源与合同；保留原预算和历史。写入任务不自动重放。改变模型、后端或权限不被解释为同一安全恢复。
同一协调 DB 默认只允许一个 writer，包括不同根目录/worktree；重叠读取和写入也需协调。此为合作式锁，不是 OS 沙箱；其他 DB 和外部编辑器不受其控制。
exec 使用原始 argv 与 stdin、结构化终态与实际用量。Windows 以 gated worker 与 Job Object 管理任务进程树，并确认活动进程归零；POSIX 对自有进程组清理，无法确认终止时保留占用。
CLI 提供 create/add/next/bind/complete/release/retry/resume/refresh/cancel/status/events/claims/decide/finish/exec-one。状态读取不创建缺失数据库。安装副本不依赖源码目录或额外 pip 包。

## 有意保留的范围边界
普通 Skill-only 原生模式仍可使用，但不享有 Runtime 持久化与事务保证。Runtime 必须显式选择，不自动改变现有会话。
exec 写入未开放；原生写入依赖实际宿主授权和关闭回执。删除操作明确不支持自动验收：实际发生时记 partial/blocked_effects，不恢复用户源码，不自动重放 writer。
没有自动嵌套工作流、后台 daemon、自动后端交接、完整写任务恢复、OS 文件隔离或复杂 Web UI。`exec-one` 是有限前台单任务执行器；竞争控制器可安全领取独立任务，本版没有自动启动并行 worker 池。
有效模型/effort 取决于真实宿主。测试请求 Astra/high，但未获得独立有效模型身份回执，仍记 UNKNOWN。已有桌面会话热加载和自动触发未实测。

## Review 与修复闭环
第一次独立只读 review 确认五项缺陷：正常退出遗漏后代清理、旧 turn 终态错误绑定新结果、历史来源在准入/验收处不一致、删除验收边界、畸形枚举字段导致 TypeError。全部修复并加入具体回归。
第二次独立 review 支持上述主要修复，另找出“畸形结果 + 来源不可读”时失败记录再次报错而漏释放。修正为已确认传输终止后 finally 释放；未知进程终止状态仍然保留占用。
第三次窄范围 review 对新增清理与跨根 writer 约束未发现具体静态阻断，但其内存探针因自身夹具错误未有效完成，动态通过数为零；没有将其记作通过。本机对应动态回归已经执行并通过。
Root 还修复了硬链接写范围别名、旧失败 attempt 借用重试成功状态、同一原生代理换节点名自审、历史探索被误当成当前证据等边界。
实际 exec 初次调用因来源路径格式不符合严格协议而失败，失败记录/预算保留，夹具未改，占用已释放。随后明确提示词必须返回 packet.task.sources 中的相对 ID，不放宽路径验收；并保留合法已观察 usage 到失败结果。
最后一轮实际只读 exec 同时进行了小改动的非作者复核：原始四文件指纹匹配，12 个非法来源/证据路径内存案例拒绝正确、usage 保留，未发现本次小范围的具体阻断。报告明确其内存 Runtime 替身不等于数据库测试；外围 Runtime 本身进行了真实 SQLite/进程端到端验收。

## 实际验证结果
| 验证 | 结果 |
|---|---|
| 完整 Windows 回归 | 180 项执行：179 通过、1 跳过；原有 93 项保留 |
| 跳过项 | 宿主不允许创建真实符号链接；未提权或修改权限 |
| 补充链接边界 | 无特权重解析点拒绝测试、真实硬链接拒绝测试通过 |
| Package validator | PASS |
| 实际只读 exec | PASS：真实任务 completed，来源未漂移，active_holds=0，usage 已记录 |
| 实际原生 Runtime | BLOCKED：安全检查在启动前阻止测试，原生测试子代理数 0 |
| 安装 | 默认原子替换，更新 15 个文件；31/31 与源码及 ownership 一致 |
| 安装后 CLI | version=3.0.0；成功只读重开真实运行数据库并确认有效 completed |
| 安装后 dry-run | changes=[] |
| 既有三个 cwf profile | 内容与安装前一致 |
| 新会话 Skill 目录发现/桌面热加载 | 本轮未运行额外模型验证，不以文件存在冒充已验证 |

真实成功 run：`2547379417d849f0bddf6d7ddb01e62e`。DB：`.delivery/v3-exec-contract-edcf17f6/runtime.sqlite`。
该 run 用量：input_tokens=180035，cached_input_tokens=137600，output_tokens=2910；是工具返回的观测值，不推算货币成本或性能收益。初次失败 run 单独保留，不被清空或计为成功。
本轮实际 primary 模型调用共五次：三次只读 review、一次失败 exec smoke、一次成功 exec smoke/小改动独立核验。没有实现 writer 模型调用；最后一次使用原计划未消耗的实现调用额度，不突破总额度。原生 smoke 没有启动。

## 使用
在项目目录查看帮助或创建持久任务：
```text
python -B scripts/workflow.py --version
python -B scripts/workflow.py --db .delivery/runtime.sqlite init
python -B scripts/workflow.py --db .delivery/runtime.sqlite create --plan examples/runtime-exec-readonly.json
python -B scripts/workflow.py --db .delivery/runtime.sqlite exec-one --run 返回的RUN_ID
python -B scripts/workflow.py --db .delivery/runtime.sqlite finish --run 返回的RUN_ID
```
最后三个命令使用真实返回的 run ID；exec-one 会调用模型并消耗额度，示例文件中的故意错误夹具不会被修复。不要将示例结果作为业务项目审核结论。
安装入口可直接使用：`python -B D:\CodexData\.codex\skills\codex-dynamic-workflow\scripts\cwf.py --version`。无须源码目录位于当前工作目录。
日常 Skill 调用保持 `$codex-dynamic-workflow`；选择 Runtime 时，原生/exec 后端、DB、范围与授权必须明确。普通 Skill-only 使用不获得数据库恢复和硬调度保证。

## 相比 v2.0.2
v2 的派工、计数和状态主要依赖会话合同；v3 的显式 Runtime 将图、尝试、调用预留、事件和结果身份落实到数据库事务中，重启后可以检查历史并在满足条件时恢复只读任务。
收益是并发准入可验证、必要核验额度不会被可选任务挤掉、重复/过期结果被隔离、失败和未知状态可追溯。模型角色、预算逻辑和证据原则仍与 Skill 共享，不新造一套冲突规则。
代价是数据库和 CLI/host 回执需要维护；默认跨 root 的单 writer 更保守；合法来源范围、候选刷新与关闭回执需要精确管理。raw-first 可能重复读取，不能承诺 Token 更低或速度更快。

## 原始记录
- `v3-final-regression.log`：完整回归。
- `v3-readonly-review.md`、`v3-readonly-followup.md`、`v3-readonly-final.md`：三次独立只读 review 原文，包含实际覆盖和失败探针说明。
- `v3-review-dispositions.md`：修复与验证处置。
- `v3-live-exec.json`：首次真实调用失败记录；`v3-live-exec-retry.json`：成功的真实 Runtime 执行、事件、用量、源指纹与小改动 review。
- `v3-live-delta-review.md`：最新小改动独立核验摘要。
- `v3-live-native.json`：真实原生测试未启动的阻塞记录。
- `v3-install-preflight.json`、`v3-install-atomic-result.json`、`v3-install-verification.json`：安装前后状态和恢复回执。

结论：**已交付并安装可执行的 v3 Runtime，已完成确定性测试、只读 review/修复和真实 readonly exec 验收；原生 Runtime 真实集成仍为 BLOCKED，不宣称整个双后端 v3 已完全收口。** 没有剩余已知代码阻断项于本轮已审查/测试的范围内，也不保证不存在其他缺陷。
