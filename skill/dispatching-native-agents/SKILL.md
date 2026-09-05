---
name: dispatching-native-agents
description: "Deprecated compatibility alias for Codex Dynamic Workflow. Use only when an older prompt explicitly invokes $dispatching-native-agents; canonical workflows use $codex-dynamic-workflow."
metadata:
  version: "2.0.2-compat"
---

# Deprecated compatibility alias

`$dispatching-native-agents` has been renamed to `$codex-dynamic-workflow`.

Do not run a second independent workflow from this alias. If the canonical
`codex-dynamic-workflow` Skill is available, hand this task to that Skill and follow
its current raw-source-first, authorization, budget, routing, write and completion
contracts. Preserve the user's exact scope and permissions during the handoff.

If the canonical Skill is not available in the current runtime catalog, report that
the migration is incomplete. Do not fall back to CLI children, the old JavaScript
runtime, retired `$dynamic-workflow`, or another backend.

This alias is explicit-only and must not be selected implicitly.
