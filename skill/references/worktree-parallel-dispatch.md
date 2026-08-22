# Worktree And Parallel Dispatch

本流程决定何时使用工具级并行、只读 subagent、串行写入或隔离 worktree。并行用于缩短独立工作，不扩大授权、写入范围或外部状态变更权限。

## 路由顺序

1. 独立、低风险的读取或命令调用优先使用工具级并行，不创建 agent。
2. 当前授权允许 subagent 时，独立证据收集、探索、分类和复审可主动拆成只读子任务；说明角色、范围和交付物即可，不机械追问“是否使用 subagent”。
3. 只有一个 writer，或多个写入任务可以严格串行时，直接在当前工作树执行，不为形式创建 worktree。
4. 两个或以上 writer 需要同时修改同一 repo 时，每个并发写入子任务必须使用独立 git worktree，且 `owned_targets` 必须互斥并作为封闭写入范围；临时产物目录也必须归入某一方。
5. 非 git 目录不能使用 git worktree；默认退回单 writer 串行执行，不自动 `git init`。

可用 agent、模型、推理强度和并发槽位以当前运行时与工具 schema 为准，不在流程文档中硬编码型号或固定并发数。

## 路径规则

worktree 根目录按以下优先级解析：

1. 显式 `DYNWF_WORKTREE_ROOT`；
2. 系统临时目录下的 `codex-dynamic-workflow/worktrees`。

每次运行再创建 `<YYYYMMDD>-<topic>/<writer-id>` 子目录。共享文档、角色配置和代码不得硬编码个人用户名、固定盘符或本机 Node 安装路径。创建或清理前必须展示解析后的绝对路径，并确认它不位于项目目录、`CODEX_HOME`、用户主目录根或敏感配置目录。

## Worktree 前提检查

1. 确认 repo root、branch 和 `git status -s --untracked-files=all`。只有发布、正式交接或派工基线存在歧义时才记录具体 commit/ref。
2. 工作树存在未提交改动时，明确指出新 worktree 基于 HEAD、不会包含这些改动；选择改为串行、先形成可用基线，或调整子任务，不能假设改动已复制。
3. 用 `git worktree list` 检查已有副本和路径冲突。
4. 主 agent 记录每个 writer 的 worktree、允许文件和集成顺序；不得让两个 writer 修改同一物理工作树。

## 派工规则

- 子任务必须包含：目标、只读或写入属性、允许文件、禁止动作、验证命令和交付格式。
- worktree 必须放在解析后的 `DYNWF_WORKTREE_ROOT` 下，不放项目目录内。
- 子 agent 不执行 `commit`、`checkout`、`reset`、`merge`、`branch`、`add` 等 git 写命令；worktree 创建、补丁集成和最终 commit 由主 agent 负责。
- 子 agent 不得安装、升级或删除依赖，不得写共享 `node_modules`、缓存、全局配置或项目范围外文件，除非授权包逐项点名。
- Python 项目测试必须确认从 worktree 路径加载源码，不能误用主目录 editable install。
- subagent 输出只是证据或候选补丁；主 agent 必须复核结论、变更和验证结果。

## 验收与集成

1. 每个写入子任务先报告 `git status -s --untracked-files=all` 和 `git ls-files --others --exclude-standard`。
2. 清单外修改或新增文件默认不通过；重叠改动先由主 agent 决定集成顺序。
3. 运行声明的验证命令；必跑验证不能因执行环境不便而静默跳过。
4. 通过后由主 agent 用补丁方式落到目标工作树，不用 `git merge` 合并子任务。
5. 集成前复查目标工作树分支和状态仍符合派工基线；任务明确绑定具体 commit/ref 时才额外核对该身份，不一致时停下协调。
6. 全部补丁落地后，在目标工作树执行聚合验证和最终 diff 审查。

## 卡死与清理

- 使用有界等待保持状态可见；仅经过时间、沉默或暂时没有进度，不构成中止、失败或改派依据。
- 只有用户明确取消或撤回范围，或现场已观察到关键身份不匹配、未授权的外部/破坏性/凭据操作、具体且迫近的安全风险时，才使用原生取消或关闭能力，并先停止新的相关派发、随后核对实际影响。
- 不自行放宽沙箱、审批或授权范围，也不无限自动重试。
- 失败或未复核的子任务不进入补丁集成。
- 清理前展示绝对路径并确认它位于解析后的 `DYNWF_WORKTREE_ROOT` 内；只移除对应 worktree/Junction，不递归穿透共享依赖。
