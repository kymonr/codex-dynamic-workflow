from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import cli
import ops_cli
import swarm_presets
from runtime.workflow_ir import validate_workflow_ir


def _node(ir: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in ir["nodes"] if node["id"] == node_id)


def _prompt(node: dict[str, Any]) -> str:
    if node["kind"] == "map":
        return node["config"]["template"]["prompt"]
    return node["config"].get("prompt", "")


class SwarmPresetCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workdir = self.root / "does-not-exist"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def render(self, name: str, **overrides: Any) -> dict[str, Any]:
        options = {
            "objective": "Review and improve the bounded system",
            "workdir": str(self.workdir),
        }
        options.update(overrides)
        return swarm_presets.render_preset(name, **options)

    def test_preset_list_is_deterministic_zero_model_and_zero_write(self) -> None:
        first = swarm_presets.list_presets()
        second = swarm_presets.list_presets()
        self.assertEqual(first, second)
        self.assertEqual(first["operation"], "preset-list")
        self.assertEqual(first["model_calls"], 0)
        self.assertEqual(first["writes"], [])
        self.assertEqual(
            [item["name"] for item in first["presets"]],
            ["design-swarm", "repo-sweep", "ultra-review"],
        )
        expected = {
            "design-swarm": 19,
            "repo-sweep": 24,
            "ultra-review": 23,
        }
        for item in first["presets"]:
            self.assertEqual(
                item["projected_agent_claims"],
                expected[item["name"]],
            )
            self.assertEqual(item["default_max_agents"], 24)
            self.assertEqual(item["default_max_concurrency"], 8)
            self.assertEqual(item["maximum_max_concurrency"], 10)
            self.assertTrue(item["human_gate"])

    def test_all_presets_validate_plan_and_stay_within_budget(self) -> None:
        expected = {
            "design-swarm": 19,
            "repo-sweep": 24,
            "ultra-review": 23,
        }
        for name, claims in expected.items():
            with self.subTest(name=name):
                raw = self.render(name)
                normalized = validate_workflow_ir(raw)
                self.assertEqual(
                    normalized["execution"]["unsupported_node_kinds"],
                    [],
                )
                plan = ops_cli._plan_preview(raw)
                self.assertEqual(plan["model_calls"], 0)
                self.assertEqual(plan["writes"], [])
                self.assertFalse(plan["workdir_preflight"]["performed"])
                self.assertEqual(
                    plan["agent_claim_projection"]["total_upper_bound"],
                    claims,
                )
                self.assertTrue(
                    plan["agent_claim_projection"]["upper_bound_within_budget"]
                )
                self.assertFalse(self.workdir.exists())
                self.assertNotIn(
                    "loop",
                    {node["kind"] for node in normalized["nodes"]},
                )

    def test_design_swarm_topology_and_claims(self) -> None:
        raw = self.render("design-swarm")
        self.assertEqual(
            [node["id"] for node in raw["nodes"]],
            [
                "brief-analysis",
                "perspective-planner",
                "design-options",
                "verify-designs",
                "synthesize-design",
                "review-gate",
                "choose-gate-outcome",
                "record-accepted",
                "record-rejected",
                "finalize-accepted",
                "finalize-rejected",
            ],
        )
        self.assertEqual(_node(raw, "design-options")["config"]["item_limit"], 6)
        self.assertEqual(
            _node(raw, "verify-designs")["config"]["target"],
            "design-options",
        )
        self.assertEqual(_node(raw, "synthesize-design")["config"]["profile"], "sol")
        self.assertEqual(
            _node(raw, "review-gate")["config"]["options"],
            ["approve", "reject"],
        )

    def test_ultra_review_topology_and_selected_report_join(self) -> None:
        raw = self.render("ultra-review")
        scope_schema = _node(raw, "scope-discovery")["config"]["output_schema"]
        self.assertEqual(scope_schema["type"], "array")
        self.assertEqual(scope_schema["minItems"], 7)
        self.assertEqual(scope_schema["maxItems"], 7)
        scope_prompt = _prompt(_node(raw, "scope-discovery"))
        self.assertIn("performance and test/CI evidence", scope_prompt)
        self.assertEqual(_node(raw, "review-findings")["config"]["item_limit"], 7)
        self.assertEqual(
            _node(raw, "verify-findings")["config"]["target"],
            "review-findings",
        )
        self.assertEqual(_node(raw, "cross-check-findings")["config"]["profile"], "luna")
        self.assertEqual(_node(raw, "synthesize-review")["config"]["profile"], "sol")
        self.assertEqual(_node(raw, "review-gate")["dependency_policy"], "join")
        self.assertEqual(
            _node(raw, "review-gate")["depends_on"],
            ["prepare-clean-candidate", "prepare-blocker-report"],
        )
        for record_id in ("record-accepted", "record-rejected"):
            record = _node(raw, record_id)
            self.assertEqual(
                record["depends_on"],
                ["choose-gate-outcome", "review-gate", "synthesize-review"],
            )
            self.assertIn("{{result:review-gate}}", _prompt(record))
            self.assertIn("{{result:synthesize-review}}", _prompt(record))
            self.assertNotIn("prepare-clean-candidate", _prompt(record))
            self.assertNotIn("prepare-blocker-report", _prompt(record))

    def test_repo_sweep_uses_exact_twenty_four_claim_upper_bound(self) -> None:
        raw = self.render("repo-sweep")
        plan = ops_cli._plan_preview(raw)
        projection = plan["agent_claim_projection"]
        self.assertEqual(projection["static_agent_claims"], 4)
        self.assertEqual(projection["map_child_upper_bound"], 10)
        self.assertEqual(projection["verify_child_upper_bound"], 10)
        self.assertEqual(projection["total_upper_bound"], 24)
        self.assertEqual(_node(raw, "audit-modules")["config"]["item_limit"], 10)
        ids = {node["id"] for node in raw["nodes"]}
        self.assertNotIn("finalize-accepted", ids)
        self.assertNotIn("finalize-rejected", ids)

    def test_budget_and_concurrency_bounds_fail_closed(self) -> None:
        for name, too_small in (
            ("design-swarm", 18),
            ("ultra-review", 22),
            ("repo-sweep", 23),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    swarm_presets.PresetError,
                    "projected claims exceed max_agents",
                ):
                    self.render(name, max_agents=too_small)
        for invalid in (0, 11):
            with self.subTest(max_concurrency=invalid):
                with self.assertRaises(swarm_presets.PresetError):
                    self.render("design-swarm", max_concurrency=invalid)

    def test_objective_placeholder_text_is_inert_in_prompts(self) -> None:
        objective = 'Design {{result:evil}} and {literal} "quoted"\nline two'
        raw = self.render("design-swarm", objective=objective)
        self.assertEqual(raw["objective"], objective)
        prompts = "\n".join(_prompt(node) for node in raw["nodes"])
        self.assertNotIn("{{result:evil}}", prompts)
        self.assertIn(r"\u007b\u007bresult:evil\u007d\u007d", prompts)
        self.assertNotIn(str(self.workdir), prompts)

    def test_preset_output_is_deterministic_and_declared_not_resolved(self) -> None:
        first = self.render("design-swarm")
        second = self.render("design-swarm")
        self.assertEqual(first, second)
        self.assertNotIn("execution", first)
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )

    def test_required_placeholder_contract_fails_closed(self) -> None:
        raw = self.render("design-swarm")
        record = _node(raw, "record-rejected")
        record["config"]["prompt"] = record["config"]["prompt"].replace(
            "{{result:review-gate}}",
            "missing gate input",
        )
        normalized = validate_workflow_ir(raw)
        with self.assertRaisesRegex(
            swarm_presets.PresetError,
            "missing placeholders",
        ):
            swarm_presets._validate_preset_contract(
                normalized,
                swarm_presets.PRESETS["design-swarm"],
            )

    def test_cli_preset_ir_emits_plan_compatible_ir(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = swarm_presets.main(
                [
                    "preset-ir",
                    "--preset",
                    "design-swarm",
                    "--objective",
                    "Design a safe bounded service",
                    "--workdir",
                    str(self.workdir),
                    "--max-agents",
                    "24",
                    "--max-concurrency",
                    "8",
                ]
            )
        self.assertEqual(code, 0)
        raw = json.loads(output.getvalue())
        self.assertEqual(raw["name"], "design-swarm")
        self.assertNotIn("execution", raw)
        self.assertEqual(
            ops_cli._plan_preview(raw)["agent_claim_projection"]["total_upper_bound"],
            19,
        )
        self.assertFalse(self.workdir.exists())

    def test_portable_cli_routes_preset_commands(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(["preset-list"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["operation"], "preset-list")
        self.assertEqual(len(result["presets"]), 3)

    def test_invalid_text_inputs_are_rejected(self) -> None:
        with self.assertRaises(swarm_presets.PresetError):
            swarm_presets.render_preset(
                "design-swarm",
                objective=" ",
                workdir=str(self.workdir),
            )
        with self.assertRaises(swarm_presets.PresetError):
            swarm_presets.render_preset(
                "design-swarm",
                objective="valid",
                workdir="\x00",
            )
        with self.assertRaises(swarm_presets.PresetError):
            swarm_presets.render_preset(
                "design-swarm",
                objective="x" * (swarm_presets.MAX_OBJECTIVE_CHARS + 1),
                workdir=str(self.workdir),
            )


if __name__ == "__main__":
    unittest.main()
