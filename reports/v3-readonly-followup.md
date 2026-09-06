**结论：仍有 1 个阻断验收的边界缺陷。** 五项修复的主要路径已得到源码和纯内存探针支持，但“确认传输终止后不留下虚假活动占用”尚未覆盖失败记录再次出错的路径。

**[P2] 传输已终止，失败记录的指纹检查异常仍会跳过释放。**

位置：[executor.py:236](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:236)，具体是第 242 行调用 `runtime.complete()`，第 243 行才调用 `runtime.release()`；前者会经过 [core.py:549](D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:549) 的源文件指纹检查。

复现输入与过程：

1. 一个 `exec` 只读任务声明读取 `a.py`，传输完成绑定，并返回代表已确认清理的 `ProcessResult`。
2. 最终结果包含 `outcome: []`，第一次 `complete()` 正确抛出 `WorkflowError`。
3. 此时 `a.py` 缺失，或指纹读取因文件超限、访问错误而失败。
4. 异常处理器提交备用 `failed` 结果时，再次执行指纹检查并抛错，后面的 `release()` 没有执行。

三种情况均在原始函数和 SQLite `:memory:` 探针中复现：**节点仍为 `active`，`active_holds=1`**。这会继续占用容量及协作锁，需要额外协调；此处进程终止已被确认，残留占用来自结果记录失败。

最小修复：在已经取得确认终止的传输结果后，让协议失败分支通过 `try/finally` 保证执行 `release()`，同时保留结果记录或源文件异常。传输未返回、清理不确定的分支仍须保留占用。应补充“畸形结果＋指纹读取失败”的回归检查。

其余核验结果如下：

| 不变量 | 本次核验结论 |
|---|---|
| 所有退出路径清理进程树 | `run_owned()` 的 `finally` 覆盖正常退出、模拟流超限退出、取消、通信异常和绑定异常。清理抛错会阻止待返回的成功结果。Windows 清理轮询活动数至零；POSIX 组持续存在时拒绝确认。 |
| JSONL 终止与最终消息绑定 | 合法单轮被接受，并选取该轮最后一条完成的 agent message。旧终止后追加新轮、未完成轮、终止先于消息、消息先于轮开始、重复轮及失败终止均被拒绝。 |
| 多阶段写入与历史证据 | `w1→v1→w2→v2`、同时依赖 explore/write 的 review 均能在显式刷新候选后完成。无法由写入链解释的外部漂移仍阻断；后补对新候选的审查不能替代旧 writer 的候选审查。 |
| 删除不受支持 | 模拟实际指纹从存在变为缺失，并提交准确变更回执后，结果为 `partial`，记录 `blocked_effects=['deletion:a.py']`；完成、重试及重新准入均被阻断。 |
| 枚举字段类型与释放 | `outcome`、`check.status`、`claim.existence`、`claim.applicability` 分别输入数组和对象，共 8 例，在源文件可正常读取时均产生 `WorkflowError`、记录 `failed` 并释放占用。上述复合异常路径仍有缺口。 |

影响验收但已排除的疑虑：

- 历史证据机制允许识别被后续授权写入替代的旧字节，**没有因此免除旧 writer 的独立审查门槛**；未审查旧阶段的反例在 `finish()` 被拒绝。
- POSIX 组仍存在时保留占用属于要求的保守行为。可信宿主终止声明和数据库协作锁也不等同于操作系统安全隔离；没有把这些已声明边界本身列为缺陷。

本次共使用 **7 次有界 shell 读取／纯内存检查**，检查了指定原始函数、完整的 `tests/test_v3_independent_findings.py` 及必要支持代码。没有修改文件、创建临时文件、启动真实被测进程、运行完整单元测试、调用代理或读取旧审查报告。预算准入和文件指纹使用了内存替身；Windows 活动计数通过模拟查询核验字段读取及错误处理，未调用真实 Job API。一次 POSIX 模拟因 Windows 缺少 `SIGKILL` 常量而中断，补齐模拟常量后相关检查通过。

真实 Windows 进程树、真实流超限机制和实际文件删除效果仍由父线程测试确认；本报告不对这些未执行边界或指定范围之外作无缺陷声明。