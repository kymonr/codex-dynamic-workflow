# Dynamic Workflow 接入片段

把下面规则按需合并到工作区 `AGENTS.md`，不要覆盖已有的范围、安全和项目规则。

- 默认使用 **Simple Swarm**：普通分析、审核、研究、设计、诊断或实现存在至少两个依赖已就绪、可独立交付且不大面积重叠的分支时，派出 2–6 个窄 subagent。
- 只有一个隐式分支、短任务、强串行工作、多个简单读取，或委派成本高于收益时，由 root 直接完成。显式 `$dynamic-workflow` 或明确要求 subagent 时可派一个有界分支。
- 每个分支只负责一个问题、一个模块或通常 1–3 个主要文件。禁止把 CLI、runtime、Writer、安全和测试打成一个综合工作包。
- root 不重复调查正在由 child 处理的范围，只负责拆分、未覆盖范围、冲突解决、效果读回、验收和最终回答。
- Simple Swarm 的协调等待仅为保持 root 响应而有界且事件驱动，不是 child 生命周期预算或 deadline。首次 timeout 最多允许一次非中断的 partial/progress 请求；健康运行中的 child 可继续更长的 bounded wait，并提供有用的用户更新，不得反复提示进度或轮询状态。后续 timeout、等待次数或静默本身绝不授权 interrupt、close、重新拆分、reroute、replay 或重复执行；终止和 hard-stop 遵循 `skill/references/dag.md`，hard-stop 后先核对实际 effects。健康但暂时变慢的 child 仍留在 Simple；只有 checkpoint/resume、Human Gate、conditional flow、bounded loop、持久长运行恢复或正式 artifacts 才启用 Managed Workflow，不因超过两次等待而启用。两次以上等待的 live 行为仍是未证明的 `UNKNOWN`，不得声称已有可执行 liveness。
- Spark / Explorer 处理窄只读问题；Luna 负责 facts、constraints、current-state inspection、non-selecting organization、evidence verification 和格式化已决定的 plan；Sol 负责创建/修订 design candidates、选择 alternatives、解决 material tradeoffs、推荐 target design 和 design judgment。未显式指定 native 模型的写入默认使用 Sol，用户显式指定 Luna 写入时可由 Luna 担任唯一 scoped writer；root 保留 mode 选择、effects 读回、adoption 和 final acceptance。
- 只有明确需要 checkpoint/resume、Human Gate、bounded loop、长时间恢复或正式运行产物时，才启用 Managed Workflow。
- 用户明确指定 Agent Fleet，或自然要求深度审核、全面检查、对抗审核、多代理复核、仓库深审等需要质疑与独立复现的任务时，使用原生 Agent Fleet。按范围自动选择 4、6、8 个界面可见的顶层 subagent，配比分别为 `3 Luna + 1 Sol`、`5 Luna + 1 Sol`、`6 Luna + 2 Sol`。启动前公开规模、分工和原因后直接开始；Luna 负责 discovery/challenge/reproduction，Sol 复核证据、严重度、共同盲点和结论。root 必须公开处理每个重要 Sol 意见，禁止多数票抵消已复现的严重问题，未解决冲突记为 `UNKNOWN`。
- 只有用户明确授权隔离 candidate 时，才启用 Writer Workflow / Worktree Writer v2。该模式只接受 package v2，并固定使用 Sol/high Writer 与 fresh read-only Sol/xhigh reviewer；CLI、package 和模型输出都不能选择 Writer。
- Grok 不作为 native subagent、writer、native reviewer、fallback 或 recovery。只有用户明确要求且 candidate 已冻结时，才创建独立可见的只读二审对话任务。
- commit、push、PR、merge、release、deploy、cleanup、凭据和其他外部或高风险动作始终由 root 持有。
