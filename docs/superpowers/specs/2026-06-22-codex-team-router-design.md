# 设计：Codex Skill + thread tools 的三角色团队路由 MVP

- 日期：2026-06-22
- 状态：已设计，待用户审阅
- 范围：新增一个 Codex Skill 级控制平面，用 Codex app thread 工具管理长期 Agent 团队；不改 `dynamic-workflow` runner，不做 UI，不做本地常驻服务。
- 涉及文件（实现阶段预计）：`skills/codex-team-router/SKILL.md`（新增独立 skill 正文）、`src/team_router/`（可选的本地 ledger/protocol helper）、`tests/`（协议与 ledger 单测）、`README.md`（使用说明）。

---

## 1. 背景与定位

现有 `dynamic-workflow` 解决的是“一次任务内多子代理并行执行”：主会话拆任务，使用 `native-subagent` 或 `cli-runner` 跑一批子任务，最后汇总结果。

本设计要补的是另一层：**长期多会话团队控制平面**。用户在总控会话里发起任务后，Skill 负责找到或创建角色线程，派活，检查回传，验收，写入可追溯 ledger。

第一版只做三角色团队：

- `manager`：把用户目标整理成结构化 `TEAM_ROUTER_PLAN`，决定是否适合派给 executor，给出 scope、stopWhen 和风险边界。
- `executor`：执行具体任务，只按派工边界交付 `TEAM_ROUTER_CALLBACK`。
- `verifier`：验收执行结果，输出结构化 `TEAM_ROUTER_VERDICT`，决定通过、返工或阻塞。

目标不是“创建很多 Agent”，而是让一条任务有可靠闭环：

```text
register roles -> manager plan -> dispatch task -> await callback -> verify verdict -> close out or mark blocked
```

## 2. MVP 成功标准

第一版完成后，用户可以在总控会话里说：

```text
用 codex-team-router 启动三角色团队处理 <任务>
```

系统应能做到：

1. 探测当前 Codex app 是否提供所需 thread 工具；缺工具时直接 `tool_error`，不尝试降级为普通聊天。
2. 读取或创建一个项目作用域内的 `manager`、`executor`、`verifier` 线程。
3. 给每个线程设置可识别标题，并在本地 registry 记录 `threadId`、角色、项目、创建时间、最后观察时间。
4. 为用户任务生成唯一 `taskId`，写入 task ledger。
5. 先向 manager 请求结构化 plan，再按 plan 向 executor 发送标准派工消息。
6. 派工消息必须包含自线程回传 marker、回传格式、停止条件、权限边界和 callback 搜索锚点。
7. 读取线程最近状态，按 message id 或时间锚点查找符合协议的回传；窗口不可覆盖时进入可恢复状态。
8. 将 executor 原始回传交给 verifier 线程验收，读取结构化 verdict。
9. 最终向用户输出一段短 closeout：成功、失败、缺回传、未覆盖范围和下一步。

## 3. 非目标

第一版明确不做：

- 不做独立 CLI、本地服务、Web UI 或 Electron 控制台。
- 不自动修改 `dynamic-workflow` 的 runner 调度逻辑。
- 不让子线程自行创建更多线程。
- 不自动 commit、push、PR、merge、deploy。
- 不假装知道“当前活跃线程”。只使用 thread 工具可读到的 `threadId`、最近状态和最后检查时间。
- 不做无人值守轮询。每次检查由用户或总控会话明确触发。
- 不把 `read-only` 或 `design-only` 当成沙箱证明；它只是派工提示词边界。

## 4. 控制平面组件

### 4.1 Skill 入口

新增 Skill 暂定名：

```text
codex-team-router
```

触发条件：

- 用户明确要求 `团队路由`、`长期 agent 团队`、`manager/executor/verifier`、`跨会话协作`、`thread 工具派工`。
- 用户要求“系统版多 Agent 协同”。

非触发条件：

- 普通一次性并行审查或调研继续使用 `dynamic-workflow`。
- 简单单线任务不使用本 Skill。

### 4.2 Agent Registry

Registry 是本地 JSON 文件，用于记录角色线程。第一版默认使用项目内持久 runtime 目录：

```text
<projectRoot>\.codex-team-router\registry.json
```

