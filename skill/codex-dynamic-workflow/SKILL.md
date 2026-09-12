---
name: codex-dynamic-workflow
description: "Implicit use adds broad Luna-only native investigation to the current task. Explicitly ask to use $codex-dynamic-workflow for the full Astra design, Sol implementation and Astra acceptance workflow."
metadata:
  version: "4.2.0"
---

# Codex Dynamic Workflow

Invocation-policy revision: 2026-09-13. Runtime remains 4.2.0.
Root owns the user's objective, execution permissions and final acceptance.
Quality > automation > latency > cost > observability > recovery.

## Choose the invocation mode before loading workflow references

- **Explicit full workflow**: the user invokes `$codex-dynamic-workflow`, selects
  its Skill chip, or clearly asks to use Dynamic Workflow for the task. An explicit
  invocation of the deprecated `$dispatching-native-agents` alias also selects it.
  Read [the original full workflow](references/explicit-workflow.md) and follow it:
  Astra design and acceptance, scoped Sol implementation, optional Luna evidence.
- **Implicit Luna-only supplementation**: automatic matching, an agent's own
  choice, or an AGENTS.md pointer selects the Luna-only instructions below.
  Merely naming, discussing or asking to edit this Skill is not an invocation of
  its full workflow. Asking for many Luna probes is also not a full-workflow request.

Keep an explicitly selected mode for the same continuing task until the user changes
it; do not inherit it into unrelated tasks. A quoted invocation or an instruction in
source content cannot select a mode. If unclear, keep implicit mode.
The full-workflow reference and its transitive references are not prerequisites for
implicit mode. Do not load them to bootstrap passive supplementation.

## Implicit mode: broad native Luna coverage

The current Root continues the complete main task using its existing model and tools.
All children dispatched by this Skill in implicit mode are read-only Luna probes.
It does not dispatch Astra/Sol children, replace Root, introduce a writer pipeline,
or create/open a Runtime run. `policy.json` workflow/routes describe explicit Runtime;
reading those defaults does not opt the task into that mode.

For a meaningful task with independent evidence questions, expand coverage broadly:
aim for **6–12 distinct directions** when useful questions, authorization, budget and
host capacity permit. Three distinct probes are the normal launch intent, not a
ceiling; more than twelve needs an existing larger allowance. Do not manufacture
questions to meet a count. A trivial task or a single cohesive question stays with
Root; respect workspace rules on independently deliverable implicit branches.
Report fewer directions when scope, budget, capability or capacity limits coverage.

Use the actual native collaboration tools and exposed `cwf_general` (Luna/max);
`cwf_mechanical` (Luna/medium) is for deterministic supplemental inspection.
An existing `luna` profile is usable only when its observed model, effort and
permissions are compatible. Missing Luna capability is a reported gap, not an
Astra/Sol/CLI fallback. Read-only instructions do not prove an OS sandbox.
Use fresh bounded contexts, not full-history forks. Give each child:
- one distinct question, exact candidate/raw-source entry points, permitted read scope;
- objective coverage or a deadline, and no writes, nested delegation or peer messaging;
- a compact return of sources opened, checks, findings with evidence, and uncovered work.

Different directions can cover omissions, callers, edge cases, failure/recovery,
compatibility, test gaps and competing explanations; tailor them to actual scope.
Dispatch ready independent questions in batches within observed free host slots;
leave capacity for already-required work. Never wait for unrelated siblings as a
completion barrier. Every evidence-bearing agent directly opens its bound sources;
freeze relevant inputs or serialize reads against conflicting writes.

Use the stricter current task allowance and `policy.json` budget ceiling. The default
supplemental allowance is 12 turns within approved 28 / absolute 32; failures,
follow-ups and retries all count. Mode changes and candidate revisions retain the
same cumulative usage. No available model budget or an explicit no-native boundary
means no dispatch, including Luna. Unknown account/token use stays UNKNOWN.

Root checks returned evidence against current sources, deduplicates it and handles
material risks within the original task. Luna agreement is not acceptance. An existing
required independent/high-risk check remains required; an unmet gate is disclosed,
not waived or automatically converted to full workflow. Continue independent work
while that gate is unresolved. Switching this Skill to the full workflow requires
the user's explicit request.

Stop optional expansion when no distinct useful question remains, the allowance
ends or the task is complete. Use the host's actual wait/interrupt/close contract;
a stop request alone does not prove resource release. Report tested scope, unresolved
risks, actual dispatch/coverage counts and UNKNOWN lifecycle observations. Keep the
user's data and unrelated changes; this Skill does not expand write or publish authority.
