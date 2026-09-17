# Codex Dynamic Workflow v4.3.0

仅使用原生代理、原始证据优先的 Codex Skill。正式调用名：

```text
$codex-dynamic-workflow
```

旧 `$dispatching-native-agents` 仅保留为显式兼容入口，并关闭隐式调用，避免双重自动路由。

2026-09-18 Skill 4.3.0 Threaded Phase Handoff（Runtime 仍为 4.2.0）：
- 被动调用：自动匹配时，主线程继续执行原任务；有足够独立问题和额度时展开 6–12 个 Luna 方向，并自动尝试一个有独立价值的 Grok 只读探针，不启动 Astra/Sol 流程。
- 主动调用：用户明确要求使用该工作流时，才加载 Astra 设计 → Sol 实施 → Astra 验收流程；2026-09-14 起优先使用下述线程式阶段交接。

仅提到、讨论或修改 Skill 不算主动调用。分流以 [Skill 入口](skill/codex-dynamic-workflow/SKILL.md)为准；下文 Astra/Sol 分工与 Runtime 说明适用于显式模式。

适用：动态调查、深度审核，以及明确授权后的实现、测试、独立 review 与有限修复。
主 Skill 在 `skill/codex-dynamic-workflow/`；模型执行 profile 在 `profiles/`。
旧 `codex-workflow` Python/QuickJS 仓库保持独立。v3 新增显式 Runtime；确定性验收与真实模型集成状态分开记录。

当前协议：[v4.1 后续规则](skill/codex-dynamic-workflow/references/followup.md)与[补充分支协议](skill/codex-dynamic-workflow/references/supplemental.md)；[v4.1 设计](DESIGN_V41.md)保留初始设计记录。
确定性验收不等于真实模型联调、模型质量提升或宿主隔离证明。

## 4.3.0：线程式阶段交接，Sol 执行线程接管 Root

显式 Skill-only 的复杂任务优先：**Astra 规划线程定义目标、设计边界与验收标准 → 宿主支持时将紧凑任务状态交给独立 Sol 执行线程，并由该线程成为唯一 implementation Root → Sol 连续实施、测试、修复与调度 Luna/Grok → fresh Astra 审核线程独立验收**。若宿主无法安全建立独立 controller thread，则回退为用户/宿主在当前主对话切换到 Sol。

Astra 交接必须包含原始目标和非目标、explicit workflow 模式、准确基线与未提交改动、当前授权与 allowed effects、关键设计和不变量、阶段依赖、可核验验收证据、未解决 claims、活动 child/writer ownership 与 lifecycle holds、截止条件以及累计已用/预留额度；不是提前写完全部实现。
Sol 接管后重新读取实际源码和依赖，不盲信 Astra 摘要，不为普通命令和测试失败反复召回 Astra；写完后先以代码审查者视角检查整个实际 diff，也要挑战原方案本身。

同一候选只能有一个 implementation Root。Sol 接管后原 Astra 规划线程退出实现热路径，不再写入、派工或改变候选；换线程不自动终止旧 child/writer，也不证明资源已经释放。未确认的 termination/resource hold 保持 UNKNOWN。
线程变化不创造新任务：授权、候选、未解决问题、截止条件、ownership 和累计额度继续沿用，不能因为新对话重置预算、重新获得 Luna quota、扩大权限、建立第二 writer 或新建 Runtime run 绕过旧合同。

最终验收优先使用新的 Astra review context/thread，而不是回到规划线程继续确认自己的方案。Fresh Astra 重新读取原始需求、最终 candidate、完整 diff、关键依赖、测试/证据和未解决风险；旧计划和 Luna/Grok 发现只是输入，不能成为审查范围上限。若审核打回，默认回到同一个 Sol execution Root 做 bounded repair，不因此生成新额度。

`cwf_sol_writer` 仍是普通 writer-child profile，不是 Sol execution Root；模型身份或“新开一个对话”本身都不会授予 controller/dispatch 权。只有实际当前 Root 才能调度 Luna/Grok。Skill 不能凭文本自动创建或切换 controller，只有实际宿主/用户控制可以完成并观察交接。

