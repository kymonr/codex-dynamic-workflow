# Side Effect Taxonomy

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep sideEffectTaxonomy details here.

## sideEffectTaxonomy

Manager Mode must classify every parent-side action by side effect before acting. The taxonomy is a policy boundary for Manager Mode, commit closeout, role dispatch, watcher reads, and reviewer routing.

### READ_ONLY

Non-mutating inspection: inspect status/diff/log/show, read files, search with `rg`, use CodeGraph query/status/explore, perform low-frequency/event-driven `read_thread`, and other non-mutating inspection.

Allowed for manager assessment, review routing, watcher checks, and commit closeout preflight. `READ_ONLY` does not authorize implementation and must not become implementation.

### DISPATCH_ONLY

Routing actions: create or reuse role threads when required, send `TEAM_ROUTER_DISPATCH`, `TEAM_ROUTER_REVIEW_REQUEST`, or `TEAM_ROUTER_VERIFY`, record/capture ledger state, and continue direct-return state transitions.

Allowed only after an explicit current-turn request to create or dispatch visible roles. Before any `create_thread`, message send, registry, or ledger write, the objective, scope, permission boundary, and stop condition must be known. Planning, review, design acceptance, and terse replies may prepare dispatch metadata but do not execute `DISPATCH_ONLY`. `DISPATCH_ONLY` is not equivalent to the manager implementing changes.

For Version 2, decide Manager direct before this gate: a direct route creates no ledger, title, heartbeat, or thread state. A delegated route must also have explicit model-routing authorization before any `DISPATCH_ONLY` side effect; plain Manager wording cannot supply it.

### LOCAL_CLOSEOUT

After verifier pass and an explicit user request to commit, manager may run local status/diff, stage only accepted files, and create a local commit.

`LOCAL_CLOSEOUT` excludes continued implementation, unrelated untracked files, push, PR, merge, deploy, publish, and release.

### WORKSPACE_WRITE

Mutating project work: modifying project files, running formatters that write, generating fixtures, changing runtime, docs, or tests.

In active Manager Mode, `WORKSPACE_WRITE` is delegated to executor when the manager dispatch explicitly grants an authorized `local-package` scope and required reviewer/verifier gates apply. The executor may write only within the explicit scope/files/paths in that delegation. Manager/dispatcher direct file edits are opt-in: they require an explicit current-turn instruction that the manager should do that exact file-changing action. Commit, PR, publish, and release must first be presented as gated actions and wait for explicit authorization.

`local-package` does not automatically mean STRICT/PACKAGE or create Reviewer/Verifier. Version 2 first applies risk classification and route closure: FAST/NORMAL delegated work may use Manager acceptance; STRICT/PACKAGE and explicit Reviewer/QA keep the independent review/verification route.

Small artifact/docs/.gitignore policy tasks still count as `WORKSPACE_WRITE` when they edit files or run write-prone verification; active Manager Mode must dispatch an authorized executor package, or proceed only when the user explicitly says in the current turn that the manager should do that exact work.

### HEAVY_OR_RISKY

Long benchmarks, installs/upgrades, destructive cleanup, global config changes, external API or production-data access, and network publishing.

Requires explicit separate authorization. Manager cannot infer `HEAVY_OR_RISKY` authorization from `修`, `继续`, `开始修`, `先修`, `修这个`, `可以`, or `do it`.

### EXTERNAL_RELEASE

Push, PR, merge, deploy, publish, or release.

Requires separate publish/release authorization, explicitly separate from local commit. `EXTERNAL_RELEASE` never rides along with commit, `LOCAL_CLOSEOUT`, or verifier pass.

## Precedence Rules

In active Manager Mode, terse approvals like `可以`, `修`, `继续`, `开始修`, `先修`, `修这个`, and `do it` authorize only a dispatch proposal. They do not authorize `create_thread`, message dispatch, registry/ledger writes, or implementation unless the user explicitly requests that separate gate.

`READ_ONLY` can support manager judgment, review routing, low-frequency/event-driven watcher/read_thread policy, and commit preflight, but it must not become implementation.

`LOCAL_CLOSEOUT` is allowed only after verifier pass plus explicit user commit request.

`WORKSPACE_WRITE` is delegated executor work under explicit `local-package` authorization and required gates, limited to the delegated scope. It is not manager direct-edit permission unless the current turn explicitly tells the manager to do that exact file-changing work.

`HEAVY_OR_RISKY` requires explicit separate authorization and cannot be inferred from terse approvals.

`EXTERNAL_RELEASE` requires explicit publish/release authorization and never rides along with commit or local closeout.

## Policy Links

Manager Mode hard rule: terse implementation commands in active Manager Mode authorize only routing analysis and a dispatch proposal, not actual dispatch or parent-side implementation.

Manager commit closeout policy: local commit closeout is `LOCAL_CLOSEOUT`; it requires verifier pass and explicit commit request, stages only accepted files, and excludes unrelated untracked files plus push/PR/merge/deploy.

roleCloseoutPolicy: final protocol blocks are the closeout; default is no extra role-thread closeout message. Sending extra stop text is not a hidden implementation channel.

Watcher/read_thread policy: manager reads are `READ_ONLY` and must remain low-frequency and event-driven.

Named reviewer requirement: when reviewer is required or named for Team Router self changes, use an already-authorized visible reviewer role conversation. Subagent fallback is not allowed. Under a review-only gate, if no authorized reviewer role exists, report the blocker instead of creating or dispatching one.
