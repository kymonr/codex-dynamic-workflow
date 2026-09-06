# Runtime lifecycle and installation acceptance — 2026-09-06

The installed Runtime passed the bounded acceptance described below. These results supersede earlier native-readonly and regression coverage statements only within the stated scope; historical failed/blocked reports remain unchanged.

## Candidate and deterministic checks

- Existing remote baseline: `e07d4a7b0ec4dce8155995b6dda350be71972a1a` on `master`.
- Real-model smoke used installed Runtime core SHA256 `fbec9deffb4c47d5cf64cae453fc81f18011da8f9f9d868fb9ffce87efcfb280` before the final native-only clock precision correction. Final installed/source core SHA256 is `2a1e29d42533781aab8a125fccec2638856f5403b6915dfba6930f40c08a6419`.
- Installed exec adapter SHA256: `02a571eb9780441bfaf136518bae61111bfd1d2d831c74c7811e2b76b2649688`.
- Git distribution uses the existing LF line-ending policy. Its text is identical to the final installed candidate after newline normalization; core SHA256 is `db35d552c570c0541d2e2ed375b277b4da681c5c26ffdf1489a96ccd2b6f5cb7` and executor SHA256 is `bf7d241b0ce21eec8a7b53341537a81174a46028cca29ad3667d21a4379a9699`.
- Final normalized Git distribution on Windows Python 3.12: 218 deterministic tests executed, 217 passed, one symlink-creation case skipped for missing privilege; 49.064 seconds.
- Package validation passed. The installer verified all 22 currently managed files, with no pending changes; the already-retired legacy entry stayed disabled.
- An independent source review and in-memory probes found no remaining scoped blocker in the five external-review repairs. The reviewer did not claim actual model, process-tree or installer-write validation from those probes.

The pre-commit full suite exposed a clock precision flake in native readonly receipts. A first integer-microsecond adjustment still failed across floating-point boundaries and was rejected by independent review. The final correction allows only one microsecond plus one floating-point ULP at the completion lower bound, retaining strict future rejection. Original and crossing-boundary counterexamples are now deterministic regressions; the final complete suite passed. No exec code path changed after the one-call real-model smoke.

The precision reviewer passed two in-memory boundary tests and 10,000 synthetic 100ns samples. One initial real-time sampling probe reported 821 rejects without classifying or saving counterexamples; 60,000 subsequent classified samples did not reproduce it. That isolated sampling result remains inconclusive rather than being erased or called a pass. Root's separate 10,000 classified acceptance samples had no rejection. These observations are bounded checks, not a guarantee against all system clock adjustments.

## Installed Runtime with real local processes

`scripts/verify_installed_process_flow.py` imports the installed Runtime and runs its real gated worker and owned-process cleanup against deterministic local emitters. It does not launch a model or modify host ACLs.

| Scenario | Observed result |
|---|---|
| Normal exit with a sleeping descendant | Completed; Windows Job accounting reached zero active processes |
| U+0085, U+2028 and U+2029 in JSON content | Completed; characters preserved in the accepted stored result |
| Malformed JSONL | Failed result; confirmed process resources released |
| Oversized JSON integer | Ordinary ValueError retained as failure; resources released |
| Injected source PermissionError after transport return | Interrupted/unaccepted; resources released; parsed usage retained |
| Actual process timeout | Interrupted; owned process tree cleanup confirmed |
| Injected loss of the transport return | Initially retained running hold; controller reconciled only after observing actual cleanup |

All seven cases passed. Every case retained one charged attempt; all were settled with zero execution/resource holds at the end. Readonly reopening of the SQLite status and events matched exactly, and the source fixture remained unchanged. Negative cases were cancelled after their acceptance check, preserving failure history.

Two earlier harness runs stopped on test-script mistakes: an incorrect saved-result field, then double-decoding a Unicode fixture. Those failures were not product failures and were not counted as successful acceptance. The corrected full run passed all seven scenarios; earlier local databases remain preserved.

## One actual readonly model call

`scripts/verify_installed_exec_smoke.py` made one explicitly authorized real Codex exec call through the installed Runtime, against a small harmless arithmetic fixture. No retry or additional exec-model call was made.

- Run ID: `87375da10c4d49c6a3ff303efa298656`.
- Attempt: `4575cc881a2e43fc8fe52ad7a241c63a`.
- Requested model/effort: `gpt-6-astra` / `high`; effective model identity was not independently exposed and remains UNKNOWN.
- The model directly read the assigned fixture and correctly reported documented 90 versus actual 110.
- Final state: completed, full declared scope complete, no drift, current evidence valid.
- Charged attempts: 1; execution holds: 0; host-resource holds: 0; resource state: RELEASE_CONFIRMED by the exec transport.
- Observed usage: 85,636 input tokens, including 28,160 cached input tokens; 410 output tokens. These counters are not a monetary-cost or model-quality claim.
- SQLite status/events reopened identically and the source remained unchanged.

## Native boundary and publication contents

A prior actual two-agent native readonly run passed installed CLI admission, distinct host identity binding, original-source inspection, independent verification, host completion observation, finish and SQLite reopen. Its execution holds were zero while two resource reservations remained UNKNOWN. The updated Runtime reopened that database consistently.

The current collaboration surface still provides no physical close receipt. Native writer completion/recovery and native physical resource reclamation were not qualified by this acceptance. Exec cleanup evidence does not replace those native-host observations. OS sandbox denial was not tested.

Only source, tests, these reusable acceptance scripts and this portable summary are intended for publication. Raw model streams, local SQLite files, installation backups and machine-local task records remain local.
