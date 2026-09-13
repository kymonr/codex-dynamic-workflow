# Astra design, Sol main thread, independent Astra acceptance (4.2)

Skill-only phase-handoff revision: 2026-09-14; Runtime contracts remain unchanged.

## Smallest useful operating model
Astra owns key design decisions, risk boundaries and original-goal acceptance.
Root is the current main-thread controller, not a permanently Astra-owned model role.
After a user/host switch, Sol Root owns continuous implementation, tests, bounded
repair, progress and Luna triage; do not keep Astra supervising every tool result.
Luna performs independent read-only questions, never final acceptance or voting. Tools
perform deterministic searches, formatting, tests and hash checks without model delegation.
This replaces the implementation owner; it does not add a duplicate Astra implementation
pass, another scheduler, another ledger or a hierarchy of reviewers. Skill-only is normal.

## Phase handoff, not another scheduler

In explicit Skill-only mode, prefer Astra design -> user/host switches the main
conversation to Sol -> continuous Sol execution -> fresh Astra acceptance at a
meaningful delivery or risk boundary. Small cohesive work need not invent phases.
Implicit supplementation mode does not acquire this pipeline or Astra/Sol children.

Before handing off, Astra reads the relevant raw sources and records an executable
brief in the existing task/plan document when authorized, or in the conversation
otherwise. Include the original outcome and non-goals, the baseline commit when
Git exists (otherwise exact source hashes or a bound snapshot; do not initialize
Git merely for handoff), relevant uncommitted changes, protected/owned files,
invariants and design rationale,
staged dependencies, concrete acceptance checks and expected evidence, unresolved
assumptions, escalation conditions, and the cumulative allowance/reserved review.
A full outcome/acceptance plan is not a line-by-line implementation script. Detail
the next executable stage; keep later stages revisable when evidence changes.

At the handoff checkpoint, give one compact ready-to-continue brief and tell the
user which host control must change the current model. Only the user/host can
switch the running model. Verify the selected model/effort with the actual exposed
host status when available; otherwise record effective identity UNKNOWN, not Sol.
Do not edit global configuration, simulate a switch in prose, create a second
controller, or silently substitute an Astra-supervised Sol child. A model switch
alone is not completion, new write authority, independent review or a new budget.

The task, source identities, allowed effects, unresolved claims, deadlines, active
children/ownership and spent/reserved allowance continue across the switch. Sol
reopens the named original sources and checks the brief against the current tree;
stale assumptions need reconciliation, not blind execution or wholesale replanning.
If a new conversation is necessary, transfer this compact state and resolve active
ownership before continuing. If the host cannot transfer control of active children,
close out those task-owned children using observed lifecycle receipts; unresolved
holds stay UNKNOWN, never implicitly released. Do not copy every log or other
agents' conclusions.

Sol Root may dispatch and screen Luna using the actual native host tools. A Sol
child using cwf_sol_writer remains a child: no nested delegation, peer messaging
or controller commands. Model identity never grants Root authority to a child.
A fresh Astra reviewer is dispatched by Root or opened as a separate review thread,
not spawned by the writer child. Missing native capability is an explicit gap.

This manual Skill-only handoff is NOT Runtime handoff. A selected Runtime keeps the
same DB/run, immutable routes, attempt accounting and required Astra verifier.
Its managed steps still need admitted native child packets; moving a writer into
Root does not satisfy or bypass those gates. Never use another run to reset limits.

## A sufficient brief, not a second implementation
Use the existing task/scope/sources/check/stop fields. State the original outcome, decided
change and rationale, invariants, exact baseline and owned files, acceptance evidence,
and the contradictions or scope/permission/budget changes that require escalation.
Do not require a new form or make Astra prewrite code, every command or every edge case.
Sol reads the real sources, decides implementation details and returns concrete
counterevidence when the brief is wrong. Routine test failures stay with the scoped
implementer; changing goals, safety policy or weakening acceptance never does.
Escalate a disproved design premise, required semantic/permission/scope change, or
bounded diagnosis that no longer produces new evidence. Stop the affected work;
continue unrelated safe work. Do not repeatedly escalate routine test failures.
Before handing back the candidate, Sol switches to a code-reviewer perspective and
examines the entire actual diff, original goal, dependencies and tests, including
whether Astra's plan was wrong. Self-review is required but is not independent
acceptance. Preserve failing checks; never weaken tests merely to obtain PASS.
A coherent task may contain multiple tool calls, not unaccounted native follow-up turns.
Do not route Runtime-managed follow-ups outside admitted attempts or replay a writer.

