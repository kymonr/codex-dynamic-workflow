# Explicit Grok second-review conversation

Use this path only when the user explicitly asks to create, open, or start a separate Grok second-review conversation after a candidate is frozen. It is a visible user-owned read-only task, not a native subagent, writer, native reviewer, fallback, or recovery route. Complexity, latency, provider failure, or a model preference inferred by the root never creates one.

## Creation

Use the Codex task-creation capability with model `xai/grok-4.6`. Keep reasoning effort at the task default unless the user specifies it. Supply the frozen candidate revision, bounded review question, relevant evidence, and a checkable review deliverable. The task has no file, Git, runtime, or external write authority.

## Broad handoff

Give Grok the frozen candidate, review objective, primary scope, safety boundary, and a checkable completion standard. It may inspect relevant callers and evidence but must remain read-only.

Keep hard boundaries narrow: preserve unrelated work; leave implementation, credentials, destructive actions, external writeback, commit, push, publication, merge, and deployment to the root; stop when the requested outcome or authorization materially changes.

Ask the task to finish with findings, supporting evidence, remaining risks, and explicit `UNKNOWN`. The root independently verifies and decides whether to adopt the second opinion; Grok never performs final native acceptance. Silence or elapsed time is not a native-child failure, and the task never enters the native route DAG.
