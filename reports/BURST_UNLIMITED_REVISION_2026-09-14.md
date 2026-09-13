# Burst unlimited revision — 2026-09-14

This revision supersedes only the Burst-specific lease/count/time limits documented in
`BURST_REVIEW_2026-09-14.md`. Historical evidence there remains a record of the prior
candidate, not the current policy.

Current Burst policy is manual `enabled` on/off, explicit Skill-only, native OpenCodex,
`cwf_burst_grok` / `xai/grok-4.6` / high / read-only. It has no automatic expiry,
per-task attempt count, follow-up count, or per-turn wall-clock ceiling. Calls are
observed separately when possible and do not consume Astra/Sol/Luna launch-count ceilings.

Nonblocking quality gates remain: Grok is optional, cannot write or accept, cannot replace
required Astra review, and cannot make the mainline wait. Source/privacy checks, exact
profile matching, fresh host observations, provider availability, mainline slot reserve,
and resource/backpressure checks still fail closed for new optional dispatch.

Luna rules remain separate: package-owned Luna profiles still request 1M Fast and retain
their existing bounded supplemental behavior. Runtime 4.2.0 routes, `policy.json`, saved
contracts and Astra/Sol/Luna accounting are byte-identical to the pre-revision candidate.
## Verification and installation

Focused unlimited-Burst tests: 15 passed. Package validation and `git diff --check` pass.
Full Windows regression: 491 tests, 490 passed, one environment skip, 122.889 seconds.
The skip is environment-dependent and did not fail the suite.

Runtime `policy.json`, `cwf_runtime/core.py` and `cwf_runtime/policy.py` remain byte-identical
to the pre-revision candidate. The first apply attempt used PowerShell's read-only `$HOME`
name by mistake and was safely rejected before writes; the corrected apply used the exact
`D:\CodexData\.codex` home.

Actual install updated 10 managed files and verified 35. Recovery receipt:
`reports/install-backup-5bd9efaf3af6/receipt.json`. Global config, OpenCodex catalog and
separately owned user profiles were unchanged across the install. Post-install dry-run is
empty and all 35 installed managed files match source bytes.

An installed-helper synthetic admission returned `allowed=true`, read-only/non-accepting,
with no `stop_at`, task/Burst usage counter or follow-up counter in its result. This is a
zero-model policy smoke only; effective Grok execution and Luna 1M Fast backend behavior
remain dependent on actual native OpenCodex execution evidence.
