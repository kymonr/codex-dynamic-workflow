# Simple Swarm contract

Simple Swarm is the default Dynamic Workflow mode for ordinary multi-branch work:

```text
decompose → dispatch → collect → integrate → finish
```

It does not create Workflow IR, checkpoints, resume state, Human Gates, bounded loops, formal evidence packages, or Worktree Writer runs.

## Activation

Implicit activation requires at least two branches that are:

- substantive;
- dependency-ready;
- separately useful;
- non-overlapping enough to progress independently;
- cheaper to coordinate than to execute serially at root.

A single implicit branch stays with root. An explicit `$dynamic-workflow` invocation or explicit request for a subagent may dispatch one bounded branch.

Default child count is 2–6. More than 6 requires an explicit user request or Managed Workflow. The hard Simple Swarm ceiling is 8.

## Smallest useful branch

A branch should normally have:

- one objective;
- one primary responsibility;
- one module or 1–3 primary files;
- one concrete deliverable;
- one root-verifiable acceptance check.

Reading adjacent context is allowed only when it directly supports that objective. Do not package CLI, runtime, Writer authority, security, tests, and coverage into one child merely because they belong to the same repository.

When a proposed branch spans multiple independent questions, split it before dispatch.

## Non-overlap

Active branches should not substantially duplicate files, evidence, or judgment.

The root may work on decomposition, integration, uncovered scope, conflict resolution, and independent acceptance checks. The root must not repeat an active child’s investigation “just in case”.

If two branches would inspect the same primary files for the same question, merge them or give them different evidence questions.

## Dispatch packet

Use the compact packet in [work-package.md](work-package.md). A read-only Simple Swarm packet needs only:

1. objective;
2. bounded scope;
3. deliverable;
4. verification;
5. exclusions.

Do not require a JSON authority manifest for read-only work.

Simple Swarm forbids nested delegation. If a branch needs its own decomposition, return it to root for re-splitting or use Managed Workflow.

## Waiting

1. Start one bounded event-driven wait.
2. After the first timeout, request one partial result or progress signal.
3. Wait once more.
4. If the second wait produces no useful delivery and the branch blocks completion, close it and re-split, return the scope to root, or report it `UNKNOWN`.

Do not poll repeatedly. Long-running work that legitimately needs multiple wait cycles belongs in Managed Workflow.

## Adoption

Every child ends as adopted, partially adopted, not adopted, failed, or cancelled. The root must know which child evidence affected the final answer.

Success metrics are useful result adoption, less duplicate work, lower total delivery time, and independent evidence quality. Dispatch count is not a success metric.

## Writes

Read-only is the default.

When the user explicitly asks for implementation, Simple Swarm may use one scoped native writer while other branches remain read-only. The root must not write the same targets concurrently.

Worktree Writer v2 is a different explicit mode. A normal implementation request does not automatically authorize it.

## Final output

The root integrates all adopted results and gives one answer. Keep routing telemetry brief:

```text
<branch> -> <route> -> <status>
```

Do not include checkpoint, digest, gate, or Writer terminology unless those advanced modes were actually selected.
