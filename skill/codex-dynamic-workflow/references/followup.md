# v4.1: screening, resolution and candidate-bound supplementation

## Defaults and compatibility
The meaningful-task default remains at least three distinct native Luna probes, started
early when capability, budget and observed host capacity permit. Astra owns all necessary
work and delegates scoped implementation/tests/repairs to Sol in new 4.2 contracts. Three counts task-level launch intent, not completed results, votes or a new quota
on each repair. Keep probes small enough to return useful evidence during the mainline.
Skill-only remains normal; the commands below apply only to explicitly selected Runtime.

New 4.1 contracts carry supplemental_protocol=2 and immutable acceptance_mode=review or
repair (default repair when implement=true). Repair mode requires implement authority.
Saved 3.0.0, 4.0.0, 4.1.0, 4.1.1 and 4.1.2 records retain exact hashes, fields, budgets and earlier gates.
They are not rewritten or silently upgraded. No model CLI fallback is enabled.

In 4.1.1, Astra reader/writer profiles keep their model and role constraints but omit
fixed effort. Root explicitly passes the selected host-supported effort; high is only
the Runtime default. New Astra contracts accept low/medium/high/xhigh/max/ultra.
Luna profiles retain max/medium. New contracts using any shipped profile, including
explicit legacy contracts, must match its fixed model and any fixed effort. Package
validation checks these constraints and rejects accidentally re-pinned Astra effort.
Inspect the current native tool schema before dispatch: a session still advertising an
old fixed-high profile cannot execute a different effort under that profile. Reloaded
profile discovery and effective execution need host evidence; installation alone is not proof.

## Information channel and bounded Root screening
The v4.1 result schema is scripts/cwf_runtime/result-v41.schema.json. The original
result.schema.json remains the legacy schema. Both keep the existing result fields.
Optional notes (at most 12 compact text/evidence entries) record naming suggestions,
coverage observations or scoped negative checks. They do not create acceptance claims.
A plausible delivery/security risk MUST be a claim, not hidden in notes or uncovered.
The controller cannot infer semantic risk; Root remains responsible for this distinction.

Screen returned concrete candidates at natural mainline checkpoints. Immediately surface
credible severe risks or evidence relevant to an imminent irreversible action. Do not
interrupt Astra for every generic suggestion. Root reopens current original evidence,
deduplicates by proposition/scope/candidate, and may classify a candidate as dismissed,
advisory, duplicate of another same-run claim, or promoted. Unknown is not disproof.

Use triage for one claim or screen --run RUN --decisions decisions.json for an atomic
batch (1..64 decisions). Each decision has claim, disposition, reason, plus target for
promotion or duplicate_of for a duplicate. Duplicate source coverage is checked; cycles
and cross-run links are rejected. A duplicate of an unresolved claim stays unresolved.
Promoted issues cannot be demoted to an advisory as a shortcut around resolution.

New unscreened claims still temporarily make current acceptance unavailable. A benign
screened note/claim does not change the established mainline receipt key, so screening
can restore acceptance WITHOUT rerunning the whole mainline or another finish. A new
promotion adds a real mainline obligation and does require normal acceptance afterwards.
This is a bounded attention cost, not a guarantee that supplementary evidence is free.

## Early evidence and explicit problem disposition
When a probe has concrete evidence, return it to Root through the actual host's supported
parent communication rather than waiting for the final report. Root can record it with:
report --attempt TOKEN --external-id CHILD --backend native --report report.json
The report contains report_id, sources_opened and claims. Early reports are append-only,
identity/scope checked and idempotent by attempt/report_id; a conflicting retry is rejected.
Up to 128 early claims per attempt are retained, separately from the final result's
existing 64-claim bound. Interruption or retry does not erase an early finding.
This records a host-delivered report; it neither polls nor messages the native agent.

