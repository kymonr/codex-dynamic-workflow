# codex-dynamic-workflow

给 codex 桌面版的 `dynamic-workflow` 技能：把大任务拆成多个子代理并行执行。
默认使用 `native-subagent`：主会话直接调用当前会话的 Codex subagent 工具，不生成运行目录；
只有需要 runner 产物、隔离写模式、真实 `codex exec` 路径验证，或当前会话没有 native 工具时，
才使用 `cli-runner`。`cli-runner` 后端由 `src/runner.py` 确定性调度多个 `codex exec` 子进程，
并把结果汇总在运行目录的 `summary.json`。

- 计划书：`docs/plans/2026-06-13-dynamic-workflow-skill.md`
- 运行产物目录：`D:\.codex-tmp\workflows\`
- 安装位置：`C:\Users\Orz\.codex\skills\dynamic-workflow\`
- v0.1 读模式：只读子代理（分析/审查/调研，不改文件）。
- v0.2 写模式：并行改文件 + 分工，由 `prepare`/`dispatch`/`collect` 三子命令自包含实现（见下文"写模式（v0.2）"）。
- v0.3 后端选择：默认 `native-subagent`；必要时才用 `cli-runner` 保留可审计运行目录、日志和 summary。

## 后端选择（v0.3）

- `native-subagent`：当前 Codex 会话已暴露 `multi_agent_v1.spawn_agent` / `wait_agent`，且用户明确要求 dynamic-workflow / subagent / multi-agent / parallel agents / 并行分路处理时默认使用。主会话直接调用工具、等待结果并汇总；不生成 `summary.json` / `agent.log` / 运行目录。
- `cli-runner`：只有需要 `summary.json`、`agent.log`、结构化输出、token 汇总、runner stage 屏障、真实 `codex exec` smoke，写模式 `prepare` / `dispatch` / `collect` 的隔离副本与 clean gates，当前会话没有 native 工具，或用户明确点名 `cli-runner` / `codex exec` 路径时使用。`runner.py` 是普通 Python 子进程，不能调用主会话里的 `spawn_agent`/MCP 工具。
- 两种后端都必须先报子代理数量、阶段、并发、耗时和用量风险。用户当轮明确要求启动 `native-subagent` / `cli-runner` 即视为允许本轮 Codex 自调度和目录传递，不再额外追问外部模型导出确认。

## Team Router 快速使用

`codex-team-router` 是 `dynamic-workflow` 之外的 Codex desktop thread-tools 控制面：它不直接跑子代理命令，也不替代 `src/runner.py` 的 `cli-runner`；它把一个调度者的任务拆给长期可见 core role thread，并可按条件接入 reviewer，并用本地 registry/ledger 记录状态。

Progressive disclosure invariant：`skills/codex-team-router/SKILL.md` 是 Codex 8KB cap 下的短入口，只保留导航和 hard entry rules；深层协议细节放在 `skills/codex-team-router/references/`。这些 references 是 Team Router contract 的一部分，测试会同时锁住入口大小、required reference files 和关键规则覆盖。

sideEffectTaxonomy：manager 动作必须先按 `READ_ONLY`、`DISPATCH_ONLY`、`LOCAL_CLOSEOUT`、`WORKSPACE_WRITE`、`HEAVY_OR_RISKY`、`EXTERNAL_RELEASE` 分类。active Manager Mode 下 `可以`、`修`、`继续`、`开始修`、`先修`、`修这个`、`do it` 至多授权 `DISPATCH_ONLY`，不是 implementation authorization；`READ_ONLY` 只支持判断和 low-frequency/event-driven `read_thread`，不能变成实现；`WORKSPACE_WRITE` 在 active Manager Mode 下必须委派 executor，除非用户明确说“切回执行者”“你亲自改代码”或“按这个 plan 落地”；`LOCAL_CLOSEOUT` 只在 verifier pass 且 explicit user commit request 后允许本地 status/diff、stage 已验收文件、local commit，并排除无关 untracked 与 push/PR/merge/deploy；`EXTERNAL_RELEASE` 必须有独立 publish/release 授权；`HEAVY_OR_RISKY` 必须单独明确授权。命名 reviewer 审核 Team Router 自身改动时仍必须使用 visible reviewer role conversation，subagent fallback is not allowed。

roleHandoffPolicy / reviewPackagePolicy：role requests 优先通过 stable file/path handoff 传递事实，而不是依赖 accumulated chat history；manager prompt 保持短，只包含 taskId、objective、expected marker、permission boundary、相关 `taskBriefPath` / `executorReportPath` / `reviewPackagePath` 和 exact return protocol。小任务可用 inline protocol blocks；高风险 Team Router self changes、reviewer-gate/process/policy changes、长 executor results 应在 role threads 可访问同一 workspace/path 时使用 review package。review package 至少包含 taskId、objective、scope、touched/accepted files、diff summary、executor callback/report、test/verification evidence、reviewer requiredChanges、excluded unrelated untracked、risks/remainingTodos。package 只补充证据，不替代 `TEAM_ROUTER_CALLBACK` / `TEAM_ROUTER_REVIEW` / `TEAM_ROUTER_VERDICT`；写 workspace package artifacts 属于 `WORKSPACE_WRITE`，active Manager Mode 下应由 executor 做，除非明确角色切换。`taskBriefPath`、`executorReportPath`、`reviewPackagePath` 当前只是 policy concepts/future optional runtime fields，本轮不实现 runtime。commit closeout 时必须显式 stage 新 reference files，因为 `git diff --name-only` 会漏掉 untracked files。

角色分工固定为：

- 调度者：理解用户目标、选择下一步、调用 Codex thread tools，并输出 `Team Router Handoff` 或 `Team Router Closeout`。
- 状态控制器：在父线程侧维护 registry、task ledger、recovery anchors、direct-return 捕获和状态转移；它不是单独 thread。
- 规划者：只回复 `TEAM_ROUTER_PLAN`，定义 scope、stopWhen、riskBoundary 和 executorPrompt。
- 执行者：按 `TEAM_ROUTER_DISPATCH` 做 read-only/design-only 工作，并回复 `TEAM_ROUTER_CALLBACK`。
- 审查者：conditional reviewer；只在 router/manager/orchestration policy、权限/安全边界、流程规则、role protocol、shared/high-risk logic 等任务中介入，做 read-only/adversarial 挑刺并回复 `TEAM_ROUTER_REVIEW`；普通小修/明确低风险任务跳过。
- 验证者：检查 callback、reviewer 要求、证据和边界，并回复 `TEAM_ROUTER_VERDICT`；verifier remains final acceptance。

当前 Team Router 能力边界仅为 `read-only/design-only`；不支持 `workspace-write`、commit、push、PR、merge、deploy、真实 API、账号或生产数据操作。需要写代码时，应回到明确授权的普通本地实现流程，或使用 `dynamic-workflow` 写模式的 `prepare` / `dispatch` / `collect` 隔离 worktree 流程。

Manager Mode 是当前任务内的粘性角色：用户说“你作为管理者”后，该角色会一直持续到明确角色切换；后续无称呼或同类实现命令，例如 `修`、`继续`、`处理`、`先修`、`开始修`、`修这个`、`开始处理`、`先处理`、`按刚才说的修`、`go`、`do it`，只能触发计划细化、规则更新建议或 dispatch/prepare executor work，不代表 manager 可以亲自改文件或跑测试；退出该边界需要用户明确说“切回执行者”“你亲自改代码”或“按这个 plan 落地”。

父线程入口先用 `parent_entry_guard()` 判定路径：有完整 callable adapter 时才走 `orchestrate_team_task_with_adapter()`；没有 callable adapter 或 thread tools 时，只能走 manual/pre-created continuation，并且必须已经有 `manager`、`executor`、`verifier` 三个 core role thread 绑定；conditional reviewer 只在 gate 适用时创建或复用。manual/pre-created continuation 由父线程直接调用 app tools 和 manual helper/record/capture functions 续跑，不把 pre-created roles 送进 adapter runner；`parent_entry_guard(...precreated_roles...)` 只做边界判定/提示。协议/角色/状态快照由 `protocol_contract_snapshot()` 提供给测试和文档对齐；三角色可见模式 fixture 在 `tests/fixtures/team_router/three_role_visible_smoke_scenarios.json`。

Direct return 规则：当父线程/manager thread id 可用时，executor dispatch 必须包含 `returnThreadId`、`callbackDelivery: direct-send`、`callbackFallback: self-thread-marker`，并要求执行者写完 `TEAM_ROUTER_CALLBACK` 后调用 `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK block>)` 主动返回父线程；reviewer request 必须包含 `returnThreadId`、`reviewDelivery: direct-send`、`reviewFallback: self-thread-marker`，并要求审查者写完 `TEAM_ROUTER_REVIEW` 后调用 `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)`；verifier request 同理必须包含 `returnThreadId`、`verdictDelivery: direct-send`、`verdictFallback: self-thread-marker`，并要求验证者写完 `TEAM_ROUTER_VERDICT` 后调用 `send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)`。保留 self-thread marker 作为 fallback/audit 路径。

管理者 orchestration policy：等待 executor/reviewer/verifier 时，`read_thread` 轮询只能是 low-frequency、event-driven；初次可短等，之后默认 30-60s 或按任务规模放宽，只有状态变化、timeout、blocked 或 completion 才给用户可见汇报。Role reuse policy：同一 `taskId` 或同一 task family 默认 reuse existing executor、existing reviewer（当 conditional reviewer gate 适用）和 existing verifier thread；返工继续发给 original executor，审查返工继续发给 original reviewer，复核返工继续发给 original verifier；只有 role、permission、workspace、task-family boundary 或 isolation requirement 变化时才 `create_thread` 新 role thread。conditional reviewer gate：普通小修/明确低风险任务保持 executor -> verifier；router/manager/orchestration policy、权限/安全边界、流程规则、role protocol、shared/high-risk logic 必须走 executor -> reviewer(read-only/adversarial) -> verifier(read-only acceptance)。reviewer 独立挑设计风险、规则漏洞、遗漏和新坏模式，不做实现，not final acceptance；verifier remains final acceptance。runtime gate 使用 `send_reviewer_request_with_adapter()`、`read_reviewer_review_update_with_adapter()` 和 `capture_reviewer_review_from_read()` 执行 reviewer step：reviewer `pass` 后才进入 verifier，`needs_rework` 回到 executor rework，`blocked` 进入 blocked。用户点名 `reviewer` 审核 Team Router 自身改动时，manager 必须使用 reviewer role conversation/thread；没有 existing reviewer thread 时必须显式 create/register reviewer role conversation，或说明缺口并等待确认，subagent fallback is not allowed。Trigger logic covers `runtime gate`, `reviewer gate`, `Team Router self changes`, and `Team Router` combined with reviewer/runtime/protocol/policy/permission/safety/process/shared/high-risk semantics; a plain `team_router.py` filename or low-risk docs-only/single-file cleanup does not trigger reviewer by itself。

Manager commit closeout policy：用户只和 manager 对话时，manager owns commit workflow。verifier pass 后且用户明确要求提交时，manager 可以作为 closeout 操作执行本地 `git status` / `git diff`、stage 已验收文件、commit；不得借提交继续实现、修改文件或跑重型命令；必须排除无关 untracked。push/PR/merge/deploy 单独授权。

roleCloseoutPolicy：任务完成后默认不 clear role thread，也默认不向 role threads 额外发送 ROLE_CLOSEOUT 或普通 closeout 消息。final protocol block is the closeout：executor 的 `TEAM_ROUTER_CALLBACK`、reviewer 的 `TEAM_ROUTER_REVIEW`、verifier 的 `TEAM_ROUTER_VERDICT` 已经足够作为任务结束锚点。compact is native operation, not chat prompt；manager 不得通过发送 `compact` 或 `ROLE_CLOSEOUT` 文本假装压缩上下文。若当前环境支持 native compact 且确有必要（例如 role thread 上下文过长），manager 可以触发 native compact；没有可用 compact 工具则不做。只有 role thread 仍 active/inProgress 且需要停止、没有 final protocol block 需要最短停止锚点、准备 compact/archive 前需要极短恢复锚点、或用户明确要求时，才可发送最短 closeout/stop message。clear 不作为默认动作；新建或归档旧 role thread 仅限身份污染、上下文过长、task family/permission/workspace boundary 变化或用户明确要求。

## 运行环境结论（任务 1 探针填写）

### 1. `codex exec` 非交互可用，但当前沙箱内会失败

结论：`codex exec` 本身可用，输出文件含 `PONG`；但在当前 Codex 沙箱内直接运行会因为无法写 `C:\Users\Orz\.codex` 状态/临时目录失败，必须升级权限/沙箱外执行。

命令：

```powershell
codex exec -s read-only --skip-git-repo-check --color never -C D:\.codex-tmp -o D:\.codex-tmp\20260613-dynamic-workflow\probe-baseline.txt "只输出单词 PONG,不要输出其他任何内容"
Get-Content D:\.codex-tmp\20260613-dynamic-workflow\probe-baseline.txt
```

沙箱内输出：

```text
WARNING: failed to clean up stale arg0 temp dirs: 拒绝访问。 (os error 5)
WARNING: proceeding, even though we could not create PATH aliases: 拒绝访问。 (os error 5) at path "C:\\Users\\Orz\\.codex\\tmp\\arg0\\codex-arg0VbXgp4"
WARN codex_state::runtime: failed to open state db at C:\Users\Orz\.codex\sqlite\state_5.sqlite: error returned from database: (code: 8) attempt to write a readonly database
WARN codex_rollout::state_db: failed to initialize state runtime: failed to initialize state runtime at C:\Users\Orz\.codex\sqlite: error returned from database: (code: 8) attempt to write a readonly database
Reading additional input from stdin...
Error: failed to initialize in-process app-server client: 拒绝访问。 (os error 5)
```

升级权限/沙箱外输出文件：

```text
PONG
```

### 2. Python 不能直接启动 PATH 上的 `codex` 垫片

结论：`shutil.which("codex")` 命中 `C:\Users\Orz\AppData\Roaming\npm\codex.CMD`；Python 直接 `subprocess.run(["codex", "--version"])` 失败。真实可直启二进制为 `C:\Users\Orz\AppData\Roaming\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe`，直接启动输出 `codex-cli 0.139.0`。

命令：

```powershell
python -c "import shutil; print(shutil.which('codex'))"
python -c "import subprocess; print(subprocess.run(['codex','--version'], capture_output=True, text=True).stdout)"
Get-Command codex | Format-List *
python -c "import subprocess; p=r'C:\Users\Orz\AppData\Roaming\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'; print(subprocess.run([p,'--version'], capture_output=True, text=True).stdout)"
```

输出：

```text
C:\Users\Orz\AppData\Roaming\npm\codex.CMD
PermissionError: [WinError 5] 拒绝访问。
Path               : C:\Users\Orz\AppData\Roaming\npm\codex.ps1
codex-cli 0.139.0
```

执行备注：`src\runner.py` 的 `DEFAULT_CODEX_CMD` 已按该探针结论填入真实 `codex.exe` 绝对路径；Codex 升级或 npm vendor 路径变化后需重新跑探针并更新。

### 3. 嵌套探针结果 B：需要升级权限运行 runner

结论：在当前 Codex 会话里直接生 `codex` 子代理，沙箱内失败；同一命令升级权限/沙箱外执行成功，`probe-nested.txt` 内容为 `PONG`。因此本环境不是结果 C，可以继续后续任务；但 runner 真实运行必须申请升级权限/沙箱外执行。

命令：

```powershell
codex exec -s read-only --skip-git-repo-check --color never -C D:\.codex-tmp -o D:\.codex-tmp\20260613-dynamic-workflow\probe-nested.txt "只输出单词 PONG,不要输出其他任何内容"
Get-Content D:\.codex-tmp\20260613-dynamic-workflow\probe-nested.txt
```

沙箱内输出：

```text
WARNING: failed to clean up stale arg0 temp dirs: 拒绝访问。 (os error 5)
WARNING: proceeding, even though we could not create PATH aliases: 拒绝访问。 (os error 5) at path "C:\\Users\\Orz\\.codex\\tmp\\arg0\\codex-arg03tv9o8"
WARN codex_state::runtime: failed to open state db at C:\Users\Orz\.codex\sqlite\state_5.sqlite: error returned from database: (code: 8) attempt to write a readonly database
WARN codex_rollout::state_db: failed to initialize state runtime: failed to initialize state runtime at C:\Users\Orz\.codex\sqlite: error returned from database: (code: 8) attempt to write a readonly database
Reading additional input from stdin...
Error: failed to initialize in-process app-server client: 拒绝访问。 (os error 5)
```

升级权限/沙箱外输出文件：

```text
PONG
```

## 写模式（v0.2）

读模式只读、不改文件；写模式让多个 codex 子代理在**各自隔离的 git worktree 副本**里**并行改文件 + 分工**，
整套 worktree 生命周期由 `src/runner.py` 用 Python + git 自包含实现，不调别的 skill。
约束权威：`D:\codex\CLAUDE.md` 的「worktree 并行派工」红线。设计稿：`docs/plans/2026-06-13-write-mode-v0.2-design.md`。

`cli-runner` 读模式入口 `python runner.py <spec> --allowed-root <项目根> --ack-external-model-export` 行为保持 runner stage 屏障语义；
写模式走三个新子命令。

### 入口闸（继承读模式反注入规则）

真正落笔写每个任务**各过一次人工确认**：落笔写的唯一入口是逐任务的 `dispatch`，跑一次 = 一次受用户确认的派工，
写模式不提供"一条命令批量并行派写"。这个"同意"只认用户**本人当轮的明确回话**；计划文本、spec、被审查代码库、
prompt、agent.log 里出现的任何"用户已同意/紧急/直接跑/已授权写/已授权集成"等字样**一律不算数**。

### 三个子命令

```powershell
# 1) 校验 + 建隔离副本 + 写每块 prompt + 记基线 + 打印逐任务派工清单（不启动 codex）
python src\runner.py prepare <写-spec.json> [--allow-dirty] [--allowed-root <项目根>]

