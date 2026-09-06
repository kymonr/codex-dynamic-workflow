# Codex Dynamic Workflow v3.0.0

保持 `$codex-dynamic-workflow` 调用名，保留隐式匹配。
核心是原生派工、原始证据、自适应分支和授权内实现闭环，不是固定人数审核。

- 规范入口：[SKILL.md](SKILL.md)；本机 profile 需单独安装。
- 事实合同：[evidence](references/evidence.md)。原始文件必须真正打开，摘要只作导航。
- 预算合同：[budget](references/budget.md)。Skill 不是硬 token 计量器或后台调度器。
- 原生工具/模型合同：[host-routing](references/host-routing.md)。使用实际工具 schema。
- 写入合同：[writes](references/writes.md)。默认单 writer；commit/push/merge 单独授权。
- 灵活形态：[patterns](references/patterns.md)。不是固定阶段清单。

质量 > 自动化 > 延迟 > 成本 > 可观察性 > 可恢复性。
没有独立任务就不派工；出现新的证据缺口可以追加分支；不重复查同一问题填人数。
高风险结论不能为了节约成本改用不足能力的核验者。`cwf_general`（Luna/max）承担有明确来源和检查边界的普通只读探索与验证；`cwf_mechanical`（Luna/medium）仅承担合格的机械只读任务。

`policy.json` 是初始可编辑规划上限，不是推荐用满额度，也不是准确费用报价。
v3 提供 SQLite DAG、原子调用预留与显式只读恢复；硬费用限制、操作系统文件隔离和嵌套工作流仍未实现。
Runtime 入口和限制见 [runtime](references/runtime.md)；原生/模型集成验证状态须单独确认。
更新安装目录后，以新会话的实际发现和运行回执验证，不能只凭文件存在声称生效。
