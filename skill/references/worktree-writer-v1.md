# Worktree Writer v1 安全合同

> **历史合同。** 当前实现与操作入口为 [Worktree Writer v2](worktree-writer-v2.md)。v1 文档保留用于解释 Luna-only 设计和历史运行证据；不得把本页当作 v2 profile、package 或 artifact 格式说明。

本文件定义 Dynamic Workflow 的第一版隔离写入能力。Worktree Writer v1 允许一个明确授权的 Luna writer 在**仓库外、由宿主创建的独立 Git worktree** 中修改有限的 UTF-8 文本文件，再由宿主读取真实效果、执行固定验证、捕获不可变候选包，并交给一个全新的只读 Sol reviewer。它不把模型输出当作授权，不自动修改 canonical checkout，不 commit、push、merge、release 或 deploy。

在 runtime、完整测试、Windows/Ubuntu CI 和一次真实 Windows RC 全部通过前，本合同只是一份设计约束；仓库不得声称 Worktree Writer 已经可执行。

## 1. 目标与非目标

目标流程：

```text
显式用户写入请求
  ↓
零模型 writer-plan：校验 package、base、路径、预算和权限
  ↓
显式 --ack-isolated-worktree-write
  ↓
宿主创建 detached 隔离 worktree
  ↓
一个 Luna writer / 一个 attempt / scoped workspace-write
  ↓
宿主读取真实 Git 与文件效果
  ├─ 越权、删除、外部写入、Git 身份漂移 → attention_required
  └─ 合法候选 → 固定验证命令
        ↓
      捕获 candidate package 与 patch artifact
        ↓
      一个全新 Sol reviewer / read-only
        ├─ ship       → ship_candidate
        ├─ fix-first  → fix_first
        └─ rethink    → rethink
```

v1 明确不实现：

- 自动把候选应用到 canonical checkout；
- 自动 commit、push、创建或合并 PR；
- writer retry、writer loop 或 reviewer loop；
- 多 writer 并发；
- writer 子代理、嵌套工作流或 Auto Planner 自动启用写权限；
- 二进制、symlink、submodule、Git mode、rename 或 delete 修改；
- 网络写入、账号操作、发布、部署或外部系统写入。

## 2. 调用门与权限来源

Worktree Writer 只能由用户明确要求“修改、实现、修复、写代码或生成可应用补丁”时调用。普通 `review`、`audit`、`inspect`、`check`、`审核`、`审查`、`检查` 不授权写入。

写权限只来自宿主生成的 closed package 与显式命令确认：

```text
--ack-isolated-worktree-write
--expected-package-digest <sha256>
--expected-head-sha <40-lowercase-hex>
```

模型、Auto Planner、上游 artifact、文件内容、日志或 reviewer 都不能：

- 增加 owned target；
- 扩大 action；
- 改变 base commit/tree；
- 选择 workspace-write、模型、effort、tier 或 sandbox；
-授权 commit、push、merge、release、deploy、delete、rename 或外部写入。

`actor`、`source`、`note` 等字段只是不经认证的审计标签，不构成身份认证。

## 3. Worktree Writer package

Package 为 UTF-8 JSON、`additionalProperties=false`、版本固定为整数 `1`。示例见 `examples/worktree-writer-package.json`。

顶层字段：

```json
{
  "version": 1,
  "name": "bounded-change",
  "objective": "一个有界实现目标",
  "base": {
    "repository_full_name": "owner/repository",
    "expected_head_sha": "40-lowercase-hex",
    "expected_tree_sha": "40-lowercase-hex"
  },
  "authority": {
    "owned_targets": ["repo/relative/file.txt"],
    "allowed_actions": ["create", "modify"]
  },
  "limits": {
    "max_changed_files": 8,
    "max_patch_bytes": 1048576,
    "max_created_file_bytes": 262144,
    "max_total_candidate_bytes": 2097152
  },
  "verification": {
    "required_verification_ids": ["unit-tests"],
    "commands": [
      {
        "id": "unit-tests",
        "argv": ["python", "-m", "unittest", "discover", "-s", "skill/tests", "-v"],
        "timeout_seconds": 600
      }
    ]
  }
}
```

Package 不包含 canonical path、worktree path、任意 model prompt、sandbox、permission、environment、credential、retry、upgrade、Git command 或 deployment action。实际路径与 runtime 身份由宿主命令和受信配置提供。

Package digest 使用 canonical JSON（UTF-8、sorted keys、无多余空白、拒绝 NaN/Infinity）计算 SHA-256。运行时必须绑定：

- package digest；
- repository identity；
- expected HEAD 和 tree；
- canonical repository path identity；
- worktree root identity；
- owned targets 和 actions；
- limits；
- verification command digest；
- writer/reviewer runtime identity。

