"""Instruction consistency checks, NOT model-behavior or performance evidence."""
import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skill' / 'codex-dynamic-workflow'


def read(relative):
    return (SKILL / relative).read_text(encoding='utf-8')


class DispatchGuidanceTests(unittest.TestCase):
    def test_root_work_is_not_a_fixed_staffing_list(self):
        skill = read('SKILL.md')
        patterns = read('references/patterns.md')
        self.assertIn('Role names are not a staffing list', skill)
        self.assertIn('For supplemental probes,', ' '.join(skill.split()))
        self.assertIn('Root can keep cohesive mainline work in its own thread', patterns)
        self.assertIn('three-probe intent applies to supplemental coverage', patterns)
        self.assertIn('Runtime-managed work still requires an admitted packet', patterns)

    def test_effort_selection_preserves_user_parent_and_saved_routes(self):
        routing = read('references/host-routing.md')
        for rule in ('Do not silently downgrade an explicit user selection',
                     'Do not reconfigure the parent or global defaults',
                     'Runtime routes are fixed per tier when the run is created',
                     'not a per-node escalation API'):
            self.assertIn(rule, routing)

    def test_alternative_profiles_do_not_bypass_runtime_packets(self):
        routing = read('references/host-routing.md')
        self.assertIn('In Skill-only mode, if cwf_general is not exposed', routing)
        start = routing.index('In Skill-only mode, if cwf_general is not exposed')
        paragraph = routing[start:routing.index('\n\n', start)]
        self.assertIn('existing luna profile', paragraph)
        self.assertIn('With Runtime, execute the exact admitted route', paragraph)
        self.assertIn('not substitution authority', paragraph)

    def test_risk_evidence_is_not_truncated_to_three_cards(self):
        supplemental = read('references/supplemental.md')
        self.assertIn('every potentially material lead belongs in CLAIMS', supplemental)
        self.assertNotIn('record additional material leads as\nuncovered scope', supplemental)
        self.assertIn('Never treat a truncated report as clean coverage', supplemental)
        profile = (ROOT / 'profiles' / 'cwf_general.toml').read_text(encoding='utf-8')
        self.assertIn('retain every other potentially material lead in CLAIMS', profile)

    def test_review_efficiency_does_not_remove_required_checks(self):
        skill = read('SKILL.md')
        patterns = read('references/patterns.md')
        self.assertIn('Keep all required writer/high-risk/user-requested checks', skill)
        self.assertIn('Self-review at a higher effort is still self-review', patterns)
        self.assertIn('Do not attach an Astra reviewer to every Luna report', patterns)
        self.assertIn('same obligation and candidate', patterns)
        self.assertIn('a new promotion still requires its own explicit resolution', patterns)

    def test_probe_examples_are_optional_and_cover_three_distinct_questions(self):
        patterns = read('references/patterns.md')
        for heading in ('## Bounded probe examples', '| Coverage |', '| Counterexample |', '| Test gap |'):
            self.assertIn(heading, patterns)
        self.assertIn('Examples, not a mandatory task list or pre-established findings', patterns)
        self.assertIn('not a new Runtime schema or a mandatory form', patterns)

    def test_defaults_and_execution_profiles_are_preserved(self):
        policy = json.loads(read('policy.json'))
        self.assertEqual(policy['budget']['minimum_meaningful_luna_probes'], 3)
        self.assertEqual(policy['budget']['supplemental_luna_launches'], 12)
        self.assertEqual(policy['backend'], 'native-only')
        profiles = {p.stem: tomllib.loads(p.read_text(encoding='utf-8'))
                    for p in (ROOT / 'profiles').glob('*.toml')}
        self.assertEqual(set(profiles), {'cwf_reader', 'cwf_writer', 'cwf_general', 'cwf_mechanical'})
        for name in ('cwf_reader', 'cwf_writer'):
            self.assertEqual(profiles[name]['model'], 'gpt-6-astra')
            self.assertNotIn('model_reasoning_effort', profiles[name])


if __name__ == '__main__':
    unittest.main()
