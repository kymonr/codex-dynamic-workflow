# v4.1 follow-up design

Baseline: e5f3d6e9b15419724ff6eda5b46a657f61016c58 (4.0 candidate).
Canonical behavior: [followup protocol](skill/codex-dynamic-workflow/references/followup.md).

Astra keeps a complete end-to-end mainline. Meaningful work proactively starts at least
three different Luna directions early where native capability/capacity permits. No result
quota, repair-cycle quota, voting gate, CLI-model fallback or automatic background worker.

## Implementation choices
- New contract version 4.1.0 with supplemental_protocol=2; immutable review/repair intent.
  Saved 3.0.0/4.0.0 hashes, routes, accounting and completion behavior are preserved.
- Exact fixed route triples plus package/profile cross-validation. The writer wording is
  version-neutral. Unsupported overrides fail rather than silently downgrading.
- A bounded notes channel for non-risk observations. Concrete candidate claims still need
  trusted Root screening. Atomic screening and source-linked duplicates avoid redundant
  full investigations. Nonmaterial screening can restore the existing mainline receipt.
- Promoted problems need explicit reported/disproved/fixed/blocking resolution. Reported
  closes only review objectives; fixed needs an observed writer change and current capable
  non-author verification. Current resolution sources and promotion revision are bound.
- Early host-delivered findings are appended independently of terminal results. Interruptions,
  retries and notes never erase them. No streaming tool interface is invented.
- Supplemental admission needs actual host capacity AND active observations. Reserve the
  known next required frontier and greater explicit Root demand, while protecting the
  full unused strong allowance. Observations are trusted inputs, not hard host enforcement.
- Acceptance cuts off a candidate epoch. A materially changed bound candidate can explicitly
  reopen supplementation within a still-open run; omitted nodes and all counters stay intact.
  This does not resurrect closed runs or make arbitrary external drift acceptable.
- Acceptance does not automatically interrupt useful probes. Bounded closeout records identify
  actual continuation ownership or observed stop requests. A record creates no receiver,
  invokes no tool and releases no resources. Unknown and expired handoffs stay visible.

## Adversarial review before coding
Examined: effort shadowing; false advisory/notes; unresolved duplicates; investigation-only
repair acceptance; promotion demotion; stale resolution; early evidence erased on interrupt;
next-frontier starvation; configured capacity confused with live observation; unlimited
candidate reopen; stop request confused with termination; old-contract reinterpretation;
and synthetic benchmark inputs falsely described as native execution.

New branches in the behavior have direct negative tests alongside the existing suite.
Instructions cannot prove semantic risk classification, source honesty or actual model identity.
The passive comparison tool validates supplied attestations and capture fingerprints only.
Its tests use synthetic data and perform zero model calls. Real hosted trials, non-author
model review and Windows installation must be recorded separately from container/CI tests.
