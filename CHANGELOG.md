# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格记录面向使用者和维护者的重要变化。

## [1.0.0-rc.1] - Unreleased

这是首个发布候选。它冻结当前 `master` 的 Dynamic Workflow v1 功能面，用于隔离安装、真实业务仓库只读试运行和受限 Writer 候选验证；在这些发布门完成前，不创建稳定版 `v1.0.0`。

### Added

- Workflow IR v3：受限、版本化、可校验的声明式工作流格式。
- 可信控制流节点：`agent`、`map`、`verify`、`reduce`、`conditional`、`human_gate`，以及满足 Bounded Loop v1 完整合同的受限 `loop`。
- 内容寻址 artifact、事件日志、checkpoint、显式 resume 和 no-replay 恢复合同。
- `plan-ir`、`run-status`、`gate-status`、`gate-decide`、`resume-ir` 等操作命令。
- 三个固定只读 Swarm 预设：`design-swarm`、`ultra-review`、`repo-sweep`。
- Auto Planner v1：一个 Luna 只从固定注册表选择预设，不能生成任意 DAG 或扩大权限。
- Bounded Loop v1：有限迭代、严格 verifier、canonical progress digest、no-progress、iteration limit 和 whole-workflow absolute deadline。
- Worktree Writer v1：显式 package、宿主创建 detached worktree、单 Luna Writer、真实 effect reconciliation、固定 argv 验证、不可变 candidate capture、fresh read-only Sol reviewer、`writer-status`、`writer-export` 和显式 cleanup。

### Changed

- CLI、运行状态目录和 worktree 默认路径改为跨平台解析，不再依赖固定用户名或盘符。
- Windows 子任务在 `--ignore-user-config` 下显式恢复 `windows.sandbox=elevated`，同时保留只读或隔离 worktree 的精确 sandbox 请求。
- reference repository audit 使用显式 accepted/rejected record 与分支专属 closeout，避免把 `depends_on` 误当作数据注入。
- `resume-ir` 将 `execution` 视为可信 resolved artifact 的派生元数据，重新计算并严格比较后再恢复。
- public Python CLI 入口在 Windows 非 UTF-8 主机编码下统一配置 UTF-8 stdout/stderr。

### Security and integrity

- 运行级进程锁和 OS-backed lease，阻止同一 run 的并发执行。
- symlink、junction、reparse、Windows 8.3/长路径身份、run-root containment 和 artifact path 校验。
- gate waiting contract 不可变；terminal decision 使用独立 exclusive-create record，并绑定 input identity。
- completion state、checkpoint、summary、events 和 artifact path/size/SHA/task identity 交叉校验。
- 取消发生在 stdin drain、stdin close 或 process wait 时，进程树 cleanup uncertainty 会稳定保留为 terminal failure。
- Writer package 使用封闭 Schema、canonical digest、精确 owned targets、create/modify-only authority 和单 Writer lock。
- Writer 结果由宿主读取真实 Git/filesystem effects；拒绝 unowned、delete、rename、mode、binary/NUL、LFS、symlink/reparse、submodule/gitlink、Git metadata 和 candidate 外部效应。
- Reviewer 只消费冻结 candidate，不能写入或自动触发修复循环。

### Validation

- 组合候选在 Windows 和 Ubuntu、push 与 pull-request 两种触发下均通过 CI。
- 合并后的正式 `master` 再次通过 Windows 和 Ubuntu CI。
- 已完成真实 Windows RC：
  - reference workflow `reject → resume → terminal rejected closeout`；
  - `design-swarm` 运行到 `review-gate=waiting`；
  - Auto Planner v1 单 Luna 选择固定预设；
  - Bounded Loop v1 `reject × 3 → iteration_limit → needs_escalation`；
  - Worktree Writer v1 一次 Luna Writer + 一次 fresh Sol Reviewer，终态 `ship_candidate`，候选未应用到 canonical checkout。

### Known limitations

- `max_tokens` 仍是 advisory；若 Codex CLI 不提供 usage，不能作为可靠硬停止条件。
- `observed_sandbox=unknown` 必须如实保留；sandbox 请求参数、健康 helper/provisioning 和宿主观察到的 effects 不是独立的 per-child enforcement attestation。
- Windows 无 symlink privilege 的环境会跳过需要创建真实 symlink 的测试；不会为了测试通过而扩大权限。
- `actor` 与 `source` 是未经认证的审计标签，不构成身份认证。
- 旧式或不完整的 `loop` 声明仍为 instance-level validated-only，并在执行前明确拒绝。
- Writer 不会自动 apply 到 canonical checkout，也不会自动 `git add`、commit、push、merge、release 或 deploy。
- Writer 中断后不自动 retry/resume；reviewer `fix-first` 不触发自动 Writer 循环。

### Release gates still open

- 启用并验证 `master` 分支保护及必需的 Windows/Ubuntu CI checks。
- 审计并保全旧的本地工作区未提交修改。
- 建立跟踪正式 `master` 的全新干净本地 checkout。
- 在隔离的 `CODEX_HOME` 中安装并验证本候选。
- 对 `kymonr/shopee-order-collector` 的精确候选分支运行一次只读 `ultra-review` 或 `repo-sweep`。
- 仅在人工选定一个低风险改动后，运行一次 create/modify-only Writer candidate；人工确认前不应用。
- 完成稳定观察期后，再决定是否发布 `v1.0.0`。
