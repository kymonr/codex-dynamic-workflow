# Team Router Active Role Return Design

## Purpose

Team Router role threads should actively return completed protocol blocks to the Manager thread instead of requiring the Manager to discover results by reading role threads. The current `self-thread-marker` behavior remains as the audit and fallback path, but it is no longer the primary delivery path.

## Decision

Use `direct-send + self-thread-marker fallback` as the default delivery model for Executor, Reviewer, and Verifier role threads.

Each role prompt must include:

```text
sourceThreadId: <manager thread id>
callbackDelivery: direct-send
callbackFallback: self-thread-marker
```

Role completion has two required steps:

1. Send the complete protocol block back to the Manager thread with `send_message_to_thread(sourceThreadId, protocolBlock)`.
2. Output the same protocol block in the role thread final answer as the `self-thread-marker` fallback and audit record.

For example, a Reviewer sends the complete `TEAM_ROUTER_REVIEW ...` block to the Manager thread first, then prints the same block in its own thread.

## Manager Behavior

The Manager treats direct-send as the primary result path.

If the Manager receives the protocol block in the main thread, it proceeds from that block and does not need to read the role thread.

The Manager performs a bounded result-collection read/check only when:

- direct-send failed or reported an error,
- direct-send status is unknown and the role thread is expected to be idle,
- the user says the role has completed,
- or the task has exceeded the expected wait window.

Continuous polling is not the default.

## Fallback Behavior

The role thread must keep the same protocol block in its own final answer even after a successful direct-send.

If direct-send fails, the role thread should still output the protocol block locally and include the send failure reason in its local notes when available. The Manager can then recover the result with one bounded `read_thread` check.

## Scope

Implementation should update Team Router policy, docs, prompt examples, and tests only.

Expected surfaces:

- `src/team_router.py`
- `tests/test_team_router.py`
- `README.md`
- `docs/runbooks/codex-team-router-live-orchestration.md`
- `skills/codex-team-router/references/manager-mode.md`
- `skills/codex-team-router/references/manual-orchestration.md`
- `skills/codex-team-router/references/testing-and-quality-gates.md`

Avoid editing `skills/codex-team-router/SKILL.md` because it is near the 8192 byte cap.

This design does not add a new runtime thread transport API. It relies on Codex role threads using the available `send_message_to_thread` capability when the prompt instructs them to return results to `sourceThreadId`.

## Test Plan

Focused tests should lock these contracts:

- `callbackDeliveryModel` primary delivery is `direct-send`.
- fallback is `self-thread-marker`.
- `sourceThreadId` is required for active return.
- docs mention `send_message_to_thread`, `sourceThreadId`, and sending the same protocol block back to the Manager.
- docs retain bounded fallback read/check behavior.
- docs do not describe `self-thread-marker` as the default primary delivery path.
- existing `auxiliaryAgentSelectionPolicy` and closeout `compoundingDecision` contracts remain intact.

Verification should include:

```text
py -m unittest tests.test_team_router.TestTeamRouterProtocol tests.test_team_router.TestTeamRouterSkillDoc
py -m unittest tests.test_team_router
py -m py_compile src\team_router.py tests\test_team_router.py
git diff --check
```

## Acceptance Criteria

- Executor, Reviewer, and Verifier prompt guidance requires direct-send to the Manager first and local protocol output second.
- Policy/docs/tests consistently describe `direct-send + self-thread-marker fallback`.
- Manager fallback collection is bounded and does not reintroduce continuous polling.
- `SKILL.md` remains under 8192 bytes and preferably unchanged.
- The change passes focused and full Team Router tests.
