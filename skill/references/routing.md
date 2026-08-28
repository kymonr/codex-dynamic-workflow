# Native routing contract

## Mode selection before route selection

Choose execution mode before model route:

1. **Root only** for trivial reads, short serial work, one implicit branch, or delegation whose coordination cost exceeds its value.
2. **Simple Swarm** for ordinary work with at least two dependency-ready, non-overlapping branches. This is the default.
3. **Managed Workflow** only when checkpoint/resume, Human Gate, bounded loop, conditional flow, long-running recovery, or formal run artifacts are explicitly needed.
4. **Writer Workflow** only when the user explicitly authorizes an isolated Worktree Writer candidate.

An explicit `$dynamic-workflow` or explicit subagent request may route one bounded branch. Implicit activation requires at least two useful child branches.

Complexity, repository size, file count, security wording, or the word `audit` does not by itself select Managed Workflow or Writer Workflow.

## Simple Swarm branch width

Simple Swarm routes 2–6 branches by default, with a hard ceiling of 8.

Each branch should normally have one objective, one primary responsibility, one module or 1–3 primary files, one independently useful deliverable, and one root-verifiable acceptance check.

Do not dispatch a combined package such as “CLI + runtime + Writer authority + tests + coverage”. Split it into orthogonal branches first.

Active branches should not substantially duplicate files or responsibility. Root must not repeat an active child’s investigation. Simple Swarm forbids nested delegation.

Use one bounded wait, one progress request after the first timeout, and one final bounded wait. If the second wait still produces no useful delivery and the branch blocks completion, close and re-split it or return the scope to root.

## Precedence

Apply routing rules in this order:

1. The user's explicit model, effort, tier, or context instruction.
2. An applicable dedicated skill or repository rule.
3. Risk and reversibility.
4. The ordinary complexity boundary: Luna for ordinary delegated work and scoped writing; Sol for complex or high-impact work.

Role files under the active `CODEX_HOME/agents` directory are authoritative for built-in role values. Resolve `CODEX_HOME` from the current process; use the platform default only when it is unset.

A named Dynamic Workflow route is a complete preset, not a set of independently overridable fields. When the user names only Spark, Luna, or Sol, use that route's preset. When the user also gives a conflicting model, effort, or tier, preserve the requested label for reporting but set the effective route to `Custom`:

- use `agent_type="default"` with the requested route's preset model/effort plus any explicit overrides, `fork_turns=none` or a finite positive range, and the parent tier only when that exactly represents the request;
- if the complete requested model/effort/tier combination matches a built-in preset, use that preset instead of Custom;
- if native dispatch cannot express the exact combination, show the conflict in the pre-dispatch line and ask the user before dispatch.

Never label a Custom dispatch as Luna, Spark, or Sol merely because its model resembles that preset.

Execution mode and model route are separate. Simple Swarm, Managed Workflow, and Writer Workflow choose orchestration shape; Luna and Sol choose the executor for one branch. Grok is outside native routing and never appears as an automatic route or recovery node. A dedicated reviewer is a separate exception role and lifecycle, not the ordinary Sol executor route. Trigger it only from the entry-point independent-review rule.

## Narrow Explorer pre-route

An explicit native route selection (`Spark`, `Luna`, `Sol`, `Custom`, or `inherited`) takes precedence and skips this pre-route, even for a bounded read-only question. Resolve the named route directly under its preset/context rules; never relabel an explicit route as `Explorer`.

When no explicit route was selected, use `agent_type="explorer"` only for one concrete, bounded, read-only codebase question whose answer can be locally verified. Broad or cross-module analysis, implementation, architecture/security decisions, synthesis, and final acceptance continue through the ordinary routes below.

Explorer uses `fork_turns=none` by default. It is not an automatic recovery node; any terminal non-success returns root.

## Complexity-based route boundary

Route ordinary read-only work and ordinary scoped implementation, repair, refactor, or file editing to Luna. Route directly to Sol when the branch itself requires complex cross-module reasoning, a nontrivial high-impact behavior change, architecture or security judgment, difficult rollback, or final judgment. Assess complexity per branch: file count, branch count, or long context alone does not select Sol. Grok is not a native route; only a user-requested separate Grok conversation task follows `grok-thread.md`.

