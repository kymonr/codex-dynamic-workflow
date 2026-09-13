# Temporary native Burst / Grok sidecar — 2026-09-14

## Candidate and observed host

This revision extends the previously installed, uncommitted phase-handoff candidate
in the dedicated checkout. Git base remains b132e12efb01eefe4c4e0b33cd3fe3a82342b221.
The exact 121-file incoming source snapshot and the prior installation ownership
ledger are preserved under .delivery/burst-20260914/before and install-state.before.
The older non-Git project copy and its ownership state were not rewritten.

OpenCodex's local catalog advertises xai/grok-4.6, high effort and 500000 context.
The user confirms that their Codex Desktop can dispatch it as a native subagent.
This chat does not expose native subagent tools; catalog inspection is not a live
Grok execution receipt. No CLI model call, direct external model API or proxy was
used as a substitute. No model-quality, speed or credit-saving claim is made.

The user requests Luna 1M Fast. Package-owned cwf_general and cwf_mechanical now
request model_context_window=1000000 and service_tier=fast, keeping max/medium
effort and read-only permissions. The separate user luna.toml still declares
500000; the OpenCodex catalog declares 272000. These observations are retained,
not silently edited into agreement. Effective 1M support remains unverified.

## Implemented boundary

Burst is a temporary optional explicit Skill-only extension. The leased native
profile is cwf_burst_grok / xai/grok-4.6 / high / read-only. Initial activation is
2026-09-14 00:00:00 +08:00 through 2026-09-28 00:00:00 +08:00 (exclusive), a local
user-selected two-week cutoff, not a verified provider subscription expiry.

The installed policy permits at most four cumulative attempts per task, one active
Burst child, a 240-second probe cutoff and one new-input follow-up inside the
original cutoff. Attempts also consume the existing task allowance. Reserve
required mainline work first. These are planning limits, not a hard host timer,
credit meter, new ledger or daemon. The helper gives read-only admission advice.

Grok adds design counterexamples, cross-module evidence, stable-candidate pre-review,
stalled diagnosis or reusable source-bound evidence. It is never a required stage,
mainline dependency, writer or final verifier. Required Astra review proceeds
without waiting for Grok. Removing Luna and Grok leaves a complete mainline.
Received credible material risks remain actionable even after expiry or interruption.

Implicit mode remains Luna-only. Runtime 4.2.0 cannot express the sidecar route, so
Runtime-managed work omits it rather than dispatching outside its ledger. Existing
Runtime code, policy.json, model routes and saved-contract semantics are unchanged.
Root retains source-sharing authorization, actual snapshot checks, lifecycle
observations, cumulative accounting and the full-diff independent acceptance gate.

## Whole-diff author review and corrections

The author read the entire incremental diff, including profiles, instructions,
policy helper, package validator and tests, and reread every subsequent fix. This
is a reviewer-perspective SELF-REVIEW, not an independent non-author model review.

1. Matching only model and effort did not identify the actual native profile.
   Admission now also checks the exact observed profile name and read-only setting.
2. A saved host observation could pass long after capacity changed. The helper
   rejects future observations and observations older than 30 seconds. Caller
   timestamps are not authenticated receipts; Root must refresh actual observations.
3. Following up on a retained idle child must not consume an additional host slot.
   Explicit same-task idle-thread reuse keeps the thread counted, preserves the
   original cutoff and charges another attempt. Initial-turn misuse, full capacity
   and exhausted budgets are still rejected.

## Verification and installation

Completed verification and actual installation results are recorded below.
All model identities and host observations used by regression tests are SYNTHETIC.

## External state preservation

A concurrent global config change was observed before installation: reasoning effort
changed from high to medium. This task did not edit that configuration and does not
restore its old hash. Provider catalog and unrelated profiles remain protected.
No commit, push, PR, merge, global configuration, authentication or permission change
is part of this delivery. Physical native-resource release, native model behavior
and independent model acceptance remain untested in this chat.

### Final deterministic results

- Windows / Python 3.12.10: 496 tests, 494 passed and two unchanged environment
  skips; 118.947 seconds. Log: .delivery/burst-20260914/final-full-regression.log.
- Burst focused suite: 20 passed; 2.604 seconds. Log: focused-final.log.
- Package validator PASS, 43 Python source files compiled in memory, diff whitespace
  check PASS, Runtime code and policy.json byte-identical to the incoming snapshot.
- Tests include strict policy/types, exact expiry, no renewal, mismatched native
  routes, stale observations, shared capacity/budget reservations, preserved original
  follow-up cutoffs and isolated installation without touching actual user files.
- Skips: Windows symlink-creation permission and unavailable 8.3 short-path alias.


### Actual local installation

Installed into D:/CodexData/.codex with the existing reversible ownership-aware
installer. Updated 12 files; verified 35 managed files byte-for-byte.
Post-install dry-run has zero changes. Retired legacy alias remains absent.
The installed controller reports Runtime 4.2.0.

Recovery receipt: `D:\codex\temp\dynamic-workflow-handoff-20260914\repo\reports\install-backup-60e71f786bc4\receipt.json`.

A fresh installed-helper process rejected a SYNTHETIC implicit-mode observation
with allowed=false/mainline_blocked=false and exit code 2. This verifies local
policy loading only; no native subagent or external model was invoked.

Global config, provider catalog and all six separately owned user profiles were
unchanged across the actual install. The earlier observed high-to-medium config
change was preserved. Effective native profile activation, Grok execution identity,
Luna 1M Fast backend support and physical native-resource cleanup are NOT verified.

The candidate remains uncommitted and unpublished. Source hashes include this
report; install receipts and test logs stay under their existing local evidence paths.
