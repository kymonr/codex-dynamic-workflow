# 独立 Luna 探索池验收

历史记录：下述 CLI 路线已被用户随后明确的“不要走cli，全都走原生的”替代。当前派工规则见项目 README；本报告保留当时的验证事实，不再作为启用 CLI 的依据。

本地实现、安装与限定范围验收完成。Luna 的探索和验证默认通过独立只读 CLI 进程池执行；需要的 Astra 仍使用原生代理。同一授权范围和额度内不按批次重复确认，显式后端指令优先。

## 行为与边界

- 可以按多个独立方向批量探索、找反例和验证；答案不必预先已知。每个方向声明来源、交付物、覆盖或截止条件。高风险结论、writer 和关键独立验收继续留给主线程及必要的 Astra。
- `luna-pool --workers <width>` 使用真正的独立 CLI 进程，不调用原生 `spawn_agent`。每个调用保持 readonly sandbox，并使用 ephemeral 和禁止嵌套代理的本地 CLI 参数。需要的 Astra 无须等待无关 Luna 支线。
- `execution_pool=luna` 的不可变合同只允许合格的 ordinary Luna/max 或机械 Luna/medium 节点；后续 `add` 同样不能加入 strong、高风险或 writer 节点。
- `capacity_scope=backend` 只改变容量计数，文件冲突和单 writer 锁仍覆盖同一个协调 DB。缺失 scope 或显式 database 的旧合同保持原语义；旧 native 数值容量仍会计入 exec 保留，不能声称自动改造旧合同。
- Luna 使用独立声明的总次数、截止时间和进程宽度；主线程合并核算整个任务，并保留必要 Astra 额度。大量派发不意味着零资源或零账号用量，也不允许重建 run 消除已消费次数。
- 取消停止新准入；进程回收由既有 Job Object/process-group 执行器确认。未知 transport 状态继续保留占用，不退款、不自动重试。提交先入队后失败时，启动门闩阻止队列中的 worker 继续启动。

## 自动检查与独立复核

| 检查 | 实际结果 |
|---|---|
| 完整回归 | 248 项执行，247 通过，1 项因 Windows 符号链接权限跳过，56.899 秒 |
| 新增池与容量回归 | 17 项，覆盖旧合同、跨 backend 与同 backend 容量、DB-wide 写锁、并发准入、固定路由、依赖补充、取消、未知 transport 和入队失败 |
| 真实本地进程 fixture | 6 个独立进程共同到达启动屏障，均完成并确认进程树回收；没有调用模型 |
| 公共 CLI 示例 | init/create/status/luna-pool help 通过，2 个节点，0 次模型调用 |
| 包校验器 | PASS |
| 默认路由最后调整 | 98 项 package/contract 检查通过；Runtime 执行代码未改动 |
| 独立源码复核 | Astra/high 请求的非作者审阅 13 个冻结候选，含新文件全文与旧安装对照；纯内存入队后失败探针通过，未发现具体阻断项 |
| 验收脚本与示例复核 | 单独检查两个新增文件；并发措辞按观测能力收窄，脚本新增优化模式拒绝入口 |

测试中的已修正失败如实保留：首次取消检查把待派节点误期望为 pending，既有取消行为实际是 cancelled；首次完整回归保留了“never CLI children”的旧断言。公共 CLI 的第一次临时探针忘记关闭它自己打开的 SQLite 连接，临时目录清理失败；修正探针关闭逻辑后完整通过。这些失败不计为通过，也不是被隐藏的产品失败。

## 真实安装调用

实际 run：`6a2c722aec93427ca929e8ef590335e8`。通过已安装的 Runtime 执行两次真实只读 `codex exec`，没有自动重试。

| 任务 | 返回的数值证据 | helper 身份 | 观测区间（UTC） |
|---|---|---|---|
| invoice | `expected=90; actual=110` | 56624 | 10:20:52.750211 至 10:21:29.299759 |
| stock | `expected=0; actual=-2` | 46552 | 10:20:52.774137 至 10:21:34.267805 |

两个 CLI 调用均成功，owned transport 观测区间重叠约 **36.532 秒**。开始记录发生在 helper 绑定后、目标 CLI 接收启动输入前，结束记录发生在整棵树清理返回后；因此不把它当作服务端模型推理严格同时执行的证明。

两次调用均请求 `gpt-5.6-luna / max`；有效模型身份为 `UNKNOWN`。观测用量合计：input 149653、其中 cached input 97280、output 2504。未根据这些计数推算货币费用。

Runtime 完成验收，`used=2`、`strong_used=0`、`execution_holds=0`、所有资源保留已释放；原始来源与 Runtime 文件未变。除脚本内新连接核对外，主线程又用独立 Python 进程导入安装位置的 Runtime，以只读方式重新打开 DB，status/events 与记录完全一致。

Astra 原生验收复核已正常派出并完成。后续 `list_agents` 观察时 Luna 已结束，故该观察文件不作为三路实际同时运行的证据。实现不调用原生工具来启动 Luna；没有测量宿主内部精确槽位计数，也没有进行 Luna/Astra 质量对照基准。

## 安装与候选

确认的 `CODEX_HOME` 进程值和用户值均为 `D:\CodexData\.codex`。

- 首次池安装：11 个文件更新，25 个受管文件全部验证。回执：`reports/install-backup-d19099330bbc/receipt.json`。
- 最终默认路由安装：4 个说明/策略文件更新，25 个受管文件全部验证。回执：`reports/install-backup-f0075643072b/receipt.json`。
- 最后逐字节比较：25/25 与源码一致；安装 dry-run 无待更新项，旧兼容入口继续保持停用。
- 独立审阅、真实调用和最终安装的四个 Runtime 执行文件 SHA-256 一致。最后的默认路由文案与 validator 声明由主线程读回并通过针对性检查。
- 真实调用使用的验收脚本 SHA-256 为 `0d03cd53671da7fff39b585aa4080697c80b508dd4fb3c5649e3ffabb2b367e4`。之后仅收窄并发措辞并新增优化模式拒绝入口；普通 Python 优化级别现场为 0，`python -O` 被入口拒绝的检查通过，没有再消耗模型调用。

机器可读证据位于 `D:\codex\temp\dynamic-workflow-luna-20260906\`：`pool-candidate-sha256.json`、`pool-final-sha256.json`、`pool-final-verification.json`、`pool-live-installed/result.json` 和该目录中的只读运行 DB。它们是本地验收记录，未发布到 Git。

本轮没有 commit、push、PR、merge、部署、全局配置修改或旧仓库清理。独立发布 clone 仍保持先前提交 `d302ae0` 的干净状态；新源码变化尚未同步到该 clone。
