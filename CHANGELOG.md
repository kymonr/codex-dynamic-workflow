# Changelog

## 2.0.2 - 2026-09-05

- Apply identical ownership checks to canonical Skill, legacy alias and all profiles; reject edited, deleted or unowned targets before writes.
- Add explicit per-manifest-file PATH=SHA256 adoption, checked against inspected preimages and recorded in reversible receipts. No generic force overwrite.
- Define mandatory reservations including the current request only with consumes_mandatory=true; preserve remaining total, approved and strong capacity for every admission.
- Replace substring metadata checks with a closed YAML mapping parser, exact field/type/version/policy checks, and duplicate JSON-key rejection.
- Add ownership/collision/adoption, reservation-boundary/invariant, and metadata mutation regression tests.
- Keep native raw-source workflows, model profiles, permissions, canonical invocation and explicit-only legacy alias unchanged.

## 2.0.1 - 2026-09-05

- Canonical Skill renamed from `dispatching-native-agents` to `codex-dynamic-workflow`.
- Canonical invocation is now `$codex-dynamic-workflow`; implicit invocation remains enabled only there.
- `$dispatching-native-agents` remains as an explicit-only deprecated compatibility alias.
- Installer and validator now manage both canonical and compatibility directories during migration.
- Core v2 evidence, routing, budget, write, and quality contracts are unchanged.

## 2.0.0 — 2026-09-05

保留：原生工具派工、Fan-out/Pipeline/Loop/Segments、候选身份、授权边界、明确未覆盖项。
新增：raw-source-first、基于新证据动态追加分支、职责与模型 profile 解耦、强核验质量门、
增量 claim/证据版本、累计低成本预授权余量、Root/子代理成本未知项、完整实现闭环、
独立安装 profile、安装前像/漂移检查、静态测试、参考策略回归与真实原生验收记录。
移除默认：固定反驳人数、多数票决定事实、mandatory Sol gate、所有兄弟结束后统一去重、
硬编码 native 工具参数、固定三波搜索上限，以及只能依赖 Root 摘要包的核验。

行为变化：缺 native 工具时明确报告限制，Root 可做无依赖的已授权工作，但不冒充多代理完成；
旧模型名称不再决定职责；同一条重要结论可随实质反证重新打开，不由模型身份保证正确。

代价：独立读取原始来源可能增加 I/O 与重复 token；需要可访问且一致的候选态；
动态规划依赖 Root 判断；低成本资格尚需真实项目评测；Skill 层不能硬限制实际费用或文件写入。

不包含：完整工作流引擎、自动恢复、后台任务、嵌套派工、自动后端切换、自动发布或 Git 提交。
