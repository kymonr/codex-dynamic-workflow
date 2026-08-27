# Dynamic Workflow 接入片段

把下面规则按需合并到工作区 `AGENTS.md`，不要覆盖已有的范围、安全和项目规则。

- 默认使用 **Simple Swarm**：普通分析、审核、研究、设计、诊断或实现存在至少两个依赖已就绪、可独立交付且不大面积重叠的分支时，派出 2–6 个窄 subagent。
- 只有一个隐式分支、短任务、强串行工作、多个简单读取，或委派成本高于收益时，由 root 直接完成。显式 `$dynamic-workflow` 或明确要求 subagent 时可派一个有界分支。
- 每个分支只负责一个问题、一个模块或通常 1–3 个主要文件。禁止把 CLI、runtime、Writer、安全和测试打成一个综合工作包。
- root 不重复调查正在由 child 处理的范围，只负责拆分、未覆盖范围、冲突解决、效果读回、验收和最终回答。
- Simple Swarm 禁止嵌套委派。一次 bounded wait 后只做一次进度检查；第二次仍无有效交付且阻塞完成时，关闭并重新拆小或由 root 接管。
- Spark / Explorer 处理窄只读问题；Luna 处理普通任务和明确授权的 scoped writing；Sol 处理复杂或高影响任务。
- 只有明确需要 checkpoint/resume、Human Gate、bounded loop、长时间恢复或正式运行产物时，才启用 Managed Workflow。
- 只有用户明确授权隔离 candidate 时，才启用 Writer Workflow / Worktree Writer v1。
- Grok 不作为 native subagent、reviewer 或自动 fallback。只有用户明确要求新建 Grok 对话任务时，才创建独立可见任务。
- commit、push、PR、merge、release、deploy、cleanup、凭据和其他外部或高风险动作始终由 root 持有。
