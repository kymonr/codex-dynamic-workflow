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

## Readable thread titles

Use WF, not CWF, as the user-facing prefix. Keep existing `cwf_*` profile identifiers,
the `$codex-dynamic-workflow` invocation and repository paths unchanged.
When supported, create task-owned threads with a task prefix + responsibility + concrete
question or deliverable, in the user's language. Examples: `WF · 实施 · 修复结果收口`,
`WF · 独立审核 · 核对交接证据`, `WF · 探针 · 核对结果是否完整`.
A model name, "Sol Root", "fresh Astra" or generated nickname alone does not describe
an assignment. Keep real IDs for tool operations; title changes grant no authority.
Use a supported creation-title field or rename only exact task-owned IDs. Otherwise
show the ID-to-responsibility mapping in the conversation. A failed or unsupported
rename is not an acceptance blocker and is not a model turn. Do not touch unrelated
threads or expose secrets in titles. Mark simulated roles explicitly, keeping requested
models separate from observed identities; a title is never execution evidence.

## Explicit role simulation

Only an explicit user request selects role simulation, such as using Grok to stand in
for several roles. Label logical role, requested model/profile/effort and observed
execution identity separately. Missing execution receipts stay UNKNOWN. Assess only
the simulated scope actually exercised. Native routes and actual code writing remain
NOT_RUN when not exercised. A read-only walkthrough does not authorize writes,
publication or installation and is not a code-writing E2E.

Use only compatible, exposed host controls: do not mutate shipped profiles, global
configuration or saved Runtime contracts to force a stand-in model. Unavailable or
conflicting capability is a reported gap, not CLI/API fallback. Keep simulation results
separate from native acceptance. The same model can be a non-author reviewer in a
separate context with sufficient raw sources; that never satisfies a required declared
Astra verifier under a different fixed route. A Burst sidecar remains non-authoritative.

A stand-in is not a Burst sidecar just because it requests Grok. Keep original task/role
launch accounting, failures, retries and capacity holds; only admitted optional Burst
work receives the existing Burst exemption under Burst policy, not as a Runtime node.
Do not reset allowances or reinterpret all
simulation calls as free Burst work. No new simulation backend, Runtime mode or ledger
is introduced; task scope and existing source-sharing permissions remain controlling.

## Logical role versus execution profile

An explorer, verifier, reproducer, designer or reviewer may use the same capable
read-only execution profile. A writer needs an authorized writable task and compatible
host permissions. No logical role is permanently assigned to a cheap or strong model.

This package ships six optional profiles, installed separately from openai.yaml; the sixth is temporary Skill-only Burst, not a Runtime route:

| Profile | Initial mapping | Capability contract |
|---|---|---|
| cwf_reader | Astra / selected effort (default high) | Bounded read-only raw-source analysis and independent judgment |
| cwf_sol_writer | Sol / selected effort (default high) | Default Skill-only sole writer child or admitted Runtime writer; never controller or final acceptance |
| cwf_writer | Astra / selected effort (default high) | Preserved for old contracts and explicit compatible Skill-only use |
| cwf_general | Luna / max | Optional omissions, counterexamples, test gaps and second opinions |
| cwf_mechanical | Luna / medium | Low-risk mechanical read-only work with objective checks |
| cwf_burst_grok | OpenCodex xai/grok-4.6 / high | Temporary optional read-only evidence, never a required verifier |

The two package Luna profiles request 1M context and Fast service; these are not
reasoning-effort settings or proof of effective backend support. Preserve the
user's separate luna profile and global catalog. Burst requires manual enablement
and actual native capability; see [Burst](burst.md). Existing Runtime route
identities/effort and acceptance gates remain unchanged.

Runtime 4.1.1 permits explicit Astra effort selection; reader/writer profiles no longer
pin high. Root passes route.effort through the actual native tool's effort parameter.
Check the currently exposed profile first: old sessions can still advertise fixed high.
New contracts, including legacy, reject shipped-profile model or fixed-Luna-effort conflicts.
Package validation checks that Astra and Sol profiles do not shadow the selected effort.
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

