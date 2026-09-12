# 原生验收采集器与零模型 runner 接手审查 — 2026-09-11

## 当前结论

**零模型采集链路与 runner 集成已通过；正式原生模型验收仍未通过。**

接手基线为 `abecfba5baac763c07a8eaaec721d00a6f6245aa`，分支为 `codex/astra-mainline-luna-supplement`，PR #41 保持 Draft。历史被测产品源码仍为 `4e795ac779f801bd358933cd21747a38675b58d3`。本轮没有修改 Skill、profiles、Runtime、比较器、已安装文件、权限配置或旧验收数据库；没有新增原生模型回合，没有提交、推送或发布。

真实 Git checkout 为 `D:/codex/temp/codex-dynamic-workflow-v4-20260909`。原专属 RDC PID 51300 在 Desktop Commander 重连后消失，后续重新建立本项目专属长期终端 PID **20896**；没有接管其他项目会话。

历史事实仍以 [HANDOFF.md](HANDOFF.md)、[observations.json](observations.json) 和既有状态文件为准。本文件不覆盖旧失败、预算、UNKNOWN、claims 或资源 holds。

## 对交接后修复快照的三个可复现 finding

以下均用 AST 仅提取 `collector-fixed.py.txt` 的采集函数，配合内存事件与 RPC 替身复现；没有导入或运行原生 runner。

| Finding | 位置与反例 | 影响 |
| --- | --- | --- |
| F1：一次元数据读取错误阻断后续采集/清理 | `snapshot()` 批量读取中让 child-a 首次读取失败 | 后续线程漏采；清理入口若依赖同一批 snapshot，会跳过逐线程收尾 |
| F2：只收到 `thread/started` 时漏记新线程 | 事件中的线程 ID 位于 `params.thread.id`，旧逻辑只取顶层 `threadId` | parent 已结束、子线程尚无 turn 时可能提前判定 settled |
| F3：观察到线程不等于获得控制权 | 任意非 parent turn ID 会进入 `known`，该集合又用于 archive/interrupt/unsubscribe | 缺少父子归属核验，无关事件可能进入可变更目标集合 |

这些反例证明交接后的修复快照仍有缺口；并不证明三者都发生在历史原生运行中，也不是 workflow 产品源码缺陷的证明。

## 采集状态机与 runner 候选

[collector_candidate.py](collector_candidate.py) 区分 observed IDs 与有实际 `parentThreadId` 证据的 owned IDs；从嵌套 `thread/started`、turn 与 item 事件登记线程。单次 metadata step 最多做一次有期限读取，单线程失败不会阻断其他线程；生命周期终态、工具结束、host active 状态、unsubscribe 和 `thread/closed` 分开记录。未知身份、权限与资源回收不会自动补成预期值。

[runner_candidate.py](runner_candidate.py) 是可执行的任务级 subprocess/JSON-RPC runner 候选。它不内置 Codex 可执行路径、模型名、Runtime 写入或自动审批；启动命令、线程参数和控制输入必须由调用方显式注入。证据 journal 使用新目录、append-only timeline 和排他 summary 创建，避免覆盖既有原始证据。

实现后重新以代码审查者视角复核，而不是默认第一版设计正确。除 collector 的 active/tool/status/代数竞态外，本轮又抓到 runner 的一个关键优先级缺陷：第一版 `run()` 会在控制器看到最新 mainline 完成事件前执行一次 `thread/read`。修复后循环顺序为 **先排空 host 事件 → 控制器决定必要 verifier/stop → 再允许可选 metadata RPC**。

## 零模型 runner 集成验证

`tests/test_native_acceptance_runner.py` 使用真实 Python 子进程承载 synthetic JSON-RPC host；fixture 明确记录 `model_calls=0`、`network_calls=0`。测试覆盖：

- main 完成后才触发 verifier；触发时 3 个 Luna 仍处于 in-progress；
- `turn/steer` 必须早于任何 `thread/read` 元数据补查；
- child-main 首次 metadata 读取失败后仍轮转到其余线程并最终补齐；
- 6 个 turn、父子 lineage、settings、item/turn terminal、逐线程 unsubscribe 与 `thread/closed` 分开记录；
- 不调用 `turn/interrupt` 或 `thread/archive`，不把 unsubscribe 冒充资源回收；
- start 失败、控制失败、非 JSON host 输出和 summary 冲突均保留为显式失败。

最终 runner 专项：**6/6 PASS**。collector 专项：**33/33 PASS**；`python -B -O` 同样 33/33 PASS。原交接离线 replay 继续 PASS，历史事件和快照未改写。

另做了一次真实 Codex **0.154.0** app-server transport 预检：仅启动 `app-server --listen stdio://`、调用 `initialize`、发送 `initialized` 后关闭；进程退出码 0，无 stderr。该预检没有 `thread/start`、没有 `turn/start`、没有模型调用，不能当作原生模型验收。完整本机记录为 `D:/codex/temp/cwf-zero-model-final-20260911/app-server-transport-preflight.json`。

## 四个 subprocess 超时的处理

接手时四个测试方法在完整回归中反复出现 15/20 秒超时；单独运行则约 0.2–1.2 秒。简单把上限提到 60 秒仍能在完整回归中复现超时，因此没有用“延长 timeout”作为最终修复。

最终修复的是测试子进程隔离边界：这些 correctness tests 改为直接执行自包含脚本入口，并使用 `-E -S -B`、`stdin=DEVNULL` 和文件承载 stdout/stderr；原 15/20 秒硬上限已恢复。这样不依赖父测试进程的 PYTHON/site/stdin 环境，也不把管道 EOF 行为混进 CLI 正确性检查。

无法从现有证据把此前的长停顿唯一归因到某一个 user-site 模块或宿主组件，因此不宣称更细的根因。可确认的是：产品 CLI 单独连续执行稳定在亚秒到约 1 秒量级，而上述隔离修改后完整回归不再复现超时。

## 最终验证记录

| 检查 | 结果 |
| --- | --- |
| collector 专项 | 33/33 PASS |
| collector `python -B -O` | 33/33 PASS |
| runner 零模型 subprocess 集成 | 6/6 PASS |
| 四个原超时测试（原 15/20 秒上限） | 4/4 PASS，约 2.1 秒 |
| 真实 Codex app-server initialize-only | PASS；Codex 0.154.0；0 thread / 0 turn / 0 model |
| 完整回归 | **427 项：425 PASS、2 skip、0 failure/error；103.954 秒** |
| Package validator | PASS |
| 新原生模型回合 | **0** |

两个 skip 仍为宿主不允许创建 symlink、卷未提供 8.3 alias；不是本轮新增失败。

完整本机日志位于 `D:/codex/temp/cwf-zero-model-final-20260911/`，包括多轮失败回归、最终通过回归、四项专项和 app-server transport preflight。失败历史全部保留，没有用最终 PASS 覆盖前面的超时证据。

## 仍未满足的正式原生验收

本轮证明的是 **零模型 runner/collector 的调度、采集、异常与证据链**，不是模型身份、权限和效果验收。`identity_validation` 仍未在真实子线程上执行，`host_resource_recycling` 仍不能由 unsubscribe 或进程退出补造；旧 `PARTIAL / NOT_QUALIFIED` 状态保持不变。

新的真实补验仍需要新的明确范围与额度。若后续获批，最小范围仍应为独立新 run：观察者 1、主线 1、必要独立 verifier 1、Luna 3；前置能力不满足即停止，不自动模型重试，不重跑六组成对试验，不降低比较器标准。只有实际子线程 model/profile/effort、只读能力、执行完成与资源释放回执全部满足后，才能改正式验收状态。
