"""Wording-contract regressions, not a host simulator or native E2E proof.

These checks protect the handoff/result-reading distinctions that a host adapter
must implement. No model, subprocess, user installation or Runtime is invoked.
"""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path('skill/codex-dynamic-workflow')

CONTRACTS = {
    'results': ('references/evidence.md', '## Native result collection', (
        'execution state, result existence, retrieval completeness, review disposition',
        'host-resource release are separate observations',
        'A summary-only or truncated read is not evidence that no result exists',
        'includeOutputs=false', 'includeTurns=false',
        'do not equate these adapter-specific options',
        'originating tool family and exact returned IDs',
        'thread, turn/attempt, item and candidate',
        'pagination or output-range controls',
        'preserve known result existence',
        'supplied versus independently opened',
        'not a new model turn',
        'never creates an all-probe waiting stage',
    )),
    'handoff': ('references/delegation.md', '### Threaded control transfer', (
        'Creation lineage, probe custody and implementation control are different facts',
        'An unchanged parent ID does not by itself prove two implementation Roots',
        'Creating or naming a thread is not an ownership acknowledgement',
        "sender's relinquishment and receiver's acknowledgement",
        'Until this is confirmed, the proposed receiver must not write or dispatch',
        'Effective model identity and controller transfer are checked separately',
        'Custody is not implementation authority',
        'actual host access and a working result-delivery path',
        'cannot launch or follow up probes, change scope, write the candidate',
        'No all-probe completion barrier is introduced',
    )),
    'titles': ('references/host-routing.md', '## Readable thread titles', (
        'task prefix + responsibility + concrete question or deliverable',
        'Use WF, not CWF, as the user-facing prefix',
        '`WF · 实施 · 修复结果收口`',
        '`WF · 独立审核 · 核对交接证据`',
        '`WF · 探针 · 核对结果是否完整`',
        'only exact task-owned IDs',
        'title changes grant no authority',
        'A failed or unsupported rename is not an acceptance blocker',
        'not a model turn',
    )),
    'simulation': ('references/host-routing.md', '## Explicit role simulation', (
        'Only an explicit user request selects role simulation',
        'logical role, requested model/profile/effort and observed execution identity',
        'Native routes and actual code writing remain NOT_RUN when not exercised',
        'does not authorize writes, publication or installation',
        'do not mutate shipped profiles, global configuration or saved Runtime contracts',
        'The same model can be a non-author reviewer in a separate context',
        'never satisfies a required declared Astra verifier',
        'A stand-in is not a Burst sidecar just because it requests Grok',
        'Keep original task/role launch accounting',
        'only admitted optional Burst work receives the existing Burst exemption',
    )),
}


def section(text, heading):
    """Read normative prose in one section; comments/examples cannot mask removal."""
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'^```.*?^```[^\n]*$', '', text, flags=re.M | re.S)
    match = re.search(r'^' + re.escape(heading) + r'\s*$', text, re.M)
    if match is None:
        raise AssertionError('missing section: ' + heading)
    level = len(heading) - len(heading.lstrip('#'))
    rest = text[match.end():]
    end = re.search(r'^#{1,' + str(level) + r'} ', rest, re.M)
    return ' '.join(rest[:end.start() if end else len(rest)].split())


def verify_contract(text, heading, clauses):
    body = section(text, heading)
    missing = [clause for clause in clauses if clause not in body]
    if missing:
        raise AssertionError('missing contract clauses: ' + '; '.join(missing))