Root owns the complete mainline objective. In explicit Skill-only work, current Root
directs one `cwf_sol_writer` child as the sole source writer by default. The child owns
coherent implementation, tests and bounded repair; Root owns dispatch, screening,
authorization and closeout and may continue nonconflicting read-only work. Profiles do
not promote a controller: `cwf_sol_writer` never gains dispatch authority merely because
its model is Sol. Main-conversation direct writing remains available when the user
explicitly selects it, within the original authorization and single-writer ownership;
no controller-transfer proof is required. A true controller transfer requires explicit
user selection and host proof under the full
[control-transfer contract](delegation.md#optional-threaded-control-transfer). Preserve
authorization, candidate/source identity, ownership, unresolved claims, deadlines and
cumulative spent/reserved allowance across any supported alternative. Do not create a
new Runtime run, fresh quota or second active writer/controller because a conversation
changed. Verify observed identity and controller/source capability; unknown host state
remains UNKNOWN. Runtime packets/routes stay unchanged.
Astra designs and accepts; Sol implements, tests and repairs under
the [delegation contract](delegation.md). Do not move required work to Luna because it is bounded or
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
conclusions and critical independent acceptance, including review of Sol implementation.
An unknown answer alone does not require Astra. Luna may gather bounded evidence
about a difficult area while Root/capable review owns its high-risk conclusions.
Unknown risk or inadequate checks require investigation or the capable route; an
unqualified task must not be labeled ordinary or mechanical merely to lower cost.

Keep required evidence collection in the complete Astra-led mainline, including Sol's
implementation checks. Add independent Luna probes rather than removing required work. Keep
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

Writing is not enabled by cwf_mechanical or cwf_general. In Skill-only work, use one
`cwf_sol_writer` child for the closed sequential write scope by default, with required
Astra acceptance. Root counts as a writer and must not edit the candidate while the
child owns it. Direct Root writing, true controller transfer and parallel writers are
explicit alternatives under [the delegation contract](delegation.md); never defeat a
non-writer profile by relabeling it.
There is no automatic expensive fallback
outside the approved allowance. Incompatible explicit user route/model selections
are surfaced, not silently rewritten.

Astra reader/writer profiles already omit fixed effort; do not add a neutral profile
merely to select another supported effort. Other explicit mappings need a compatible
host and run contract, not a shadowed override. Model unavailable: retain partial
results and report the exact limitation; do not silently substitute another mapping.

## Lifecycle

A host may cap open threads, not only running turns. Use its actual completion/closure
contract; idle is not automatically closed and interrupt is not confirmed termination.
A controller handoff does not release old child/writer ownership by itself. Before an
optional Sol execution Root takes control, reconcile task-owned active work through
settlement, supported transfer or explicitly assigned legacy-probe custody under
[the handoff rule](delegation.md#optional-threaded-control-transfer); unresolved holds remain UNKNOWN.
A collection-only custodian is not a second implementation Root. After transfer,
the former planning thread must not dispatch or write against the same candidate.
Use [native result collection](evidence.md#native-result-collection) to distinguish
execution/collection gaps from confirmed failure or resource release.
While work runs, rely on host completion notification or suspend/resume and continue
independent Root work. Wait/read/status only when the next step depends on the result,
or reconcile once after resume. Avoid short-interval polling, mechanical wakeups and
repeated unchanged logs. Do not invent timers or adapter fields.

Distinguish suspending or resuming the Root from restoring a child that was already
closed. In explicit Skill-only work, a writer whose current turn has stopped may remain
open and continuable while required review or a repair decision is pending. It still
occupies host capacity and must not displace required review. When authorized repair
remains and capacity permits, continue that same writer; close it only after no further
repair is needed or the task is closing, or when an actual capacity constraint requires
release for needed review. Do not retain a writer with no pending work merely in case.
Ordinary bounded repair uses a same-task follow-up to that still-open writer rather than
a needless close/restore cycle.

After a writer is closed, do not assume that restoring it preserves the requested
model, profile or effort. When the host cannot reliably preserve that route across
closed-child restoration, a restored instance must not perform implementation. After
the old writer is confirmed stopped and retained resource/capacity constraints are
satisfied, Root may create one replacement writer with the original explicit profile,
model and effort and a compact continuation of the original task state. This is a
replacement, not a second writer: the same candidate, authorization, cumulative task
allowance and unresolved risks continue, with no fresh quota. If observation shows an
identity mismatch after restoration, stop the affected execution, record the actual
identity, and never present it as the requested model.

Use the exposed native lifecycle tools and execution observations. A tool-family name
does not establish the host's internal implementation generation. Do not add a model
turn merely to handshake, require new fields or ledgers, start another scheduler, probe
every turn, or switch backends automatically. Runtime work remains on the original
run's admitted attempts, routes and verifier; this Skill-only replacement rule cannot
bypass Runtime admission or replay a Runtime writer.
On capacity failure inspect once, queue eligible work, and avoid retry loops. A queued
branch remains accounted for. Never spawn past capacity or free an unconfirmed writer.
A host-confirmed completed readonly turn with settled tools can reconcile execution through the Runtime protocol while its host-resource reservation remains UNKNOWN. Keep execution completion and host-resource cleanup separate.
Root alone owns dispatch. No peers, child spawning or autonomous nested workflow.

## Installation and native execution

The installer requires an explicit discovered home and installation scope. Do not
infer the active home from a username or directory existence. Some hosts use user
`.agents/skills`; existing installations may use CODEX_HOME/skills. Verify discovery
on the actual client and avoid duplicate same-name skill copies.

Astra, Sol and Luna all use native host agent tools. Use the compatible native profiles
above, preserving bounded unknown-answer exploration and critical capable judgment.
All consume native host capacity; no model label grants a slot exemption. Batch
useful Luna work as capacity allows and keep needed Astra reservations available.
On a native capacity or capability gap, queue/report the affected work. CLI model
dispatch and the former independent Luna process pool are disabled, not fallback.
Do not repeat permission questions for native batches within the task's scope/allowance.
Persistent graphs and transactional launch reservations remain optional Runtime state
management; read [Runtime protocol](runtime.md) before using its native host bridge.
