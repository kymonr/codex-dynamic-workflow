# v4.1 native-host validation and paired comparison

Actual live-trial status is recorded in [V41_NATIVE_COMPARISON_STATUS.json](V41_NATIVE_COMPARISON_STATUS.json). Schema generation is a capability observation, not model execution or Desktop activation. No credentials, permissions or global configuration are changed to work around missing or blocked capabilities.

## Live bridge qualification
Use a fresh, authorized Desktop session on the installed candidate. First confirm actual
Skill discovery, active source/version hashes and the native tool schema. Verify profile,
model, effort and actual read-only capability from host configuration/receipts, not a child
self-report. Do not invent missing tools or equate a requested profile with effective identity.

For one bounded review, Root retains all mainline checks and starts three distinct probes
(omissions, counterexamples, test gaps) early. Capture actual native IDs, request/effective
identity, sources, host capacity/active observations, results, timestamps and actual usage
when available. Keep UNKNOWN where the host does not expose a value. Do not turn an observed
full-access session into a proven read-only sandbox merely because its role says read-only.

Exercise: return an early real finding; mainline acceptance while useful supplementation
remains active; bounded Root screening; explicit issue disposition appropriate to review or
repair; stop request versus confirmed execution/physical cleanup; and a real changed-candidate
probe within the original allowance. Use actual host tools; controller CLI only records state.
No routine requires waiting for all probes. Never drop already returned credible risk evidence.
If continued receipt after Root delivery is unsupported, stop safely through a bounded host
closeout and report incomplete coverage. A closeout record does not create a background worker.

## Paired trials (do not run on production data)
Prepare at least three representative, fixed repository snapshots: a local behavioral fix,
a cross-module/configuration check, and a review with deliberately known boundary cases.
Each pair receives exactly the same original requirement, constraints, bytes and acceptance
checks. Reserve sufficient capacity beforehand. Keep mainline model/effort matched.
Arm A: native Astra, with its own necessary same-model delegation allowed.
Arm B: the same complete Astra mainline plus >=3 distinct optional Luna probes.
Use fresh contexts and distinct native identities; alternate arm order across pairs. Do not
feed one arm's answer into the other. Run each pair more than once before generalizing.

Keep failures and omissions, not only successful trials. Grade findings against original
sources and concrete tests; preferably use a capable non-author reviewer who is blinded to
which arm produced the report. Record verified incremental findings, false findings, missed
findings, time until mainline delivery, Root screening/rework time, and total observed usage
including Root and interrupted probes. Unknown measurements are null, never zero.
Native thread cleanup is reported separately from mainline completion and token accounting.

## Passive comparison input
The evaluator reads one local JSON file with status=OBSERVED and a pairs array. Each pair
has trial_id plus astra and astra_luna arm objects. Each arm records:
- provenance=native-host, synthetic=false, capture={path,sha256} for its raw local host log;
- task_sha256, candidate_sha256, acceptance_sha256 (same within the pair);
- started_at, finished_at, accepted_at (Unix timestamps; accepted_at null on failed acceptance),
  acceptance_passed (boolean), triage_seconds, rework_seconds, total_tokens, host_resources_released;
- verified_findings, false_findings, missed_findings (stable, nonoverlapping graded ID lists);
- agents: actual id, role=mainline|supplemental, status, requested and effective identity objects
  containing model/profile/effort; effective sandbox and distinct direction for supplemental agents.
Requested fields are never substituted for missing effective values. Raw logs remain local:
inspect/redact credentials and unrelated private material before any external publication.

Run python -B scripts/evaluate_native_comparison.py /path/to/observations.json .
NOT_RUN, unknown/mismatched identity, synthetic markers, unsafe/changed captures or unmatched
pair inputs refuse qualification. Valid data yields ATTESTATIONS_VALIDATED and paired metrics,
NOT an assertion that this passive tool ran native agents or authenticated the host's claims.
A manually labeled native-host record is not proof: independently inspect the exact raw
capture before accepting a live-test claim. Small paired samples do not establish universal
quality, latency or cost superiority. Publish the observed tradeoffs, not a forced winner.
