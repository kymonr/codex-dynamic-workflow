# Codex Dynamic Workflow

面向 Codex v2 native subagent 的轻量编排 Skill。它把真正可独立交付的支线交给合适的子代理，同时由主线程保留范围控制、授权、结果整合和最终验收。

## 当前路由

- Spark / Explorer：窄而明确、低风险、可本地核对的只读调查。
- Luna：普通委派任务，以及边界清晰、低风险的 scoped writing。
- Sol：复杂、跨模块、高影响、架构/安全判断或最终技术判断。
- Grok：不属于 native subagent 路由，也不是自动 fallback；只有用户明确要求时才创建独立可见的 Grok 对话任务。

默认只允许一个 native writer。Grok 与 native writer 并发写入时，必须使用独立 worktree，并给双方互斥、封闭的 `owned_targets`。

机器可读的角色、资源限制与路径合同位于 `config/workflow-policy.toml`。角色 TOML、公开文档和接入片段必须通过一致性检查，避免规则在多个文件之间悄悄漂移。

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

中断后的显式恢复：

```powershell
py -3.12 skill\cli.py resume `
  --run-dir D:\path\to\runs\example-run `
  --allowed-root D:\path\bounded-project `
  --ack-external-model-export
```

`run` 会持续写入 `events.jsonl` 和 `checkpoint.json`。显式 `resume` 会核对计划摘要，只恢复未完成节点；已成功节点通过内容寻址 artifact 复用，不重新把完整结果塞入主线程或下游 prompt。

## 资源和结果边界

每次运行始终存在有限上限：

- 单节点结构化输出；
- 单节点日志；
- 整次运行产物；
- 注入下游 prompt 的上游结果累计字节；
- 单条事件日志。

默认值和不可突破的硬上限记录在 `config/workflow-policy.toml`。超过限制会终止相关节点；超量日志会截断到上限，超量结构化输出会被丢弃，并保留最后一个仍可安全写入的 checkpoint，不会无限增长磁盘或上下文。

所有成功结果都会生成 SHA-256 内容寻址 artifact。小结果仍可内联；超过累计 inline budget 时，下游只收到带摘要、哈希和精确只读路径的 `UPSTREAM_ARTIFACT_REFERENCE`，避免重复复制大对象。

## Workflow IR v3

仓库已加入声明式 Workflow IR v3 基础：

```powershell
py -3.12 skill\cli.py validate-ir --spec workflow-v3.json
```

当前静态 `agent` 节点可以编译成 v2 只读 DAG；`map`、`verify`、`loop`、`reduce`、`conditional` 与 `human_gate` 已有严格版本化校验，但在 v3 控制流 runtime 完成前不会被静默执行或降级。详细合同见 `skill/references/workflow-ir.md`。

## 仓库结构

```text
config/workflow-policy.toml      机器可读路由、限制与路径合同
config/agents/                   配套 native agent 角色模板
integration/                     工作区 AGENTS.md 接入片段
skill/SKILL.md                   Dynamic Workflow Skill 主规则
skill/cli.py                     跨平台 CLI 入口
skill/platform_paths.py          本地状态、产物与 worktree 路径解析
skill/runner.py                  有界、可恢复的只读 DAG runner
skill/runtime/                   schema、artifact、limits、state、Workflow IR 模块
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
| `DYNWF_MAX_RESULT_BYTES` | 单节点输出上限，不能超过硬上限 |
| `DYNWF_MAX_LOG_BYTES` | 单节点日志上限，不能超过硬上限 |
| `DYNWF_MAX_RUN_ARTIFACT_BYTES` | 单次运行总产物上限 |
| `DYNWF_MAX_UPSTREAM_INLINE_BYTES` | 每个下游 prompt 的累计上游内联预算 |
| `DYNWF_MAX_EVENT_BYTES` | 单条事件上限 |

优先级为“spec 显式限制 → 环境变量 → 默认值”。共享配置和文档中不得提交个人用户名、固定 Node 安装路径或固定盘符临时目录。

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

## Trusted Workflow IR 控制流

Workflow IR v3 可通过 `skill/cli.py run-ir` 执行可信的只读 `agent`、`map`、`verify` 和 `reduce` 节点，并用 `resume-ir` 从 checkpoint 显式恢复。动态 child、manifest、事件和结果均受既有资源预算与内容寻址 artifact 边界约束。

`loop`、`conditional` 和 `human_gate` 仍会被严格校验，但当前不会执行或静默降级。IR 本身不是授权，不能扩大写入、凭据、发布或破坏性权限。
