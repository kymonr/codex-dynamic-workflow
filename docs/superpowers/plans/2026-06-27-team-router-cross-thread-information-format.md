# Team Router Cross-Thread Information Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. For this Team Router self-change, do not use subagent-driven-development or multiple parallel writer roles: reviewer feedback for `ctr-20260627-info-format-review` requires one visible Team Router Executor followed by Reviewer and Verifier. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the accepted Team Router dual-layer cross-thread information format: strict protocol blocks plus durable Markdown handoff packages.

**Architecture:** Keep parser/runtime state transitions unchanged. Update the policy snapshot, reference documentation, and docs-contract tests so `reviewPackagePath` defaults to durable `docs/team-router/packages/<taskId>.md` evidence, package content has a bilingual Markdown shape, and package files carry diff summaries without full diffs.

**Tech Stack:** Python standard library, `unittest`, Markdown contract docs, existing `src/team_router.py` protocol snapshot constants.

**Status Note:** Checkboxes were aligned on 2026-06-27 after the implementation package had already landed on `master` as `b3b9024 docs: standardize Team Router handoff package format`; this plan is now a completed durable record, not an active task queue.

---

## File Structure

- Modify: `tests/test_team_router.py`
  - Responsibility: lock the updated role handoff/review package contract through `protocol_contract_snapshot()` and reference-doc checks.
- Modify: `src/team_router.py`
  - Responsibility: keep `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY` as the code-side center of truth for package expectations.
- Modify: `skills/codex-team-router/references/role-handoff-and-review-package.md`
  - Responsibility: explain the human-facing package convention, durable path, bilingual shape, language rules, and no-full-diff policy.
- Do not modify: `skills/codex-team-router/SKILL.md`
  - Reason: the current entrypoint already points to the reference file and is near the Codex size cap. Keep deep details in `references/`.
- Do not modify: `.gitignore`
  - Reason: `docs/team-router/packages/<taskId>.md` is durable evidence and should remain git-trackable.
- Do not modify: parser functions or runtime package-content reading.
  - Reason: the design explicitly keeps runtime from reading, executing, parsing, or trusting Markdown package content.

## Task 1: Add Failing Contract Tests

**Files:**
- Modify: `tests/test_team_router.py`
- Test: `tests/test_team_router.py`

- [x] **Step 1: Update `test_protocol_contract_snapshot_includes_role_handoff_review_package_policy` expected minimum content**

In `tests/test_team_router.py`, replace the `policy["reviewPackage"]["minimumContent"]` expected list with:

```python
        self.assertEqual(
            policy["reviewPackage"]["minimumContent"],
            [
                "taskId",
                "objective",
                "scope",
                "protocol marker references",
                "touched files",
                "accepted files when different from touched files",
                "behavior changes",
                "diff summary without full diff",
                "executor callback/report summary",
                "reviewer findings and requiredChanges when present",
                "verification evidence and actual commands/results",
                "excluded unrelated changes and untracked files",
                "risks",
                "remainingTodos",
            ],
        )
```

- [x] **Step 2: Add assertions for durable path, language, and diff policy**

Immediately after the `minimumContent` assertion, add:

```python
        self.assertEqual(
            policy["reviewPackage"]["defaultReviewPackagePath"],
            "docs/team-router/packages/<taskId>.md",
        )
        self.assertIn("durable project evidence", policy["reviewPackage"]["gitPolicy"])
        self.assertIn("must not be added to .gitignore", policy["reviewPackage"]["gitPolicy"])
        self.assertIn("does not apply to taskBriefPath", policy["reviewPackage"]["defaultPathScope"])
        self.assertIn("does not apply to executorReportPath", policy["reviewPackage"]["defaultPathScope"])
        self.assertIn("full diff", policy["reviewPackage"]["diffPolicy"])
        self.assertIn("must not include", policy["reviewPackage"]["diffPolicy"])
        self.assertIn("free-text fields default to Chinese", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("field names", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("enum values", policy["reviewPackage"]["languagePolicy"])
        self.assertIn("English classifier signals", policy["reviewPackage"]["languagePolicy"])
        self.assertIn(
            "Task Summary / 任务摘要",
            policy["reviewPackage"]["bilingualTemplateSections"],
        )
        self.assertIn(
            "Behavior Changes / 行为变化",
            policy["reviewPackage"]["bilingualTemplateSections"],
        )
        self.assertIn(
            "Diff Summary / Diff 摘要",
            policy["reviewPackage"]["bilingualTemplateSections"],
        )
```

- [x] **Step 3: Keep existing gate expectation assertions unchanged**

Do not change these existing assertions:

