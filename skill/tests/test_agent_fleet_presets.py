from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import fleet_contract
import fleet_presets


def package(*, preset: str = "adversarial-review", count: int = 6):
    raw = {
        "version": 1,
        "name": "fleet-plan",
        "preset": preset,
        "agent_count": count,
        "objective": "Review the candidate.",
        "acceptance_criteria": ["Findings are evidence-backed."],
        "scope": ["Frozen candidate"],
        "exclusions": [],
        "candidate": {
            "repository_full_name": "owner/repo",
            "expected_head_sha": "a" * 40,
            "changed_files": [],
        },
        "risk_tags": [],
        "verification": {"required_ids": [], "commands": []},
        "limits": {
            "max_patch_bytes": 524288,
            "max_untracked_file_bytes": 131072,
            "max_candidate_bytes": 1048576,
            "max_agent_output_bytes": 524288,
            "max_agent_log_bytes": 1048576,
        },
    }
    return fleet_contract.validate_package(raw)


class FleetPresetTests(unittest.TestCase):
    def test_phase_allocation_is_deterministic_for_every_size(self) -> None:
        expected = {
            4: (4, 0, 0),
            5: (4, 1, 0),
            6: (4, 1, 1),
            7: (5, 1, 1),
            8: (6, 1, 1),
            9: (6, 2, 1),
            10: (7, 2, 1),
            11: (8, 2, 1),
            12: (8, 2, 2),
        }
        for count, values in expected.items():
            with self.subTest(count=count):
                phases = fleet_presets.phase_counts(count)
                self.assertEqual(
                    (phases["discovery"], phases["challenge"], phases["reproduction"]),
                    values,
                )

    def test_all_presets_produce_unique_fresh_luna_agents(self) -> None:
        for preset in sorted(fleet_contract.PRESETS):
            for count in (4, 6, 12):
                with self.subTest(preset=preset, count=count):
                    schedule = fleet_presets.build_schedule(package(preset=preset, count=count))
                    self.assertEqual(len(schedule["agents"]), count)
                    self.assertEqual(
                        len({item["agent_id"] for item in schedule["agents"]}), count
                    )
                    self.assertEqual(
                        len({item["role_id"] for item in schedule["agents"]}), count
                    )
                    for agent in schedule["agents"]:
                        self.assertEqual(agent["route"]["role"], "luna")
                        self.assertEqual(agent["route"]["model"], "gpt-5.6-luna")
                        self.assertEqual(agent["route"]["effort"], "max")
                        self.assertEqual(agent["route"]["tier"], "fast")
                        self.assertEqual(agent["route"]["sandbox"], "read-only")
                        self.assertTrue(agent["route"]["fresh"])
                        self.assertEqual(agent["route"]["nested_agents"], 0)

    def test_schedule_digest_changes_with_preset_or_size(self) -> None:
        first = fleet_presets.build_schedule(package())
        same = fleet_presets.build_schedule(package())
        other_size = fleet_presets.build_schedule(package(count=7))
        other_preset = fleet_presets.build_schedule(package(preset="test-matrix"))
        self.assertEqual(first, same)
        self.assertNotEqual(first["schedule_digest"], other_size["schedule_digest"])
        self.assertNotEqual(first["schedule_digest"], other_preset["schedule_digest"])

    def test_four_agents_are_diverse_discovery_not_duplicate_prompts(self) -> None:
        schedule = fleet_presets.build_schedule(package(count=4))
        agents = schedule["agents"]
        self.assertEqual({item["phase"] for item in agents}, {"discovery"})
        self.assertEqual(len({item["focus"] for item in agents}), 4)
        self.assertEqual(
            [item["role_id"] for item in agents],
            [
                "correctness-hunter",
                "regression-hunter",
                "test-evidence-auditor",
                "devils-advocate",
            ],
        )


if __name__ == "__main__":
    unittest.main()
