from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "routing_smoke.py"


def isolated_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPYCACHEPREFIX", None)
    env.update({"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location(
        "dynamic_workflow_routing_smoke", SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke_module()


def _events(case):
    return [
        json.loads(line)
        for line in smoke._synthetic_transcript(case).splitlines()
    ]


def _transcript(events):
    return "\n".join(json.dumps(event) for event in events)


def _reviewer_events(
    *,
    runtime=True,
    model="gpt-5.6-sol",
    effort="xhigh",
    task_name="fixture-reviewer",
):
    events = [
        {
            "type": "item.completed",
            "item": {
                "type": "tool_call",
                "name": "collaboration.spawn_agent",
                "arguments": {
                    "agent_type": "dynamic_workflow_sol_reviewer",
                    "task_name": task_name,
                    "fork_turns": "none",
                },
            },
        }
    ]
    if runtime:
        events.append(
            {
                "type": "subagent.runtime",
                "task_name": task_name,
                "model": model,
                "effort": effort,
            }
        )
    return events


class RoutingSmokeTests(unittest.TestCase):
    def test_default_self_test_is_offline_and_zero_cost(self) -> None:
        with mock.patch.object(smoke.subprocess, "run") as run:
            result = smoke.run_self_test()
        run.assert_not_called()
        self.assertTrue(result["passed"])
        self.assertEqual(result["mode"], "offline-evaluator-self-test")
        self.assertEqual(result["codex_exec_calls"], 0)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["network_calls"], 0)
        self.assertEqual(result["adversarial_prompt_echo"], "unknown")
        self.assertEqual(result["incomplete_transcript"], "unknown")

    def test_representative_structured_routes(self) -> None:
        for case in smoke.CASES.values():
            with self.subTest(case=case.name):
                result = smoke.evaluate_transcript(
                    case, smoke._synthetic_transcript(case)
                )
                self.assertEqual(result["status"], "pass")
                self.assertEqual(
                    sorted(result["observed"]["routes"]),
                    sorted(case.routes),
                )

    def test_agent_fleet_mode_is_accepted_by_synthetic_evaluator(self) -> None:
        case = smoke.SmokeCase(
            name="agent-fleet-mode",
            prompt="",
            workflow=True,
            routes=("Luna", "Luna", "Luna", "Sol"),
            mode="execute",
            orchestration_mode="agent-fleet",
        )
        result = smoke.evaluate_transcript(
            case, smoke._synthetic_transcript(case)
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            result["observed"]["orchestration_mode"], "agent-fleet"
        )

    def test_implicit_single_branch_stays_root(self) -> None:
        case = smoke.CASES["implicit-single-negative"]
        result = smoke.evaluate_transcript(
            case, smoke._synthetic_transcript(case)
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["observed"]["routes"], [])
        self.assertEqual(result["observed"]["selection_count"], 0)

    def test_broad_simple_swarm_uses_three_luna_branches(self) -> None:
        case = smoke.CASES["broad-simple-swarm"]
        result = smoke.evaluate_transcript(
            case, smoke._synthetic_transcript(case)
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["observed"]["routes"], ["Luna", "Luna", "Luna"])

    def test_orchestration_mode_is_required_and_bound(self) -> None:
        case = smoke.CASES["broad-simple-swarm"]
        baseline = _events(case)
        result = smoke.evaluate_transcript(case, _transcript(baseline))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            result["observed"]["orchestration_mode"], "simple-swarm"
        )
        self.assertEqual(
            result["observed"]["visible_orchestration_mode_count"], 1
        )

        missing = _events(case)
        marker = next(
            event
            for event in missing
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("id") == "marker"
        )
        marker["item"]["text"] = "Workflow: dynamic-workflow"
        self.assertEqual(
            smoke.evaluate_transcript(case, _transcript(missing))["status"],
            "fail",
        )

        wrong = _events(case)
        marker = next(
            event
            for event in wrong
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("id") == "marker"
        )
        marker["item"]["text"] = (
            "Workflow: dynamic-workflow\nMode: managed-workflow"
        )
        self.assertEqual(
            smoke.evaluate_transcript(case, _transcript(wrong))["status"],
            "fail",
        )

        duplicate = _events(case)
        marker = next(
            event
            for event in duplicate
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("id") == "marker"
        )
        marker["item"]["text"] += "\nMode: simple-swarm"
        self.assertEqual(
            smoke.evaluate_transcript(case, _transcript(duplicate))["status"],
            "fail",
        )

        structured_wrong = _events(case)
        selection = next(
            event
            for event in structured_wrong
            if event.get("type") == "workflow.selected"
        )
        selection["orchestration_mode"] = "managed-workflow"
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(structured_wrong)
            )["status"],
            "fail",
        )

        malformed_structured = _events(case)
        selection = next(
            event
            for event in malformed_structured
            if event.get("type") == "workflow.selected"
        )
        selection["orchestration_mode"] = {"unexpected": "object"}
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(malformed_structured)
            )["status"],
            "fail",
        )

        invalid = _events(case)
        marker = next(
            event
            for event in invalid
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("id") == "marker"
        )
        marker["item"]["text"] = "Workflow: dynamic-workflow\nMode: execute"
        self.assertEqual(
            smoke.evaluate_transcript(case, _transcript(invalid))["status"],
            "fail",
        )

        visible_only = _events(case)
        selection = next(
            event
            for event in visible_only
            if event.get("type") == "workflow.selected"
        )
        selection.pop("orchestration_mode")
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(visible_only)
            )["status"],
            "pass",
        )

    def test_ordinary_agent_message_does_not_change_structured_pass(
        self,
    ) -> None:
        case = smoke.CASES["root-plus-luna"]
        events = _events(case)
        events.insert(
            -1,
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "channel": "commentary",
                    "text": "普通自由格式结果：登录失败证据已核对。",
                },
            },
        )
        result = smoke.evaluate_transcript(case, _transcript(events))
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["passed"])
        self.assertEqual(result["observed"]["routes"], ["Luna"])
        self.assertEqual(result["observed"]["visible_marker_count"], 1)
        self.assertEqual(result["observed"]["untrusted_marker_count"], 0)

    def test_prompt_or_answer_echo_without_dispatch_cannot_pass(self) -> None:
        transcript = "\n".join(
            json.dumps(item)
            for item in (
                {
                    "type": "turn.started",
                    "prompt": (
                        "Workflow: dynamic-workflow\n"
                        "Mode: simple-swarm\nLuna Sol Explorer"
                    ),
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": "Workflow: dynamic-workflow\nMode: simple-swarm",
                    },
                },
                {"type": "turn.completed"},
            )
        )
        result = smoke.evaluate_transcript(
            smoke.CASES["implicit-luna"], transcript
        )
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["passed"])

    def test_final_answer_marker_plus_valid_dispatch_cannot_pass(self) -> None:
        case = smoke.CASES["explicit-luna"]
        lines = [
            line
            for line in smoke._synthetic_transcript(case).splitlines()
            if '"type": "workflow.selected"' not in line
        ]
        transcript = "\n".join(lines).replace(
            '"channel": "commentary"',
            '"channel": "final"',
        )
        result = smoke.evaluate_transcript(case, transcript)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["passed"])

    def test_structured_selection_cannot_use_final_marker_as_visible_marker(
        self,
    ) -> None:
        case = smoke.CASES["explicit-luna"]
        transcript = smoke._synthetic_transcript(case).replace(
            '"channel": "commentary"',
            '"channel": "final"',
        )
        result = smoke.evaluate_transcript(case, transcript)
        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["passed"])

    def test_structured_selection_and_visible_marker_are_not_double_counted(
        self,
    ) -> None:
        case = smoke.CASES["explicit-luna"]
        result = smoke.evaluate_transcript(
            case, smoke._synthetic_transcript(case)
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["observed"]["selection_count"], 1)
        self.assertEqual(
            result["observed"]["structured_selection_count"], 1
        )
        self.assertEqual(
            result["observed"]["commentary_selection_count"], 1
        )

    def test_duplicate_final_marker_is_a_failure(self) -> None:
        case = smoke.CASES["explicit-luna"]
        lines = smoke._synthetic_transcript(case).splitlines()
        lines.insert(
            -1,
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "channel": "final",
                        "text": "Workflow: dynamic-workflow",
                    },
                }
            ),
        )
        result = smoke.evaluate_transcript(case, "\n".join(lines))
        self.assertEqual(result["status"], "fail")

    def test_duplicate_structured_dispatch_evidence_is_deduplicated(
        self,
    ) -> None:
        case = smoke.CASES["explicit-luna"]
        lines = smoke._synthetic_transcript(case).splitlines()
        lines.insert(
            -1,
            json.dumps(
                {
                    "type": "subagent.dispatched",
                    "task_name": "fixture-1",
                    "agent_type": "luna",
                    "fork_turns": "none",
                }
            ),
        )
        result = smoke.evaluate_transcript(case, "\n".join(lines))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["observed"]["routes"], ["Luna"])

    def test_same_task_dispatch_alias_cannot_inflate_route_count(self) -> None:
        case = smoke.CASES["implicit-luna"]
        events = []
        for event in _events(case):
            item_args = event.get("item", {}).get("arguments", {})
            if event.get("task_name") == "fixture-2":
                continue
            if item_args.get("task_name") == "fixture-2":
                continue
            events.append(event)
        events.insert(
            -1,
            {
                "type": "subagent.dispatched",
                "task_name": "fixture-1",
                "agent_type": "luna",
            },
        )
        result = smoke.evaluate_transcript(case, _transcript(events))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["observed"]["routes"], ["Luna"])

    def test_conflicting_same_task_dispatch_evidence_fails(self) -> None:
        case = smoke.CASES["explicit-luna"]
        events = _events(case)
        events.insert(
            -1,
            {
                "type": "subagent.dispatched",
                "task_name": "fixture-1",
                "agent_type": "sol",
                "fork_turns": "none",
            },
        )
        result = smoke.evaluate_transcript(case, _transcript(events))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(
            result["observed"]["dispatch_conflict_tasks"],
            ["fixture-1"],
        )

    def test_conflicting_dispatch_aliases_fail_but_effective_route_wins(
        self,
    ) -> None:
        case = smoke.CASES["explicit-luna"]
        conflicts = (
            ("task", "different-task"),
            ("reasoning_effort", "low"),
            ("service_tier", "standard"),
        )
        for field, value in conflicts:
            events = _events(case)
            spawn = next(
                event
                for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "tool_call"
            )
            arguments = spawn["item"]["arguments"]
            if field == "reasoning_effort":
                arguments["effort"] = "max"
            elif field == "service_tier":
                arguments["tier"] = "fast"
            arguments[field] = value
            with self.subTest(alias=field):
                result = smoke.evaluate_transcript(
                    case, _transcript(events)
                )
                self.assertEqual(result["status"], "fail")

        events = _events(case)
        spawn = next(
            event
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "tool_call"
        )
        spawn["item"]["arguments"].update(
            {"route": "Sol", "effective_route": "Luna"}
        )
        result = smoke.evaluate_transcript(case, _transcript(events))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["observed"]["routes"], ["Luna"])

        cross_source = _events(case)
        spawn = next(
            event
            for event in cross_source
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "tool_call"
        )
        spawn["item"]["arguments"]["route"] = "Sol"
        cross_source.insert(
            -1,
            {
                "type": "subagent.dispatched",
                "task_name": "fixture-1",
                "agent_type": "luna",
                "effective_route": "Luna",
                "fork_turns": "none",
            },
        )
        result = smoke.evaluate_transcript(
            case, _transcript(cross_source)
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["observed"]["routes"], ["Luna"])

    def test_incomplete_or_invalid_transcript_is_unknown(self) -> None:
        incomplete = smoke.evaluate_transcript(
            smoke.CASES["implicit-luna"],
            '{"type":"turn.started"}',
        )
        invalid = smoke.evaluate_transcript(
            smoke.CASES["implicit-luna"],
            'not-json\n{"type":"turn.completed"}',
        )
        self.assertEqual(incomplete["status"], "unknown")
        self.assertEqual(invalid["status"], "unknown")

    def test_explicit_luna_fixture_skips_explorer(self) -> None:
        case = smoke.CASES["explicit-luna"]
        result = smoke.evaluate_transcript(
            case, smoke._synthetic_transcript(case)
        )
        self.assertEqual(result["observed"]["routes"], ["Luna"])
        self.assertNotIn("Explorer", result["observed"]["routes"])

    def test_missing_or_mismatched_route_identity_cannot_pass(self) -> None:
        for name in ("explicit-luna", "complex-sol", "bounded-explorer"):
            case = smoke.CASES[name]
            complete = smoke._synthetic_transcript(case)
            missing = "\n".join(
                line
                for line in complete.splitlines()
                if '"type": "subagent.runtime"' not in line
            )
            with self.subTest(case=name):
                missing_result = smoke.evaluate_transcript(case, missing)
                self.assertEqual(missing_result["status"], "unknown")

        luna = smoke.CASES["explicit-luna"]
        mismatched = smoke._synthetic_transcript(luna).replace(
            '"model": "gpt-5.6-luna"',
            '"model": "gpt-5.6-sol"',
        )
        mismatch_result = smoke.evaluate_transcript(luna, mismatched)
        self.assertEqual(mismatch_result["status"], "fail")

        sol = smoke.CASES["complex-sol"]
        legacy_default = smoke._synthetic_transcript(sol).replace(
            '"agent_type": "sol"',
            '"agent_type": "default"',
        )
        legacy_default_result = smoke.evaluate_transcript(
            sol, legacy_default
        )
        self.assertEqual(legacy_default_result["status"], "fail")

    def test_native_grok_dispatch_cannot_pass(self) -> None:
        case = smoke.CASES["explicit-luna"]
        events = _events(case)
        spawn = next(
            event
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "tool_call"
        )
        spawn["item"]["arguments"]["agent_type"] = "grok_writer"
        runtime = next(
            event
            for event in events
            if event.get("type") == "subagent.runtime"
        )
        runtime["model"] = "xai/grok-4.6"
        runtime["effort"] = "high"
        runtime["tier"] = "default"

        result = smoke.evaluate_transcript(case, _transcript(events))

        self.assertNotEqual(result["status"], "pass")
        self.assertIn("UNKNOWN", result["observed"]["routes"])

    def test_requested_identity_conflicts_cannot_pass(self) -> None:
        case = smoke.CASES["explicit-luna"]
        conflicts = {
            "model": ("model", "gpt-5.6-sol"),
            "effort": ("reasoning_effort", "low"),
        }
        for label, (field, value) in conflicts.items():
            events = _events(case)
            spawn = next(
                event
                for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "tool_call"
            )
            spawn["item"]["arguments"][field] = value
            with self.subTest(field=label):
                result = smoke.evaluate_transcript(
                    case, _transcript(events)
                )
                self.assertEqual(result["status"], "fail")

    def test_service_tier_is_independent_telemetry(self) -> None:
        case = smoke.CASES["explicit-luna"]
        missing_tier = "\n".join(
            line.replace(', "tier": "fast"', "")
            if '"type": "subagent.runtime"' in line
            else line
            for line in smoke._synthetic_transcript(case).splitlines()
        )
        missing_result = smoke.evaluate_transcript(case, missing_tier)
        self.assertEqual(missing_result["status"], "pass")
        self.assertEqual(
            missing_result["observed"]["service_tier"],
            ["UNKNOWN"],
        )

        events = _events(case)
        spawn = next(
            event
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "tool_call"
        )
        spawn["item"]["arguments"]["service_tier"] = "standard"
        mismatch_result = smoke.evaluate_transcript(
            case, _transcript(events)
        )
        self.assertEqual(mismatch_result["status"], "pass")
        self.assertEqual(
            mismatch_result["observed"]["service_tier"],
            ["MISMATCH"],
        )

    def test_controlled_routes_reject_full_history_fork(self) -> None:
        for name in ("explicit-luna", "complex-sol"):
            case = smoke.CASES[name]
            events = _events(case)
            executor = next(
                event
                for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {})
                .get("arguments", {})
                .get("task_name")
                == "fixture-1"
            )
            executor["item"]["arguments"]["fork_turns"] = "all"
            with self.subTest(case=name):
                result = smoke.evaluate_transcript(
                    case, _transcript(events)
                )
                self.assertEqual(result["status"], "fail")

    def test_conflicting_runtime_events_fail_and_identical_duplicates_pass(
        self,
    ) -> None:
        case = smoke.CASES["explicit-luna"]
        events = _events(case)
        runtime = next(
            event
            for event in events
            if event.get("type") == "subagent.runtime"
        )
        events.insert(-1, dict(runtime))
        identical = smoke.evaluate_transcript(case, _transcript(events))
        self.assertEqual(identical["status"], "pass")

        events[-2] = {
            **events[-2],
            "model": "gpt-5.6-sol",
        }
        conflict = smoke.evaluate_transcript(case, _transcript(events))
        self.assertEqual(conflict["status"], "fail")
        self.assertEqual(
            conflict["observed"]["runtime_conflict_tasks"],
            ["fixture-1"],
        )

        for field, value in (
            ("task", "different-task"),
            ("reasoning_effort", "xhigh"),
            ("service_tier", "standard"),
        ):
            events = _events(case)
            runtime = next(
                event
                for event in events
                if event.get("type") == "subagent.runtime"
            )
            runtime[field] = value
            with self.subTest(runtime_alias=field):
                result = smoke.evaluate_transcript(
                    case, _transcript(events)
                )
                self.assertEqual(result["status"], "fail")
                self.assertEqual(
                    result["observed"]["runtime_conflict_tasks"],
                    ["fixture-1"],
                )

    def test_events_are_bound_to_one_ordered_thread_and_turn(self) -> None:
        case = smoke.CASES["explicit-luna"]

        terminal_first = _events(case)
        terminal = terminal_first.pop()
        terminal_first.insert(2, terminal)
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(terminal_first)
            )["status"],
            "fail",
        )

        after_terminal = _events(case)
        after_terminal.append(
            {
                "type": "workflow.selected",
                "skill": "dynamic-workflow",
                "mode": "execute",
            }
        )
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(after_terminal)
            )["status"],
            "fail",
        )

        repeated_thread = _events(case)
        repeated_thread.insert(
            1, {"type": "thread.started", "thread_id": "other"}
        )
        repeated_turn = _events(case)
        repeated_turn.insert(2, {"type": "turn.started"})
        repeated_terminal = _events(case)
        repeated_terminal.append({"type": "turn.completed"})
        for label, events in {
            "thread": repeated_thread,
            "turn": repeated_turn,
            "terminal": repeated_terminal,
        }.items():
            with self.subTest(repeated=label):
                self.assertEqual(
                    smoke.evaluate_transcript(
                        case, _transcript(events)
                    )["status"],
                    "fail",
                )

        mixed_turn = _events(case)
        mixed_turn[1]["turn_id"] = "turn-a"
        mixed_turn[-1]["turn_id"] = "turn-b"
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(mixed_turn)
            )["status"],
            "fail",
        )

        runtime_first = _events(case)
        runtime_index = next(
            index
            for index, event in enumerate(runtime_first)
            if event.get("type") == "subagent.runtime"
        )
        runtime = runtime_first.pop(runtime_index)
        spawn_index = next(
            index
            for index, event in enumerate(runtime_first)
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "tool_call"
        )
        runtime_first.insert(spawn_index, runtime)
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(runtime_first)
            )["status"],
            "fail",
        )

        foreign_context = _events(case)
        for event in foreign_context:
            if event.get("type") in {
                "workflow.selected",
                "item.completed",
                "subagent.runtime",
            }:
                event["thread_id"] = "foreign-thread"
                event["turn_id"] = "foreign-turn"
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(foreign_context)
            )["status"],
            "fail",
        )

    def test_successful_and_failed_terminal_evidence_conflicts(self) -> None:
        case = smoke.CASES["explicit-luna"]
        after_success = _events(case)
        after_success.append(
            {"type": "turn.failed", "turn_id": "offline-turn"}
        )
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(after_success)
            )["status"],
            "fail",
        )

        before_success = _events(case)
        before_success.insert(
            -1, {"type": "turn.failed", "turn_id": "offline-turn"}
        )
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(before_success)
            )["status"],
            "fail",
        )

    def test_selection_mode_and_commentary_channel_are_enforced(self) -> None:
        case = smoke.CASES["explicit-luna"]

        mismatch = _events(case)
        selection = next(
            event
            for event in mismatch
            if event.get("type") == "workflow.selected"
        )
        selection["mode"] = "audit"
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(mismatch)
            )["status"],
            "fail",
        )

        wrong_but_matching = _events(smoke.CASES["implicit-luna"])
        selection = next(
            event
            for event in wrong_but_matching
            if event.get("type") == "workflow.selected"
        )
        marker = next(
            event
            for event in wrong_but_matching
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
        )
        selection["mode"] = "audit"
        marker["item"]["text"] = "Workflow: dynamic-workflow (audit)"
        self.assertEqual(
            smoke.evaluate_transcript(
                smoke.CASES["implicit-luna"],
                _transcript(wrong_but_matching),
            )["status"],
            "fail",
        )

        missing = _events(case)
        selection = next(
            event
            for event in missing
            if event.get("type") == "workflow.selected"
        )
        selection.pop("mode")
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(missing)
            )["status"],
            "pass",
        )

        for channel in ("status", "progress"):
            events = _events(case)
            marker = next(
                event
                for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "agent_message"
            )
            marker["item"]["channel"] = channel
            with self.subTest(channel=channel):
                result = smoke.evaluate_transcript(
                    case, _transcript(events)
                )
                self.assertEqual(result["status"], "fail")
                self.assertEqual(
                    result["observed"]["commentary_selection_count"], 0
                )

        conflicting_channel = _events(case)
        marker = next(
            event
            for event in conflicting_channel
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
        )
        marker["channel"] = "final"
        result = smoke.evaluate_transcript(
            case, _transcript(conflicting_channel)
        )
        self.assertEqual(result["status"], "fail")

    def test_reviewer_dispatch_count_and_identity_are_enforced(self) -> None:
        negative = smoke.CASES["simple-negative"]
        events = _events(negative)
        events[-1:-1] = _reviewer_events()
        self.assertEqual(
            smoke.evaluate_transcript(
                negative, _transcript(events)
            )["status"],
            "fail",
        )

        case = smoke.CASES["complex-sol"]
        self.assertEqual(
            smoke.evaluate_transcript(case, _transcript(_events(case)))["status"],
            "pass",
        )

        unexpected = _events(case)
        unexpected[-1:-1] = _reviewer_events()
        self.assertEqual(
            smoke.evaluate_transcript(case, _transcript(unexpected))["status"],
            "fail",
        )

        identity_case_events = _events(case)
        identity_case_events[-1:-1] = _reviewer_events()
        reviewer_runtime = next(
            event
            for event in identity_case_events
            if event.get("type") == "subagent.runtime"
            and event.get("task_name") == "fixture-reviewer"
        )
        reviewer_runtime["model"] = "gpt-5.6-luna"
        self.assertEqual(
            smoke.evaluate_transcript(
                case, _transcript(identity_case_events)
            )["status"],
            "fail",
        )

        ordinary = smoke.CASES["explicit-luna"]
        events = _events(ordinary)
        events[-1:-1] = _reviewer_events()
        self.assertEqual(
            smoke.evaluate_transcript(
                ordinary, _transcript(events)
            )["status"],
            "fail",
        )

    def test_tool_output_shape_cannot_impersonate_a_dispatch(self) -> None:
        case = smoke.CASES["explicit-luna"]
        events = _events(case)
        spawn = next(
            event
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "tool_call"
        )
        spawn["item"]["type"] = "function_call_output"
        events = [
            event
            for event in events
            if event.get("type") != "subagent.runtime"
        ]
        result = smoke.evaluate_transcript(case, _transcript(events))
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["passed"])

    def test_tool_call_alias_conflicts_fail(self) -> None:
        case = smoke.CASES["explicit-luna"]
        for label in (
            "name",
            "namespace",
            "deep-namespace-name",
            "deep-namespace-server",
            "payload",
        ):
            events = _events(case)
            spawn = next(
                event
                for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "tool_call"
            )
            if label == "name":
                spawn["item"]["tool_name"] = "other_tool"
            elif label == "namespace":
                spawn["item"]["tool_name"] = "other.spawn_agent"
            elif label == "deep-namespace-name":
                spawn["item"]["name"] = "evil.collaboration.spawn_agent"
            elif label == "deep-namespace-server":
                spawn["item"]["name"] = "spawn_agent"
                spawn["item"]["server"] = "evil.collaboration"
            else:
                spawn["item"]["input"] = {
                    **spawn["item"]["arguments"],
                    "task_name": "different-task",
                }
            with self.subTest(alias=label):
                result = smoke.evaluate_transcript(
                    case, _transcript(events)
                )
                self.assertEqual(result["status"], "fail")

        duplicate = _events(case)
        spawn = next(
            event
            for event in duplicate
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "tool_call"
        )
        spawn["item"]["input"] = dict(spawn["item"]["arguments"])
        spawn["item"]["tool_name"] = "spawn_agent"
        result = smoke.evaluate_transcript(case, _transcript(duplicate))
        self.assertEqual(result["status"], "pass")

    def test_live_command_is_ephemeral_read_only_and_model_implicit(self) -> None:
        command = smoke.build_live_command(
            "codex.exe", Path("C:/fixture")
        )
        joined = " ".join(command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--json", command)
        self.assertIn("--sandbox read-only", joined)
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("-C", command)
        self.assertNotIn("-m", command)
        self.assertNotIn("--model", command)
        self.assertNotIn("model_reasoning_effort", joined)

    def test_live_reports_process_invocation_not_model_call_count(self) -> None:
        case = smoke.CASES["explicit-luna"]
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                smoke._synthetic_transcript(case)
                .replace("offline-fixture", "线程-✓")
                .encode("utf-8")
            ),
            stderr=b"",
        )
        with (
            mock.patch.object(
                smoke.shutil, "which", return_value="codex.exe"
            ),
            mock.patch.object(
                smoke.subprocess, "run", return_value=completed
            ) as run,
            mock.patch.object(
                smoke,
                "evaluate_transcript",
                wraps=smoke.evaluate_transcript,
            ) as evaluate,
        ):
            result = smoke.run_live(case, timeout_seconds=10)
        run.assert_called_once()
        call = run.call_args
        self.assertEqual(call.kwargs["input"], case.prompt.encode("utf-8"))
        self.assertNotEqual(call.kwargs.get("text"), True)
        passed_transcript = evaluate.call_args.args[1]
        self.assertIsInstance(passed_transcript, str)
        self.assertIn("线程-✓", passed_transcript)
        self.assertEqual(result["codex_exec_calls"], 1)
        self.assertEqual(result["model_calls"], "UNKNOWN")
        self.assertEqual(result["status"], "pass")

    def test_live_nonzero_stays_unknown_once_with_stderr_summary(
        self,
    ) -> None:
        case = smoke.CASES["root-plus-luna"]
        stderr = (
            "fatal: 中文✓ provider unavailable " + ("x" * 2048)
        ).encode("utf-8")
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=17,
            stdout=smoke._synthetic_transcript(case),
            stderr=stderr,
        )
        with (
            mock.patch.object(
                smoke.shutil, "which", return_value="codex.exe"
            ),
            mock.patch.object(
                smoke.subprocess, "run", return_value=completed
            ) as run,
        ):
            result = smoke.run_live(case, timeout_seconds=10)
        run.assert_called_once()
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["passed"])
        self.assertEqual(result["codex_exec_calls"], 1)
        self.assertEqual(result["model_calls"], "UNKNOWN")
        self.assertEqual(result["process_returncode"], 17)
        self.assertIn("中文✓", result["stderr_summary"])
        self.assertIn("provider unavailable", result["stderr_summary"])
        self.assertLess(len(result["stderr_summary"]), len(stderr))

    def test_live_stderr_summary_redacts_sensitive_values(self) -> None:
        case = smoke.CASES["root-plus-luna"]
        secrets = (
            "TOKEN_SENTINEL_DO_NOT_LEAK",
            "COOKIE_SENTINEL_DO_NOT_LEAK",
            "PASSWORD_SENTINEL_DO_NOT_LEAK",
            "BEARER_SENTINEL_DO_NOT_LEAK",
        )
        stderr = (
            "token=TOKEN_SENTINEL_DO_NOT_LEAK "
            "Cookie: session=COOKIE_SENTINEL_DO_NOT_LEAK; "
            "refresh=REFRESH_SENTINEL_DO_NOT_LEAK\n"
            "password=PASSWORD_SENTINEL_DO_NOT_LEAK "
            "Authorization: Basic BASIC_SENTINEL_DO_NOT_LEAK\n"
            "Bearer BEARER_SENTINEL_DO_NOT_LEAK "
            "fatal: provider unavailable"
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=stderr
        )
        with (
            mock.patch.object(
                smoke.shutil, "which", return_value="codex.exe"
            ),
            mock.patch.object(
                smoke.subprocess, "run", return_value=completed
            ),
        ):
            result = smoke.run_live(case, timeout_seconds=10)
        public_payload = json.dumps(result, ensure_ascii=False)
        for secret in secrets + (
            "REFRESH_SENTINEL_DO_NOT_LEAK",
            "BASIC_SENTINEL_DO_NOT_LEAK",
        ):
            self.assertNotIn(secret, public_payload)
        self.assertIn("[REDACTED]", result["stderr_summary"])
        self.assertEqual(result["status"], "unknown")

    def test_stderr_summary_redacts_full_cookie_and_auth_headers(
        self,
    ) -> None:
        summary = smoke._public_stderr_summary(
            "Cookie: session=FIRST; refresh=SECOND\n"
            "Authorization: Basic BASIC_CREDENTIAL\n"
            "fatal: provider unavailable"
        )
        self.assertNotIn("FIRST", summary)
        self.assertNotIn("SECOND", summary)
        self.assertNotIn("BASIC_CREDENTIAL", summary)
        self.assertIn("fatal: provider unavailable", summary)

    def test_stderr_summary_redacts_compound_credential_keys(self) -> None:
        secrets = (
            "ACCESS_SENTINEL",
            "CLIENT_SENTINEL",
            "PASSWORD_SENTINEL",
            "REFRESH_SENTINEL",
            "API_KEY_SENTINEL",
        )
        summary = smoke._public_stderr_summary(
            "access_token=ACCESS_SENTINEL "
            "client_secret=CLIENT_SENTINEL "
            "db_password=PASSWORD_SENTINEL "
            "refresh-token=REFRESH_SENTINEL "
            "api_key=API_KEY_SENTINEL fatal: visible"
        )
        for secret in secrets:
            self.assertNotIn(secret, summary)
        self.assertIn("fatal: visible", summary)

    def test_offline_transcript_cli_is_executable(self) -> None:
        case = smoke.CASES["implicit-luna"]
        with tempfile.TemporaryDirectory() as temp:
            transcript = Path(temp) / "events.jsonl"
            transcript.write_text(
                smoke._synthetic_transcript(case), encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--json",
                    "--case",
                    case.name,
                    "--transcript",
                    str(transcript),
                ],
                check=True,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                env=isolated_subprocess_env(),
                timeout=30,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["mode"], "offline-transcript")
        self.assertEqual(result["codex_exec_calls"], 0)
        self.assertEqual(result["model_calls"], 0)

    def test_cli_default_does_not_enter_live_mode(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--json"],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=isolated_subprocess_env(),
            timeout=30,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["mode"], "offline-evaluator-self-test"
        )
        self.assertEqual(result["codex_exec_calls"], 0)
        self.assertEqual(result["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
