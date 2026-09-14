# Astra design, Sol execution Root, independent Astra acceptance (4.2)

Skill-only phase-handoff revision: 2026-09-14; threaded control-transfer revision:
2026-09-14. Runtime contracts remain unchanged.

## Smallest useful operating model
Astra owns key design decisions, risk boundaries and original-goal acceptance.
Root is the current main-thread controller, not a permanently Astra-owned model role.
For substantial explicit Skill-only work, prefer a separate Sol execution thread when
the host can create or select an independent conversation with the required source/tool
access and can transfer the task state described below. That Sol thread becomes the sole
implementation Root for continuous implementation, tests, bounded repair, progress and
Luna/Grok triage. If separate controller transfer is unavailable, the user/host may
switch the current main conversation to Sol instead. Do not replace either path with an
Astra-supervised `cwf_sol_writer` child.
Luna performs independent read-only questions, never final acceptance or voting. Tools
perform deterministic searches, formatting, tests and hash checks without model delegation.
This replaces the implementation owner; it does not add a duplicate Astra implementation
pass, another scheduler, another ledger or a hierarchy of reviewers. Skill-only is normal.

## Phase handoff, not another scheduler

In explicit Skill-only mode, prefer Astra design -> separate Sol execution Root thread
when supported -> continuous Sol execution -> fresh Astra acceptance thread at a
meaningful delivery or risk boundary. The same-conversation user/host model switch is
the fallback when a separate Root thread cannot be established with equivalent task
access. Small cohesive work need not invent phases. Implicit supplementation mode does
not acquire this pipeline or Astra/Sol children.

Before handing off, Astra reads the relevant raw sources and records an executable
brief in the existing task/plan document when authorized, or in the conversation
otherwise. Include the original outcome and non-goals; the selected workflow mode
(`explicit full workflow`) and applicable Skill/runtime revision; the baseline commit
when Git exists (otherwise exact source hashes or a bound snapshot; do not initialize
Git merely for handoff); relevant uncommitted changes; protected/owned files; current
authorization and allowed effects; invariants and design rationale; staged dependencies;
concrete acceptance checks and expected evidence; unresolved assumptions and claims;
escalation conditions; active child/writer ownership and lifecycle holds; deadlines;
the cumulative spent/reserved allowance; and completed/pending supplemental direction
identities, including whether the automatic Burst probe already ran or was skipped and
which returned risks remain open. The receiving thread continues this exact task and
mode; opening a new conversation is not a new invocation or a new allowance.
A full outcome/acceptance plan is not a line-by-line implementation script. Detail
the next executable stage; keep later stages revisable when evidence changes.

### Threaded control transfer
When the host supports it, start or select the separate Sol execution conversation
through the actual host/user control and pass only the compact handoff state needed to
resume the task. The Skill cannot create an unsupported controller thread, silently
reconfigure a parent, or claim a transfer from prose alone. Only the user/host can create,
select or switch the running controller conversation/model through supported controls.
Verify the selected model, effort, repository/source access and controller capability
from exposed host state when available; otherwise record effective identity UNKNOWN,
not Sol, and controller transfer UNKNOWN rather than claiming success.

A successful transfer has exactly one implementation Root for the candidate. Once the
Sol execution thread takes ownership, the Astra planning thread stops writing, dispatching,
changing candidate state or acting as a second controller. It may remain available as
read-only historical context, but material design escalation is a bounded consultation,
not concurrent control. Do not leave two Roots believing they own the same writer,
children, candidate or merge boundary. A later user message in the old planning thread
does not silently retake implementation ownership; reconcile or explicitly transfer
controller ownership before either thread performs further writes or dispatch.

Before transfer, settle or explicitly transfer task-owned active children and ownership
using real host lifecycle observations. If the host cannot transfer control of active
children, close out task-owned children where supported; unresolved termination/resource
holds stay UNKNOWN and keep their relevant capacity/ownership reservations. A stop request
or a new conversation never proves release. Do not terminate unrelated sessions.

