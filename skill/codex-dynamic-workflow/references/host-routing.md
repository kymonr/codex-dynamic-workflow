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

This package ships four optional profiles, installed separately from openai.yaml:

| Profile | Initial mapping | Capability contract |
|---|---|---|
| cwf_reader | Astra / high | Bounded read-only raw-source analysis and independent judgment |
| cwf_writer | Astra / high | Scoped implementation; inherits permissions, never grants writes |
| cwf_general | Luna / max | Ordinary bounded read-only investigation, analysis, planning and noncritical verification |
| cwf_mechanical | Luna / medium | Low-risk mechanical read-only work with objective checks |

These are model mappings, not built-in tools or a model quality benchmark. Cost tiers
are configured assumptions: check current availability and cost suitability. Existing
Luna/Sol/Spark profiles and global defaults remain unchanged by installation.

Prefer cwf_general for ordinary bounded read-only work when source access and named
checks can establish its deliverable and capability is sufficient. Examples include
scoped call-site tracing, comparing documented behavior with code, collecting test
evidence and checking a small noncritical change. Ordinary planning or review does
not automatically require Astra just because of its logical role. If cwf_general is
not exposed yet, an existing luna profile with compatible Luna/max and read-only
constraints can perform this same task; inspect the actual host profile first.

Before selecting Luna, state the deliverable and how it can be recomputed or checked
against original evidence: specified input/output cases, an enumerated source list,
or a bounded code/document comparison. Discovery may produce candidate causes,
alternative hypotheses, missing coverage or counterexamples whose answers were not
known in advance. Check the examined sources, method and evidence; preserve UNKNOWN
where discovery is inconclusive. Small scope, read-only access and low impact
do not by themselves establish that a task is easy or adequately checked.
Luna may report exact check outcomes, including "no hash differences" or "these
named cases passed". Broader claims such as "no defects", "the fix is complete" or
"ready for acceptance" need Root/capable judgment when the checks do not establish
their semantic coverage. Root retains any required capable non-author review.
Treat a clean Luna result as evidence within its checked scope; Root must examine
the coverage and residual uncertainty even when Luna reports no capability gap.

Use cwf_mechanical for low-risk mechanical work with objective checks and known cost
suitability. Its economy reserve is narrower than ordinary Luna delegation. Use the
capable route for complex cross-module reasoning, uncertain security impact, high-risk
conclusions, implementation and critical independent acceptance, including writer review.
An unknown answer alone does not require Astra. Luna may gather bounded evidence
about a difficult area while Root/capable review owns its high-risk conclusions.
Unknown risk or inadequate checks require investigation or the capable route; an
unqualified task must not be labeled ordinary or mechanical merely to lower cost.

When useful evidence work can be separated from complex judgment, assign the bounded
branch to Luna instead of absorbing it into Root or a broad Astra task. Keep closely
dependent work together when decomposition would lose context or add more rework.
Batch distinct bounded exploratory or verification directions when useful, including
large batches under the user's selected allowance. Stop on coverage/deadline or lack
of useful new directions. Avoid duplicate or trivial fragments, not unknown outcomes.
There is no fixed model ratio. Needed Astra work proceeds normally in parallel;
Luna exploration does not replace or delay a ready critical review.

If Luna returns a concrete capability gap, preserve its evidence and let Root handle
the remainder or assign one bounded capable follow-up within the existing allowance.
Account for both calls; avoid repeating the whole task or resetting budgets. Explicit
Runtime retries retain the original route and unresolved nodes; they do not implement
automatic model escalation or convert a partial result into completed evidence.

Passing routing, installation and budget tests establishes controller behavior,
not equal task quality between models. Any quality comparison must use the same
representative tasks and candidate sources, verified omissions/false findings and
rework; successful routing or additional agent count is not that comparison.

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
A host-confirmed completed readonly turn with settled tools can reconcile execution through the Runtime protocol while its host-resource reservation remains UNKNOWN. Keep execution completion and host-resource cleanup separate.
Root alone owns dispatch. No peers, child spawning or autonomous nested workflow.

## Installation and native execution

The installer requires an explicit discovered home and installation scope. Do not
infer the active home from a username or directory existence. Some hosts use user
`.agents/skills`; existing installations may use CODEX_HOME/skills. Verify discovery
on the actual client and avoid duplicate same-name skill copies.

Luna and Astra both use native host agent tools. Use the compatible native profiles
above, preserving bounded unknown-answer exploration and critical capable judgment.
Both consume native host capacity; no model label grants a slot exemption. Batch
useful Luna work as capacity allows and keep needed Astra reservations available.
On a native capacity or capability gap, queue/report the affected work. CLI model
dispatch and the former independent Luna process pool are disabled, not fallback.
Do not repeat permission questions for native batches within the task's scope/allowance.
Persistent graphs and transactional launch reservations remain optional Runtime state
management; read [Runtime protocol](runtime.md) before using its native host bridge.
