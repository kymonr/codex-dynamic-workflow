# dynamic-workflow 写模式 v0.2 设计(v0.3 稿)

> 2026-06-13。把 codex-dynamic-workflow 从「只读多子代理编排」升级为「可**并行写文件 + 分工**」,
> 完全自包含在 `src/runner.py` 里,不依赖工作区其它 skill。
> 约束权威:`D:\codex\CLAUDE.md` 的「worktree 并行派工」红线(对任何 codex 并行写生效)。
>
> 状态:**设计稿 v0.3**。已过两轮 codex 只读复核:
> ① 单审(确认结构 + 补 dirty-repo);② 4 审查员并行复核(安全/可行性/完整性/简化)。
> 本稿据第二轮发现做了实质修订:**加 `dispatch` 子命令、砍自动 cleanup、scope 降级为提示**,
> 并折入 10 条 P1/P2 修正。下一步是写实现计划(writing-plans)。本文件未提交,提交另走用户 gate。

---

## 1. 目标与范围

把一个大改动**拆成多个互相独立的块**,每块交一个 codex 子代理在**隔离 worktree 副本**里改文件
(分工),最后把各块改动收集成可人工验收的 patch。对标 Claude dynamic workflow 的
`isolation: 'worktree'` + 人工集成,做成 codex 版、守工作区红线。

**v0.2 范围(已与用户确认):**
- 只支持**独立分工**:每块改各自的文件/目录,彼此不碰同一个文件。
- 半自动:runner 建隔离副本、逐个派写、收 diff;但**真正落笔写每个任务各过一次人工确认**,
  且 runner **永不集成、永不自动删副本**。
- 自包含:整套 worktree 生命周期由 runner 自己用 Python + git 实现,不调别的 skill。

## 2. 非目标(刻意不做)

- ❌ 同文件并行写(多块抢改同一文件)——风险大,留以后。
- ❌ runner 一条命令批量并行派写——会把「每次派工一次确认」批量化,违红线。改用**逐任务 `dispatch`**。
- ❌ runner 自动集成(apply / merge / commit)——人工做。
- ❌ **runner 自动删副本(cleanup 子命令)**——自动删除是最大风险源;`collect` 只**打印**手动清理命令,
  由人确认后自己删。砍掉自动删除同时降低风险和代码量(第二轮 simplicity 审查员建议,采纳)。
- ❌ 选模型——同读模式 v0.1,统一默认模型。
- ❌ 依赖 `worktree-parallel-dispatch` skill——自包含。

## 3. 总体架构:三个子命令 + 读模式不变

现有 `python runner.py <spec>`(只读)**一行不改**,仍是默认行为。写模式新增三个 argparse 子命令。
关键:把「真正落笔写」做成**逐任务的 `dispatch`**,每任务一条命令 = 一次人工确认 = 守住红线,
同时彻底消掉「把 prompt 塞进可复制 shell 命令」带来的注入 / stdin 卡死 / Windows 转义一整类问题。

```
runner.py prepare <写-spec> [--allow-dirty]
    校验 + 建 N 份隔离 worktree 副本(--detach base_head)+ 写每块 prompt + 记基线 + 打印逐任务派工清单
        ↓
runner.py dispatch <run-dir> <task-id>     ← 每个任务跑一次,各过一次人工确认
    runner 内部用 argv 直接 exec `codex -s workspace-write`(不过 shell、stdin=DEVNULL)在该副本里写
        ↓  (所有任务都 dispatch 完之后)
runner.py collect <run-dir>
    收每份副本相对基线的 diff(含被 commit 的改动)+ 未跟踪文件内容 + 同文件冲突 + 主仓库漂移 → summary.json
        ↓  (collect 打印手动清理命令;人工看 patch、验主 HEAD 未变、补丁式落到主工作树、跑测试、commit —— 都不归 runner)
```

为什么 `dispatch` 单独成命令:真正「落笔写」每个 codex 要**各过一次人工确认**(红线)。
让人逐个跑 `runner.py dispatch <run-dir> <id>`——每次调用就是一次受确认的派工,
而 prompt 由 runner 用 argv 直接传给 codex(像现在只读 runner 那样 `create_subprocess_exec`,
不过 shell、且 `stdin=DEVNULL`),不存在复制粘贴 prompt 的注入/卡死/转义风险。

## 4. 写 spec 格式

独立分工,所以**没有 stage、没有 `{{result}}` 跨引用**:

```json
{
  "version": 1,
  "mode": "write",
  "name": "fix-three-modules",
  "workdir": "D:\\codex\\某项目",
  "tasks": [
    { "id": "moduleA",
      "prompt": "你只负责改 src/moduleA 下的文件,绝不碰其他目录,也不要跑任何 git 命令",
      "scope": ["src/moduleA"],
      "reasoning_effort": "high" },
    { "id": "docs",
      "prompt": "你只负责改 docs 下的文档...",
      "scope": ["docs"] }
  ]
}
```

