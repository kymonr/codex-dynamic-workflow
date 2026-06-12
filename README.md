# codex-dynamic-workflow

给 codex 桌面版的 `dynamic-workflow` 技能：把大任务拆成多个只读 `codex exec` 子代理并行执行，
由 `src/runner.py` 确定性调度，结果汇总在运行目录的 `summary.json`。

- 计划书：`docs/plans/2026-06-13-dynamic-workflow-skill.md`
- 运行产物目录：`D:\.codex-tmp\workflows\`
- 安装位置：`C:\Users\Orz\.codex\skills\dynamic-workflow\`
- v0.1 范围：只读子代理。并行改文件不在本技能内（走 Claude Code 方案二）。

## 运行环境结论（任务 1 探针填写）
（待填）

## 测试

```
python -m unittest discover -s tests -v
```
