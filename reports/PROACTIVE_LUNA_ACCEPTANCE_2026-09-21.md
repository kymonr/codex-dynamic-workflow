# Proactive Luna and Fast routing acceptance

## Scope

Closeout scope: useful proactive Luna delegation in implicit mode and Fast request
routing for the two package-owned Luna profiles. Runtime 4.2.0 code/routes/budgets,
the existing explicit workflow and Grok policy retain the upstream baseline.
Separate local explicit-workflow and Grok adaptations are not part of this patch.
The user's independent `luna` profile and OpenCodex configuration are not installed
or managed by this package.

## Observed execution

On 2026-09-21, two fresh native `cwf_general` children performed distinct readonly
checks: installer preservation of local edits and delivery of packaged roles.
Both completed; their task execution intervals overlapped by 144.215 seconds.
Root continued its own installation-ledger and request-evidence checks and used
the returned findings. This was useful source investigation, not a dummy response
or a text-only policy test.

Both native child sessions recorded `gpt-5.6-luna--fast`, max effort and 875900
usable context tokens. The parent-session-correlated request batch during their
execution contained 37 Luna/max records, all HTTP 200 with `wireValue=priority`
and `fastOutcome=applied`. Requests are correlated to the parent batch, not joined
one-to-one to individual children. `confirmation=assumed` and the response tier
echo `default` do not establish backend scheduling or a measured speedup.
Earlier fresh medium and max canaries also emitted priority; configuration alone
was not used as proof of propagation.

The current conversation already knew the validation objective and loaded Skill.
It therefore did not independently establish automatic Skill discovery in an
unprimed root task. The user subsequently confirmed automatic invocation with
“已经会了” and accepted closeout. This is recorded as **user-confirmed acceptance**,
separate from the directly observed native execution and request routing above.
No claim of an independently reproduced unprimed-root test is made.

## Source findings and limits

The readonly investigation confirmed that installation gates reject observed
ownership/preimage drift and that ordinary `luna.toml` is outside the package
manifest. It also identified an existing check-to-replace concurrency window in
the installer; no actual overwrite was reproduced. The installer is unchanged.
Two previously existing installed-file ownership differences were retained;
this patch does not claim that the complete local installation matches its ledger.

Child completion does not prove native slot release or OS-enforced readonly
isolation. Backend latency, pricing, and priority scheduling were not measured.
The local Jev follow-up verified five narrow evidence claims, but the original
overall gate remained `escalate`; it is not represented as whole-patch approval.
Final source-package validation and CI are recorded on the pull request for the
actual submitted commit, rather than inferred from these earlier runtime checks.
