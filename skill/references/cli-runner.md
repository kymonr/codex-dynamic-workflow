# Explicit CLI bounded read-mode runner

Use the CLI runner only when the user explicitly needs reproducible CLI logs, per-task artifacts, a machine-readable summary, or a controlled real `codex exec` probe. Native subagents remain the default.

The runner is intentionally Codex-only. Every child command is fixed to Codex CLI `read-only` mode, and there is no Claude backend, workspace-write mode, Git preparation, commit, worktree, apply, push, cleanup command, or arbitrary command override. The runner itself still writes prompts, schemas, logs, outputs, and summaries to its isolated artifact directory.

## Portable entry point

Use `cli.py`, which establishes platform-appropriate state directories before importing the compatibility runner:

```powershell
python "$env:CODEX_HOME\skills\dynamic-workflow\cli.py" run `
  --spec D:\path\workflow.json `
  --allowed-root D:\codex\one-project `
  --ack-external-model-export
```

```bash
python "$CODEX_HOME/skills/dynamic-workflow/cli.py" run \
  --spec /path/workflow.json \
  --allowed-root /workspace/one-project \
  --ack-external-model-export
```

The artifact root uses `DYNWF_RUNS_ROOT` when set. Otherwise it resolves from `DYNWF_HOME` or the platform user-state directory. `DYNWF_WORKTREE_ROOT` is reserved for isolated writer workflows and is not used by this read-only runner. Direct execution of `runner.py` remains a compatibility path only.

`--allowed-root` is mandatory. The runner rejects drive/filesystem roots, the user's home, the active `CODEX_HOME`, their ancestors, work outside the allowed root, reparse-point escapes, and a narrow set of high-confidence credential or local-database filenames. Exact false positives can be allowed only from the command line with repeated `--allow-sensitive-path`; never put those exceptions in a shared spec.

These are fail-closed path preflights, not an operating-system read allowlist or content/DLP scan. `-C` and `--allowed-root` do not prove that every possible read is confined to that tree. The runner does not independently block network, accounts, Windows credential stores, or external model access. On Windows it requires the PATH-resolved `codex.exe` to pass a Codex version probe and an OpenAI Authenticode publisher check, but it does not pin an immutable binary hash. Use the CLI path only on a deliberately bounded, sanitized, non-production worktree; otherwise stop. The root agent owns artifact retention and any later manual cleanup decision.

`--ack-external-model-export` records that the root agent already evaluated the export boundary. It is not a substitute for user authorization and must not be treated as a second approval ceremony.

## Version 2 specification

```json
{
  "version": 2,
  "name": "bounded-read-review",
  "workdir": "D:\\codex\\one-project",
  "max_concurrency": 3,
  "soft_timeout_seconds": 900,
  "hard_timeout_seconds": 3600,
  "tasks": [
    {
      "id": "inspect",
      "prompt": "Inspect the named module and report evidence only.",
      "role": "luna",
      "route_reason": "ordinary bounded inspection",
      "depends_on": [],
      "output_schema": {
        "type": "object",
        "additionalProperties": false,
        "properties": {"finding": {"type": "string"}},
        "required": ["finding"]
      },
      "allow_escalation": false
    }
  ]
}
```

Roles are `spark`, `luna`, and `sol`. Luna is the default. Spark and Luna resolve model metadata from the active role files; Sol resolves to the configured pinned Sol route. `allow_escalation` is retained as a compatibility input: `false` is accepted and `true` is rejected during spec validation, before any run directory, artifact, or child process exists, with the exact error `v2 allow_escalation=true is no longer executable; choose the final role explicitly or use native Dynamic Workflow routing`.

The runner accepts legacy read-only `stages` specs and converts each stage barrier into `depends_on` edges to the immediately preceding stage. It rejects legacy Claude tasks and exposes no write-oriented runner command or mode; task behavior is still bounded by Codex read-only mode and the prompt boundary, not a separate OS write detector.

## Artifacts

Each run retains its local task directories and writes `summary.json`. Artifacts are never deleted automatically and inherit the artifact root's existing filesystem ACL; the runner does not claim private storage. The full task prompt is retained in `prompt.txt` but is sent to the child over stdin rather than exposed in `cmd.json` or the process command line. Do not put credentials, reusable sessions, customer datasets, or unnecessary personal information into a workflow prompt.

The resolved spec and summary retain the v2 shape, including route metadata, attempts, duration, token estimates, output, terminal state, and deprecated compatibility fields `retry` and `upgrade`; those fields are always `0` and `null` and are not active control state. Runtime model metadata is requested/resolved configuration unless the CLI itself proves a different value.

There is no transient same-route retry, prompt replay, regex retry classification, automatic model upgrade, CLI v3, `--mode`, or write capability. Nonzero exits, transient-looking text, rate limits, timeouts, `needs_escalation`, permanent failures, and ambiguous failures terminate the task and return evidence to root. Unrelated DAG branches continue; descendants of a non-success task are blocked. Cancellation and hard safety timeouts remain resource/termination controls.
