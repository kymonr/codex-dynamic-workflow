# Worktree Writer v2 operations

Worktree Writer v2 is an explicit isolated-candidate path. It is not a Workflow IR node, is not selected by Auto Planner, and is never entered by Bounded Loop. It never applies, commits, pushes, merges, releases, or deploys a candidate.

The current runtime has one host-fixed execution shape:

```text
package v2
→ fixed Sol / high writer
→ host effect reconciliation
→ fixed validation
→ immutable candidate
→ fresh read-only Sol / xhigh reviewer
```

The writer route is not selectable by the package, CLI, repository text, model output, or reviewer. The machine-checked settings are in `config/worktree-writer-policy.toml`; the design contract is [worktree-writer-v2.md](worktree-writer-v2.md).

## Fixed writer boundary

The writer is always:

- role `sol`;
- model `gpt-5.6-sol`;
- reasoning effort `high`;
- `workspace-write` in one host-created detached worktree;
- one attempt, `retry=0`, no upgrade and no nested agents;
- shell tool, code mode, web search and network disabled.

The hard package ceiling is 8 owned targets, 8 changed files, a 512 KiB patch, a 256 KiB created file and 2 MiB total candidate content. These are ceilings, not recommended task width; ordinary packages should stay narrower.
## Package v2

Prepare a closed package from `examples/worktree-writer-package.json`. Replace the repository identity and exact 40-character base HEAD/tree values, then compute the canonical package digest with the contract parser rather than hashing the JSON file bytes.

Package v2 requires:

- `acceptance_criteria`;
- `constraints`;
- `non_goals`;
- `behavior.before` and `behavior.after`;
- `implementation_context.relevant_symbols` and `analysis_summary`;
- exact base identity, authority, limits and fixed verification commands.

The quality context is canonical-digest-bound task data. It can improve implementation quality but cannot add owned targets, actions, writable roots, tools, credentials or effects. Its canonical UTF-8 size is capped at 128 KiB.

The v2 runtime does not accept package v1. Historical v1 run artifacts remain immutable and should be queried with the matching v1 release rather than silently migrated.

## Prerequisites

Set repository-external roots before any operation:

```powershell
$env:DYNWF_RUNS_ROOT = 'D:\codex-tmp\dynamic-workflow-runs'
$env:DYNWF_WORKTREE_ROOT = 'D:\codex-tmp\dynamic-workflow-worktrees'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP ('dynwf-writer-' + [guid]::NewGuid().ToString('N'))
```
`DYNWF_WORKTREE_ROOT` must already exist and must not overlap the canonical repository, runs root or `CODEX_HOME`.

## Zero-model preview

```powershell
python skill\cli.py writer-plan `
  --package '<PACKAGE_JSON>' `
  --repository '<CLEAN_CANONICAL_REPOSITORY>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>'
```

A successful preview reports zero model calls and zero writes, exact base and origin identity, lock availability, Codex capability evidence, the fixed Sol/high writer route and the fresh Sol/xhigh reviewer route.

The fixed writer binding contains the exact route, package version and hard budgets. It is copied into authorization, lock, checkpoint, candidate package and candidate revision. Any mismatch fails closed.

## Execute one isolated candidate

```powershell
python skill\cli.py writer-run `
  --package '<PACKAGE_JSON>' `
  --repository '<CLEAN_CANONICAL_REPOSITORY>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>' `
  --expected-head-sha '<40_LOWERCASE_HEX>' `
  --ack-isolated-worktree-write
```

The acknowledgement authorizes only the exact package in one host-created detached worktree. Host reconciliation, not model self-report, determines the actual effects.
Only declared UTF-8 text targets may be created or modified. Delete, rename, mode change, binary/NUL/LFS content, links/reparse points, Git metadata mutation, external writes and credentialed actions fail closed.

After every declared verification passes, the runtime freezes the candidate and starts one separate fresh read-only Sol/xhigh process. The reviewer cannot fix files. Writer and reviewer use the same model family, so this is process, prompt, sandbox, authority and artifact independence—not model-family diversity.

The reviewer returns one terminal verdict:

- `ship_candidate`;
- `fix_first`;
- `rethink`.

All three preserve the isolated candidate and perform no canonical apply or Git publication action. `fix_first` does not start an automatic revision loop.

## Read-only status and export

```powershell
python skill\cli.py writer-status --run-dir '<RUN_DIR>'
python skill\cli.py writer-export --run-dir '<RUN_DIR>'
```

`writer-status` revalidates the checkpoint, journal, fixed writer binding, authorization, lock, process identity, effect manifest, validation evidence, candidate revision, patch, captured files and reviewer record. It performs no model call and must not modify evidence.

`writer-export` emits the immutable candidate package, deterministic patch and bounded base64 file contents. It does not apply the candidate.

## Explicit cleanup

```powershell
python skill\cli.py writer-cleanup `
  --run-dir '<RUN_DIR>' `
  --expected-run-id '<RUN_ID>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>' `
  --ack-delete-isolated-worktree
```

Cleanup requires a terminal run, no active process, captured candidate evidence, exact run/package/binding/lock/worktree identity and an unchanged canonical repository. It removes only the isolated worktree and exclusive writer lock; run evidence remains.

## Exit behavior

- `0`: preview, query, export or cleanup succeeded, or the run reached `ship_candidate`, `fix_first` or `rethink`;
- `1`: input, capability, identity, integrity or command failure before a trusted terminal summary;
- `2`: `validation_failed`, `effect_violation` or `attention_required`;
- `130`: cancelled.

A nonzero writer run must not trigger an automatic retry. Inspect `writer-status`, the preserved worktree and retained evidence first.