该目录是长期状态源，不得放在 `D:\.codex-tmp`。实现阶段必须确保 `.codex-team-router/` 不被误提交：初始化时先检查 `<projectRoot>\.gitignore`，缺少该条目时要求用户确认后追加；如果目标项目不可写，先要求用户指定一个 `D:\codex\...` 下的持久状态目录。

记录结构：

```json
{
  "version": 1,
  "projects": {
    "<codexProjectId>": {
      "projectId": "<codexProjectId>",
      "projectName": "codex-dynamic-workflow",
      "localPathHash": "<hash-of-project-root>",
      "target": {"type": "project", "environment": {"type": "local"}},
      "hostId": "local",
      "roles": {
        "manager": {
          "threadId": "<threadId>",
          "title": "TeamRouter manager - <project>",
          "status": "active",
          "createdAt": "2026-06-22T00:00:00+08:00",
          "lastObservedAt": "2026-06-22T00:00:00+08:00"
        }
      }
    }
  }
}
```

Registry 主键必须是 `list_projects` 返回的 Codex `projectId`。本地路径 hash 只能做 metadata，不能作为主 key；否则同一 repo 的多个 worktree 会创建多份 registry 和多组角色线程。

Registry 还必须保存创建线程所需的 `target.environment` 和可选 `hostId`。这些字段用于重建线程前的候选输入，但每次创建前仍要重新调用 `list_projects` 确认当前 target，不能把旧 registry 当成唯一真相。

### 4.3 Task Ledger

Ledger 是任务级事实表。建议路径：

```text
<projectRoot>\.codex-team-router\tasks\<taskId>.json
```

状态机分为主干、返工回边和终止态：

```text
main: created -> roles_ready -> planning -> planned -> dispatched -> awaiting_callback -> verifying -> done
rework: verifying -> needs_rework -> dispatched
terminal: blocked | malformed_callback | tool_error | missing_role | callback_unreachable | abandoned
```

`needs_rework` 不是终态；用户确认返工后追加一条 dispatch 记录并回到 `dispatched`。默认最多返工 3 次，超过后转 `blocked`。

任务记录最小结构：

```json
{
  "version": 1,
  "taskId": "ctr-20260622-001",
  "projectId": "<codexProjectId>",
  "projectLocalPath": "D:\\codex\\codex-dynamic-workflow",
  "objective": "<用户原始目标>",
  "status": "awaiting_callback",
  "reworkCount": 0,
  "maxRework": 3,
  "dispatches": [
    {
      "role": "executor",
      "threadId": "<threadId>",
      "messageId": "<send_message_result_id_or_null>",
      "sentAt": "2026-06-22T00:00:00+08:00",
      "searchAnchor": {"messageId": "<messageId_or_null>", "sentAt": "2026-06-22T00:00:00+08:00"},
      "expectedCallback": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-001",
      "attempt": 1
    }
  ],
  "observations": [],
  "verification": null,
  "closeout": null
}
```

`messageId` 必须保存 `send_message_to_thread` 的返回 id；如果工具不返回 id，明确存 `null`，并用 `sentAt` 作为弱锚点。弱锚点只能降低误判，不能证明 callback 覆盖完整历史。

## 5. 消息协议

所有跨线程消息必须带机器可识别的头部，避免自然语言回传漏掉关键字段。总控只消费含正确 marker 和当前 `taskId` 的最后一条有效回传。

### 5.1 Manager plan

```text
TEAM_ROUTER_PLAN_REQUEST
 taskId: <taskId>
 objective: <用户目标>
 permission: read-only | design-only

请在本线程输出：
TEAM_ROUTER_PLAN taskId=<taskId>
status: planned | blocked
scope: <明确路径或业务范围>
stopWhen: <完成条件或阻塞条件>
riskBoundary: <权限、数据、外部系统边界>
executorPrompt: <给 executor 的具体任务>
notes: <其他注意事项；无则写 none>
```

总控必须等待并解析 `TEAM_ROUTER_PLAN`。如果 manager 返回 `blocked` 或没有结构化 plan，不得直接派给 executor；状态转 `blocked` 或 `malformed_callback`。

### 5.2 Executor dispatch 与 callback

