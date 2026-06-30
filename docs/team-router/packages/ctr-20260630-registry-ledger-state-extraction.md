# ctr-20260630-registry-ledger-state-extraction

## Package

- taskId: `ctr-20260630-registry-ledger-state-extraction`
- openedAt: 2026-06-30
- status: reviewer and verifier passed; local commit pending
- objective: define and execute the next conservative registry/ledger state extraction step after the role-thread prompt path contract closeout.
- startTruth: package starts after `0596316` was pushed to `origin/master` and the authorized global skill sync reported `match`; fresh commands remain the source of current truth.

## Scope

- Review the current registry/ledger responsibility split between `src/team_router.py` and `src/team_router_state.py`.
- Move only pure registry/ledger state helpers that do not call thread tools and do not change protocol, gate, direct-return, watcher, host, or prompt behavior.
- Keep public imports through `src/team_router.py`.
- Update focused tests and module/workbench docs if implementation proceeds.

## Implementation

- Moved `_search_anchor()` from `src/team_router.py` to `src/team_router_state.py` and kept facade compatibility by importing it through `src/team_router.py`.
- Moved pure ledger accessors `_latest_executor_dispatch()`, `_latest_reviewer_request()`, `_return_thread_id_from_record()`, `_inherited_reviewer_return_thread_id()`, and `_inherited_verifier_return_thread_id()` to `src/team_router_state.py`.
- Moved pure review request record construction `_role_review_request_record()` to `src/team_router_state.py` for architect/QA review request ledger metadata.
- Left `record_*_sent()`, capture/read handlers, direct-return receipt validation, watcher refresh, parser/gate policy, host runtime, and prompt text in `src/team_router.py` or their existing extracted modules.
- Added facade re-export coverage for the moved state helpers in `tests/test_team_router.py`.
## Current Boundary

- No push, PR, merge, deploy, publish/release, or global skill sync in this package unless separately authorized.
- No live host adapter implementation, production scheduler/daemon, or thread-tool automation.
- No parser marker schema, reviewer/verifier gate policy, direct-return receipt validation, watcher cadence, or prompt contract behavior change unless explicitly scoped later.
- Opening this package records docs/workbench state only; implementation must remain compatibility-preserving.

## Starting Evidence

- `git status -sb --untracked-files=all` after push: `## master...origin/master`.
- `py -B scripts\team_router_truth_check.py --json` after push/global sync: `staleClaims: []`, `skillSync.status: match`, clean diff.
- `py -B scripts\team_router_doctor.py --json`: `truthStatus: clean_synced`; `nextAction: no action required unless the manager opens a new package`.
- Module map says the remaining safe extraction order is registry/ledger state.
- `src/team_router_state.py` already owns JSON primitives, registry/task path helpers, normalization, and role binding persistence; `src/team_router.py` still owns higher-level ledger mutations and orchestration transitions.

## Verification Record

- `py -B -m py_compile src\team_router.py src\team_router_state.py tests\test_team_router.py` -> exit 0.
- `py -B -m unittest tests.test_team_router.TestTeamRouterProtocol.test_facade_reexports_extracted_state_symbols -v` -> Ran 1 test OK.
- Focused dispatch/fallback tests -> Ran 3 tests OK.
- Focused architect/QA request metadata tests -> Ran 3 tests OK.
- Initial full suite: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 347 tests OK.
- Reviewer v2 found duplicate unittest method name hiding the new re-export assertions; fixed test name collision and added a uniqueness guard.
- Focused recheck after fix -> Ran 3 tests OK.
- Full suite after fix: `py -B -m unittest discover -s tests -p test_team_router.py -q` -> Ran 349 tests OK.

## Reviewer Gate

- Reviewer v2 thread: `019f190d-4ff5-79f0-bda6-00c7ea1d0e49`.
- Initial result: `needs_rework` because duplicate unittest method names meant the new state re-export assertions were overwritten.
- Fix: restored the prompt path handoff test to unique name `test_manager_reviewer_verifier_prompts_codify_path_handoff_contract` and added `test_test_case_names_are_unique` guard.
- Re-review result: `pass`.
- Reviewer requiredChanges: `none`.
- Reviewer residual risk: `git diff --check` CRLF/LF warnings only; package doc must be included in closeout/commit.

## Verifier Gate

- Verifier thread: `019f1914-ec15-7fa2-9357-10946ccf52cf`.
- Initial result: `needs_rework` because docs contained literal `\n-` Markdown artifacts.
- Fix: replaced literal `\n-` artifacts with real Markdown list newlines in this package doc and `docs/workbench.md`.
- Re-check result: `pass`.
- Verifier requiredChanges: `none`.
- Verifier next: `commit`.
## Planned Verification

- Focused tests around state/registry/ledger helpers touched by this package.
- `py -B -m unittest discover -s tests -p test_team_router.py -q`
- `py -B scripts\team_router_truth_check.py --json`
- `py -B scripts\team_router_doctor.py --json`
- `py -B scripts\team_router_closeout_check.py --json`
- `git diff --check`

## Open Questions

- Which ledger mutation helpers are pure enough for extraction without changing public facade behavior?
- Should the first implementation step be a docs/spec-only cut, or the smallest safe helper move?
