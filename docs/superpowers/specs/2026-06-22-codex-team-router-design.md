# 设计：Codex Skill + thread tools 的三角色团队路由 MVP

- 日期：2026-06-22
- 状态：已设计，待用户审阅
- 范围：新增一个 Codex Skill 级控制平面，用 Codex app thread 工具管理长期 Agent 团队；不改 `dynamic-workflow` runner，不做 UI，不做本地常驻服务。
- 涉及文件（实现阶段预计）：`skill/`（新增 skill 正文）、`src/`（可选的本地 ledger/protocol helper）、`tests/`（协议与 ledger 单测）、`README.md`（使用说明）。

---

## 1. 背景与定位

现有 `dynamic-workflow` 解决的是“一次任务内多子代理并行执行”：主会话拆任务，使用 `native-subagent` 或 `cli-runner` 跑一批子任务，最后汇总结果。

本设计要补的是另一层：**长期多会话团队控制平面**。用户在总控会话里发起任务后，Skill 负责找到或创建角色线程，派活，检查回传，验收，写入可追溯 ledger。

第一版只做三角色团队：

- `manager`：拆任务、维护状态、决定派给谁。
- `executor`：执行具体任务，只按派工边界交付。
- `verifier`：验收执行结果，找风险，决定是否通过或返工。

目标不是“创建很多 Agent”，而是让一条任务有可靠闭环：

```text
register roles -> dispatch task -> await callback -> verify result -> close out or mark blocked
```

## 2. MVP 成功标准

第一版完成后，用户可以在总控会话里说：

```text
用 codex-team-router 启动三角色团队处理 <任务>
```

系统应能做到：

1. 读取或创建一个项目作用域内的 `manager`、`executor`、`verifier` 线程。
2. 给每个线程设置可识别标题，并在本地 registry 记录 `threadId`、角色、项目、创建时间、最后观察时间。
3. 为用户任务生成唯一 `taskId`，写入 task ledger。
4. 向目标线程发送标准派工消息，消息里强制包含回传目标、回传格式、停止条件、权限边界。
5. 读取线程最近状态，判断是否有符合协议的回传。
6. 将执行结果交给 verifier 线程验收，或在缺回传/异常时标记 `blocked`。
7. 最终向用户输出一段短 closeout：成功、失败、缺回传、未覆盖范围和下一步。

## 3. 非目标

第一版明确不做：

- 不做独立 CLI、本地服务、Web UI 或 Electron 控制台。
- 不自动修改 `dynamic-workflow` 的 runner 调度逻辑。
- 不让子线程自行创建更多线程。
- 不自动 commit、push、PR、merge、deploy。
- 不假装知道“当前活跃线程”。只使用 thread 工具可读到的 `threadId`、最近状态和最后检查时间。
- 不做无人值守轮询。每次检查由用户或总控会话明确触发。

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

Registry 是本地 JSON 文件，用于记录角色线程。建议路径：

```text
D:\.codex-tmp\team-router\registry.json
```

记录结构：

```json
{
  "version": 1,
  "projects": {
    "<projectKey>": {
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

`projectKey` 第一版用当前项目路径归一化后的短 hash 或 slug。不要用“当前线程”推断；必须来自当前工作目录、用户指定项目或 `list_projects` 返回值。

### 4.3 Task Ledger

Ledger 是任务级事实表。建议路径：

```text
D:\.codex-tmp\team-router\tasks\<taskId>.json
```

状态机：

```text
created
  -> roles_ready
  -> dispatched
  -> awaiting_callback
  -> verifying
  -> done
  -> blocked
```

任务记录最小结构：

```json
{
  "version": 1,
  "taskId": "ctr-20260622-001",
  "projectKey": "codex-dynamic-workflow",
  "objective": "<用户原始目标>",
  "status": "awaiting_callback",
  "dispatches": [
    {
      "role": "executor",
      "threadId": "<threadId>",
      "messageId": null,
      "sentAt": "2026-06-22T00:00:00+08:00",
      "expectedCallback": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-001"
    }
  ],
  "observations": [],
  "verification": null,
  "closeout": null
}
```

## 5. 消息协议

所有跨线程消息必须带机器可识别的头部，避免自然语言回传漏掉关键字段。

### 5.1 派工消息

```text
TEAM_ROUTER_DISPATCH
taskId: <taskId>
role: executor
replyToThread: <managerThreadId or callingThreadId>
callbackMarker: TEAM_ROUTER_CALLBACK taskId=<taskId>
permission: read-only | workspace-write | design-only
scope: <明确路径或业务范围>
stopWhen: <完成条件或阻塞条件>

目标：
<用户目标>

