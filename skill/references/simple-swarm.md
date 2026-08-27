# Simple Swarm native mode

Simple Swarm is the default lightweight multi-agent mode for Dynamic Workflow. It directly dispatches native subagents and returns their results to the root. It is not a Workflow IR preset and does not create checkpoints, Human Gates, run directories, content-addressed artifacts, evidence ZIPs, or Writer candidates.

## Selection

Select Simple Swarm when two or more substantive, dependency-ready branches can progress independently and their concurrency or context isolation is worth the coordination cost. One branch is allowed only when the user explicitly requests a subagent or the isolated context has a clear benefit.

Stay root-only for a few simple reads, one short direct task, strongly serial work, or a request that cannot be split without overlap.

## Default envelope

- two to five children;
- six as the ordinary maximum unless the user explicitly asks for more;
- read-only by default;
- no nested delegation except the existing Sol-to-Luna rule;
- no independent reviewer unless explicitly requested;
- no Workflow IR, checkpoint, gate, loop, artifact package, attestation, or Worktree Writer.

## Smallest useful branch

A valid branch has:

- one primary question;
- one module or responsibility;
- usually no more than three primary files;
- a deliverable that can be accepted independently;
- a root-owned verification check;
- explicit exclusions and no-nesting boundary.

A repository-wide search is allowed only when the query is narrow and bounded. Otherwise partition by module. A branch that combines CLI, runtime, Writer authority, tests, and coverage is not one branch; split it.

## Overlap rule

Before dispatch, create an ownership table. Two branches must not share the same central question. Primary-file overlap should stay below roughly twenty percent. Shared entry points may be read by multiple branches, but only one branch owns the corresponding conclusion.

If overlap is material, merge the branches or re-split them. Do not rely on the root to reconcile duplicate full audits after the fact.

## Root responsibility

The root owns scope, authorization, integration, conflict resolution, and final verification. While a branch is active, the root may inspect shared entry points or complementary evidence, but it must not redo the branch's full investigation.

Root takeover is allowed after terminal failure, explicit shutdown, or a deliberate re-split. Final verification is not considered duplicate investigation.

## Dispatch and waiting

Dispatch ready branches concurrently. Use the compact work package in [work-package.md](work-package.md) and route each branch independently under [routing.md](routing.md).

Wait once for normal completion. If a child is still active, request one concise progress or partial result when supported. If it still cannot provide useful work, shut it down and either re-split the task or return the remaining work to root. Repeated waits that block the whole answer are a delegation failure.

## Delivery and adoption

Each child returns:

- conclusion;
- supporting sources or code locations;
- uncertainty;
- blocker or remaining work.

The root records whether the result was adopted, partially adopted, rejected, or replaced by takeover. Dispatch count is not a success metric. A swarm succeeds when adopted child results shorten delivery and root duplication remains limited to verification or conflict resolution.

## Escalation to advanced modes

Use Managed Workflow only when the user explicitly needs checkpoint/resume, Human Gate, bounded loop, conditional persistence, reproducible task artifacts, or a long-running workflow.

Use Worktree Writer only when the user explicitly requests an isolated write candidate or invokes that flow. An ordinary request to analyze, review, inspect, or audit never activates Writer.
