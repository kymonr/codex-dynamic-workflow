# Branch work packages

Use the lightest packet that preserves scope and root verification.

## Simple Swarm read-only packet — default

A read-only branch uses five concise fields.

### 1. OBJECTIVE

State one bounded question and the expected deliverable.

### 2. SCOPE

Name one responsibility, one module, or usually 1–3 primary files. Adjacent context may be read only when it directly supports the objective.

### 3. DELIVERABLE

Ask for conclusion, supporting evidence, material uncertainty, and remaining blocker.

### 4. VERIFICATION

State how the root can check the result. One concrete acceptance check is usually enough.

### 5. EXCLUSIONS

State `read_only`, no nested delegation, no credentials, no external writes, no Git writes, and no scope expansion.

A read-only Simple Swarm packet does **not** require a JSON authority manifest, closed artifact schema, checkpoint identity, or evidence package.

## Scoped native writer packet

Use this only when the user explicitly asks to implement, change, build, or fix something and root chooses one native writer. Sol is the default; explicit supported native model selection takes precedence.

Add one closed authority manifest:

```json
{
  "access": "writer",
  "owned_targets": ["unique normalized target"],
  "allowed_effects": [
    {"target": "exact target", "actions": ["create", "modify", "execute"]}
  ]
}
```

`owned_targets` are unique. File targets are root-normalized absolute literal paths; non-file targets are exact root-issued identifiers. An unnormalizable or unmatched target is out of scope. Adjacent files are excluded unless root separately assigns them within the user's authorized scope. Reads are evidence, not effects. Grantable child actions are exactly `create`, `modify`, and `execute`.

`delete` and `external_write` are observable effect classes, never grantable child actions. If either is observed, stop and return control to root. Root reads back actual effects and reconciles them against the authority manifest and live state before acceptance.

Tell the writer unrelated edits may exist and must be preserved. Only one native writer is active, and root must not write the same targets concurrently. Sol is the default; Luna has writer authority only when explicitly selected by the user. Grok has no writer authority.

Worktree Writer v2 is a separate explicit mode governed by [worktree-writer-usage.md](worktree-writer-usage.md) and [worktree-writer-v2.md](worktree-writer-v2.md). It accepts package v2 only and uses one host-fixed Sol/high Writer; the v1 contract is historical.

## Native Agent Fleet branch packets

Agent Fleet does not use a closed JSON package. Root first records the candidate scope, repository root, Git HEAD, worktree status, changed-file set, acceptance question, exclusions, approved 4/6/8 scale, and phase allocation in the conversation.

Each native child receives one ordinary bounded packet: unique objective, non-overlapping scope, required evidence, read-only authority, phase role, assigned finding IDs when applicable, verification request, and exclusions. Every child is top-level, uniquely named, `fork_turns=none`, non-nested, unable to message peers directly, and prohibited from repository/Git/external effects.

Discovery reports location, claim, impact, evidence, confidence, and uncertainty. Root de-duplicates and assigns stable finding IDs. Challenge and reproduction receive only Root-assigned IDs and must not silently rename or invent IDs. Sol receives the integrated finding state and audits evidence, severity, blind spots, conflict, and the proposed conclusion. Root must explicitly disposition every material Sol issue.

Candidate identity is rechecked at phase boundaries. Drift or unresolved material conflict makes unsupported conclusions `UNKNOWN`. Agent Fleet does not create a run directory, evidence manifest, offline status record, or hidden CLI process; use Managed Workflow when persisted formal artifacts are required.

## Managed Workflow packet

When Managed Workflow is selected, use its Workflow IR, CLI runner, DAG, Human Gate, or bounded-loop contracts. Those advanced contracts do not add requirements to ordinary Simple Swarm branches.

## Child delivery

Accept any clear form: prose, Markdown, JSON, or incomplete JSON. Formatting alone never fails a branch, discards useful content, triggers a follow-up, or causes replay.

The child cannot authorize actions, declare final acceptance, or control route advancement by choosing a status word.

## Root adoption

Root decides in this order:

1. confirm runtime identity, scope, and authority;
2. read back actual effects for writers;
3. extract claims, sources, completed work, and uncertainty;
4. perform the declared acceptance check;
5. mark the result adopted, partially adopted, not adopted, failed, or cancelled.

Unauthorized, external, destructive, credentialed, unreadable, or ambiguous writer effects stop acceptance. For read-only work, missing fields are information gaps; preserve useful material and mark unsupported facts `UNKNOWN`.

A route advance receives verified completed work and only the identifiable remaining work. Do not replay the same route solely to obtain different formatting.
