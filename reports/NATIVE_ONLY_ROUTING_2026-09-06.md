# Luna 与 Astra 全原生路由验收

已按用户“不要走cli，全都走原生的”更新本地源码并安装。Luna 和 Astra 的模型派工统一使用原生代理工具；此前独立 CLI 池方案已被替代。

## 当前行为

- 普通、有明确来源与交付边界的探索和验证使用原生 Luna/max；机械检查使用原生 Luna/medium。探索答案可以未知，可按互不重复的方向批量派发。
- 复杂判断、实现和必要的关键独立复核保留 Astra 路由。就绪的必要 Astra 工作不等待无关 Luna 支线，主线程保留相应额度和实际宿主容量。
- Luna 与 Astra 共享实际原生容量，Luna 没有槽位豁免；超出容量的支线排队，不通过 CLI 回退，不重建任务抹去已消费次数或失败。
- 当前策略为 `backend=native-only`、`luna_readonly_backend=native`、`runtime.backends=[native]`。公开控制器拒绝 `exec-one`、`luna-pool`、`next --backend exec` 及新 exec 计划。两个旧模型验收脚本也在模型启动前按安装策略拒绝。
- `scripts/cwf.py` 可继续作为原生工作的本地状态控制器。历史 exec 记录和确定性回归适配器保留，不能用来启用当前 CLI 模型派工。
- Luna 的有限检查结果仍须对应明确覆盖范围；超出该范围的修复完整性或关键验收判断，保留主线程和必要独立复核。

## 已执行检查

| 检查 | 实际结果 |
|---|---|
| 完整回归 | 254 项执行，253 通过，1 项因 Windows 符号链接权限跳过；55.775 秒 |
| 新增原生路由回归 | 6 项，覆盖模型入口拒绝、新计划限制、原生 Luna 准入、旧 exec 状态读取和旧模型验收脚本停用 |
| 包验证器 | PASS |
| 原生子代理场景检查 | 请求 Luna/max；直接检查 5 个原始文件、3 个场景，文件检查前后无变化；限定范围内未发现活跃 CLI 派工条款 |
| 安装 | 8 个文件更新，25 个受管文件验证成功 |
| 安装后读回 | 25/25 文件与源码字节一致，策略字段符合全原生要求 |
| 已安装派工入口 | `exec-one`、`luna-pool` 和 `next --backend exec` 均返回原生路由限制错误，未创建探针 DB、未调用模型 |
| 安装预检 | `changes=[]`，`legacy_enabled=false` |

进程级和用户级 `CODEX_HOME` 均核实为 `D:\CodexData\.codex`。本轮没有通过 CLI 调用模型，没有修改全局配置，也没有执行 commit、push 或 merge。

验收范围不包含真实模型身份、Desktop profile 热重载、Luna 与 Astra 的质量对照或同时执行的最大原生代理数量。请求的模型标签不能替代宿主实际模型回执。

## 证据与恢复

- 安装后读回：`reports/native-only-installed-result.json`。
- 本轮安装收据：`reports/install-backup-e53ac6414d14/receipt.json`，包含受管文件前像及恢复身份；恢复须按当时目标状态重新核对，不自动执行。
- 完整回归日志：`D:\codex\temp\dynamic-workflow-luna-20260906\native-only-regression.log`。
- 旧 CLI 池报告 `reports/LUNA_POOL_ACCEPTANCE_2026-09-06.md` 保留为历史验证记录，已明确标记被当前选择替代。