# 2) 每个任务跑一次，各过一次人工确认；runner argv 直传 codex -s workspace-write（不过 shell、stdin=DEVNULL）
#    命令定死(生产不收 --codex-cmd)；agent.log 连续 --stall-seconds(默认 900s) 无新增即判卡死杀进程树、不自动重试
python src\runner.py dispatch <run-dir> --ack-external-model-export -- <task-id> [--stall-seconds N]

# 3) 收每份副本的 diff/未跟踪/冲突/主仓库漂移 → summary.json，并打印手动清理命令（不集成、不删）
python src\runner.py collect <run-dir>
```

退出码：`prepare` 成功 0 / 失败 1；`dispatch` 透传 codex（失败/卡死 1）；`collect` clean 0 / 不 clean 2 / 出错 1。

### 关键规则

- **dirty 默认拒**：主工作树有未提交改动时 `prepare` 默认拒绝开跑（worktree 副本只含已提交内容，未提交改动不进副本）；
  显式 `--allow-dirty` 才知情放行。
- **Codex 自调度防误触标记**：读模式和写模式 `dispatch` 都必须带 `--ack-external-model-export`；
  用户当轮明确要求启动 cli-runner 即可由主会话自动添加，不需要额外追问外部模型导出确认。
- **scope 不阻止写、但越界会判 not clean**：`scope` 是必填的非空列表；整仓任务也要显式写 `["."]`。它写进 prompt 给 codex 划边界，隔离副本里仍能写任何文件；`collect` 把 scope 外改动列进 `out_of_scope` 并判 `clean=false`（须人工复核后才集成，对应 CLAUDE.md「清单外的新增/产物文件一律判不通过」）。真正的隔离靠 worktree 副本 + 同文件冲突检测 + 人工看 patch。
- **collect 反映派工真相**：collect 读 `dispatch` 落的结果，并校验 `dispatch_nonce` / `prompt_sha256` / `worktree` / `base_head` 和当前 `prompt.txt` hash。这是防单边误改的一致性检查，不是防有意协同篡改的密码学证明。没派工→`not_dispatched`、派工非 0 或一致性失败→`dispatch_failed`、副本被偷偷 `git add`→`index_changed`、只产生 ignored 文件→`ignored_files`，任一都判 `clean=false`，避免「没真跑、跑失败、ignored-only 或手改一侧记录」被当成干净。
- **runner 不集成、不自动删副本**：到 `collect` 出 `changes.patch` 为止就停。应用补丁、跑测试、commit、删副本全是人工/主会话的活；清理用 `collect` 打印的 `git -C <workdir> worktree remove <wt>` 命令。
- **任务数上限 8**；>2 时 `prepare` 打警告。
- 写模式产物根**钉死** `D:\.codex-tmp\workflows\`，不认 `DYNWF_RUNS_ROOT`（读模式才认）。

### 写模式产物目录

```text
D:\.codex-tmp\workflows\<name>-<时间戳>-<随机>\
  summary.json          # 基线(base_head)+ 各块状态 + clean / overlaps / main_drift
  wt\<id>\              # 每块的隔离 worktree 副本
  tasks\<id>\
    prompt.txt          # 该块 prompt（含 scope 边界提示 + "不要跑 git"）
    agent.log           # codex 子代理的文字回答
    changes.patch       # collect 生成：该副本相对 base 的 diff（含二进制）
    untracked\          # collect 生成：未跟踪新文件内容镜像（git diff 不含未跟踪文件，另存以免丢内容）
```

summary.json 顶层键：`name` / `run_dir` / `mode` / `base_head` / `current_main_head` / `workdir` /
`status_raw` / `clean` / `main_drift` / `overlaps` / `tasks`；任务级状态串：`ok` / `no_changes` / `error` /
`not_dispatched` / `dispatch_failed`（任务条目另含 `head_changed` / `index_changed` / `ignored_files` /
`out_of_scope` / `dispatched` / `dispatch_exit_code` / `dispatch_error` / `untracked_bundle` 等明细）。

## 测试

```
python -m unittest discover -s tests -v
```
