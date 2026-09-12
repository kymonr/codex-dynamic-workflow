# 4.1.2 原生验收交接 — 2026-09-11

**正式验收仍未通过。** 已完成一次原 Runtime 恢复、三类六组原生 paired pilot，以及一次限定只读补验。最后一次补验的主要失败来自临时采集器和主线程控制衔接；尚未确认需要修改 workflow 产品源码的缺陷。

被测源码提交为 `4e795ac779f801bd358933cd21747a38675b58d3`，PR #41 的 head branch 为 `codex/astra-mainline-luna-supplement`，base 为 `master`。本次 push 只交接证据、状态和临时采集器修复的审阅快照，不改变 Skill、角色配置、控制器或比较器。后续文档提交不是新的已验收运行时代码。

当前状态入口为 [V41_NATIVE_COMPARISON_STATUS.json](../V41_NATIVE_COMPARISON_STATUS.json)，数值和失败记录见 [observations.json](observations.json)。该文件保留先前 NOT_RUN 记录作为历史状态。

## 已确认的结果

| 阶段 | 观察结果 | 不能据此得出的结论 |
|---|---|---|
| 原 run `16bf6b3beead412cb921c437ef74f3b0` 的恢复 | Runtime 记录 mainline_accepted=true；5 个恢复阶段原生执行身份已记录 | 当时实际 sandbox 为 full access；没有证明硬只读隔离、槽位回收或 finish 时仍有 Luna 运行 |
| 三类六组 paired pilot | 六个最终完整尝试均交付相应任务；失败阶段保留 | 比较器返回 NOT_QUALIFIED，不能宣布一般质量、速度或成本优势 |
| 最后一次限定补验 `13b57082b79c4863acdcff8a300abb23` | 观察者会话返回 readOnly，并真实拒绝一次文件创建；5 个子 turn 完成 | 子线程身份与释放回执缺失；mainline_accepted=false；目标 Runtime 时序未观察到 |

安装中的 24 个当前 Skill 文件与 4 个 cwf 角色文件曾逐字节匹配被测 Git 提交。项目主目录是非 Git 副本；本机实际 Git checkout 为 `D:\codex\temp\codex-dynamic-workflow-v4-20260909`。应先核对真实 checkout 和候选，不把主目录或历史 manifest 当成当前 Git 身份。

## Paired pilot 摘要

| 用例 | Astra-only 最终主线交付 | Astra + 3 Luna 最终主线交付 | 任务结果 |
|---|---:|---:|---|
| config_review | 83.27 秒 | 124.43 秒 | 两组均报告相同的两个根因 |
| lifecycle_review | 75.29 秒 | 313.07 秒 | 两组均报告相同的两个根因 |
| retry_fix | 216.26 秒 | 237.05 秒 | 两组均通过 48 项共同检查和各自必要独立复核 |

配置混合组还有名额不足和采集失败两个阶段，不能只统计最终成功尝试。计入已观察失败阶段，该组从首次启动到交付为 807.25 秒，已观察 Token 小计至少为 1365282。全部 paired pilot 的已观察小计至少为 4535063，含缓存输入；外层 Root 用量与货币费用未完整计量。

三个 Skill-only 混合组主线交付时，分别仍有 3、2、1 个 Luna 在运行。这些事件不能替代 Runtime 的 finish 验证。本轮没有发现 Astra-only 遗漏、而由 Luna 新增确认的独立缺陷；同一根因的重复表述没有被算作增量收益。至少三个 Luna 的策略未改变。

比较器拒绝的实际首个原因是 `model/profile/effort unverified or mismatched`。顶层 Root 没有可用的命名 profile 回执，补充线程缺少强制 read-only 的完整证据，部分失败历史也缺少完整终态。没有修改比较器或补造字段使其通过。

## 最后一次限定补验为什么失败

用户明确批准了专用验收会话选择现有 `:read-only`、独立计账的新 run，以及最多 6 个新增原生回合：观察者 1、主线 1、独立 verifier 1、Luna 3。执行窗口为 10 分钟，另留最多 90 秒收尾；没有自动模型重试，也没有重跑六组 paired pilot。

观察者的 `thread/settings/updated` 返回 Astra/high、readOnly、networkAccess=false。一次指定路径的排他创建在 Python 文件操作层返回 `PermissionError: [Errno 13] Permission denied`，探针文件没有生成。这个结果只确认观察者会话中的拒绝，不能补成子线程权限回执。

临时采集器的具体缺陷：

