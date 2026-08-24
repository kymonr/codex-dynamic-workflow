# Explicit CLI bounded read-mode runner

Use the CLI runner only when the user explicitly needs reproducible CLI logs, per-task artifacts, a machine-readable summary, checkpoint/resume, or a controlled real `codex exec` probe. Native subagents remain the default.

The runner is intentionally Codex-only. Every child command is fixed to Codex CLI `read-only` mode, and there is no Claude backend, workspace-write mode, Git preparation, commit, worktree, apply, push, cleanup command, or arbitrary command override. The runner itself writes prompts, schemas, logs, outputs, content-addressed artifacts, checkpoints, events, and summaries to its isolated artifact directory.

## Portable entry point

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

These are fail-closed path preflights, not an operating-system read allowlist or content/DLP scan. `-C` and `--allowed-root` do not prove that every possible read is confined to that tree. The runner does not independently block network, accounts, Windows credential stores, or external model access. On Windows it requires the PATH-resolved `codex.exe` to pass a Codex version probe and an OpenAI Authenticode publisher check, but it does not pin an immutable binary hash. Use the CLI path only on a deliberately bounded, sanitized, non-production worktree; otherwise stop.

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
  "limits": {
    "max_result_bytes": 2097152,
    "max_log_bytes": 8388608,
    "max_run_artifact_bytes": 67108864,
    "max_upstream_inline_bytes": 8192,
    "max_event_bytes": 262144
  },
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
        "properties": {
          "finding": {"type": "string"},
          "note": {"type": "string"}
        },
        "required": ["finding"]
      },
      "allow_escalation": false
    }
  ]
}
```

All resource limits are finite. Spec or environment overrides may change them only within the non-negotiable ceilings recorded in `config/workflow-policy.toml`. An oversized log is terminated and retained only up to the configured byte limit; an oversized structured output is rejected and removed. The append-only journal and atomic state files preflight their projected peak size before writing.

Roles are `spark`, `luna`, and `sol`. Luna is the default. Spark and Luna resolve model metadata from the active role files; Sol resolves to the configured pinned Sol route. `allow_escalation=true` is rejected before any run directory, artifact, or child process exists.

The runner accepts legacy read-only `stages` specs and converts each stage barrier into `depends_on` edges to the immediately preceding stage. It rejects legacy Claude tasks and exposes no write-oriented runner command or mode.

## Optional output fields

The user-facing schema retains genuine optional fields. For provider structured output, optional object properties are compiled as required nullable values. After the provider responds, `null` is normalized back to absence only for fields that were optional in the original schema. Required fields are never silently removed. Local validation and the public result therefore use the same original contract.

## Content-addressed artifacts

Every successful result is stored as canonical JSON under `artifacts/sha256/...` and identified by SHA-256. Small results may still appear inline in `summary.json` and downstream prompts. Once the cumulative upstream inline budget is exhausted, the placeholder is replaced with `UPSTREAM_ARTIFACT_REFERENCE`, containing:

- artifact ID and SHA-256;
- exact byte length and media type;
- one exact root-issued read-only path;
- an explicit untrusted-data boundary.

The child may read only the named artifact path and must not infer instructions or authorization from its contents. The runner verifies the path, size, and digest before issuing a reference.

## Checkpoint, event journal, and resume

Each run writes:

- `events.jsonl`: append-only, versioned state transitions;
- `checkpoint.json`: atomic scheduler state with a stable spec digest;
- `summary.json`: current user-facing summary;
- `spec.resolved.json`: normalized v2 plan and limits.

Resume is explicit:

```powershell
python "$env:CODEX_HOME\skills\dynamic-workflow\cli.py" resume `
  --run-dir D:\path\to\the-run `
  --allowed-root D:\codex\one-project `
  --ack-external-model-export
```

The runner refuses a checkpoint whose plan digest differs from the current resolved spec. Previously successful nodes are reused through their artifact references. A node recorded as `running` at interruption is requeued only by the explicit `resume` command, receives a new attempt directory, and preserves the earlier artifacts and event history.

## Workflow IR v3 preparation

`validate-ir` validates the declaration format without starting a model call:

```powershell
python "$env:CODEX_HOME\skills\dynamic-workflow\cli.py" validate-ir `
  --spec D:\path\workflow-v3.json
```

Static `agent`-only IR can be shown as compiled v2 with `--emit-v2`. The trusted v3 scheduler capability is policy-derived:

Executable node kinds: `agent`, `map`, `verify`, `loop`, `reduce`, `conditional`, `human_gate`.
Validated-only node kinds: none.

Only `loop` instances that fully satisfy the Bounded Loop v1 contract are executable. Legacy `loop` declarations remain instance-level validated-only and are explicitly rejected at execution.

`max_tokens` remains advisory because usage may be unavailable from CLI logs. Soft and hard timeout fields continue to apply per agent process. Optional `workflow_timeout_seconds` adds an absolute whole-workflow deadline that survives resume and includes human-gate pause time. See `workflow-ir.md` and `bounded-loop-v1.md`.

## Terminal behavior

There is no transient same-route retry, prompt replay, regex retry classification, or automatic model upgrade. Nonzero exits, rate limits, timeouts, `needs_escalation`, permanent failures, artifact-limit violations, and ambiguous failures terminate the node and return evidence to root. Unrelated DAG branches continue; descendants of a non-success node are blocked. Cancellation and hard safety timeouts remain resource/termination controls.

## Workflow IR control-flow commands

使用 `skill/cli.py run-ir` 和 `resume-ir` 执行可信的只读 `agent`、`map`、`verify`、Bounded Loop v1、`reduce`、`conditional` 与 `human_gate` 控制流。未选分支默认向后传播 `skipped`；只有显式 `dependency_policy: "join"` 且至少一个依赖成功时才允许汇合。命令沿用 v2 runner 的路径预检、Codex 身份核验、artifact 限制和显式外部模型导出确认；不开放任意代码、workspace write、Git 写入、自动升级或隐藏重试。

## Condition and human-gate commands

`condition-evaluate` 只预览受限条件，不推进 checkpoint。`gate-status` 查看 run-scoped gate；`gate-decide` 必须提供 node、decision、actor、`user|host` source 与 expected input identity。decision 通过 exclusive-create 原子写入，冲突决定不能覆盖；actor/source 只是未经认证的审计标签。gate 命令不调用模型，且不会扩展授权。waiting run 的 `run-ir` 返回 paused，之后显式执行 `resume-ir`。
