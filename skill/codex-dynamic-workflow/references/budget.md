# Budget and stopping

## Three levels

Absolute ceilings are never raised automatically. Approved working allowance can
be allocated by Root. A separately preauthorized cumulative economy reserve permits
small low-cost expansion **inside** those ceilings. Strong-model extension outside
the approved allowance needs the user; a previously approved strong call does not.

`policy.json` contains initial planning defaults, not empirically optimal values.
Before the first dispatch, record the effective values, user overrides, native host
limits, mandatory-check reservations and measurement gaps in internal bookkeeping.
Keep user-facing dispatch updates to task + model; explain budget details only when
requested or when an allowance decision blocks progress. Defaults are upper bounds,
never a target headcount.
Use the stricter applicable host/authorization constraint. The reserve is per run,
not per node, wave, retry or model. Unknown cost/risk is not eligible for economy reserve.
Supplemental Luna/max work consumes the supplemental portion of approved non-strong
allowance. Plan up to 12 supplemental launches by default for meaningful work, with
at least three distinct probes as the normal launch intent when host capacity permits.
These are ceilings/coverage defaults, never a completion quota. Reserve the strong
allowance needed for Astra design/acceptance and total allowance for Sol implementation before admitting
supplemental work. In v4, both supplemental tiers use their own approved pool and cannot spill into
the economy reserve; the reserve is retained for legacy compatibility. All attempts
still count toward the absolute launch ceiling. The runtime protects all unused
strong allowance and at least one host slot, not only already declared verifiers.
In 4.1 this slot count also covers the known upcoming required frontier and any larger
explicit Root demand. Both observed host-capacity and host-active counts are required
before new supplemental admission; a configured ceiling alone is not an observation.

Concurrency has no fixed Skill ceiling: `max_concurrent_children: null` follows the
actual host's available capacity, including retained child sessions. A positive
explicit limit may further restrict it. Runtime `capacity: null` likewise adds no
controller cap; Root checks host capacity before admission/dispatch. Cumulative
launch allowances and required-check reservations still apply. If capacity is
unknown, inspect the host once and queue work on a capacity failure.

All Astra, Sol and Luna work uses native agents and shares native host capacity. Broad
Luna exploration can increase the declared useful scope and approved launch allowance,
but cannot bypass the host's actual slot limit. Admit ready directions in batches,
queue the rest, and keep capacity and approved strong calls for needed Astra work.
Do not wait for unrelated Luna siblings before dispatching a ready critical check.
No model is exempt from accounting, and low assumed cost is not zero account usage.

All child launches count, including failed attempts, repair turns, verifiers,
reviewers and retries. Keep active capacity separate from cumulative spending.
Record Root's observed consumption alongside children; if the host does not expose
Root or live usage, record unknown, never zero. Launch counters do not bound Root
reasoning or monetary spend. Do not transfer work to Root to evade an exhausted budget.

For future metered execution, track used + in-flight reserved usage; completion-only
usage is delayed accounting, not a real-time hard cap. Do not launch another costly
node on the assumption that running siblings are free. Never translate model labels
or a fixed token count into a guaranteed currency amount without current accounting.

## Expansion decision

Name the unresolved gap, distinct method, expected decision impact and required
allowance before expansion. Prefer valuable ready work; do not start an optional
coverage wave that predictably consumes the allowance required for mandatory review.
An evidence-based exclusion or successful necessary check counts as progress.

Two consecutive completed optional expansions with no meaningful information,
decision change or new executable path stop optional exploration. This is not a
universal search-round cap. Do not interrupt still-promising independent work merely
because another branch was dry. Mandatory acceptance checks are never waived by it.

When the remaining allowance cannot provide sufficient high-risk verification,
request the required extension or mark that acceptance blocked/UNKNOWN. Do not
substitute a weaker checker. Continue unrelated authorized work when safe.

## Deadlines, cancellations and repair

Record deadline/iteration limits appropriate to the task. A review→fix sequence
creates versioned successor nodes; changing segment name cannot reset limits.
At a ceiling stop new admissions. Account for live/queued branches and arrange a
safe stop of task-owned work through the host. No unconfirmed interruption is success.

Skill-only mode offers best-effort bookkeeping, not hard wall-clock, currency, file
lock or token guarantees. Report only enforcement that an actual host implements.
The reference policy tests in this package do not install a background controller.

## Final accounting

Record completed, empty-with-scope, failed, interrupted, blocked and deliberately
omitted work. Explain budget-caused omissions, distinguish optional coverage from
unmet acceptance, and report measurement gaps. Never hide a high-risk unverified
claim because its verification was unaffordable.

## Reservation semantics (2.0.2)

The reference helper's `mandatory_pending` counts all reserved checks that have not
started. It includes the current request ONLY when `consumes_mandatory=true`.
That flag is incompatible with `optional=true` and requires a matching reserved
economy/strong check. Consuming one reservation decrements the pending count;
starting an unrelated node never decrements it. No reservation is a completed check.

Before every admission, including nonoptional requests, require:
`used + mandatory_pending <= absolute`,
`used - reserve_used + mandatory_pending <= approved`, and
`strong_used + mandatory_strong_pending <= strong_approved`.
An impossible absolute reservation blocks admission; insufficient approved/strong
allowance requires an extension. Do not silently drop reservations to make it fit.

A permitted launch must preserve these inequalities for all remaining reservations.
A qualified discretionary economy node may use unused preauthorized reserve instead
of consuming approved capacity reserved for mandatory checks. Reserve is cumulative.
Mandatory checks themselves use approved allowance. The caller must update launch,
reserve and pending counters together before dispatch; this pure reference function
does not perform atomic bookkeeping or enforce the host's actual spending.

Candidate reopening changes neither spending nor the deadline. Unused supplemental
allowance is not a fresh per-repair three-probe quota. Follow [4.1 closeout](followup.md)
for bounded continuation ownership; neither the library nor this Skill installs a receiver.

## 4.2 Sol implementation accounting
In new astra-mainline contracts only, the fixed Sol writer uses approved total launches
without incrementing strong_used. Its strong node label still enforces writer capability,
closed scope and a declared required Astra verifier. It cannot borrow the economy reserve.
The declared required graph must be fundable before any admission: optional probes and
Sol implementation cannot consume the remaining Astra review reservation. Old contract
routes and counters are unchanged. These are launch counters, not account credit pools.
No available model budget means no model dispatch, not free Luna work. Reserve Root's
final acceptance separately when its usage is visible; otherwise disclose the unknown
and block unaffordable required review. See [delegation](delegation.md) for brief and handoff.
