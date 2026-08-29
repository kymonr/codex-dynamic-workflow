from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from typing import Any, Awaitable, Callable

import sys

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

import agent_fleet
import cli
import fleet_contract
import ops_cli
import runtime.control_flow as control_flow
from runtime.control_flow import TrustedControlFlowScheduler
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import (
    WorkflowIRValidationError,
    project_agent_claims,
    validate_workflow_ir,
)


AgentExecutor = Callable[
    [dict[str, Any], dict[str, Any], dict[str, Any] | None],
    Awaitable[dict[str, Any]],
]


def _node(ir: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in ir["nodes"] if node["id"] == node_id)


def _success(task_id: str, output: Any) -> dict[str, Any]:
    return {
        "id": task_id,
        "status": "succeeded",
        "error": None,
        "output": output,
        "output_artifact": None,
        "attempt_count": 1,
        "retry": 0,
        "upgrade": None,
    }


class AgentFleetCompilerTests(unittest.TestCase):
    def render(self, preset: str = "adversarial-review", **overrides: Any) -> dict[str, Any]:
        options = {
            "objective": "Review the bounded candidate",
            "workdir": "D:/bounded/repository",
            "subject_id": "sha256:candidate",
        }
        options.update(overrides)
        return agent_fleet.render_fleet(preset, **options)

    def test_list_and_all_presets_are_deterministic(self) -> None:
        first = agent_fleet.list_fleets()
        self.assertEqual(first, agent_fleet.list_fleets())
        self.assertEqual(first["operation"], "fleet-list")
        self.assertEqual(first["model_calls"], 0)
        self.assertEqual(first["writes"], [])
        self.assertEqual(
            [item["name"] for item in first["presets"]],
            [
                "adversarial-review",
                "architecture-council",
                "competing-hypotheses",
                "repository-audit",
                "test-matrix",
            ],
        )

    def test_every_size_uses_exact_luna_fleet_plus_optional_sol(self) -> None:
        for preset in agent_fleet.PRESETS:
            for size in (4, 6, 12):
                with self.subTest(preset=preset, size=size):
                    raw = self.render(preset, fleet_size=size)
                    ir = validate_workflow_ir(raw)
                    members = _node(ir, "aggregate-fleet")["config"]["members"]
                    self.assertEqual(len(members), size)
                    self.assertEqual(
                        sum(
                            node["kind"] == "agent"
                            and node["config"]["profile"] == "luna"
                            for node in ir["nodes"]
                        ),
                        size,
                    )
                    self.assertEqual(
                        project_agent_claims(ir)["total_upper_bound"],
                        size + 1,
                    )

    def test_conditional_and_always_sol_topologies_are_distinct(self) -> None:
        conditional = self.render("adversarial-review", fleet_size=8)
        choose = _node(conditional, "choose-sol")
        self.assertEqual(choose["config"]["then"], ["sol-arbitration"])
        self.assertEqual(choose["config"]["else"], [])
        self.assertEqual(
            _node(conditional, "sol-arbitration")["depends_on"],
            ["choose-sol", "aggregate-fleet"],
        )
        always = self.render("architecture-council", fleet_size=8)
        self.assertNotIn("choose-sol", {node["id"] for node in always["nodes"]})
        self.assertEqual(
            _node(always, "sol-arbitration")["depends_on"],
            ["aggregate-fleet"],
        )

    def test_objective_is_brace_neutral_and_challenges_consume_discovery(self) -> None:
        objective = "Review {{result:evil}} and {literal}"
        raw = self.render(objective=objective, fleet_size=5)
        self.assertEqual(raw["objective"], objective)
        discovery = [
            node for node in raw["nodes"] if node["id"].startswith("discover-")
        ]
        challenge = [
            node for node in raw["nodes"] if node["id"].startswith("challenge-")
        ]
        self.assertNotIn(
            "{{result:evil}}",
            "\n".join(node["config"]["prompt"] for node in discovery),
        )
        expected = [node["id"] for node in discovery]
        for node in challenge:
            self.assertEqual(node["depends_on"], expected)
            for source in expected:
                self.assertIn(f"{{{{result:{source}}}}}", node["config"]["prompt"])

    def test_subject_identity_and_fleet_member_topology_fail_closed(self) -> None:
        with self.assertRaises(agent_fleet.AgentFleetError):
            self.render(subject_id="{{result:evil}}")

        raw = self.render(fleet_size=6)
        discovery = next(
            node for node in raw["nodes"] if node["id"].startswith("discover-")
        )
        discovery["config"]["profile"] = "sol"
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "fleet member must use Luna"
        ):
            validate_workflow_ir(raw)

        raw = self.render(fleet_size=6)
        challenge = next(
            node for node in raw["nodes"] if node["id"].startswith("challenge-")
        )
        challenge["depends_on"] = []
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "fleet member dependencies are invalid"
        ):
            validate_workflow_ir(raw)

        raw = self.render(fleet_size=6)
        discovery = next(
            node for node in raw["nodes"] if node["id"].startswith("discover-")
        )
        discovery["config"]["output_schema"] = {"type": "object"}
        with self.assertRaisesRegex(
            WorkflowIRValidationError, "fleet member output schema is invalid"
        ):
            validate_workflow_ir(raw)

    def test_cli_emits_plan_compatible_ir(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = agent_fleet.main(
                [
                    "fleet-ir",
                    "--preset",
                    "adversarial-review",
                    "--objective",
                    "Review a bounded candidate",
                    "--workdir",
                    "D:/bounded/repository",
                    "--subject-id",
                    "sha256:cli",
                    "--fleet-size",
                    "8",
                ]
            )
        self.assertEqual(code, 0)
        raw = json.loads(output.getvalue())
        plan = ops_cli._plan_preview(raw)
        self.assertEqual(plan["model_calls"], 0)
        self.assertEqual(plan["writes"], [])
        fleet = next(node for node in plan["nodes"] if node["id"] == "aggregate-fleet")
        self.assertEqual(fleet["fleet_members"], 8)
        self.assertEqual(plan["agent_claim_projection"]["total_upper_bound"], 9)

    def test_portable_cli_routes_fleet_commands(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(["fleet-list"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["operation"], "fleet-list")
        self.assertEqual(len(result["presets"]), 5)

    def test_invalid_bounds_fail_closed(self) -> None:
        for size in (3, 13, True):
            with self.subTest(size=size):
                with self.assertRaises(agent_fleet.AgentFleetError):
                    self.render(fleet_size=size)
        with self.assertRaises(agent_fleet.AgentFleetError):
            self.render(fleet_size=4, max_concurrency=5)
        with self.assertRaises(agent_fleet.AgentFleetError):
            self.render(risk_level="invented")


def _aggregate_config(
    *,
    risk: str = "ordinary",
    sol_policy: str = "conditional",
) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "mode": "adversarial_review",
        "subject_id": "sha256:candidate",
        "risk_level": risk,
        "sol_policy": sol_policy,
        "selector_node": "choose-sol" if sol_policy == "conditional" else None,
        "arbiter_node": "sol-arbitration",
        "members": [
            {"node_id": "discover-a", "role_id": "correctness", "stage": "discovery"},
            {"node_id": "discover-b", "role_id": "regression", "stage": "discovery"},
            {"node_id": "discover-c", "role_id": "tests", "stage": "discovery"},
            {"node_id": "challenge-a", "role_id": "devils-advocate", "stage": "challenge"},
        ],
    }


def _discovery(
    role_id: str,
    *,
    verdict: str = "accept",
    claims: list[dict[str, Any]] | None = None,
    unknown: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_version": 1,
        "subject_id": "sha256:candidate",
        "role_id": role_id,
        "stage": "discovery",
        "verdict": verdict,
        "summary": f"{role_id} summary",
        "claims": claims or [],
        "unknown": unknown or [],
        "effects": [],
    }


def _challenge(
    *,
    role_id: str = "devils-advocate",
    verdict: str = "accept",
    assessments: list[dict[str, Any]] | None = None,
    new_claims: list[dict[str, Any]] | None = None,
    unknown: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_version": 1,
        "subject_id": "sha256:candidate",
        "role_id": role_id,
        "stage": "challenge",
        "verdict": verdict,
        "summary": "challenge summary",
        "assessments": assessments or [],
        "new_claims": new_claims or [],
        "unknown": unknown or [],
        "effects": [],
    }


def _claim(priority: str, statement: str) -> dict[str, Any]:
    return {
        "kind": "correctness",
        "priority": priority,
        "statement": statement,
        "evidence": ["module.py:10"],
    }


def _clean_outputs() -> dict[str, Any]:
    return {
        "discover-a": _discovery("correctness"),
        "discover-b": _discovery("regression"),
        "discover-c": _discovery("tests"),
        "challenge-a": _challenge(),
    }


class FleetAggregateTests(unittest.TestCase):
    def test_clean_unanimous_panel_skips_sol(self) -> None:
        aggregate = fleet_contract.aggregate_fleet_records(
            _aggregate_config(),
            _clean_outputs(),
        )
        self.assertTrue(aggregate["clean"])
        self.assertFalse(aggregate["requires_sol"])
        self.assertEqual(aggregate["escalation_reasons"], [])
        self.assertTrue(aggregate["aggregate_digest"].startswith("sha256:"))

    def test_confirmed_blocker_requires_sol(self) -> None:
        outputs = _clean_outputs()
        outputs["discover-a"] = _discovery(
            "correctness",
            verdict="escalate",
            claims=[_claim("P1", "state can be corrupted")],
        )
        outputs["challenge-a"] = _challenge(
            verdict="escalate",
            assessments=[
                {
                    "source_node": "discover-a",
                    "claim_index": 0,
                    "outcome": "confirmed",
                    "summary": "reproduced",
                    "evidence": ["test_repro.py:20"],
                }
            ],
        )
        aggregate = fleet_contract.aggregate_fleet_records(
            _aggregate_config(), outputs
        )
        self.assertFalse(aggregate["clean"])
        self.assertTrue(aggregate["requires_sol"])
        self.assertIn("surviving_P1_or_P2_claim", aggregate["escalation_reasons"])
        self.assertEqual(aggregate["claim_counts"]["P1"], 1)

    def test_refuted_blocker_can_skip_sol(self) -> None:
        outputs = _clean_outputs()
        outputs["discover-a"] = _discovery(
            "correctness",
            verdict="escalate",
            claims=[_claim("P2", "suspected regression")],
        )
        outputs["challenge-a"] = _challenge(
            assessments=[
                {
                    "source_node": "discover-a",
                    "claim_index": 0,
                    "outcome": "refuted",
                    "summary": "caller preserves the invariant",
                    "evidence": ["caller.py:30"],
                }
            ]
        )
        aggregate = fleet_contract.aggregate_fleet_records(
            _aggregate_config(), outputs
        )
        self.assertTrue(aggregate["clean"])
        self.assertFalse(aggregate["requires_sol"])
        self.assertEqual(aggregate["claim_counts"]["refuted"], 1)

    def test_high_risk_and_disagreement_require_sol(self) -> None:
        high = fleet_contract.aggregate_fleet_records(
            _aggregate_config(risk="high"),
            _clean_outputs(),
        )
        self.assertTrue(high["requires_sol"])
        self.assertIn("high_risk_subject", high["escalation_reasons"])
        always = fleet_contract.aggregate_fleet_records(
            _aggregate_config(sol_policy="always"),
            _clean_outputs(),
        )
        self.assertTrue(always["requires_sol"])

    def test_unknown_and_disputed_evidence_require_sol(self) -> None:
        unknown_outputs = _clean_outputs()
        unknown_outputs["discover-b"] = _discovery(
            "regression",
            verdict="unknown",
            unknown=["caller behavior cannot be established"],
        )
        unknown = fleet_contract.aggregate_fleet_records(
            _aggregate_config(), unknown_outputs
        )
        self.assertTrue(unknown["requires_sol"])
        self.assertIn("unknown_evidence", unknown["escalation_reasons"])

        config = _aggregate_config()
        config["members"].append(
            {
                "node_id": "challenge-b",
                "role_id": "finding-challenger",
                "stage": "challenge",
            }
        )
        disputed_outputs = _clean_outputs()
        disputed_outputs["discover-a"] = _discovery(
            "correctness",
            verdict="escalate",
            claims=[_claim("P2", "ambiguous state transition")],
        )
        disputed_outputs["challenge-a"] = _challenge(
            verdict="escalate",
            assessments=[
                {
                    "source_node": "discover-a",
                    "claim_index": 0,
                    "outcome": "confirmed",
                    "summary": "first reproduction confirms it",
                    "evidence": ["test_state.py:20"],
                }
            ],
        )
        disputed_outputs["challenge-b"] = _challenge(
            role_id="finding-challenger",
            assessments=[
                {
                    "source_node": "discover-a",
                    "claim_index": 0,
                    "outcome": "refuted",
                    "summary": "alternate caller preserves the invariant",
                    "evidence": ["caller.py:40"],
                }
            ],
        )
        disputed = fleet_contract.aggregate_fleet_records(
            config, disputed_outputs
        )
        self.assertTrue(disputed["requires_sol"])
        self.assertIn("assessment_disagreement", disputed["escalation_reasons"])
        self.assertEqual(disputed["claim_counts"]["disputed"], 1)

    def test_effects_and_bad_claim_references_fail_closed(self) -> None:
        outputs = _clean_outputs()
        outputs["discover-a"]["effects"] = ["wrote file"]
        with self.assertRaises(fleet_contract.FleetContractError):
            fleet_contract.aggregate_fleet_records(_aggregate_config(), outputs)
        outputs = _clean_outputs()
        outputs["challenge-a"]["assessments"] = [
            {
                "source_node": "discover-a",
                "claim_index": 99,
                "outcome": "confirmed",
                "summary": "invalid reference",
                "evidence": ["none"],
            }
        ]
        with self.assertRaises(fleet_contract.FleetContractError):
            fleet_contract.aggregate_fleet_records(_aggregate_config(), outputs)


class AgentFleetRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workdir = self.root / "repo"
        self.workdir.mkdir()
        self.limits = RuntimeLimits.from_mapping(agent_fleet.DEFAULT_LIMITS)

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    def executor(
        self,
        ir: dict[str, Any],
        calls: list[str],
        *,
        blocker: bool,
    ) -> AgentExecutor:
        aggregate = _node(ir, "aggregate-fleet")
        members = {item["node_id"]: item for item in aggregate["config"]["members"]}
        discovery_nodes = [
            item["node_id"] for item in aggregate["config"]["members"]
            if item["stage"] == "discovery"
        ]
        subject_id = aggregate["config"]["subject_id"]

        async def execute(
            task: dict[str, Any],
            results: dict[str, Any],
            prior: dict[str, Any] | None,
        ) -> dict[str, Any]:
            task_id = task["id"]
            calls.append(task_id)
            if task_id == "sol-arbitration":
                return _success(
                    task_id,
                    {
                        "record_version": 1,
                        "subject_id": subject_id,
                        "decision": "revise",
                        "summary": "Sol confirmed the blocker",
                        "accepted_claims": ["state corruption"],
                        "rejected_claims": [],
                        "unknown": [],
                        "next_actions": ["fix the state transition"],
                        "effects": [],
                    },
                )
            member = members[task_id]
            if member["stage"] == "discovery":
                is_blocker = blocker and task_id == discovery_nodes[0]
                output = {
                    "record_version": 1,
                    "subject_id": subject_id,
                    "role_id": member["role_id"],
                    "stage": "discovery",
                    "verdict": "escalate" if is_blocker else "accept",
                    "summary": "discovery result",
                    "claims": [
                        {
                            "kind": "correctness",
                            "priority": "P1",
                            "statement": "state corruption",
                            "evidence": ["state.py:10"],
                        }
                    ] if is_blocker else [],
                    "unknown": [],
                    "effects": [],
                }
                return _success(task_id, output)
            assessments = []
            if blocker:
                assessments = [
                    {
                        "source_node": discovery_nodes[0],
                        "claim_index": 0,
                        "outcome": "confirmed",
                        "summary": "independent reproduction",
                        "evidence": ["test_state.py:20"],
                    }
                ]
            output = {
                "record_version": 1,
                "subject_id": subject_id,
                "role_id": member["role_id"],
                "stage": "challenge",
                "verdict": "escalate" if blocker else "accept",
                "summary": "challenge result",
                "assessments": assessments,
                "new_claims": [],
                "unknown": [],
                "effects": [],
            }
            return _success(task_id, output)

        return execute

    async def run_fleet(self, *, blocker: bool) -> tuple[dict[str, Any], list[str]]:
        raw = agent_fleet.render_fleet(
            "adversarial-review",
            objective="Review one bounded candidate",
            workdir=str(self.workdir),
            subject_id="sha256:runtime",
            fleet_size=4,
        )
        ir = validate_workflow_ir(raw)
        calls: list[str] = []
        scheduler = TrustedControlFlowScheduler(
            ir,
            self.root / ("blocked" if blocker else "clean"),
            execute_agent=self.executor(ir, calls, blocker=blocker),
            limits=self.limits,
        )
        return await scheduler.run(resume=False), calls

    async def test_clean_fleet_skips_sol_deterministically(self) -> None:
        summary, calls = await self.run_fleet(blocker=False)
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(summary["claimed_agent_count"], 4)
        self.assertEqual(states["aggregate-fleet"], "succeeded")
        self.assertEqual(states["choose-sol"], "succeeded")
        self.assertEqual(states["sol-arbitration"], "skipped")
        self.assertNotIn("sol-arbitration", calls)
        aggregate = next(
            node["output"] for node in summary["nodes"]
            if node["id"] == "aggregate-fleet"
        )
        self.assertFalse(aggregate["requires_sol"])

    async def test_invalid_challenge_reference_fails_before_sol(self) -> None:
        raw = agent_fleet.render_fleet(
            "adversarial-review",
            objective="Review one bounded candidate",
            workdir=str(self.workdir),
            subject_id="sha256:invalid-reference",
            fleet_size=4,
        )
        ir = validate_workflow_ir(raw)
        calls: list[str] = []
        base = self.executor(ir, calls, blocker=False)
        aggregate = _node(ir, "aggregate-fleet")
        members = {
            item["node_id"]: item for item in aggregate["config"]["members"]
        }
        discovery_id = next(
            item["node_id"]
            for item in aggregate["config"]["members"]
            if item["stage"] == "discovery"
        )

        async def execute(
            task: dict[str, Any],
            results: dict[str, Any],
            prior: dict[str, Any] | None,
        ) -> dict[str, Any]:
            member = members.get(task["id"])
            if member is not None and member["stage"] == "challenge":
                calls.append(task["id"])
                return _success(
                    task["id"],
                    {
                        "record_version": 1,
                        "subject_id": aggregate["config"]["subject_id"],
                        "role_id": member["role_id"],
                        "stage": "challenge",
                        "verdict": "accept",
                        "summary": "malformed semantic reference",
                        "assessments": [
                            {
                                "source_node": discovery_id,
                                "claim_index": 99,
                                "outcome": "confirmed",
                                "summary": "references a nonexistent claim",
                                "evidence": ["none"],
                            }
                        ],
                        "new_claims": [],
                        "unknown": [],
                        "effects": [],
                    },
                )
            return await base(task, results, prior)

        scheduler = TrustedControlFlowScheduler(
            ir,
            self.root / "invalid-reference",
            execute_agent=execute,
            limits=self.limits,
        )
        summary = await scheduler.run(resume=False)
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertEqual(states["aggregate-fleet"], "failed")
        self.assertEqual(states["choose-sol"], "blocked")
        self.assertEqual(states["sol-arbitration"], "blocked")
        self.assertNotIn("sol-arbitration", calls)

    async def test_completed_fleet_resume_recomputes_without_replay(self) -> None:
        raw = agent_fleet.render_fleet(
            "adversarial-review",
            objective="Review one bounded candidate",
            workdir=str(self.workdir),
            subject_id="sha256:resume",
            fleet_size=4,
        )
        ir = validate_workflow_ir(raw)
        calls: list[str] = []
        run_dir = self.root / "resume"
        first = TrustedControlFlowScheduler(
            ir,
            run_dir,
            execute_agent=self.executor(ir, calls, blocker=False),
            limits=self.limits,
        )
        first_summary = await first.run(resume=False)
        self.assertTrue(first_summary["all_succeeded"])
        replay_calls: list[str] = []

        async def refuse_replay(
            task: dict[str, Any],
            results: dict[str, Any],
            prior: dict[str, Any] | None,
        ) -> dict[str, Any]:
            replay_calls.append(task["id"])
            raise AssertionError("completed Fleet must not replay agents")

        resumed = TrustedControlFlowScheduler(
            ir,
            run_dir,
            execute_agent=refuse_replay,
            limits=self.limits,
        )
        with mock.patch.object(
            control_flow,
            "aggregate_fleet_records",
            wraps=fleet_contract.aggregate_fleet_records,
        ) as recompute:
            resumed_summary = await resumed.run(resume=True)
        self.assertTrue(resumed_summary["all_succeeded"])
        self.assertEqual(replay_calls, [])
        self.assertGreaterEqual(recompute.call_count, 1)
        self.assertEqual(
            {node["id"]: node["status"] for node in resumed_summary["nodes"]},
            {node["id"]: node["status"] for node in first_summary["nodes"]},
        )

    async def test_always_sol_preset_runs_one_arbiter_on_clean_evidence(self) -> None:
        raw = agent_fleet.render_fleet(
            "architecture-council",
            objective="Compare bounded architecture options",
            workdir=str(self.workdir),
            subject_id="sha256:architecture",
            fleet_size=4,
        )
        ir = validate_workflow_ir(raw)
        calls: list[str] = []
        scheduler = TrustedControlFlowScheduler(
            ir,
            self.root / "always-sol",
            execute_agent=self.executor(ir, calls, blocker=False),
            limits=self.limits,
        )
        summary = await scheduler.run(resume=False)
        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(calls.count("sol-arbitration"), 1)
        self.assertEqual(summary["claimed_agent_count"], 5)

    async def test_blocker_fleet_invokes_one_sol_arbiter(self) -> None:
        summary, calls = await self.run_fleet(blocker=True)
        states = {node["id"]: node["status"] for node in summary["nodes"]}
        self.assertTrue(summary["all_succeeded"])
        self.assertEqual(summary["claimed_agent_count"], 5)
        self.assertEqual(states["sol-arbitration"], "succeeded")
        self.assertEqual(calls.count("sol-arbitration"), 1)
        aggregate = next(
            node["output"] for node in summary["nodes"]
            if node["id"] == "aggregate-fleet"
        )
        self.assertTrue(aggregate["requires_sol"])


if __name__ == "__main__":
    unittest.main()