class HandoffObservationTests(unittest.TestCase):
    def check_contract(self, name):
        path, heading, clauses = CONTRACTS[name]
        verify_contract((ROOT / SKILL / path).read_text(encoding='utf-8'), heading, clauses)

    def test_result_completeness_is_not_delivery_or_lifecycle(self):
        self.check_contract('results')

    def test_lineage_custody_and_controller_are_not_conflated(self):
        self.check_contract('handoff')

    def test_titles_are_readable_but_not_authority_or_acceptance(self):
        self.check_contract('titles')

    def test_wf_prefix_is_display_only_and_preserves_contract_identifiers(self):
        text = (ROOT / SKILL / 'references/host-routing.md').read_text(encoding='utf-8')
        body = section(text, '## Readable thread titles')
        self.assertIn('Use WF, not CWF, as the user-facing prefix', body)
        self.assertIn('existing `cwf_*` profile identifiers', body)
        self.assertIn('`$codex-dynamic-workflow` invocation and repository paths unchanged', body)
        self.assertNotIn('`CWF ·', body)
        _, heading, clauses = CONTRACTS['titles']
        with self.assertRaises(AssertionError):
            verify_contract(text.replace('WF ·', 'CWF ·'), heading, clauses)

    def test_simulation_preserves_identity_accounting_and_native_limits(self):
        self.check_contract('simulation')

    def test_collection_precedes_any_return_repair(self):
        text = (ROOT / SKILL / 'references/explicit-workflow.md').read_text(encoding='utf-8')
        body = section(text, '## Node prompt and return')
        self.assertIn('Before diagnosing a missing/malformed return or spending a repair turn', body)
        self.assertIn('native result collection', body)
        self.assertLess(body.index('Before diagnosing'), body.index('at most one concrete'))
        self.assertIn('Creation tool family and exact returned IDs', body)

    def test_entry_exposes_observation_rules_without_starting_full_pipeline(self):
        text = (ROOT / SKILL / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('references/evidence.md#native-result-collection', text)
        self.assertIn('references/host-routing.md#readable-thread-titles', text)
        self.assertIn('references/host-routing.md#explicit-role-simulation', text)
        self.assertIn('Do not load them to bootstrap passive supplementation', text)
        self.assertLessEqual(len(text.splitlines()), 250)

    def test_custody_is_linked_from_host_lifecycle(self):
        text = (ROOT / SKILL / 'references/host-routing.md').read_text(encoding='utf-8')
        body = section(text, '## Lifecycle')
        self.assertIn('explicitly assigned legacy-probe custody', body)
        self.assertIn('not a second implementation Root', body)
        self.assertIn('former planning thread must not dispatch or write', body)
        self.assertIn('unresolved holds remain UNKNOWN', body)

    def test_existing_direct_write_independence_and_budget_guards_remain(self):
        text = ' '.join((ROOT / SKILL / 'references/delegation.md').read_text(encoding='utf-8').split())
        for clause in ('Sol Root writes directly by default', 'explicit parallel-write authorization',
                       'required non-author review', 'do not reset counters',
                       'do not treat UNKNOWN usage as zero', 'same DB/run, immutable routes',
                       'Parent-turn interruption or cancellation is not child termination',
                       'Late receipts count against the same task', 'stops writing, dispatching',
                       'same Sol execution Root', 'remain read-only by default',
                       'unresolved termination/resource'):
            with self.subTest(clause=clause):
                self.assertIn(clause, text)

    def test_result_gap_blocks_only_affected_acceptance_not_all_optional_work(self):
        body = section((ROOT / SKILL / 'references/evidence.md').read_text(encoding='utf-8'),
                       '## Native result collection')
        self.assertIn('Block only acceptance that requires the missing evidence', body)
        self.assertIn('already received material risks still need disposition', body)
        self.assertIn('A tool-call success is not the task outcome', body)
        self.assertIn('task failures do not become clean findings', body)

    def test_removed_clauses_cannot_be_hidden_in_comments_or_other_sections(self):
        for name, (path, heading, clauses) in CONTRACTS.items():
            body = section((ROOT / SKILL / path).read_text(encoding='utf-8'), heading)
            for clause in clauses:
                with self.subTest(contract=name, clause=clause):
                    changed = heading + '\n' + body.replace(clause, '', 1)
                    changed += '\n<!-- ' + clause + ' -->\n'
                    changed += '\n## Unrelated appendix\n' + clause
                    with self.assertRaises(AssertionError):
                        verify_contract(changed, heading, clauses)

    def test_legacy_contracts_fail_new_checks_without_schema_or_model_calls(self):
        counterexamples = {
            'results': 'A truncated summary with no NODE means the agent did not deliver.',
            'handoff': 'The child still has its old parent, therefore there are two Roots.',
            'titles': 'Use Sol Root or a generated nickname; the title proves authority.',
            'simulation': 'All-Grok simulation passes every native route and uses no launch quota.',
        }
        for name, old in counterexamples.items():
            _, heading, clauses = CONTRACTS[name]
            with self.subTest(contract=name), self.assertRaises(AssertionError):
                verify_contract(heading + '\n' + old, heading, clauses)

    def test_unknown_model_cannot_waive_a_model_specific_gate(self):
        body = section((ROOT / SKILL / 'references/delegation.md').read_text(encoding='utf-8'),
                       '### Threaded control transfer')
        self.assertIn('Effective model identity and controller transfer are checked separately', body)
        self.assertIn('verified model identity remains gated by that requirement', body)

    def test_tree_comparison_does_not_treat_missing_or_reference_as_installed(self):
        body = section((ROOT / SKILL / 'references/evidence.md').read_text(encoding='utf-8'),
                       '## Candidate contract')
        for clause in ('Missing is not equal', 'Do not report whole trees equal from a subset',
                       'Check the delivery manifest', 'intentional local override',
                       'never repair a reference checkout as though it were the target'):
            with self.subTest(clause=clause):
                self.assertIn(clause, body)

    def test_fenced_example_cannot_replace_normative_contract(self):
        for name, (_, heading, clauses) in CONTRACTS.items():
            text = heading + '\nNon-normative example:\n```text\n' + ' '.join(clauses) + '\n```\n'
            with self.subTest(contract=name), self.assertRaises(AssertionError):
                verify_contract(text, heading, clauses)

    def test_manifest_binds_changed_guidance_and_this_test(self):
        manifest = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
        paths = [str(SKILL / rel) for rel in (
            'SKILL.md', 'references/delegation.md', 'references/evidence.md',
            'references/explicit-workflow.md', 'references/host-routing.md')]
        paths.append('tests/test_handoff_observations.py')
        for relative in paths:
            with self.subTest(path=relative):
                key = Path(relative).as_posix()
                self.assertEqual(manifest[key], hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