## Writer Workflow profile boundary

Ordinary Luna/Sol branch routing and Worktree Writer profile selection are separate. Writer Workflow defaults to trusted `bounded-luna` for short, well-specified, low-risk edits with at most two owned targets. A nontrivial cross-module behavior change may use explicit `complex-sol` only with package v2 quality context. The package cannot select either profile, and `complex-sol` changes model identity and hard budgets—not create/modify-only authority. See [worktree-writer-v2.md](worktree-writer-v2.md).

## Routes

| Route | Native dispatch | Intended work |
|---|---|---|
| Spark | `agent_type="spark"` | Short, mechanical, low-risk, read-only, easily verified work |
| Luna | `agent_type="luna"` | Ordinary read-only work and ordinary scoped implementation, repair, refactor, or file editing |
| Sol | `agent_type="sol"` | Complex cross-module, high-impact, architectural, security-sensitive, hard-to-reverse, or final judgment work |
| Custom | `agent_type="default"` plus the preset model/effort and exact overrides | A user-requested combination that differs from a complete built-in preset |

The approved Luna role is `gpt-5.6-luna` / `max` / `fast`. In API request metadata, Fast is requested as `priority`; the pre-dispatch line reports this configured/requested tier as `fast`, not an observed delivery claim. Resolve Sol from the active `CODEX_HOME/agents/sol.toml`; its approved preset is `gpt-5.6-sol` / `xhigh` / `default`. Spark and Custom inherit the parent tier because native dispatch has no separate tier override. If `sol` is missing, disabled, or resolves to a different model/effort/tier, treat that as an unavailable or conflicting route and return to the root rather than silently selecting a generic `default`/`worker` role.

If the route is genuinely uncertain:

- choose Sol when error impact is high, rollback is difficult, or the result is a final judgment;
- otherwise choose Luna for ordinary delegated work and scoped writing;
- choose Spark only when all Spark criteria, including read-only access, are affirmative.

## Context forks

Use `fork_turns=none` by default and place the needed facts in the branch prompt. Use a finite positive range when recent turns materially reduce restatement or error risk.

Use `fork_turns=all` only when full conversation history is more important than route control. Full-history forks inherit the parent model and reasoning effort and cannot accept model/effort overrides. Report the resolved route as `inherited`, including the actual parent model and effort. Never describe such a child as Luna merely because Luna was intended.

An explicit model or effort override takes precedence over `all`: use `none` or a finite positive fork and restate the required context. If the user explicitly makes both full-history inheritance and a different model/effort non-negotiable, stop and ask which constraint to retain; never silently discard either one.

Sol-to-Luna nested work never uses `all` and is unavailable in Simple Swarm.

## Pre-dispatch disclosure

Before calling `spawn_agent`, first show one compact line per child:

`Subagent: <branch> -> <route> (<model>/<effort>/<tier>, fork=<range>)`

Resolve the values from the active role files, parent settings, user instruction, and dispatch arguments. When requested and effective routes differ, show `<requested> -> <effective>` in the route position. Append `, nested=Luna` only when nesting is allowed. Omit task, `agent_type`, and default `nested=forbidden` from this user-visible line; they remain in the dispatch prompt. If the route later advances, show the new line before spawning its replacement. An unresolved or inexpressible value is a visible conflict, not permission to guess or dispatch silently.

## Dispatch prompt

Include:

- a bounded task and concrete deliverable;
- owned files or responsibility;
- dependencies and acceptance checks;
- read/write authority and explicit exclusions;
- the instruction to preserve unrelated changes;
- whether nested delegation is allowed.

Simple Swarm forbids nested delegation for every route. Outside Simple Swarm, ordinary Luna and every Spark child still forbid nesting; a Sol branch may use at most one Luna-only nested layer when its selected advanced flow explicitly allows it. Those grandchildren must avoid further spawning.

