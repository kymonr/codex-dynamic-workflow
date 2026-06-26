# Team Router Compounding Log

This is the project-level compounding ledger. Keep reusable lessons here when a task reveals a repeatable process, role, permission, verification, or workspace-risk rule.

## Recording Rule

- Record durable lessons that should change future Team Router behavior.
- Prefer generic rules over dated incident stories.
- Link the rule to the files/tests that enforce it.
- If closeout says `compoundingDecision: recorded`, this file should be updated or the closeout must explain why the record is pending/blocked.

## Entries

### Manager Overreach, Lightweight Flow, And Role Callback Discipline

- Trigger: manager wrote or attempted to write files during active Manager Mode, a narrow mechanical fix expanded into too many roles, and a role completed key checks without proactively returning the expected protocol block.
- Rule: active Manager Mode does not self-write durable lessons or implementation files unless the user explicitly switches role and authorizes that exact file change.
- Rule: narrow mechanical fixes such as CRLF/LF normalization should not default to executor -> reviewer -> verifier; use executor plus either reviewer or verifier unless semantic/process risk appears.
- Rule: any role that completes key checks must proactively return the final protocol block by direct-send and self-thread fallback; it must not rely on parent polling or parent follow-up.
- Rule: after bounded wait/read with no final protocol block, manager CONTROL must request only scope-limited closeout from already-confirmed facts.
- Enforced by: `skills/codex-team-router/SKILL.md`, `skills/codex-team-router/references/manager-mode.md`, `skills/codex-team-router/references/manual-orchestration.md`, `skills/codex-team-router/references/role-closeout.md`, `src/team_router.py`, and `tests/test_team_router.py`.