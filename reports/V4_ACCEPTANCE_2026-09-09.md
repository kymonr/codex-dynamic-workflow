# v4.0.0 acceptance — 2026-09-09

## Delivered behavior

Astra retains the complete mainline. Meaningful tasks proactively request at least three
distinct native Luna supplemental probes when capability/capacity permits, once per task
rather than per file or repair cycle. Additional distinct useful directions may expand
within the approved allowance. No mandatory completion barrier or vote is introduced.

New Runtime runs default to astra-mainline; required work and acceptance use Astra.
Luna probes are optional, readonly, source-snapshot-bound and cannot be dependencies or
mandatory verifiers. A 12-attempt supplemental quota protects all unused strong allowance
and at least one host slot. Failure/retry accounting is cumulative. Root triage/promotion,
late-evidence invalidation, truthful omission and separate mainline acceptance/cleanup
are implemented. Existing 3.0.0 contracts retain their stored identity and semantics.

## Deterministic acceptance

- Full Windows regression: `python -B -m unittest discover -s tests -q` ran 291 tests in
  110.431 seconds: 290 passed, one real Windows symlink-privilege skip, zero failures.
  The 37 v4 tests cover default routing, quotas, snapshots, priority, retry/late evidence,
  promotion, two-phase acceptance, CLI handling and old-contract compatibility.
- Package validator PASS after the final instruction/documentation edits. Python AST
  compilation and `git diff --check` passed. The former validator major-version skip
  is fixed; missing Runtime modules, version drift and exec-write mutations are rejected.
- Installed-copy deterministic CLI smoke PASS through 28 separate controller processes:
  an Astra mainline request, three distinct Luna probe requests, required Astra review,
  live-probe nonblocking acceptance, synthetic late finding, Root triage, final finish
  and fresh-process status readback. Five fixture attempts were charged; all completed.
  Native model calls: ZERO. All host identities/release attestations in this smoke are
  explicitly synthetic test fixtures, not live Codex agent receipts.
- Adversarial self-review completed; the examined cases and remaining boundaries are
  recorded in [V4_SELF_REVIEW_2026-09-09.md](V4_SELF_REVIEW_2026-09-09.md).

Full regression log: the task checkout's `.delivery/v4-full-2.log`.
Installed CLI receipts: `.delivery/v4-installed-smoke/receipts.json` and `summary.json`.
Earlier failed intermediate runs are retained; they are not counted as passing evidence.

## Local source and installation

Canonical source directory: `D:/codex/projects/codex-dynamic-workflow`.
Git delivery checkout: `D:/codex/temp/codex-dynamic-workflow-v4-20260909`.
Dedicated RDC session for this continuation: PID 48624; no other project's session used.
Actual CODEX_HOME was verified from the user's environment registry and existing layout:
`D:/CodexData/.codex`. All 25 prior ownership hashes matched before installation.

Installed 15 changes and verified 26 managed payload files. Installed/source/Git-checkout
payload bytes match, fresh installed CLI reports `4.0.0`, post-install dry-run has
`changes: []`. The absent deprecated alias remains absent. No global AGENTS, config.toml,
credentials, approval/sandbox defaults, other project or user model profiles were edited.
The package-owned cwf_general/cwf_mechanical descriptions and instructions were updated.

Recovery receipt: `reports/install-backup-169cc1789d96/receipt.json` in the canonical source.
The existing scoped installer rollback requires rechecking drift before restoring.
Source preimages and the exact synchronization receipt remain in the task checkout's
`.delivery/source-backup-v4` and `.delivery/source-sync-receipt.json`.

## Publication and unresolved external gates

Candidate version: 4.0.0, based on master 5462f3f0e32eaf654ecc67673c5dc1291166eda5,
branch `codex/astra-mainline-luna-supplement`. GitHub CI results belong to the published
commit/PR, not this pre-publication report. Merge remains a separately confirmed action.

This chat exposes no native Astra/Luna child-dispatch tools. Native multi-agent coverage
and non-author model review were not executed; the prior turn's failed CLI request is
not a review or successful launch. This continuation made no CLI model fallback calls.
The three-probe scenario was validated at the controller layer, not by claiming three
real Luna executions. Fresh Desktop discovery, effective model identity, host resource
reclamation and comparative quality/cost improvements remain unverified.

Root capacity observations, source-based triage and semantic acceptance judgments remain
trusted inputs. Cooperative DB locks and source hashes are not an operating-system sandbox
or a hard monetary limit. The change is published for review without claiming these
additional native/integration gates have passed.