```text
TEAM_ROUTER_DISPATCH
 taskId: <taskId>
 role: executor
 callbackMode: self-thread-marker
 callbackMarker: TEAM_ROUTER_CALLBACK taskId=<taskId>
 permission: read-only | design-only
 scope: <来自 manager plan 的 scope>
 stopWhen: <来自 manager plan 的 stopWhen>
 searchAnchor: <messageId 或 sentAt，由总控记录>

目标：
<manager plan 的 executorPrompt>

交付格式：
请在本线程完成时发送一条包含以下字段的最终回传。不要尝试给其他线程发消息；总控会读取本线程并按 marker 收取结果：
TEAM_ROUTER_CALLBACK taskId=<taskId>
status: done | blocked
final: true
summary: <3-7 行>
evidence: <文件/命令/线程观察>
risks: <未覆盖或失败；无则写 none>
next: <建议下一步；无则写 none>
```

总控只把 `TEAM_ROUTER_CALLBACK taskId=<taskId>` 且 `final: true` 的内容视为 executor 最终回传。若窗口内出现多条匹配，取最后一条。

### 5.3 Verifier dispatch 与 verdict

```text
TEAM_ROUTER_VERIFY
 taskId: <taskId>
 callbackMarker: TEAM_ROUTER_VERDICT taskId=<taskId>
 permission: read-only | design-only
 scope: <同 executor scope>

以下是 executor 原始回传，总控未改写：
<verbatim TEAM_ROUTER_CALLBACK block>

请验收并只输出：
TEAM_ROUTER_VERDICT taskId=<taskId>
result: pass | needs_rework | blocked
summary: <3-7 行验收结论>
requiredChanges: <返工要求；无则写 none>
evidenceChecked: <你检查过的证据；无则写 none>
risks: <仍未覆盖的风险；无则写 none>
```

总控只把 `TEAM_ROUTER_VERDICT taskId=<taskId>` 视为 verifier verdict。`result: pass` 才能进入 `done`；`needs_rework` 必须等待用户确认后再派返工；自然语言“看起来可以”不得触发状态迁移。

第一版采用**自线程 marker 回传**模型：manager、executor、verifier 都只在自己的线程回复，主会话负责用 `read_thread` 拉取结果。不要要求子线程主动调用 `send_message_to_thread` 给 manager 回传；这会把工具权限和回传责任扩散到子线程，MVP 不做。

## 6. Thread 工具适配

当前 Codex app 已暴露以下能力，第一版只依赖这些工具：

- `list_projects`：查项目，创建项目线程前使用。
- `create_thread`：创建角色线程。只在用户明确要求系统版或角色缺失时使用；创建前必须通过 `list_projects` 取得 `projectId` 和 target。
- `list_threads`：按标题/关键词查已有角色线程。
- `read_thread`：读取近期状态和 turn summaries。
- `send_message_to_thread`：派工、验收、返工。
- `set_thread_title`：确保角色线程标题可识别。
- `set_thread_pinned`：可选，把 manager 线程 pin 住。
- `set_thread_archived`：只在用户明确要求清理时使用。

启动 Skill 时先做 capability probe：工具列表缺少 `list_projects`、`create_thread`、`read_thread` 或 `send_message_to_thread` 时，直接输出 `tool_error`。这个 Skill 只面向 Codex app thread tools 环境；在 Claude Code 或普通 CLI 中不能假装可用。

第一版不使用 `handoff_thread`，除非用户明确要求移动线程工作区。若用户触发 handoff，下一次运行必须重新 `list_projects`/`list_threads` 刷新 target、hostId 和 threadId，不能直接复用旧 registry。

## 7. 工作流

### 7.1 初始化团队

1. capability probe：确认所需 thread 工具存在。
2. 用 `list_projects` 识别项目作用域，得到 `projectId` 和 target。
3. 读取 registry；registry 主 key 必须匹配 `projectId`。
4. 检查 `.codex-team-router/` 是否被 `.gitignore` 排除；缺少时要求用户确认后追加，或要求用户指定外部持久目录。
5. 对每个角色：
   - registry 有 `threadId`：用 `read_thread` 验证能读。
   - registry 缺失或读失败：用 `list_threads` 搜索标题；多个匹配时不自动绑定，输出候选让用户确认。
   - 仍无可用线程：用 `create_thread` 创建。
6. 更新 registry。
7. 输出角色清单和未解决问题。

### 7.2 规划与派发任务

