**在这两处改动的静态审阅范围内，未发现具体剩余阻断；但本轮内存探针未有效完成，不能宣称动态验证通过。**

- [executor.py:236](/D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:236)：失败记录外层的 `finally` 会执行释放。结合 [core.py:572](/D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:572)，记录失败时仍在运行的 attempt 会转为 `interrupted`，不会标为成功，也不退还累计 launch 预算；原始协议错误和二次源文件错误通过 Python 异常链保留。
- [executor.py:129](/D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/executor.py:129)：清理或关闭抛错会阻止 `ProcessResult` 返回，因此 `execute_one` 不会进入依赖已返回结果的释放分支，hold 仍保留。
- [core.py:410](/D:/codex/projects/codex-dynamic-workflow/skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py:410)：writer 冲突查询覆盖同一 DB 的所有未释放 attempt，不按 root 筛选；拒绝发生在预算扣减前，确认释放后不再参与冲突检查。其他数据库及未接入此协调机制的工具不受该锁约束。

**实际覆盖与限制：**已阅读指定函数、直接相关辅助定义及 `tests/test_v3_followup_findings.py`，未运行该测试文件。两次纯内存探针尝试分别因加载器模块注册错误、我构造的 fixture 缺失 contract version 且哈希计算不符而失败；后一批 22 个用例均未到达目标分支，**有效动态通过数为 0**，不能据此认定项目有缺陷或已通过验证。五次操作额度已用完；未验证真实进程树清理、文件权限故障及多连接并发行为，未执行文件写入、真实子进程测试或 Git 操作。