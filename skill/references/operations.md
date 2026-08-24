# Workflow IR operational commands

`plan-ir` and `run-status` are read-only operator surfaces. They do not call a model, advance a checkpoint, write a gate decision, create a cancellation marker, or modify the workspace.

## Plan preview

Validate and preview a Workflow IR v3 declaration before choosing `run-ir`:

```powershell
py -3.12 skill\cli.py plan-ir --spec examples\reference-repository-audit.workflow-ir.json
```

```bash
python3.12 skill/cli.py plan-ir \
  --spec examples/reference-repository-audit.workflow-ir.json
```

The JSON result includes:

- deterministic topological order;
- node kind, dependencies and `dependency_policy`;
- bounded condition and human-gate contracts;
- prompt length, digest and a short preview instead of full prompt duplication;
- static, map-child, verifier-child, and bounded-loop-child agent-claim projections;
- executable and validated-only node kinds;
- current resolved artifact limits;
- warnings for advisory token budgets, per-agent timeout scope, and an optional absolute whole-workflow deadline.

`plan-ir` deliberately does **not** run allowed-root, sensitive-path, Codex executable identity or external-model export preflight. It never touches the declared `workdir`. A successful preview therefore proves that the declaration is structurally valid, not that `run-ir` is authorized or safe to start on the named path.

The reference workflow exercises the complete currently executable non-loop
control-flow set:

```text
agent → map → verify → reduce → conditional
                              ├─ selected report
                              └─ skipped report
                                   ↓
                              human_gate
                                   ↓
                              conditional
                              ├─ record-accepted → finalize-accepted
                              └─ record-rejected → finalize-rejected
```

Use `examples/bounded-design-convergence.workflow-ir.json` for the separate
Bounded Loop v1 execution path.

The closeout paths are explicit and mutually exclusive. Both record nodes
depend on `choose-gate-outcome`, `review-gate`, and `summarize-audit`; their
prompts must carry both `{{result:review-gate}}` and
`{{result:summarize-audit}}`. Each finalizer depends only on its corresponding
record and its prompt carries only that record result. The record contract is
an object with `decision` (`approve` or `reject`), `summary`, `evidence[]`, and
`next_actions[]`. Each final contract retains those fields and adds `status`
(`accepted` or `rejected`) and `uncertainty[]`, with strict object, array, item,
enum, required, and `additionalProperties: false` schema keywords. An
unselected record and its finalizer propagate `skipped`; they are not executed
and therefore do not create task directories.

Replace the example `workdir` with one deliberately sanitized repository before running it. Only complete Bounded Loop v1 instances are executable; legacy `loop` declarations remain instance-level validated-only and are explicitly rejected. A declared `workflow_timeout_seconds` is an absolute deadline that survives resume and includes human-gate pause time.

## Run status

Inspect a Workflow IR v3 run without advancing it:

```powershell
py -3.12 skill\cli.py run-status `
  --run-dir D:\path\to\dynamic-workflow\runs\one-run
```

```bash
python3.12 skill/cli.py run-status \
  --run-dir /path/to/dynamic-workflow/runs/one-run
```

Filter to one node:

```powershell
py -3.12 skill\cli.py run-status `
  --run-dir D:\path\to\one-run `
  --node-id review-gate
```

`checkpoint.json` is the status source of truth. `summary.json` is treated as a compatibility/user-facing projection and is compared against the checkpoint; mismatches are reported rather than silently reconciled. The command rejects checkpoints whose entry IDs or entry statuses disagree with the checkpoint state map. It also recomputes the resolved Workflow IR digest and reports any mismatch with the checkpoint. The command returns only operational metadata:

- workflow state and per-state counts;
- node status, timestamps, resume count and error;
- condition state and gate state;
- resolved IR / checkpoint / summary digest consistency;
- redacted gate metadata without the gate prompt or task outputs.

The run directory must be a real child of `DYNWF_RUNS_ROOT` and may not traverse symlinks, junctions or reparse points. The command rejects malformed IR, checkpoint node-set changes and unsafe gate records. For the full gate prompt and immutable decision contract, use `gate-status`.

## Exit behavior

- `0`: preview or status completed successfully;
- `1`: malformed input, unsafe path, corrupted run metadata or another fail-closed validation error.

Neither command uses the `--ack-external-model-export` flag because neither command starts a model process or exports repository data.
