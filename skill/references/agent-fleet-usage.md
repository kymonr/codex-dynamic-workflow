# Agent Fleet v1 使用指南

Agent Fleet 是显式或高级只读模式。普通审核不因为出现 `review`、`audit`、`检查` 等词就自动扩展到 4–12 个代理；用户明确要求 fleet、对抗性审核、多个相互质疑的子代理，或任务确实需要 7–12 个角色时才选择。

## 1. 准备 package

复制 `examples/agent-fleet-package.json`，替换：

- `expected_head_sha`；
- `changed_files`；
- objective、acceptance、scope、exclusions；
- risk tags；
- 固定 verification commands；
- agent count 与 preset。

计算 canonical digest：

```powershell
python -c "from skill.fleet_contract import load_package; print(load_package('fleet.json').digest)"
```

Package 只能选择 preset 和 4–12 的规模，不能选择模型、effort、sandbox、retry、写权限或 Sol 条件。

## 2. 零模型预览

```powershell
python skill\cli.py fleet-plan `
  --package fleet.json `
  --repository D:\path\to\repository `
  --expected-package-digest <64-lowercase-hex>
```

预览成功时：

- model calls 为 0；
- writes 为 `[]`；
- 不创建 run directory；
- 校验 exact HEAD、origin、changed files 和 candidate revision；
- 显示 4–12 个不同角色及阶段分配；
- 显示固定 Luna 路由和条件 Sol 路由；
- 记录 Codex capability probe。

如果预览与 package 不一致，先修正 package 或候选，不要运行。

## 3. 运行

```powershell
python skill\cli.py fleet-run `
  --package fleet.json `
  --repository D:\path\to\repository `
  --expected-package-digest <64-lowercase-hex> `
  --ack-read-only-agent-fleet
```

运行顺序：

1. 固定 verification；
2. discovery Luna 并行；
3. challenge Luna 并行；
4. reproduction Luna 并行；
5. 宿主 finding aggregation；
6. 必要时一个 fresh Sol/xhigh arbitration。

代理不能写入候选。每轮后宿主重建 candidate revision；任何变化都会停止运行。

## 4. 终态

| 状态 | 含义 |
|---|---|
| `accepted` | 低风险、无 finding/UNKNOWN/冲突，跳过 Sol |
| `accepted_with_notes` | 只剩 accepted P3，跳过 Sol |
| `ship` | Sol 裁决后可以接受当前候选 |
| `fix_first` | Sol 接受至少一个 P1/P2；先修复再重新运行 |
| `rethink` | Sol 认为设计需要重新考虑 |
| `verification_failed` | 固定验证失败，未启动代理 |
| `attention_required` | identity、revision、effect、record 或证据完整性失败 |

`accepted` 与 `ship` 都不授权写入、apply、commit、push、merge、release 或 deploy。

## 5. 状态与证据校验

```powershell
python skill\cli.py fleet-status --run-dir <fleet-run-directory>
```

`fleet-status` 是零模型、零写入查询。它验证 evidence manifest、package、candidate revision、schedule 和 terminal summary。任何运行文件修改都会使完整性校验失败。

## 6. Preset 选择

```text
adversarial-review      代码候选的多维对抗性审核
competing-hypotheses    多个根因假设并行竞争
architecture-council    多角色架构评议
security-red-blue       红队/蓝队安全审核
test-matrix             多维测试缺口分析
repository-audit        仓库功能面分区审核
research-synthesis      多证据研究与反证综合
```

规模建议：

```text
4   最小多视角检查
6   默认，含 challenge 与 reproduction
8   较宽的跨模块审核
10  高风险深度检查
12  最大 adversarial / council 模式
```

4 个代理只有 discovery。需要完整的发现—质疑—复现链时使用 6 或以上。

## 7. Fail-closed 行为

以下情况不会自动重试或改调 Sol：

- Luna/Sol identity 不匹配；
- output schema 错误或 candidate revision stale；
- 任一代理产生非空 effects；
- 候选在审核期间改变；
- run evidence 被篡改；
- Codex capability 不足或进程失败。

这些属于执行证据无效，必须返回 root。Sol 只处理语义上的 blocker、冲突、UNKNOWN 和高风险裁决。
