"""Guidance consistency and real SQLite scheduling with SYNTHETIC host receipts.
No native models, account-credit measurement or model-quality claims are made.
"""
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

import test_sol_implementation as sol
from test_v4_supplemental import node, reply, finding

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skill/codex-dynamic-workflow'
sys.path.insert(0, str(SKILL / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts'))
import install as installer
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime.core import loads


def read(relative):
    return (SKILL / relative).read_text(encoding='utf-8')


def broad_bounds():
    section = read('references/budget.md').split('## Credit-aware phase budgeting', 1)[1]
    return json.loads(re.search(r'```json\s*(.*?)\s*```', section, re.S).group(1))


class PhaseHandoffGuidanceTests(unittest.TestCase):
    """Text checks detect guidance drift, not enforcement of natural language."""

    def test_default_writer_handoff_is_explicit_and_cannot_switch_the_host(self):
        entry = read('SKILL.md')
        brief = ' '.join(read('references/delegation.md').split())
        self.assertIn('The Skill cannot itself switch the running model', entry)
        self.assertIn('Implicit supplementation mode does not acquire this pipeline', brief)
        self.assertIn('Only the user/host can', brief)
        self.assertIn('effective identity UNKNOWN', brief)
        self.assertIn('not Sol', brief)
        self.assertIn('one `cwf_sol_writer` child as the sole source writer', brief)

    def test_brief_preserves_source_authority_and_cumulative_state(self):
        brief = read('references/delegation.md')
        for clause in ('relevant uncommitted changes', 'protected/owned files',
                       'concrete acceptance checks', 'unresolved claims',
                       'active', 'spent/reserved allowance', 'not a line-by-line'):
            self.assertIn(clause, brief)
        self.assertIn('otherwise exact source hashes or a bound snapshot', brief)
        self.assertIn('If the host cannot transfer control of active children', brief)
        self.assertIn('same DB/run, immutable routes', brief)
        self.assertIn('moving a writer into', brief)

    def test_root_and_default_writer_child_are_not_conflated(self):
        brief = read('references/delegation.md')
        self.assertIn('current Root dispatches and screens Luna', brief)
        self.assertIn('Model identity never grants Root authority to a child', brief)
        writer = (ROOT / 'profiles/cwf_sol_writer.toml').read_text(encoding='utf-8')
        self.assertIn('default Skill-only writer-child profile', writer)
        self.assertIn('not the main-thread controller', writer)
        self.assertIn('do not spawn agents', writer)

    def test_self_review_does_not_replace_fresh_acceptance(self):
        brief = read('references/delegation.md')
        self.assertIn('entire actual diff', brief)
        self.assertIn("whether Astra's plan was wrong", brief)
        self.assertIn('prefer a fresh Astra review context', brief)
        self.assertIn("Check beyond Luna's findings list", brief)
        self.assertIn('Runtime always requires its declared Astra verifier', brief)

    def test_breadth_is_not_a_batch_barrier_or_new_permission(self):
        supplemental = read('references/supplemental.md')
        for clause in ('6–12 distinct useful questions', 'not a simultaneous-thread target',
                       'finite cutoff', 'at most one follow-up',
                       'Nonblocking does not waive a known risk',
                       'never truncate material risks', 'not executed tests'):
            self.assertIn(clause, supplemental)
        self.assertIn('Do not wait solely for optional probes', supplemental)
        self.assertIn('Pause new optional admissions', supplemental)

    def test_implicit_and_explicit_entries_both_have_nonblocking_rules(self):
        entry = read('SKILL.md')
        explicit = read('references/explicit-workflow.md')
        self.assertIn('## Nonblocking supplementation in either mode', entry)
        self.assertIn('at most one follow-up', entry)
        self.assertIn('preserve', entry.lower())
        self.assertIn('Do not load them to bootstrap passive supplementation', entry)
        self.assertIn('references/delegation.md', entry)
        self.assertIn('[phase handoff](delegation.md)', explicit)
        self.assertIn('Root screens', read('references/supplemental.md'))

    def test_credits_are_not_launch_counters_or_savings_guarantees(self):
        budget = read('references/budget.md')
        self.assertIn('launch counts are not account credits', budget)
        self.assertIn('Account-wide deltas', budget)
        self.assertIn('Unknown remains', budget)
        self.assertIn('not target counts, account-credit guarantees', budget)
        policy = json.loads(read('policy.json'))
        self.assertEqual(policy['budget']['supplemental_luna_launches'], 12)
        self.assertEqual(policy['budget']['approved_child_launches'], 28)
        self.assertEqual(policy['budget']['absolute_child_launches'], 32)
        self.assertEqual(broad_bounds()['supplemental_approved'], 24)

    def test_closeout_is_bounded_and_never_claims_automatic_release(self):
        followup = read('references/followup.md')
        self.assertIn('No automatic timer or background receiver is added', followup)
        self.assertIn('Preserve early', followup)
        self.assertIn('UNKNOWN closure remain separate', followup)
        self.assertIn('stop-requested and unknown are observations', followup)
        self.assertIn('reconcile once after', followup)
        self.assertIn('do not short-poll', followup)


class BroadLunaSchedulingTests(unittest.TestCase):
    """Exercise existing Runtime gates with the documented opt-in broad bounds."""
    setUp = sol.SolImplementationTests.setUp
    tearDown = sol.SolImplementationTests.tearDown
    add = sol.SolImplementationTests.add
    pair = sol.SolImplementationTests.pair
    probe = sol.SolImplementationTests.probe
    acquire = sol.SolImplementationTests.acquire
    complete = sol.SolImplementationTests.complete

    def broader_run(self):
        self.run = self.rt.create(root=self.root, goal='SYNTHETIC broad scheduling',
                                  backend='native', implement=True, bounds=broad_bounds())

    def test_24_probes_preserve_review_and_do_not_wait_for_a_slow_probe(self):
        # The fixture questions share a tiny source; this tests accounting, not
        # whether 24 duplicate real-world investigations would be useful.
        original = self.rt.run(self.run)['contract']
        original_run = self.run
        self.broader_run()
        self.add(node('design', role='designer'), *self.pair(dependencies=['design']),
                 *(self.probe(f'p{i:02}') for i in range(25)))
        self.complete(self.acquire())
        writer = self.acquire()
        self.assertEqual(writer['node_id'], 'write')
        self.rt.bind(writer['attempt'], 'SYNTHETIC-sol', backend='native')
        slow = self.rt.acquire(self.run, backend='native', host_capacity=4, host_active=1)
        self.assertTrue(slow['admitted'], slow)
        self.rt.bind(slow['attempt'], 'SYNTHETIC-slow', backend='native')
        for _ in range(23):
            packet = self.rt.acquire(self.run, backend='native', host_capacity=4, host_active=2)
            self.assertTrue(packet['admitted'], packet)
            self.assertEqual(packet['route']['model'], 'gpt-5.6-luna')
            self.complete(packet)
        denied = self.rt.acquire(self.run, backend='native', host_capacity=4, host_active=2)
        self.assertFalse(denied['admitted'])
        self.assertIn('supplemental-allowance-exhausted', str(denied))
        (self.root / 'a.py').write_text('value = 2\n', encoding='utf-8')
        self.complete(writer, reply(changed_files=['a.py']), identity='SYNTHETIC-sol')
        self.rt.refresh(self.run, 'accept', reason='SYNTHETIC post-write candidate')
        self.assertEqual((self.base / 'snapshot-p00/a.py').read_text(encoding='utf-8'), 'value = 1\n')
        review = self.rt.acquire(self.run, backend='native', host_capacity=4, host_active=1)
        self.assertEqual(review['node_id'], 'accept')
        self.assertEqual(review['route']['model'], 'gpt-6-astra')
        self.complete(review)
        status = self.rt.finish(self.run)
        self.assertTrue(status['mainline_accepted'])
        self.assertEqual(status['supplemental_execution_holds'], 1)
        self.assertFalse(status['host_resources_released'])
        self.assertEqual(status['supplemental_coverage']['omitted'], 1)
        self.assertEqual(status['budget']['used'], 27)
        self.assertEqual(status['budget']['strong_used'], 2)
        self.assertEqual(self.rt.run(original_run)['contract'], original)
        self.rt.release(slow['attempt'], external_id='SYNTHETIC-slow', confirmed=True,
                        reason='SYNTHETIC observed host termination, not just stop request')
        self.assertEqual(self.rt.finish(self.run)['status'], 'completed')

    def test_broad_allowance_does_not_consume_the_reserved_host_slot(self):
        self.broader_run()
        self.add(*self.pair(), *(self.probe(f'p{i}') for i in range(4)))
        writer = self.acquire()
        self.rt.bind(writer['attempt'], 'SYNTHETIC-writer', backend='native')
        for host_active in (1, 2):
            packet = self.rt.acquire(self.run, backend='native', host_capacity=4,
                                     host_active=host_active)
            self.assertTrue(packet['admitted'], packet)
            self.rt.bind(packet['attempt'], 'SYNTHETIC-' + packet['node_id'], backend='native')
        denied = self.rt.acquire(self.run, backend='native', host_capacity=4, host_active=3)
        self.assertFalse(denied['admitted'])
        self.assertIn('mainline-capacity-reserved', str(denied))
        self.complete(writer, identity='SYNTHETIC-writer')
        review = self.rt.acquire(self.run, backend='native', host_capacity=4, host_active=2)
        self.assertEqual(review['node_id'], 'accept')
        self.complete(review)
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])

    def test_many_clean_reports_cannot_erase_a_partial_probe_risk(self):
        self.broader_run()
        self.add(node('main'), *(self.probe(f'p{i:02}') for i in range(24)))
        self.complete(self.acquire())
        partial = self.acquire()
        self.complete(partial, reply(outcome='partial', claims=[finding()]))
        for _ in range(23):
            self.complete(self.acquire())
        with self.assertRaisesRegex(WorkflowError, 'triage'):
            self.rt.finish(self.run)
        self.add(node('investigate'))
        claim_id = partial['attempt'] + '-0'
        self.rt.triage(claim_id, 'promoted', target='investigate',
                       reason='SYNTHETIC current evidence needs required investigation')
        self.complete(self.acquire())
        with self.assertRaises(WorkflowError):
            self.rt.finish(self.run)
        self.rt.resolve(claim_id, 'blocking', reason='SYNTHETIC unresolved acceptance risk')
        with self.assertRaises(WorkflowError):
            self.rt.finish(self.run)

    def test_reopen_keeps_broad_allowance_and_consumed_attempts(self):
        self.broader_run()
        self.add(self.probe())
        self.complete(self.acquire(), reply(outcome='failed'))
        contract = self.rt.run(self.run)['contract']
        used = self.rt.run(self.run)['used']
        self.rt.close()
        self.rt = Runtime(self.db)
        self.assertEqual(self.rt.run(self.run)['contract'], contract)
        self.assertEqual(loads(contract)['bounds']['supplemental_approved'], 24)
        self.assertEqual(self.rt.run(self.run)['used'], used)
        self.assertEqual(used, 1)


