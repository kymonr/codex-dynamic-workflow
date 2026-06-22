# -*- coding: utf-8 -*-
import tempfile
import unittest
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
            "read-only/design-only 不是沙箱",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("workspace-write", text)


if __name__ == "__main__":
    unittest.main()