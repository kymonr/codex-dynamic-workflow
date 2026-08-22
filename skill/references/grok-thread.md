# Explicit Grok conversation task

Use this path only when the user explicitly asks to create, open, or start a separate Grok conversation task. It is a visible user-owned task, not a native subagent, reviewer, or recovery route. Complexity, latency, provider failure, or a model preference inferred by the root never creates one.

## Creation

Use the Codex task-creation capability with model `xai/grok-4.6`. Keep reasoning effort at the task default unless the user specifies it.

When Grok is the only writer, use a separate worktree for Git project writing by default; an explicit user request may instead select the saved project directly. Listed files are primary entry points rather than an exhaustive edit allowlist, so Grok may inspect callers and dependencies, edit necessary adjacent files within the authorized goal, choose its tools, add focused verification, and use helpful temporary analysis artifacts. Temporary artifacts should not remain in the final change unless they are useful deliverables.

When a native writer runs at the same time, isolation becomes mandatory: both writers use separate worktrees and receive disjoint closed `owned_targets` before either starts. The closed targets must include any allowed temporary-artifact directory. Grok must not edit outside its targets; if an adjacent change becomes necessary, it stops and asks the root to serialize the work or reassign ownership before continuing. An explicit request to use the saved project directly does not override concurrent isolation. Overlapping or non-Git writing remains serial, and the root never writes the same targets concurrently.

## Broad handoff

Give Grok the outcome, primary scope, current authorization and safety boundary, and a checkable completion standard. In serial mode, preserve the broad method freedom above. In concurrent mode, include the closed target manifest and isolation rule instead of implying adjacent-file freedom.

Keep hard boundaries narrow: preserve unrelated work; leave credentials, destructive actions, external writeback, commit, push, publication, merge, and deployment to the root; stop when the requested outcome or authorization materially changes.

Ask the thread to finish with the achieved outcome, actual files changed, verification results, remaining risks, and explicit `UNKNOWN`. The root verifies and integrates its effects but does not treat silence or elapsed time as a native-child failure, does not advance it through the native route DAG, and does not interrupt it merely to request a summary.
