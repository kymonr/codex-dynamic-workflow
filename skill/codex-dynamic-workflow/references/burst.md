# Burst sidecar: native Grok through OpenCodex

Revision 2026-09-14. This is an automatic implicit/explicit Skill-only extension, NOT a new
Runtime backend, permanent pipeline stage or substitute for Astra acceptance.
`../burst.json` is a manual enabled/disabled switch plus exact native route. There
is no Burst-specific expiry, per-task attempt count, follow-up count or wall-clock
limit. Reinstallation and new tasks do not create or renew a time window.

## Routing and activation

The observed OpenCodex catalog exposes `xai/grok-4.6`; use the native Codex Desktop
subagent tools with `cwf_burst_grok` (high, read-only). OpenCodex is the configured
provider transport, not separate permission to start a CLI, proxy or direct xAI API.
Do not alter provider/auth configuration or substitute another model without authority.
Inspect actual host profile/tool support before each new native turn. A requested
profile or catalog entry is not an execution identity receipt; preserve UNKNOWN when
execution identity is not exposed.

Enabled Burst automatically prefers one useful Grok probe during meaningful implicit
or explicit Skill-only work when there is an independent evidence question within the
task's source and privacy permissions. Explicit work may add further useful Grok turns.
The automatic implicit Grok probe is optional to task completion: trivial scope or failed
source, privacy, provider, profile, capacity or backpressure gates skip it with a reported
reason. Runtime 4.2.0 cannot represent the Grok route, so Runtime-managed work omits Burst rather than
dispatching around its ledger. Manual disable or unavailable provider quota prevents
new Grok turns but does not erase already returned evidence.

## Distinct work, not another review hierarchy

Automatically use Grok when it adds a genuinely different method or synthesis: challenge a material
design assumption, trace a coupled subsystem, pre-review a stable full diff, develop a
new falsifiable explanation for stalled diagnosis, or prepare source-bound reusable
evidence. Do not run every Grok shape on every task merely because calls are available.

Luna is requested as 1M Fast and can also analyze large scopes and unknown answers.
Do not route by presumed context superiority. Route by distinct value, evidence method,
current provider availability and host capacity. Keep prompts source-bound rather than
copying the entire chat history.

Astra owns key design/acceptance, Sol Root owns continuous execution and screening,
Luna adds broad probes, and Grok adds optional independent evidence. Removing Luna and
Burst must leave required implementation, tests and review intact. Grok is never the
final verifier, writer or authority to weaken acceptance. Suggested patches/tests are
proposals until the authorized implementer and real test tools apply/execute them.

## No Burst time or call-count ceiling

The workflow imposes no Grok expiry date, no per-task attempt ceiling, no follow-up
ceiling and no per-probe duration ceiling. Additional turns may continue while the
question remains useful, authorized, provider quota is actually available and host
capacity permits. Record observed Grok usage when exposed, but do not turn the record
into a hidden quota. Grok sidecar turns do NOT consume the Runtime/Skill Astra-Sol-Luna
launch-count ceilings; those budgets remain reserved for their original routes.
Different providers' quota units must not be added as if they were interchangeable.

Unlimited turns do not mean unlimited blocking. Root never waits merely because Grok
is still running. Pause new optional Grok launches when report backlog, native slots,
CPU, I/O, test locks or other shared resources threaten ready mainline work. Stop or
close task-owned Grok work on user cancellation, completed scope, duplicate/no-progress
evidence, provider unavailability or observed backpressure. A stop request is not
proof that a host thread released its slot. Already received credible severe evidence
still needs source-based disposition even if the sidecar is later disabled.

There is no Burst-specific timer, but an explicit task-level user deadline or cancellation
still applies to the overall task. The sidecar never extends user authority or creates
background delivery promises. Without a real result receiver, do bounded host closeout
rather than promising unattended later processing.

## Bound sources, privacy and results

Bind every Grok question to a verified isolated snapshot/candidate containing relevant
uncommitted changes. Grant only task-approved source paths and safe resource use. Grok
uses another provider: do not include credentials, customer exports or unrelated private
data. Existing no-external-sharing constraints remain controlling.

Use NODE/STATUS/SOURCES_OPENED/CLAIMS/CHECKS/UNCOVERED. Include candidate identity,
source/range, trigger, impact, reproduction/check and uncertainty. Return useful evidence
at natural checkpoints and retain every plausible material risk. Root reopens current
original evidence before materially adopting a finding and semantically deduplicates
Luna/Grok reports. Agreement is not verification; unexamined scope is not clean.

Fresh Astra acceptance reads original requirements, the full actual diff, critical
dependencies and raw tests rather than only model summaries. Sol performs whole-diff
self-review first. Grok disagreement is a lead, not an automatic project-wide halt.

## Capacity and native-thread reuse

All native agents share host capacity. Reserve the greater of one slot and known upcoming
mainline demand before starting a NEW Grok child. Unknown capacity fails closed for new
Burst dispatch, not for the mainline. Retained/unconfirmed threads still occupy capacity.

An additional turn may reuse the same task-owned idle Grok child on the same snapshot when
Root actually observes that ownership/state. Reuse consumes no new slot but the retained
thread remains counted in active capacity. Never mark a busy or unrelated thread reusable
or use reuse to hide a resource hold. There is no follow-up-count limit.

## Optional deterministic preflight helper

From the installed Skill root:

```text
python -B scripts/burst_sidecar.py --observation <current-observations.json>
```

This is local policy evaluation, NOT model dispatch. It never calls Grok, changes config,
starts timers, creates reservations or tracks call counts. Root supplies fresh observations
immediately before native dispatch. `observed_at` must be timezone-aware, not in the future
and at most 30 seconds old; freshness protects capacity/profile decisions and is NOT a
runtime limit on Grok. Refresh real observations rather than only changing the timestamp.

Required observation fields are mode, purpose, candidate_id, observed_at, source approval,
snapshot isolation, backpressure, provider quota availability, and host capability/capacity.
The exact observed profile name/model/effort/read-only setting must match `burst.json`.
No task-used, Burst-used, deadline, expiry or follow-up counters are part of admission.

## Luna 1M Fast: request versus observation

Package-owned `cwf_general` and `cwf_mechanical` request `model_context_window=1000000`
and `service_tier="fast"`; reasoning efforts remain max and medium. Fast is service tier,
not reasoning effort. Do not modify the user's separate `luna.toml`, global config,
provider catalog or old Runtime routes. At this revision the inspected separate Luna
profile still declared 500000 and the OpenCodex catalog advertised 272000. These values
are recorded rather than silently rewritten. A 1M Fast request is not proof of effective
backend context, latency, price or quota; verify execution evidence when exposed.

The required independent Astra acceptance remains unchanged by Burst availability, call volume or Grok findings.