交付格式：
请在完成时发送一条包含以下字段的回传：
TEAM_ROUTER_CALLBACK taskId=<taskId>
status: done | blocked
summary: <3-7 行>
evidence: <文件/命令/线程观察>
risks: <未覆盖或失败>
next: <建议下一步>
```

### 5.2 回传消息

```text
TEAM_ROUTER_CALLBACK taskId=<taskId>
status: done | blocked
summary: <3-7 行中文小结>
evidence: <文件路径、命令输出摘要或线程观察>
risks: <未覆盖、失败或不确定事项；无则写 none>
next: <建议下一步；无则写 none>
```

总控只把含 `TEAM_ROUTER_CALLBACK taskId=<taskId>` 的内容视为有效回传。普通聊天、解释、工具日志都只能作为观察，不得自动判完成。

## 6. Thread 工具适配

当前 Codex app 已暴露以下能力，第一版只依赖这些工具：

- `list_projects`：查项目，创建项目线程前使用。
- `create_thread`：创建角色线程。只在用户明确要求系统版或角色缺失时使用。
- `list_threads`：按标题/关键词查已有角色线程。
- `read_thread`：读取近期状态和 turn summaries。
- `send_message_to_thread`：派工、验收、返工。
- `set_thread_title`：确保角色线程标题可识别。
- `set_thread_pinned`：可选，把 manager 线程 pin 住。
- `set_thread_archived`：只在用户明确要求清理时使用。

第一版不使用 `handoff_thread`，除非用户明确要求移动线程工作区。

## 7. 工作流

### 7.1 初始化团队

1. 识别项目作用域。
2. 读取 registry。
3. 对每个角色：
   - registry 有 `threadId`：用 `read_thread` 验证能读。
   - registry 缺失或读失败：用 `list_threads` 搜索标题。
   - 仍无可用线程：用 `create_thread` 创建。
4. 更新 registry。
5. 输出角色清单和未解决问题。

### 7.2 派发任务

1. 生成 `taskId`。
2. 写 task ledger，状态 `created`。
3. 确认三角色线程可读，ledger 状态变为 `roles_ready`。
4. manager 线程收到目标和拆分要求。
5. executor 线程收到具体派工消息，ledger 状态变为 `dispatched`。
6. 派工消息写入成功后，ledger 状态变为 `awaiting_callback`。

### 7.3 检查回传

1. 用 `read_thread` 读取 executor 最近 turn。
2. 搜索 `TEAM_ROUTER_CALLBACK taskId=<taskId>`。
3. 找到则写入 `observations`，状态进入 `verifying`。
4. 找不到则状态保持 `awaiting_callback`，输出“缺回传”，不自动重试。

### 7.4 验收

1. 将 executor 回传发给 verifier。
2. verifier 必须输出：
   - `pass`
   - `needs_rework`
   - `blocked`
3. 总控读取 verifier 回传。
4. `pass` -> `done`。
5. `needs_rework` -> 用户确认后再派返工。
6. `blocked` -> 写明阻塞原因和缺少什么。

## 8. 错误处理

- **线程不存在**：标记角色 `missing`，尝试 `list_threads`，仍失败则创建新线程并记录替换。
- **线程无回传**：不判完成；输出“awaiting_callback”，给用户一条可复制催办消息。
- **回传格式不合格**：记录为 `malformed_callback`，要求原线程按格式重发。
- **工具调用失败**：ledger 记录 `tool_error`，不继续派下一个角色。
- **权限越界**：如果任务包含 commit/push/PR/merge/deploy/真实 API，必须停下要求用户明确授权对应 package。
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

1. registry 读写：新建、更新、缺字段兼容、无效 JSON 报错。
2. ledger 状态机：合法状态迁移、非法迁移拒绝。
3. 协议解析：识别合法 `TEAM_ROUTER_CALLBACK`，拒绝缺 `taskId` 或不匹配的回传。
4. 派工模板：必须含 `taskId`、`callbackMarker`、`permission`、`scope`、`stopWhen`。
5. 线程适配层：用 mock 工具结果模拟创建、读取、发消息、缺回传。
6. 安全边界：含 push/merge/deploy/真实 API 的目标必须要求显式授权，不得自动发送给执行线程。

若第一版只落 Skill 文档而不写 Python helper，则测试改为文档静态检查脚本：确认协议模板和必填字段存在。

## 11. 设计风险

1. **子线程忘记回传**：这是核心风险。通过强制 callback marker、ledger 检查和催办消息缓解，但不能完全消除。
2. **线程状态不是实时真相**：`read_thread` 只能提供最近状态和摘要。所有状态都要标记 `lastObservedAt`，不要声称“当前正在做什么”。
3. **线程过多后管理成本上升**：第一版限制三角色，不支持任意扩员。
4. **长期日志可能泄露敏感上下文**：ledger 只存摘要、threadId、状态和证据路径，不存大段私密内容或完整工具输出。
5. **用户授权边界容易被跨线程稀释**：每条派工消息都必须重申权限边界，子线程不能继承未写明的 publish/release 权限。

## 12. 验收标准

设计完成后进入实现前，应满足：

- 用户确认三角色 MVP 范围。
- 明确 registry 与 ledger 存放位置。
- 明确 thread 工具使用边界。
- 明确回传协议和缺回传处理。
- 明确不做 UI/服务/自动发布。

实现完成后，应能通过一次人工端到端演示：

1. 创建或绑定三角色线程。
2. 派发一个只读小任务。
3. executor 回传 callback。
4. verifier 验收。
5. ledger 记录从 `created` 到 `done` 的完整状态。
6. 总控输出 closeout，并说明未覆盖范围。