这是 Skill 4.3.0 的 Skill-only 交接规则；**Runtime 仍为 4.2.0**，包版本与 Runtime 版本独立校验，同一 DB/run、固定路由、writer/verifier admission、默认 12 次补充/28 次批准/32 次绝对调用额度和必要独立验收全部不变。真实原生线程记录见 [E2E 证据](reports/V430_THREADED_E2E_2026-09-18.md)；最终独立审核和对应提交的 CI 结果随发布 PR/release 记录。安装结果单独核验，不能从源码版本推断本机已更新。详细交接见 [delegation](skill/codex-dynamic-workflow/references/delegation.md)，非阻塞边界见 [supplemental](skill/codex-dynamic-workflow/references/supplemental.md) 和 [followup](skill/codex-dynamic-workflow/references/followup.md)。

复杂任务有足够独立问题时，争取 **6–12 个 Luna 调查方向**，按实际空闲容量分批，不凑数量、不同阶段不重复整批审查。
更多方向可采用事先明确批准的新任务额度；[预算说明](skill/codex-dynamic-workflow/references/budget.md)提供 24 次补充尝试的配置示例，而不暗中上调旧合同。
Luna 只读、基于准确版本/隔离快照，可以挑战方案、给出反例和测试/补丁建议，不能直接改主工作区或签署验收。
每项调查有覆盖目标和有限截止条件，普通跟进至多一次且不重置截止时间/额度。主线就绪即执行，不等无关结果齐套。
Sol 在自然检查点批量核对普通结果；可信重大风险及时处理受影响的操作，不能为追求不阻塞而忽略已经收到的风险。
当报告积压或 CPU、磁盘、测试锁、代理槽位影响主线时暂停新补充派工。收尾保留早期发现、报告未完成覆盖，不将停止请求冒充资源已释放。

额度按实际可观察的 **credit/合格交付**理解，包含 Root、子代理、筛查与返工；调用次数不是 credit。价格和质量等价不写成保证，不把未知消耗记为零。

## 2026-09-14：Burst / Grok sidecar（手动启停）

在原有主线程交接之上，隐式或显式 Skill-only 会自动评估并使用原生 OpenCodex Grok 子代理
`cwf_burst_grok` / `xai/grok-4.6`（high，只读）做设计反证、跨模块分析、候选预审、
疑难诊断和可复用证据。复杂任务默认尝试一个有独立价值的 Grok 探针；简单任务或准入失败时记录跳过原因。它不是完成门槛，也不取代 Astra 验收。
Grok 的自动可用性由 `burst.json` 的 `enabled` 手动启停；**没有自动到期、单任务调用次数、follow-up
次数或单次运行时长限制**。Grok sidecar 调用也不消耗 Astra/Sol/Luna 的 Runtime/Skill
调用计数额度；不同供应商额度仍分别记录，不能混算。
“无限次”不等于“无限阻塞”：主线永远不因可选 Grok 等待；报告积压、槽位、CPU、I/O、
测试锁或其他资源影响主线时暂停新 Grok 派工。已经返回的可信风险仍需核查。
Luna 的 `cwf_general` / `cwf_mechanical` 请求 **1M Fast**，仍可处理大范围问题；
不依据“Grok 上下文更大”分工。现有独立 luna.toml 和 OpenCodex 目录保持原样，
实际生效需原生执行证据，不能把配置值当作已经验证的能力。
详见 [Burst](skill/codex-dynamic-workflow/references/burst.md)。预检脚本只检查当前准入、
profile 和主线容量，不调用模型、不计数、不计时、不切换主线程。

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

安装 ownership state 可选记录精确 `local_overrides` 路径/SHA256。条目必须属于当前
ownership 与发行 manifest，且哈希一致；发行内容需要替换它时，只有匹配当前前像的
`--adopt-file` 才能授权。未变化条目跨升级保留，已明确接管并替换的条目移除；旧 state
缺少该字段继续兼容。安装失败或回滚恢复原 state，不自动覆盖或合并本地适配。

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