## Targeted adversarial breadth
For substantial tasks, aim for 6–12 distinct Luna directions when useful independent
questions, allowance and capacity exist; this is not simultaneous thread count.
More than twelve uses an explicitly larger task allowance, never an automatic reset.
The normal three-probe intent is per meaningful task, not per stage or repair. Spread
useful questions across design and post-change checkpoints instead of repeating each.
Adapt the three directions to (1) challenge the design assumptions with counterexamples,
(2) find missed callers/configuration/compatibility paths, and (3) find a false-green
test or competing explanation. At least one question may challenge Astra's plan itself.
Additional Luna work needs a distinct uncovered question, evidence method and remaining
allowance. Large batches are allowed only when those independent questions really exist.
Return source/range, trigger, impact, evidence and uncertainty; do not force findings,
repeat broad audits under different titles, or send the whole conversation to every child.
All material leads remain in CLAIMS; compact summaries never erase risks.

## Protect the acceptance budget
Reserve the needed Astra review capacity and allowance before Sol or optional probes.
Concentrate Astra attention at design and acceptance, escalating only material deviations.
These are checkpoints, not a promise of exactly two model requests. All native turns,
including failed starts, follow-ups and repairs, consume the cumulative task allowance.
When the user has no model budget or forbids native runs, launch none, including cheap
probes; do only separately authorized deterministic/local work and label native checks
NOT_RUN. Account quota and Root tokens are UNKNOWN unless actually observed.
If mandatory Astra review cannot run, keep implementation as pending acceptance; never
substitute Sol self-approval or unanimous Luna reports. No automatic model fallback.

## Same controller, versioned routes
New 4.2 astra-mainline contracts select cwf_sol_writer / gpt-5.6-sol for writer packets.
Other required mainline nodes and verifiers retain cwf_reader / gpt-6-astra. Writer
specs still require tier=strong, implement=true and a closed write set: this is the
capability/authorization label, not proof that the actual model was Astra. New Sol
writer attempts consume used/approved/absolute, not strong_used or the economy reserve.
Required Astra reservations and single-writer/candidate/claim/release gates still apply.
Saved 3.x/4.0/4.1 contracts retain exact routes, hashes and tier-based counters; new
explicit legacy contracts keep the old defaults. cwf_writer remains Astra for compatibility.
Never select legacy or start another run to bypass the active task's route or budget.
Sol may be a promoted implementation target, but cannot supply a passing issue resolution:
use applicable Astra evidence, and an independent writer verifier for fixed outcomes.

## Non-author acceptance is not automatic independence
For important deliverables, prefer a fresh Astra review context rather than simply
switching the original design/implementation conversation back to Astra. Pass raw
requirements, candidate identity, full diff and evidence; the plan is review input,
not an instruction to confirm it. Check beyond Luna's findings list. Missing fresh
context must be disclosed and cannot waive required independent verification.
After the writer stops, Astra reads the full actual diff, critical dependencies, tests
and unresolved evidence against the original goal. It may reject its own earlier design.
A planning Astra that did not write code can review implementation; reusing that same
context is not independent design review. Preserve any required high-risk/non-author
or user-requested independent check. Runtime always requires its declared Astra verifier
for a writer; a chat summary cannot replace that node. Recheck affected evidence after
a repair, not every reviewer recursively. Zero-model regression is not live model,
permission, quality, price or savings validation.

## Temporary optional Grok sidecar
An enabled [Burst sidecar](burst.md) permits extra native OpenCodex evidence in explicit
Skill-only work. Do not insert Grok as an obligatory design or pre-acceptance stage.
Sol Root screens current raw evidence; Astra still performs required independent
acceptance beyond all agents' findings. Luna 1M Fast can handle large scoped work;
Grok is selected for a distinct useful method, not presumed context superiority.