The task, source identities, allowed effects, unresolved claims, deadlines, active
ownership and spent/reserved allowance continue across the handoff. It is the SAME task
allowance: do not reset counters, invent fresh probe quotas, create a new Runtime run,
expand permissions or create parallel writer authority because the conversation changed.
If prior Skill-only launch usage cannot be reconstructed exactly, do not treat UNKNOWN
usage as zero: preserve the known lower bound/UNKNOWN state and do not spend optional
allowance that cannot be shown to remain. An explicit new user allowance may extend the
same task; it does not erase prior use. Thread changes also do not re-trigger the normal
three-probe intent or the automatic Burst preference for already-covered questions.
Sol reopens the current Skill entry/relevant references plus the named original sources,
then checks the compact brief against the current tree. Stale assumptions need
reconciliation, not blind execution or wholesale replanning. Do not copy every log,
full conversation history or other agents' conclusions into the execution thread.
Preserve the original requirements and decisions needed to understand the task, then
rely on current raw sources.

If a separate Sol Root thread cannot be established safely, keep the existing fallback:
the user/host switches the current main conversation to Sol and preserves the same task
state. Do not silently downgrade to a writer child, another backend or a second scheduler.

Sol Root may dispatch and screen Luna and enabled Grok using the actual native host tools.
It has this authority because it is the current Root, not because its model is Sol.
A Sol child using `cwf_sol_writer` remains a child: no nested delegation, peer messaging
or controller commands. Model identity never grants Root authority to a child. A fresh
Astra reviewer is opened or dispatched from the current Root/host as a separate review
context, not spawned by the writer child. Missing native capability is an explicit gap.

This manual Skill-only handoff is NOT Runtime handoff. A selected Runtime keeps the
same DB/run, immutable routes, attempt accounting and required Astra verifier.
Its managed steps still need admitted native child packets; moving a writer into Root
or opening another conversation does not satisfy or bypass those gates. Never use
another run or conversation to reset limits.

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
For important deliverables, prefer a fresh Astra review context, normally a separate
review thread, rather than simply returning control to the planning thread. Pass the
original requirements, selected explicit workflow mode, exact candidate identity, full
actual diff, critical dependencies, tests/evidence, unresolved risks, allowed review
effects and the remaining/reserved acceptance allowance; the plan is review input, not
an instruction to confirm it. The fresh Astra acceptance thread is non-author for the
candidate and should remain read-only by default. If it writes or repairs the candidate,
it loses non-author status for those bytes and a different capable reviewer must perform
any still-required independent acceptance. Do not copy the full planning or implementation
conversation as the reviewer's premise. Check beyond Luna's findings list and any Grok
findings. Prefer a genuinely fresh context rather than a full-history fork; if the host
can only provide inherited context, disclose that independence limit and do not claim a
blind independent design review from it. Missing fresh context or raw-source access must
be disclosed and cannot waive required independent verification.
After the writer stops, Astra reads the full actual diff, critical dependencies, tests
and unresolved evidence against the original goal. It may reject the original Astra
design. A planning Astra that did not write code can review implementation, but reusing
that same context is not independent design review. Preserve any required high-risk/
non-author or user-requested independent check. Runtime always requires its declared
Astra verifier for a writer; a chat summary cannot replace that node. Recheck affected
evidence after a repair, not every reviewer recursively. Rejected work returns to the
same Sol execution Root unless an explicit controller transfer changes ownership; a
repair cycle never creates a fresh allowance or duplicate writer by itself. Zero-model
regression is not live model, permission, quality, price or savings validation.

## Temporary optional Grok sidecar
An enabled [Burst sidecar](burst.md) permits extra native OpenCodex evidence in explicit
Skill-only work. Do not insert Grok as an obligatory design or pre-acceptance stage.
Sol Root screens current raw evidence; Astra still performs required independent
acceptance beyond all agents' findings. Luna 1M Fast can handle large scoped work;
Grok is selected for a distinct useful method, not presumed context superiority.