class PhaseHandoffInstallTests(unittest.TestCase):
    def test_isolated_install_preserves_unowned_files_and_delivers_handoff(self):
        # This is a synthetic install entirely under TemporaryDirectory. It never
        # inspects or modifies the user's CODEX_HOME or actual installation ledger.
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            source, home = base / 'source', base / 'synthetic-home'
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(
                '.git', '.delivery', 'reports', '__pycache__'))
            home.mkdir()
            relative = 'skills/codex-dynamic-workflow/SKILL.md'
            old_entry = home / relative
            old_entry.parent.mkdir(parents=True)
            old_entry.write_bytes(b'SYNTHETIC previous owned entry\n')
            state = source / '.delivery/install-state.json'
            state.parent.mkdir()
            state.write_text(json.dumps({
                'home': str(home), 'legacy_enabled': False,
                'hashes': {relative: installer.digest(old_entry.read_bytes())}
            }), encoding='utf-8')
            config = home / 'config.toml'
            config.write_bytes(b'# SYNTHETIC user settings must remain unchanged\n')
            role = home / 'agents/unrelated-test-role.toml'
            role.parent.mkdir()
            role.write_bytes(b'# SYNTHETIC unrelated role\n')
            preserved = {path: path.read_bytes() for path in (config, role)}
            preview = installer.install(source, home)
            self.assertEqual(preview['status'], 'DRY_RUN')
            self.assertTrue(preview['changes'])
            result = installer.install(source, home, apply=True)
            self.assertEqual(result['status'], 'INSTALLED')
            payload = installer.manifest(source, include_legacy=False)
            self.assertEqual(result['verified_files'], len(payload))
            for path, expected in payload.items():
                self.assertEqual((home / path).read_bytes(), expected, path)
            self.assertIn('current Root dispatches and screens Luna',
                          (home / 'skills/codex-dynamic-workflow/references/delegation.md')
                          .read_text(encoding='utf-8'))
            for path, expected in preserved.items():
                self.assertEqual(path.read_bytes(), expected)
            self.assertFalse((home / 'skills/dispatching-native-agents').exists())
            self.assertEqual(installer.install(source, home)['changes'], [])


if __name__ == '__main__':
    unittest.main()