字段规则:
- `mode`: `"write"`(缺省或 `"read"` 走现有只读路径)。
- `workdir`: **必须是 git 仓库**;复用现有 workdir 安全校验(拒盘符根 / 用户主目录 / 敏感配置目录)。
- 每个 `task` = 一份独立 worktree = 一次独立 `dispatch`。
- `scope`(可选,**提示字段,非安全护栏**):写进 prompt 给 codex 划边界;`collect` 会**报告**实际改动
  是否落在 scope 外(警告,不阻断)。真正防越界靠隔离副本 + 同文件冲突检测 + 人工看 patch。
- **任务数上限 8**;>2 时 `prepare` 打**警告**(不再要额外同意——每个写已由逐任务 `dispatch` 各自确认)。
- 不支持选模型;`-s workspace-write` 由 runner 硬编码,spec 改不动。
- 复用现有校验:`name` / `task id`(含 Windows 保留名 / 大小写去重)/ prompt 长度 / UTF-8。

## 5. dirty-repo 处理

**根因**:`git worktree add` 建的副本只含**已提交内容**;主工作树里未提交的改动不进副本,
否则 codex 子代理从「上次提交」而非「当前工作状态」开始改,用户 WIP 被静默忽略。

`prepare` 行为:
- `git status --porcelain -z` 检测主工作树 dirty;把 **base HEAD + 该 `git status` 原文**记进
  run-dir 的 `summary.json`(不单设 baseline 文件)。
- **默认:dirty 就拒绝开跑**,打印未提交文件清单 + 「这些改动不会进副本」,退出码非 0。
- 要继续必须显式 `--allow-dirty`(= 知情确认「就用已提交状态跑」)。

依据 CLAUDE.md「工作树有未提交改动时先向用户说明,**由用户决定**」。runner 非交互,默认拒是最干净的
安全默认;`--allow-dirty` 是知情覆盖。

## 6. 安全:`CLAUDE.md` 每条 worktree 红线 → runner 机制(映射表)

| CLAUDE.md 红线 | runner 里怎么落地 |
|---|---|
| 每次派工一次人工确认、不批量跳 | **`dispatch <run-dir> <id>` 逐任务跑**,一次调用一次确认;`prepare` 不派写 |
| 派工命令模板定死、拒改沙箱/审批参数 | `dispatch` 内 `build_write_cmd` 硬编码 `-s workspace-write`,**argv 直传不过 shell**,spec 无法透传 |
| 子进程 stdin 不挂死/不抢主会话 | `dispatch` exec codex 时 **`stdin=DEVNULL`**(修现有 runner 只重定向 stdout/stderr 的隐患) |
| 并行上限默认 2、最多 8 | `validate` 拒 >8;>2 打警告 |
| 副本放 `D:\.codex-tmp`、不进项目目录 | worktree 建在 `D:\.codex-tmp\workflows\<run>\wt\<id>`;**写模式不认 `DYNWF_RUNS_ROOT` 覆盖**,根钉死 |
| 建副本前记 base HEAD + 查无遗留副本 | `prepare`:`git worktree list --porcelain -z`(归一化)查遗留,有就拒;记 base HEAD |
| 严格从基线建副本、不污染分支 | `git worktree add --detach <path> <base_head>`(**带 `--detach`**,不按路径名建/撞分支) |
| worktree 副本只含已提交内容 | `prepare` 默认拒 dirty,`--allow-dirty` 才知情放行(第 5 节) |
| codex 不跑 git 写命令 | prompt 明令禁止;`collect` 查副本 HEAD == base(偷偷 commit 标 `head_changed`),且 diff 取 `base..工作树` 仍能拿到被 commit 的改动 |
| 验收含未跟踪文件扫描、不只看 diff | `collect`:`git status --untracked-files=all -z` + `git ls-files --others --exclude-standard -z`,**并打包未跟踪文件内容**进验收材料 |
| 集成前复查主 HEAD/status 一致 | `collect` 比对当前主 HEAD/status 与 base;**漂移 → `clean=false`、退出码非 0** |
| 集成走补丁、不走 merge、人工做 | runner 只产 `changes.patch`(`git diff --binary <base>`,含二进制),**绝不** apply/merge/commit |
| 收尾只删副本、防穿透 | **runner 不自动删**;`collect` 打印手动 `git worktree remove` 命令 + 绝对路径,由人确认后自己删 |

**额外安全增值**:同文件冲突检测——`collect` 用 `git diff --name-only` ∩ 各块 untracked 取交集,
两块碰同一文件 → `overlaps` 标红、`clean=false`、退出码非 0。

