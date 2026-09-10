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
| cwf_reader | Astra / selected effort (default high) | Bounded read-only raw-source analysis and independent judgment |
| cwf_writer | Astra / selected effort (default high) | Scoped implementation; inherits permissions, never grants writes |
| cwf_general | Luna / max | Optional omissions, counterexamples, test gaps and second opinions |
| cwf_mechanical | Luna / medium | Low-risk mechanical read-only work with objective checks |

Runtime 4.1.1 permits explicit Astra effort selection; reader/writer profiles no longer
pin high. Root passes route.effort through the actual native tool's effort parameter.
Check the currently exposed profile first: old sessions can still advertise fixed high.
New contracts, including legacy, reject shipped-profile model or fixed-Luna-effort conflicts.
Package validation also checks that Astra profiles do not shadow the selected effort.
Requested identity still does not prove the host used it.

These are model mappings, not built-in tools or a model quality benchmark. Cost tiers
are configured assumptions: check current availability and cost suitability. Existing
Luna/Sol/Spark profiles and global defaults remain unchanged by installation.

Select effort from uncertainty, cross-module coupling, consequence of a missed issue
and evidence quality, not the role title or number of edited lines. With no explicit
choice, high remains the package default. For straightforward, well-specified work,
low/medium may suffice; unresolved logic or edge cases can justify high, and especially
demanding reasoning may justify xhigh/max/ultra where the actual host supports them.
These are task heuristics, not measured guarantees or a requirement to try cheaper first.
Do not silently downgrade an explicit user selection. Report unsupported or inadequate
settings instead of substituting another model. Do not reconfigure the parent or global defaults.

Skill-only can select a compatible effort before the next authorized dispatch.
Runtime routes are fixed per tier when the run is created; execute route.effort from
the admitted packet. This is not a per-node escalation API. An inadequate saved route
requires disclosing the capability gap and blocking affected acceptance, not mutating
the contract or starting a new run to reset spending. Higher effort is not proof of
independence, source coverage or successful verification.

Astra owns the complete mainline by default. Do not move required investigation,
reasoning, implementation or acceptance to Luna merely because it is bounded or
read-only. For every meaningful non-trivial task, proactively use cwf_general for
at least three distinct supplemental probes when capacity permits: omissions/coverage,
counterexamples/failure modes, and missing tests/alternative explanations. These
probes add search width; they are not mainline dependencies or votes.

Use cwf_general for supplemental bounded read-only work when source access and named
checks can establish its deliverable and capability is sufficient. Examples include
scoped call-site tracing, comparing documented behavior with code, collecting test
evidence and checking a small noncritical change. A supplemental second opinion does
not become required acceptance merely because its logical role is reviewer.
In Skill-only mode, if cwf_general is not exposed, an existing luna profile may be used
only after checking compatible model/effort, source, permission and authority constraints.
With Runtime, execute the exact admitted route; a similar profile name is not substitution authority.
A missing contract profile is a capability gap, not permission to use legacy or another backend.

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
suitability. In v4 it uses the same isolated supplemental allowance; the separate
economy reserve remains available only to legacy policy. Use the
capable route for complex cross-module reasoning, uncertain security impact, high-risk
conclusions, implementation and critical independent acceptance, including writer review.
An unknown answer alone does not require Astra. Luna may gather bounded evidence
about a difficult area while Root/capable review owns its high-risk conclusions.
Unknown risk or inadequate checks require investigation or the capable route; an
unqualified task must not be labeled ordinary or mechanical merely to lower cost.

Keep required evidence collection with the complete Astra mainline. Add independent
Luna probes for extra coverage rather than removing required work from Astra. Keep
closely dependent work together when decomposition would lose context or add rework.
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

Astra reader/writer profiles already omit fixed effort; do not add a neutral profile
merely to select another supported effort. Other explicit mappings need a compatible
host and run contract, not a shadowed override. Model unavailable: retain partial
results and report the exact limitation; do not silently substitute another mapping.

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
