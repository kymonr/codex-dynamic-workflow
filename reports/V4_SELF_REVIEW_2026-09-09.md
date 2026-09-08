# v4 adversarial self-review — 2026-09-09

Reviewer: implementing Root, a separate source-inspection pass. This is self-review,
not a non-author model review or native multi-agent execution.

Scope: the v4 diff against 5462f3f0e32eaf654ecc67673c5dc1291166eda5; Runtime create/add,
admission, snapshot locks, completion, triage/promotion, finish/status and CLI; policy,
profiles, Skill references, package validator, generator and regression tests.

## Findings corrected

| Failure mode | Correction and evidence |
|---|---|
| Version bump silently disabled Runtime validation | Validator applies to every supported Runtime major; missing module, changed version and exec-write mutation tests pass. |
| v3 saved contracts rejected after bump | Explicit supported 3.0.0/4.0.0 read/recovery, unchanged contract hashes and old all-node gates; v3 compatibility regression passes. |
| Luna still eligible for required mainline work | New default contract requires strong Astra mainline; model/profile pair checks and dependency/verifier rejection tests pass. |
| Optional quota was only prose | Transactional per-run supplemental attempt count, retries/failures charged, full unused strong allowance protected; concurrency test admits exactly one when quota=1. |
| Luna could occupy the last host slot | Effective host/run capacity plus mainline reserve; unknown capacity queues probes; last-slot boundary test passes. |
| Optional readers could block the active writer | Disjoint snapshot roots matched against current candidate; packet/source locks use snapshot; readonly-probe/writer concurrency test passes. |
| Unfinished Luna still blocked the actual mainline acceptance | Separate acceptance receipt and execution/host cleanup; running probe does not block accepted mainline, but run remains open. |
| Failed/retried or late evidence could disappear | Root triage scans all attempts; promotion binds new required current-candidate Astra work; late evidence invalidates old receipt. |
| An old completed/optional node could launder promotion | Fresh required strong target, source coverage and snapshot equality are checked before linking. |
| Optional failure could be disguised as success | Separate omitted/failed/partial/interrupted states and coverage counters; no success rewrite or usage refund. |

## Residual boundaries

No remaining concrete blocker was identified in the examined source and deterministic
scenarios. This is not proof of completeness. Semantic coverage, decision correctness,
Root triage reasons and truthful host-capacity reports remain trusted-controller duties.
Filesystem hashes are observations, not an OS sandbox; unrelated processes/DBs are outside
cooperative locks. Model/profile receipt checks still require the actual host.

The minimum-three rule is a proactive Skill launch intent per meaningful task, not a
Runtime spawn operation or finish barrier. Tool availability, capacity, budget and distinct
useful directions may reduce actual launches and must be disclosed. No model-quality,
false-positive/omission-rate, monetary or wall-clock improvement is claimed.

Native Astra/Luna dispatch was unavailable in this chat. No CLI model fallback was used
in this continuation. The previous invocation's 401 is not an independent review receipt.
Native joint execution and non-author model review are not marked passed; publication
remains a reviewable draft change, not a claim that those additional gates were completed.
