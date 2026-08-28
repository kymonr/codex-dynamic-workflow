# Worktree Writer v2 operations

Worktree Writer v2 is an explicit candidate-production path. It is not a Workflow IR node, is not selected by Auto Planner, and is never entered by Bounded Loop. Its terminal result is an isolated candidate package; it never applies, commits, pushes, merges, releases, or deploys that candidate.

The authoritative extension contract is [worktree-writer-v2.md](worktree-writer-v2.md). The original Luna-only design remains available as the historical [worktree-writer-v1.md](worktree-writer-v1.md). Machine-checked settings live in `config/worktree-writer-policy.toml`.

## Trusted writer profiles

The host, not the package or model, selects exactly one immutable profile:

| Profile | Writer | Package versions | Hard scope |
| --- | --- | --- | --- |
| `bounded-luna` | Luna / max / fast | v1 or v2 | at most 2 owned targets and 2 changed files |
| `complex-sol` | Sol / xhigh | v2 only | at most 8 owned targets and 8 changed files |

`bounded-luna` is the default and is intended for short, well-specified, low-risk edits. `complex-sol` is explicit and intended for nontrivial cross-module behavior changes that still fit a bounded isolated candidate.

Both profiles retain one writer, one attempt, `retry=0`, no upgrade, no nested agents, no shell tool, no code mode, no network, and the same create/modify-only effect boundary. A profile never grants commit, push, merge, publication, deployment, cleanup, credentials, or external write authority.

Profile identity, route, accepted package versions, and hard budgets are copied from the trusted registry into the plan, authorization, exclusive lock, checkpoint, candidate package, and candidate revision. Changing the profile produces a different candidate revision.

## Package versions

Package v1 remains accepted only through `bounded-luna` compatibility. It contains the original objective, base, authority, limits, and fixed verification fields.

Package v2 adds digest-bound quality context:
- `acceptance_criteria` — at least one concrete condition;
- `constraints` — invariants the implementation must preserve;
- `non_goals` — nearby work that must remain out of scope;
- `behavior.before` and `behavior.after` — the intended observable transition;
- `implementation_context.relevant_symbols` and `analysis_summary` — bounded navigation and reasoning context.

These fields are task data, never authority. Their canonical UTF-8 total is capped at 128 KiB, and they cannot add owned targets, actions, writable roots, tools, credentials, or effects. `complex-sol` requires v2; examples are in `examples/worktree-writer-complex-package-v2.json`.

Runtime v2 produces v2 evidence. Package-v1 compatibility does not rewrite or migrate preserved v1 run artifacts; keep those artifacts immutable and use the matching v1 release for legacy status or cleanup operations.

## Prerequisites

Set repository-external roots before any operation:

```powershell
$env:DYNWF_RUNS_ROOT = 'D:\codex-tmp\dynamic-workflow-runs'
$env:DYNWF_WORKTREE_ROOT = 'D:\codex-tmp\dynamic-workflow-worktrees'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP ('dynwf-writer-' + [guid]::NewGuid().ToString('N'))
```

`DYNWF_WORKTREE_ROOT` must already exist, must be a real directory, and must not overlap the canonical repository, runs root, or `CODEX_HOME`.

Prepare a closed package from the v1 or v2 example, replacing the repository identity and exact 40-character base HEAD/tree values. Compute the canonical package digest with the contract parser; do not use the file-byte SHA as a substitute.

## Zero-model preview

Default bounded Luna preview:
```powershell
python skill\cli.py writer-plan `
  --package '<PACKAGE_JSON>' `
  --repository '<CLEAN_CANONICAL_REPOSITORY>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>'
```

Explicit complex Sol preview:

```powershell
python skill\cli.py writer-plan `
  --package '<V2_PACKAGE_JSON>' `
  --repository '<CLEAN_CANONICAL_REPOSITORY>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>' `
  --writer-profile complex-sol
```

A successful preview reports:

- `model_calls=0` and `writes=[]`;
- no run directory and no worktree;
- exact repository HEAD/tree and origin identity;
- the selected trusted profile, route, budgets, and package-version gate;
- the exclusive writer lock path and availability;
- native Codex identity and required CLI features;
- the fresh Sol reviewer route;
- shell, code mode, multi-agent, web search, and network disabled.

Planning reads Git and filesystem identity metadata. It does not open owned-file contents. UTF-8, NUL, LFS, binary, size, and patch checks occur after the isolated writer has produced a candidate.

## Execute one isolated candidate run

Use the same profile that passed preview. Omitting `--writer-profile` selects `bounded-luna`.

```powershell
python skill\cli.py writer-run `
  --package '<PACKAGE_JSON>' `
  --repository '<CLEAN_CANONICAL_REPOSITORY>' `
  --expected-package-digest '<CANONICAL_PACKAGE_SHA256>' `
  --expected-head-sha '<40_LOWERCASE_HEX>' `
  --writer-profile complex-sol `
  --ack-isolated-worktree-write
```

The acknowledgement authorizes only the exact package and selected profile in one host-created detached worktree. The profile chooses the writer model and hard limits; it does not expand the package authority. Host reconciliation, not model self-report, decides which effects occurred.

After an authorized candidate and all fixed validations pass, the runtime freezes the candidate and starts one fresh read-only Sol process. The reviewer cannot fix files. Its verdict maps to one of:

- `ship_candidate`;
- `fix_first`;
- `rethink`.

All three preserve the isolated candidate and perform no canonical apply or Git publication action. `fix_first` and `rethink` terminate the automatic lifecycle; a revision requires a new explicit package/run.

For `complex-sol`, writer and reviewer use the same model family but separate fresh processes, prompts, sandboxes, and authorities. This is process and artifact independence, not model-family diversity. Deterministic host validation and exact revision binding remain mandatory.

Any unauthorized path/action, delete, rename, mode change, binary/NUL/LFS payload, symlink/reparse point, staged/index/ref/config/HEAD/object mutation, validation-created source change, reviewer effect, stale revision, malformed output, profile mismatch, or interrupted non-idempotent writer attempt fails closed and preserves evidence. The same writer attempt is never replayed automatically.

## Read-only integrity query

```powershell
python skill\cli.py writer-status --run-dir '<RUN_DIR>'
```

The command validates checkpoint, event sequence, summary, selected profile, authorization, lock, process identity, candidate revision, patch, and captured-file identities. It performs no model call and must not alter file SHA, size, or mtime.

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

Cleanup is host-only. It requires a terminal run, no active process, a captured candidate, exact run/package/profile/lock/worktree identity, and an unchanged canonical repository. It removes only the isolated Git worktree and exclusive writer lock. Run evidence remains.

## Exit behavior

- `0`: preview/query/export/cleanup succeeded, or the writer run reached `ship_candidate`, `fix_first`, or `rethink`;
- `1`: input, profile, capability, identity, integrity, or command failure before a trusted writer terminal summary;
- `2`: writer run terminated as `validation_failed`, `effect_violation`, or `attention_required`;
- `130`: writer run terminated as cancelled.

A nonzero writer-run exit must not trigger an automatic retry. Inspect `writer-status`, the isolated worktree, and retained evidence first.
