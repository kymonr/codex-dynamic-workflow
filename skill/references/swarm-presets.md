# Static Luna swarm presets

`preset-list` and `preset-ir` provide deterministic, zero-model Workflow IR v3
templates for high-parallelism read-only work. They do not inspect the declared
`workdir`, create a run directory, call Codex, decide a human gate, or grant
workspace/Git write access.

## Commands

List available presets and their projected agent budgets:

```powershell
py -3.12 skill\cli.py preset-list
```

Render a plan-compatible Workflow IR declaration to stdout:

```powershell
py -3.12 skill\cli.py preset-ir `
  --preset design-swarm `
  --objective "Design a safer concurrent order collector" `
  --workdir "D:\path\to\bounded-repository" `
  --max-agents 24 `
  --max-concurrency 8
```

The output is a pure declared Workflow IR document. It deliberately excludes
runtime-derived `execution` metadata, so it can be written as UTF-8 JSON and
passed directly to `plan-ir` and then `run-ir`.

The compiler calls the production `validate_workflow_ir()` before emitting any
document. It also recomputes the static/map/verify agent-claim upper bound and
fails closed when the selected `max_agents` is too small.

## Presets

| Preset | Default upper bound | Shape |
|---|---:|---|
| `design-swarm` | 19 | brief + six Luna designs + six adversarial verifiers + Sol synthesis + human gate + branch closeout |
| `ultra-review` | 23 | seven Luna review assignments covering eight dimensions + seven verifiers + Luna cross-check + Sol judgment + clean/blocker branch + gate + closeout |
| `repo-sweep` | 24 | up to ten Luna module audits + ten verifiers + Sol repository synthesis + gate + branch-specific terminal record |

All presets default to `max_agents=24` and `max_concurrency=8`. Preset generation
caps concurrency at 10 even though the lower-level runtime supports a larger
technical range. A caller may raise `max_agents` within the existing Workflow IR
hard range, but the preset graph itself remains fixed and deterministic.

## Objective and path handling

The exact objective remains in the top-level `objective` field. When an initial
agent must receive it, the compiler inserts a JSON-escaped, brace-neutral data
block. This prevents user text such as `{{result:other-node}}` from becoming a
trusted upstream-result placeholder.

The `workdir` is only copied into the top-level declaration. Preset generation
does not resolve, stat, list, or read it. The normal `run-ir` allowed-root,
sensitive-path, Codex identity, and external-model-export checks remain
mandatory before execution.

## Data-flow rules

Dependencies control scheduling only. Every agent that consumes an upstream
result has an explicit `{{result:<node-id>}}`, `{{item}}`, `{{candidate}}`, or
`{{source}}` placeholder. The preset compiler has an additional contract check
for these required placeholders.

Unselected conditional branches propagate `skipped` and do not create task
directories, attempts, or artifacts. Branch finalizers only consume their own
selected record. `repo-sweep` omits a separate finalizer so its worst-case
static + map + verify projection remains exactly 24 claims.

## Agent Fleet relation

Static presets retain fixed large graphs and fixed budgets. When the caller needs an exact 4–12 Luna count, discovery/challenge stages, deterministic claim aggregation, or conditional Sol arbitration, use `fleet-list` / `fleet-ir` and [Agent Fleet v1](agent-fleet-v1.md) instead. Agent Fleet does not replace existing preset names or silently reinterpret `ultra-review`.

## Current scope

These fixed preset graphs use only these executable read-only node kinds:

```text
agent, map, verify, reduce, conditional, human_gate
```

They do not implement or execute `loop`, Auto Planner, arbitrary model-generated
workflow code, workspace writers, Git writers, worktree merging, hidden retry,
or automatic model upgrades.
