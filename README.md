# Codex Dynamic Workflow v4.2.0

仅使用原生代理、原始证据优先的 Codex Skill。正式调用名：

```text
$codex-dynamic-workflow
```

旧 `$dispatching-native-agents` 仅保留为显式兼容入口，并关闭隐式调用，避免双重自动路由。

2026-09-13 调用规则修订（Runtime 仍为 4.2.0）：
- 被动调用：自动匹配时，主线程继续执行原任务，子代理只派 Luna；有足够独立问题和额度时展开 6–12 个方向，不启动 Astra/Sol 流程。
- 主动调用：用户明确要求使用该工作流时，才加载原有 Astra 设计 → Sol 实施 → Astra 验收流程。

仅提到、讨论或修改 Skill 不算主动调用。分流以 [Skill 入口](skill/codex-dynamic-workflow/SKILL.md)为准；下文 Astra/Sol 分工与 Runtime 说明适用于显式模式。

适用：动态调查、深度审核，以及明确授权后的实现、测试、独立 review 与有限修复。
主 Skill 在 `skill/codex-dynamic-workflow/`；模型执行 profile 在 `profiles/`。
旧 `codex-workflow` Python/QuickJS 仓库保持独立。v3 新增显式 Runtime；确定性验收与真实模型集成状态分开记录。

当前协议：[v4.1 后续规则](skill/codex-dynamic-workflow/references/followup.md)与[补充分支协议](skill/codex-dynamic-workflow/references/supplemental.md)；[v4.1 设计](DESIGN_V41.md)保留初始设计记录。
确定性验收不等于真实模型联调、模型质量提升或宿主隔离证明。

## 本机验证与安装

要求 Python 3.11+；验证和安装脚本只用标准库。下面的 `python` 必须解析到满足版本要求的解释器。

```text
python -B -m unittest discover -s tests -v
python -B scripts/validate_package.py
python -B scripts/install.py --codex-home <经现场确认的CODEX_HOME>
python -B scripts/install.py --codex-home <经现场确认的CODEX_HOME> --apply
```

安装默认 dry-run。`--apply` 只更新本包拥有的 Skill 文件和 cwf_* profile；
不改 config.toml、审批、沙箱默认值、旧角色或 Git。安装前检查目标、保存精确前像，
对被替换的内容做漂移检查，完成后逐文件验证。前像不放在 Skill 扫描目录内。
不同客户端的 discovery 路径可能不同：此安装器面向现场已有的 CODEX_HOME/skills
布局；无此已确认布局时先验证 discovery，不能复制到多个位置制造同名 Skill。

Astra 负责规划、关键设计与最终验收；Sol 连贯完成授权范围内的实现、测试和修复。
必要主线不转交给可选 Luna；原始需求、完整 diff 与证据始终是验收依据。
每个有实质工作量的任务，容量允许时主动启动至少 3 个不同方向的 Luna 补充探针：
查漏覆盖、反例/失败模式、测试缺口/第二意见；有更多独立高价值方向时继续扩展。
这是每任务的启动意图下限，不是每轮重新开 3 个，也不是等齐结果才能交付。
主线不按岗位凑代理：Skill-only 下 Root 可以连贯完成工作，必要独立复核仍保留；Runtime 管理的步骤仍须准入。
具体派工问题和停止条件见[派工示例](skill/codex-dynamic-workflow/references/patterns.md)；
推理强度按任务及实际宿主/合同选择，不自动改全局默认或在旧 Runtime 合同内换挡。
主线设计/复核使用 cwf_reader（Astra），新实施使用 cwf_sol_writer（Sol）；二者默认 high，profile 不固定强度。
保留 cwf_writer（Astra）供旧合同兼容，不改写旧 run 的路由或计数。
补充探索使用 cwf_general（Luna/max），机械补充使用 cwf_mechanical（Luna/medium）。
模型名称是初始配置，不代表账户可用性、价格或实测质量。安装保留现有 luna profile 和全局默认值。

分给 Luna 前，先明确具体交付物及其复算或原始证据核对方法。Luna 可以报告「指定清单无哈希差异」
等已覆盖检查的结果；当检查不足以证明「没有缺陷」「修复完整」「可以验收」时，由主线程或 Astra
判断，并保留必要的独立复核。范围小、只读或影响低，本身不足以证明问题简单。
路由和安装测试通过不代表新旧模型方案质量相同；漏报、误报与返工仍需相同真实任务的对照评估。

Luna 也可做答案未知的探索：按独立方向收集候选原因、反例和验证证据，以覆盖范围或截止时间收尾。
Astra、Sol 和 Luna 全部通过原生代理工具派出；同一授权范围和额度内不按批次重复确认。
Luna 可批量探索和验证，三种模型共同受宿主原生槽位限制，超出的工作排队，并保留必要 Astra 复核空间。
CLI 模型派工入口已停用；Runtime 的本地 Python 命令只管理任务状态，由主线程调用原生工具执行。
此前 exec 记录及回归代码保留，不能作为当前派工入口或原生容量不足时的替代路线。

