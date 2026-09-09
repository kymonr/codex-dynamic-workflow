# Astra mainline and supplemental Luna coverage

For new 4.1 contracts, [followup](followup.md) refines screening, issue resolution,
capacity and candidate epochs. The earlier 4.0 behavior below remains the compatibility
contract for saved 4.0 runs; it is not the full 4.1 operational contract.

## Responsibility and proactive coverage
Astra retains the complete mainline, including required investigation, implementation,
testing and acceptance. Luna provides additional omissions, counterexamples, test gaps
and alternative explanations. Deleting the supplemental graph must leave a complete
mainline. Meaningful tasks normally launch at least three distinct Luna probes early.
The floor is per task, not per turn, file or repair cycle; it is not a waiting barrier.
More probes are encouraged for genuinely new directions, within the selected allowance.
Trivial scope, fewer genuine directions, host/capability limits, cancellation or budget
pressure permit fewer, with explicit coverage accounting. No repeated questions to fill a quota.

## Model, quota and capacity
New Runtime contracts default to workflow=astra-mainline. Mainline nodes use the strong
Astra route; writer and required reviewer remain on Astra. Supplemental nodes use Luna,
are optional, cannot write, cannot declare verifies, and cannot be dependencies of any
mainline node. Legacy selection is explicit and must not silently override the new choice.
Default approved/absolute limits are 28/32, strong allowance 8, supplemental allowance 12.
The economy reserve remains 4 for legacy compatibility. New supplemental attempts cannot
use it or exceed their own 12-call allowance. Failed attempts and retries still count.
The scheduler protects all unused strong allowance, not just already declared checks.

Ready mainline nodes are considered before all probes, including optional mainline work.
At least one host slot is reserved for Astra. A stricter run capacity is respected.
For null run capacity, next needs an actual --host-capacity observation before Luna can
be admitted; --host-active includes other open host threads. Unknown capacity queues Luna.
Host observations are trusted controller inputs, not independent enforcement by this library.
The library cannot prevent unrelated processes or a caller lying about host state.

## Snapshot contract
Each supplemental node names a canonical, non-link snapshot_root in a directory tree
disjoint from the live root. Its sources must match the live candidate at add time.
Include relevant uncommitted edits, not only HEAD. Paths, size, links and credentials
are validated by the existing source checker. The packet root is the isolated snapshot;
candidate_root identifies the live source. Snapshot readers therefore do not lock mainline
working files. The Root prepares snapshots; the runtime does not copy arbitrary files.
Snapshots stay fixed; refresh is rejected for them. New bytes need a new probe identity.
Results are evidence about their snapshot, never proof that later working bytes are correct.

## Evidence triage, not majority voting
Return compact candidates with source/range, reproducible check, possible impact and
uncertainty. Prefer three high-value evidence cards; record additional material leads as
uncovered scope. Semantic deduplication and triage belong to Root, not a vote-count rule.
No automatic Astra review per Luna turn; only meaningful received claims need attention.

Runtime triage accepts dismissed, advisory, or promoted with a nonempty Root reason.
Dismissed/advisory decisions bind the current live evidence files; later byte changes
make those decisions stale. They are trusted Root judgments, not a proof of correctness.
Promoted claims link a never-executed required Astra node covering their current evidence.
The linked node must complete and satisfy normal gates. It does not depend on Luna.
Previously completed/optional/Luna work cannot be reused to launder a new finding.
All returned claims, including failed/partial attempts, remain visible and need triage.
Direct decide does not replace supplemental triage. A credible unresolved acceptance
risk must be promoted or remain unresolved; advisory is not permission to hide that risk.

## Acceptance and cleanup are separate
finish validates all mainline work and received-claim triage, omits pending probes,
records mainline.accepted and stops further supplemental admissions. A live supplemental
turn does not block this mainline acceptance. The run remains open until execution is
actually reconciled; host-resource holds remain independently reported.
Mainline repairs may still be added, and invalidate the old acceptance receipt.
Late new claims likewise invalidate mainline_accepted until triage and another finish.
After all execution is reconciled, finish sets status=completed; unknown native thread
closure is still reported, never converted into released capacity.

scope_complete retains its literal all-node coverage meaning. mainline_complete is
structural; mainline_accepted additionally needs current evidence, gates and a matching
acceptance receipt. supplemental_coverage reports launch/attempt/completion/omission counts
and each actual state. Failed/partial/interrupted probes are not rewritten to PASS.
A supplemental-only graph never qualifies as an accepted mainline.

## Compatibility and limits
Saved 3.0.0 contracts reopen with exact stored hashes, routes, budgets and original
all-node completion semantics; new fields are not inserted into old records. No schema
migration, budget refund or writer replay occurs. Explicit legacy runs preserve the old
routing/optional semantics for compatibility; new CLI and Python calls default to v4.
The public CLI stays native-only. Historical Python exec adapters are retained for
regression/inspection and are not a supported model fallback.

Deterministic tests exercise SQLite, source snapshots, host receipt fixtures and CLI
contracts. They are not native model calls, independent model reviews, sandbox proofs,
cost benchmarks or proof of comparative task quality. Skill-only remains the normal mode;
Runtime is selected for persistent coordination, not imposed on every small task.
