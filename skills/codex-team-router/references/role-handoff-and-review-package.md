# Role Handoff And Review Package

This reference is part of the Team Router contract. `SKILL.md` is the short entrypoint; keep roleHandoffPolicy and reviewPackagePolicy details here.

## roleHandoffPolicy

Role requests should hand off stable facts by file/path when available, not by accumulated chat history. Manager prompts should stay short and include only:

- `taskId`
- objective
- expected marker
- permission boundary
- relevant package/report paths
- explicit protocol return format

Small/simple tasks may use inline protocol blocks only.

High-risk Team Router self changes, reviewer-gate/process/policy changes, and long executor results should use a review package or report path when role threads can access the same workspace/path.

If a role thread cannot access the same filesystem/path, inline protocol block fallback is allowed. The manager must mark the fallback and keep protocol fields exact.

Optional path concepts for future runtime work are `taskBriefPath`, `executorReportPath`, and `reviewPackagePath`. They are policy concepts/future optional runtime fields in this task, not implemented runtime fields.

## reviewPackagePolicy

A review package is the preferred evidence bundle for reviewer/verifier on high-risk work. Minimum content:

- `taskId`
- objective
- scope
- touched/accepted files
- diff summary
- executor callback/report
- test/verification evidence
- reviewer requiredChanges when present
- excluded unrelated untracked
- risks/remainingTodos

Reviewer should inspect package plus focused diff/evidence instead of reconstructing facts from parent chat history.

Verifier should check executor callback, reviewer result if present, package evidence, permission boundary, accepted files, excluded untracked, and final user-facing closeout.

The final protocol marker remains required. The package supplements evidence; it does not replace `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT`.

## Policy Links

sideEffectTaxonomy: creating or reading package metadata is `READ_ONLY` or `DISPATCH_ONLY` when it only prepares routing metadata. Writing workspace package artifacts is `WORKSPACE_WRITE` and should be executor work in active Manager Mode unless there is an explicit role switch.

Manager Mode: manager must not create implementation artifacts itself under active Manager Mode. It can prepare dispatch metadata and ask executor to produce reports/packages.

roleCloseoutPolicy: final protocol block is still closeout; no extra closeout messages by default.

Progressive disclosure: deep details live in references and are part of the Team Router contract.

Runtime note: `taskBriefPath`, `executorReportPath`, and `reviewPackagePath` may become optional runtime fields later, but this policy does not implement adapter/state-machine behavior.

Commit closeout risk: when committing after policy/reference splits, manager must stage new reference files explicitly, because `git diff --name-only` omits untracked files.
