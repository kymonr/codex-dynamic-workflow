# Artifact-bound independent review

Review is an optional one-pass acceptance overlay, not another implementation branch, not an Agent Fleet, and not a default outer mode. Trigger one fresh reviewer only when the user explicitly requests an independent, fresh, second-party, or final acceptance pass, or a higher-priority owning rule requires it. Ordinary `review`, `inspect`, `check`, `审核`, `审查`, or `检查` wording does not trigger this lifecycle. Deep, comprehensive, adversarial, or multi-agent review wording may select Agent Fleet, but still does not select this dedicated-reviewer lifecycle. High-impact, architecture, or security work selects the Sol executor route and does not by itself start this reviewer. Context length, compaction, long logs, repeated failures, branch count, or root uncertainty alone do not trigger an independent reviewer.

## Candidate and lifecycle

A candidate is ready for package capture only when every node that can change the candidate or its acceptance package is terminal, root has integrated the aggregate candidate, planned pre-review critical verification is complete, effects are reconciled, writes are paused, and no known in-scope edit is queued. Limitations and `UNKNOWN` may remain and enter review; they do not block capture by themselves. Multiple branches produce one aggregate candidate review, never one Sol reviewer per branch. Capture a stable, bounded package containing goal/acceptance, authorization/scope/exclusions, captured Git `HEAD`, staged diff, unstaged diff, changed-file allowlist, full content of every in-scope untracked candidate file (or, for non-Git text, bounded full content/unified diff sufficient for exact reconstruction), a revision label, validation evidence, limitations, and `UNKNOWN`. Paths alone never identify a revision. No ordinary hash requirement is added.

The package is a temporary prompt payload, not a persisted artifact. From package capture through verdict adoption, pause all candidate writes. Any candidate file, reconciled effect, acceptance evidence, or limitation change invalidates every prior verdict, including `ship`. Capture a new package/revision and dispatch a fresh reviewer only when independent acceptance is still explicitly or authoritatively required; otherwise return control to the root.

Dispatch a fresh thread with the dedicated custom role `dynamic_workflow_sol_reviewer`, `fork_turns=none`, no nesting, instruction-level read-only, and no fix authority. A fresh context reduces contamination; it is not cross-model-family independence, filesystem isolation, permission isolation, or merge/deploy authorization. The reviewer may not install or discover a role, fix a finding, expand authorization, or perform adjacent work. A missing role or spawn failure returns root; there is no fallback to an unpinned Sol.

## Identity and sandbox evidence

The critical reviewer identity is exactly observed `model=gpt-5.6-sol`, observed `effort=xhigh`, a fresh spawn/thread handle not used by an earlier reviewer for the same candidate lineage, `fork_turns=none`, and (for future tasks) `agent_type=dynamic_workflow_sol_reviewer`. Resolve native spawn/details metadata first; use scoped child `turn_context`/session metadata only for runtime fields omitted by the native receipt; use config only as requested/configured evidence, never runtime proof. Missing or mismatched critical identity invalidates the record and returns root. Reviewer tier is observed natively when available; otherwise report the parent-derived tier as configured. Tier omission alone is non-critical.

Record `requested_sandbox` separately from `observed_sandbox`. Only native runtime metadata populates the observed field; role/config values are configured fallback. A wider or unavailable observed sandbox must be disclosed as `observed_sandbox=<value|UNKNOWN>` and read-only described as behavioral/instruction-level rather than host-enforced. A reviewer write effect stops the flow, is read back, and returns root.

## Exact reviewer record

Every reviewer dispatch prompt, this document, and the custom role instructions embed or link the same record. The output is exactly one JSON object, not the ordinary branch-delivery record:

```json
{
  "CANDIDATE_REVISION": "non-empty string",
  "VERDICT": "ship | fix-first | rethink",
  "FINDINGS": [
    {"priority": "P1 | P2 | P3", "summary": "non-empty string", "evidence": ["non-empty string"]}
  ],
  "EVIDENCE": ["string"],
  "EFFECTS": []
}
```

The object has `additionalProperties=false`; duplicate keys are invalid; all five fields are required; `EFFECTS=[]` is the only valid effects value. Every finding has a non-empty summary and at least one non-empty evidence string. The revision must exactly echo the package revision. `ship` is invalid with any `P1`; `fix-first` requires at least one `P1`; `rethink` requires a finding that states why the candidate design must be reconsidered. Missing/extra fields, duplicate/multiple verdicts, stale revision, parse failure, or non-empty effects are invalid and return root without adoption. Validation evidence and limitations must remain unchanged.

## Adoption and outcomes

Root adopts only when the candidate revision matches exactly, reviewer identity is valid, reviewer effects are empty, live state matches captured candidate material, and validation evidence/limitations are unchanged. Root then performs minimal acceptance: goal/scope, changed-file/effect scope, critical test evidence, the adoption conditions, and the valid verdict. It does not duplicate the full review.

`ship` permits root to finish only the currently authorized task. `fix-first` invalidates the old verdict and ends the automatic review lifecycle: return the findings to the root without automatically fixing, revising, or spawning another reviewer. If the user explicitly asks to fix the findings, the authorized writer may fix within scope and the root reruns critical verification; dispatch a fresh reviewer only when independent acceptance remains explicitly or authoritatively required. `rethink` returns to root with no automatic redesign. Stop semantically on scope/authority change, ambiguous effects, no new revision, repeated blocker without progress, reviewer/identity failure, or invalid verdict. Do not create a review loop merely to obtain `ship`.

Tabletop/forward tests must cover a valid `ship`, malformed record, stale revision, non-empty effects, `fix-first` returning to root without an automatic loop, an explicitly required fresh re-review after revision, native-first identity, quiet success, mismatch/`UNKNOWN` stop, and requested-versus-observed sandbox semantics.