```python
        self.assertEqual(policy["reviewPackage"]["gateExpectation"]["FAST"], "optional")
        self.assertEqual(policy["reviewPackage"]["gateExpectation"]["NORMAL"], "optional")
        self.assertEqual(policy["reviewPackage"]["gateExpectation"]["STRICT"], "recommended")
        self.assertIn("default required", policy["reviewPackage"]["gateExpectation"]["PACKAGE"])
```

Expected reason: `STRICT` must remain recommended, not runtime-blocking.

- [x] **Step 4: Add reference-doc assertions**

In the same test method, after the existing policy assertions, load the reference doc if the test class already uses doc reads nearby. If no local variable exists, add this direct read:

```python
        reference = Path("skills/codex-team-router/references/role-handoff-and-review-package.md").read_text(encoding="utf-8")
        self.assertIn("docs/team-router/packages/<taskId>.md", reference)
        self.assertIn("Task Summary / 任务摘要", reference)
        self.assertIn("Behavior Changes / 行为变化", reference)
        self.assertIn("Diff Summary / Diff 摘要", reference)
        self.assertIn("must not include a full diff", reference)
        self.assertIn("free-text fields default to Chinese", reference)
```

If `Path` is not imported at the top of `tests/test_team_router.py`, add:

```python
from pathlib import Path
```

Do not add a second import if `Path` already exists.

- [x] **Step 5: Run the focused test and verify it fails**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy -v
```

Expected: FAIL because `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY` and the reference doc still use the old package minimum content and do not expose the new durable path/language/diff policies.

## Task 2: Update Code-Side Policy Snapshot

**Files:**
- Modify: `src/team_router.py`
- Test: `tests/test_team_router.py`

- [x] **Step 1: Update high-risk handoff wording**

In `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY["handoff"]["highRisk"]`, replace the current string with:

```python
        "highRisk": "high-risk Team Router self changes, reviewer-gate/process/policy changes, long executor results, and manager-required STRICT evidence should use a review package when shared workspace/path is accessible",
```

- [x] **Step 2: Update `reviewPackage` policy fields**

Replace the `reviewPackage` mapping in `ROLE_HANDOFF_REVIEW_PACKAGE_POLICY` with this shape, preserving surrounding `handoff`, `externalMaterialSafety`, `thirdPartySkillIntake`, and `pathFields` keys:

```python
    "reviewPackage": {
        "preferredFor": "reviewer/verifier evidence bundle on high-risk work",
        "defaultReviewPackagePath": "docs/team-router/packages/<taskId>.md",
        "defaultPathScope": "default reviewPackagePath only; does not apply to taskBriefPath and does not apply to executorReportPath",
        "gitPolicy": "review packages under docs/team-router/packages/ are durable project evidence, intended to be committed with the task, and must not be added to .gitignore",
        "languagePolicy": "protocol markers, field names, enum values, paths, commands, filenames, and tool names stay English/literal; free-text fields default to Chinese for human-readable task descriptions, while gate-sensitive fields retain English classifier signals or explicit fields such as requiresReviewer: true or riskClass: high",
        "diffPolicy": "packages must include a diff summary, but must not include a full diff; use paths, symbols, behavior descriptions, and verification evidence instead of pasting the entire patch",
        "gateExpectation": {
            "FAST": "optional",
            "NORMAL": "optional",
            "STRICT": "recommended; manager should require a package for high-risk, long-running, multi-file, policy, role-protocol, permission, safety, or reviewer-gate work",
            "PACKAGE": "default required unless explicit inline fallback is marked",
        },
        "minimumContent": [
            "taskId",
            "objective",
            "scope",
            "protocol marker references",
            "touched files",
            "accepted files when different from touched files",
            "behavior changes",
            "diff summary without full diff",
            "executor callback/report summary",
            "reviewer findings and requiredChanges when present",
            "verification evidence and actual commands/results",
            "excluded unrelated changes and untracked files",
            "risks",
            "remainingTodos",
        ],
        "bilingualTemplateSections": [
            "Task Summary / 任务摘要",
            "Scope / 范围",
            "Protocol References / 协议引用",
            "Touched Files / 触及文件",
            "Behavior Changes / 行为变化",
            "Diff Summary / Diff 摘要",
            "Verification / 验证",
            "Excluded Changes / 未纳入改动",
            "Risks / 风险",
            "Remaining Todos / 剩余事项",
        ],
        "shape": {
            "objectiveSection": ("taskId", "objective", "scope", "reviewPackagePath"),
            "protocolSection": ("protocol marker references", "parser-compatible English field names and enum values", "Chinese free-text task descriptions"),
            "fileBoundarySection": ("accepted files", "touched files", "excluded unrelated changes", "excluded untracked files"),
            "executionSection": ("task brief reference or inline fallback note", "executor callback/report summary", "behavior changes", "review findings/required changes when present"),
            "verificationSection": ("verification evidence and commands/results", "review evidence when present", "risks", "remainingTodos"),
        },
        "reviewerUse": "reviewer inspects package plus focused diff/evidence instead of reconstructing facts from parent chat history",
        "verifierUse": "verifier checks executor callback, reviewer result if present, package evidence, permission boundary, accepted files, excluded changes, and final user-facing closeout",
        "protocolMarkers": "package supplements evidence and does not replace TEAM_ROUTER_CALLBACK/TEAM_ROUTER_REVIEW/TEAM_ROUTER_VERDICT",
    },
