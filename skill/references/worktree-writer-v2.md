# Worktree Writer v2 安全与质量合同

Worktree Writer v2 是 Dynamic Workflow 的显式隔离候选生成能力。它只接受 package v2，并固定使用一个 Sol/high Writer；宿主读取真实 Git/文件系统效果、执行固定验证、冻结候选，再启动一个全新的只读 Sol/xhigh reviewer。

```text
显式 package v2 + 精确 base
  ↓
宿主固定 Sol/high Writer
  ↓
真实 effect reconciliation
  ↓
固定非 shell 验证
  ↓
不可变 candidate revision
  ↓
fresh read-only Sol/xhigh review
```

它不自动修改 canonical checkout，不 commit、push、merge、release 或 deploy，也不允许 package、CLI、仓库内容、Writer 或 reviewer 选择或升级模型。

## 1. 目标

- 用更强且稳定的默认写手提高隔离候选质量；
- 删除“小任务 Luna / 复杂任务 Sol”的易错路由判断；
- 用 package v2 的验收、约束、非目标和行为上下文提高任务定义质量；
- 保持单 Writer、单 attempt、无 replay、create/modify-only 和宿主真实效果核对；
- 把精确 Writer 路由和预算绑定到全部可信运行证据。

## 2. 非目标

- 不是通用多代理写入框架；
- 不提供 Writer 模型或 effort 选择参数；
- 不自动修订 reviewer 的 `fix-first`；
- 不把同模型家族的 Writer/reviewer 描述为模型异构审核；
- 不迁移或重写历史 v1 run artifact。
## 3. 固定 Writer binding

可信宿主代码生成唯一 binding：

```json
{
  "writer_binding_version": 1,
  "selection": "fixed-host-route",
  "route": {
    "role": "sol",
    "model": "gpt-5.6-sol",
    "effort": "high",
    "tier": null,
    "sandbox": "workspace-write"
  },
  "package_version": 2,
  "limits": {
    "max_owned_targets": 8,
    "max_changed_files": 8,
    "max_patch_bytes": 524288,
    "max_created_file_bytes": 262144,
    "max_total_candidate_bytes": 2097152
  },
  "requires_quality_context": true
}
```

CLI 不暴露 `--writer-profile`、`--model` 或 `--effort`。Package 中也不存在 route 字段。任何未知或被篡改的 binding 都必须在模型结果采用前 fail closed。

8 个文件是硬上限，不是推荐宽度。普通候选仍应尽量保持 1–4 个主要文件和单一行为目标；超过边界时返回 root 重新拆分。
## 4. Package v2

Package 是任务数据，不是权限扩展。顶层为 closed schema，必须包含：

- `version=2`、`name`、`objective`；
- `acceptance_criteria[]`，至少一项；
- `constraints[]` 与 `non_goals[]`；
- `behavior.before` 与 `behavior.after`；
- `implementation_context.relevant_symbols[]` 与 `analysis_summary`；
- 精确 `base`、`authority`、`limits` 和 `verification`。

质量上下文使用 UTF-8、长度/数量上限和封闭嵌套对象，总 canonical UTF-8 大小最多 128 KiB。它进入 canonical package digest，因此任何验收、约束、行为或上下文变化都会改变 package identity。

质量字段只能帮助 Writer 理解目标。它们不能：

- 添加 owned target 或 allowed action；
- 请求额外 writable root、shell、code mode、网络或 nested agent；
- 授权凭据、外部写入或 Git publication；
- 覆盖宿主验证与真实效果核对。

v2 runtime 拒绝 package v1。历史 v1 artifact 必须由匹配的 v1 release 查询；不得在缺少原始 identity 的情况下升级为 v2。

## 5. 写入权限

Writer 只能对 exact repo-relative POSIX `owned_targets` 执行 `create` 或 `modify`。以下效果始终禁止：delete、rename、mode change、binary/NUL/LFS、symlink/reparse、submodule/gitlink、Git metadata、仓库外写入和凭据动作。
Writer 只有一次 attempt，`retry=0`、无模型 upgrade、无 nested agent。Shell tool、code mode、web search 和 network 都关闭；预期编辑面只有 `apply_patch`。中断或未知效果必须保留隔离 worktree 和证据并返回 `attention_required`。

## 6. 生命周期与证据绑定

`writer-plan` 在零模型、零写入条件下校验 package、digest、base、路径、预算、固定 binding、锁和 Codex capability。

显式 `--ack-isolated-worktree-write` 后，宿主创建 detached worktree 和 exclusive per-repository lock。固定 binding 必须原样进入：

- plan 输出；
- `writer-authorization.json`；
- 外部 lock 与 run 内 lock copy；
- checkpoint 与 summary；
- Writer prompt；
- candidate package；
- candidate revision basis；
- `writer-status` 完整性校验；
- cleanup identity 检查。

Writer 返回的 `reported_effects` 只是 advisory。宿主从 live Git 与文件系统重新生成 effect manifest，并核对 changed path、action、mode、bytes、SHA、patch 和 Git metadata。验证命令必须是 package 中预先声明的固定 argv、`shell=false`，且不能改变候选。

全部必需验证通过后，宿主捕获 patch 和候选文件，再以 canonical JSON 计算 `candidate_revision=sha256:<digest>`。Review 开始后，candidate package、patch、captured files 和 live worktree manifest 都必须保持不变。

## 7. Fresh reviewer

Reviewer 固定为 `gpt-5.6-sol / xhigh / read-only`，使用一个新的进程、空 reviewer workspace、独立 prompt 和只读 authority。它只消费冻结的 candidate package 与 patch，不能修复或扩大权限。
Writer 与 reviewer 属于同一模型家族，但具有进程、上下文、sandbox、authority 和 artifact 独立性。项目只能称其为 fresh independent review，不能称为模型家族异构 review。

Reviewer 终态：

- `ship` → `ship_candidate`；
- `fix-first` → `fix_first`；
- `rethink` → `rethink`。

三种状态都保留候选且不 apply。`fix_first` 不能自动重放 Writer；后续修订必须由 root/用户创建新的 package identity 和新 run。

## 8. 完整性与失败

`writer-status` 必须交叉校验 runtime identity、package v2、固定 binding、authorization、lock、event sequence、Writer/Reviewer 进程身份、effect manifest、验证证据、candidate revision、patch、captured files、canonical checkout 和 live worktree。

以下情况 fail closed：

- package、binding、base、lock 或 revision 不匹配；
- Writer 实际 role/model/effort/sandbox 与固定 route 不符；
- 未授权路径或动作；
- validation 改变候选；
- reviewer 产生任何 workspace effect；
- review record 陈旧、形状错误或 verdict 不一致；
- canonical repository 出现未解释漂移。

运行不会自动 retry、resume 或 cleanup。显式 cleanup 只删除已核对的隔离 worktree 和 lock，保留 run evidence。

## 9. 最低回归覆盖

实现至少验证：package v1 拒绝、quality-context digest、固定 Sol/high route、CLI 无选择面、8 文件与字节预算、prompt 中 untrusted-data 边界、binding 全链路一致性、binding tamper、Writer/Reviewer 身份、真实 effect reconciliation、验证不可变性、candidate revision、status/export/cleanup 和 canonical checkout 不变。
