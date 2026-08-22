# Dynamic Workflow 接入片段

把下面规则按需合并到工作区 `AGENTS.md`，不要机械覆盖已有的范围、安全和项目规则。

- 非简单请求先做一次轻量工作线判断。只要存在至少一条实质、依赖已就绪、可单独交付并由 root 验收，且并发或上下文隔离有实际收益的普通支线，就使用 `$dynamic-workflow`。
- 短任务、强串行工作、多个简单读取、没有可委派实质支线，或专用 Skill 已完整拥有分析、执行和验证流程时，不触发委派。
- 窄而明确的只读问题可用 Spark / Explorer；普通任务和边界清晰的低风险写入用 Luna；复杂或高影响任务用 Sol。
- Grok 不作为 native subagent、reviewer 或自动 fallback。只有用户明确要求新建 Grok 对话任务时，才创建独立可见任务。
- 默认只允许一个 native writer。Grok 与 native writer 并发写入时，必须遵守 `skill/references/worktree-parallel-dispatch.md`，使用独立 worktree 和互斥、封闭的 `owned_targets`。
- root 保留范围控制、效果读回、diff 审查、最终测试，以及 commit、push、PR、merge、deploy 和其他外部或高风险动作。