新 Runtime 默认 `workflow: "astra-mainline"`；Luna 节点必须标记 `supplemental: true`、
`required: false`，并绑定与当前候选匹配的隔离 `snapshot_root`。默认补充额度 12 次，
保护未用完的 Astra strong 额度；槽位预留覆盖已知的下一阶段必要主线工作，而不只固定留 1 个。新补充调用不能借用旧机械储备。
主线验收、补充覆盖、执行结束和线程资源清理分别报告；普通意见由 Root 简短筛查；重要发现升级后必须明确处置，调查完成不等于修复完成。
旧任务的路由与累计预算不变；未包含 ordinary 路由的旧合同不会自动加入模型。详见 [Runtime 协议](skill/codex-dynamic-workflow/references/runtime.md)。

## 2.0.2 ownership 与元数据校验

所有 canonical、legacy 和 profile 文件统一核对 `.delivery/install-state.json`。
已拥有文件与记录不一致（包括被删除）时停止；同名现有文件没有 ownership 时也停止，
即使其内容恰好等于发布包也不会隐式接管。正常升级不需要额外授权参数。

已停用并移除旧 `dispatching-native-agents` 目录时，先运行：
```text
python -B scripts/install.py --codex-home <已确认路径> --retire-missing-legacy
```
核对 dry-run 后，沿用同一命令加 `--apply`。该选项要求正式 Skill 已存在且旧目录完全缺失，
只登记 `legacy_enabled=false` 并移除旧入口的 ownership 条目，不删除或恢复文件。
后续常规升级沿用停用状态，无须重复该选项。若旧目录重新出现，安装器停止并保留其内容。
回滚恢复本次范围的文件和原 ownership 前像，不重建此前已经缺失的旧入口。

迁移或明确采用安装目录中的人工修改时，先逐文件检查内容，再对精确路径显式提供前像：

```text
python -B scripts/install.py --codex-home <已确认路径> --adopt-file "skills/dispatching-native-agents/SKILL.md=<已检查内容的SHA256>"
```

检查 dry-run 后，沿用同一批路径和 SHA256 加 `--apply`。每个同名冲突文件都要单独列出。
不接受通配符、manifest 外路径、重复条目、错误/过期哈希或缺失文件的接管。
`--expected-skill-sha` 仅是附加检查，不是接管授权。回执保留接管记录与可恢复前像。
不要自动读取当前哈希并无条件重试：这样会掩盖人工修改或并发变化。

校验器仅支持本包使用的受限 YAML 子集：两层 mapping、两空格缩进、JSON 双引号字符串、
布尔值及仅用于 name 的普通 slug。其他字符串必须加双引号（null 空值不能充当字符串）。拒绝重复字段、缺失字段、错误类型、未知字段及不支持的 YAML 语法；
不是通用 YAML 解析器。canonical 和 legacy 的名称、版本、界面及隐式调用策略都精确检查。
扩展元数据结构时必须同步扩展 schema 和测试，不能把静态 PASS 当作宿主行为证明。

## 验证级别

静态/结构测试只证明格式、链接和必须保留的合同没有明显漂移。
`policy_reference.py` 的测试验证纯参考逻辑，不是对真实模型行为或宿主安全边界的证明。
真实 Codex 集成验收另存 `reports/`，区分已观察、失败和未覆盖；不宣称零缺陷。

当前分工见 [delegation](skill/codex-dynamic-workflow/references/delegation.md)；[DESIGN_V41.md](DESIGN_V41.md) 为历史设计，`DESIGN.md` 与 `DESIGN_V3.md` 保留历史设计；本次 review、安装与验收见 `reports/`；
变更对照见 [CHANGELOG.md](CHANGELOG.md)。源目录与安装目录是独立副本。

## Windows 原位更新例外

本机若原子重命名替换被 Windows 拒绝、但同一账号的普通文件写入已验证允许，
可显式加 `--in-place-skill`，仅对已存在的 `SKILL.md` 使用普通原位写入。
不自动回退、不改 ACL、不提权、不结束占用文件的其他程序；其余文件仍原子替换。
保存写前意图和精确前像，Windows 下持有字节范围锁，完成后逐字节验证。
该例外不具备进程强杀/断电时的文件级原子性：半写状态记为恢复冲突，必须检查前像，
不会覆盖可能来自其他进程的变化或谎报已恢复。默认模式仍为原子替换。

## v4.1 Runtime 使用入口

