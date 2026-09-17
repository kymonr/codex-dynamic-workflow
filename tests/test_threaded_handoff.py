"""Guidance regression checks for threaded Skill-only phase handoff.

These tests validate package contracts and wording only. They do not prove that a
particular host can create independent controller conversations, transfer native
children, or run the requested models.
"""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill/codex-dynamic-workflow"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_package import parse_package_mapping


def read(relative: str) -> str:
    return (SKILL / relative).read_text(encoding="utf-8")


class ThreadedHandoffGuidanceTests(unittest.TestCase):
    def assert_threaded_prompt(self, prompt):
        for clause in ('prefer a separate Sol execution thread', 'sole implementation Root',
                       'when the host supports controller handoff', 'writes directly by default',
                       'same-conversation Sol model switch is only the fallback',
                       'writer subagents only for authorized isolated parallel writes',
                       'fresh read-only Astra context', 'existing Runtime contracts'):
            self.assertIn(clause, prompt)

    def test_ui_default_prompt_matches_threaded_direct_write_workflow(self):
        metadata = parse_package_mapping(read("agents/openai.yaml"))
        self.assertTrue(metadata['policy']['allow_implicit_invocation'])
        prompt = metadata['interface']['default_prompt']
        self.assertIn('$codex-dynamic-workflow', prompt)
        self.assert_threaded_prompt(prompt)

    def test_stale_ui_prompt_cannot_hide_behind_comments_or_descriptions(self):
        metadata = read("agents/openai.yaml")
        parsed = parse_package_mapping(metadata)
        current = parsed['interface']['default_prompt']
        stale = ('Use $codex-dynamic-workflow: a user/host switch lets Sol own '
                 'the execution main thread; a fresh Astra context reviews it.')
        changed = metadata.replace(json.dumps(current), json.dumps(stale))
        changed += '\n# ' + current + '\n'
        actual = parse_package_mapping(changed)['interface']['default_prompt']
        with self.assertRaises(AssertionError):
            self.assert_threaded_prompt(actual)

    def test_direct_root_writes_and_parallel_exception_are_consistent(self):
        for relative in ('SKILL.md', 'references/delegation.md', 'references/explicit-workflow.md',
                         'references/patterns.md'):
            text = ' '.join(read(relative).split())
            with self.subTest(relative=relative):
                self.assertIn('Sol Root writes directly by default', text)
                self.assertIn('parallel write', text)
        patterns = ' '.join(read('references/patterns.md').split())
        self.assertIn('separate Sol execution thread', patterns)
        self.assertIn('same-conversation Sol model switch is only the fallback', patterns)
        delegation = ' '.join(read('references/delegation.md').split())
        for clause in ('Do not delegate routine writing', 'explicit parallel-write authorization',
                       'disjoint owned files', 'required non-author review',
                       'serialized within the coordination DB', 'disclose that mismatch'):
            self.assertIn(clause, delegation)

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
        explicit = read("references/explicit-workflow.md")

        self.assertIn("exactly one implementation Root", delegation)
        self.assertIn("stops writing, dispatching", delegation)
        self.assertIn("must not remain a concurrent implementation controller", explicit)
        self.assertIn("former planning thread must not dispatch or write", routing)
        self.assertIn("Do not leave two Roots", delegation)
        self.assertIn("does not silently retake implementation ownership", delegation)
        policy = json.loads(read("policy.json"))
        self.assertEqual(policy["default_writer_count"], 1)
        self.assertFalse(policy["overlapping_writers"])

    def test_new_thread_preserves_explicit_mode_and_never_resets_budget_or_runtime(self):
        entry = read("SKILL.md")
        delegation = read("references/delegation.md")
        routing = read("references/host-routing.md")

        self.assertIn("controller-thread handoffs", entry)
        self.assertIn("explicit full workflow", delegation)
        self.assertIn("continues this exact task and\nmode", delegation)
        self.assertIn("SAME task\nallowance", delegation)
        self.assertIn("do not reset counters", delegation)
        self.assertIn("expand permissions", delegation)
        self.assertIn("same DB/run, immutable routes", delegation)
        self.assertIn("another run or conversation to reset limits", delegation)
        self.assertIn("Do not create a new Runtime run", routing)

    def test_receiving_root_inherits_completed_preflight_and_scope(self):
        entry = read("SKILL.md")

        self.assertIn("Completed preparation and preflight state transfers with the task", entry)
        self.assertIn("rechecks only necessary mutable state", entry)
        self.assertIn("does not replay unrelated preparation", entry)
        self.assertIn("cannot expand the authorized source or write scope", entry)

    def test_unknown_usage_and_supplemental_history_do_not_restart_on_new_thread(self):
        delegation = read("references/delegation.md")
        burst = read("references/burst.md")

        self.assertIn("automatic Burst probe already ran or was skipped", delegation)
        self.assertIn("do not treat UNKNOWN\nusage as zero", delegation)
        self.assertIn("do not re-trigger the normal\nthree-probe intent", delegation)
        self.assertIn("explicit new user allowance", delegation)
        self.assertIn("handoff is still the SAME task", burst)
        self.assertIn("Do not treat a new Sol execution thread", burst)
        self.assertIn("handoff itself is not that distinction", burst)

    def test_active_ownership_and_unknown_release_survive_thread_change(self):
        delegation = read("references/delegation.md")
        routing = read("references/host-routing.md")

        self.assertIn("active child/writer ownership", delegation)
        self.assertIn("unresolved termination/resource", delegation)
        self.assertIn("stay UNKNOWN", delegation)
        self.assertIn("A stop request", delegation)
        self.assertIn("controller handoff does not release", routing)
        self.assertIn("unresolved holds remain UNKNOWN", routing)

    def test_parent_turn_interruption_never_implies_child_termination(self):
        delegation = ' '.join(read("references/delegation.md").split())

        self.assertIn("Parent-turn interruption or cancellation is not child termination", delegation)
        self.assertIn("reconcile every previously launched attempt and child ID", delegation)
        self.assertIn("Late receipts count against the same task", delegation)
        self.assertIn("keep it UNKNOWN and do not relaunch the same work", delegation)
        self.assertIn("creates no new controller or ledger", delegation)

    def test_sol_writer_profile_remains_a_non_controller_child(self):
        writer = (ROOT / "profiles/cwf_sol_writer.toml").read_text(encoding="utf-8")
        delegation = read("references/delegation.md")

        self.assertIn("writer-child profile", writer)
        self.assertIn("not the Sol execution Root", writer)
        self.assertIn("do not spawn agents", writer)
        self.assertIn("new conversation also does not promote", writer)
        self.assertIn("Model identity never grants Root authority to a child", delegation)

    def test_fresh_astra_review_is_non_author_and_not_the_planning_context(self):
        delegation = read("references/delegation.md")

        self.assertIn("prefer a fresh Astra review context", delegation)
        self.assertIn("returning control to the planning thread", delegation)
        self.assertIn("full\nactual diff", delegation)
        self.assertIn("non-author for the\ncandidate", delegation)
        self.assertIn("remain read-only by default", delegation)
        self.assertIn("loses non-author status", delegation)
        self.assertIn("full-history fork", delegation)
        self.assertIn("It may reject the original Astra\ndesign", delegation)
        self.assertIn("same Sol execution Root", delegation)

    def test_threaded_handoff_is_skill_only_not_runtime_handoff(self):
        delegation = read("references/delegation.md")
        skill_readme = read("README.md")

        self.assertIn("manual Skill-only handoff is NOT Runtime handoff", delegation)
        self.assertIn("admitted native child packets", delegation)
        self.assertIn("Skill-only Root 交接", skill_readme)
        self.assertIn("不能绕过 Runtime", skill_readme)

    def test_source_manifest_tracks_threaded_handoff_files(self):
        manifest = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
        tracked = (
            "CHANGELOG.md",
            "README.md",
            "profiles/cwf_sol_writer.toml",
            "skill/codex-dynamic-workflow/README.md",
            "skill/codex-dynamic-workflow/SKILL.md",
            "skill/codex-dynamic-workflow/agents/openai.yaml",
            "skill/codex-dynamic-workflow/references/burst.md",
            "skill/codex-dynamic-workflow/references/delegation.md",
            "skill/codex-dynamic-workflow/references/explicit-workflow.md",
            "skill/codex-dynamic-workflow/references/host-routing.md",
            "tests/test_threaded_handoff.py",
        )
        actual = {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in tracked
        }
        mismatches = {
            path: {"manifest": manifest.get(path), "actual": actual[path]}
            for path in tracked
            if manifest.get(path) != actual[path]
        }
        self.assertEqual(mismatches, {}, json.dumps(mismatches, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main()