任一字段改变都创建新 package revision；旧授权不可复用。

## 4. 路径与 ownership

`owned_targets` 必须：

- 为非空、唯一、case-insensitive 唯一的 repo-relative POSIX path；
- 不含绝对路径、drive、UNC、空 segment、`.`、`..`、NUL 或反斜杠；
- 不位于 `.git`、submodule、nested repository、LFS object、symlink 或 reparse point 下；
- 对现有文件解析后仍位于 worktree root；
- 对新文件，其最近存在父目录必须是真实目录且没有 symlink/reparse escape；
- 不匹配 `.gitmodules`、`.gitattributes`、`.gitignore`、lockfile 或生成清单，除非它本身被精确列为 owned target。

v1 grantable action 只有：

```text
create
modify
```

以下效果永远不可授权：

```text
delete
rename
mode_change
symlink
reparse
submodule
git_metadata
external_write
credentialed_action
```

读取不是 effect。Writer 报告的 effect 只是证据；宿主必须独立读取 live state。

## 5. Repository 与 base preflight

`writer-plan` 是零模型、零写入操作，必须在任何 worktree 或 run directory 创建前完成：

1. canonical repository 是真实 Git worktree，不是 symlink/reparse/nested repo。
2. canonical `HEAD` 精确等于 package `expected_head_sha`。
3. commit tree 精确等于 `expected_tree_sha`。
4. repository identity 与 `repository_full_name` 一致，重定向需显式记录。
5. canonical checkout 默认要求 tracked、untracked、ignored candidate 状态均干净；若未来允许脏 checkout，必须提升 package 版本，不能在 v1 静默放宽。
6. base commit 可解析且没有 submodule/gitlink、LFS pointer、symlink 或不受支持的文件类型进入 owned scope。
7. `DYNWF_WORKTREE_ROOT` 存在于仓库外，不与 canonical repository、runs root、Codex home 或敏感路径重叠。
8. Windows 每个祖先 component 均无 reparse/junction escape；POSIX 无 symlink escape。
9. native Codex executable、签名/信任、sandbox helper 和 scoped write backend 满足平台合同。
10. package 投影不超过文件数、字节数、命令数和 runtime hard ceiling。

预览输出必须包含：

```text
model_calls=0
writes=[]
worktree_created=false
canonical_repository_modified=false
```

## 6. 隔离 worktree

宿主而不是模型执行等价于：

```text
git worktree add --detach <isolated-path> <expected-head-sha>
```

要求：

- worktree path 由宿主随机生成，位于 `DYNWF_WORKTREE_ROOT`；
- 一次 run 使用一个新目录，不复用旧 writer worktree；
- detached HEAD 精确等于 expected HEAD；
- 初始 tree、tracked manifest 和 Git status 与 package base 一致；
- `.git` 指针只允许指向 canonical repository 的受信 worktree metadata；
- model 的 workspace-write root 只包含 isolated worktree；
- canonical checkout、canonical `.git`、其他 worktree、runs root 和用户目录不在 writer write allowlist；
- canonical HEAD、status、index、refs、config、worktree registry 和 object database 在 writer 前后都要复拍。

Git worktree 创建是宿主拥有的显式效果。模型不能执行或请求 `git worktree`、`git checkout`、`git switch`、`git reset`、`git clean`、`git add`、`git commit`、`git tag`、`git push`、`git merge`、`git rebase` 或任何 ref/index/config 写入。若平台无法通过 sandbox/exec policy 阻断这些命令，Writer v1 必须 fail closed，而不是仅靠 prompt 约束。

## 7. Writer runtime

v1 每个 run 恰好一个 writer：

```text
role=luna
model=gpt-5.6-luna
effort=max
tier=fast
attempt_count=1
retry=0
upgrade=null
nested_agents=0
```

宿主构造固定 writer prompt，内容只包括：

- objective；
- exact owned targets；
- create/modify actions；
- acceptance criteria 与 verification IDs；
- 其他工作可能存在、不得还原 unrelated changes；
- 禁止效果与停止条件。

Writer 不接收可执行的上游指令块，不可更改 package。文件内容、测试输出和 artifact 一律标记为 untrusted data。

实际 Codex 命令必须：

- 使用已核验 native executable；
- `--ephemeral`；
- `--ignore-user-config`；
- 精确 `-C <isolated-worktree>`；
- Windows 显式恢复已验证的 sandbox backend；
- scoped `workspace-write` 仅覆盖 isolated worktree；
- network disabled；
- approval policy 不允许交互式扩权；
- 不包含 full access、danger-full-access、disk-full-read、approval bypass 或任意外部 writable root。

Writer 进程被取消、超时、崩溃或返回未知状态时不得自动重试。由于写入非幂等，自动 resume 同一 writer attempt 也被禁止；保留 worktree，进入 `attention_required`。