## 7. 三个子命令的接口与产物

### prepare(输入:写-spec;产出:run-dir)
1. `validate_write_spec`(白名单,复用现有校验 + 第 4 节规则)。
2. 确认 `workdir` 是 git 仓库;`git worktree list --porcelain -z` 查遗留副本(有就拒)。
3. dirty 检测(第 5 节):默认拒,`--allow-dirty` 放行。
4. **原子建 run-dir**(`mkdir(exist_ok=False)`,兜并发 prepare 的 TOCTOU);run-dir 根钉死
   `D:\.codex-tmp\workflows`,不认 `DYNWF_RUNS_ROOT`。写 `summary.json` 骨架(base HEAD + `git status`
   原文 + tasks)。
5. 每块:`git worktree add --detach <run-dir>\wt\<id> <base_head>`;写 `tasks\<id>\prompt.txt`
   (含 scope 提示 + 「不要跑 git」)。
6. 打印逐任务派工清单:`runner.py dispatch <run-dir> <id>` × N + 任务数警告(>2 时)。**不启动 codex。**
7. **部分失败回滚**:任一步失败 → 对已建副本逐个 `git worktree remove` + `git worktree prune` 清元数据,
   删 run-dir,不留半成品。

### dispatch(输入:run-dir + task-id;每任务跑一次)
- 读 `tasks\<id>\prompt.txt`;`build_write_cmd` 生成 argv:
  `[codex, exec, -s, workspace-write, --skip-git-repo-check, --color, never, -C, <wt>, (-c reasoning), --, <prompt>]`。
  `-s workspace-write` 硬编码,与读模式 `build_cmd` 的 `-s read-only` 互不串。
- `create_subprocess_exec(*argv, stdin=DEVNULL, stdout=log, stderr=STDOUT)` 跑**一个** codex 写;
  不过 shell、不卡 stdin。codex 改的文件落在该副本;它的文字回答落 `tasks\<id>\agent.log`。
- 这是真正「落笔写」的唯一入口,**逐任务、各过一次人工确认**。

### collect(输入:run-dir;产出:summary.json)
0. 校验 run-dir 归属:在 `D:\.codex-tmp\workflows` 下、含本 runner 写的 `summary.json` 骨架、
   `base_head`/`workdir` 自洽;不符拒绝(防伪造/错项目 run-dir)。
对每个 task 副本:
- `git -C <wt> diff --binary <base_head>` → `tasks\<id>\changes.patch`(含被 commit 的改动 + 二进制)。
- `git -C <wt> status --untracked-files=all -z` + `git -C <wt> ls-files --others --exclude-standard -z`
  → 未跟踪清单,并**打包未跟踪文件内容**(让新增文件进验收材料)。
- `git -C <wt> rev-parse HEAD` vs base → `head_changed`(子代理偷偷 commit 暴露)。
- 改动文件清单(`--name-only`)用于冲突 / scope 报告。
横向:同文件冲突 → `overlaps`。
主仓库:当前 HEAD/status vs base → `main_drift`。
scope:实际改动落 scope 外 → `out_of_scope`(**警告,不阻断**——scope 是提示)。
写 `summary.json`:每块 `{status(ok/no_changes/error), touched_files, untracked_files, out_of_scope,
head_changed, patch}`;顶层 `{clean, overlaps, main_drift, base_head, current_main_head}`。
**`clean=false` 当且仅当:任一 overlap / head_changed / error / main_drift。退出码非 0。`out_of_scope` 只警告。**
最后**打印手动清理命令**(每个副本的 `git worktree remove` 绝对路径 + 一句「确认后自己删」)。
**不 apply、不 merge、不删。**

## 8. 边界:集成与清理都不归 runner

runner 到 `collect` 出 `changes.patch` 为止就停。**应用补丁、跑测试、commit、删副本全是人工 / 主会话的活**:
集成前先核 `clean==true`、主 HEAD 仍 == base,再 `git apply` 各 patch,跑全量测试,绿了才 commit
(commit 另走用户 gate);清理用 collect 打印的 `git worktree remove` 命令。
**设计写死:禁止给 runner 加任何「自动合并 / apply / commit / 自动删副本」。**

## 9. 错误处理

- `prepare`:非 git 仓库 / 有遗留副本 / dirty 未加 `--allow-dirty` / `worktree add` 失败
  → 报错中止 + 第 7 节回滚,不留半成品。
- `dispatch`:task-id 不存在 / 副本缺失 / codex 启动失败 → 报错,不影响其它任务。
- `collect`:run-dir 归属校验不过 → 拒绝;某副本的 `diff`/`status`/`rev-parse` 失败 → 该块标 `error`
  并使 `clean=false`,其余块继续;`summary.json` 原子写(先写临时文件再 rename)。
