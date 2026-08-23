from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import swarm_presets
from runtime.workflow_ir import validate_workflow_ir


def _node(ir: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in ir["nodes"] if node["id"] == node_id)


def _enum(ir: dict[str, Any], node_id: str, field: str) -> list[str]:
    return _node(ir, node_id)["config"]["output_schema"]["properties"][field][
        "enum"
    ]


class SwarmBranchContractTests(unittest.TestCase):
    def render(self, name: str) -> dict[str, Any]:
        return swarm_presets.render_preset(
            name,
            objective="Exercise exact branch outcome contracts",
            workdir="/bounded/work",
        )

    def test_records_and_finalizers_use_exact_branch_enums(self) -> None:
        for preset in ("design-swarm", "ultra-review", "repo-sweep"):
            with self.subTest(preset=preset):
                ir = self.render(preset)
                self.assertEqual(_enum(ir, "record-accepted", "decision"), ["approve"])
                self.assertEqual(_enum(ir, "record-rejected", "decision"), ["reject"])
                ids = {node["id"] for node in ir["nodes"]}
                if "finalize-accepted" in ids:
                    self.assertEqual(
                        _enum(ir, "finalize-accepted", "decision"), ["approve"]
                    )
                    self.assertEqual(
                        _enum(ir, "finalize-accepted", "status"), ["accepted"]
                    )
                    self.assertEqual(
                        _enum(ir, "finalize-rejected", "decision"), ["reject"]
                    )
                    self.assertEqual(
                        _enum(ir, "finalize-rejected", "status"), ["rejected"]
                    )

    def test_branch_contract_drift_fails_closed(self) -> None:
        ir = self.render("design-swarm")
        accepted = _node(ir, "record-accepted")
        accepted["config"]["output_schema"]["properties"]["decision"]["enum"] = [
            "approve",
            "reject",
        ]
        normalized = validate_workflow_ir(ir)
        with self.assertRaisesRegex(
            swarm_presets.PresetError,
            "decision schema must be exactly",
        ):
            swarm_presets._validate_preset_contract(
                normalized,
                swarm_presets.PRESETS["design-swarm"],
            )


if __name__ == "__main__":
    unittest.main()