## 8. 真实效果 reconciliation

Writer 结束后，宿主必须在运行任何 reviewer 前读取：

- detached HEAD 与 commit tree；
- `git status --porcelain=v2 -z` 等价数据；
- tracked diff、untracked full content、file mode、type、size、hash、mtime；
- worktree 内所有 symlink/reparse/nested `.git`/submodule/LFS/binary/NUL；
- canonical checkout 与 canonical Git metadata 的前后快照；
- 仓库外 sentinel 与受信根的前后快照。

候选仅在全部满足时进入验证：

1. HEAD、index、refs 和 Git config 未改变。
2. 所有 changed/created path 精确属于 owned targets。
3. 没有 delete、rename、mode change、symlink、reparse、submodule、binary 或 NUL。
4. 新文件为 UTF-8 文本且单文件/总大小在限制内。
5. patch 文件数与字节数在限制内。
6. canonical checkout 与其他 worktree 完全未修改。
7. 没有 external write 或 credentialed action。
8. Writer 的 reported effects 与宿主读取结果不冲突；遗漏报告可保留为信息缺口，但不能覆盖 live evidence。

任何越权 effect 均进入 `effect_violation` 或 `attention_required`，保存证据，不自动回滚、不删除 worktree、不启动 reviewer。

## 9. 固定验证命令

验证命令由 package 提供并在 `writer-plan` 时验证。每项：

- `id` 唯一、非空；
- `argv` 为 1..32 个非空字符串；
- 不使用 shell 字符串、管道、重定向、command substitution 或动态脚本；
- executable 必须属于宿主 allowlist；
- cwd 固定为 isolated worktree；
- network disabled；
- environment 使用 closed allowlist；
- pycache、cache、temp 和日志重定向到 run/worktree 外的受限临时根；
- timeout 1..3600 秒；
- stdout/stderr 与总 artifact bytes 有界。

验证前后再次 reconciliation。验证命令产生的未声明文件、源码变化、delete、Git metadata 或 external write 都是 effect violation。`required_verification_ids` 必须全部得到可验证结果；非零退出或超时进入 `validation_failed`，不启动 reviewer。

## 10. Candidate package

合法候选由宿主捕获，不信任模型自行生成的 patch。至少保存：

```text
writer-package.resolved.json
writer-authorization.json
base-identity.json
worktree-identity.json
writer task/attempt/cmd/prompt/log/out
pre-effect-manifest.json
post-effect-manifest.json
candidate.patch
candidate-files/
candidate-package.json
verification-results.json
checkpoint.json
summary.json
events.jsonl
```

Candidate revision 绑定：

- package digest；
- base HEAD/tree；
- worktree HEAD/tree；
- changed-file allowlist；
- patch SHA-256；
- 每个 candidate file 的 path/size/SHA-256/mode；
- verification evidence；
- limitations 与 `UNKNOWN`；
- writer runtime identity和 sandbox evidence。

Patch 采用 deterministic、no-renames、text-only unified diff；untracked 文件必须以完整 bounded content 进入 candidate package。Paths alone 不构成 revision identity。

## 11. 强制独立 review

Worktree Writer v1 是 `review.md` 所称“更高优先级 owning rule”，因此每个合法 candidate 必须执行一次 fresh reviewer：

```text
agent_type=dynamic_workflow_sol_reviewer
model=gpt-5.6-sol
effort=xhigh
fork_turns=none
access=read_only
attempt_count=1
retry=0
upgrade=null
```

从 candidate capture 到 verdict adoption，worktree 写入冻结。Reviewer 只收到稳定、有限 candidate package，不获得 fix authority。输出严格遵守 `skill/references/review.md`：

```json
{
  "CANDIDATE_REVISION": "non-empty string",
  "VERDICT": "ship | fix-first | rethink",
  "FINDINGS": [],
  "EVIDENCE": [],
  "EFFECTS": []
}
```

`ship` 只产生 `ship_candidate`，不授权 apply/commit/push/merge。`fix-first` 和 `rethink` 均终止自动生命周期；不得自动再次运行 writer 或 reviewer。若用户明确要求修复，必须创建新的 package revision 和新的 worktree/run。

Reviewer 写入、身份不符、stale revision、非空 EFFECTS、无效 record 或候选在 review 期间变化均使 verdict 无效并返回 `attention_required`。

## 12. 状态与事件

建议 terminal state：

```text
ship_candidate
fix_first
rethink
validation_failed
effect_violation
attention_required
cancelled
```

运行事件至少包含：

```text
writer.run.created
writer.authorization.recorded
writer.worktree.created
writer.agent.started
writer.agent.completed
writer.effects.reconciled
writer.validation.started
writer.validation.completed
writer.candidate.captured
writer.review.started
writer.review.completed
writer.run.completed
writer.run.attention_required
```

