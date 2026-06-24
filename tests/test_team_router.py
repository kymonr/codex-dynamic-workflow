# -*- coding: utf-8 -*-
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = str(ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import team_router


class FakeThreadAdapter:
    def __init__(self):
        self.created = []
        self.sent = []
        self.messages = {}
        self._thread_count = 0
        self._message_count = 0

    def create_thread(self, **kwargs):
        prompt = kwargs["prompt"]
        role = "role"
        for candidate in ("manager", "executor", "verifier", "reviewer"):
            if candidate in prompt:
                role = candidate
                break
        self._thread_count += 1
        thread_id = "thread-%s" % role
        self.messages[thread_id] = []
        record = {"threadId": thread_id, "title": "TeamRouter %s" % role}
        self.created.append({"kwargs": kwargs, "result": record})
        return record

    def send_message_to_thread(self, **kwargs):
        self._message_count += 1
        message_id = "msg-%02d" % self._message_count
        sent_at = "2026-06-22T20:%02d:00+08:00" % self._message_count
        message = {
            "messageId": message_id,
            "sentAt": sent_at,
            "text": kwargs["prompt"],
        }
        self.messages.setdefault(kwargs["threadId"], []).append(message)
        self.sent.append({"kwargs": kwargs, "result": message})
        return {"message": {"id": message_id, "createdAt": sent_at}}

    def read_thread(self, **kwargs):
        return {"thread": {"messages": list(self.messages.get(kwargs["threadId"], []))}}

    def append_reply(self, thread_id, text, *, message_id, sent_at):
        self.messages.setdefault(thread_id, []).append({
            "messageId": message_id,
            "sentAt": sent_at,
            "text": text,
        })


class FullThreadAdapter(FakeThreadAdapter):
    def list_projects(self, **kwargs):
        return {"projects": []}

    def list_threads(self, **kwargs):
        return {"threads": []}

    def set_thread_title(self, **kwargs):
        return {"threadId": kwargs["threadId"], "title": kwargs["title"]}


class TestTeamRouterProtocol(unittest.TestCase):
    def test_callback_parser_rejects_colon_marker(self):
        text = """TEAM_ROUTER_CALLBACK taskId: ctr-1
status: done
final: true
summary: ok
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_callback(text, "ctr-1")

    def test_callback_parser_rejects_malformed_marker_after_valid_block(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary: old
evidence: old
risks: none
next: none

TEAM_ROUTER_CALLBACK taskId: ctr-1
status: blocked
final: true
summary: new
evidence: new
risks: none
next: none
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_callback(text, "ctr-1")

    def test_callback_parser_uses_last_final_message(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary: draft
evidence: old
risks: none
next: none

TEAM_ROUTER_CALLBACK taskId=ctr-1
status: blocked
final: true
summary: final
evidence: latest
risks: missing data
next: retry
"""
        msg = team_router.parse_callback(text, "ctr-1")
        self.assertEqual(msg.fields["status"], "blocked")
        self.assertEqual(msg.fields["summary"], "final")

    def test_callback_parser_keeps_multiline_summary(self):
        text = """TEAM_ROUTER_CALLBACK taskId=ctr-1
status: done
final: true
summary:
checked protocol parser
confirmed no missing fields
evidence: tests
risks: none
next: none
"""
        msg = team_router.parse_callback(text, "ctr-1")
        self.assertEqual(
            msg.fields["summary"],
            "checked protocol parser\nconfirmed no missing fields",
        )

    def test_plan_requires_acknowledged_permission(self):
        text = """TEAM_ROUTER_PLAN taskId=ctr-1
status: planned
scope: docs
stopWhen: done
riskBoundary: read only
executorPrompt: inspect docs
notes: none
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_plan(text, "ctr-1")

    def test_plan_rejects_empty_required_fields(self):
        text = """TEAM_ROUTER_PLAN taskId=ctr-1
status: planned
acknowledgedPermission: read-only
scope:
stopWhen: done
riskBoundary: read only
executorPrompt:
notes: none
"""
        with self.assertRaises(team_router.ProtocolError):
            team_router.parse_plan(text, "ctr-1")

    def test_verdict_result_is_structured(self):
        text = """TEAM_ROUTER_VERDICT taskId=ctr-1
result: needs_rework
summary: missing edge case
requiredChanges: add state test
evidenceChecked: test plan
risks: none
"""
        msg = team_router.parse_verdict(text, "ctr-1")
        self.assertEqual(msg.fields["result"], "needs_rework")


class TestTeamRouterState(unittest.TestCase):
    def test_callback_unreachable_is_recoverable_not_terminal(self):
        self.assertNotIn("callback_unreachable", team_router.TERMINAL_STATUSES)
        self.assertEqual(
            team_router.manual_recovery_target("callback_unreachable"),
            "verifying",
        )
        self.assertEqual(
            team_router.manual_recovery_target("plan_unreachable"),
            "planned",
        )
        self.assertEqual(
            team_router.manual_recovery_target("review_unreachable"),
            "reviewing",
        )

    def test_rework_limit_blocks_without_incrementing(self):
        status, count = team_router.next_rework_dispatch(rework_count=3, max_rework=3)
        self.assertEqual(status, "blocked")
        self.assertEqual(count, 3)
        status, count = team_router.next_rework_dispatch(rework_count=2, max_rework=3)
        self.assertEqual(status, "dispatched")
        self.assertEqual(count, 3)


    def test_review_parser_accepts_adversarial_review_marker(self):
        text = """TEAM_ROUTER_REVIEW taskId=ctr-1
result: needs_rework
summary: risky
findings: missing direct-return fallback
requiredChanges: add reviewer gate tests
evidenceChecked: protocol snapshot
risks: none
"""

        msg = team_router.parse_review(text, "ctr-1")

        self.assertEqual(msg.fields["result"], "needs_rework")
        self.assertEqual(msg.fields["findings"], "missing direct-return fallback")
    def test_reviewer_gate_required_for_runtime_gate_reviewer_gate_and_team_router_self_changes(self):
        cases = (
            ("Team Router reviewer runtime gate rework", {"scope": "runtime gate"}),
            ("repair reviewer gate trigger policy", {"riskBoundary": "reviewer gate must run"}),
            ("Team Router self changes", {"executorPrompt": "review routing policy"}),
            ("Team Router manager orchestration policy update", {"scope": "docs"}),
            ("Team Router permission boundary change", {"scope": "src"}),
            ("ordinary task", {"requiresReviewer": "true"}),
            ("ordinary task", {"riskClass": "high"}),
        )
        for objective, fields in cases:
            with self.subTest(objective=objective, fields=fields):
                ledger = {"objective": objective, "plan": {"fields": fields}}
                self.assertTrue(team_router.reviewer_gate_required_for_ledger(ledger))

    def test_reviewer_gate_required_does_not_trigger_on_team_router_filename_only(self):
        ledger = {
            "objective": "low-risk docs-only single-file cleanup",
            "plan": {
                "fields": {
                    "scope": "src/team_router.py",
                    "riskBoundary": "low-risk docs-only single-file fix",
                    "executorPrompt": "adjust a typo in src/team_router.py",
                    "notes": "typo-only cleanup",
                }
            },
        }

        self.assertFalse(team_router.reviewer_gate_required_for_ledger(ledger))
    def test_protocol_contract_snapshot_centralizes_roles_states_and_markers(self):
        snapshot = team_router.protocol_contract_snapshot()

        self.assertEqual(snapshot["parentSideRoles"]["parent_orchestrator"]["displayName"], "调度者")
        self.assertEqual(snapshot["parentSideRoles"]["parent_orchestrator"]["englishAlias"], "Orchestrator")
        snapshot_text = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("父线程" + "调度者", snapshot_text)
        self.assertNotIn("Parent " + "Orchestrator", snapshot_text)
        self.assertFalse(snapshot["parentSideRoles"]["state_controller"]["thread"])
        self.assertEqual(snapshot["roleThreads"]["manager"]["displayName"], "规划者")
        self.assertEqual(snapshot["roleThreads"]["reviewer"]["displayName"], "审查者")
        self.assertEqual(snapshot["roleThreads"]["reviewer"]["englishAlias"], "Reviewer")
        self.assertTrue(snapshot["roleThreads"]["reviewer"]["conditional"])
        self.assertTrue(snapshot["roleThreads"]["executor"]["thread"])
        self.assertEqual(snapshot["threadPermissions"], ["design-only", "read-only"])
        self.assertIn("send_message_to_thread", snapshot["threadToolNames"])
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_CALLBACK"]["requiredFields"],
            ["status", "final", "summary", "evidence", "risks", "next"],
        )
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_VERDICT"]["allowedValues"]["result"],
            ["blocked", "needs_rework", "pass"],
        )
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_REVIEW"]["requiredFields"],
            ["result", "summary", "findings", "requiredChanges", "evidenceChecked", "risks"],
        )
        self.assertEqual(
            snapshot["markers"]["TEAM_ROUTER_REVIEW"]["allowedValues"]["result"],
            ["blocked", "needs_rework", "pass"],
        )
        self.assertIn("awaiting_callback", snapshot["stateMachine"]["main"])
        self.assertIn("reviewing", snapshot["stateMachine"]["main"])
        self.assertEqual(snapshot["recoverableStatuses"]["callback_unreachable"], "verifying")
        self.assertEqual(snapshot["recoverableStatuses"]["review_unreachable"], "reviewing")
        self.assertEqual(snapshot["stateMachine"]["manual_recovery"]["review_unreachable"], "reviewing")



    def test_protocol_contract_snapshot_includes_manager_orchestration_policy(self):
        policy = team_router.protocol_contract_snapshot()["managerOrchestrationPolicy"]

        self.assertIn("low-frequency", policy["polling"]["mode"])
        self.assertIn("event-driven", policy["polling"]["mode"])
        self.assertIn("read_thread", policy["polling"]["mode"])
        self.assertIn("30-60s", policy["polling"]["steadyCadence"])
        self.assertIn("status changes", policy["polling"]["userVisibleUpdates"])
        self.assertIn("reuse existing executor", policy["roleReuse"]["default"])
        self.assertIn("existing verifier", policy["roleReuse"]["default"])
        self.assertIn("same taskId or task family", policy["roleReuse"]["default"])
        self.assertIn("original executor", policy["roleReuse"]["reworkExecutor"])
        self.assertIn("original verifier", policy["roleReuse"]["reworkVerifier"])
        self.assertIn("isolation requirement changes", policy["roleReuse"]["newThreadOnlyWhen"])
        self.assertIn("verdictDelivery: direct-send", policy["verifierDirectReturn"]["requiredFields"])
        self.assertIn("verdictFallback: self-thread-marker", policy["verifierDirectReturn"]["requiredFields"])
        self.assertEqual(
            policy["verifierDirectReturn"]["sendInstruction"],
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)",
        )

        reviewer_gate = policy["conditionalReviewerGate"]
        self.assertIn("executor -> verifier", reviewer_gate["defaultFlow"])
        self.assertIn("reviewer(read-only/adversarial)", reviewer_gate["reviewerFlow"])
        self.assertIn("router/manager/orchestration policy", reviewer_gate["requiredFor"])
        self.assertIn("role protocol changes", reviewer_gate["requiredFor"])
        self.assertIn("runtime gate or reviewer gate changes", reviewer_gate["requiredFor"])
        self.assertIn("Team Router self changes", "\n".join(reviewer_gate["requiredFor"]))
        self.assertIn("ordinary small fixes", reviewer_gate["skipWhen"])
        self.assertIn("not final acceptance", reviewer_gate["reviewerResponsibility"])
        self.assertIn("final acceptance", reviewer_gate["verifierResponsibility"])
        self.assertIn("reuse existing reviewer", reviewer_gate["roleReuse"])
        self.assertIn("original reviewer", reviewer_gate["roleReuse"])
        self.assertIn("send_reviewer_request_with_adapter()", reviewer_gate["runtimeImplementation"])
        self.assertIn("read_reviewer_review_update_with_adapter()", reviewer_gate["runtimeImplementation"])
        self.assertIn("capture_reviewer_review_from_read()", reviewer_gate["runtimeImplementation"])
        self.assertIn("needs_rework -> executor rework", reviewer_gate["runtimeImplementation"])
        self.assertIn("reviewer role conversation/thread", reviewer_gate["namedReviewerRequirement"])
        self.assertIn("create/register reviewer role conversation", reviewer_gate["namedReviewerRequirement"])
        self.assertIn("subagent fallback is not allowed", reviewer_gate["namedReviewerRequirement"])
        self.assertIn("reviewDelivery: direct-send", policy["reviewerDirectReturn"]["requiredFields"])
        self.assertIn("reviewFallback: self-thread-marker", policy["reviewerDirectReturn"]["requiredFields"])
        self.assertEqual(
            policy["reviewerDirectReturn"]["sendInstruction"],
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)",
        )

    def test_protocol_contract_snapshot_includes_side_effect_taxonomy_policy(self):
        policy = team_router.protocol_contract_snapshot()["sideEffectTaxonomy"]

        self.assertEqual(
            set(policy) & {
                "READ_ONLY",
                "DISPATCH_ONLY",
                "LOCAL_CLOSEOUT",
                "WORKSPACE_WRITE",
                "HEAVY_OR_RISKY",
                "EXTERNAL_RELEASE",
            },
            {
                "READ_ONLY",
                "DISPATCH_ONLY",
                "LOCAL_CLOSEOUT",
                "WORKSPACE_WRITE",
                "HEAVY_OR_RISKY",
                "EXTERNAL_RELEASE",
            },
        )
        self.assertIn("CodeGraph query/status/explore", policy["READ_ONLY"]["description"])
        self.assertIn("read_thread low-frequency", policy["READ_ONLY"]["description"])
        self.assertIn("not implementation", policy["READ_ONLY"]["boundary"])
        self.assertIn("TEAM_ROUTER_DISPATCH", policy["DISPATCH_ONLY"]["description"])
        self.assertIn("record/capture ledger state", policy["DISPATCH_ONLY"]["description"])
        self.assertIn("routing is not implementation", policy["DISPATCH_ONLY"]["boundary"])
        self.assertIn("verifier pass", policy["LOCAL_CLOSEOUT"]["requires"])
        self.assertIn("explicit user commit request", policy["LOCAL_CLOSEOUT"]["requires"])
        self.assertIn("stage only accepted files", policy["LOCAL_CLOSEOUT"]["allowedFor"])
        self.assertIn("unrelated untracked", policy["LOCAL_CLOSEOUT"]["excludes"])
        self.assertIn("push/PR/merge/deploy", policy["LOCAL_CLOSEOUT"]["excludes"])
        self.assertIn("fixtures", policy["WORKSPACE_WRITE"]["description"])
        self.assertIn("executor", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("explicit role switch", policy["WORKSPACE_WRITE"]["boundary"])
        self.assertIn("external API", policy["HEAVY_OR_RISKY"]["description"])
        self.assertIn("explicit separate authorization", policy["HEAVY_OR_RISKY"]["requires"])
        self.assertIn("push/PR/merge/deploy/publish/release", policy["EXTERNAL_RELEASE"]["description"])
        self.assertIn("separate publish/release authorization", policy["EXTERNAL_RELEASE"]["requires"])
        self.assertIn("at most DISPATCH_ONLY", policy["terseApprovalBoundary"])
        self.assertIn("subagent fallback is not allowed", policy["namedReviewerRequirement"])

    def test_protocol_contract_snapshot_includes_role_closeout_policy(self):
        policy = team_router.protocol_contract_snapshot()["roleCloseoutPolicy"]

        self.assertIn("no extra ROLE_CLOSEOUT", policy["default"])
        self.assertIn("ordinary closeout messages", policy["default"])
        self.assertIn("final protocol block is the closeout", policy["finalProtocolBlock"])
        self.assertIn("TEAM_ROUTER_CALLBACK", policy["finalProtocolBlock"])
        self.assertIn("TEAM_ROUTER_REVIEW", policy["finalProtocolBlock"])
        self.assertIn("TEAM_ROUTER_VERDICT", policy["finalProtocolBlock"])
        self.assertIn("compact is native operation, not chat prompt", policy["compact"])
        self.assertIn("must not send compact or ROLE_CLOSEOUT text", policy["compact"])
        self.assertIn("if no compact tool is available, do nothing", policy["noCompactTool"])
        self.assertIn("role thread is still active/inProgress and must stop", policy["exceptionsOnly"])
        self.assertIn("no final protocol block exists", "\n".join(policy["exceptionsOnly"]))
        self.assertIn("compact/archive recovery anchor", "\n".join(policy["exceptionsOnly"]))
        self.assertIn("user explicitly asks", policy["exceptionsOnly"])
        self.assertIn("clear is not a default action", policy["clearArchiveNewThread"])
        self.assertIn("task family/permission/workspace boundary changes", policy["clearArchiveNewThread"])

    def test_protocol_contract_snapshot_includes_role_handoff_review_package_policy(self):
        policy = team_router.protocol_contract_snapshot()["roleHandoffReviewPackagePolicy"]

        self.assertIn("stable file/path handoff", policy["handoff"]["preferred"])
        self.assertIn("accumulated chat history", policy["handoff"]["preferred"])
        self.assertIn("taskId", policy["handoff"]["promptShape"])
        self.assertIn("expected marker", policy["handoff"]["promptShape"])
        self.assertIn("explicit protocol return format", policy["handoff"]["promptShape"])
        self.assertIn("inline protocol blocks", policy["handoff"]["smallTasks"])
        self.assertIn("Team Router self changes", policy["handoff"]["highRisk"])
        self.assertIn("reviewer-gate/process/policy changes", policy["handoff"]["highRisk"])
        self.assertIn("shared workspace/path", policy["handoff"]["highRisk"])
        self.assertIn("inline protocol block fallback", policy["handoff"]["fallback"])
        self.assertEqual(
            policy["reviewPackage"]["minimumContent"],
            [
                "taskId",
                "objective",
                "scope",
                "touched/accepted files",
                "diff summary",
                "executor callback/report",
                "test/verification evidence",
                "reviewer requiredChanges when present",
                "excluded unrelated untracked",
                "risks/remainingTodos",
            ],
        )
        self.assertIn("focused diff/evidence", policy["reviewPackage"]["reviewerUse"])
        self.assertIn("parent chat history", policy["reviewPackage"]["reviewerUse"])
        self.assertIn("executor callback", policy["reviewPackage"]["verifierUse"])
        self.assertIn("accepted files", policy["reviewPackage"]["verifierUse"])
        self.assertIn("excluded untracked", policy["reviewPackage"]["verifierUse"])
        self.assertIn("does not replace TEAM_ROUTER_CALLBACK", policy["reviewPackage"]["protocolMarkers"])
        self.assertIn("TEAM_ROUTER_REVIEW", policy["reviewPackage"]["protocolMarkers"])
        self.assertIn("TEAM_ROUTER_VERDICT", policy["reviewPackage"]["protocolMarkers"])
        self.assertEqual(
            policy["futureOptionalRuntimeFields"],
            ["taskBriefPath", "executorReportPath", "reviewPackagePath"],
        )
        self.assertIn("no runtime behavior implemented", policy["runtimeStatus"])
        self.assertIn("WORKSPACE_WRITE/executor-delegated", policy["sideEffectTaxonomy"])
        self.assertIn("READ_ONLY", policy["sideEffectTaxonomy"])
        self.assertIn("git diff --name-only omits untracked files", policy["commitCloseoutRisk"])

class TestTeamRouterRegistryAndReadWindow(unittest.TestCase):
    def test_registry_path_uses_shared_state_root_not_worktree_root(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            canonical = base / "repo"
            worktree = base / "repo-wt"
            canonical.mkdir()
            worktree.mkdir()
            a = team_router.resolve_state_root(worktree, canonical_root=canonical)
            b = team_router.resolve_state_root(canonical, canonical_root=canonical)
            self.assertEqual(a, b)
            self.assertEqual(
                team_router.registry_path(a, "project-123"),
                canonical / ".codex-team-router" / "projects" / "project-123" / "registry.json",
            )

    def test_state_root_rejects_codex_tmp(self):
        with tempfile.TemporaryDirectory() as td:
            forbidden_root = Path(td) / ".codex-tmp" / "team-router"
            project_root = Path(td) / "repo"

            with self.assertRaises(team_router.StateStoreError):
                team_router.resolve_state_root(
                    project_root,
                    explicit_state_root=forbidden_root,
                )

    def test_state_root_rejects_windows_codex_tmp(self):
        with self.assertRaises(team_router.StateStoreError):
            team_router.resolve_state_root(
                r"D:\codex\repo",
                explicit_state_root=r"D:\.codex-tmp\team-router",
            )

    def test_read_window_without_time_or_message_id_is_unreachable(self):
        messages = [{"text": "summary only"}]
        anchor = {"messageId": None, "sentAt": "2026-06-22T00:00:00+08:00"}
        self.assertFalse(team_router.read_window_covers_anchor(messages, anchor))

    def test_read_window_compares_timestamp_offsets_by_instant(self):
        messages = [{"sentAt": "2026-06-22T00:30:00+09:00"}]
        anchor = {"messageId": None, "sentAt": "2026-06-21T23:45:00+08:00"}
        self.assertTrue(team_router.read_window_covers_anchor(messages, anchor))

    def test_observation_schema_requires_bounded_fields(self):
        obs = team_router.make_observation(
            "callback_raw",
            "executor",
            "thread-1",
            "2026-06-22T00:00:00+08:00",
            "TEAM_ROUTER_CALLBACK taskId=ctr-1",
            {"status": "done"},
        )
        self.assertEqual(obs["type"], "callback_raw")
        self.assertEqual(obs["parsedFields"]["status"], "done")

    def test_observation_rejects_oversized_content(self):
        with self.assertRaises(team_router.ProtocolError):
            team_router.make_observation(
                "callback_raw",
                "executor",
                "thread-1",
                "2026-06-22T00:00:00+08:00",
                "x" * (team_router.MAX_OBSERVATION_CONTENT_CHARS + 1),
                {"status": "done"},
            )


class TestTeamRouterJsonState(unittest.TestCase):
    def test_registry_round_trip_normalizes_missing_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            path = team_router.registry_path(root, project_id)
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps({
                    "projects": {
                        project_id: {
                            "roles": {
                                "manager": {"threadId": "thread-1"},
                            },
                        },
                    },
                }),
                encoding="utf-8",
            )

            registry = team_router.load_registry(root, project_id)

            self.assertEqual(registry["version"], 1)
            self.assertEqual(registry["stateRoot"], str(root.resolve()))
            project = registry["projects"][project_id]
            self.assertEqual(project["projectId"], project_id)
            self.assertEqual(project["roles"]["manager"]["threadId"], "thread-1")

            saved = team_router.save_registry(root, project_id, registry)
            self.assertEqual(saved, registry)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), registry)

    def test_task_ledger_round_trip_normalizes_missing_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"
            path = team_router.task_path(root, project_id, task_id)
            path.parent.mkdir(parents=True)
            path.write_text('{"objective":"inspect docs"}', encoding="utf-8")

            ledger = team_router.load_task_ledger(root, project_id, task_id)

            self.assertEqual(ledger["version"], 1)
            self.assertEqual(ledger["taskId"], task_id)
            self.assertEqual(ledger["projectId"], project_id)
            self.assertEqual(ledger["stateRoot"], str(root.resolve()))
            self.assertEqual(ledger["objective"], "inspect docs")
            self.assertEqual(ledger["status"], "created")
            self.assertEqual(ledger["reworkCount"], 0)
            self.assertEqual(ledger["maxRework"], 3)
            self.assertEqual(ledger["dispatches"], [])
            self.assertEqual(ledger["observations"], [])

            ledger["status"] = "awaiting_callback"
            team_router.save_task_ledger(root, project_id, task_id, ledger)
            self.assertEqual(
                team_router.load_task_ledger(root, project_id, task_id)["status"],
                "awaiting_callback",
            )

    def test_missing_task_ledger_raises_state_store_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"

            with self.assertRaises(team_router.StateStoreError) as caught:
                team_router.load_task_ledger(root, project_id, task_id)

            self.assertIn("missing JSON file", str(caught.exception))

    def test_new_task_ledger_rejects_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"

            invalid_calls = [
                {
                    "objective": "",
                    "project_local_path": ".",
                    "max_rework": 3,
                    "message": "objective must be a non-empty string",
                },
                {
                    "objective": object(),
                    "project_local_path": ".",
                    "max_rework": 3,
                    "message": "objective must be a non-empty string",
                },
                {
                    "objective": "inspect docs",
                    "project_local_path": ".",
                    "max_rework": True,
                    "message": "maxRework must be a non-negative integer",
                },
                {
                    "objective": "inspect docs",
                    "project_local_path": ".",
                    "max_rework": -1,
                    "message": "maxRework must be a non-negative integer",
                },
            ]
            for kwargs in invalid_calls:
                message = kwargs.pop("message")
                with self.subTest(message=message):
                    with self.assertRaises(team_router.StateStoreError) as caught:
                        team_router.new_task_ledger(
                            root,
                            project_id,
                            task_id,
                            **kwargs,
                        )
                    self.assertIn(message, str(caught.exception))

    def test_bad_registry_json_raises_state_store_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            path = team_router.registry_path(root, project_id)
            path.parent.mkdir(parents=True)
            path.write_text("{bad json", encoding="utf-8")

            with self.assertRaises(team_router.StateStoreError) as caught:
                team_router.load_registry(root, project_id)

            self.assertIn("invalid JSON", str(caught.exception))

    def test_bad_task_ledger_json_raises_state_store_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"
            path = team_router.task_path(root, project_id, task_id)
            path.parent.mkdir(parents=True)
            path.write_text("{bad json", encoding="utf-8")

            with self.assertRaises(team_router.StateStoreError) as caught:
                team_router.load_task_ledger(root, project_id, task_id)

            self.assertIn("invalid JSON", str(caught.exception))

    def test_task_ledger_read_permission_error_raises_state_store_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"

            with mock.patch.object(Path, "open", side_effect=PermissionError("denied")):
                with self.assertRaises(team_router.StateStoreError) as caught:
                    team_router.load_task_ledger(root, project_id, task_id)

            self.assertIn("cannot read JSON file", str(caught.exception))

    def test_atomic_save_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            project_id = "project-123"
            task_id = "ctr-20260622-160000-a7f3"
            ledger = team_router.new_task_ledger(
                root,
                project_id,
                task_id,
                objective="inspect docs",
                project_local_path="D:\\codex\\codex-dynamic-workflow",
            )

            team_router.save_task_ledger(root, project_id, task_id, ledger)

            path = team_router.task_path(root, project_id, task_id)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), ledger)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_two_worktrees_share_registry_via_canonical_root(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            canonical = base / "repo"
            worktree = base / "repo-wt"
            canonical.mkdir()
            worktree.mkdir()
            project_id = "project-123"
            state_a = team_router.resolve_state_root(worktree, canonical_root=canonical)
            state_b = team_router.resolve_state_root(canonical, canonical_root=canonical)
            self.assertEqual(state_a, state_b)

            registry = team_router.load_registry(state_a, project_id)
            registry["projects"][project_id]["roles"]["manager"] = {
                "threadId": "thread-1",
                "title": "TeamRouter manager - repo",
            }
            team_router.save_registry(state_a, project_id, registry)

            reloaded = team_router.load_registry(state_b, project_id)
            self.assertEqual(
                reloaded["projects"][project_id]["roles"]["manager"]["threadId"],
                "thread-1",
            )


class TestTeamRouterManagerIntegration(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name) / "state"
        self.project_id = "project-123"
        self.task_id = "ctr-20260622-160000-a7f3"
        self.roles = {
            "manager": {
                "threadId": "thread-manager",
                "title": "TeamRouter manager - repo",
            },
            "executor": {
                "threadId": "thread-executor",
                "title": "TeamRouter executor - repo",
            },
            "verifier": {
                "threadId": "thread-verifier",
                "title": "TeamRouter verifier - repo",
            },
        }

    def tearDown(self):
        self.td.cleanup()

    def _ready_ledger(self, max_rework=3):
        return team_router.create_team_task(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            roles=self.roles,
            observed_at="2026-06-22T20:00:00+08:00",
            max_rework=max_rework,
        )

    def _awaiting_plan_ledger(self):
        self._ready_ledger()
        return team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id="msg-plan",
        )

    def _planned_ledger(self, max_rework=3):
        self._ready_ledger(max_rework=max_rework)
        team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id="msg-plan",
        )
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=ctr-20260622-160000-a7f3\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none"},
        ]
        return team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

    def _awaiting_callback_ledger(self, max_rework=3):
        self._planned_ledger(max_rework=max_rework)
        return team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
        )

    def _verifying_ledger(self, max_rework=3):
        self._awaiting_callback_ledger(max_rework=max_rework)
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
        ]
        return team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

    def test_create_team_task_writes_registry_roles_and_task_file(self):
        ledger = self._ready_ledger()

        self.assertEqual(ledger["status"], "roles_ready")
        saved_ledger = team_router.load_task_ledger(self.root, self.project_id, self.task_id)
        self.assertEqual(saved_ledger["objective"], "inspect docs")
        registry = team_router.load_registry(self.root, self.project_id)
        project = registry["projects"][self.project_id]
        self.assertEqual(project["roles"]["manager"]["threadId"], "thread-manager")
        self.assertEqual(project["roles"]["executor"]["threadId"], "thread-executor")
        self.assertEqual(project["roles"]["verifier"]["threadId"], "thread-verifier")
        self.assertEqual(project["roles"]["manager"]["lastObservedAt"], "2026-06-22T20:00:00+08:00")

    def test_plan_request_and_plan_capture_record_anchors_and_fields(self):
        ledger = self._ready_ledger()
        message = team_router.make_plan_request_message(
            ledger["taskId"],
            ledger["objective"],
            "read-only",
        )
        self.assertIn("TEAM_ROUTER_PLAN_REQUEST taskId=ctr-20260622-160000-a7f3", message)
        self.assertIn("permission: read-only", message)

        awaiting = team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id="msg-plan",
        )
        self.assertEqual(awaiting["status"], "awaiting_plan")
        self.assertEqual(awaiting["planRequest"]["searchAnchor"]["messageId"], "msg-plan")

        planned = self._planned_ledger()
        self.assertEqual(planned["status"], "planned")
        self.assertEqual(planned["plan"]["fields"]["executorPrompt"], "inspect src")

    def test_plan_capture_marks_unreachable_when_read_window_misses_anchor(self):
        ledger = self._awaiting_plan_ledger()
        messages = [{"text": "plan without ids or timestamps"}]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "plan_unreachable")

    def test_plan_capture_keeps_waiting_when_window_covers_but_marker_missing(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-later", "sentAt": "2026-06-22T20:01:30+08:00", "text": "still planning"},
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_plan")

    def test_plan_capture_blocks_escalation_required(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: escalation-required\nscope: src\nstopWhen: done\nriskBoundary: needs write access\nexecutorPrompt: inspect src\nnotes: none" % ledger["taskId"]},
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "blocked")

    def _high_risk_awaiting_callback_ledger(self):
        ledger = self._awaiting_callback_ledger()
        ledger["objective"] = "update role protocol and orchestration policy"
        ledger["plan"]["fields"]["scope"] = "role protocol and orchestration policy"
        return team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

    def test_executor_dispatch_records_attempt_and_recovery_anchor(self):
        ledger = self._planned_ledger()
        message = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"},
        )
        self.assertIn("callbackMode: self-thread-marker", message)
        self.assertIn("callbackMarker: TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", message)
        anchor_line = next(line for line in message.splitlines() if line.startswith("searchAnchor: "))
        self.assertEqual(anchor_line, "searchAnchor: {\"messageId\": \"msg-dispatch\", \"sentAt\": \"2026-06-22T20:02:00+08:00\"}")
        anchor_json = anchor_line.removeprefix("searchAnchor: ")
        self.assertEqual(json.loads(anchor_json), {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"})

        updated = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
        )
        self.assertEqual(updated["status"], "awaiting_callback")
        self.assertEqual(updated["dispatches"][-1]["attempt"], 1)
        registry = team_router.load_registry(self.root, self.project_id)
        read_request = team_router.recovery_read_request(updated, registry, "executor")
        self.assertEqual(read_request["threadId"], "thread-executor")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-dispatch")

    def test_executor_dispatch_supports_direct_return_delivery_metadata(self):
        ledger = self._planned_ledger()

        message = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00"},
            return_thread_id="parent-manager-thread",
        )

        self.assertIn("returnThreadId: parent-manager-thread", message)
        self.assertIn("callbackDelivery: direct-send", message)
        self.assertIn("callbackFallback: self-thread-marker", message)
        self.assertIn(
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK block>)",
            message,
        )
        self.assertIn("callbackMarker: TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", message)

        updated = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        latest = updated["dispatches"][-1]
        self.assertEqual(latest["returnThreadId"], "parent-manager-thread")
        self.assertEqual(latest["callbackDelivery"], "direct-send")
        self.assertEqual(latest["callbackFallback"], "self-thread-marker")
        self.assertEqual(latest["fallbackSearchAnchor"], latest["searchAnchor"])
        self.assertEqual(
            latest["returnSearchAnchor"],
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )

    def test_executor_dispatch_search_anchor_serializes_null_message_id(self):
        ledger = self._planned_ledger()

        message = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )

        anchor_line = next(line for line in message.splitlines() if line.startswith("searchAnchor: "))
        self.assertEqual(anchor_line, "searchAnchor: {\"messageId\": null, \"sentAt\": \"2026-06-22T20:02:00+08:00\"}")

    def test_callback_capture_uses_dispatch_anchor_from_ledger(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["type"], "callback_raw")
        self.assertEqual(updated["observations"][-1]["threadId"], "thread-executor")

    def test_callback_capture_accepts_same_timestamp_response_for_time_only_anchor(self):
        ledger = self._planned_ledger()
        dispatch_prompt = team_router.make_executor_dispatch_message(
            ledger["taskId"],
            ledger["plan"]["fields"],
            "read-only",
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )
        ledger = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "type": "userMessage",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": dispatch_prompt,
            },
            {
                "type": "agentMessage",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: same second\nevidence: tests\nrisks: none\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "same second")

    def test_callback_capture_falls_back_to_timestamp_when_send_message_id_missing_from_read(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {
                "type": "userMessage",
                "messageId": "item-dispatch",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_DISPATCH taskId=ctr-20260622-160000-a7f3",
            },
            {
                "type": "agentMessage",
                "messageId": "item-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: id mismatch\nevidence: live thread\nrisks: none\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "id mismatch")

    def test_callback_capture_uses_timestamp_when_read_thread_is_newest_first(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {
                "type": "agentMessage",
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: newest first\nevidence: live thread\nrisks: none\nnext: none",
            },
            {
                "type": "userMessage",
                "messageId": "msg-dispatch",
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_DISPATCH taskId=ctr-20260622-160000-a7f3",
            },
            {
                "type": "agentMessage",
                "messageId": "msg-before-dispatch",
                "sentAt": "2026-06-22T20:01:30+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: stale\nevidence: old\nrisks: stale\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "newest first")

    def test_callback_capture_preserves_multiline_summary(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: first line\nsecond line\nthird line\nevidence: tests\nrisks: none\nnext: none"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(
            updated["observations"][-1]["parsedFields"]["summary"],
            "first line\nsecond line\nthird line",
        )

    def test_callback_capture_marks_unreachable_when_read_window_misses_anchor(self):
        ledger = self._awaiting_callback_ledger()
        messages = [{"text": "summary without ids or timestamps"}]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "callback_unreachable")

    def test_callback_capture_keeps_waiting_when_window_covers_but_marker_missing(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-later", "sentAt": "2026-06-22T20:03:00+08:00", "text": "still working"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_callback")

    def test_high_risk_executor_callback_enters_reviewer_gate_instead_of_verifier(self):
        ledger = self._high_risk_awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: protocol changed\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "reviewing")
        self.assertIsNone(updated["verification"])

    def test_low_risk_executor_callback_still_enters_verifier_gate(self):
        ledger = self._awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: verifier"},
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")

    def test_watch_sends_reviewer_request_for_high_risk_callback(self):
        adapter = FakeThreadAdapter()
        ledger = self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        adapter.messages.setdefault("thread-executor", []).append({
            "messageId": "msg-dispatch",
            "sentAt": "2026-06-22T20:02:00+08:00",
            "text": "TEAM_ROUTER_DISPATCH taskId=%s" % self.task_id,
        })
        adapter.append_reply(
            ledger["dispatches"][-1]["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
            return_thread_id="parent-manager-thread",
        )

        self.assertEqual(update["action"], "watch_sent_reviewer_request")
        self.assertEqual(update["status"], "reviewing")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-reviewer")
        prompt = adapter.sent[-1]["kwargs"]["prompt"]
        self.assertIn("reviewDelivery: direct-send", prompt)
        self.assertIn("reviewFallback: self-thread-marker", prompt)
        self.assertNotIn("verdictDelivery: direct-send", prompt)
        self.assertEqual(update["nextWakeup"]["role"], "reviewer")
        self.assertEqual(update["nextWakeup"]["reason"], "awaiting TEAM_ROUTER_REVIEW")
        self.assertEqual(
            update["nextWakeup"]["searchAnchor"],
            update["ledger"]["review"]["request"]["fallbackSearchAnchor"],
        )

    def test_review_unreachable_next_wakeup_points_to_reviewer_fallback_anchor(self):
        self._high_risk_awaiting_callback_ledger()
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id},
        ]
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            callback_messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        reviewing = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        reviewing["status"] = "review_unreachable"
        reviewing = team_router.save_task_ledger(self.root, self.project_id, self.task_id, reviewing)

        wakeup = team_router._watch_next_wakeup(reviewing)

        self.assertIsNotNone(wakeup)
        self.assertEqual(wakeup["role"], "reviewer")
        self.assertEqual(wakeup["reason"], "awaiting TEAM_ROUTER_REVIEW")
        self.assertEqual(wakeup["searchAnchor"], reviewing["review"]["request"]["fallbackSearchAnchor"])

    def test_watch_reviewer_request_inherits_return_thread_id_after_executor_fallback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        ledger["objective"] = "Team Router reviewer runtime gate rework"
        ledger["plan"]["fields"]["scope"] = "role protocol and orchestration policy"
        ledger["plan"]["fields"]["riskBoundary"] = "runtime gate change"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        ledger = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:02:30+08:00",
        )
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % ledger["taskId"],
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_reviewer_request")
        self.assertIn("returnThreadId: parent-manager-thread", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertEqual(update["ledger"]["review"]["request"]["returnThreadId"], "parent-manager-thread")
        self.assertEqual(update["nextWakeup"]["role"], "reviewer")

    def test_watch_verifier_request_inherits_return_thread_id_after_executor_fallback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        ledger = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: verifier" % ledger["taskId"],
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertIn("returnThreadId: parent-manager-thread", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertEqual(update["ledger"]["verification"]["request"]["returnThreadId"], "parent-manager-thread")

    def test_watch_verifier_request_inherits_return_thread_id_after_reviewer_fallback(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id},
            ],
            captured_at="2026-06-22T20:04:00+08:00",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:04:30+08:00",
        )
        team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["thread-reviewer"] = [
            {"messageId": "msg-review", "sentAt": "2026-06-22T20:05:00+08:00", "text": "review request"},
            {
                "messageId": "msg-review-pass",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": "TEAM_ROUTER_REVIEW taskId=%s\nresult: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none" % self.task_id,
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertIn("returnThreadId: parent-manager-thread", adapter.sent[-1]["kwargs"]["prompt"])
        self.assertEqual(update["ledger"]["verification"]["request"]["returnThreadId"], "parent-manager-thread")

    def test_watch_captures_reviewer_direct_return_and_sends_verifier(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("pass"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["result"], "pass")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-verifier")
        self.assertIn("TEAM_ROUTER_VERIFY taskId=%s" % self.task_id, adapter.sent[-1]["kwargs"]["prompt"])

    def test_watch_ignores_reviewer_direct_return_with_wrong_source_thread_id(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("pass", source_thread_id="thread-other-reviewer"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "review_unreachable")
        self.assertEqual(adapter.sent, [])
        self.assertNotIn("result", update["ledger"]["review"])
        self.assertIsNone(update["ledger"]["verification"])

    def test_watch_ignores_reviewer_direct_return_with_wrong_task_id(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("pass", task_id="ctr-20260622-wrong-task"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "review_unreachable")
        self.assertEqual(adapter.sent, [])
        self.assertNotIn("result", update["ledger"]["review"])
        self.assertIsNone(update["ledger"]["verification"])

    def test_watch_reads_reviewer_direct_return_needs_rework_without_verifier(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("needs_rework"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "needs_rework")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["result"], "needs_rework")
        self.assertEqual(adapter.sent, [])
        self.assertIsNone(update["ledger"]["verification"])

    def test_watch_reads_reviewer_direct_return_blocked_without_verifier(self):
        adapter = self._record_reviewer_direct_return_request()
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-review-return",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": self._reviewer_direct_return_wrapper("blocked"),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_reviewer_review")
        self.assertEqual(update["status"], "blocked")
        self.assertEqual(update["ledger"]["review"]["result"]["fields"]["result"], "blocked")
        self.assertEqual(adapter.sent, [])
        self.assertIsNone(update["ledger"]["verification"])

    def _record_reviewer_direct_return_request(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            [
                {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id},
            ],
            captured_at="2026-06-22T20:04:00+08:00",
        )
        reviewing = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        request = reviewing["review"]["request"]
        self.assertEqual(request["reviewDelivery"], "direct-send")
        self.assertEqual(request["reviewFallback"], "self-thread-marker")
        self.assertNotIn("verdictDelivery", request)
        self.assertNotIn("verdictFallback", request)
        return adapter

    def _reviewer_direct_return_wrapper(self, result, task_id=None, source_thread_id="thread-reviewer"):
        review_task_id = task_id or self.task_id
        return (
            "<codex_delegation>\n"
            "  <source_thread_id>%s</source_thread_id>\n"
            "  <input>TEAM_ROUTER_REVIEW taskId=%s\n"
            "result: %s\n"
            "summary: review result\n"
            "findings: focused check\n"
            "requiredChanges: none\n"
            "evidenceChecked: tests\n"
            "risks: none</input>\n"
            "</codex_delegation>"
        ) % (source_thread_id, review_task_id, result)

    def test_reviewer_pass_sends_verifier_request_and_needs_rework_or_blocked_stops(self):
        ledger = self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}},
            "2026-06-22T20:02:30+08:00",
        )
        callback_messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]
        reviewing = team_router.capture_executor_callback_from_read(
            self.root, self.project_id, self.task_id, callback_messages, captured_at="2026-06-22T20:04:00+08:00"
        )
        self.assertEqual(reviewing["status"], "reviewing")
        reviewing = team_router.record_reviewer_request_sent(
            self.root, self.project_id, self.task_id, reviewer_thread_id="thread-reviewer", sent_at="2026-06-22T20:05:00+08:00", message_id="msg-review"
        )
        pass_messages = [
            {"messageId": "msg-review", "sentAt": "2026-06-22T20:05:00+08:00", "text": "review"},
            {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]
        passed = team_router.capture_reviewer_review_from_read(
            self.root, self.project_id, self.task_id, pass_messages, captured_at="2026-06-22T20:07:00+08:00"
        )
        self.assertEqual(passed["status"], "verifying")
        self.assertEqual(passed["review"]["result"]["fields"]["result"], "pass")

        self.tearDown(); self.setUp()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(self.root, self.project_id, {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}}, "2026-06-22T20:02:30+08:00")
        team_router.capture_executor_callback_from_read(self.root, self.project_id, self.task_id, callback_messages, captured_at="2026-06-22T20:04:00+08:00")
        team_router.record_reviewer_request_sent(self.root, self.project_id, self.task_id, reviewer_thread_id="thread-reviewer", sent_at="2026-06-22T20:05:00+08:00", message_id="msg-review")
        rework = team_router.capture_reviewer_review_from_read(
            self.root, self.project_id, self.task_id, [pass_messages[0], {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: gap\nfindings: missing test\nrequiredChanges: add test\nevidenceChecked: tests\nrisks: none"}], captured_at="2026-06-22T20:07:00+08:00"
        )
        self.assertEqual(rework["status"], "needs_rework")

        self.tearDown(); self.setUp()
        self._high_risk_awaiting_callback_ledger()
        team_router.update_registry_roles(self.root, self.project_id, {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-test"}}, "2026-06-22T20:02:30+08:00")
        team_router.capture_executor_callback_from_read(self.root, self.project_id, self.task_id, callback_messages, captured_at="2026-06-22T20:04:00+08:00")
        team_router.record_reviewer_request_sent(self.root, self.project_id, self.task_id, reviewer_thread_id="thread-reviewer", sent_at="2026-06-22T20:05:00+08:00", message_id="msg-review")
        blocked = team_router.capture_reviewer_review_from_read(
            self.root, self.project_id, self.task_id, [pass_messages[0], {"messageId": "msg-review-result", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3\nresult: blocked\nsummary: blocked\nfindings: unsafe\nrequiredChanges: redesign\nevidenceChecked: tests\nrisks: high"}], captured_at="2026-06-22T20:07:00+08:00"
        )
        self.assertEqual(blocked["status"], "blocked")

    def test_reviewer_gate_without_role_thread_requires_role_conversation_not_subagent(self):
        adapter = FakeThreadAdapter()
        self._high_risk_awaiting_callback_ledger()
        messages = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: callback\nevidence: tests\nrisks: none\nnext: reviewer"},
        ]
        team_router.capture_executor_callback_from_read(self.root, self.project_id, self.task_id, messages, captured_at="2026-06-22T20:04:00+08:00")

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.send_reviewer_request_with_adapter(
                self.root, self.project_id, self.task_id, thread_adapter=adapter, permission="read-only", sent_at="2026-06-22T20:05:00+08:00"
            )
        self.assertIn("reviewer role conversation", str(ctx.exception))
        self.assertIn("subagent fallback is not allowed", str(ctx.exception))

    def test_verifier_pass_writes_verification_and_closeout(self):
        ledger = self._verifying_ledger()
        verify_message = team_router.make_verifier_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
        )
        self.assertIn("TEAM_ROUTER_VERIFY taskId=ctr-20260622-160000-a7f3", verify_message)

        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        registry = team_router.load_registry(self.root, self.project_id)
        read_request = team_router.recovery_read_request(requested, registry, "verifier")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-verify")

        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]
        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["verification"]["verdict"]["fields"]["result"], "pass")
        self.assertEqual(updated["closeout"]["status"], "done")
        self.assertEqual(updated["closeout"]["remainingTodos"], "none")

    def test_verifier_request_supports_direct_return_delivery_metadata(self):
        ledger = self._verifying_ledger()

        verify_message = team_router.make_verifier_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
            return_thread_id="parent-manager-thread",
        )

        self.assertIn("returnThreadId: parent-manager-thread", verify_message)
        self.assertIn("verdictDelivery: direct-send", verify_message)
        self.assertIn("verdictFallback: self-thread-marker", verify_message)
        self.assertIn(
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)",
            verify_message,
        )
        self.assertIn("callbackMarker: TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3", verify_message)

        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        request = requested["verification"]["request"]
        self.assertEqual(request["returnThreadId"], "parent-manager-thread")
        self.assertEqual(request["verdictDelivery"], "direct-send")
        self.assertEqual(request["verdictFallback"], "self-thread-marker")
        self.assertEqual(request["fallbackSearchAnchor"], request["searchAnchor"])
        self.assertEqual(
            request["returnSearchAnchor"],
            {"messageId": None, "sentAt": "2026-06-22T20:05:00+08:00"},
        )


    def test_reviewer_request_supports_direct_return_delivery_metadata(self):
        ledger = self._verifying_ledger()

        review_message = team_router.make_reviewer_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
            return_thread_id="parent-manager-thread",
        )

        self.assertIn("returnThreadId: parent-manager-thread", review_message)
        self.assertIn("reviewDelivery: direct-send", review_message)
        self.assertIn("reviewFallback: self-thread-marker", review_message)
        self.assertIn(
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)",
            review_message,
        )
        self.assertIn("reviewMarker: TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3", review_message)
        self.assertIn("reviewerMode: read-only/adversarial", review_message)

        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {
                "reviewer": {
                    "threadId": "thread-reviewer",
                    "title": "审查者-test",
                }
            },
            "2026-06-22T20:04:30+08:00",
        )
        requested = team_router.record_reviewer_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            reviewer_thread_id="thread-reviewer",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-review",
            return_thread_id="parent-manager-thread",
        )
        request = requested["review"]["request"]
        self.assertEqual(request["returnThreadId"], "parent-manager-thread")
        self.assertEqual(request["reviewDelivery"], "direct-send")
        self.assertEqual(request["reviewFallback"], "self-thread-marker")
        self.assertEqual(request["fallbackSearchAnchor"], request["searchAnchor"])
        self.assertEqual(requested["status"], "reviewing")

        registry = team_router.load_registry(self.root, self.project_id)
        read_request = team_router.recovery_read_request(requested, registry, "reviewer")
        self.assertEqual(read_request["threadId"], "thread-reviewer")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-review")
        self.assertEqual(read_request["expectedCallback"], "TEAM_ROUTER_REVIEW taskId=ctr-20260622-160000-a7f3")
    def test_verifier_capture_accepts_same_timestamp_response_for_time_only_anchor(self):
        ledger = self._verifying_ledger()
        verify_prompt = team_router.make_verifier_request_message(
            ledger["taskId"],
            ledger["observations"][-1]["content"],
            "read-only",
            "src",
        )
        ledger = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "type": "userMessage",
                "sentAt": "2026-06-22T20:05:00+08:00",
                "text": verify_prompt,
            },
            {
                "type": "agentMessage",
                "sentAt": "2026-06-22T20:05:00+08:00",
                "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: same second\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none",
            },
        ]

        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "done")
        self.assertEqual(updated["closeout"]["summary"], "same second")

    def test_verifier_needs_rework_respects_max_rework(self):
        ledger = self._verifying_ledger(max_rework=0)
        team_router.save_task_ledger(self.root, self.project_id, ledger["taskId"], ledger)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
        ]

        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(updated["status"], "blocked")
        self.assertEqual(updated["closeout"]["status"], "blocked")
        self.assertEqual(updated["closeout"]["nextAction"], "fix docs")
        self.assertEqual(updated["closeout"]["remainingTodos"], "fix docs")

    def test_terminal_task_cannot_be_redispatched(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )

        with self.assertRaises(team_router.StateStoreError):
            team_router.record_executor_dispatch_sent(
                self.root,
                self.project_id,
                ledger["taskId"],
                executor_thread_id="thread-executor",
                sent_at="2026-06-22T20:08:00+08:00",
                message_id="msg-again",
            )

        saved = team_router.load_task_ledger(self.root, self.project_id, ledger["taskId"])
        self.assertEqual(saved["status"], "done")
        self.assertEqual(len(saved["dispatches"]), 1)

    def test_done_verifier_capture_is_idempotent(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        observation_count = len(done["observations"])

        repeated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(repeated["status"], "done")
        self.assertEqual(len(repeated["observations"]), observation_count)
        self.assertEqual(repeated["closeout"]["capturedAt"], "2026-06-22T20:07:00+08:00")

    def test_blocked_terminal_task_rejects_guarded_manager_executor_verifier_actions(self):
        plan_ledger = self._awaiting_plan_ledger()
        plan_ledger["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, plan_ledger["taskId"], plan_ledger)
        with self.assertRaises(team_router.StateStoreError):
            team_router.record_plan_request_sent(
                self.root,
                self.project_id,
                plan_ledger["taskId"],
                manager_thread_id="thread-manager",
                sent_at="2026-06-22T20:09:00+08:00",
                message_id="msg-plan-again",
            )
        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_manager_plan_from_read(
                self.root,
                self.project_id,
                plan_ledger["taskId"],
                [{"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"}],
                captured_at="2026-06-22T20:09:00+08:00",
            )

        self.tearDown()
        self.setUp()
        callback_ledger = self._awaiting_callback_ledger()
        callback_ledger["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, callback_ledger["taskId"], callback_ledger)
        with self.assertRaises(team_router.StateStoreError):
            team_router.record_executor_dispatch_sent(
                self.root,
                self.project_id,
                callback_ledger["taskId"],
                executor_thread_id="thread-executor",
                sent_at="2026-06-22T20:09:00+08:00",
                message_id="msg-dispatch-again",
            )
        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_executor_callback_from_read(
                self.root,
                self.project_id,
                callback_ledger["taskId"],
                [{"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"}],
                captured_at="2026-06-22T20:09:00+08:00",
            )

        self.tearDown()
        self.setUp()
        verifier_ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            verifier_ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        verifier_ledger = team_router.load_task_ledger(self.root, self.project_id, verifier_ledger["taskId"])
        verifier_ledger["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, verifier_ledger["taskId"], verifier_ledger)
        with self.assertRaises(team_router.StateStoreError):
            team_router.record_verifier_request_sent(
                self.root,
                self.project_id,
                verifier_ledger["taskId"],
                verifier_thread_id="thread-verifier",
                sent_at="2026-06-22T20:09:00+08:00",
                message_id="msg-verify-again",
            )
        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_verifier_verdict_from_read(
                self.root,
                self.project_id,
                verifier_ledger["taskId"],
                [{"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"}],
                captured_at="2026-06-22T20:09:00+08:00",
            )

    def test_escalation_required_blocks_executor_dispatch(self):
        ledger = self._awaiting_plan_ledger()
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00", "text": "request"},
            {"messageId": "msg-plan-result", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: escalation-required\nscope: src\nstopWhen: done\nriskBoundary: needs write access\nexecutorPrompt: inspect src\nnotes: none" % ledger["taskId"]},
        ]
        blocked = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        with self.assertRaises(team_router.StateStoreError):
            team_router.record_executor_dispatch_sent(
                self.root,
                self.project_id,
                ledger["taskId"],
                executor_thread_id="thread-executor",
                sent_at="2026-06-22T20:02:00+08:00",
                message_id="msg-dispatch",
            )
        self.assertEqual(blocked["dispatches"], [])

    def test_sent_at_fallback_ignores_anchor_message_template(self):
        self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_DISPATCH taskId=ctr-20260622-160000-a7f3\nTEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done | blocked\nfinal: true\nsummary: <3-7 lines>\nevidence: <evidence>\nrisks: <risks>\nnext: <next>",
            },
            {
                "sentAt": "2026-06-22T20:02:30+08:00",
                "text": "still working",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_callback")

    def test_plan_sent_at_fallback_ignores_request_template(self):
        ledger = self._ready_ledger()
        team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            manager_thread_id="thread-manager",
            sent_at="2026-06-22T20:01:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:01:00+08:00",
                "text": team_router.make_plan_request_message(ledger["taskId"], ledger["objective"], "read-only"),
            },
            {
                "sentAt": "2026-06-22T20:01:30+08:00",
                "text": "still planning",
            },
        ]

        updated = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        self.assertEqual(updated["status"], "awaiting_plan")

    def test_verifier_sent_at_fallback_ignores_request_template(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:05:00+08:00",
                "text": team_router.make_verifier_request_message(
                    ledger["taskId"],
                    ledger["observations"][-1]["content"],
                    "read-only",
                    "src",
                ),
            },
            {
                "sentAt": "2026-06-22T20:05:30+08:00",
                "text": "still verifying",
            },
        ]

        updated = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:06:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")

    def test_same_timestamp_callback_without_message_id_is_captured(self):
        self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id=None,
        )
        messages = [
            {
                "sentAt": "2026-06-22T20:02:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: same timestamp\nevidence: tests\nrisks: none\nnext: none",
            },
        ]

        updated = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            messages,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(updated["observations"][-1]["parsedFields"]["summary"], "same timestamp")

    def test_rework_redispatch_can_finish_with_fresh_closeout(self):
        ledger = self._verifying_ledger(max_rework=2)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        needs_rework = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["closeout"]["status"], "needs_rework")

        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:08:00+08:00",
            message_id="msg-rework",
        )
        verifying = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-rework", "sentAt": "2026-06-22T20:08:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback-2", "sentAt": "2026-06-22T20:09:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: fixed\nevidence: tests\nrisks: none\nnext: none"},
            ],
            captured_at="2026-06-22T20:09:30+08:00",
        )
        self.assertEqual(verifying["status"], "verifying")
        self.assertIsNone(verifying["closeout"])
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:10:00+08:00",
            message_id="msg-verify-2",
        )

        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify-2", "sentAt": "2026-06-22T20:10:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict-2", "sentAt": "2026-06-22T20:11:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok after rework\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:11:30+08:00",
        )

        self.assertEqual(done["status"], "done")
        self.assertEqual(done["closeout"]["status"], "done")
        self.assertEqual(done["closeout"]["summary"], "ok after rework")

    def test_manager_capture_requires_plan_request_anchor(self):
        ledger = self._ready_ledger()
        ledger["planRequest"] = None
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:30+08:00", "text": "TEAM_ROUTER_PLAN taskId=ctr-20260622-160000-a7f3\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none"},
        ]

        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_manager_plan_from_read(
                self.root,
                self.project_id,
                self.task_id,
                messages,
                captured_at="2026-06-22T20:01:40+08:00",
            )

    def test_verifier_capture_requires_verification_request_anchor(self):
        ledger = self._verifying_ledger()
        ledger["verification"] = None
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)
        messages = [
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
        ]

        with self.assertRaises(team_router.StateStoreError):
            team_router.capture_verifier_verdict_from_read(
                self.root,
                self.project_id,
                self.task_id,
                messages,
                captured_at="2026-06-22T20:07:00+08:00",
            )

    def test_confirm_rework_dispatch_increments_rework_count(self):
        ledger = self._verifying_ledger(max_rework=2)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        messages = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
        ]
        needs_rework = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            messages,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["status"], "needs_rework")

        dispatched = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:08:00+08:00",
            message_id="msg-rework",
        )

        self.assertEqual(dispatched["status"], "awaiting_callback")
        self.assertEqual(dispatched["reworkCount"], 1)
        self.assertEqual(dispatched["dispatches"][-1]["attempt"], 2)
        self.assertIsNone(dispatched["closeout"])

    def test_old_task_ledger_normalizes_plan_fields(self):
        path = team_router.task_path(self.root, self.project_id, self.task_id)
        path.parent.mkdir(parents=True)
        path.write_text('{"objective":"inspect docs"}', encoding="utf-8")

        ledger = team_router.load_task_ledger(self.root, self.project_id, self.task_id)

        self.assertIn("planRequest", ledger)
        self.assertIsNone(ledger["planRequest"])
        self.assertIn("plan", ledger)
        self.assertIsNone(ledger["plan"])
    def test_recovery_read_request_uses_registry_thread_when_ledger_lacks_thread_id(self):
        ledger = self._ready_ledger()
        ledger["planRequest"] = {
            "searchAnchor": {"messageId": "msg-plan", "sentAt": "2026-06-22T20:01:00+08:00"},
            "expectedCallback": "TEAM_ROUTER_PLAN taskId=ctr-20260622-160000-a7f3",
        }
        registry = team_router.load_registry(self.root, self.project_id)

        read_request = team_router.recovery_read_request(ledger, registry, "manager")

        self.assertEqual(read_request["threadId"], "thread-manager")
        self.assertEqual(read_request["searchAnchor"]["messageId"], "msg-plan")

    def test_thread_send_anchor_normalizes_common_tool_shapes(self):
        direct = team_router.thread_send_anchor(
            {"messageId": "msg-direct", "sentAt": "2026-06-22T20:01:00+08:00"},
            fallback_sent_at="fallback",
        )
        nested = team_router.thread_send_anchor(
            {"message": {"id": "msg-nested", "createdAt": "2026-06-22T20:02:00+08:00"}},
            fallback_sent_at="fallback",
        )
        fallback = team_router.thread_send_anchor({}, fallback_sent_at="2026-06-22T20:03:00+08:00")

        self.assertEqual(direct, {"messageId": "msg-direct", "sentAt": "2026-06-22T20:01:00+08:00"})
        self.assertEqual(nested, {"messageId": "msg-nested", "sentAt": "2026-06-22T20:02:00+08:00"})
        self.assertEqual(fallback, {"messageId": None, "sentAt": "2026-06-22T20:03:00+08:00"})

    def test_thread_adapter_capability_probe_reports_missing_tools(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.probe_thread_adapter_capabilities(FakeThreadAdapter())
        self.assertIn("list_projects", str(ctx.exception))
        self.assertIn("list_threads", str(ctx.exception))
        self.assertIn("set_thread_title", str(ctx.exception))
        self.assertNotIn("host adapter wrapper", str(ctx.exception))

        capabilities = team_router.probe_thread_adapter_capabilities(FullThreadAdapter())
        self.assertTrue(capabilities["create_thread"])
        self.assertTrue(capabilities["list_projects"])
        self.assertTrue(capabilities["list_threads"])
        self.assertTrue(capabilities["set_thread_title"])

    def test_parent_entry_guard_blocks_adapter_runner_without_callable_tools(self):
        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.parent_entry_guard(FakeThreadAdapter())

        self.assertIn("adapter-created path unavailable", str(ctx.exception))
        self.assertIn("manual/pre-created continuation", str(ctx.exception))

    def test_parent_entry_guard_allows_manual_precreated_when_adapter_unusable(self):
        entry = team_router.parent_entry_guard(
            FakeThreadAdapter(),
            precreated_roles=self.roles,
        )

        self.assertEqual(entry["path"], "manual-precreated")
        self.assertFalse(entry["adapterUsable"])
        self.assertIn("list_projects", entry["reason"])

    def test_parent_entry_guard_rejects_manual_precreated_without_thread_ids(self):
        invalid_roles = {
            "manager": {"title": "TeamRouter manager"},
            "executor": {"threadId": "thread-executor"},
            "verifier": {"threadId": "thread-verifier"},
        }

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.parent_entry_guard(precreated_roles=invalid_roles)

        self.assertIn("roles.manager.threadId", str(ctx.exception))

    def test_parent_entry_guard_accepts_full_callable_adapter_path(self):
        entry = team_router.parent_entry_guard(FullThreadAdapter())

        self.assertEqual(entry["path"], "adapter-created")
        self.assertTrue(entry["adapterUsable"])
        self.assertTrue(entry["capabilities"]["send_message_to_thread"])

    def test_thread_adapter_capability_probe_rejects_model_tool_descriptors(self):
        descriptor_adapter = {
            tool_name: "codex_app.%s" % tool_name
            for tool_name in team_router.THREAD_TOOL_NAMES
        }

        with self.assertRaises(team_router.StateStoreError) as ctx:
            team_router.probe_thread_adapter_capabilities(descriptor_adapter)

        self.assertIn("in-process Python callables", str(ctx.exception))
        self.assertIn("model-side Codex app tool descriptors need a host adapter wrapper", str(ctx.exception))
        self.assertIn("list_projects", str(ctx.exception))

    def test_normalize_thread_read_messages_accepts_lists_nested_messages_and_turns(self):
        raw_list = team_router.normalize_thread_read_messages([
            {"id": "m1", "createdAt": "2026-06-22T20:01:00+08:00", "content": "hello"},
        ])
        nested = team_router.normalize_thread_read_messages({
            "thread": {"messages": [
                {"message_id": "m2", "timestamp": "2026-06-22T20:02:00+08:00", "summary": "nested"},
            ]},
        })
        turns = team_router.normalize_thread_read_messages({
            "turns": [
                {"id": "turn-1", "createdAt": "2026-06-22T20:03:00+08:00", "summary": "turn summary"},
            ],
        })

        self.assertEqual(raw_list[0]["messageId"], "m1")
        self.assertEqual(raw_list[0]["text"], "hello")
        self.assertEqual(nested[0]["messageId"], "m2")
        self.assertEqual(nested[0]["text"], "nested")
        self.assertEqual(turns[0]["messageId"], "turn-1")
        self.assertEqual(turns[0]["text"], "turn summary")

    def test_normalize_thread_read_messages_unwraps_result_and_content_blocks(self):
        messages = team_router.normalize_thread_read_messages({
            "result": {
                "messages": [
                    {
                        "id": "m1",
                        "createdAt": "2026-06-22T20:03:00+08:00",
                        "content": [
                            {"type": "text", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3"},
                            {"type": "text", "text": "status: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
                        ],
                    },
                ],
            },
        })

        self.assertEqual(messages[0]["messageId"], "m1")
        self.assertIn("TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", messages[0]["text"])
        self.assertIn("summary: ok", messages[0]["text"])

    def test_normalize_thread_read_messages_prefers_content_blocks_over_summary(self):
        messages = team_router.normalize_thread_read_messages({
            "messages": [
                {
                    "id": "m1",
                    "summary": "model summary without protocol marker",
                    "content": [
                        {"type": "text", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3"},
                        {"type": "text", "text": "status: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
                    ],
                },
            ],
        })

        self.assertIn("TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", messages[0]["text"])
        self.assertIn("summary: ok", messages[0]["text"])
        self.assertNotEqual(messages[0]["text"], "model summary without protocol marker")

    def test_normalize_thread_read_messages_flattens_codex_turn_items(self):
        messages = team_router.normalize_thread_read_messages({
            "turns": [
                {
                    "id": "turn-1",
                    "startedAt": "2026-06-22T20:03:00+08:00",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "item-user",
                            "content": [{"type": "text", "text": "request"}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "item-agent",
                            "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none",
                        },
                    ],
                },
            ],
        })

        self.assertEqual([msg["messageId"] for msg in messages], ["item-user", "item-agent"])
        self.assertEqual(messages[0]["sentAt"], "2026-06-22T20:03:00+08:00")
        self.assertIn("TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", messages[1]["text"])
        self.assertIn("summary: ok", messages[1]["text"])

    def test_normalize_thread_read_messages_accepts_live_codex_numeric_turn_timestamps(self):
        messages = team_router.normalize_thread_read_messages({
            "schemaVersion": 1,
            "thread": {"id": "thread-live", "status": {"type": "idle"}},
            "turns": [
                {
                    "id": "turn-live",
                    "startedAt": 1767225600,
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "item-user",
                            "content": [{"type": "text", "text": "TEAM_ROUTER_VERDICT request"}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "item-agent",
                            "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: live smoke\nevidenceChecked: thread tools\nrisks: none",
                        },
                    ],
                },
            ],
        })

        self.assertEqual(messages[0]["sentAt"], 1767225600)
        self.assertEqual(messages[1]["sentAt"], 1767225600)
        anchor = {"messageId": None, "sentAt": "2026-01-01T00:00:00+00:00"}
        self.assertTrue(team_router.read_window_covers_anchor(messages, anchor))
        filtered = team_router._messages_after_anchor(messages, anchor)
        self.assertEqual([msg["messageId"] for msg in filtered], ["item-agent"])

    def test_live_manager_inbox_direct_return_fixture_normalizes_source_thread(self):
        path = ROOT / "tests" / "fixtures" / "team_router" / "live_manager_inbox_direct_return.json"
        raw = json.loads(path.read_text(encoding="utf-8"))

        messages = team_router.normalize_thread_read_messages(raw)
        marker_messages = [
            msg for msg in messages
            if "TEAM_ROUTER_CALLBACK taskId=ctr-live-direct-fixture-1" in msg["text"]
        ]

        self.assertTrue(marker_messages)
        self.assertEqual(marker_messages[-1]["messageId"], "item-direct-callback")
        self.assertEqual(marker_messages[-1]["sentAt"], 1767225660)
        self.assertEqual(marker_messages[-1]["sourceThreadId"], "thread-executor-fixture")
        self.assertEqual(marker_messages[-1]["delegatedText"], marker_messages[-1]["text"])

    def test_live_read_thread_fixture_matches_normalizer_contract(self):
        path = ROOT / "tests" / "fixtures" / "team_router" / "live_read_thread_verdict.json"
        raw = json.loads(path.read_text(encoding="utf-8"))

        messages = team_router.normalize_thread_read_messages(raw)
        marker_messages = [
            msg for msg in messages
            if "TEAM_ROUTER_VERDICT taskId=ctr-live-smoke-fixture-1" in msg["text"]
        ]

        self.assertTrue(marker_messages)
        self.assertEqual(marker_messages[-1]["messageId"], "item-verdict")
        self.assertEqual(marker_messages[-1]["sentAt"], 1767225600)

    def test_adapter_send_wrappers_do_not_send_for_terminal_or_max_rework(self):
        adapter = FakeThreadAdapter()
        blocked = self._awaiting_plan_ledger()
        blocked["status"] = "blocked"
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, blocked)

        with self.assertRaises(team_router.StateStoreError):
            team_router.send_manager_plan_request_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:09:00+08:00",
            )
        self.assertEqual(adapter.sent, [])

        self.tearDown()
        self.setUp()
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger(max_rework=0)
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        needs_rework = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["status"], "blocked")

        with self.assertRaises(team_router.StateStoreError):
            team_router.send_executor_dispatch_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                thread_adapter=adapter,
                permission="read-only",
                sent_at="2026-06-22T20:08:00+08:00",
            )
        self.assertEqual(adapter.sent, [])

    def test_create_role_threads_uses_nested_title_from_create_result(self):
        class NestedTitleAdapter(FakeThreadAdapter):
            def create_thread(self, **kwargs):
                prompt = kwargs["prompt"]
                role = "role"
                for candidate in ("manager", "executor", "verifier", "reviewer"):
                    if candidate in prompt:
                        role = candidate
                        break
                thread_id = "thread-%s" % role
                self.messages[thread_id] = []
                return {"thread": {"id": thread_id, "title": "Nested %s title" % role}}

        roles = team_router.create_role_threads_with_adapter(
            NestedTitleAdapter(),
            project_id=self.project_id,
            objective="inspect docs",
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(roles["manager"]["title"], "Nested manager title")
        self.assertEqual(roles["executor"]["title"], "Nested executor title")
        self.assertEqual(roles["verifier"]["title"], "Nested verifier title")


    def test_reviewer_role_is_first_class_but_not_default_created(self):
        default_adapter = FakeThreadAdapter()
        default_roles = team_router.create_role_threads_with_adapter(
            default_adapter,
            project_id=self.project_id,
            objective="inspect docs",
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )
        self.assertEqual(sorted(default_roles), ["executor", "manager", "verifier"])
        self.assertNotIn("reviewer", default_roles)

        reviewer_adapter = FakeThreadAdapter()
        reviewer_roles = team_router.create_role_threads_with_adapter(
            reviewer_adapter,
            project_id=self.project_id,
            objective="inspect router protocol",
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
            role_names=["reviewer"],
        )
        self.assertEqual(sorted(reviewer_roles), ["reviewer"])
        self.assertEqual(reviewer_roles["reviewer"]["threadId"], "thread-reviewer")
        self.assertTrue(team_router.role_thread_title(self.project_id, "reviewer", "协议审查").startswith("审查者-"))
    def test_role_thread_title_supports_chinese_visible_task_titles_and_legacy_default(self):
        self.assertEqual(
            team_router.role_thread_title(
                self.project_id,
                "manager",
                "Team Router 自动化入口与待办提醒",
            ),
            "规划者-Team Router 自动化入口与待办提醒",
        )
        self.assertEqual(
            team_router.role_thread_title(
                self.project_id,
                "executor",
                "  Team   Router   自动化入口与待办提醒  ",
            ),
            "执行者-Team Router 自动化入口与待办提醒",
        )
        self.assertEqual(
            team_router.role_thread_title(self.project_id, "verifier"),
            "TeamRouter verifier - project-123",
        )

    def test_start_team_task_with_adapter_reuses_existing_registry_roles(self):
        adapter = FakeThreadAdapter()
        existing_roles = {
            role: dict(record, createdAt="2026-06-22T19:00:00+08:00")
            for role, record in self.roles.items()
        }
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            existing_roles,
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.created, [])
        registry = team_router.load_registry(self.root, self.project_id)
        for role in ("manager", "executor", "verifier"):
            self.assertEqual(
                registry["projects"][self.project_id]["roles"][role]["threadId"],
                self.roles[role]["threadId"],
            )

    def test_start_team_task_with_adapter_reuses_registry_without_target_lookup(self):
        adapter = FakeThreadAdapter()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            self.roles,
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.created, [])

    def test_start_team_task_with_adapter_creates_only_missing_registry_roles(self):
        adapter = FakeThreadAdapter()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"manager": self.roles["manager"]},
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        created_prompts = [record["kwargs"]["prompt"] for record in adapter.created]
        self.assertEqual(len(created_prompts), 2)
        self.assertFalse(any("role: manager" in prompt for prompt in created_prompts))
        self.assertTrue(any("role: executor" in prompt for prompt in created_prompts))
        self.assertTrue(any("role: verifier" in prompt for prompt in created_prompts))
        registry = team_router.load_registry(self.root, self.project_id)
        project_roles = registry["projects"][self.project_id]["roles"]
        self.assertEqual(project_roles["manager"]["threadId"], "thread-manager")
        self.assertEqual(project_roles["executor"]["threadId"], "thread-executor")
        self.assertEqual(project_roles["verifier"]["threadId"], "thread-verifier")

    def test_start_team_task_with_adapter_discovers_existing_role_threads(self):
        class DiscoveryAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed = 0
                self.renamed = []
                self.thread_list = [
                    {
                        "threadId": "live-manager",
                        "title": "Old manager title",
                        "role": "manager",
                        "projectId": "project-123",
                    },
                    {
                        "threadId": "live-executor",
                        "title": "TeamRouter executor - project-123",
                    },
                ]

            def list_threads(self, **kwargs):
                self.listed += 1
                return {"threads": list(self.thread_list)}

            def set_thread_title(self, **kwargs):
                self.renamed.append(dict(kwargs))
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        adapter = DiscoveryAdapter()

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.listed, 1)
        self.assertEqual(len(adapter.created), 1)
        self.assertIn("role: verifier", adapter.created[0]["kwargs"]["prompt"])
        registry = team_router.load_registry(self.root, self.project_id)
        project_roles = registry["projects"][self.project_id]["roles"]
        self.assertEqual(project_roles["manager"]["threadId"], "live-manager")
        self.assertEqual(project_roles["executor"]["threadId"], "live-executor")
        self.assertEqual(project_roles["verifier"]["threadId"], "thread-verifier")
        self.assertIn(
            {"threadId": "live-manager", "title": "规划者-inspect docs"},
            adapter.renamed,
        )
        self.assertIn(
            {"threadId": "live-executor", "title": "执行者-inspect docs"},
            adapter.renamed,
        )
        self.assertIn(
            {"threadId": "thread-verifier", "title": "验证者-inspect docs"},
            adapter.renamed,
        )

    def test_start_team_task_with_adapter_ignores_ambiguous_bound_registry_roles(self):
        class DuplicateManagerAdapter(FakeThreadAdapter):
            def list_threads(self, **kwargs):
                return {
                    "threads": [
                        {"threadId": "manager-a", "title": "TeamRouter manager - project-123"},
                        {"threadId": "manager-b", "title": "TeamRouter manager - project-123"},
                    ],
                }

        adapter = DuplicateManagerAdapter()
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"manager": self.roles["manager"]},
            "2026-06-22T19:00:00+08:00",
        )

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(len(adapter.created), 2)
        registry = team_router.load_registry(self.root, self.project_id)
        self.assertEqual(
            registry["projects"][self.project_id]["roles"]["manager"]["threadId"],
            "thread-manager",
        )

    def test_start_team_task_with_adapter_does_not_bind_bare_role_from_other_project(self):
        class ForeignRoleAdapter(FakeThreadAdapter):
            def list_threads(self, **kwargs):
                return {
                    "threads": [
                        {
                            "threadId": "foreign-manager",
                            "title": "Other project manager",
                            "role": "manager",
                        },
                    ],
                }

        adapter = ForeignRoleAdapter()

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        registry = team_router.load_registry(self.root, self.project_id)
        self.assertEqual(
            registry["projects"][self.project_id]["roles"]["manager"]["threadId"],
            "thread-manager",
        )

    def test_start_team_task_with_adapter_blocks_ambiguous_discovered_role_threads(self):
        class AmbiguousAdapter(FakeThreadAdapter):
            def list_threads(self, **kwargs):
                return {
                    "threads": [
                        {"threadId": "manager-a", "title": "TeamRouter manager - project-123"},
                        {"threadId": "manager-b", "title": "TeamRouter manager - project-123"},
                    ],
                }

        with self.assertRaises(team_router.StateStoreError):
            team_router.start_team_task_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                objective="inspect docs",
                project_local_path="D:\\codex\\codex-dynamic-workflow",
                thread_adapter=AmbiguousAdapter(),
                target={"type": "projectless"},
                observed_at="2026-06-22T20:00:00+08:00",
            )

    def test_start_team_task_with_adapter_resolves_target_from_list_projects(self):
        class ProjectListAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed_projects = 0

            def list_projects(self, **kwargs):
                self.listed_projects += 1
                return {
                    "projects": [
                        {
                            "projectId": "project-123",
                            "target": {
                                "type": "worktree",
                                "path": "D:\\codex\\codex-dynamic-workflow",
                            },
                        },
                    ],
                }

        adapter = ProjectListAdapter()

        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(ledger["status"], "roles_ready")
        self.assertEqual(adapter.listed_projects, 1)
        for record in adapter.created:
            self.assertEqual(
                record["kwargs"]["target"],
                {"type": "worktree", "path": "D:\\codex\\codex-dynamic-workflow"},
            )

    def test_orchestrate_team_task_with_adapter_discovers_reuses_and_advances(self):
        class ParentAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed_projects = 0
                self.listed_threads = 0
                self.renamed = []
                self.thread_list = [
                    {
                        "threadId": "live-manager",
                        "title": "Old manager title",
                        "role": "manager",
                        "projectId": "project-123",
                    },
                    {
                        "threadId": "live-executor",
                        "title": "TeamRouter executor - project-123",
                    },
                    {
                        "threadId": "live-verifier",
                        "title": "TeamRouter verifier - project-123",
                    },
                ]

            def list_projects(self, **kwargs):
                self.listed_projects += 1
                return {
                    "projects": [
                        {
                            "projectId": "project-123",
                            "target": {
                                "type": "project",
                                "projectId": "project-123",
                                "environment": {"type": "local"},
                            },
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                self.listed_threads += 1
                return {"threads": list(self.thread_list)}

            def set_thread_title(self, **kwargs):
                self.renamed.append(dict(kwargs))
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        adapter = ParentAdapter()

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
        )

        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(update["ledger"]["status"], "awaiting_plan")
        self.assertEqual(adapter.listed_projects, 1)
        self.assertEqual(adapter.listed_threads, 1)
        self.assertEqual(adapter.created, [])
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "live-manager")
        self.assertEqual(
            adapter.renamed,
            [
                {"threadId": "live-executor", "title": "执行者-inspect docs"},
                {"threadId": "live-manager", "title": "规划者-inspect docs"},
                {"threadId": "live-verifier", "title": "验证者-inspect docs"},
            ],
        )
        self.assertEqual(update["projectTarget"]["environment"], {"type": "local"})
        registry = team_router.load_registry(self.root, self.project_id)
        project_roles = registry["projects"][self.project_id]["roles"]
        self.assertEqual(project_roles["manager"]["threadId"], "live-manager")
        self.assertEqual(project_roles["executor"]["threadId"], "live-executor")
        self.assertEqual(project_roles["verifier"]["threadId"], "live-verifier")

    def test_orchestrate_team_task_with_adapter_can_resolve_path_codex_project_id(self):
        class PathProjectAdapter(FakeThreadAdapter):
            def __init__(self):
                super().__init__()
                self.listed_projects = 0
                self.listed_threads = 0

            def list_projects(self, **kwargs):
                self.listed_projects += 1
                return {
                    "projects": [
                        {
                            "projectId": "D:\\codex\\codex-dynamic-workflow",
                            "target": {
                                "type": "project",
                                "projectId": "D:\\codex\\codex-dynamic-workflow",
                                "environment": {"type": "local"},
                            },
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                self.listed_threads += 1
                return {
                    "threads": [
                        {"threadId": "live-manager", "title": "TeamRouter manager - project-123"},
                        {"threadId": "live-executor", "title": "TeamRouter executor - project-123"},
                        {"threadId": "live-verifier", "title": "TeamRouter verifier - project-123"},
                    ],
                }

            def set_thread_title(self, **kwargs):
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        adapter = PathProjectAdapter()

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            codex_project_id="D:\\codex\\codex-dynamic-workflow",
        )

        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(update["ledger"]["projectId"], "project-123")
        self.assertEqual(update["codexProjectId"], "D:\\codex\\codex-dynamic-workflow")
        self.assertEqual(update["projectTarget"]["projectId"], "D:\\codex\\codex-dynamic-workflow")
        self.assertEqual(adapter.listed_projects, 1)
        self.assertEqual(adapter.listed_threads, 1)
        self.assertEqual(adapter.created, [])

    def test_orchestrate_team_task_with_adapter_accepts_codex_desktop_project_shape(self):
        class CodexDesktopProjectAdapter(FakeThreadAdapter):
            def list_projects(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "projects": [
                        {
                            "projectId": "D:\\codex\\codex-dynamic-workflow",
                            "projectKind": "local",
                            "label": "codex-dynamic-workflow",
                            "path": "D:\\codex\\codex-dynamic-workflow",
                            "hostId": "local",
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "threads": [
                        {"id": "live-manager", "title": "TeamRouter manager - project-123"},
                        {"id": "live-executor", "title": "TeamRouter executor - project-123"},
                        {"id": "live-verifier", "title": "TeamRouter verifier - project-123"},
                    ],
                }

            def set_thread_title(self, **kwargs):
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

        update = team_router.orchestrate_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=CodexDesktopProjectAdapter(),
            permission="read-only",
            observed_at="2026-06-22T20:00:00+08:00",
            codex_project_id="D:\\codex\\codex-dynamic-workflow",
        )

        self.assertEqual(update["action"], "sent_manager_plan_request")
        self.assertEqual(update["projectTarget"], {
            "type": "project",
            "projectId": "D:\\codex\\codex-dynamic-workflow",
            "environment": {"type": "local"},
        })

    def test_orchestrate_team_task_with_adapter_reaches_closeout_with_codex_desktop_shapes(self):
        class CodexDesktopE2EAdapter(FakeThreadAdapter):
            def __init__(self, task_id):
                super().__init__()
                self.task_id = task_id
                self.created = []
                self.reads = []
                self.renamed = []
                self.messages = {
                    "thread-manager": [],
                    "thread-executor": [],
                    "thread-verifier": [],
                }
                self.reply_specs = {
                    "thread-manager": (
                        "msg-live-plan",
                        "2026-06-23T11:40:30+08:00",
                        "assistant",
                        "TEAM_ROUTER_PLAN taskId=%s\n"
                        "status: planned\n"
                        "acknowledgedPermission: read-only\n"
                        "scope: src/team_router.py tests/test_team_router.py\n"
                        "stopWhen: closeout\n"
                        "riskBoundary: read only\n"
                        "executorPrompt: inspect adapter orchestration\n"
                        "notes: desktop e2e" % task_id,
                    ),
                    "thread-executor": (
                        "msg-live-callback",
                        "2026-06-23T11:41:30+08:00",
                        "assistant",
                        "TEAM_ROUTER_CALLBACK taskId=%s\n"
                        "status: done\n"
                        "final: true\n"
                        "summary: first line\n"
                        "second line\n"
                        "evidence: codex desktop shape\n"
                        "risks: none\n"
                        "next: verifier" % task_id,
                    ),
                    "thread-verifier": (
                        "msg-live-verdict",
                        "2026-06-23T11:42:30+08:00",
                        "assistant",
                        "TEAM_ROUTER_VERDICT taskId=%s\n"
                        "result: pass\n"
                        "summary: verified closeout\n"
                        "requiredChanges: none\n"
                        "evidenceChecked: codex desktop shape\n"
                        "risks: none" % task_id,
                    ),
                }

            def create_thread(self, **kwargs):
                raise AssertionError("pre-created role threads should be reused")

            def list_projects(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "projects": [
                        {
                            "projectId": "D:\\codex\\codex-dynamic-workflow",
                            "projectKind": "local",
                            "label": "codex-dynamic-workflow",
                            "path": "D:\\codex\\codex-dynamic-workflow",
                            "hostId": "local",
                        },
                    ],
                }

            def list_threads(self, **kwargs):
                return {
                    "schemaVersion": 1,
                    "threads": [
                        {"id": "thread-manager", "title": "规划者-inspect docs"},
                        {"id": "thread-executor", "title": "执行者-inspect docs"},
                        {"id": "thread-verifier", "title": "验证者-inspect docs"},
                    ],
                }

            def set_thread_title(self, **kwargs):
                self.renamed.append(dict(kwargs))
                return {"threadId": kwargs["threadId"], "title": kwargs["title"]}

            def send_message_to_thread(self, **kwargs):
                thread_id = kwargs["threadId"]
                self.sent.append({"kwargs": kwargs, "result": {"threadId": thread_id}})
                self.messages[thread_id].append({
                    "id": "user-%02d" % len(self.sent),
                    "sentAt": {
                        "thread-manager": "2026-06-23T11:40:00+08:00",
                        "thread-executor": "2026-06-23T11:41:00+08:00",
                        "thread-verifier": "2026-06-23T11:42:00+08:00",
                    }[thread_id],
                    "role": "user",
                    "content": [{"type": "text", "text": kwargs["prompt"]}],
                })
                reply_id, sent_at, role, text = self.reply_specs[thread_id]
                self.messages[thread_id].append({
                    "id": reply_id,
                    "sentAt": sent_at,
                    "role": role,
                    "content": [{"type": "text", "text": text}],
                })
                return {"threadId": thread_id}

            def read_thread(self, **kwargs):
                thread_id = kwargs["threadId"]
                self.reads.append(dict(kwargs))
                return {
                    "schemaVersion": 1,
                    "page": {"order": "newest_first"},
                    "thread": {"id": thread_id},
                    "turns": [
                        {
                            "id": "turn-%s" % thread_id,
                            "startedAt": "2026-06-23T11:40:00+08:00",
                            "items": list(reversed(self.messages[thread_id])),
                        },
                    ],
                }

        adapter = CodexDesktopE2EAdapter(self.task_id)
        observed_at = [
            "2026-06-23T11:40:00+08:00",
            "2026-06-23T11:41:00+08:00",
            "2026-06-23T11:42:00+08:00",
            "2026-06-23T11:43:00+08:00",
        ]

        updates = [
            team_router.orchestrate_team_task_with_adapter(
                self.root,
                self.project_id,
                self.task_id,
                objective="inspect docs",
                project_local_path="D:\\codex\\codex-dynamic-workflow",
                thread_adapter=adapter,
                permission="read-only",
                observed_at=timestamp,
                codex_project_id="D:\\codex\\codex-dynamic-workflow",
            )
            for timestamp in observed_at
        ]

        self.assertEqual(
            [(update["action"], update["status"]) for update in updates],
            [
                ("sent_manager_plan_request", "awaiting_plan"),
                ("sent_executor_dispatch", "awaiting_callback"),
                ("sent_verifier_request", "verifying"),
                ("read_verifier_verdict", "done"),
            ],
        )
        self.assertEqual(adapter.created, [])
        self.assertEqual([record["kwargs"]["threadId"] for record in adapter.sent], [
            "thread-manager",
            "thread-executor",
            "thread-verifier",
        ])
        self.assertEqual([record["threadId"] for record in adapter.reads], [
            "thread-manager",
            "thread-executor",
            "thread-verifier",
        ])
        self.assertEqual(adapter.renamed, [])
        self.assertTrue(updates[-1]["userOutput"].startswith("Team Router Closeout"))
        self.assertEqual(
            updates[-1]["ledger"]["observations"][-2]["parsedFields"]["summary"],
            "first line\nsecond line",
        )
        self.assertEqual(updates[-1]["codexProjectId"], "D:\\codex\\codex-dynamic-workflow")

    def test_verifier_request_uses_recent_executor_callback_observation(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        ledger["observations"].append(team_router.make_observation(
            "system_event",
            "system",
            "thread-system",
            "2026-06-22T20:04:30+08:00",
            "manual note after executor callback",
            {"status": "not-callback"},
        ))
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, ledger)

        updated = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        self.assertEqual(updated["status"], "verifying")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-verifier")
        self.assertIn("TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3", adapter.sent[-1]["kwargs"]["prompt"])

    def test_fake_thread_adapter_runs_manager_executor_verifier_smoke(self):
        adapter = FakeThreadAdapter()
        ledger = team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )
        self.assertEqual(ledger["status"], "roles_ready")

        awaiting_plan = team_router.send_manager_plan_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = awaiting_plan["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        planned = team_router.read_manager_plan_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:01:40+08:00",
        )
        self.assertEqual(planned["status"], "planned")

        awaiting_callback = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        executor_thread = awaiting_callback["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: ok\nevidence: fake adapter\nrisks: none\nnext: none" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        verifying = team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(verifying["status"], "verifying")

        verifying = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        verifier_thread = verifying["verification"]["request"]["threadId"]
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict",
            sent_at="2026-06-22T20:06:00+08:00",
        )
        done = team_router.read_verifier_verdict_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(done["status"], "done")
        self.assertEqual(done["closeout"]["summary"], "ok")
        self.assertEqual(len(adapter.created), 3)
        self.assertEqual(len(adapter.sent), 3)

    def test_run_team_task_with_adapter_orchestrates_until_external_waits(self):
        adapter = FakeThreadAdapter()

        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        self.assertEqual(first["action"], "sent_manager_plan_request")
        self.assertEqual(first["ledger"]["status"], "awaiting_plan")
        self.assertTrue(first["userOutput"].startswith("Team Router Handoff"))
        self.assertEqual(len(adapter.created), 3)
        self.assertEqual(len(adapter.sent), 1)

        manager_thread = first["ledger"]["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        second = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        self.assertEqual(second["action"], "sent_executor_dispatch")
        self.assertEqual(second["ledger"]["status"], "awaiting_callback")
        self.assertEqual(len(adapter.sent), 2)

        executor_thread = second["ledger"]["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: line one\nline two\nevidence: fake adapter\nrisks: none\nnext: verifier" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        third = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(third["action"], "sent_verifier_request")
        self.assertEqual(third["ledger"]["status"], "verifying")
        self.assertEqual(
            third["ledger"]["observations"][-1]["parsedFields"]["summary"],
            "line one\nline two",
        )
        self.assertEqual(len(adapter.sent), 3)

        verifier_thread = third["ledger"]["verification"]["request"]["threadId"]
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        fourth = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:06:00+08:00",
        )
        self.assertEqual(fourth["action"], "read_verifier_verdict")
        self.assertEqual(fourth["ledger"]["status"], "done")
        self.assertTrue(fourth["userOutput"].startswith("Team Router Closeout"))

    def test_run_team_task_with_adapter_routes_high_risk_callback_through_reviewer_pass(self):
        adapter = FakeThreadAdapter()
        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = first["ledger"]["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: Team Router reviewer runtime gate\nstopWhen: done\nriskBoundary: runtime gate and reviewer gate change\nexecutorPrompt: inspect Team Router self changes\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        second = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:02:30+08:00",
        )
        executor_thread = second["ledger"]["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: runtime gate fixed\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )

        third = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(third["action"], "sent_reviewer_request")
        self.assertEqual(third["ledger"]["status"], "reviewing")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-reviewer")
        self.assertIn("TEAM_ROUTER_REVIEW_REQUEST taskId=%s" % self.task_id, adapter.sent[-1]["kwargs"]["prompt"])

        adapter.append_reply(
            "thread-reviewer",
            "TEAM_ROUTER_REVIEW taskId=%s\nresult: pass\nsummary: reviewer passed\nfindings: none\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none" % self.task_id,
            message_id="msg-review-pass",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        fourth = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:06:00+08:00",
        )

        self.assertEqual(fourth["action"], "sent_verifier_request")
        self.assertEqual(fourth["ledger"]["status"], "verifying")
        self.assertEqual(fourth["ledger"]["review"]["result"]["fields"]["result"], "pass")
        self.assertEqual(adapter.sent[-1]["kwargs"]["threadId"], "thread-verifier")

    def test_run_team_task_with_adapter_stops_for_reviewer_needs_rework(self):
        adapter = FakeThreadAdapter()
        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        adapter.append_reply(
            first["ledger"]["planRequest"]["threadId"],
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: Team Router reviewer gate\nstopWhen: done\nriskBoundary: runtime gate change\nexecutorPrompt: inspect Team Router self changes\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        second = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        team_router.update_registry_roles(
            self.root,
            self.project_id,
            {"reviewer": {"threadId": "thread-reviewer", "title": "审查者-runtime-gate"}},
            "2026-06-22T20:02:30+08:00",
        )
        adapter.append_reply(
            second["ledger"]["dispatches"][-1]["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: runtime gate fixed\nevidence: tests\nrisks: none\nnext: reviewer" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        third = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(third["action"], "sent_reviewer_request")
        adapter.append_reply(
            "thread-reviewer",
            "TEAM_ROUTER_REVIEW taskId=%s\nresult: needs_rework\nsummary: gap remains\nfindings: trigger missing\nrequiredChanges: expand reviewer gate trigger tests\nevidenceChecked: tests\nrisks: none" % self.task_id,
            message_id="msg-review-rework",
            sent_at="2026-06-22T20:05:00+08:00",
        )

        fourth = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="Team Router reviewer runtime gate rework",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:06:00+08:00",
        )

        self.assertEqual(fourth["action"], "needs_rework_pending")
        self.assertEqual(fourth["ledger"]["status"], "needs_rework")
        self.assertEqual(fourth["ledger"]["review"]["result"]["fields"]["result"], "needs_rework")
    def test_watch_team_task_reads_executor_callback_and_sends_verifier(self):
        adapter = FakeThreadAdapter()
        awaiting = self._awaiting_callback_ledger()
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: callback ready\n"
                    "evidence: fake adapter\n"
                    "risks: none\n"
                    "next: verifier" % awaiting["taskId"]
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["type"], "callback_raw")
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "thread-verifier")
        self.assertIn("TEAM_ROUTER_VERIFY taskId=%s" % self.task_id, adapter.sent[0]["kwargs"]["prompt"])
        self.assertEqual(update["nextWakeup"]["role"], "verifier")
        self.assertEqual(update["nextWakeup"]["reason"], "awaiting TEAM_ROUTER_VERDICT")
        self.assertIn("host watcher", update["automationBoundary"])

    def test_watch_team_task_prefers_manager_inbox_direct_return_callback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: direct return callback\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_sent_verifier_request")
        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["ledger"]["observations"][-1]["parsedFields"]["summary"], "direct return callback")
        self.assertEqual(len(adapter.sent), 1)
        self.assertEqual(adapter.sent[0]["kwargs"]["threadId"], "thread-verifier")

    def test_watch_team_task_ignores_manager_inbox_callback_with_wrong_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>wrong-executor-thread</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: wrong source\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_executor_callback")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertEqual(update["ledger"]["observations"], [])
        self.assertEqual(adapter.sent, [])

    def test_watch_team_task_ignores_manager_inbox_callback_with_wrong_task_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=ctr-wrong-task\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: wrong task\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>"
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_executor_callback")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertEqual(update["ledger"]["observations"], [])
        self.assertEqual(adapter.sent, [])

    def test_executor_role_fallback_read_uses_fallback_search_anchor(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        awaiting = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        awaiting["dispatches"][-1]["searchAnchor"] = {"messageId": "manager-direct-callback"}
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, awaiting)
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: fallback callback\nevidence: executor self-thread\nrisks: none\nnext: verifier" % self.task_id,
            },
        ]

        update = team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(update["status"], "verifying")
        self.assertEqual(update["observations"][-1]["parsedFields"]["summary"], "fallback callback")

    def test_watch_team_task_reads_verifier_pass_and_returns_closeout(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {
                "messageId": "msg-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: watcher closeout\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: fake adapter\n"
                    "risks: none" % requested["taskId"]
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "done")
        self.assertIsNone(update["nextWakeup"])
        self.assertIn("Team Router Closeout", update["userOutput"])
        self.assertIn("summary: watcher closeout", update["userOutput"])
        self.assertIn("remainingTodos: none", update["userOutput"])
        self.assertEqual(len(adapter.sent), 0)

    def test_verifier_role_fallback_read_uses_fallback_search_anchor(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        requested = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        requested["verification"]["request"]["searchAnchor"] = {"messageId": "manager-direct-verdict"}
        team_router.save_task_ledger(self.root, self.project_id, self.task_id, requested)
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {
                "messageId": "msg-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: fallback closeout\nrequiredChanges: none\nevidenceChecked: verifier self-thread\nrisks: none" % self.task_id,
            },
        ]

        update = team_router.read_verifier_verdict_update_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["ledger"]["status"], "done")
        self.assertIn("summary: fallback closeout", update["userOutput"])

    def test_watch_team_task_prefers_manager_inbox_direct_return_verdict(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-verifier</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: direct return closeout\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "done")
        self.assertIn("summary: direct return closeout", update["userOutput"])
        self.assertIn("remainingTodos: none", update["userOutput"])
        self.assertEqual(len(adapter.sent), 0)

    def test_watch_team_task_ignores_manager_inbox_verdict_with_wrong_source_thread_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>wrong-verifier-thread</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=%s\n"
                    "result: pass\n"
                    "summary: wrong source\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertIsNone(update["ledger"]["closeout"])
        self.assertEqual(len(adapter.sent), 0)

    def test_watch_team_task_ignores_manager_inbox_verdict_with_wrong_task_id(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-verdict",
                "sentAt": "2026-06-22T20:06:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-verifier</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_VERDICT taskId=ctr-wrong-task\n"
                    "result: pass\n"
                    "summary: wrong task\n"
                    "requiredChanges: none\n"
                    "evidenceChecked: manager inbox\n"
                    "risks: none</input>\n"
                    "</codex_delegation>"
                ),
            },
        ]

        update = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["action"], "watch_read_verifier_verdict")
        self.assertEqual(update["status"], "callback_unreachable")
        self.assertIsNone(update["ledger"]["closeout"])
        self.assertEqual(len(adapter.sent), 0)

    def test_fallback_self_thread_does_not_redispatch_after_direct_return_callback(self):
        adapter = FakeThreadAdapter()
        ledger = self._planned_ledger()
        team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            executor_thread_id="thread-executor",
            sent_at="2026-06-22T20:02:00+08:00",
            message_id="msg-dispatch",
            return_thread_id="parent-manager-thread",
        )
        adapter.messages["parent-manager-thread"] = [
            {
                "messageId": "msg-manager-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": (
                    "<codex_delegation>\n"
                    "  <source_thread_id>thread-executor</source_thread_id>\n"
                    "  <input>TEAM_ROUTER_CALLBACK taskId=%s\n"
                    "status: done\n"
                    "final: true\n"
                    "summary: direct return callback\n"
                    "evidence: manager inbox\n"
                    "risks: none\n"
                    "next: verifier</input>\n"
                    "</codex_delegation>" % self.task_id
                ),
            },
        ]

        first = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(first["action"], "watch_sent_verifier_request")
        self.assertEqual(len(first["ledger"]["observations"]), 1)
        self.assertEqual(len(adapter.sent), 1)

        adapter.messages["parent-manager-thread"] = []
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:04:00+08:00", "text": "verify"},
        ]
        adapter.messages["thread-executor"] = [
            {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
            {
                "messageId": "msg-callback",
                "sentAt": "2026-06-22T20:03:00+08:00",
                "text": "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: direct return callback\nevidence: manager inbox\nrisks: none\nnext: verifier" % self.task_id,
            },
        ]

        second = team_router.watch_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            observed_at="2026-06-22T20:05:00+08:00",
        )

        self.assertEqual(second["action"], "watch_read_verifier_verdict")
        self.assertEqual(len(second["ledger"]["observations"]), 1)
        self.assertEqual(len(adapter.sent), 1)

    def test_run_team_task_with_adapter_waits_for_rework_confirmation(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        adapter = FakeThreadAdapter()

        update = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:08:00+08:00",
        )

        self.assertEqual(update["action"], "needs_rework_pending")
        self.assertEqual(update["ledger"]["status"], "needs_rework")
        self.assertEqual(adapter.sent, [])

    def test_run_team_task_with_adapter_dispatches_rework_when_confirmed(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: needs_rework\nsummary: missing\nrequiredChanges: fix docs\nevidenceChecked: callback\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        adapter = FakeThreadAdapter()

        update = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:08:00+08:00",
            confirm_rework=True,
        )

        self.assertEqual(update["action"], "sent_executor_dispatch")
        self.assertEqual(update["ledger"]["status"], "awaiting_callback")
        self.assertEqual(update["ledger"]["reworkCount"], 1)
        self.assertEqual(len(adapter.sent), 1)

    def test_run_team_task_with_adapter_retries_plan_unreachable_reads(self):
        adapter = FakeThreadAdapter()
        first = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = first["ledger"]["planRequest"]["threadId"]
        original_messages = list(adapter.messages[manager_thread])
        adapter.messages[manager_thread] = [{"text": "summary-only window"}]

        unreachable = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:02:00+08:00",
        )
        self.assertEqual(unreachable["ledger"]["status"], "plan_unreachable")

        adapter.messages[manager_thread] = original_messages
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        retried = team_router.run_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            permission="read-only",
            observed_at="2026-06-22T20:04:00+08:00",
        )

        self.assertEqual(retried["action"], "sent_executor_dispatch")
        self.assertEqual(retried["ledger"]["status"], "awaiting_callback")

    def test_manual_precreated_flow_uses_direct_send_read_and_capture_helpers(self):
        adapter = FakeThreadAdapter()
        ledger = self._ready_ledger()

        manager_prompt = team_router.make_plan_request_message(
            ledger["taskId"],
            ledger["objective"],
            "read-only",
        )
        manager_send = adapter.send_message_to_thread(
            threadId="thread-manager",
            prompt=manager_prompt,
        )
        manager_anchor = team_router.thread_send_anchor(
            manager_send,
            fallback_sent_at="2026-06-22T20:01:00+08:00",
        )
        awaiting_plan = team_router.record_plan_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            manager_thread_id="thread-manager",
            sent_at=manager_anchor["sentAt"],
            message_id=manager_anchor["messageId"],
        )
        adapter.append_reply(
            awaiting_plan["planRequest"]["threadId"],
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        planned = team_router.capture_manager_plan_from_read(
            self.root,
            self.project_id,
            self.task_id,
            team_router.normalize_thread_read_messages(
                adapter.read_thread(threadId="thread-manager")
            ),
            captured_at="2026-06-22T20:01:40+08:00",
        )
        self.assertEqual(planned["status"], "planned")

        executor_prompt = team_router.make_executor_dispatch_message(
            self.task_id,
            planned["plan"]["fields"],
            "read-only",
            {"messageId": None, "sentAt": "2026-06-22T20:02:00+08:00"},
        )
        executor_send = adapter.send_message_to_thread(
            threadId="thread-executor",
            prompt=executor_prompt,
        )
        executor_anchor = team_router.thread_send_anchor(
            executor_send,
            fallback_sent_at="2026-06-22T20:02:00+08:00",
        )
        awaiting_callback = team_router.record_executor_dispatch_sent(
            self.root,
            self.project_id,
            self.task_id,
            executor_thread_id="thread-executor",
            sent_at=executor_anchor["sentAt"],
            message_id=executor_anchor["messageId"],
        )
        adapter.append_reply(
            awaiting_callback["dispatches"][-1]["threadId"],
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: first line\nsecond line\nevidence: direct tools\nrisks: none\nnext: verifier" % self.task_id,
            message_id="msg-callback",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        verifying = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            self.task_id,
            team_router.normalize_thread_read_messages(
                adapter.read_thread(threadId="thread-executor")
            ),
            captured_at="2026-06-22T20:04:00+08:00",
        )
        self.assertEqual(
            verifying["observations"][-1]["parsedFields"]["summary"],
            "first line\nsecond line",
        )

        verifier_prompt = team_router.make_verifier_request_message(
            self.task_id,
            verifying["observations"][-1]["content"],
            "read-only",
            verifying["plan"]["fields"]["scope"],
        )
        verifier_send = adapter.send_message_to_thread(
            threadId="thread-verifier",
            prompt=verifier_prompt,
        )
        verifier_anchor = team_router.thread_send_anchor(
            verifier_send,
            fallback_sent_at="2026-06-22T20:05:00+08:00",
        )
        verifying = team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            self.task_id,
            verifier_thread_id="thread-verifier",
            sent_at=verifier_anchor["sentAt"],
            message_id=verifier_anchor["messageId"],
        )
        adapter.append_reply(
            verifying["verification"]["request"]["threadId"],
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: direct tools\nrisks: none" % self.task_id,
            message_id="msg-verdict",
            sent_at="2026-06-22T20:06:00+08:00",
        )
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            self.task_id,
            team_router.normalize_thread_read_messages(
                adapter.read_thread(threadId="thread-verifier")
            ),
            captured_at="2026-06-22T20:07:00+08:00",
        )
        registry = team_router.load_registry(self.root, self.project_id)

        self.assertEqual(done["status"], "done")
        self.assertEqual(len(adapter.sent), 3)
        self.assertIn("Team Router Closeout", team_router.format_task_update_for_user(done, registry))

    def test_fake_thread_adapter_runs_rework_cycle_smoke(self):
        adapter = FakeThreadAdapter()
        team_router.start_team_task_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            objective="inspect docs",
            project_local_path="D:\\codex\\codex-dynamic-workflow",
            thread_adapter=adapter,
            target={"type": "projectless"},
            observed_at="2026-06-22T20:00:00+08:00",
        )
        awaiting_plan = team_router.send_manager_plan_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:01:00+08:00",
        )
        manager_thread = awaiting_plan["planRequest"]["threadId"]
        adapter.append_reply(
            manager_thread,
            "TEAM_ROUTER_PLAN taskId=%s\nstatus: planned\nacknowledgedPermission: read-only\nscope: src\nstopWhen: done\nriskBoundary: read only\nexecutorPrompt: inspect src\nnotes: none" % self.task_id,
            message_id="msg-plan-result",
            sent_at="2026-06-22T20:01:30+08:00",
        )
        team_router.read_manager_plan_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:01:40+08:00",
        )

        first_dispatch = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:02:00+08:00",
        )
        executor_thread = first_dispatch["dispatches"][-1]["threadId"]
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: first attempt\nevidence: fake adapter\nrisks: none\nnext: verifier" % self.task_id,
            message_id="msg-callback-1",
            sent_at="2026-06-22T20:03:00+08:00",
        )
        team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:04:00+08:00",
        )
        first_verify = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:05:00+08:00",
        )
        verifier_thread = first_verify["verification"]["request"]["threadId"]
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: needs_rework\nsummary: missing evidence\nrequiredChanges: add evidence\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict-1",
            sent_at="2026-06-22T20:06:00+08:00",
        )
        needs_rework = team_router.read_verifier_verdict_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )
        self.assertEqual(needs_rework["status"], "needs_rework")

        second_dispatch = team_router.send_executor_dispatch_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:08:00+08:00",
        )
        self.assertEqual(second_dispatch["reworkCount"], 1)
        self.assertIsNone(second_dispatch["closeout"])
        adapter.append_reply(
            executor_thread,
            "TEAM_ROUTER_CALLBACK taskId=%s\nstatus: done\nfinal: true\nsummary: second attempt\nevidence: added evidence\nrisks: none\nnext: none" % self.task_id,
            message_id="msg-callback-2",
            sent_at="2026-06-22T20:09:00+08:00",
        )
        team_router.read_executor_callback_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:10:00+08:00",
        )
        second_verify = team_router.send_verifier_request_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            permission="read-only",
            sent_at="2026-06-22T20:11:00+08:00",
        )
        self.assertEqual(second_verify["verification"]["request"]["threadId"], verifier_thread)
        adapter.append_reply(
            verifier_thread,
            "TEAM_ROUTER_VERDICT taskId=%s\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none" % self.task_id,
            message_id="msg-verdict-2",
            sent_at="2026-06-22T20:12:00+08:00",
        )
        done = team_router.read_verifier_verdict_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:13:00+08:00",
        )

        self.assertEqual(done["status"], "done")
        self.assertEqual(done["reworkCount"], 1)
        self.assertEqual(len(done["dispatches"]), 2)
        self.assertEqual(len(adapter.sent), 5)

    def test_closeout_and_handoff_user_formats_include_threads_and_anchors(self):
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            ledger["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: ok\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )
        registry = team_router.load_registry(self.root, self.project_id)

        closeout = team_router.format_closeout_for_user(done, registry)
        handoff = team_router.format_handoff_for_user(done, registry)

        self.assertIn("taskId: ctr-20260622-160000-a7f3", closeout)
        self.assertIn("status: done", closeout)
        self.assertIn("manager: thread-manager", closeout)
        self.assertIn("summary: ok", closeout)
        self.assertIn("remainingTodos: none", closeout)
        self.assertIn("read_thread anchors", handoff)
        self.assertIn("msg-verify", handoff)
        self.assertIn("verification", handoff)
        self.assertIn("remainingTodos: none", handoff)

    def test_format_task_update_for_user_uses_closeout_only_for_terminal_closeout(self):
        awaiting = self._awaiting_callback_ledger()
        registry = team_router.load_registry(self.root, self.project_id)

        handoff = team_router.format_task_update_for_user(awaiting, registry)

        self.assertIn("Team Router Handoff", handoff)
        self.assertIn("read_thread anchors", handoff)
        self.assertIn("executor.dispatch[1]", handoff)

        done = team_router.capture_executor_callback_from_read(
            self.root,
            self.project_id,
            awaiting["taskId"],
            [
                {"messageId": "msg-dispatch", "sentAt": "2026-06-22T20:02:00+08:00", "text": "dispatch"},
                {"messageId": "msg-callback", "sentAt": "2026-06-22T20:03:00+08:00", "text": "TEAM_ROUTER_CALLBACK taskId=ctr-20260622-160000-a7f3\nstatus: done\nfinal: true\nsummary: ok\nevidence: tests\nrisks: none\nnext: none"},
            ],
            captured_at="2026-06-22T20:04:00+08:00",
        )
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            done["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        done = team_router.capture_verifier_verdict_from_read(
            self.root,
            self.project_id,
            done["taskId"],
            [
                {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
                {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: complete\nrequiredChanges: none\nevidenceChecked: tests\nrisks: none"},
            ],
            captured_at="2026-06-22T20:07:00+08:00",
        )

        closeout = team_router.format_task_update_for_user(done, registry)

        self.assertIn("Team Router Closeout", closeout)
        self.assertIn("summary: complete", closeout)
        self.assertIn("remainingTodos: none", closeout)
        self.assertNotIn("read_thread anchors", closeout)

    def test_read_verifier_verdict_update_with_adapter_returns_user_output(self):
        adapter = FakeThreadAdapter()
        ledger = self._verifying_ledger()
        team_router.record_verifier_request_sent(
            self.root,
            self.project_id,
            ledger["taskId"],
            verifier_thread_id="thread-verifier",
            sent_at="2026-06-22T20:05:00+08:00",
            message_id="msg-verify",
        )
        adapter.messages["thread-verifier"] = [
            {"messageId": "msg-verify", "sentAt": "2026-06-22T20:05:00+08:00", "text": "verify"},
            {"messageId": "msg-verdict", "sentAt": "2026-06-22T20:06:00+08:00", "text": "TEAM_ROUTER_VERDICT taskId=ctr-20260622-160000-a7f3\nresult: pass\nsummary: adapter done\nrequiredChanges: none\nevidenceChecked: fake adapter\nrisks: none"},
        ]

        update = team_router.read_verifier_verdict_update_with_adapter(
            self.root,
            self.project_id,
            self.task_id,
            thread_adapter=adapter,
            captured_at="2026-06-22T20:07:00+08:00",
        )

        self.assertEqual(update["ledger"]["status"], "done")
        self.assertIn("Team Router Closeout", update["userOutput"])
        self.assertIn("summary: adapter done", update["userOutput"])
        self.assertIn("remainingTodos: none", update["userOutput"])


class TestTeamRouterSkillDoc(unittest.TestCase):
    REQUIRED_SKILL_REFERENCE_FILES = (
        "manager-mode.md",
        "side-effect-taxonomy.md",
        "role-handoff-and-review-package.md",
        "direct-return.md",
        "reviewer-gate.md",
        "role-closeout.md",
        "adapter-runtime.md",
        "manual-orchestration.md",
        "testing-and-quality-gates.md",
    )

    def _skill_path(self):
        return ROOT / "skills" / "codex-team-router" / "SKILL.md"

    def _skill_references_dir(self):
        return ROOT / "skills" / "codex-team-router" / "references"

    def _skill_contract_text(self):
        parts = [self._skill_path().read_text(encoding="utf-8")]
        for filename in self.REQUIRED_SKILL_REFERENCE_FILES:
            parts.append((self._skill_references_dir() / filename).read_text(encoding="utf-8"))
        return "\n\n".join(parts)

    def _section(self, text, heading):
        start = text.index(heading)
        candidates = [
            text.find("\n## ", start + len(heading)),
            text.find("\n### ", start + len(heading)),
        ]
        ends = [candidate for candidate in candidates if candidate != -1]
        if not ends:
            return text[start:]
        return text[start:min(ends)]

    def test_skill_entrypoint_uses_progressive_disclosure_references(self):
        skill_path = self._skill_path()
        references_dir = self._skill_references_dir()
        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertLessEqual(len(skill_path.read_bytes()), 8192)
        self.assertTrue(references_dir.is_dir())
        self.assertIn("Codex 8KB cap", skill_text)
        self.assertIn("references/", skill_text)
        self.assertIn("part of the Team Router contract", skill_text)
        for filename in self.REQUIRED_SKILL_REFERENCE_FILES:
            self.assertTrue((references_dir / filename).is_file(), filename)
            self.assertIn("references/%s" % filename, skill_text)

    def test_skill_doc_contains_required_boundaries(self):
        text = self._skill_contract_text()
        for needle in (
            "TEAM_ROUTER_PLAN",
            "TEAM_ROUTER_CALLBACK",
            "TEAM_ROUTER_VERDICT",
            "stateRoot",
            "callback_unreachable",
            "planRequest",
            "searchAnchor",
            "recovery_read_request",
            "registry role persistence",
            "read-only/design-only 不是沙箱",
            "remainingTodos",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("workspace-write", text)

    def test_skill_doc_contains_parent_thread_operating_flow(self):
        text = self._skill_contract_text()
        for needle in (
            "## Parent Thread Entry Flow",
            "list_projects -> create_thread -> send_message_to_thread -> read_thread",
            "parent_entry_guard()",
            "protocol_contract_snapshot()",
            "orchestrate_team_task_with_adapter()",
            "run_team_task_with_adapter()",
            "watch_team_task_with_adapter()",
            "start_team_task_with_adapter()",
            "send_manager_plan_request_with_adapter()",
            "read_manager_plan_with_adapter()",
            "send_executor_dispatch_with_adapter()",
            "read_executor_callback_with_adapter()",
            "send_verifier_request_with_adapter()",
            "read_verifier_verdict_update_with_adapter()",
            "emit `update[\"userOutput\"]`",
            "callbackDelivery: direct-send",
            "verdictDelivery: direct-send",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_VERDICT block>)",
            "watcher/scheduler polling is the fallback",
        ):
            self.assertIn(needle, text)

    def test_skill_doc_contains_chinese_role_model(self):
        text = self._skill_contract_text()
        for needle in (
            "## Role Model",
            "调度者 (Orchestrator)",
            "工具宿主边界 (Adapter Host Boundary)",
            "状态控制器 (State Controller)",
            "规划者 (Manager)",
            "执行者 (Executor)",
            "验证者 (Verifier)",
            "只有规划者、执行者、验证者是长期 role thread",
            "父线程侧状态控制器 (Parent-Side State Controller)",
            "Visible Codex desktop role-thread titles use `角色-任务名`",
            "`执行者-管理者模式触发词修复`",
            "`验证者-管理者模式触发词修复`",
            "Do not include the project name by default",
            "explicit role-intent phrases",
            "“你是管理者”",
            "“你作为管理者”",
            "“团队管理者”",
            "“进入 Manager Mode”",
            "`act as team manager`",
            "裸 `manager` 不触发 Manager Mode",
            "`manager thread`",
            "`manager parser`",
            "`manager integration`",
            "continues an already-active Manager Mode task with terse follow-ups",
            "Manager Mode is sticky for the current task",
            "A terse follow-up or implementation command such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` is not execution authorization",
            "`先修`",
            "`开始修`",
            "`修这个`",
            "`开始处理`",
            "`先处理`",
            "`按刚才说的修`",
            "propose rule updates",
            "Manager Mode 禁止亲自修改文件、跑测试、执行实现命令、commit、push、PR 或 merge",
            "If implementation is requested during active Manager Mode",
            "Do not personally edit files or run project commands from Manager Mode",
            "除非用户明确说“切回执行者”",
            "“你亲自改代码”",
        ):
            self.assertIn(needle, text)
        manager_mode = self._section(text, "### Manager Mode Hard Rule")
        self.assertNotIn(
            "`manager`, or `team manager`, the assistant enters Manager Mode",
            manager_mode,
        )
        self.assertNotIn("“" + "直接" + "改”", manager_mode)
        self.assertNotIn("你" + "来执行", manager_mode)
        self.assertNotIn("while the user is still addressing" + " the agent as manager", manager_mode)
        self.assertNotIn("update the rules", manager_mode)

    def test_skill_doc_separates_adapter_created_and_precreated_role_paths(self):
        text = self._skill_contract_text()

        adapter_created = self._section(text, "### Adapter-created roles path")
        pre_created = self._section(text, "### Pre-created roles path")
        adapter_continuation = self._section(text, "### Adapter continuation")
        manual_continuation = self._section(text, "### Manual/pre-created continuation")

        self.assertIn("start_team_task_with_adapter()", adapter_created)
        self.assertIn("Do not pre-call `create_thread`", adapter_created)
        self.assertIn("create_team_task()", pre_created)
        self.assertIn(
            "Do not call `start_team_task_with_adapter()` after manually creating role threads",
            pre_created,
        )
        for needle in (
            "send_manager_plan_request_with_adapter()",
            "read_manager_plan_with_adapter()",
            "send_executor_dispatch_with_adapter()",
            "read_executor_callback_with_adapter()",
            "send_verifier_request_with_adapter()",
            "read_verifier_verdict_update_with_adapter()",
        ):
            self.assertIn(needle, adapter_continuation)
        for needle in (
            "send_message_to_thread",
            "read_thread",
            "thread_send_anchor()",
            "normalize_thread_read_messages()",
            "record_plan_request_sent()",
            "capture_manager_plan_from_read()",
            "record_executor_dispatch_sent()",
            "capture_executor_callback_from_read()",
            "record_verifier_request_sent()",
            "capture_verifier_verdict_from_read()",
            "format_task_update_for_user()",
        ):
            self.assertIn(needle, manual_continuation)
        self.assertNotIn("send_manager_plan_request_with_adapter()", manual_continuation)
        self.assertNotIn("read_verifier_verdict_update_with_adapter()", manual_continuation)
        self.assertIn("does not continue through `orchestrate_team_task_with_adapter()`", manual_continuation)
        self.assertIn("not an end-to-end adapter-runner entrypoint", manual_continuation)

    def test_live_orchestration_runbook_exists(self):
        path = ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        text = path.read_text(encoding="utf-8")
        for needle in (
            "# Codex Team Router Live Orchestration Runbook",
            "create_thread",
            "send_message_to_thread",
            "read_thread",
            "parent_entry_guard()",
            "orchestrate_team_task_with_adapter()",
            "run_team_task_with_adapter()",
            "watch_team_task_with_adapter()",
            "read_verifier_verdict_update_with_adapter()",
            "tests/fixtures/team_router/live_read_thread_verdict.json",
            "tests/fixtures/team_router/live_manager_inbox_direct_return.json",
            "tests/fixtures/team_router/three_role_visible_smoke_scenarios.json",
            "Emit `update[\"userOutput\"]` exactly",
            "Team Router Closeout",
            "Team Router Handoff",
            "direct-send-callback-success",
            "direct-send-missed-self-thread-fallback",
            "verifier-needs-rework",
            "verifier-blocked-closeout",
            "remainingTodos",
            "callbackDelivery: direct-send",
            "verdictDelivery: direct-send",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK/TEAM_ROUTER_VERDICT block>)",
            "Watcher polling is the fallback path",
            "调度者 (Orchestrator)",
            "规划者 (Manager)",
            "执行者 (Executor)",
            "验证者 (Verifier)",
            "Visible Codex desktop role-thread titles use `角色-任务名`",
            "`执行者-管理者模式触发词修复`",
            "`验证者-管理者模式触发词修复`",
            "Do not include the project name by default",
            "explicit role-intent phrases",
            "“你是管理者”",
            "“你作为管理者”",
            "“团队管理者”",
            "“进入 Manager Mode”",
            "`act as team manager`",
            "裸 `manager` 不触发 Manager Mode",
            "`manager thread`",
            "`manager parser`",
            "`manager integration`",
            "Manager Mode is sticky for the current task",
            "A terse follow-up or implementation command such as `修`, `继续`, `处理`, `先修`, `开始修`, `修这个`, `开始处理`, `先处理`, `按刚才说的修`, `go`, or `do it` is not execution authorization",
            "`先修`",
            "`开始修`",
            "`修这个`",
            "`开始处理`",
            "`先处理`",
            "`按刚才说的修`",
            "propose rule updates",
            "Do not personally edit files or run project commands from Manager Mode",
            "“你亲自改代码”",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("“" + "直接" + "改”", text)
        self.assertNotIn("你" + "来执行", text)
        self.assertNotIn("while the user is still addressing" + " the agent as manager", text)

    def test_readme_and_runbook_document_skill_progressive_disclosure(self):
        paths = (
            ROOT / "README.md",
            ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for needle in (
                    "Progressive disclosure invariant",
                    "SKILL.md",
                    "Codex 8KB cap",
                    "references/",
                    "Team Router contract",
                ):
                    self.assertIn(needle, text)
        self.assertNotIn("update the rules", text)

    def test_side_effect_taxonomy_docs_cover_manager_action_boundaries(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "sideEffectTaxonomy",
                    "READ_ONLY",
                    "DISPATCH_ONLY",
                    "LOCAL_CLOSEOUT",
                    "WORKSPACE_WRITE",
                    "HEAVY_OR_RISKY",
                    "EXTERNAL_RELEASE",
                    "`可以`",
                    "`修`",
                    "`继续`",
                    "`开始修`",
                    "`先修`",
                    "`修这个`",
                    "`do it`",
                    "verifier pass",
                    "explicit user commit request",
                    "push/PR/merge/deploy",
                    "subagent fallback is not allowed",
                ):
                    self.assertIn(needle, text)
                for alternatives in (
                    ("at most `DISPATCH_ONLY`", "至多授权 `DISPATCH_ONLY`"),
                    ("not implementation authorization", "不是 implementation authorization"),
                    ("must be delegated to executor", "必须委派 executor"),
                    ("explicitly switches roles", "明确说“切回执行者”"),
                    ("stage only accepted files", "stage 已验收文件"),
                    ("unrelated untracked", "无关 untracked"),
                    ("separate publish/release authorization", "独立 publish/release 授权"),
                    ("explicit separate authorization", "单独明确授权"),
                ):
                    self.assertTrue(
                        any(needle in text for needle in alternatives),
                        "%s missing one of %r" % (name, alternatives),
                    )

    def test_role_handoff_and_review_package_policy_docs_cover_stable_packages(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "roleHandoffPolicy",
                    "reviewPackagePolicy",
                    "stable file/path handoff",
                    "accumulated chat history",
                    "taskBriefPath",
                    "executorReportPath",
                    "reviewPackagePath",
                    "future optional runtime fields",
                    "taskId",
                    "objective",
                    "scope",
                    "touched/accepted files",
                    "diff summary",
                    "executor callback/report",
                    "test/verification evidence",
                    "reviewer requiredChanges",
                    "excluded unrelated untracked",
                    "risks/remainingTodos",
                    "TEAM_ROUTER_CALLBACK",
                    "TEAM_ROUTER_REVIEW",
                    "TEAM_ROUTER_VERDICT",
                    "WORKSPACE_WRITE",
                    "executor",
                    "git diff --name-only",
                    "untracked files",
                ):
                    self.assertIn(needle, text)
                for alternatives in (
                    ("stable facts by file/path", "stable file/path handoff"),
                    ("inline protocol block fallback", "inline protocol blocks"),
                    ("does not replace", "不替代"),
                    ("supplements evidence", "补充证据"),
                    ("not implemented runtime fields", "不实现 runtime"),
                    ("stage new reference files explicitly", "显式 stage 新 reference files"),
                    ("role threads can access the same workspace/path", "可访问同一 workspace/path"),
                    ("Writing workspace package artifacts", "写 workspace package artifacts"),
                    ("active Manager Mode unless there is an explicit role switch", "除非明确角色切换"),
                    ("READ_ONLY", "DISPATCH_ONLY"),
                ):
                    self.assertTrue(
                        any(needle in text for needle in alternatives),
                        "%s missing one of %r" % (name, alternatives),
                    )

    def test_live_orchestration_runbook_separates_adapter_created_and_precreated_role_paths(self):
        path = ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md"
        text = path.read_text(encoding="utf-8")

        adapter_created = self._section(text, "### Adapter-created roles path")
        pre_created = self._section(text, "### Pre-created roles path")
        adapter_continuation = self._section(text, "### Adapter continuation")
        manual_continuation = self._section(text, "### Manual/pre-created continuation")

        self.assertIn("start_team_task_with_adapter()", adapter_created)
        self.assertIn("Do not pre-call `create_thread`", adapter_created)
        self.assertIn("create_team_task()", pre_created)
        self.assertIn(
            "Do not call `start_team_task_with_adapter()` after manually creating role threads",
            pre_created,
        )
        for needle in (
            "send_message_to_thread",
            "read_thread",
            "record_plan_request_sent()",
            "capture_manager_plan_from_read()",
            "record_executor_dispatch_sent()",
            "capture_executor_callback_from_read()",
            "record_verifier_request_sent()",
            "capture_verifier_verdict_from_read()",
        ):
            self.assertIn(needle, manual_continuation)
        self.assertIn("read_verifier_verdict_update_with_adapter()", adapter_continuation)
        self.assertNotIn("send_manager_plan_request_with_adapter()", manual_continuation)
        self.assertIn("does not continue through `orchestrate_team_task_with_adapter()`", manual_continuation)
        self.assertIn("not an end-to-end adapter-runner entrypoint", manual_continuation)

    def test_three_role_visible_smoke_fixture_covers_required_paths(self):
        path = ROOT / "tests" / "fixtures" / "team_router" / "three_role_visible_smoke_scenarios.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        names = {scenario["name"] for scenario in raw["scenarios"]}

        self.assertEqual(raw["roles"]["manager"], "规划者")
        self.assertIn("调度者", raw["parentSideConcepts"])
        self.assertNotIn("父线程" + "调度者", raw["parentSideConcepts"])
        self.assertEqual(
            names,
            {
                "direct-send-callback-success",
                "direct-send-missed-self-thread-fallback",
                "verifier-needs-rework",
                "verifier-blocked-closeout",
            },
        )
        direct = next(s for s in raw["scenarios"] if s["name"] == "direct-send-callback-success")
        self.assertIn("returnThreadId", direct["requiredLedgerFields"])
        self.assertIn("fallbackSearchAnchor", direct["requiredLedgerFields"])

    def test_readme_documents_team_router_quick_start_and_boundaries(self):
        path = ROOT / "README.md"
        text = path.read_text(encoding="utf-8")
        for needle in (
            "## Team Router 快速使用",
            "`codex-team-router`",
            "`dynamic-workflow`",
            "read-only/design-only",
            "不支持 `workspace-write`",
            "调度者",
            "规划者",
            "执行者",
            "验证者",
            "审查者",
            "TEAM_ROUTER_REVIEW",
            "reviewDelivery: direct-send",
            "reviewFallback: self-thread-marker",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)",
            "parent_entry_guard()",
            "protocol_contract_snapshot()",
            "tests/fixtures/team_router/three_role_visible_smoke_scenarios.json",
            "Manager Mode 是当前任务内的粘性角色",
            "规则更新建议或 dispatch/prepare executor work",
            "`先修`",
            "`开始修`",
            "`修这个`",
            "`开始处理`",
            "`先处理`",
            "`按刚才说的修`",
            "dispatch/prepare executor work",
            "一直持续到明确角色切换",
            "manual helper/record/capture functions",
            "不把 pre-created roles 送进 adapter runner",
            "returnThreadId",
            "callbackDelivery: direct-send",
            "callbackFallback: self-thread-marker",
            "verdictDelivery: direct-send",
            "verdictFallback: self-thread-marker",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_CALLBACK block>)",
            "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)",
            "切回执行者",
            "你亲自改代码",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("你" + "来执行", text)
        self.assertNotIn("直接" + "改", text)
        self.assertNotIn("while the user is still addressing" + " the agent as manager", text)



    def test_project_layout_keeps_team_router_root_and_dynamic_workflow_subproject(self):
        self.assertTrue((ROOT / "src" / "team_router.py").is_file())
        self.assertTrue((ROOT / "skills" / "codex-team-router" / "SKILL.md").is_file())
        self.assertTrue((ROOT / "tests" / "test_team_router.py").is_file())
        self.assertTrue((ROOT / "tests" / "fixtures" / "team_router").is_dir())
        self.assertTrue((ROOT / "dynamic-workflow" / "src" / "runner.py").is_file())
        self.assertTrue((ROOT / "dynamic-workflow" / "skill" / "SKILL.md").is_file())
        self.assertTrue((ROOT / "dynamic-workflow" / "tests" / "test_run.py").is_file())
        self.assertFalse((ROOT / "src" / "runner.py").exists())
        self.assertFalse((ROOT / "tests" / "test_run.py").exists())
        self.assertIn(
            "dynamic-workflow/src/runner.py",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
    def test_manager_orchestration_policy_docs_cover_polling_reuse_and_verifier_return(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "low-frequency",
                    "event-driven",
                    "read_thread",
                    "30-60s",
                    "Role reuse policy",
                    "reuse existing executor",
                    "existing verifier",
                    "original executor",
                    "original verifier",
                    "isolation requirement",
                    "verdictDelivery: direct-send",
                    "verdictFallback: self-thread-marker",
                    "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_VERDICT block>)",
                ):
                    self.assertIn(needle, text)

    def test_closeout_policies_docs_cover_commit_and_role_thread_closeout(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "Manager commit closeout policy",
                    "manager owns commit workflow",
                    "verifier pass",
                    "stage 已验收文件",
                    "排除无关 untracked",
                    "push/PR/merge/deploy 单独授权",
                    "roleCloseoutPolicy",
                    "不 clear role thread",
                    "ROLE_CLOSEOUT",
                    "final protocol block is the closeout",
                    "TEAM_ROUTER_CALLBACK",
                    "TEAM_ROUTER_REVIEW",
                    "TEAM_ROUTER_VERDICT",
                    "compact is native operation, not chat prompt",
                    "active/inProgress",
                    "compact/archive",
                    "身份污染",
                    "上下文过长",
                    "boundary 变化",
                    "用户明确要求",
                ):
                    self.assertIn(needle, text)
                for alternatives in (
                    ("explicit user request to commit", "用户明确要求提交"),
                    ("continue implementation", "继续实现"),
                    ("modify files", "修改文件"),
                    ("heavy commands", "重型命令"),
                    ("默认不向 role threads 额外发送", "does not send extra ROLE_CLOSEOUT"),
                    ("没有可用 compact 工具则不做", "if no compact tool is available, do nothing"),
                    ("没有 final protocol block", "no final protocol block exists"),
                    ("最短 closeout/stop message", "shortest closeout/stop message"),
                ):
                    self.assertTrue(
                        any(needle in text for needle in alternatives),
                        "%s missing one of %r" % (name, alternatives),
                    )



    def test_conditional_reviewer_docs_cover_role_policy_reuse_and_direct_return(self):
        docs = (
            ("README.md", (ROOT / "README.md").read_text(encoding="utf-8")),
            ("codex-team-router skill contract", self._skill_contract_text()),
            (
                "codex-team-router-live-orchestration.md",
                (ROOT / "docs" / "runbooks" / "codex-team-router-live-orchestration.md").read_text(
                    encoding="utf-8"
                ),
            ),
        )
        for name, text in docs:
            with self.subTest(path=name):
                for needle in (
                    "conditional reviewer",
                    "reviewer",
                    "TEAM_ROUTER_REVIEW",
                    "read-only/adversarial",
                    "not final acceptance",
                    "verifier remains final acceptance",
                    "existing reviewer",
                    "original reviewer",
                    "reviewDelivery: direct-send",
                    "reviewFallback: self-thread-marker",
                    "send_message_to_thread(threadId=<returnThreadId>, prompt=<TEAM_ROUTER_REVIEW block>)",
                    "send_reviewer_request_with_adapter()",
                    "read_reviewer_review_update_with_adapter()",
                    "capture_reviewer_review_from_read()",
                    "create/register reviewer role conversation",
                    "subagent fallback is not allowed",
                    "router/manager/orchestration policy",
                    "role protocol",
                    "shared/high-risk logic",
                ):
                    self.assertIn(needle, text)

if __name__ == "__main__":
    unittest.main()