1. 生成 `taskId`。
2. 写 task ledger，状态 `created`。
3. 确认三角色线程可读，ledger 状态变为 `roles_ready`。
4. 向 manager 线程发送 `TEAM_ROUTER_PLAN_REQUEST`，记录 `messageId` 和 `sentAt`，状态变为 `planning`。
5. 用 `read_thread` 读取 manager 线程，解析最后一条有效 `TEAM_ROUTER_PLAN`。
6. manager `status: planned` 后，ledger 状态变为 `planned`；否则转 `blocked` 或 `malformed_callback`。
7. 向 executor 线程发送 `TEAM_ROUTER_DISPATCH`，记录 `messageId`、`sentAt`、`searchAnchor` 和 attempt，ledger 状态变为 `dispatched`。
8. 如果 `send_message_to_thread` 明确返回错误，转 `tool_error`；否则状态变为 `awaiting_callback`。`awaiting_callback` 只表示“已发出并等待回传”，不证明 executor 已实际处理。

### 7.3 检查回传

1. 用 `read_thread` 读取 executor 最近 turn。
2. 只搜索 dispatch `messageId` 之后的内容；如果没有 `messageId`，搜索 `sentAt` 之后的内容；如果工具只返回最近摘要，则把这一步标记为弱匹配。
3. 搜索 `TEAM_ROUTER_CALLBACK taskId=<taskId>` 且 `final: true`。
4. 找到多条时取最后一条，写入 `observations`，状态进入 `verifying`。
5. 找不到但 read window 覆盖了 dispatch 之后的时间段：状态保持 `awaiting_callback`，输出“缺回传”，给用户一条可复制催办消息。
6. 找不到且 read window 不能证明覆盖 dispatch 之后的时间段：状态转 `callback_unreachable`，提示用户打开 executor 线程手动复制 `TEAM_ROUTER_CALLBACK` 回总控重新解析。

### 7.4 验收

1. 将 executor 的原始 `TEAM_ROUTER_CALLBACK` block 逐字转发给 verifier，不做摘要或改写。
2. 向 verifier 发送 `TEAM_ROUTER_VERIFY`，记录 `messageId`、`sentAt` 和 `searchAnchor`。
3. 用 `read_thread` 读取 verifier 线程，搜索最后一条 `TEAM_ROUTER_VERDICT taskId=<taskId>`。
4. `result: pass` -> `done`。
5. `result: needs_rework` -> `needs_rework`，输出返工要求；用户确认后追加新 dispatch，`reworkCount += 1`，状态回到 `dispatched`。
6. `result: blocked` -> `blocked`，写明阻塞原因和缺少什么。
7. 无结构化 verdict -> `malformed_callback`；窗口不可覆盖 -> `callback_unreachable`。

## 8. 错误处理

- **工具不可用**：缺少 thread 工具或工具 schema 不匹配时，ledger 状态变为 `tool_error`，不继续派工。
- **线程不存在**：标记角色 `missing_role`，尝试 `list_threads`；多个候选要求用户确认，仍失败则创建新线程并记录替换。
- **线程无回传**：窗口可覆盖时不判完成；状态保持 `awaiting_callback`，给用户一条可复制催办消息。
- **回传窗口不可覆盖**：ledger 状态变为 `callback_unreachable`，要求用户手动复制原线程 marker block。
- **回传格式不合格**：ledger 状态变为 `malformed_callback`，要求原线程按格式重发。
- **工具调用失败**：ledger 状态变为 `tool_error`，不继续派下一个角色。
- **角色缺失**：无法创建或绑定必需角色时，ledger 状态变为 `missing_role`。
- **用户放弃**：用户明确取消、线程已删除或任务过时时，ledger 状态变为 `abandoned`。
- **权限越界**：第一版只允许 `read-only` 与 `design-only` 派工。如果任务包含写文件、commit/push/PR/merge/deploy/真实 API，必须停下，列出所需授权项，要求用户明确说出对应授权；获得授权后也不得在本 Skill 里执行写操作，必须转入现有 `dynamic-workflow`/worktree 写模式或后续版本的真实隔离 runner。
- **状态漂移**：如果 registry 的 thread title 与读到的线程不一致，保留 `threadId` 为真，title 只作为提示字段。

## 9. 与 dynamic-workflow 的关系

两者不互相替代：

- `dynamic-workflow`：一次性并行执行，适合批量 review、调研、模块化实现。
- `codex-team-router`：长期角色线程管理，适合跨天、跨任务、需要回传和验收的协作。