Promotion binds never-executed required mainline work on current evidence. In 4.2 a
Sol writer may be that work, but only Astra evidence can support a passing resolution.
Finishing that investigation is NOT the same as resolving the issue. Root records:
resolve --claim CLAIM --outcome reported|disproved|fixed|blocking --reason ... [--node ID]
- reported: sufficient only for a review task whose deliverable is the finding report.
- disproved: a current, completed required Astra evidence node supports rejection.
- fixed: an observed writer change and its current required, independent Astra verifier.
- blocking: still unresolved; not a passing repair or a waiver.
All passing outcomes bind the whole resolution evidence set and the promotion revision.
Changed evidence invalidates the disposition. Node labels and reasons remain trusted Root
judgments, not automatic proof that a natural-language requirement was satisfied.
For new 4.1.1 contracts, the writer used by fixed must itself be the promoted work or
its causal descendant. A new reviewer cannot turn a pre-investigation writer into a new fix.

## Capacity and a genuinely new candidate
For supplemental admission, next requires BOTH actual --host-capacity N and --host-active M.
A configured run ceiling is not a live host observation. Unknown capacity queues only Luna.
Root supplies fresh observations; controller timestamps/counts are not host authentication.
Reserve the greater of the configured minimum, the known upcoming required mainline
frontier and --mainline-slots-needed N when Root knows a larger near-term demand. Root can
increase but not remove the reserve. Unconfirmed retained host threads still occupy slots.
CPU-heavy tools, shared databases and rate limits also remain Root/host responsibilities.

First acceptance closes supplemental admissions for that candidate epoch, not forever.
Within a still-open run, after an authorized material change and settled candidate writers,
Root may reopen-supplemental --run RUN --changed-paths paths.json --reason ... .
The changed paths must belong to the bound mainline candidate and have different bytes.
This admits new snapshot-bound nodes; it never revives omitted probes or changes routes,
launch counts, attempts, strong reservations, deadline or absolute ceilings. No fresh
three-probe minimum applies to repairs. Another acceptance closes the new epoch.
Already completed/cancelled runs are not resurrected by this operation.

## Nonblocking delivery and honest closeout
A successful mainline can be reported while useful Luna work is running. Neither idle
Root time nor mainline acceptance alone is a reason to wait for, or immediately kill,
a useful probe. Stop on an actual duplicate/no-progress/budget/deadline/capacity reason.
No automatic interrupt or background scheduler is added.

If the host really supports receiving results after mainline delivery, identify the
actual responsible receiver and a bounded cutoff. Runtime closeout --run RUN --entries
entries.json records task-owned attempt/action/reason/observed_via entries. continue also
requires receiver and a future until (Unix time, at most 300 seconds from recording).
This is a maximum tail observation window, NOT a mandatory wait and NOT a new agent budget.
Without a real receiver, perform one bounded host closeout, request stop where appropriate,
and report incomplete coverage. Do not promise automatic later processing.

stop-requested and unknown are observations, not confirmed termination. Expired continuation
is visible in status but triggers no tool call. Existing actual release/readonly-turn
receipts remain necessary. Root must collect already returned material evidence before
recording closure; a stop request is never proof that a host slot or tool process is free.
Mainline acceptance, supplemental coverage, execution reconciliation and physical host
resource release remain separate. Do not wait for all four merely to deliver the mainline.

Resolution evidence must be the promoted investigation itself or its causal mainline descendant; unrelated preexisting completed work cannot close a new finding.

## 4.1.2 review hardening
Any explicitly declared verifies relationship in 4.1.2 and 4.2 contracts requires a
different native author identity and matching coverage of the entire target candidate,
even when the target is low-risk Astra work. Low-risk work without a declared verifier
does not acquire a new review requirement. Older saved contracts are not migrated.

Capacity includes unbound unreleased dispatch reservations in addition to the larger of
known bound holds and the observed host active count. Unbound reservations may not yet
exist as host threads; a lost launch response is conservatively retained, not refunded.
This does not authenticate host counts or turn a stop request into resource release.

Serialized database envelopes share the 1 MiB read limit. Oversized results are rejected
inside the transaction without losing the active attempt, budget charge or earlier
findings; submit a smaller truthful result. Aggregate hash preimages are not stored
envelopes and may cover multiple individually bounded records.