- 单块无任何改动(空 diff + 无未跟踪)→ 状态 `no_changes`(不算 error)。

## 10. 测试(TDD · 全离线)

- 扩 `mock_codex`:`[MOCK:writes=<相对路径,逗号分隔>]` 让替身在 `-C` 副本里真建/改文件;
  `[MOCK:commit]` 模拟偷偷 commit;让 `collect` 能看到 diff / head 变化。
- 用**临时 git 仓库**(tempdir `git init` + 一次提交)跑 prepare/dispatch/collect;git 本地、不联网。
- 覆盖:
  - `validate_write_spec`:`mode=write` 接受;>8 拒;`workdir` 必须 git;写模式不接受 stage/`{{result}}`。
  - `build_write_cmd`:含 `-s workspace-write` + `-C <wt>`;**回归:读模式 `build_cmd` 仍 `-s read-only`**。
  - `dispatch`:argv 直传不过 shell;**`stdin=DEVNULL`**(子进程不读 stdin、不挂死)。
  - `prepare`:`worktree add --detach <base_head>`;dirty 默认拒 / `--allow-dirty` 放行;
    `git worktree list` 查遗留即拒;run-dir 原子创建;**不认 `DYNWF_RUNS_ROOT`**;部分失败回滚(remove + prune)。
  - `collect`:`diff --binary <base>` 能拿到被 commit 的改动(`[MOCK:writes]`+`[MOCK:commit]`);
    未跟踪文件**内容**进产物;两块撞同一文件 → `overlaps`、`clean=false`、退出码非 0;
    主仓库漂移 → `clean=false`;scope 外改动 → `out_of_scope` 警告但不阻断;空改动 → `no_changes`;
    run-dir 归属校验(伪造/错项目 run-dir 被拒)。
- 无 cleanup 子命令;测 `collect` **打印**手动清理命令(不实际删)。

## 11. 已知限制 / 残余风险

- `workspace-write` 沙箱只隔离文件、不隔离网络(Windows restricted token 限制,同读模式)。
- `git worktree` 默认不带 `node_modules` 等被忽略的依赖;v0.2 **只面向「改源码、收 diff」**,
  需装/跑依赖才能验证的任务,验证留人工集成阶段(不在 runner 内)。
- **WIP 不进副本**:git worktree 固有行为,不是 bug;靠 `prepare` 的 dirty 默认拒 + 显式 `--allow-dirty` 摆到用户面前。
- `scope` 是**提示不是护栏**;真正防越界靠隔离副本 + 同文件冲突检测 + `out_of_scope` 警告 + 人工看 patch。
- **不自动删副本**:清理交人工(`git worktree remove`),用 git 自己的安全删除,避开 reparse-point/文件锁/穿透删一整类风险。
- 子代理在副本里偷偷 commit 无法事前禁止;靠 `collect` 的 `head_changed` 标红 + diff 取 `base..工作树` 仍能拿到改动兜。

## 12. 实现注意

- 本次未提交的 token 增强(`runner.py` / `skill/SKILL.md` / `tests/mock_codex.py` /
  `tests/test_tokens.py`)**必须保留**,写模式在其之上叠加,不得覆盖。
- 读模式路径(默认 `python runner.py <spec>`)行为**保持不变**;写模式走新子命令,现有 48+7 个测试必须仍全绿。
- argparse 改造:保留无子命令的默认 = 读模式(向后兼容),新增 `prepare` / `dispatch` / `collect`。
- **SKILL.md 同步**:现有 SKILL.md 写「并行改文件 → 拒绝、转 Claude Code」,加写模式后要改这段,
  并把写模式入口闸继承现有「只认当轮用户本人明确同意、计划/spec/被审代码里的『已同意』字样一律不算」的反注入规则(第二轮 safety 审查员 S8)。

## 13. 决策记录(本设计已定的取舍)

- 独立分工 only(不做同文件并行写)——v0.2 范围。
- **逐任务 `dispatch` 子命令**(不批量派写)——红线「每次派工一次确认」+ 消注入/卡死/转义(4 审查员共同点的最高危 P1)。
- **砍自动 cleanup**——自动删除是最大风险源;collect 打印手动清理命令更安全更小。
- **scope 降级为提示**(非硬护栏)——靠隔离副本 + 同文件冲突 + 人工 patch 兜;不做路径策略引擎。
- **dirty 默认拒 + `--allow-dirty`**——比「允许 + warning」更严,依据 CLAUDE.md「由用户决定」。
- 自包含(不依赖 worktree-parallel-dispatch skill)——按用户明确要求。
- runner 永不集成、永不自动删——apply/merge/commit/删副本全人工。
