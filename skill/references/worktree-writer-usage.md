# Worktree Writer v1 operations

Worktree Writer v1 is an explicit candidate-production path. It is not a Workflow IR node, is not selected by Auto Planner, and is never entered by Bounded Loop. Its terminal result is an isolated candidate package; it never applies, commits, pushes, merges, releases, or deploys that candidate.

The authoritative safety contract is [worktree-writer-v1.md](worktree-writer-v1.md). The machine-checked policy is `config/worktree-writer-policy.toml`.

## Prerequisites

Set repository-external roots before any operation:

```powershell
$env:DYNWF_RUNS_ROOT = 'D:\codex-tmp\dynamic-workflow-runs'
$env:DYNWF_WORKTREE_ROOT = 'D:\codex-tmp\dynamic-workflow-worktrees'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP ('dynwf-writer-' + [guid]::NewGuid().ToString('N'))
```

`DYNWF_WORKTREE_ROOT` must already exist, must be a real directory, and must not overlap the canonical repository, runs root, or `CODEX_HOME`.

Prepare a closed package from `examples/worktree-writer-package.json`, replacing the repository identity and exact 40-character base HEAD/tree values. Compute the canonical package digest with the contract parser; do not use the file-byte SHA as a substitute.

## Zero-model preview

```powershell
python skill\cli.py writer-plan `
  --package '<PACKAGE_JSON>' `
  --repository '<CLEAN_CANONICAL_REPOSITORY>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>'
```

A successful preview reports:

- `model_calls=0`;
- `writes=[]`;
- no run directory and no worktree;
- exact repository HEAD/tree and origin identity;
- the exclusive writer lock path and availability;
- native Codex identity and required CLI features;
- the fixed Luna writer and fresh Sol reviewer routes;
- shell, code mode, multi-agent, web search, and network disabled.

Planning reads Git and filesystem identity metadata. It does not open owned-file contents. UTF-8, NUL, LFS, binary, size, and patch checks occur after the isolated writer has produced a candidate.

## Execute one isolated candidate run

```powershell
python skill\cli.py writer-run `
  --package '<PACKAGE_JSON>' `
  --repository '<CLEAN_CANONICAL_REPOSITORY>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>' `
  --expected-head-sha '<40_LOWERCASE_HEX>' `
  --ack-isolated-worktree-write
```

The acknowledgement authorizes only the exact package in one host-created detached worktree. The writer receives one Luna attempt with workspace-write limited to the isolated worktree. The shell and code-mode tools are disabled, so the only intended editing surface is `apply_patch`; network and nested agents are disabled. Host reconciliation, not model self-report, decides which effects occurred.

After an authorized candidate and all fixed validations pass, the runtime freezes the candidate and starts one separate read-only Sol process. The reviewer cannot fix files. Its verdict maps to one of:

- `ship_candidate`;
- `fix_first`;
- `rethink`.

All three preserve the isolated candidate and perform no canonical apply or Git publication action.

Any unauthorized path/action, delete, rename, mode change, binary/NUL/LFS payload, symlink/reparse point, staged/index/ref/config/HEAD/object mutation, validation-created source change, reviewer effect, stale revision, malformed output, or interrupted non-idempotent writer attempt fails closed and preserves evidence. The same writer attempt is never replayed automatically.

## Read-only integrity query

```powershell
python skill\cli.py writer-status --run-dir '<RUN_DIR>'
```

The command validates checkpoint, event sequence, summary, candidate revision, patch and captured-file identities. It performs no model call and must not alter file SHA, size, or mtime.

## Export the candidate

```powershell
python skill\cli.py writer-export --run-dir '<RUN_DIR>'
```

The command emits the immutable candidate package, deterministic patch, and bounded base64 file contents. It does not apply the patch.

## Explicit cleanup

```powershell
python skill\cli.py writer-cleanup `
  --run-dir '<RUN_DIR>' `
  --expected-run-id '<RUN_ID>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>' `
  --ack-delete-isolated-worktree
```

Cleanup is host-only. It requires a terminal run, no active process, a captured candidate, exact run/package/lock/worktree identity, and an unchanged canonical repository. It removes only the isolated Git worktree and exclusive writer lock. Run evidence remains.

## Exit behavior

- `0`: preview/query/export/cleanup succeeded, or the writer run reached `ship_candidate`, `fix_first`, or `rethink`;
- `1`: input, capability, identity, integrity, or command failure before a trusted writer terminal summary;
- `2`: writer run terminated as `validation_failed`, `effect_violation`, or `attention_required`;
- `130`: writer run terminated as cancelled.

A nonzero writer-run exit must not trigger an automatic retry. Inspect `writer-status`, the isolated worktree, and retained evidence first.
