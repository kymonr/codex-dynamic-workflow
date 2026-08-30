# Dynamic Workflow 接入片段

把下面规则按需合并到工作区 `AGENTS.md`，不要覆盖已有的范围、安全和项目规则。

- 默认使用 **Simple Swarm**：普通分析、审核、研究、设计、诊断或实现存在至少两个依赖已就绪、可独立交付且不大面积重叠的分支时，派出 2–6 个窄 subagent。
- 只有一个隐式分支、短任务、强串行工作、多个简单读取，或委派成本高于收益时，由 root 直接完成。显式 `$dynamic-workflow` 或明确要求 subagent 时可派一个有界分支。
- 每个分支只负责一个问题、一个模块或通常 1–3 个主要文件。禁止把 CLI、runtime、Writer、安全和测试打成一个综合工作包。
- root 不重复调查正在由 child 处理的范围，只负责拆分、未覆盖范围、冲突解决、效果读回、验收和最终回答。
- Simple Swarm 禁止嵌套委派。一次 bounded wait 后只做一次进度检查；第二次仍无有效交付且阻塞完成时，关闭并重新拆小或由 root 接管。
- Spark / Explorer 处理窄只读问题；Luna 默认处理普通只读任务；未显式指定 native 模型的写入默认使用 Sol，用户显式指定 Luna 写入时可由 Luna 担任唯一 scoped writer；Sol 也处理复杂或高影响任务。
- 只有明确需要 checkpoint/resume、Human Gate、bounded loop、长时间恢复或正式运行产物时，才启用 Managed Workflow。
- 用户明确指定 Agent Fleet，或自然要求深度审核、全面检查、对抗审核、多代理复核、仓库深审等需要质疑与独立复现的任务时，使用原生 Agent Fleet。按范围自动选择 4、6、8 个界面可见的顶层 subagent，配比分别为 `3 Luna + 1 Sol`、`5 Luna + 1 Sol`、`6 Luna + 2 Sol`。启动前公开规模、分工和原因后直接开始；Luna 负责 discovery/challenge/reproduction，Sol 复核证据、严重度、共同盲点和结论。root 必须公开处理每个重要 Sol 意见，禁止多数票抵消已复现的严重问题，未解决冲突记为 `UNKNOWN`。
- 只有用户明确授权隔离 candidate 时，才启用 Writer Workflow / Worktree Writer v2。该模式只接受 package v2，并固定使用 Sol/high Writer 与 fresh read-only Sol/xhigh reviewer；CLI、package 和模型输出都不能选择 Writer。
- Grok 不作为 native subagent、writer、native reviewer、fallback 或 recovery。只有用户明确要求且 candidate 已冻结时，才创建独立可见的只读二审对话任务。
- commit、push、PR、merge、release、deploy、cleanup、凭据和其他外部或高风险动作始终由 root 持有。
