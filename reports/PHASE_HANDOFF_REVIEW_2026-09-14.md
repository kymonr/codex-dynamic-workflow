# Phase handoff and nonblocking Luna guidance — 2026-09-14

## Candidate and authority

Baseline: `b132e12efb01eefe4c4e0b33cd3fe3a82342b221` on remote master.
The existing local project was an older non-Git source copy. Changes were made in a
new dedicated task checkout; the old source, its delivery checkouts and installed
files were not overwritten. This is an uncommitted local candidate, not a published
or activated release. Runtime and Skill metadata remain 4.2.0; the instruction
revision is dated 2026-09-14.

## Delivered scope

Explicit Skill-only work now prefers an Astra plan and evidence-based acceptance
brief, a user/host switch of the main conversation to Sol for continuous execution
and Luna screening, and a fresh Astra review context for important deliverables.
Root authority is separate from the Sol writer-child profile. Source identities,
permissions, pending claims, active ownership, deadlines and cumulative allowance
survive handoff. Implicit mode remains Luna-only. No automatic host model switch,
Runtime migration, nested child dispatch or new orchestration service was added.

Luna coverage targets useful independent questions rather than headcount. Guidance
covers 6–12 directions where useful, exact snapshots, finite cutoffs, at most one
routine new-input follow-up, checkpoint screening, resource/queue backpressure,
full preservation of plausible risks, and bounded nonblocking closeout. Credible
risks may still block affected acceptance; a slow optional sibling alone may not.

A documented opt-in new-task bounds example permits 24 supplemental attempts inside
40 approved / 44 absolute calls, retaining 8 strong calls and 8 other approved calls.
This is not an automatic default increase, an account-credit budget or a concurrency
claim. Runtime code, schemas, routes, policy.json and saved-contract handling remain
byte-identical to the baseline. Observed credits include Root, triage and rework;
unknown usage is not zero and no price or quality-parity guarantee is made.

## Whole-diff self-review and fixes

The author reread all instruction/profile changes, the complete new test module,
README and changelog from a reviewer perspective, rather than assuming the proposed
design was correct. This is self-review, NOT independent non-author acceptance.

1. A commit-only brief would exclude non-Git projects. The final rule accepts exact
   source hashes or a bound snapshot and forbids Git initialization just for handoff.
2. A new conversation might not control children owned by the old conversation.
   The final rule requires actual ownership transfer or bounded observed closeout;
   unresolved resource holds remain UNKNOWN rather than being silently released.
3. The initial broad-probe regression completed a writer without changing a file.
   The final test performs an actual temporary-file write, refreshes the acceptance
   candidate and verifies that the still-running probe retains its old snapshot.
4. Added a synthetic isolated installation test to check full payload equality,
   unchanged unrelated configuration/role files, retired-alias preservation and an
   empty post-install dry-run. It does not access the user's real installation.

## Actual deterministic verification

Environment: Windows, Python 3.12.10. Test temporary files were directed to the
dedicated task area. No test invoked a native model or a CLI model backend.

| Check | Observed result |
|---|---|
| Baseline full suite | 463 tests: 461 passed, 2 environment skips; 76.375 seconds |
| Final new focused suite | 13 passed; 2.141 seconds |
| Final full suite after review fixes | 476 tests: 474 passed, 2 environment skips; 87.620 seconds |
| Package validator | PASS |
| In-memory Python compilation | 46 source files compiled |
| Diff whitespace validation | PASS |
| Runtime code and policy comparison | Byte-identical to baseline |

The two unchanged skips are Windows symlink creation without the needed host
permission, and an 8.3-path test on a volume without the required short-name alias.
Logs are in the task directory above this checkout: `baseline-tests.log`,
`review-fix-tests.log` and `final-reviewed-tests.log`.

The new tests exercise actual SQLite with explicitly SYNTHETIC host receipts:
24 supplemental attempts do not consume reserved review capacity; a slow probe
need not delay mainline acceptance; 23 clean reports do not erase a partial probe's
risk; reopened state retains spent attempts; source snapshots survive an actual
writer change. Text consistency tests are not natural-language enforcement.

## Unexecuted gates and delivery limits

A tool call intended to inspect the real installed Skill and its ownership state
was blocked by a tool safety check before returning those observations. It was not
retried through another route. No real installation, adoption, configuration change
or claim of live activation was made. Only a temporary synthetic install was tested.

This session exposed no native subagent dispatch capability. No native Astra/Sol/
Luna run, fresh non-author model review, physical native-resource release test or
comparative quality/credit measurement was performed. The synthetic tests do not
prove the host will enforce the cutoff, model identity, sandbox or independence.

No commit, push, pull request, merge, tag, branch deletion, global configuration
change or CLI model fallback was performed. Required live acceptance remains an
explicit gap; this report does not declare the user's installed workflow updated.