```

- [x] **Step 3: Run the focused policy test**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy -v
```

Expected: still FAIL until the reference doc assertions are satisfied, or PASS if Task 1 did not add reference-doc assertions yet. The policy-snapshot assertions should pass after this task.

## Task 3: Update Role Handoff Reference Doc

**Files:**
- Modify: `skills/codex-team-router/references/role-handoff-and-review-package.md`
- Test: `tests/test_team_router.py`

- [x] **Step 1: Update the path-fields section**

In `skills/codex-team-router/references/role-handoff-and-review-package.md`, keep the existing three path field bullets, then add this paragraph after them:

````markdown
Default durable review package path:

```text
docs/team-router/packages/<taskId>.md
```

This default applies to `reviewPackagePath` only. It does not apply to `taskBriefPath` or `executorReportPath`. Package files under `docs/team-router/packages/` are durable project evidence, should be committed with the task when created, and must not be added to `.gitignore`. Commit closeout must explicitly account for package files because untracked files are not shown by `git diff --name-only`.
````

- [x] **Step 2: Update gate expectations**

Keep the current bullets, but change the `STRICT` bullet to:

```markdown
- `STRICT`: recommended; manager should require a package for high-risk, long-running, multi-file, policy, role-protocol, permission, safety, or reviewer-gate work
```

Keep the `PACKAGE` bullet as:

```markdown
- `PACKAGE`: default required unless explicit inline fallback is marked
```

- [x] **Step 3: Replace the minimum content list**

Replace the old `Minimum content:` list with:

```markdown
Minimum content:

- `taskId`
- objective
- scope
- protocol marker references
- touched files
- accepted files, when different from touched files
- behavior changes
- diff summary without full diff
- executor callback/report summary
- reviewer findings and `requiredChanges` when present
- verification evidence and actual commands/results
- excluded unrelated changes and untracked files
- risks
- remainingTodos
```

- [x] **Step 4: Add language and diff rules**

After the minimum content list, add:

```markdown
Protocol markers, field names, enum values, paths, commands, filenames, and tool names stay English/literal. Free-text fields default to Chinese for human-readable task descriptions. Gate-sensitive fields should preserve English classifier signals or use explicit fields such as `requiresReviewer: true` or `riskClass: high`.

Packages must include a diff summary, but must not include a full diff. Use paths, symbols, behavior descriptions, and verification evidence instead of pasting the entire patch.
```

- [x] **Step 5: Replace recommended shape with bilingual template**

Replace the current `Recommended shape:` bullets with:

````markdown
Recommended shape:

```markdown
# Team Router Handoff Package: <taskId>

## Task Summary / 任务摘要
## Scope / 范围
## Protocol References / 协议引用
## Touched Files / 触及文件
## Behavior Changes / 行为变化
## Diff Summary / Diff 摘要
## Verification / 验证
## Excluded Changes / 未纳入改动
## Risks / 风险
## Remaining Todos / 剩余事项
```
````

- [x] **Step 6: Add legacy package warning**

Before `## External Material Safety`, add:

```markdown
Legacy note: older ignored `.superpowers/sdd/` packages may include full diffs. They predate this contract and must not be used as the template for new durable `docs/team-router/packages/<taskId>.md` packages.
```

