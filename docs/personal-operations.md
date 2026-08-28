# Personal Operations

本页只面向个人日常维护：设置可读版本号、确认实际安装版本、预览覆盖范围、应用精确安装，以及最多回退一步。所有命令均为本地零模型操作，不调用 Codex 模型，也不会修改工作区 `AGENTS.md`。

## 推荐流程

```text
version-bump
→ review and commit skill/VERSION
→ install-plan
→ install-apply
→ install-status
```

版本升级和安装是两个独立事务。`version-bump` 只修改仓库中的 `skill/VERSION`；安装命令只安装已经确定的版本。

## 设置下一版本

当前版本的唯一来源是：

```text
skill/VERSION
```

文件使用严格语义版本，只接受：

```text
MAJOR.MINOR.PATCH
MAJOR.MINOR.PATCH-rc.N
```

默认升级规则：当前是 RC 时递增 RC；当前是正式版时递增 patch。

```powershell
py -3.12 skill\cli.py version-bump --source-root .
```

```bash
python3.12 skill/cli.py version-bump --source-root .
```

也可以显式指定：

```text
--prerelease  1.0.0-rc.2 → 1.0.0-rc.3
--release     1.0.0-rc.2 → 1.0.0
--patch       1.0.0      → 1.0.1
--minor       1.0.1      → 1.1.0
--major       1.1.0      → 2.0.0
```

对正式版执行 `--prerelease` 会进入下一个 patch 的 `rc.1`，例如 `1.0.0 → 1.0.1-rc.1`。`--release` 只允许当前版本为 RC。

该命令原子写入 `skill/VERSION`，但不提交 Git、不创建 tag，也不触碰 `CODEX_HOME`。

## 安装计划

从仓库根目录执行：

```powershell
py -3.12 skill\cli.py install-plan --source-root .
```

```bash
python3.12 skill/cli.py install-plan --source-root .
```

命令不会创建 `CODEX_HOME` 或 `DYNWF_HOME`，输出中的 `writes` 始终为空。重点检查：

- `skill_version` 是否是准备安装的版本；
- `source_commit` 与 `source_dirty` 是否符合预期；
- `managed_files[].action` 是 `create`、`replace_managed`、`replace_unmanaged`、`adopt_existing` 或 `unchanged`；
- `stale_files` 是否只包含上一 manifest 拥有、且仍与记录一致的旧文件；
- `blocked` 是否为空；若存在未完成事务，会显示 `active_install_transaction` 并拒绝新计划；
- `plan_digest` 是否是准备应用的精确计划摘要。

启用的 agent 只包括 `config/agents/` 根目录下扩展名恰好为 `.toml` 的文件。`grok_writer.toml.disabled`、Python cache、`.pyc`、`.pyo` 和本地安装 manifest 不会进入安装载荷。`skill/VERSION` 会作为 managed file 安装到 `$CODEX_HOME/skills/dynamic-workflow/VERSION`。

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

应用时会重新生成计划；版本文件、源文件、目标文件、活动 manifest 或路径身份发生变化都会使摘要不匹配并拒绝继续。写入顺序为：

1. 获取安装级 OS-backed lease；
2. 备份所有将被替换或删除的目标；
3. 写入 `prepared` rollback record，并发布固定的 active transaction pointer；
4. 原子写入新文件并删除已确认未漂移的 stale managed file；
5. 逐文件重新验证 SHA-256；
6. 最后发布 active manifest；
7. 将 rollback record 标记为 `applied`，删除 active transaction pointer；
8. 清理上一份已不可寻址的 rollback snapshot。

安装器不会删除未被上一 manifest 管理的额外文件，也不会覆盖已经发生漂移的 managed file。第一次接管一个同名未管理文件时，计划会显示 `replace_unmanaged`，应用前会先保存其原始内容。

## 检查实际安装身份

```powershell
py -3.12 skill\cli.py install-status
```

```bash
python3.12 skill/cli.py install-status
```

用于识别安装的主要字段：

```text
skill_version
source_commit
source_dirty
payload_digest
install_id
rollback_available
previous_skill_version
```

其中 `skill_version` 便于人工查看，`source_commit` 对应源码身份，`payload_digest` 绑定实际 managed payload。三者同时保留，避免只有版本号却无法确认内容。

主要状态：

| 状态 | 含义 |
|---|---|
| `not_installed` | 没有 active manifest |
| `clean` | 所有 managed file 与 active manifest 一致 |
| `clean_with_unmanaged_files` | 安装一致，但 Skill 目录中还有未管理的本地文件 |
| `drifted` | managed file 缺失或内容改变 |
| `metadata_error` | manifest 与当前 rollback record 身份或状态不一致 |
| `apply_incomplete` | apply 已中断；使用 pending install ID 执行 `install-rollback` 恢复到 apply 前状态 |
| `rollback_incomplete` | rollback 已开始或终态尚未发布；使用同一 install ID 续跑 |

修改 agent TOML、Skill 规则或路由配置后，应先检查此输出，再开始新的 Codex 任务。

## 只回退一步

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

只保留当前安装对应的一份 rollback snapshot。成功回退后，恢复出来的版本会显示 `rollback_available: false`，不能继续链式回退。下一次 `install-apply` 会重新建立一份新的单步 snapshot。

正常 rollback 要求当前 managed files 无漂移。若 apply 中断，`install-status` 会返回 `apply_incomplete` 和 `pending_install_id`；使用该 ID 执行同一 `install-rollback` 命令会恢复 apply 前状态，不会继续原计划。若 rollback 中断，则返回 `rollback_incomplete`，再次使用同一 ID 可续跑。

## 本地状态布局

默认位置由 `CODEX_HOME` 与 `DYNWF_HOME` 决定：

```text
$CODEX_HOME/
  skills/dynamic-workflow/
    VERSION
    .dynamic-workflow-install.json
    ...managed Skill payload...
  agents/
    ...enabled managed agent TOML...

$DYNWF_HOME/
  install-manager/
    active-transaction.json  # 仅事务未完成时存在
  installations/<active-install-id>/
    record.json
    before/
      ...immediately previous target state...
```

旧 snapshot 在新安装成功后清理；它们不会形成可选择的历史版本仓库。未设置 `CODEX_HOME` 时使用 `~/.codex`。未设置 `DYNWF_HOME` 时使用 `skill/platform_paths.py` 定义的平台状态目录。

## 工作区接入仍为手工操作

安装管理器只报告 `integration/AGENTS.dynamic-workflow.md` 的位置，不会推断或修改任何工作区 `AGENTS.md`。工作区规则可能包含更高优先级的安全、范围与工具约束，因此必须人工合并，不能机械覆盖。

功能边界见 [`module-map.md`](module-map.md)。
