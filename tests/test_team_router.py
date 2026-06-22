# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from helpers import ROOT
import team_router


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

    def test_rework_limit_blocks_without_incrementing(self):
        status, count = team_router.next_rework_dispatch(rework_count=3, max_rework=3)
        self.assertEqual(status, "blocked")
        self.assertEqual(count, 3)
        status, count = team_router.next_rework_dispatch(rework_count=2, max_rework=3)
        self.assertEqual(status, "dispatched")
        self.assertEqual(count, 3)


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

    def test_same_timestamp_callback_without_message_id_keeps_waiting(self):
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

        self.assertEqual(updated["status"], "awaiting_callback")

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
class TestTeamRouterSkillDoc(unittest.TestCase):
    def test_skill_doc_contains_required_boundaries(self):
        path = ROOT / "skills" / "codex-team-router" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
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
        ):
            self.assertIn(needle, text)
        self.assertNotIn("workspace-write", text)


if __name__ == "__main__":
    unittest.main()