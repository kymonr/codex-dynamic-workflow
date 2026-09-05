# Native host and model routing

## Capability check

Use the tool schema currently exposed to the session. Inspect available profiles,
model/effort support, context inheritance options, lifecycle semantics and capacity.
Do not hard-code `fork_turns`, wait target lists or legacy feature flags from memory.
When independent context is supported, select it using that actual schema. Otherwise
report the independence limit; do not claim a blind verifier from inherited opinions.

A role file can override explicit spawn model/effort and inherit unrelated parent
settings. Resolve effective configuration before dispatch and check the execution
receipt when exposed. Never bypass approvals, sandbox, hook trust or model availability.
A read-only role is an intent/constraint; actual host controls must be inspected.

## Logical role versus execution profile

An explorer, verifier, reproducer, designer or reviewer may use the same capable
read-only execution profile. A writer needs an authorized writable task and compatible
host permissions. No logical role is permanently assigned to a cheap or strong model.

This package ships three optional profiles, installed separately from openai.yaml:

| Profile | Initial mapping | Capability contract |
|---|---|---|
| cwf_reader | Astra / high | Bounded read-only raw-source analysis and independent judgment |
| cwf_writer | Astra / high | Scoped implementation; inherits permissions, never grants writes |
| cwf_mechanical | Luna / medium | Low-risk mechanical read-only work with objective checks |

These are model mappings, not built-in tools or a model quality benchmark. Cost tiers
are configured assumptions: check current availability and cost suitability. Existing
Luna/Sol/Spark profiles and global defaults remain unchanged by installation.

Select economy only when scope is bounded, risk low, the result objectively checkable,
capability sufficient and expected rework does not erase savings. Unknown risk or
unqualified checks must not be classified as low-risk to save money. Cross-module
reasoning, uncertain security impact and critical acceptance are not mechanical work.

Cheap writing is not enabled by cwf_mechanical. A future/user-selected economy writer
must have a writer-capable profile, closed scope and evidence-backed quality checks;
never defeat an existing non-writer profile by relabeling it. No expensive fallback
outside the approved allowance. Incompatible explicit user route/model selections
are surfaced, not silently rewritten.

For an explicit supported model/effort override, use a compatible neutral profile
without conflicting fixed values, when the host supports it. Do not silently ignore
the override or pass shadowed values to a fixed profile. Model unavailable: retain
partial results, report the exact observed limitation and proposed bounded alternative.

## Lifecycle

A host may cap open threads, not only running turns. Use its actual completion/closure
contract; idle is not automatically closed and interrupt is not confirmed termination.
On capacity failure inspect once, queue eligible work, and avoid retry loops. A queued
branch remains accounted for. Never spawn past capacity or free an unconfirmed writer.
Root alone owns dispatch. No peers, child spawning or autonomous nested workflow.

## Installation and future backend

The installer requires an explicit discovered home and installation scope. Do not
infer the active home from a username or directory existence. Some hosts use user
`.agents/skills`; existing installations may use CODEX_HOME/skills. Verify discovery
on the actual client and avoid duplicate same-name skill copies.

A CLI invocation is permitted as an explicitly identified integration-test harness,
not as the skill's dispatch fallback. A future Runtime adapter needs an explicit
backend handoff and one authority/budget ledger. Persistent graph, enforcement,
automatic resume and nested orchestration are not shipped in this version.
