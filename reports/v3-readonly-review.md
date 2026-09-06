**本次检查范围内确认 5 项缺陷，其中 2 项 P1、3 项 P2；仍有验收与生命周期阻塞项。** 以下结论来自原始源码和纯内存探针，未修改文件。

1. **P1 — POSIX 正常退出后未清理后代进程，却释放执行占用。**  
   位置：[executor.py:80](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:80)、[executor.py:91](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:91)、[executor.py:171](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:171)。  
   **触发：** 前台命令退出，但仍有关闭或重定向标准流的后台后代进程。`communicate()` 可以返回；POSIX 的正常返回路径没有进程组清理，随后 `execute_one()` 直接确认释放。流量超限导致 worker 提前退出也存在同类缺口。  
   **后果：** 未管理的后代继续运行，数据库却报告占用已释放，违反已声明的进程树生命周期边界。模拟 `Popen` 探针确认：正常返回时进程组清理调用为 **0**；未运行真实 POSIX 进程。  
   **限定修复：** 所有终止路径统一清理并确认任务所属进程组；无法确认时保留占用。补充“前台退出、后代仍存活”的回归。

2. **P1 — exec 成功终止事件没有与最终消息所属轮次绑定。**  
   位置：[executor.py:109](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:109)。  
   **触发：** JSONL 包含 `turn.completed → turn.started → 有效 agent_message`，新轮次没有终止事件，进程返回码为 0。解析器只统计终止事件数量，再取最后一条消息。  
   **后果：** 前一轮的终止事件可为后一轮未完成的结果提供“成功”凭据。纯内存探针返回了 `completed`；“终止事件在消息之前”的畸形序列也被接受。  
   **限定修复：** 跟踪轮次和事件顺序，要求最终消息属于已成功终止的轮次，并拒绝随后出现的未完成执行。补充上述截断、乱序回归。

3. **P2 — 历史候选的处理在调度与最终质量门之间不一致，合法多阶段 DAG 会卡死。**  
   位置：[core.py:447](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:447)、[core.py:700](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:700)、[core.py:714](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:714)。  
   **触发与实测：**
   - `w1 → v1 → w2 → v2`：每次写入均有独立复核，四个节点均为 `completed`，状态查询正确标记历史证据；`finish()` 仍报 `candidate drift: v1`。
   - `explore → write → review`，且 review 显式依赖 explore 和 write：刷新 review 到写后候选，仍因 `candidate drift: explore` 无法调度。
   
   **后果：** 按契约使用新节点表达后续修改、保留正常依赖关系，反而无法完成工作流。  
   **限定修复：** 在依赖校验和质量门中一致处理由授权后继写入解释的历史候选：保留每阶段原候选与独立复核关系，最终证据仍须匹配当前字节；不能简单跳过漂移检查。补充这两种 DAG 回归。

4. **P2 — 删除可被记为写入完成，但无法完成必需的写后复核。**  
   位置：[core.py:543](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:543)、[core.py:658](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:658)、[core.py:699](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:699)。  
   **触发：** 主控明确授权删除闭合写集合中的文件，writer 如实报告 `changed_files`。writer 的指纹允许文件缺失，readonly reviewer 的指纹读取却不允许；质量门还要求复核快照包含这个删除项。  
   **后果：** 内存探针中删除结果被接受为 `completed`，随后 review 的 `refresh()` 报 `missing source: a.py`，工作流无法验收。  
   **限定修复：** 明确支持删除项的只读验收协议，保留删除前指纹并验证当前不存在；若本版不支持删除，应明确拒绝该效果并记录为待人工处理，不能先宣称写入完成。

5. **P2 — 畸形结果可绕过协议失败清理，留下虚假的 active 占用。**  
   位置：[core.py:496](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:496)、[executor.py:173](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:173)。  
   **触发：** 已返回的执行结果包含 `outcome: []`。集合成员检查抛出 `TypeError`，而适配器只捕获 `WorkflowError` 执行已终止结果的失败登记和释放。  
   **后果：** 注入 transport 的内存探针确认：抛出 `TypeError: unhashable type: 'list'`，节点仍为 `active`，`active_holds=1`，即使 transport 已正常返回。  
   **限定修复：** 在不可信结果边界先验证类型并统一转为 `WorkflowError`，确保已确认终止的协议失败走失败登记与释放；未知 transport 故障仍保留占用。

**已排除的实质疑点：** 配置不保证实际模型能力、native 协作排他不等于 OS 隔离、不同数据库不互锁，均属于已披露边界，未列为缺陷。相同完成回执的幂等返回不重复扣费或改写事件；旧 attempt 的 claim 也有当前 token 校验。上述发现不依赖主控伪造授权或虚假终止确认；第 2、5 项针对必须正确处理的不可信协议输入。

**实际覆盖：** 使用 **11 次 shell 读取／检查调用**，完整读取指定的 5 个 runtime 模块、bundled schema、4 个项目脚本、3 个 `test_runtime*.py`、设计与 runtime 文档，并检查安装入口。执行了 SQLite `:memory:`、模拟指纹及模拟 transport/process 探针；预算函数检查 **3,888 组输入**，其中 **788 个允许结果**均保持剩余 total／approved／strong 预留不变量。bundled schema 与生成 schema 一致。

未运行落盘测试、真实子进程、Windows Job Object 回归、实际 native／exec 模型调用或安装操作；因此不对这些现场边界宣称通过。现有已读测试没有覆盖上述反例，本报告也不替代父线程的 Windows 回归结果。