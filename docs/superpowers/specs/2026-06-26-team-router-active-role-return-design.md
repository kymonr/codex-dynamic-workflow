# Team Router Active Role Return Design

## Purpose

Team Router role threads should actively return completed protocol blocks to the Manager thread instead of requiring the Manager to discover results by reading role threads. The current `self-thread-marker` behavior remains as the audit and fallback path, but it is no longer the primary delivery path.

## Decision

Use `direct-send + self-thread-marker fallback` as the default delivery model for Executor, Reviewer, and Verifier role threads.

Each role dispatch prompt must include:

```text
sourceThreadId: <manager thread id>
sourceRoleThreadId: <role thread id>
role: Executor | Reviewer | Verifier
callbackDelivery: direct-send
callbackFallback: self-thread-marker
```

For newly created role threads, the Manager may need a two-step bootstrap: create the role thread first, record the returned `sourceRoleThreadId`, then send the formal role dispatch prompt containing that id. Reused role threads already have a known `sourceRoleThreadId`.

Role completion has two required steps:

1. Send the complete protocol block back to the Manager thread with `send_message_to_thread(sourceThreadId, protocolBlock)`.
2. Output the same protocol block body in the role thread final answer as the `self-thread-marker` fallback and audit record.

For example, a Reviewer sends the complete `TEAM_ROUTER_REVIEW ...` block to the Manager thread first, then prints the same block in its own thread.

The direct-send payload must include enough routing metadata for the Manager to verify the result source:

```text
sourceThreadId: <manager thread id>
sourceRoleThreadId: <role thread id>
role: Executor | Reviewer | Verifier
delivery: direct-send
```

The Manager accepts a direct-send result only when `taskId`, `role`, and `sourceRoleThreadId` match the pending role ledger entry.

## Manager Behavior

The Manager treats direct-send as the primary result path.

If the Manager receives the protocol block in the main thread, it proceeds from that block and does not need to read the role thread.

The Manager treats a received `TEAM_ROUTER_CALLBACK`, `TEAM_ROUTER_REVIEW`, or `TEAM_ROUTER_VERDICT` block as a pending role result before interpreting it as ordinary user input. If the block does not match a pending role ledger entry, the Manager must reject it or quarantine it instead of expanding task scope.

The Manager performs a bounded result-collection read/check only when:

- direct-send failed or reported an error,
- direct-send status is unknown and the role thread is expected to be idle,
- the user says the role has completed,
- or the task has exceeded the expected wait window.

Continuous polling is not the default.

## Fallback Behavior

The role thread must keep the same protocol block body in its own final answer even after a successful direct-send.

If direct-send fails, the role thread should still output the protocol block locally and include the send failure reason in delivery metadata when available:

```text
deliveryStatus: fallback_only
deliveryError: <short send failure reason>
```

The protocol body fields must stay the same between direct-send and local fallback. Delivery metadata may be appended to the local fallback block so the Manager can see why bounded `read_thread` recovery was needed.

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
- `sourceRoleThreadId` and `role` are required so the Manager can match the result to a pending ledger entry.
- docs explain the two-step bootstrap for newly created role threads: create first, then dispatch with the returned role thread id.
- docs mention `send_message_to_thread`, `sourceThreadId`, and sending the same protocol block body back to the Manager.
- docs require Manager-side validation of `taskId`, `role`, and `sourceRoleThreadId`.
- docs define `deliveryStatus: fallback_only` and `deliveryError` for direct-send failures without changing the protocol body.
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
- Manager-side validation rejects or quarantines direct-send protocol blocks that do not match the pending `taskId`, `role`, and `sourceRoleThreadId`.
- Fallback metadata records direct-send failure without changing the protocol body.
- Manager fallback collection is bounded and does not reintroduce continuous polling.
- At least one Reviewer smoke trial confirms the Manager thread receives the direct-send protocol block. If the smoke fails, the local `self-thread-marker` fallback must still recover the result.
- `SKILL.md` remains under 8192 bytes and preferably unchanged.
- The change passes focused and full Team Router tests.