## Recovery and route advances

### Monotonic route path

Do not maintain retry counters, route-change counters, or per-branch recovery budgets. Keep one executor active per branch. After an executor is confirmed terminal, the orchestrator does not replay, follow up, or respawn the same route. Provider or SDK retries underneath remain `UNKNOWN`.

Native recovery is a forward-only route DAG:

- Spark advances to Luna, then Sol, then root;
- Luna advances to Sol, then root;
- Sol advances to root;
- inherited and Custom routes return to root.

A route appears at most once in a branch path. Never return to an earlier route. Reaching root is terminal for automatic recovery.

### Failure classification

Root classifies provider and transport failures from native structured runtime fields; human-readable text and the child record are supporting evidence only:

- `CAPACITY`: `codex_error_info == server_overloaded`;
- `RATE_LIMIT`: a structured 429 or explicit rate-limit result;
- `OTHER_TRANSIENT`: a clearly recoverable transport or spawn failure;
- `CAPABILITY`: the child directly reports that the branch exceeds its reasoning or risk capability;
- `PERMANENT`: authentication, quota, unsupported-model, invalid-request, policy, or configuration failure;
- `AMBIGUOUS`: missing or conflicting fields, or a timeout whose side effects or terminal state cannot be established.

Do not classify generic latency, a missing response, or an arbitrary 5xx as capacity. A child-supplied provider failure class never overrides conflicting or missing native telemetry. Child labels and packaging are supporting evidence only; the root classifies the condition from runtime evidence, task content, and live state.

### Advance or stop

Only a root-confirmed `CAPACITY` or `CAPABILITY` condition with identifiable remaining work advances a native route to its next node. A child claim alone is insufficient. Show the replacement's updated `Subagent` line before dispatch. `RATE_LIMIT`, `OTHER_TRANSIENT`, `PERMANENT`, and `AMBIGUOUS` return directly to root; they do not switch models. Generic latency, a missing response, an arbitrary 5xx, or an output-format defect never advances a route.

Before the next route starts, the root reads back and reconciles completed local effects, verifies reusable completed work, then creates a minimal handoff for only the remaining work. External, destructive, credentialed, or `UNKNOWN` effects stop at root. Use `fork_turns=none` or a finite positive range; never assume a new child inherits the previous child's hidden reasoning or tool state.

The handoff contains the branch goal and acceptance check, authority and exclusions, requested and effective route/model/effort/tier/fork, the traversed route path, root-owned failure evidence, completed effects with readback, useful verified results, remaining work, and explicit `UNKNOWN`. Do not replay or follow up with the same route solely to obtain different formatting.

Outside Simple Swarm, nested Luna helpers are part of their Sol branch, not independent recovery routes. A terminal nested failure returns its structured error and effects through Sol to the top-level root. Neither Sol nor the nested Luna automatically follows up, respawns, replaces, or reroutes that nested branch.

A root handoff is a stop condition, not permission to execute the branch again automatically.

## Post-spawn adoption

The pre-dispatch line is the expected/configured identity:

`Subagent: <branch> -> <route> (<model>/<effort>/<tier>, fork=<range>)`

After spawn, use native runtime metadata first. Use scoped child `turn_context`/session metadata only for runtime fields omitted by the native receipt, and applicable project/user config only for missing requested/configured fields. Never overwrite observed metadata with fallback. Model and reasoning-effort mismatches are critical identity mismatches: interrupt/exclude the branch output, reconcile observed effects, and return root. Service tier is performance telemetry, not model identity: record requested/configured and observed response tiers separately. A requested `priority`/`fast` tier that returns `default` is a downgrade, not fast delivery and not a branch-invalidating identity mismatch unless the user explicitly made fast service a non-negotiable acceptance condition. An unresolved critical identity is `UNKNOWN` and returns root. Do not present configuration as runtime observation.

When independent review is triggered, reviewer identity, sandbox evidence, and adoption are governed only by [review.md](review.md). A reviewer mismatch or unresolved critical identity returns root before verdict adoption.