- [x] **Step 7: Run the focused policy/reference test**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy -v
```

Expected: PASS.

## Task 4: Verify No Parser Or Runtime Trust Boundary Drift

**Files:**
- Test: `src/team_router.py`
- Test: `tests/test_team_router.py`
- Test: `skills/codex-team-router/references/role-handoff-and-review-package.md`

- [x] **Step 1: Confirm parser functions were not edited**

Run:

```powershell
git diff -- src\team_router.py | Select-String -Pattern "def parse_message|def parse_plan|def parse_callback|def parse_verdict|def parse_review|def _apply_review_package_path_metadata|read_text|open\\("
```

Expected:

- No changes to parser function definitions.
- No new Markdown file reads in runtime package metadata code.
- `_apply_review_package_path_metadata` may appear only because nearby policy constants changed, not because runtime now reads package content.

- [x] **Step 2: Confirm `.gitignore` did not ignore durable packages**

Run:

```powershell
Select-String -Path .gitignore -Pattern "docs/team-router/packages|team-router/packages"
```

Expected: no matches.

- [x] **Step 3: Confirm reference doc includes the exact durable path**

Run:

```powershell
Select-String -Path skills\codex-team-router\references\role-handoff-and-review-package.md -Pattern "docs/team-router/packages/<taskId>.md|must not include a full diff|free-text fields default to Chinese|Behavior Changes / 行为变化"
```

Expected: all four patterns found.

## Task 5: Run Focused And Full Verification

**Files:**
- Test: `tests/test_team_router.py`
- Test: `src/team_router.py`
- Test: `skills/codex-team-router/references/role-handoff-and-review-package.md`

- [x] **Step 1: Run the focused docs/policy test**

Run:

```powershell
py -m unittest tests.test_team_router.TestTeamRouterState.test_protocol_contract_snapshot_includes_role_handoff_review_package_policy -v
```

Expected: PASS.

- [x] **Step 2: Run Python compile check**

Run:

```powershell
py -m py_compile src\team_router.py tests\test_team_router.py
```

Expected: no output and exit code 0.

- [x] **Step 3: Run the full Team Router test file**

Run:

```powershell
py -m unittest discover -s tests -p test_team_router.py -v
```

Expected: PASS. If Windows temp cleanup fails after assertions pass, rerun with temp environment redirected to `C:\tmp`:

```powershell
$env:TMP='C:\tmp'; $env:TEMP='C:\tmp'; $env:PYTHONPYCACHEPREFIX='C:\tmp\team-router-pycache'; py -m unittest discover -s tests -p test_team_router.py -v
```

Expected: PASS.

- [x] **Step 4: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: PASS, or only known CRLF/LF context warnings already accepted by the project and no whitespace errors.

- [x] **Step 5: Inspect final diff surface**

Run:

```powershell
git status -sb --untracked-files=all
git diff -- docs\superpowers\specs\2026-06-27-team-router-cross-thread-information-format-design.md docs\superpowers\plans\2026-06-27-team-router-cross-thread-information-format.md src\team_router.py tests\test_team_router.py skills\codex-team-router\references\role-handoff-and-review-package.md
```

Expected:

- Intentional files only.
- No `.gitignore` change.
- No parser/runtime Markdown-reading change.
- New implementation plan and existing design spec are visible as untracked/modified until explicitly staged.

## Task 6: Team Router Review And Verification Gate

**Files:**
- Review: all files changed by Tasks 1-5.

- [x] **Step 1: Dispatch one visible Team Router Reviewer**

Create or reuse one reviewer role thread. Prompt boundary:

```text
Review the Team Router cross-thread information format implementation. Read-only only. Check that parser/runtime behavior did not change, STRICT remains recommended, PACKAGE remains required-or-inline-fallback, package path is durable and git-tracked, and package content rules include behavior changes plus diff summary without full diff. Reply only with TEAM_ROUTER_REVIEW.
```

Expected: `TEAM_ROUTER_REVIEW result: pass`.

- [x] **Step 2: Dispatch one visible Team Router Verifier**

After reviewer pass, create or reuse one verifier role thread. Prompt boundary:

```text
Verify the executor callback and reviewer result for the Team Router cross-thread information format implementation. Confirm tests, docs, policy snapshot, changed files, excluded changes, and remaining risks. Reply only with TEAM_ROUTER_VERDICT.
```

Expected: `TEAM_ROUTER_VERDICT result: pass`.

- [x] **Step 3: Closeout without commit unless separately authorized**

Report:

```text
Team Router Closeout
status: done
changed: <files changed>
verified: <commands and results>
acceptedBy: reviewer + verifier
notDone: commit/push/PR/merge/publish/release not done unless separately authorized
risks: <remaining risks or none>
next: ask user for commit authorization if they want a local commit
compoundingDecision: skipped
reason: ordinary successful policy/docs/test implementation with no new reusable risk
```

Expected: plain-language closeout for the user.

## Commit Gate

Do not commit during implementation unless the user explicitly authorizes commit after verifier pass. If authorized, stage only intentional files:

```powershell
git add docs\superpowers\specs\2026-06-27-team-router-cross-thread-information-format-design.md docs\superpowers\plans\2026-06-27-team-router-cross-thread-information-format.md src\team_router.py tests\test_team_router.py skills\codex-team-router\references\role-handoff-and-review-package.md
git commit -m "docs: standardize Team Router handoff package format"
```

Before commit, rerun:

```powershell
git status -sb --untracked-files=all
git diff --cached --check
```

Expected: only accepted files are staged and whitespace check passes.
