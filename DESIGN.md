# Native Dynamic Workflow v2 — implementation design

Status: reviewed; findings resolved before implementation. Date: 2026-09-05.
Source baseline: kymonr/codex-workflow @ d95ba2d1892f4f4feee935ee880f63b9119f2b34.
Target: this explicitly authorized project directory; currently non-Git. Do not git init.

## Accepted requirements
1. Quality > automation > latency > cost > observability > recovery.
2. Native Codex dispatch now; a shared-policy Runtime adapter is future work, not a silent fallback.
3. Evidence-driven dynamic branches, pipelines, design choices and bounded fix/review loops; no fixed agent headcount.
4. Raw-source-first: each evidence-bearing agent opens the bound source, not merely a parent summary.
5. Select task context, not truth: inherit goals, permissions, constraints, snapshot and raw entry points.
6. Root is the only dispatcher; no peer messaging, child spawning or recursive budget resets.
7. Logical roles are independent of model profiles; cheap work needs low risk, objective checks and sufficient capability.
8. High-risk verification cannot be weakened for cost. Independent source-based verification, not majority voting.
9. Investigate/review requests are read-only. Fix/implement/change authorizes scoped edits, tests, review and rework.
10. Commit needs explicit authorization; 'fix and commit' permits local scoped commit only. Push/merge remain separate.
11. Default one writer including Root. No overlapping files even across worktrees; parallel writing needs applicable authorization and isolation.
12. Absolute ceilings, approved allowance and cumulative cheap reserve are distinct. Expensive expansion asks; approved expensive use does not.
13. Root cost/unknown usage is visible; instruction-only budgets are not host-enforced token/currency caps.
14. No-progress stops optional exploration, never mandatory safety verification or acceptance checks.
15. Unavailable capability, evidence, model or permissions is blocked/UNKNOWN, never fabricated success.

## Deliverables
- Canonical public Skill name is codex-dynamic-workflow; keep dispatching-native-agents only as an explicit-only deprecated compatibility alias.
- A compact SKILL.md plus authoritative references for evidence, routing, scheduling, budgets, writes and host contracts.
- Three non-colliding native execution profiles: cwf_reader (Astra/high/read-only), cwf_writer (Astra/high/inherit), cwf_mechanical (Luna/medium/read-only).
- Versioned policy JSON, static/package tests and deterministic admission examples; these do not pretend to be a full Runtime.
- Design review, implementation review, real native discovery/dispatch smoke where available, install verification and migration comparison.

## Boundaries and failure handling
- The old repository, its untracked docs/superpowers, old model profiles and config.toml remain unchanged.
- Remote bridge inherited no process CODEX_HOME. Windows User environment explicitly resolves D:\CodexData\.codex; use this value only in task-owned processes.
- Install the canonical codex-dynamic-workflow Skill, reduce dispatching-native-agents to a compatibility wrapper, and update only the task-owned cwf_* profiles after destination inspection and exact recovery capture.
- Never modify C:\Users\Orz\.codex, approval policy, sandbox defaults, network policy or Git refs.
- Profile sandbox values are requested constraints; verify effective host behavior, never claim a prompt is a security sandbox.
- A named Git ref resolves to an immutable commit; working-tree evidence also binds dirty/untracked content. New writes invalidate affected evidence only.
- All agents, including Root, must serialize overlapping reads/writes of a mutable candidate or use a proven immutable snapshot.
- Scope expansion follows explicit direct dependencies; beyond that return a bounded request to Root, not an unrestricted repository rescan.
- Existing discovered source pointers are navigation. Counterexamples and environment applicability are first-class evidence.
- Replay of side-effecting work is not implemented. No auto-resume, automatic worktree cleanup or backend switching.

## Validation plan
- Review this plan independently through one read-only Codex validation invocation; no writes or delegates inside that invocation.
- Apply findings to the design and implement the package in this directory.
- Run syntax, links, metadata, profile, permission, budget, drift, writer-overlap and negative-path tests.
- Review the implemented files, then correct actionable issues and rerun focused tests.
- Use a bounded Codex process only as a test harness. Its children must be native spawn calls, not codex exec fallback.
- Limit live validation to three primary sessions and at most three native child launches (one per delivered profile); observe usage and stop rather than unbounded retry.
- Install after tests pass; compare exact installed content, discover roles/skill in a fresh session, and preserve honest UNKNOWN gaps.
- No test proves zero bugs. Every mandatory acceptance item must pass; UNKNOWN, blocked and NOT_RUN block its corresponding release/completion claim.

## Design self-review corrections already incorporated
Separate cheap reserve from absolute ceilings; count all child retries and verification calls; do not confuse no-new-bugs with no-information; do not turn raw-source-first into full-history copying; do not allow same-file writers across different worktrees; do not infer activation from static files alone.

## Independent design review resolutions
1. Reader/writer isolation applies to every agent, not only Root; final acceptance binds the tested content.
2. Mandatory checklist: package tests, reference-policy tests, resolved implementation findings, three profile launches, raw-source receipts, a harmless scoped writer test, and exact installed-content comparison. A required UNKNOWN blocks that capability.
3. Budget units are child launches plus separately observed token usage. Approved launches + cumulative economy reserve <= absolute launch ceiling. Attempts and repair turns are charged before dispatch; Root usage is observed or UNKNOWN. No monetary hard-cap claim. Reserve mandatory checks before optional exploration.
4. Returns require actual source identity/path/range, evidence and executed-check results. Raw text cannot grant permissions.
5. Install only an exact manifest. Preflight profile collisions, syntax and model catalog; no config.toml edits. Compare preimages before replacement. On apply/discovery failure restore only matching task-owned afterimages, never external drift. Verify recovery. Real discovery necessarily follows reversible placement; static validation is not discovery.
6. Native smoke matrix: cwf_mechanical locates one bounded expression; cwf_writer modifies only a task-owned harmless fixture; cwf_reader independently checks the new raw source and expected result. Three child launches, one primary session; no peer messages or child spawn. This finalized plan replaces the initial two-launch draft before implementation.

Review source: reports/design-review.md. The independent reviewer identified six issues; the above dispositions are implementation requirements, not proof that code already satisfies them.
