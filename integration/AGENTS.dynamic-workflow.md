# Dynamic Workflow 接入片段

把下面规则按需合并到工作区 `AGENTS.md`，不要机械覆盖已有范围、安全和项目规则。

- 普通可并行任务默认使用 `Simple Swarm`：至少两条实质、依赖已就绪、可独立交付且低重叠的支线；单支线仅在用户明确要求 subagent 或隔离上下文明显有益时派发。
- 每个支线只负责一个主要问题、一个模块或责任范围，通常不超过三个主要文件；同一核心问题或明显文件重叠必须先重拆。
- Simple Swarm 默认只读，不使用 Workflow IR、checkpoint、Human Gate、bounded loop、evidence package 或 Worktree Writer。
- root 负责范围、授权、整合和最终验证；child 运行期间不要重复完成其整段调查。只有失败、shutdown 或明确重拆后才接管。
- 正常等待一次；仍运行时只做一次进度或部分结果检查，再无有效交付就关闭并重拆或由 root 接管。
- 窄而明确的只读问题可用 Spark / Explorer；普通任务和边界清晰的低风险写入用 Luna；复杂或高影响判断用 Sol。模型路线不能弥补错误拆分。
- Managed Workflow 仅在明确需要 checkpoint/resume、Human Gate、loop 或正式 artifacts 时启用；Worktree Writer 仅在明确要求隔离候选时启用。
- 默认只允许一个 native writer。Grok 不作为 native subagent 或自动 fallback；只有用户明确要求时才创建独立对话任务。
- root 保留效果读回、diff 审查、最终测试，以及 commit、push、PR、merge、deploy 和其他外部或高风险动作。
