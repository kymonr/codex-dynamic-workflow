from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Awaitable, Callable

import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import swarm_presets
from runtime.control_flow import TrustedControlFlowScheduler
from runtime.human_gate import HumanGateStore
from runtime.limits import RuntimeLimits
from runtime.workflow_ir import validate_workflow_ir


AgentExecutor = Callable[
    [dict[str, Any], dict[str, Any], dict[str, Any] | None],
    Awaitable[dict[str, Any]],
]


def _states(summary: dict[str, Any]) -> dict[str, str]:
    return {node["id"]: node["status"] for node in summary["nodes"]}


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


class SwarmPresetRuntimeE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workdir = self.base / "bounded-work"
        self.workdir.mkdir()
        self.limits = RuntimeLimits.from_mapping(swarm_presets.DEFAULT_LIMITS)

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    def executor(self, calls: list[str]) -> AgentExecutor:
        async def execute(
            task: dict[str, Any],
            results: dict[str, Any],
            prior_entry: dict[str, Any] | None,
        ) -> dict[str, Any]:
            task_id = task["id"]
            calls.append(task_id)

            if task_id == "brief-analysis":
                output = {
                    "goal": "bounded design",
                    "constraints": ["read only"],
                    "success_criteria": ["verified"],
                    "open_questions": [],
                }
            elif task_id == "perspective-planner":
                output = [
                    {
                        "perspective": f"perspective-{index}",
                        "focus": f"focus-{index}",
                        "questions": [f"question-{index}"],
                    }
                    for index in range(6)
                ]
            elif task_id.startswith("design-options_map_"):
                output = {
                    "perspective": task_id,
                    "proposal": "proposal",
                    "assumptions": [],
                    "risks": [],
                    "evidence": ["bounded evidence"],
                    "open_questions": [],
                }
            elif task_id.startswith("verify-designs_verify_"):
                output = {
                    "verdict": "accept",
                    "summary": "verified design",
                    "evidence": ["bounded evidence"],
                }
            elif task_id == "synthesize-design":
                output = {
                    "verdict": "clean_candidate",
                    "summary": "synthesized design",
                    "recommended_design": "recommended",
                    "agreements": ["agreement"],
                    "disagreements": [],
                    "risks": [],
                    "next_actions": ["review"],
                }
            elif task_id == "scope-discovery":
                output = [
                    {
                        "dimension": f"dimension-{index}",
                        "scope": f"scope-{index}",
                        "questions": [f"question-{index}"],
                    }
                    for index in range(7)
                ]
            elif task_id.startswith("review-findings_map_"):
                output = {
                    "dimension": task_id,
                    "findings": [
                        {
                            "severity": "minor",
                            "summary": "review finding",
                            "evidence": ["path:line"],
                            "uncertainty": [],
                        }
                    ],
                }
            elif task_id.startswith("verify-findings_verify_"):
                output = {
                    "verdict": "accept",
                    "summary": "verified finding",
                    "evidence": ["path:line"],
                }
            elif task_id == "cross-check-findings":
                output = {
                    "verified_blockers": ["one blocker"],
                    "verified_important": [],
                    "minor": [],
                    "rejected_claims": [],
                    "unknown": [],
                    "evidence_gaps": [],
                }
            elif task_id == "synthesize-review":
                output = {
                    "clean_candidate": False,
                    "summary": "blocker remains",
                    "blockers": ["one blocker"],
                    "important": [],
                    "uncertainty": [],
                    "next_actions": ["fix blocker"],
                }
            elif task_id == "prepare-blocker-report":
                output = {
                    "summary": "blocker report",
                    "evidence": ["path:line"],
                    "uncertainty": [],
                    "next_actions": ["fix blocker"],
                }
            elif task_id == "prepare-clean-candidate":
                output = {
                    "summary": "clean report",
                    "evidence": ["path:line"],
                    "uncertainty": [],
                    "next_actions": ["review"],
                }
            elif task_id == "discover-modules":
                output = [
                    {
                        "name": f"module-{index}",
                        "path": f"module-{index}",
                        "reason": "bounded module",
                    }
                    for index in range(10)
                ]
            elif task_id.startswith("audit-modules_map_"):
                output = {
                    "module": task_id,
                    "findings": [
                        {
                            "severity": "minor",
                            "summary": "module finding",
                            "evidence": ["path:line"],
                            "uncertainty": [],
                        }
                    ],
                }
            elif task_id.startswith("verify-audits_verify_"):
                output = {
                    "verdict": "accept",
                    "summary": "verified module audit",
                    "evidence": ["path:line"],
                }
            elif task_id == "synthesize-repository":
                output = {
                    "verdict": "blockers_present",
                    "summary": "repository synthesis",
                    "verified_blockers": ["one blocker"],
                    "verified_important": [],
                    "minor": [],
                    "rejected_claims": [],
                    "unknown": [],
                    "evidence_gaps": [],
                    "next_actions": ["fix blocker"],
                }
            elif task_id == "record-accepted":
                output = {
                    "decision": "approve",
                    "summary": "accepted",
                    "evidence": ["gate decision"],
                    "next_actions": ["proceed"],
                }
            elif task_id == "record-rejected":
                output = {
                    "decision": "reject",
                    "summary": "rejected",
                    "evidence": ["gate decision"],
                    "next_actions": ["revise"],
                }
            elif task_id == "finalize-accepted":
                output = {
                    "decision": "approve",
                    "status": "accepted",
                    "summary": "accepted closeout",
                    "evidence": ["gate decision"],
                    "uncertainty": [],
                    "next_actions": ["proceed"],
                }
            elif task_id == "finalize-rejected":
                output = {
                    "decision": "reject",
                    "status": "rejected",
                    "summary": "rejected closeout",
                    "evidence": ["gate decision"],
                    "uncertainty": [],
                    "next_actions": ["revise"],
                }
            else:
                raise AssertionError(f"unexpected preset agent task: {task_id}")

            return _success(task_id, output)

        return execute

    async def run_flow(
        self,
        preset: str,
        decision: str,
    ) -> tuple[dict[str, Any], dict[str, Any], list[str], list[str]]:
        raw = swarm_presets.render_preset(
            preset,
            objective=f"Exercise {preset}",
            workdir=str(self.workdir),
        )
        ir = validate_workflow_ir(raw)
        run_dir = self.base / f"{preset}-{decision}"
        calls: list[str] = []
        executor = self.executor(calls)

        first = TrustedControlFlowScheduler(
            ir,
            run_dir,
            execute_agent=executor,
            limits=self.limits,
        )
        paused = await first.run(resume=False)
        self.assertTrue(paused["paused"])
        self.assertEqual(_states(paused)["review-gate"], "waiting")
        before_resume = list(calls)

        gate_store = HumanGateStore(run_dir, self.limits)
        waiting = gate_store.load("review-gate")
        gate_store.decide(
            "review-gate",
            decision=decision,
            actor="offline-e2e",
            source="host",
            expected_input_identity=waiting["input_identity"],
            note="preset runtime E2E",
        )

        resumed = TrustedControlFlowScheduler(
            ir,
            run_dir,
            execute_agent=executor,
            limits=self.limits,
        )
        final = await resumed.run(resume=True)
        return paused, final, before_resume, calls[len(before_resume) :]

    async def test_design_swarm_approve_and_reject_are_terminal_without_replay(self) -> None:
        for decision, selected, skipped in (
            (
                "approve",
                ["record-accepted", "finalize-accepted"],
                ["record-rejected", "finalize-rejected"],
            ),
            (
                "reject",
                ["record-rejected", "finalize-rejected"],
                ["record-accepted", "finalize-accepted"],
            ),
        ):
            with self.subTest(decision=decision):
                paused, final, pre_calls, resumed_calls = await self.run_flow(
                    "design-swarm",
                    decision,
                )
                self.assertEqual(paused["claimed_agent_count"], 15)
                self.assertEqual(final["claimed_agent_count"], 17)
                self.assertTrue(final["all_succeeded"])
                self.assertEqual(resumed_calls, selected)
                states = _states(final)
                for node_id in selected:
                    self.assertEqual(states[node_id], "succeeded")
                for node_id in skipped:
                    self.assertEqual(states[node_id], "skipped")
                self.assertEqual(len(pre_calls), len(set(pre_calls)))

    async def test_ultra_review_runs_blocker_join_then_rejected_closeout(self) -> None:
        paused, final, pre_calls, resumed_calls = await self.run_flow(
            "ultra-review",
            "reject",
        )
        self.assertEqual(paused["claimed_agent_count"], 18)
        self.assertEqual(final["claimed_agent_count"], 20)
        self.assertTrue(final["all_succeeded"])
        self.assertEqual(resumed_calls, ["record-rejected", "finalize-rejected"])
        states = _states(final)
        self.assertEqual(states["prepare-clean-candidate"], "skipped")
        self.assertEqual(states["prepare-blocker-report"], "succeeded")
        self.assertEqual(states["record-accepted"], "skipped")
        self.assertEqual(states["finalize-accepted"], "skipped")
        self.assertEqual(len(pre_calls), len(set(pre_calls)))

    async def test_repo_sweep_reaches_gate_at_twenty_two_and_finishes_at_twenty_three(self) -> None:
        paused, final, pre_calls, resumed_calls = await self.run_flow(
            "repo-sweep",
            "reject",
        )
        self.assertEqual(paused["claimed_agent_count"], 22)
        self.assertEqual(final["claimed_agent_count"], 23)
        self.assertTrue(final["all_succeeded"])
        self.assertEqual(resumed_calls, ["record-rejected"])
        states = _states(final)
        self.assertEqual(states["record-accepted"], "skipped")
        self.assertEqual(states["record-rejected"], "succeeded")
        self.assertEqual(len(pre_calls), len(set(pre_calls)))


if __name__ == "__main__":
    unittest.main()
