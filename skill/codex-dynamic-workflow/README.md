# Codex Dynamic Workflow v4.2.0

保持 `$codex-dynamic-workflow` 调用名，保留隐式匹配。
2026-09-14 起，隐式匹配增加 Luna 只读调查和自动 Grok Burst：主线程保持原任务，有足够独立问题和额度时展开 6–12 个 Luna 方向，并自动尝试一个有独立价值的 Grok 探针。
用户显式调用时，才按[完整流程](references/explicit-workflow.md)运行 Astra 规划与验收、Sol 实施、Luna/Grok 补充。

显式复杂任务优先使用**线程式阶段交接**：Astra 规划线程形成紧凑、可执行的交接状态；宿主支持独立控制器对话时，转交给独立 Sol 执行线程，由它成为唯一 implementation Root 并连续实施、测试、修复和调度补充调查；完成后再交给 fresh Astra 审核线程。若宿主不能安全建立独立 Sol Root，则回退为用户/宿主在当前主对话切换到 Sol。普通 `cwf_sol_writer` 子代理不能替代 Sol Root，因为子代理没有控制器和嵌套派工权限。

线程变化不创造新任务：原授权、候选、未解决问题、活动 ownership、截止条件和累计额度继续沿用；不能因为开新对话就重置预算、重建 Runtime run、制造第二 writer 或扩大权限。交接后 Astra 规划线程退出实现热路径，不再与 Sol 同时控制候选。最终 Astra 审核使用新的上下文重新读取原始需求、完整 diff、关键依赖和测试证据，不把旧计划或 Luna/Grok 发现当作审查范围上限。

具体触发判断见 [SKILL.md](SKILL.md)；线程交接和失败回退见 [delegation](references/delegation.md)。下方流程参考均在显式模式按需读取。
启动下限不是等待门槛，也不是每次修复重开一组；容量、预算或真实独立方向不足时记录原因。
详见 [v4.1 结果与收尾协议](references/followup.md)。

- 规范入口：[SKILL.md](SKILL.md)；本机 profile 需单独安装。
- 事实合同：[evidence](references/evidence.md)。原始文件必须真正打开，摘要只作导航。
- 预算合同：[budget](references/budget.md)。Skill 不是硬 token 计量器或后台调度器。
- 原生工具/模型合同：[host-routing](references/host-routing.md)。使用实际工具 schema。
- 写入合同：[writes](references/writes.md)。默认单 writer；commit/push/merge 单独授权。
- 灵活形态：[patterns](references/patterns.md)。不是固定阶段清单。

质量 > 自动化 > 延迟 > 成本 > 可观察性 > 可恢复性。
没有独立任务就不派工；出现新的证据缺口可以追加分支；不重复查同一问题填人数。
高风险结论不能为了节约成本改用不足能力的核验者。`cwf_general`（Luna/max）承担有明确来源和检查边界的可选补充探索；`cwf_mechanical`（Luna/medium）仅承担合格的机械只读任务。

`policy.json` 是初始可编辑规划上限，不是推荐用满额度，也不是准确费用报价。
v4 延续 SQLite DAG、原子调用预留与显式只读恢复，并加入补充分支隔离与独立主线验收；硬费用限制、操作系统文件隔离和嵌套工作流仍未实现。线程式 Skill-only Root 交接也不是 Runtime handoff，不能绕过 Runtime 的固定 route、writer/verifier admission 或累计预算。
Runtime 入口和限制见 [runtime](references/runtime.md)；原生/模型集成验证状态须单独确认。
更新安装目录后，以新会话的实际发现和运行回执验证，不能只凭文件存在声称生效。

## Burst / OpenCodex Grok 与 Luna 1M Fast

`burst.json` 以 `enabled` 手动控制隐式和显式 Skill-only 的自动 Grok sidecar；不设置自动到期、
单任务调用次数、follow-up 次数或单次运行时长上限。复杂任务自动尝试一个有独立价值的探针；准入失败时记录原因。它只读、非完成门槛、非最终验收者。
Grok 调用不占用 Astra/Sol/Luna 的 Runtime/Skill 调用计数额度；主线资源和必要验收优先。
包内 Luna profile 请求 1M Fast；用户独立的 luna.toml、OpenCodex 目录和全局配置不改。
请求配置、目录宣告和实际运行分别记录；不声称已验证 1M 后端、速度、价格或节省。
