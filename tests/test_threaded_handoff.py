"""Guidance regression checks for threaded Skill-only phase handoff.

These tests validate package contracts and wording only. They do not prove that a
particular host can create independent controller conversations, transfer native
children, or run the requested models.
"""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill/codex-dynamic-workflow"


def read(relative: str) -> str:
    return (SKILL / relative).read_text(encoding="utf-8")


class ThreadedHandoffGuidanceTests(unittest.TestCase):
    def test_explicit_mode_prefers_separate_sol_execution_root_with_safe_fallback(self):
        entry = read("SKILL.md")
        delegation = read("references/delegation.md")
        explicit = read("references/explicit-workflow.md")

        for text in (entry, delegation, explicit):
            self.assertIn("separate Sol execution", text)
        self.assertIn("sole implementation Root", delegation)
        self.assertIn("fallback", delegation)
        self.assertIn("switch the current main conversation to Sol", delegation)
        self.assertIn("ordinary Sol writer child", entry)
        self.assertIn("not a substitute", entry)

    def test_control_transfer_keeps_exactly_one_implementation_root(self):
        delegation = read("references/delegation.md")
        routing = read("references/host-routing.md")

        self.assertIn("exactly one implementation Root", delegation)
        self.assertIn("stops writing, dispatching", delegation)
        self.assertIn("must not remain a concurrent implementation controller", explicit := read("references/explicit-workflow.md"))
        self.assertIn("former planning thread must not dispatch or write", routing)
        self.assertIn("Do not leave two Roots", delegation)
        self.assertIn("default_writer_count", read("policy.json"))
        policy = json.loads(read("policy.json"))
        self.assertEqual(policy["default_writer_count"], 1)
        self.assertFalse(policy["overlapping_writers"])

    def test_new_thread_never_resets_authority_budget_or_runtime(self):
        entry = read("SKILL.md")
        delegation = read("references/delegation.md")
        routing = read("references/host-routing.md")

        self.assertIn("controller-thread handoffs", entry)
        self.assertIn("SAME task allowance", delegation)
        self.assertIn("do not reset counters", delegation)
        self.assertIn("expand permissions", delegation)
        self.assertIn("same DB/run, immutable routes", delegation)
        self.assertIn("another run or conversation to reset limits", delegation)
        self.assertIn("Do not create a new Runtime run", routing)

    def test_active_ownership_and_unknown_release_survive_thread_change(self):
        delegation = read("references/delegation.md")
        routing = read("references/host-routing.md")

        self.assertIn("active child/writer ownership", delegation)
        self.assertIn("unresolved termination/resource", delegation)
        self.assertIn("stay UNKNOWN", delegation)
        self.assertIn("A stop request", delegation)
        self.assertIn("controller handoff does not release", routing)
        self.assertIn("unresolved holds remain UNKNOWN", routing)

    def test_sol_writer_profile_remains_a_non_controller_child(self):
        writer = (ROOT / "profiles/cwf_sol_writer.toml").read_text(encoding="utf-8")
        delegation = read("references/delegation.md")

        self.assertIn("writer-child profile", writer)
        self.assertIn("not the Sol execution Root", writer)
        self.assertIn("do not spawn agents", writer)
        self.assertIn("new conversation also does not promote", writer)
        self.assertIn("Model identity never grants Root authority to a child", delegation)

    def test_fresh_astra_review_is_not_the_planning_context_or_a_summary_review(self):
        delegation = read("references/delegation.md")

        self.assertIn("fresh Astra review thread/context", delegation)
        self.assertIn("rather than simply\nreturning control to the planning thread", delegation)
        self.assertIn("full actual diff", delegation)
        self.assertIn("Do not copy the full planning", delegation)
        self.assertIn("It may reject the original Astra\ndesign", delegation)
        self.assertIn("same Sol execution Root", delegation)

    def test_threaded_handoff_is_skill_only_not_runtime_handoff(self):
        delegation = read("references/delegation.md")
        skill_readme = read("README.md")

        self.assertIn("manual Skill-only handoff is NOT Runtime handoff", delegation)
        self.assertIn("admitted native child packets", delegation)
        self.assertIn("threaded Skill-only Root", skill_readme)
        self.assertIn("cannot bypass Runtime", skill_readme)


if __name__ == "__main__":
    unittest.main()