第一版只在文档中说明如何组合：

- 用户要“一次性分路” -> 用 `dynamic-workflow`。
- 用户要“长期团队组织” -> 用 `codex-team-router`。
- `manager` 后续可以建议把某个子任务交给 `dynamic-workflow`，但不能自动启动，仍按现有 dynamic-workflow 报数/授权规则走。

## 10. 测试计划

实现阶段至少覆盖：

1. registry 读写：以 `projectId` 为主 key，新建、更新、缺字段兼容、无效 JSON 报错。
2. ledger 状态机：主干、`needs_rework -> dispatched` 回边、终止态、非法迁移拒绝。
3. manager plan 协议：识别 `TEAM_ROUTER_PLAN`，拒绝缺 `taskId`、缺 `scope` 或 `status: blocked` 的派工。
4. executor callback 协议：识别合法 `TEAM_ROUTER_CALLBACK final: true`，同窗口多条时取最后一条。
5. verifier verdict 协议：识别 `TEAM_ROUTER_VERDICT result: pass|needs_rework|blocked`，拒绝自然语言 verdict。
6. 派工模板：必须含 `taskId`、`callbackMarker`、`permission`、`scope`、`stopWhen`、`searchAnchor`。
7. read_thread 恢复：覆盖 messageId 有值、messageId 为空但 sentAt 可用、窗口不可覆盖转 `callback_unreachable`。
8. 线程适配层：用 mock 工具结果模拟创建、读取、发消息、缺回传、多个 title 匹配、工具缺失。
9. 安全边界：含写文件、push/merge/deploy/真实 API 的目标必须要求显式授权，并转出本 Skill；不得自动发送给执行线程。
10. thread 创建输入：registry 必须记录并复用 `projectId`、target environment 和 role title；创建前重新 `list_projects` 确认 target。

若第一版只落 Skill 文档而不写 Python helper，则测试改为文档静态检查脚本：确认协议模板、状态和必填字段存在。

## 11. 设计风险

1. **子线程忘记回传**：这是核心风险。通过强制 callback marker、ledger 检查和催办消息缓解，但不能完全消除。
2. **线程状态不是实时真相**：`read_thread` 只能提供最近状态和摘要。所有状态都要标记 `lastObservedAt`，不要声称“当前正在做什么”。
3. **回传窗口可能不可覆盖**：如果 `read_thread` 不能读取 dispatch 之后的完整窗口，系统必须转 `callback_unreachable`，不能假装任务没回传。
4. **线程过多后管理成本上升**：第一版限制三角色，不支持任意扩员。
5. **长期日志可能泄露敏感上下文**：ledger 只存摘要、threadId、状态和证据路径，不存大段私密内容或完整工具输出。
6. **用户授权边界容易被跨线程稀释**：每条派工消息都必须重申权限边界，子线程不能继承未写明的 publish/release 权限。
7. **写权限声明可能被误解为沙箱**：MVP 不提供 `workspace-write` 派工字段；`read-only`/`design-only` 只是提示词边界，不是可验证沙箱。写入任务必须走单独授权和可验证 worktree/runner 边界。
8. **handoff 后 registry 可能陈旧**：用户明确移动线程工作区后，必须重新发现 target 和 hostId。

## 12. 验收标准

设计完成后进入实现前，应满足：

- 用户确认三角色 MVP 范围。
- 明确 registry 与 ledger 存放位置，并以 `projectId` 做 registry 主 key。
- 明确 thread 工具使用边界和 capability probe。
- 明确 manager plan、executor callback、verifier verdict 三类协议。
- 明确缺回传与 `callback_unreachable` 手工恢复处理。
- 明确 `read-only`/`design-only` 不是沙箱证明。
- 明确不做 UI/服务/自动发布。

实现完成后，应能通过一次人工端到端演示：

1. 创建或绑定三角色线程。
2. manager 输出 `TEAM_ROUTER_PLAN`。
3. 派发一个只读小任务，记录 `messageId` 或 `sentAt`。
4. executor 回传 `TEAM_ROUTER_CALLBACK final: true`。
5. verifier 回传 `TEAM_ROUTER_VERDICT result: pass`。
6. ledger 记录从 `created` 到 `done` 的完整状态。
7. 总控输出 closeout，并说明未覆盖范围。
