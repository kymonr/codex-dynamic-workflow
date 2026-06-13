# codex-dynamic-workflow

给 codex 桌面版的 `dynamic-workflow` 技能：把大任务拆成多个只读 `codex exec` 子代理并行执行，
由 `src/runner.py` 确定性调度，结果汇总在运行目录的 `summary.json`。

- 计划书：`docs/plans/2026-06-13-dynamic-workflow-skill.md`
- 运行产物目录：`D:\.codex-tmp\workflows\`
- 安装位置：`C:\Users\Orz\.codex\skills\dynamic-workflow\`
- v0.1 范围：只读子代理。并行改文件不在本技能内（走 Claude Code 方案二）。

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

## 测试

```
python -m unittest discover -s tests -v
```
