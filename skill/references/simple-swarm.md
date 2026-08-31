# Simple Swarm contract

Simple Swarm is the default Dynamic Workflow mode for ordinary multi-branch work:

```text
decompose → dispatch → collect → integrate → finish
```

It does not create Workflow IR, checkpoints, resume state, Human Gates, bounded loops, native Agent Fleet phases, formal evidence packages, or Worktree Writer runs.

## Activation

Implicit activation requires at least two branches that are:

- substantive;
- dependency-ready;
- separately useful;
- non-overlapping enough to progress independently;
- cheaper to coordinate than to execute serially at root.

A single implicit branch stays with root. An explicit `$dynamic-workflow` invocation or explicit request for a subagent may dispatch one bounded branch.

Default child count is 2–6. More than 6 requires an explicit user request or Managed Workflow. The hard Simple Swarm ceiling is 8. A deep, comprehensive, adversarial, multi-agent, or challenge-and-reproduction review uses native Agent Fleet instead of widening Simple Swarm. An ordinary four-branch review with no such requirement remains Simple Swarm. Agent Fleet itself supports only total sizes 4, 6, and 8.

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

Simple Swarm forbids nested delegation. If a branch needs its own decomposition, return it to root for re-splitting or use Managed Workflow. If the user wants deep coordinated review with discovery, challenge, reproduction, and Sol judgment, use the native contract in [agent-fleet.md](agent-fleet.md) rather than nesting inside a Simple Swarm child.

## Waiting

Coordination waits are bounded and event-driven only to keep Root responsive; they are not a child lifecycle budget or deadline.

1. Start a bounded event-driven wait.
2. After the first timeout, allow at most one non-interrupting request for a partial result or progress signal.
3. If the child is healthy, continue with longer bounded waits and useful user updates; do not repeat progress prompts or status polling.
4. A later timeout, wait count, or silence alone never authorizes interrupt, close, re-split, reroute, replay, or duplicate execution. Let a healthy child finish naturally.

Terminal and hard-stop conditions follow [dag.md](dag.md). Use the native cancellation or close primitive only for the explicit cancellation, scope revocation, identity mismatch, unauthorized/external/destructive/credential effect, or imminent safety conditions described there, and reconcile actual effects after a hard stop. Temporarily slow but healthy work remains Simple. Managed Workflow is for checkpoint/resume, Human Gate, conditional flow, bounded loops, persistent long-running recovery, or formal artifacts—not merely for needing more than two waits. Live behavior beyond two waits is unproven and remains `UNKNOWN`; this contract does not claim executable liveness.

## Adoption

Every child ends as adopted, partially adopted, not adopted, failed, or cancelled. The root must know which child evidence affected the final answer.

Success metrics are useful result adoption, less duplicate work, lower total delivery time, and independent evidence quality. Dispatch count is not a success metric.

## Writes

Read-only is the default.

When the user explicitly asks for implementation, Simple Swarm may use one scoped native writer while other branches remain read-only. Sol is the default writer; an explicit supported native model selection takes precedence, so user-selected Luna may be the one scoped writer. Grok never writes. The root must not write the same targets concurrently.

Worktree Writer v2 is a different explicit mode. A normal implementation request does not automatically authorize it.

## Final output

The root integrates all adopted results and gives one answer. Keep routing telemetry brief:

```text
<branch> -> <route> -> <status>
```

Do not include checkpoint, digest, gate, or Writer terminology unless those advanced modes were actually selected.
