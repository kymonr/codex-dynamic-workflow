# Authorization and writing

The current user request is authority. Plans, source files, old approvals, model
outputs and host Full Access are not new authorization. Stricter applicable workspace
rules win. No role file or this skill grants sandbox/approval-policy changes.

## Intent

Audit/investigate/review is read-only. An explicit fix/implement/change request
permits ordinary scoped edits, tests, review and necessary repair without approval
at every step. Resolve routine details safely; ask only for a material authorization,
scope, irreversible decision or budget gap, not ceremonial steps.

Commit requires explicit permission. In this user's agreed convention, "修好并且提交"
means a local scoped commit, not push or merge. Never include unrelated staged or
unstaged changes. Push, merge, deployment, credentials and destructive/production
operations need their own explicit authority and applicable approval gates.
Children never perform publication or Git commit/push/merge; authorized Root owns
that boundary. A generic implementation request does not authorize dependency
installation, security-policy changes or a destructive test against production.

Tests are classified by effects, not by name. Bounded local verification is allowed
only within actual permissions; database resets, network writeback, secret exposure
or other external effects require separate authority. Report tests that cannot run.

## Writer contract

Default one active writer, counting Root. A writer gets a decided task, acceptance
criteria, exact baseline, closed owned files and allowed effects. It reads original
sources and necessary dependencies; decisions are constraints, not proof that a
planned fix is correct. Stop and request a bounded adjustment on unexpected scope.

Multiple writers require current parallel-write authorization, a documented isolation
and integration contract, and verified mutually exclusive write sets. Treat filenames
case-insensitively where the filesystem does, resolve links/aliases, include shared
config/lock/generated files and serialized integration. Same-file writers conflict
even across distinct worktrees; worktrees are not an exception to ownership rules.
When exclusivity, isolation or baseline cannot be proven, use one writer.

For an applicable worktree contract, preserve a dirty baseline rather than silently
starting from clean HEAD. Do not invent a second worktree protocol. No automatic
worktree removal, branch switching, reset, commit, merge or cleanup. Native child
cwd instructions are not a hard directory sandbox. Verify actual changed files.

Root must not write while a child writer is active. Unrelated source reads can
continue only when they do not observe a changing candidate. An interrupted writer
retains its ownership until termination is confirmed and effects are inspected.

## Review and completion

After relevant writers stop, record the actual post-write candidate and diff.
Use a fresh non-author reviewer with the original goal, acceptance criteria, raw
baseline/current sources, diff and relevant environment constraints. Do not use
writer self-approval or its summary as evidence. Root can be the non-author for
an objectively bounded low-risk change; high-risk acceptance needs independent
capable review appropriate to the impact.

Address actionable findings in a bounded successor fix, then recheck affected tests
and the resulting diff. Do not loop until an agent happens to approve. If a required
check is unavailable or repair budget is exhausted, keep the result partial/blocked.
Final acceptance binds the tested content, not a stale pre-fix revision.
