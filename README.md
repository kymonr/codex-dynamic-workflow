# Codex Dynamic Workflow v2

原生优先、原始证据优先的 Codex Skill。正式调用名：

```text
$codex-dynamic-workflow
```

旧 `$dispatching-native-agents` 仅保留为显式兼容入口，并关闭隐式调用，避免双重自动路由。

适用：动态调查、深度审核，以及明确授权后的实现、测试、独立 review 与有限修复。
主 Skill 在 `skill/codex-dynamic-workflow/`；模型执行 profile 在 `profiles/`。
旧 `codex-workflow` Python/QuickJS 仓库保持不变，本目录不冒充已完成的 Runtime。

## 本机验证与安装

要求 Python 3.11+；验证和安装脚本只用标准库。下面的 `python` 必须解析到满足版本要求的解释器。

```text
python -B -m unittest discover -s tests -v
python -B scripts/validate_package.py
python -B scripts/install.py --codex-home <经现场确认的CODEX_HOME>
python -B scripts/install.py --codex-home <经现场确认的CODEX_HOME> --apply
```

安装默认 dry-run。`--apply` 只更新本包拥有的 Skill 文件和三个新 cwf_* profile；
不改 config.toml、审批、沙箱默认值、旧角色或 Git。安装前检查目标、保存精确前像，
对被替换的内容做漂移检查，完成后逐文件验证。前像不放在 Skill 扫描目录内。
不同客户端的 discovery 路径可能不同：此安装器面向现场已有的 CODEX_HOME/skills
布局；无此已确认布局时先验证 discovery，不能复制到多个位置制造同名 Skill。

角色说明：cwf_reader 为 Astra/high 只读；cwf_writer 为 Astra/high、继承权限；
cwf_mechanical 为 Luna/medium、机械只读。职责与这些 profile 分离；模型名称
是初始配置，不是用户账户可用性、价格或质量的保证。原有角色不覆盖。

## 2.0.2 ownership 与元数据校验

所有 canonical、legacy 和 profile 文件统一核对 `.delivery/install-state.json`。
已拥有文件与记录不一致（包括被删除）时停止；同名现有文件没有 ownership 时也停止，
即使其内容恰好等于发布包也不会隐式接管。正常升级不需要额外授权参数。

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

完整设计见 `DESIGN.md`；本次 review、安装与验收见 `reports/`；
变更对照见 [CHANGELOG.md](CHANGELOG.md)。源目录与安装目录是独立副本。

## Windows 原位更新例外

本机若原子重命名替换被 Windows 拒绝、但同一账号的普通文件写入已验证允许，
可显式加 `--in-place-skill`，仅对已存在的 `SKILL.md` 使用普通原位写入。
不自动回退、不改 ACL、不提权、不结束占用文件的其他程序；其余文件仍原子替换。
保存写前意图和精确前像，Windows 下持有字节范围锁，完成后逐字节验证。
该例外不具备进程强杀/断电时的文件级原子性：半写状态记为恢复冲突，必须检查前像，
不会覆盖可能来自其他进程的变化或谎报已恢复。默认模式仍为原子替换。