普通 `$codex-dynamic-workflow` 按原生 Skill-only 模式工作；显式选择 Runtime 时，SQLite 统一管理动态图、调用预留、尝试记录和事件。当前新任务全部使用 native，历史 exec 记录保持可读且不改写。详细协议见 [runtime.md](skill/codex-dynamic-workflow/references/runtime.md)。

在本源码目录执行：
```text
python -B scripts/workflow.py --version
python -B scripts/workflow.py --db .delivery/runtime.sqlite init
python -B scripts/workflow.py --db .delivery/runtime.sqlite create --plan examples/runtime-readonly.json
python -B scripts/workflow.py --db .delivery/runtime.sqlite status --run RUN_ID
```
含 3 个隔离快照探针的示例可用 `python -B scripts/prepare_v4_example.py --output <不存在的任务示例目录>` 生成，再将生成的 `plan.json` 交给 create。
调度 Luna 时由 Root 将真实宿主观察传入 `next --host-capacity N --host-active M`；不能把示例数值冒充实际容量。
`RUN_ID` 使用 create 的真实返回值。Root 领取任务后调用实际 native 工具，回填准确 child ID、结果及对应生命周期回执；Python 只管理状态。`exec-one` 与 `luna-pool` 已停用，不能用于当前模型派工。

安装副本自带完整 Runtime：`python -B <Skill安装目录>/scripts/cwf.py ...`，不依赖源码目录或额外 pip 安装。根目录旧 `scripts/policy_reference.py` 只是兼容导入；真正预算函数与 Runtime 共享同一份实现。安装器排除 `__pycache__`/字节码，不把运行缓存接管成受管源码。

恢复必须显式确认旧进程/线程终结，并重新检查来源、合同、模型和宿主权限；保留已经消耗的调用预算。只读任务可重试/恢复，执行过写入的混合任务不能自动重放。默认单 writer；跨 run 的互斥要求它们使用同一个 DB，不能保护来自其他数据库或非 Runtime 工具的写入。

确定性测试覆盖真实 SQLite、竞争准入、负面状态、隔离安装副本及无害本机进程；这些不是实际模型或 native 子代理的端到端证明。真实调用和独立模型 review 的状态以 `reports/` 本轮记录为准。未完成的 live 集成验收不能标记为通过。

历史 v3 在 2026-09-06 已通过两代理真实 native readonly 执行验收，使用安装副本完成准入、实际身份绑定、原文检查、独立验证、宿主完成观察及 SQLite 重开读回。执行协调与宿主资源释放分别记账：本次 `execution_holds=0`，两条 `host_resource_holds` 仍保留，物理回收状态为 `UNKNOWN`。本地完整证据位于 `reports/native-readonly-live-20260906/report.md`；可分发源码副本不包含本地报告。

## 4.1 收尾与实际验证

[4.1 协议](skill/codex-dynamic-workflow/references/followup.md)定义 notes/claims 分流、批量 screen、
显式 resolve、增量 report，以及新候选在剩余额度内重新开放补充检查。
主线不等全部 Luna，但不把“主线已完成”当作立即中断有效探针的唯一理由。
继续运行必须有真实结果接收者和有界截止；控制器不创建后台接收机制。
真实宿主与效果比较按 `reports/V41_NATIVE_VALIDATION_PROTOCOL.md`执行；
[evaluate_native_comparison.py](scripts/evaluate_native_comparison.py)只是读取实际记录的比较器，不调用模型。
当前 `reports/V41_NATIVE_COMPARISON_STATUS.json`为 PARTIAL / NOT_QUALIFIED，正式原生验收未通过。
本轮零模型采集器与 subprocess runner 接手审查记录位于 `reports/native-validation-2026-09-11/COLLECTOR_REVIEW.md`；零模型集成已覆盖事件、RPC、持久化和清理观察，但未连接真实 Codex 模型宿主，不等于正式原生验收通过。

## 4.2.0：Astra 设计与验收，Sol 实施

不增加第二套调度器、账本或固定审查层。新 Runtime 沿用 astra-mainline 与现有节点字段，
writer 改走专属 Sol profile；实现调用计入总额度，不侵占 Astra strong 计数，也不借用机械储备。
必须提前声明并保留必要 Astra 复核额度；不因没额度而用 Sol 自审或 Luna 投票替代验收。
三个不同 Luna 方向是每个实质任务的启动意图，不是每阶段重开三名；新增方向须有实际覆盖价值。
规划说明使用现有 task/scope/check/stop 字段，Sol 可以用源码反证设计，Astra 最终必须审查方案本身。
本次更新与历史原生补验分开记录：reports/V420_ACCEPTANCE_2026-09-12.md。
当前只做零模型代码/包验证；未运行新的原生模型，不宣称实际额度节省或正式原生验收通过。