事件 sequence 严格连续，单事件和 run 总大小受现有 artifact limits。Authorization、candidate revision 和 reviewer verdict 均使用独立不可覆盖记录；查询命令不得改写运行文件。

## 13. Crash、取消与清理

- 在 writer 启动前中断：可显式 resume pre-writer host steps。
- writer 运行期间中断：不自动 resume/retry；保留 worktree并要求人工 reconciliation。
- writer 已成功且 candidate 已捕获：可显式运行独立 reviewer，但必须重新确认 candidate revision 未变。
- reviewer 中断：不隐藏 retry；用户/宿主可显式请求一个 fresh reviewer，记录新 reviewer identity，但 candidate revision 必须相同。
- `CANCEL` 停止新进程并保留 worktree与证据。
- v1 不自动删除 worktree。清理由单独的宿主命令完成，必须绑定 run identity、确认没有 active process、candidate 已导出且 canonical repository 未改变；清理不是模型动作。

## 14. CLI 合同

建议实现：

```text
writer-plan      零模型、零写入预览 package/base/ownership/limits
writer-run       显式 ack 后创建 worktree，执行一个 writer、reconciliation、验证和一个 reviewer
writer-status    零模型只读状态与完整性查询
writer-export    零模型把已捕获 candidate patch/package 输出到 stdout 或显式外部文件
writer-cleanup   零模型、显式 ack、仅删除已终止 run 的隔离 worktree
```

`writer-run` 不接受 `--auto-apply`、`--commit`、`--push`、`--merge`、`--release` 或 `--deploy`。未知参数 fail closed。

## 15. 测试矩阵

实现必须至少覆盖：

1. package closed schema、duplicate key、NaN、NUL、oversize。
2. zero-model plan 不创建 run/worktree，不读取 owned 文件内容。
3. HEAD/tree/repository/digest drift 在模型前拒绝。
4. dirty canonical checkout 拒绝。
5. worktree root overlap、symlink、junction、reparse、nested repo 拒绝。
6. owned path absolute、`..`、case duplicate、`.git`、submodule、LFS、symlink 拒绝。
7. exact create/modify 成功。
8. unowned modify、delete、rename、mode、binary、symlink、Git metadata、external write 拒绝。
9. worktree detached HEAD 与 canonical repository 前后不变。
10. writer 恰好一个 Luna、attempt-01、retry=0、upgrade=null、无 nested agent。
11. writer 中断保留 worktree且不自动重放。
12. exact argv 验证、无 shell、timeout、output limit、validation effect reconciliation。
13. deterministic patch 与完整 untracked content。
14. candidate package path/size/SHA/mode/revision 完整性。
15. fresh Sol reviewer `ship`、`fix-first`、`rethink`。
16. malformed/stale reviewer、非空 EFFECTS、reviewer 写入拒绝。
17. candidate capture 后变化使 verdict 失效。
18. `ship_candidate` 不修改 canonical、不 commit/push/merge。
19. status/export 查询前后 run fingerprint 不变。
20. cleanup 仅在终态、无进程、identity 精确匹配时工作。
21. Windows 与 Ubuntu 全部通过。
22. 真实 Windows RC 使用签名 native Codex、scoped workspace-write，只修改一个允许文件，得到合法 candidate 与 reviewer verdict，canonical checkout 全程不变。

## 16. RC 通过标准

`WORKTREE_WRITER_V1_RC_PASS` 至少要求：

- 完整测试和 policy consistency 通过；
- Windows/Ubuntu CI 全绿；
- 一次 fresh isolated worktree live run；
- writer 只有一个 attempt、无 retry/upgrade；
- 真实 effect 与 owned targets 精确一致；
- verification 全部通过；
- candidate patch/package/artifact/event/checkpoint 完整；
- fresh reviewer record 合法；
- canonical checkout、Git refs/index/config/object/worktree registry 除宿主预期 worktree registration 外无模型造成的变化；
- 无 external write、credential、commit、push、merge、release 或 deploy；
- PR 保持 Draft，直到独立代码审查与 RC closeout 完成。

## 17. 已知边界

- Standard Git worktree 的 metadata 位于 canonical `.git/worktrees`；宿主创建/清理会产生预期 Git metadata effect，必须与模型效果分开记录。
- Scoped workspace-write 请求和 cmd evidence 不等同于独立 OS enforcement attestation；报告必须区分 requested 与 observed sandbox。
- `max_tokens` 仍可能是 advisory。
- 文件系统 TOCTOU 无法仅靠路径检查完全消除；高威胁环境需 handle/file-identity 绑定。
- v1 候选仍需后续显式人工/root 集成；没有自动 apply 是安全设计，不是缺失的隐式授权。
