# ctr-20260701-live-broker-smoke

## Package Metadata

- taskId: `ctr-20260701-live-broker-smoke`
- branch: `master`
- permission: local live broker smoke package. Includes read-only current-truth checks, localhost broker discovery/probing, package/workbench updates, reviewer/verifier gates, and local commit after acceptance. Excludes code changes, push, PR, merge, deploy, publish/release, production scheduler/broker daemon, live role dispatch, real account/API use, thread-tool calls, and global skill sync.
- scope: confirm whether a real localhost Team Router broker is currently discoverable and can satisfy the existing readiness gate.

## Objective

Run a live broker smoke against the current Codex Desktop/workspace environment without dispatching work or calling thread-tool endpoints. The only pass condition is a real broker URL plus session token that can return Team Router `/readiness` evidence compatible with the existing host-readiness gate.

## Boundary

Included:

- Refresh current repo truth before probing.
- Search current environment and repo docs/scripts for a broker URL/session token.
- Probe localhost candidate listener ports for `/readiness` with a dummy smoke token and short timeout.
- Run the existing broker feasibility and runtime wiring checks without broker args to confirm missing required inputs.
- Record the blocked live-smoke result in package/workbench current truth.

Excluded:

- No code changes.
- No live role dispatch.
- No calls to `create_thread`, `read_thread`, `send_message_to_thread`, `set_thread_title`, or any `/thread-tools/*` endpoint.
- No broker/adapter/scheduler daemon startup.
- No non-localhost broker, external API, account, credential, push, PR, merge, deploy, publish/release, or global skill sync.

## Acceptance Criteria

- If a broker URL/session token is present, `/readiness` must return Team Router readiness evidence and the dry-run checks must classify host readiness as ready before any automatic-entry claim.
- If no broker URL/session token is present, the package must remain blocked and say `manual_only`; it must not claim live broker smoke success.
- Localhost port probes must be treated only as discovery evidence; random HTML/404/401/connection errors are not valid Team Router readiness.
- Closeout checks must be rerun after package/workbench updates.

## Verification Record

- Starting current truth: `git status -sb --untracked-files=all` -> `## master...origin/master`.
- Starting truth check: `py -B scripts\team_router_truth_check.py --json` -> clean/synced; `diffFiles: []`; `gitStatusShort: []`; `staleClaims: []`; `skillSync.status: match`.
- Starting doctor: `py -B scripts\team_router_doctor.py --json` -> `truthStatus: clean_synced`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`.
- Environment discovery found no `broker-url`, `session-token`, or Team Router broker environment variable. Visible Codex variables were runtime metadata only, including `CODEX_THREAD_ID`.
- Repo discovery found only documented/scripted broker argument references; no live broker URL/token was configured in the repo.
- Localhost listener probing attempted `/readiness` on candidate ports from `netstat`. Responses were non-Team Router evidence: HTML app pages, 404s, 401 from an unrelated local service, connection resets, empty replies, HTTPS mismatch, and timeouts. No candidate returned a valid Team Router readiness payload.
- `py -B scripts\team_router_broker_feasibility_check.py --json` without args -> exit 1; `status: blocked`; `missing: ["broker-url", "session-token"]`; `reason: broker URL and session token are required`.
- `py -B scripts\team_router_runtime_wiring_check.py --json` without args -> exit 1; `status: manual_only`; `orchestrationStatus: manual_only`; `automaticEntryAllowed: false`; missing `broker-url` / `session-token`; no thread-tool calls executed.
- Final truth check after docs update: `py -B scripts\team_router_truth_check.py --json` -> exit 0; `staleClaims: []`; `skillSync.status: match`; dirty surface is this docs-only package.
- Final doctor after docs update: `py -B scripts\team_router_doctor.py --json` -> exit 0; `truthStatus: dirty`; `orchestrationStatus: manual_only`; `hostReadiness.status: not_supplied`.
- Final closeout check after docs update: `py -B scripts\team_router_closeout_check.py --json` -> exit 0; `skillSync.status: match`; dirty surface is this docs-only package.
- `git diff --check` initially reported a workbench EOF blank-line issue; fixed before final re-run.
- Reviewer: thread `019f1e5e-c50e-7c10-89d1-d2c8dfc6e130` -> pass; `requiredChanges: []`; confirmed blocked smoke conclusion is evidence-backed and no automatic-ready/live-dispatch overclaim is present.
- Verifier: thread `019f1e5f-faf5-7492-af2e-9ae7bd8e0c50` -> accepted; `requiredChanges: []`; `acceptedForCommit: true`; confirmed local commit may proceed and push/PR/merge/global sync remain outside.

## Current Conclusion

Live broker smoke is blocked, not passed. The current Desktop/workspace environment does not expose a discoverable Team Router broker URL/session token, and localhost probing did not find a valid `/readiness` endpoint.

Team Router remains `manual_only` until a real broker URL/session token is supplied or a broker/adapter startup package exposes one through the host readiness injection path.

## Review And Verification Gate

Current next gate: none after verifier acceptance and local commit. Future live pass requires a real broker URL/session token.

Future live pass gate: provide or launch a real localhost Team Router broker with session token, then rerun:

- `py -B scripts\team_router_broker_feasibility_check.py --broker-url <url> --session-token <token> --json`
- `py -B scripts\team_router_runtime_wiring_check.py --broker-url <url> --session-token <token> --json`

push, PR, merge, deploy, publish/release, production broker startup, live role dispatch, thread-tool calls, and global skill sync remain outside this package unless separately authorized.
