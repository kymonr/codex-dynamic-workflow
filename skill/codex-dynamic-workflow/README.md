# Codex Dynamic Workflow v4.3.0

保持 `$codex-dynamic-workflow` 调用名，保留隐式匹配。
Skill 4.3.0 中，隐式匹配增加 Luna 只读调查和自动 Grok Burst：主线程保持原任务，有足够独立问题和额度时展开 6–12 个 Luna 方向，并自动尝试一个有独立价值的 Grok 探针。
用户显式调用时，才按[完整流程](references/explicit-workflow.md)运行 Astra 规划与验收、Sol 实施、Luna/Grok 补充。

显式任务默认使用**Root 统筹、单一 Sol writer 实施**：Astra 给出紧凑、可执行的设计与验收边界；当前主对话保持 Root，把封闭写范围交给一个 `cwf_sol_writer` 子代理，由它连续实施、测试和范围内修复；Root 不重复实现，也不逐命令、逐消息审核已授权步骤。writer 停止修改候选后，再由 fresh Astra 审核线程重新读取原始目标、完整实际 diff、关键依赖和测试证据。

Root 计入 writer；默认只有 `cwf_sol_writer` 修改候选，Root 继续无冲突的只读工作并负责调度、授权、结果筛查与收口。用户明确选择时，主对话可直接写，或通过宿主支持的真实控制权交接让另一对话成为 Root；这两种路径不是默认门槛，也不能制造第二 writer。线程变化不创造新任务：原授权、候选、未解决问题、活动 ownership、截止条件和累计额度继续沿用。

具体触发判断见 [SKILL.md](SKILL.md)；线程交接和失败回退见 [delegation](references/delegation.md)。下方流程参考均在显式模式按需读取。
启动下限不是等待门槛，也不是每次修复重开一组；容量、预算或真实独立方向不足时记录原因。
等待依赖宿主原生完成通知或挂起恢复；Root 有独立工作时继续推进，只在下一步依赖结果或恢复后对账一次，避免短间隔轮询、机械唤醒和重复日志。
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
v4 延续 SQLite DAG、原子调用预留与显式只读恢复，并加入补充分支隔离与独立主线验收；硬费用限制、操作系统文件隔离和嵌套工作流仍未实现。可选的 Skill-only Root 控制权交接也不是 Runtime handoff，不能绕过 Runtime 的固定 route、writer/verifier admission 或累计预算。
Runtime 入口和限制见 [runtime](references/runtime.md)；原生/模型集成验证状态须单独确认。
源码发布与本机安装分别核验；最终独立审核和对应提交的 CI 结果随发布记录提供。更新安装目录后，以新会话的实际发现和运行回执验证，不能只凭文件存在声称生效。

## Burst / OpenCodex Grok 与 Luna 1M Fast

`burst.json` 以 `enabled` 手动控制隐式和显式 Skill-only 的自动 Grok sidecar；不设置自动到期、
单任务调用次数、follow-up 次数或单次运行时长上限。复杂任务自动尝试一个有独立价值的探针；准入失败时记录原因。它只读、非完成门槛、非最终验收者。
Grok 调用不占用 Astra/Sol/Luna 的 Runtime/Skill 调用计数额度；主线资源和必要验收优先。
包内 Luna profile 请求 1M Fast；用户独立的 luna.toml、OpenCodex 目录和全局配置不改。
请求配置、目录宣告和实际运行分别记录；不声称已验证 1M 后端、速度、价格或节省。
