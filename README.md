# Codex Dynamic Workflow

面向 Codex v2 native subagent 的轻量编排 Skill。目标是把真正可独立交付的支线交给合适的子代理，同时由主线程保留范围控制、结果整合和最终验收。

## 当前路由

- Spark / Explorer：窄而明确的只读调查。
- Luna：普通委派任务和边界清晰的低风险写入。
- Sol：复杂、高影响或需要最终判断的任务。
- Grok：不属于 native subagent 路由，也不是自动降级节点；只有用户明确要求时才创建独立可见的 Grok 对话任务。

默认只允许一个 native writer。Grok 与 native writer 并发写入时，必须使用独立 worktree，并给双方互斥、封闭的 `owned_targets`。

## 仓库结构

```text
skill/                 可安装的 dynamic-workflow Skill
config/agents/         配套 native agent 角色模板
integration/           工作区 AGENTS.md 接入片段
```

`config/agents/grok_writer.toml.disabled` 仅作为停用状态的历史参考，不应复制为启用的 `.toml`。

## 安装

先从当前进程解析 `CODEX_HOME`；未设置时再使用平台默认目录。然后：

1. 将 `skill/` 的内容复制到 `$CODEX_HOME/skills/dynamic-workflow/`。
2. 将 `config/agents/` 中启用的 `.toml` 复制到 `$CODEX_HOME/agents/`。
3. 按工作区实际需要，将 `integration/AGENTS.dynamic-workflow.md` 的规则合并进对应 `AGENTS.md`。

安装后重新开始一个 Codex 任务，让 Skill 和 agent 配置从新任务加载。

## 验证

在仓库根目录运行：

```powershell
py -3.12 skill\scripts\routing_smoke.py
py -3.12 -m unittest discover -s skill\tests -v
```

离线路由 smoke 只能验证静态路由规则，不能证明某次任务实际使用了哪个模型、推理强度或 service tier；运行态身份应以新任务生成后的原生元数据为准。`routing_smoke.py --live` 会创建真实任务，只应在得到明确授权并指定 case 时使用。
