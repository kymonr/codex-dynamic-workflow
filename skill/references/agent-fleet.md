# Native Agent Fleet contract

Agent Fleet is the native, user-visible deep-review mode for Dynamic Workflow. It preserves the adversarial sequence—discovery, challenge, reproduction, and final review—without a Fleet CLI, package runtime, run directory, or hidden `codex exec` processes.

## Selection

Select Agent Fleet when the user explicitly names Agent Fleet or naturally asks for a deep audit, comprehensive inspection, adversarial review, multi-agent verification, repository deep review, or equivalent work that requires independent challenge and reproduction. Ordinary requests such as “check this”, “look at this code”, or a normal multi-branch review remain Root-only or Simple Swarm.

Use only these total native-subagent sizes:

| Total | Native routes | Intended scope |
|---:|---|---|
| 4 | 3 Luna + 1 Sol | Small, bounded, lower-risk deep review |
| 6 | 5 Luna + 1 Sol | Default cross-file or cross-module deep review |
| 8 | 6 Luna + 2 Sol | Large or high-risk security, data, permission, concurrency, installer, release, or architecture review |

An exact unsupported count is a visible constraint conflict. Do not silently remap it to 4, 6, or 8.

Before spawning, disclose the workflow, total count, Luna/Sol mix, phase roles, and reason. Start immediately after that disclosure unless a higher-priority instruction requires confirmation. Show one normal `Subagent:` line for every child before its `spawn_agent` call.

## Native execution boundary

Every member is a fresh, top-level, UI-visible native subagent with a unique task name and `fork_turns=none`. All Fleet work is instruction-level read-only. Children may not write the repository, use credentials, message one another directly, spawn nested agents, expand scope, or perform Git/external effects. Root owns all coordination and final acceptance.

Root records the repository root, candidate scope, Git HEAD, worktree status, and changed-file set in the conversation before discovery. Recheck those facts at every phase boundary. Candidate drift stops the Fleet and makes unverified conclusions `UNKNOWN`.

Technical spawn/transport failure may replace the failed slot once with one fresh subagent after a visible replacement disclosure. A substantive negative result, disagreement, or failure to reproduce is evidence, not a retry reason.

## Phase allocation

### Four members

- 1 Luna discovery
- 1 Luna challenge
- 1 Luna reproduction
- 1 Sol final evidence and conclusion review

### Six members

- 3 Luna discovery with non-overlapping focuses
- 1 Luna challenge
- 1 Luna reproduction
- 1 Sol final evidence and conclusion review

### Eight members

- 4 Luna discovery with non-overlapping focuses
- 1 Luna challenge
- 1 Luna reproduction
- 1 Sol evidence/severity review
- 1 Sol system-level omission and conclusion review

Run phases in order. Do not spawn challenge, reproduction, or Sol review before Root has integrated the preceding phase.

## Finding lifecycle

Discovery returns bounded findings with location, claim, impact, evidence, confidence, and material uncertainty. Root de-duplicates them and assigns stable IDs such as `F-001`.

Challenge receives only Root-assigned finding IDs and attempts to refute each assigned claim. Reproduction independently verifies the still-material assigned IDs. Challenge and reproduction may not invent or silently rename finding IDs; new observations return separately to Root.

Root classifies each finding as proposed, challenged, reproduced, refuted, unknown, adopted, or rejected. Evidence outranks headcount. An independently reproduced severe finding cannot be outvoted by clean reports.

## Sol and Root judgment

Sol reviews do not have unilateral veto authority and do not repeat the full repository scan. They audit evidence quality, severity, shared blind spots, unresolved conflicts, and whether the proposed final conclusion is too optimistic or too severe.

Root makes the final decision, but every material Sol issue must appear in the final disposition as adopted, rejected, or `UNKNOWN`. Rejecting a Sol issue requires the original Sol claim, Root’s reason, and the code, test, or reproduction evidence used. Root may not silently omit it.

When Luna and Sol materially conflict and the available evidence cannot resolve the conflict, report `UNKNOWN`; do not present the candidate as proven safe. A reproduced severe issue remains a blocker until the authorized task explicitly resolves or accepts it.

## Evidence and completion

Native receipts, child results, live repository reads, and Root-run verification are the evidence surface. Agent Fleet no longer promises machine-validated candidate digests, closed JSON records, offline status reconstruction, or formal evidence packages. Use Managed Workflow when checkpoint/resume or persisted formal artifacts are explicitly required.

The final report states the selected scale and mix, candidate identity checked, each finding disposition, every material Sol disposition, limitations/`UNKNOWN`, and a concise routing summary.
