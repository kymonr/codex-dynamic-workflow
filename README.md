# Codex Dynamic Workflow

面向 Codex v2 native subagent 的轻量编排 Skill。它把真正可独立交付的支线交给合适的子代理，同时由主线程保留范围控制、授权、结果整合和最终验收。

## 当前路由

- Spark / Explorer：窄而明确、低风险、可本地核对的只读调查。
- Luna：普通委派任务，以及边界清晰、低风险的 scoped writing。
- Sol：复杂、跨模块、高影响、架构/安全判断或最终技术判断。
- Grok：不属于 native subagent 路由，也不是自动 fallback；只有用户明确要求时才创建独立可见的 Grok 对话任务。

默认只允许一个 native writer。Grok 与 native writer 并发写入时，必须使用独立 worktree，并给双方互斥、封闭的 `owned_targets`。

机器可读的角色与路径合同位于 `config/workflow-policy.toml`。角色 TOML、公开文档和接入片段必须通过一致性检查，避免路由规则在多个文件之间悄悄漂移。

## 执行路径

Native subagent 是默认路径。只有用户明确需要可复现的 CLI 日志、逐任务产物目录、JSON summary 或真实 `codex exec` 探针时，才使用显式 CLI runner。

CLI runner 是有界只读路径，不提供 workspace write、Git 写入、任意命令或自动模型升级。使用跨平台入口：

```powershell
py -3.12 skill\cli.py run `
  --spec D:\path\workflow.json `
  --allowed-root D:\path\bounded-project `
  --ack-external-model-export
```

```bash
python3.12 skill/cli.py run \
  --spec /path/workflow.json \
  --allowed-root /path/bounded-project \
  --ack-external-model-export
```

`skill/cli.py` 会在导入兼容 runner 前设置跨平台的运行目录默认值。直接执行 `skill/runner.py` 仅保留为兼容入口，不应作为新的集成方式。

## 仓库结构

```text
config/workflow-policy.toml      机器可读路由与路径合同
config/agents/                   配套 native agent 角色模板
integration/                     工作区 AGENTS.md 接入片段
skill/SKILL.md                   Dynamic Workflow Skill 主规则
skill/cli.py                     跨平台 CLI 入口
skill/platform_paths.py          本地状态、产物与 worktree 路径解析
skill/runner.py                  兼容的只读 DAG runner
skill/scripts/                   路由 smoke 与合同检查
skill/tests/                     离线回归测试
```

`config/agents/grok_writer.toml.disabled` 仅作为停用状态的历史参考，不应复制或重命名为启用的 `.toml`。

## 安装

先从当前进程解析 `CODEX_HOME`；未设置时再使用平台默认目录。然后：

1. 将 `skill/` 的内容复制到 `$CODEX_HOME/skills/dynamic-workflow/`。
2. 将 `config/agents/` 中启用的 `.toml` 复制到 `$CODEX_HOME/agents/`。
3. 按工作区实际需要，将 `integration/AGENTS.dynamic-workflow.md` 的规则合并进对应 `AGENTS.md`，不要覆盖已有项目规则。
4. 重新开始一个 Codex 任务，让 Skill 与 agent 配置从新任务加载。

## 本地路径

运行状态默认保存在平台合适的用户状态目录，worktree 默认保存在系统临时目录，不再要求固定盘符或用户名。以下变量可以显式覆盖：

| 变量 | 用途 |
|---|---|
| `DYNWF_HOME` | Dynamic Workflow 本地状态根目录 |
| `DYNWF_RUNS_ROOT` | CLI run artifacts 根目录 |
| `DYNWF_WORKTREE_ROOT` | 隔离 worktree 根目录 |

优先级为“显式环境变量 → 平台默认目录”。共享配置和文档中不得提交个人用户名、固定 Node 安装路径或固定盘符临时目录。

## 验证

在仓库根目录运行：

```powershell
py -3.12 skill\scripts\check_policy_consistency.py
py -3.12 skill\scripts\routing_smoke.py
py -3.12 -m unittest discover -s skill\tests -v
```

```bash
python3.12 skill/scripts/check_policy_consistency.py
python3.12 skill/scripts/routing_smoke.py
python3.12 -m unittest discover -s skill/tests -v
```

GitHub Actions 会在 Windows 和 Linux 的 Python 3.12 上运行编译检查、policy consistency、routing smoke 和完整离线单元测试。

离线路由 smoke 只能验证 evaluator 和静态路由合同，不能证明某次任务实际使用了哪个模型、推理强度或 service tier。运行态身份应以新任务产生的原生结构化元数据为准。`routing_smoke.py --live` 会创建真实任务，只应在得到明确授权并指定 case 时使用。
