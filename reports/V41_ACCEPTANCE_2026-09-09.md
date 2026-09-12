# v4.1.0 acceptance - 2026-09-09

Baseline: e5f3d6e9b15419724ff6eda5b46a657f61016c58, PR #41.
This report separates deterministic implementation acceptance from native execution.

## Delivered
Exact fixed model/profile/effort consistency, atomic screening and evidence-linked
semantic duplicates, explicit review/repair issue outcomes, incremental findings,
known next-mainline capacity reservations, changed-candidate supplementation, and
bounded host closeout observations. The >=3 meaningful-task Luna launch intent remains.
No wait-all barrier, automatic background receiver, automatic kill or budget reset.
Saved 3.0.0/4.0.0 contracts retain their original identity and behavior.

## Actual validation
- Container/Linux: 353 tests, 352 passed, one Windows-only skip, 23.197 seconds.
- User Windows: 353 tests, 351 passed, two skips, zero failures/errors, 89.318 seconds.
  The only conditional skips are symlink creation privilege and unavailable 8.3 aliases.
- Added 60 tests: 48 v4.1 follow-up/package cases and 12 passive comparison cases.
- Package validator, full-diff whitespace check and source review: PASS.
- Implementing Root performed a second full diff review, fixed findings and reran tests.
  This is self-review, not a non-author model review; see V41_REVIEW_2026-09-09.md.
- Installed controller smoke: 39 independent CLI processes, PASS, run
  561b5bff8b744e28ae03aed31b254815. Three distinct supplemental route requests,
  early reports, advisory/duplicate screening, promotion, explicit review resolution,
  mainline acceptance with running probes, closeout records and fresh-process readback.
  All identities and lifecycle receipts were SYNTHETIC. Native model calls: ZERO.

## Source and installed state
Canonical source: D:/codex/projects/codex-dynamic-workflow.
Git checkout: D:/codex/temp/codex-dynamic-workflow-v4-20260909.
Dedicated RDC session: PID 46504; other project sessions were not used or terminated.
CODEX_HOME was read from the single User environment variable and confirmed against
existing ownership state: D:/CodexData/.codex. Only task-process environment was set.

First installer dry-run refused externally changed agents/cwf_writer.toml. Inspection
showed its version-neutral text already exactly matched this candidate; all other 25
owned files matched prior ownership. Only this identical file was explicitly readopted.
Normal atomic installation then completed: 14 changed/ownership entries, 28 verified files.
No in-place exception, ACL change, authentication or global config change was used.
Installed CLI reports 4.1.0; normal post-install dry-run has changes: [].
Deprecated dispatching-native-agents remains disabled and was not reinstalled.
Recovery receipt: canonical source reports/install-backup-e01ab67766f0/receipt.json.
The existing installer rollback must recheck drift before restoring this scoped receipt.

Local evidence in Git checkout .delivery: v41-windows-tests.log, v41-install-dry-run.json
(initial refusal), v41-install-dry-run-adopt.json, v41-install-apply.json,
v41-post-install-dry-run.json and v41-installed-controller-smoke/receipts.json.

## External validation still open
Codex CLI 0.153.4 identity and version-specific app-server schema generation were observed.
A tool safety check blocked writing the next native preflight helper. No alternate route
was used to bypass that block. Native RPC/model execution, effective Astra/Luna identity,
non-author model review, fresh Desktop activation and paired quality/cost trials remain
NOT_RUN or UNKNOWN; see V41_NATIVE_COMPARISON_STATUS.json and the native validation protocol.
CI results must be read against the published commit. Keep PR #41 draft; no merge,
Release/tag, deployment, global policy update or branch cleanup is part of this delivery.

## Final byte alignment and installed rerun
The non-Git canonical source applied this text patch using CRLF, while the reviewed Git
candidate uses LF. Only the 30 paths in this task's delta were checked for exact text
identity and aligned to the Git candidate bytes; no unrelated source files were replaced.
The installer then applied the 14 affected entries through its normal atomic mode again.
Final recovery receipt: reports/install-backup-24e68364e92e/receipt.json in canonical source;
the earlier e01ab67766f0 receipt records the initial v4.1 upgrade before newline alignment.

All 28 installed payload files now match BOTH canonical source and the Git candidate.
Final normal dry-run again reports changes: [] and legacy_enabled: false.
After alignment, 39 fresh installed-controller CLI processes passed again, fixture run
cc0bc4744f8047d9a52731527de97b74, with receipts in .delivery/v41-final-installed-controller-smoke/.
Native model calls remain 0. Local source alignment and installer logs are preserved.
