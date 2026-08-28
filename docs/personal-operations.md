# Personal Operations

本页只面向个人日常维护：确认实际安装版本、预览覆盖范围、安装候选、检查漂移，以及退回安装前状态。所有安装管理命令都为本地零模型操作，不调用 Codex 模型，也不会修改工作区 `AGENTS.md`。

## 安装计划

从仓库根目录执行：

```powershell
py -3.12 skill\cli.py install-plan --source-root .
```

```bash
python3.12 skill/cli.py install-plan --source-root .
```

命令不会创建 `CODEX_HOME` 或 `DYNWF_HOME`，输出中的 `writes` 始终为空。重点检查：

- `source_commit` 与 `source_dirty` 是否符合预期；
- `managed_files[].action` 是 `create`、`replace_managed`、`replace_unmanaged`、`adopt_existing` 或 `unchanged`；
- `stale_files` 是否只包含上一安装记录拥有、且仍与记录一致的旧文件；
- `blocked` 是否为空；
- `plan_digest` 是否是准备应用的精确计划摘要。

启用的 agent 只包括 `config/agents/` 根目录下扩展名恰好为 `.toml` 的文件。`grok_writer.toml.disabled`、Python cache、`.pyc`、`.pyo` 和本地安装 manifest 不会进入安装载荷。

## 应用精确计划

把上一命令返回的 `plan_digest` 原样传入：

```powershell
py -3.12 skill\cli.py install-apply `
  --source-root . `
  --expected-plan-digest <SHA256> `
  --ack-install
```

```bash
python3.12 skill/cli.py install-apply \
  --source-root . \
  --expected-plan-digest <SHA256> \
  --ack-install
```

应用时会重新生成计划；源文件、目标文件、活动 manifest 或路径身份发生变化都会使摘要不匹配并拒绝继续。写入顺序为：

1. 获取安装级 OS-backed lease；
2. 备份所有将被替换或删除的目标；
3. 写入 `prepared` history record；
4. 原子写入新文件并删除已确认未漂移的 stale managed file；
5. 逐文件重新验证 SHA-256；
6. 最后发布 active manifest；
7. 将 history record 标记为 `applied`。

安装器不会删除未被上一 manifest 管理的额外文件，也不会覆盖已经发生漂移的 managed file。第一次接管一个同名未管理文件时，计划会显示 `replace_unmanaged`，应用前会先保存其原始内容。

## 检查实际安装身份

```powershell
py -3.12 skill\cli.py install-status
```

```bash
python3.12 skill/cli.py install-status
```

主要状态：

| 状态 | 含义 |
|---|---|
| `not_installed` | 没有 active manifest |
| `clean` | 所有 managed file、manifest 和 history record 一致 |
| `clean_with_unmanaged_files` | 安装一致，但 Skill 目录中还有未管理的本地文件 |
| `drifted` | managed file 缺失或内容改变 |
| `metadata_error` | manifest 与 history record 身份或状态不一致 |
| `rollback_incomplete` | 上一次 rollback 已开始，目标处于可续跑的 before/after 混合状态 |

`source_commit`、`source_dirty`、`payload_digest` 和 `install_id` 用于回答“当前实际加载的是哪一版”。修改 agent TOML、Skill 规则或路由配置后，应先检查此输出，再开始新的 Codex 任务。

## 回退一步

从 `install-status` 复制当前 `install_id`：

```powershell
py -3.12 skill\cli.py install-rollback `
  --expected-install-id <INSTALL_ID> `
  --ack-rollback
```

```bash
python3.12 skill/cli.py install-rollback \
  --expected-install-id <INSTALL_ID> \
  --ack-rollback
```

rollback 只恢复这次安装实际改变的目标：

- 被替换或删除的文件从内容校验后的 backup 恢复；
- 本次新建的文件被删除；
- 上一 active manifest 被恢复；
- 未管理文件保持不变。

正常 rollback 要求当前 managed files 无漂移。若进程在 rollback 中断，history record 会保留 `rolling_back`，再次使用同一 `install_id` 执行命令可从已恢复和未恢复的混合状态继续。

## 本地状态布局

默认位置由 `CODEX_HOME` 与 `DYNWF_HOME` 决定：

```text
$CODEX_HOME/
  skills/dynamic-workflow/
    .dynamic-workflow-install.json
    ...managed Skill payload...
  agents/
    ...enabled managed agent TOML...

$DYNWF_HOME/
  installations/<install-id>/
    record.json
    before/
      ...replaced or removed target backups...
```

未设置 `CODEX_HOME` 时使用 `~/.codex`。未设置 `DYNWF_HOME` 时使用 `skill/platform_paths.py` 定义的平台状态目录。

## 工作区接入仍为手工操作

安装管理器只报告 `integration/AGENTS.dynamic-workflow.md` 的位置，不会推断或修改任何工作区 `AGENTS.md`。工作区规则可能包含更高优先级的安全、范围与工具约束，因此必须人工合并，不能机械覆盖。

功能边界与后续个人模块顺序见 [`module-map.md`](module-map.md)。
