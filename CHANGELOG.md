# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格记录面向使用者和维护者的重要变化。

## [Unreleased]

### Added

- 新增唯一人工可读版本源 `skill/VERSION`，以及独立的 `version-bump` 命令；支持默认升级与显式 `--prerelease`、`--release`、`--patch`、`--minor`、`--major`，但不自动 commit、tag 或 release。
- 新增个人安装管理模块与 `install-plan`、`install-apply`、`install-status`、`install-rollback`：记录 `skill_version`、source commit/dirty state、逐文件 SHA-256、active manifest 和 before backup，并对 managed drift 与路径 reparse fail closed。
- 新增个人运维说明和功能模块地图，记录当前功能边界与明确排除项。
- 新增固定 active transaction pointer：中断的 apply 由现有 `install-rollback` 恢复到 before 状态，中断的 rollback 可用同一 install ID 续跑。

### Changed

- 持久化安装路径只接受规范 POSIX 相对路径；Windows 上 case-only target collision 在写入前 fail closed。
- 个人安装历史精简为只保留紧邻上一状态的一份 rollback snapshot；成功回退后不允许继续链式回退，后续安装再建立新的单步 snapshot。
- 将 Dynamic Workflow 默认入口改为轻量 `Simple Swarm`：隐式触发至少需要两个窄而不重叠的分支，默认 2–6 个 child，root 不重复活跃分支。
- 将 checkpoint/resume、Human Gate、bounded loop 与正式 evidence 归入按需 `Managed Workflow`；将 Worktree Writer v1 保持为显式授权模式。
- 简化 read-only child packet、等待策略和结果采用规则，避免宽工作包、无限 wait 和为编排而编排。

## [1.0.0-rc.1] - 2026-08-28

这是首个发布候选。它冻结当前 `master` 的 Dynamic Workflow v1 功能面，用于隔离安装、对 Dynamic Workflow 自身精确 RC Head 的只读自审，以及在确有 verifier 支持的小范围问题时生成受限 Writer 候选；在这些发布门完成前，不创建稳定版 `v1.0.0`。外部业务仓库的 dogfooding 属于可选验证，不是本版本的发布依赖、合并门或 tag 门。

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
- Ultra Review 的 scope discovery 通过 `minItems=7` / `maxItems=7` 强制恰好七个 assignment，同时保持 `review-findings.item_limit=7`、投影 `23 / 24` 和 `max_concurrency=8`。
- map、verify 与 bounded-loop 的 child 恢复路径在采用持久化结果前重新校验声明 Schema、身份、artifact 和 lifecycle 状态。

### Security and integrity

- 运行级进程锁和 OS-backed lease，阻止同一 run 的并发执行。
- symlink、junction、reparse、Windows 8.3/长路径身份、run-root containment 和 artifact path 校验。
- gate waiting contract 不可变；terminal decision 使用独立 exclusive-create record，并绑定 input identity。
- completion state、checkpoint、summary、events 和 artifact path/size/SHA/task identity 交叉校验。
- 取消发生在 stdin drain、stdin close 或 process wait 时，进程树 cleanup uncertainty 会稳定保留为 terminal failure。
- Provider output envelope 在采纳前整体校验；map manifest 的版本、节点、连续 index、child ID、artifact 和 public output identity 在 verifier 派发前 fail-closed 复核。
- 并行 child 组发生异常时会取消并收口 sibling，避免留下未解释的 `running` 状态。
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

- 验证 `master` 分支保护及必需的 Windows/Ubuntu CI checks。
- 审计并保全旧的本地工作区未提交修改。
- 建立跟踪正式 `master` 的全新干净本地 checkout。
- 在隔离的 `CODEX_HOME` 中安装并验证本候选。
- 对 PR #27 的精确当前 Head 运行一次只读 Dynamic Workflow self-review，并在 `review-gate=waiting` 停止；不写 gate decision，不 resume。
- 仅当 self-review 产生 verifier 支持、低风险且可用 1–2 个 owned targets 修复的问题时，运行一次 Dynamic Workflow 自身的 create/modify-only Writer candidate；没有合适 finding 时以 `WRITER_CANDIDATE_NOT_JUSTIFIED` 正常关闭该门，不制造无价值改动。
- 若生成 candidate，由用户人工查看 patch、验证和 reviewer 结论后单独决定 apply、fix-first、rethink 或 discard；人工确认前不应用。
- 外部仓库审查仅为可选 dogfooding，必须使用独立授权、身份、数据和 Writer 合同，不能阻塞本 RC。
- 完成稳定观察期后，再决定是否发布 `v1.0.0`。
