# Auto Planner v1

Auto Planner v1 is a bounded selector over the fixed, versioned read-only swarm preset registry. It does **not** generate Workflow IR graphs, prompts, schemas, permissions, code, commands, retries, model routes, releases, or deployment actions.

## Commands

Show the zero-model registry and contracts:

```powershell
py -3.12 skill\cli.py auto-plan-contract `
  --max-agents 24 `
  --max-concurrency 8
```

Use one Luna planner to select a preset and have the host compile it:

```powershell
py -3.12 skill\cli.py auto-plan `
  --objective "Review the order collector for concurrency and recovery bugs" `
  --workdir "D:\sanitized\repository" `
  --max-agents 24 `
  --max-concurrency 8 `
  --ack-external-model-export
```

The result contains the validated model selection, deterministic adapter evidence, and a declared Workflow IR document. It does not execute the generated workflow. Save `workflow_ir` to a UTF-8 JSON file, inspect it with `plan-ir`, then deliberately choose `run-ir` with the normal allowed-root and external-model-export checks.

Revalidate a saved selection without a model call:

```powershell
py -3.12 skill\cli.py auto-plan-apply `
  --selection D:\evidence\planner-selection.validated.json `
  --objective "Review the order collector for concurrency and recovery bugs" `
  --workdir "D:\sanitized\repository" `
  --max-agents 24 `
  --max-concurrency 8
```

## Registry contract

The registry is built from `swarm_presets.PRESETS` and additional versioned selection guidance. Every entry fixes:

- preset name and description;
- conservative projected agent claims;
- when the preset is appropriate or inappropriate;
- deterministic compiler identity;
- read-only and human-gate properties.

Registry guidance must cover the preset registry exactly. Missing or extra guidance fails closed. A SHA-256 registry digest and a context-specific contract digest bind the selection.

## Parameter contract

The host owns:

- objective;
- workdir;
- max agent and concurrency budgets;
- preset allowlist;
- permissions, models, timeouts, artifact limits, prompts, schemas, and workflow nodes.

The model never receives the target workdir and the planner workspace is an empty temporary directory. An opaque parameter digest binds objective, workdir, budgets, and the eligible preset set without disclosing the workdir to the model.

Objective text is JSON encoded and its braces are neutralized before entering the planner prompt. Text such as `{{result:other-node}}` remains untrusted data and cannot become a result placeholder.

## Action contract

The only model action is:

```text
select_preset
```

The selection must:

- choose one eligible registered preset;
- evaluate every eligible preset exactly once;
- mark exactly one candidate `best`;
- make `selected_preset` equal to that candidate;
- echo exact registry, contract, and parameter digests;
- return bounded rationale, signals, and uncertainty.

Unknown keys, stale digests, duplicate candidates, missing candidates, multiple best candidates, or any model-authored graph fail closed.

## Adapter contract

After semantic validation, the host calls only:

```python
swarm_presets.render_preset(...)
```

The adapter then runs the production Workflow IR validator and `plan-ir` projection. It refuses projection drift, unsupported node kinds, or budget overflow. The model cannot override the selected preset's graph, prompts, schemas, permissions, models, retry behavior, or branch semantics.

## Evidence and exit behavior

`auto-plan` creates a normal bounded planner run directory containing the one Luna task plus:

- `planner-selection.validated.json`;
- `workflow-ir.declared.json`;
- `auto-plan.json`.

The target workdir is neither read nor written during planning. The output reports one model call, the planner attempt metadata, selection, adapter digests, and generated IR.

Exit codes:

- `0`: contract, deterministic apply, or one-agent plan completed;
- `1`: invalid host input, stale/invalid saved selection, or missing export acknowledgement;
- `2`: planner process failure, escalation, malformed model output, semantic selection failure, or interruption.

Auto Planner v1 does not execute `loop`, perform workspace/Git writes, hide retries, upgrade models, merge, release, or deploy.
