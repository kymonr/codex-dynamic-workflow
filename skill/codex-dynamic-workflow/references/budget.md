# Budget and stopping

## Three levels

Absolute ceilings are never raised automatically. Approved working allowance can
be allocated by Root. A separately preauthorized cumulative economy reserve permits
small low-cost expansion **inside** those ceilings. Strong-model extension outside
the approved allowance needs the user; a previously approved strong call does not.

`policy.json` contains initial planning defaults, not empirically optimal values.
Before the first dispatch, state the effective values, user overrides, native host
limits and measurement gaps. Defaults are upper bounds, never a target headcount.
Use the stricter applicable host/authorization constraint. The reserve is per run,
not per node, wave, retry or model. Unknown cost/risk is not eligible for economy reserve.

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