1. `snapshot()` 仅从 `thread/list(useStateDbOnly=true)` 填充 `known`。
2. 本次临时子线程没有出现在该查询结果中。
3. 虽然 `drain()` 已收到子线程的 turn/started 和 turn/completed，它没有把这些 ID 加入 `known`。
4. 后续 thread/read、身份采集和逐子线程 unsubscribe 均漏掉它们。

主线程又将时间用于补查元数据，main 完成到 verifier 启动间隔 285.08 秒。三个 Luna 均已结束后才启动 verifier，所以没有取得需要的时序证据。观察者在 600 秒边界被中断；实际 6 个原生回合中，5 个子回合 completed，观察者 interrupted。

主线和 verifier 独立读取两份原始夹具，均发现槽位计算错用 max 而非累加，以及可见检查缺少组合输入和主线未完成分支。这里的 [ledger.py](fixture/ledger.py) 是故意带错的隔离夹具，不是 workflow 产品源码；[checks.py](fixture/checks.py) 的现有断言全部通过不等于夹具正确。

counterexample 返回的必需 `source-based-review` 为 FAIL，因此 Runtime 记录 partial；其他四个节点记录 completed。原始 FAIL 没有改成 PASS。额外字段、字典式 checks 和字符串 notes 只做了格式适配，原文保留在本机。

公共 decide 因 `run deadline reached` 被拒绝。13 条返回 claim 已在账本外完成源码判断，但没有写入 Runtime；7 条 supplemental claim 仍为 untriaged。finish 返回 `live/unreconciled mainline execution attempts remain`。5 个 execution holds 和 5 个 host-resource holds 保留，不能用进程退出替代释放回执。

## 采集器修复与离线复现

- [collector-executed.py.txt](collector-executed.py.txt)：本轮实际使用的逻辑。
- [collector-fixed.py.txt](collector-fixed.py.txt)：之后修复的逻辑，从 turn 事件登记子线程，并要求回合终态与工具结束后才判断执行结束。
- [host-probe.py.txt](host-probe.py.txt)：临时 stdio 客户端源码，供审阅调用关系。
- [lifecycle-events.json](lifecycle-events.json)：从本次原始事件流抽取的 12 条生命周期事件，仅保留线程/turn 身份、状态和时间。

两个采集器文本移除了本机 Codex 可执行文件路径，换行按仓库规范存储，相关采集函数逻辑保持原样。fixture 文件通过本目录的 .gitattributes 保留原始字节，可与 observations.json 中的 SHA256 核对。采集器文本是审阅快照，不是可直接运行的产品入口，也不授予新的模型调用或权限变更。

在仓库根运行以下离线检查。它只通过 AST 提取采集函数，不导入或执行原生 runner，不调用模型，不写入源文件：

```text
python -B reports/native-validation-2026-09-11/verify_collector_replay.py
```

检查以空的元数据索引复现旧行为：执行版只请求观察者元数据，修复版会请求观察者和全部五个子线程；六个回合均保留。运行中、UNKNOWN、工具未结束的情况不会被当成已结束。元数据响应是测试替身，不能当成真实宿主身份或释放证明。修复后没有新的真实模型重跑。

## 后续处理重点

先审核采集器及控制器衔接，确认在子线程尚可读时采集实际身份、终态、工具完成和对应释放回执。主线完成后的必要 verifier 应及时进入已准入路径；不能让元数据补查或可选 Luna 结果阻塞它。

然后核对现有原生入口是否能提供匹配的 model/profile/effort 和实际子线程只读能力。仅有角色文件、请求参数或父会话只读拒绝都不够。不得为通过比较器放宽字段要求或把 UNKNOWN 填成期望值。

旧 run 和最后一次补验的状态、预算及失败均须保留。本次追加额度已用完：新 Runtime 5 次、strong 2 次，观察者另计 1 回合；合并旧 Runtime 账目为 12 次、strong 5 次。新的真实补验需要新的明确执行范围与额度。本提交没有授权再跑模型、merge、mark ready、tag、Release 或部署。

## 本机保留的完整材料

完整材料位于 `D:\codex\temp\cwf-native-acceptance-20260910`，入口为 `NATIVE_ACCEPTANCE_REPORT.md`，最后一次补验位于 `runtime-case\followup-20260911`。其中包括原始会话/命令事件、SQLite、每个返回、规范化说明和释放缺口。它们未随本次 push 上传。

本次补验的已观察 Token 为 1453302，其中缓存输入 1298944；观察者 969544，五个子节点合计 483758。外层主任务用量和货币费用未知。数据摘要与文件哈希不是宿主签名，不能替代原始证据的独立核验。
