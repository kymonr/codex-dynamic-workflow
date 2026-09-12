"""4.2 adversarial regressions. All model identities and host receipts are SYNTHETIC.
No model, network client or paid/native runner is started by these tests.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skill/codex-dynamic-workflow/scripts'))
sys.path.insert(0, str(ROOT / 'scripts'))
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime.core import DEFAULT_ROUTES, LEGACY_ROUTES, dump, loads, sha
from test_v4_supplemental import node, reply, finding
from validate_package import validate


class SolImplementationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        (self.root / 'a.py').write_text('value = 1\n', encoding='utf-8')
        (self.root / 'b.py').write_text('other = 1\n', encoding='utf-8')
        self.db = self.base / 'state.sqlite'
        self.rt = Runtime(self.db, initialize=True)
        self.run = self.rt.create(root=self.root, goal='synthetic implementation', backend='native', implement=True)

    def tearDown(self):
        self.rt.close()
        self.tmp.cleanup()

    def add(self, *nodes):
        return self.rt.add(self.run, list(nodes), reason='synthetic zero-model graph')

    def pair(self, *, dependencies=None, sources=None, writes=None):
        sources = sources or ['a.py']
        return (node('write', role='writer', sources=sources, writes=writes or ['a.py'], depends=dependencies or []),
                node('accept', role='verifier', sources=sorted(set(sources + (writes or ['a.py']))),
                     verifies='write', depends=['write']))

    def acquire(self):
        return self.rt.acquire(self.run, backend='native', host_capacity=12, host_active=0)

    def complete(self, packet, result=None, identity=None, release=True):
        self.assertTrue(packet['admitted'], packet)
        identity = identity or 'SYNTHETIC-' + packet['attempt']
        self.rt.bind(packet['attempt'], identity, backend='native')
        self.rt.complete(packet['attempt'], result or reply(), external_id=identity, backend='native')
        if release:
            self.rt.release(packet['attempt'], external_id=identity, confirmed=True, reason='SYNTHETIC host closure')
        return identity

    def probe(self, name='probe'):
        snapshot = self.base / ('snapshot-' + name)
        snapshot.mkdir()
        (snapshot / 'a.py').write_bytes((self.root / 'a.py').read_bytes())
        return node(name, supplemental=True, required=False, ordinary_qualified=True, snapshot_root=str(snapshot))

    def constrained(self, approved=2, strong=1, reserve=0):
        self.run = self.rt.create(root=self.root, goal='synthetic constrained budget', backend='native',
                                  implement=True, bounds=dict(approved=approved, absolute=approved+reserve,
                                  strong_approved=strong, reserve=reserve))

    def test_new_routes_are_fixed_and_legacy_defaults_remain_astra(self):
        c = loads(self.rt.run(self.run)['contract'])
        self.assertEqual(c['version'], '4.2.0')
        self.assertEqual(c['routes']['writer'], dict(model='gpt-5.6-sol', profile='cwf_sol_writer', effort='high'))
        self.assertEqual(c['routes']['strong']['model'], 'gpt-6-astra')
        old = self.rt.create(root=self.root, goal='explicit legacy', backend='native', workflow='legacy')
        self.assertEqual(loads(self.rt.run(old)['contract'])['routes'], LEGACY_ROUTES)

    def test_one_sol_and_one_astra_fit_two_total_one_strong(self):
        self.constrained()
        self.add(*self.pair())
        writer = self.acquire()
        self.assertEqual(writer['route']['model'], 'gpt-5.6-sol')
        self.assertEqual(writer['permissions']['write_files'], ['a.py'])
        for permission in ('delete_files', 'publication', 'child_spawn', 'peer_messaging'):
            self.assertFalse(writer['permissions'][permission])
        self.assertEqual(self.rt.run(self.run)['used'], 1)
        self.assertEqual(self.rt.run(self.run)['strong_used'], 0)
        (self.root / 'a.py').write_text('value = 2\n', encoding='utf-8')
        self.complete(writer, reply(changed_files=['a.py']))
        self.rt.refresh(self.run, 'accept', reason='bind actual post-write candidate')
        verifier = self.acquire()
        self.assertEqual(verifier['route']['model'], 'gpt-6-astra')
        self.complete(verifier)
        status = self.rt.finish(self.run)
        self.assertTrue(status['mainline_accepted'])
        self.assertEqual((status['budget']['used'], status['budget']['strong_used'], status['budget']['reserve_used']), (2, 1, 0))

    def test_no_astra_allowance_blocks_sol_before_any_spend(self):
        self.constrained(strong=0)
        self.add(*self.pair())
        result = self.acquire()
        self.assertFalse(result['admitted'])
        self.assertIn('mandatory-reservations-exceed-strong', str(result))
        self.assertEqual(self.rt.run(self.run)['used'], 0)

    def test_sol_cannot_borrow_reserve_for_required_review(self):
        self.constrained(approved=1, strong=1, reserve=3)
        self.add(*self.pair())
        result = self.acquire()
        self.assertFalse(result['admitted'])
        self.assertIn('mandatory-reservations-exceed-approved', str(result))
        self.assertEqual(self.rt.run(self.run)['reserve_used'], 0)

    def test_writer_needs_declared_required_astra_verifier(self):
        self.add(self.pair()[0])
        self.assertIn('required-verifier-not-declared', str(self.acquire()))
        self.assertEqual(self.rt.run(self.run)['used'], 0)

    def test_luna_cannot_be_the_required_writer_verifier(self):
        writer, verifier = self.pair()
        verifier.update(tier='ordinary', ordinary_qualified=True)
        with self.assertRaises(WorkflowError):
            self.add(writer, verifier)
        self.assertEqual(self.rt.status(self.run)['nodes'], [])

    def test_no_implementation_authority_cannot_add_sol_writer(self):
        self.run = self.rt.create(root=self.root, goal='audit only', backend='native')
        with self.assertRaisesRegex(WorkflowError, 'implement authority'):
            self.add(*self.pair())

    def test_mainline_sol_precedes_luna_and_protects_final_review(self):
        self.constrained(approved=3, strong=1)
        self.add(self.probe('p1'), self.probe('p2'), *self.pair())
        writer = self.acquire()
        self.assertEqual(writer['node_id'], 'write')
        self.rt.bind(writer['attempt'], 'SYNTHETIC-live-writer', backend='native')
        first = self.acquire()
        self.assertEqual(first['node_id'], 'p1')
        self.complete(first)
        denied = self.acquire()
        self.assertFalse(denied['admitted'])
        self.assertIn('mainline-allowance-reserved', str(denied))
        self.assertEqual(self.rt.run(self.run)['strong_used'], 0)

    def test_complete_astra_sol_astra_flow_with_three_live_luna(self):
        self.constrained(approved=6, strong=2)
        self.add(node('design', role='designer'), *self.pair(dependencies=['design']),
                 *(self.probe('luna-' + str(i)) for i in range(3)))
        design = self.acquire()
        self.assertEqual(design['route']['model'], 'gpt-6-astra')
        self.complete(design)
        writer = self.acquire()
        self.assertEqual(writer['route']['model'], 'gpt-5.6-sol')
        self.rt.bind(writer['attempt'], 'SYNTHETIC-sol', backend='native')
        for _ in range(3):
            probe = self.acquire()
            self.assertTrue(probe['admitted'], probe)
            self.assertEqual(probe['route']['model'], 'gpt-5.6-luna')
            self.rt.bind(probe['attempt'], 'SYNTHETIC-' + probe['node_id'], backend='native')
        (self.root / 'a.py').write_text('value = 2\n', encoding='utf-8')
        self.complete(writer, reply(changed_files=['a.py']), identity='SYNTHETIC-sol')
        self.rt.refresh(self.run, 'accept', reason='post-write fixture')
        verifier = self.acquire()
        self.assertEqual(verifier['node_id'], 'accept')
        self.complete(verifier)
        status = self.rt.finish(self.run)
        self.assertTrue(status['mainline_accepted'])
        self.assertEqual(status['status'], 'open')
        self.assertEqual(status['supplemental_execution_holds'], 3)
        self.assertEqual((status['budget']['used'], status['budget']['strong_used']), (6, 2))

    def test_completed_writer_without_completed_review_never_accepts(self):
        self.add(*self.pair())
        self.complete(self.acquire())
        with self.assertRaises(WorkflowError):
            self.rt.finish(self.run)

    def test_model_labels_cannot_launder_same_host_author(self):
        self.add(*self.pair())
        self.complete(self.acquire(), identity='SYNTHETIC-same-author')
        self.complete(self.acquire(), identity='SYNTHETIC-same-author')
        with self.assertRaisesRegex(WorkflowError, 'independent'):
            self.rt.finish(self.run)

    def test_review_must_cover_all_writer_sources_not_just_diff(self):
        writer, verifier = self.pair(sources=['a.py', 'b.py'])
        verifier['sources'] = ['a.py']
        self.add(writer, verifier)
        self.complete(self.acquire(), reply(sources_opened=['a.py', 'b.py']))
        self.complete(self.acquire())
        with self.assertRaisesRegex(WorkflowError, 'independent'):
            self.rt.finish(self.run)

    def test_failed_sol_attempt_is_not_refunded(self):
        self.add(*self.pair())
        self.complete(self.acquire(), reply(outcome='failed'))
        r = self.rt.run(self.run)
        self.assertEqual((r['used'], r['strong_used']), (1, 0))
        with self.assertRaises(WorkflowError):
            self.rt.finish(self.run)

    def test_unreleased_sol_still_holds_writer_lock(self):
        self.add(*self.pair())
        writer = self.acquire()
        self.complete(writer, release=False)
        result = self.acquire()
        self.assertFalse(result['admitted'])
        self.assertIn('source-writer-lock', str(result))
        with self.assertRaises(WorkflowError):
            self.rt.finish(self.run)

    def test_saved_v41_routes_and_counters_remain_exact(self):
        for version in ('4.1.0', '4.1.1', '4.1.2'):
            with self.subTest(version=version):
                self.run = self.rt.create(root=self.root, goal='synthetic old contract', backend='native', implement=True)
                c = loads(self.rt.run(self.run)['contract'])
                c['version'], c['routes'] = version, deepcopy(LEGACY_ROUTES)
                self.rt.conn.execute('UPDATE runs SET contract=?,contract_hash=? WHERE id=?', (dump(c), sha(c), self.run))
                before = self.rt.run(self.run)['contract']
                self.add(*self.pair())
                writer = self.acquire()
                self.assertEqual(writer['route'], LEGACY_ROUTES['writer'])
                self.complete(writer)
                self.complete(self.acquire())
                self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
                self.assertEqual(self.rt.run(self.run)['strong_used'], 2)
                self.rt.close(); self.rt = Runtime(self.db)
                self.assertEqual(self.rt.run(self.run)['contract'], before)

    def test_sol_effort_selection_and_no_ultra(self):
        for effort in ('low', 'medium', 'high', 'xhigh', 'max'):
            routes = deepcopy(DEFAULT_ROUTES); routes['writer']['effort'] = effort
            r = self.rt.create(root=self.root, goal='synthetic effort', backend='native', routes=routes)
            self.assertEqual(loads(self.rt.run(r)['contract'])['routes']['writer']['effort'], effort)
        routes['writer']['effort'] = 'ultra'
        with self.assertRaisesRegex(WorkflowError, 'unsupported effort'):
            self.rt.create(root=self.root, goal='unsupported Sol effort', backend='native', routes=routes)

    def test_fixed_route_mutations_fail_before_any_run_created(self):
        for tier, key, value in (('writer','model','gpt-6-astra'), ('writer','profile','cwf_writer'),
                                 ('writer','profile','cwf_general'), ('strong','model','gpt-5.6-sol'),
                                 ('strong','profile','cwf_sol_writer'), ('ordinary','model','gpt-5.6-sol')):
            with self.subTest(tier=tier, key=key):
                count = self.rt.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
                routes = deepcopy(DEFAULT_ROUTES); routes[tier][key] = value
                with self.assertRaises(WorkflowError):
                    self.rt.create(root=self.root, goal='mutated route', backend='native', routes=routes)
                self.assertEqual(self.rt.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0], count)

    def test_old_astra_profile_cannot_be_relabelled_sol_in_legacy(self):
        routes = deepcopy(LEGACY_ROUTES); routes['writer']['model'] = 'gpt-5.6-sol'
        with self.assertRaisesRegex(WorkflowError, 'identity mismatch'):
            self.rt.create(root=self.root, goal='bad compatibility profile', backend='native', workflow='legacy', routes=routes)

    def test_sol_cannot_supply_resolution_but_astra_verifier_can(self):
        self.add(self.probe())
        probe = self.acquire(); self.complete(probe, reply(claims=[finding()]))
        cid = probe['attempt'] + '-0'
        self.add(*self.pair())
        self.rt.triage(cid, 'promoted', target='write', reason='SYNTHETIC Root confirmed fix scope')
        writer = self.acquire()
        (self.root / 'a.py').write_text('value = 2\n', encoding='utf-8')
        self.complete(writer, reply(changed_files=['a.py']))
        self.rt.refresh(self.run, 'accept', reason='post-write fixture')
        self.complete(self.acquire())
        with self.assertRaisesRegex(WorkflowError, 'Astra evidence'):
            self.rt.resolve(cid, 'disproved', reason='must not launder Sol judgment', node='write')
        self.rt.resolve(cid, 'fixed', reason='SYNTHETIC current independent verification', node='accept')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])


    def test_two_runs_cannot_have_concurrent_sol_writers(self):
        self.add(*self.pair())
        first = self.acquire()
        self.assertTrue(first['admitted'])
        other_root = self.base / 'other'
        other_root.mkdir(); (other_root/'a.py').write_text('x = 1')
        self.run = self.rt.create(root=other_root, goal='other isolated root', backend='native', implement=True)
        self.add(*self.pair())
        denied = self.acquire()
        self.assertFalse(denied['admitted'])
        self.assertIn('source-writer-lock', str(denied))

    def test_node_and_result_cannot_override_the_model_or_budget(self):
        writer, verifier = self.pair()
        writer['model'] = 'gpt-6-astra'
        with self.assertRaises(WorkflowError):
            self.add(writer, verifier)
        self.add(*self.pair())
        packet = self.acquire()
        self.rt.bind(packet['attempt'], 'SYNTHETIC-sol', backend='native')
        with self.assertRaises(WorkflowError):
            self.rt.complete(packet['attempt'], reply(route=DEFAULT_ROUTES['strong'], strong_used=0),
                             external_id='SYNTHETIC-sol', backend='native')
        self.assertEqual(self.rt.run(self.run)['used'], 1)

    def test_sol_writer_cannot_use_readonly_release(self):
        self.add(*self.pair())
        packet = self.acquire(); identity = self.complete(packet, release=False)
        with self.assertRaises(WorkflowError):
            self.rt.release(packet['attempt'], external_id=identity, confirmed=True,
                            reason='SYNTHETIC invalid writer receipt', kind='readonly-turn-completed', receipt={})
        self.assertEqual(self.rt.attempt(packet['attempt'])['released'], 0)

    def test_old_writer_still_consumes_strong_budget(self):
        self.constrained(approved=2, strong=1)
        c = loads(self.rt.run(self.run)['contract'])
        c['version'], c['routes'] = '4.1.2', deepcopy(LEGACY_ROUTES)
        self.rt.conn.execute('UPDATE runs SET contract=?,contract_hash=? WHERE id=?', (dump(c), sha(c), self.run))
        self.add(*self.pair())
        self.assertFalse(self.acquire()['admitted'])
        self.assertEqual(self.rt.run(self.run)['used'], 0)


    def test_sol_admission_rolls_back_all_counters_on_event_failure(self):
        self.constrained()
        self.add(*self.pair())
        original = self.rt.event
        def fail_reservation(run, kind, data):
            if kind == 'attempt.reserved':
                raise OSError('SYNTHETIC event write failure')
            original(run, kind, data)
        with patch.object(self.rt, 'event', side_effect=fail_reservation):
            with self.assertRaises(OSError):
                self.acquire()
        state = self.rt.run(self.run)
        self.assertEqual((state['used'], state['strong_used'], state['reserve_used']), (0, 0, 0))
        self.assertEqual(self.rt.node(self.run, 'write')['state'], 'pending')
        self.assertEqual(self.rt.node(self.run, 'write')['attempts'], 0)
        self.assertEqual(self.rt.status(self.run)['attempts'], [])
        self.assertEqual(self.acquire()['route']['model'], 'gpt-5.6-sol')

    def test_optional_sol_cannot_spend_the_only_astra_reservation(self):
        self.constrained(approved=1, strong=1, reserve=2)
        writer, verifier = self.pair()
        writer['required'] = False
        self.add(writer, verifier)
        self.assertFalse(self.acquire()['admitted'])
        state = self.rt.run(self.run)
        self.assertEqual((state['used'], state['strong_used'], state['reserve_used']), (0, 0, 0))

    def test_sol_change_requires_refresh_before_verifier_admission(self):
        self.add(*self.pair())
        writer = self.acquire()
        (self.root / 'a.py').write_text('value = 3\n', encoding='utf-8')
        self.complete(writer, reply(changed_files=['a.py']))
        blocked = self.acquire()
        self.assertFalse(blocked['admitted'])
        self.assertIn('candidate drift', str(blocked))
        self.rt.refresh(self.run, 'accept', reason='bind changed Sol candidate')
        self.complete(self.acquire())
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])

    def test_luna_readonly_profile_does_not_gain_sol_write_authority(self):
        malicious = node('probe-write', writes=['a.py'], tier='ordinary', ordinary_qualified=True)
        with self.assertRaises(WorkflowError):
            self.add(malicious)
        self.assertEqual(self.rt.status(self.run)['nodes'], [])

    def test_pre_v41_legacy_writer_keeps_its_exact_budget_after_reopen(self):
        for version in ('3.0.0', '4.0.0'):
            with self.subTest(version=version):
                self.run = self.rt.create(root=self.root, goal='SYNTHETIC saved legacy',
                                          backend='native', workflow='legacy', implement=True)
                contract = loads(self.rt.run(self.run)['contract'])
                contract['version'] = version
                before = dump(contract)
                self.rt.conn.execute('UPDATE runs SET contract=?,contract_hash=? WHERE id=?',
                                     (before, sha(contract), self.run))
                self.add(*self.pair())
                packet = self.acquire()
                self.assertEqual(packet['route'], LEGACY_ROUTES['writer'])
                self.complete(packet)
                self.complete(self.acquire())
                self.assertEqual(self.rt.finish(self.run)['status'], 'completed')
                self.rt.close(); self.rt = Runtime(self.db, read_only=True)
                state = self.rt.run(self.run)
                self.assertEqual(state['contract'], before)
                self.assertEqual(state['strong_used'], 2)
                self.rt.close(); self.rt = Runtime(self.db)


class SolPackageContractTests(unittest.TestCase):
    def mutation_rejected(self, rel, old, new, marker):
        target = (ROOT / rel).resolve()
        original = Path.read_text
        source = original(target, encoding='utf-8')
        self.assertEqual(source.count(old), 1)
        changed = source.replace(old, new)
        def read(path, *args, **kwargs):
            return changed if path.resolve() == target else original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            errors = validate(ROOT)
        self.assertTrue(any(marker in e for e in errors), errors)

    def test_sol_profile_cannot_shadow_model_or_permission(self):
        path = 'profiles/cwf_sol_writer.toml'
        assignment = 'model = ' + json.dumps('gpt-5.6-sol')
        self.mutation_rejected(path, assignment, 'model = '+json.dumps('gpt-6-astra'), 'identity drift')
        self.mutation_rejected(path, assignment, assignment+chr(10)+'sandbox_mode = '+json.dumps('workspace-write'), 'writer must inherit')

    def test_sol_profile_does_not_pin_effort(self):
        path = 'profiles/cwf_sol_writer.toml'
        config = tomllib.loads((ROOT/path).read_text(encoding='utf-8'))
        self.assertNotIn('model_reasoning_effort', config)
        self.assertNotIn('sandbox_mode', config)
        assignment = 'model = '+json.dumps('gpt-5.6-sol')
        self.mutation_rejected(path, assignment, assignment+chr(10)+'model_reasoning_effort = '+json.dumps('medium'), 'flexible profile pins effort')

    def test_preserved_astra_writer_profile_cannot_drift(self):
        self.mutation_rejected('profiles/cwf_writer.toml', 'model = '+json.dumps('gpt-6-astra'),
                               'model = '+json.dumps('gpt-5.6-sol'), 'identity drift')

    def test_new_sol_profile_is_owned_not_an_arbitrary_user_role(self):
        from install import manifest, destination
        files = manifest(ROOT, include_legacy=False)
        self.assertEqual(files['agents/cwf_sol_writer.toml'], (ROOT/'profiles/cwf_sol_writer.toml').read_bytes())
        self.assertIn('agents/cwf_writer.toml', files)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(destination(Path(tmp), 'agents/cwf_sol_writer.toml'), Path(tmp).resolve()/'agents/cwf_sol_writer.toml')
            with self.assertRaises(ValueError):
                destination(Path(tmp), 'agents/sol.toml')

    def test_default_policy_cannot_revert_writer_without_rejection(self):
        key = json.dumps('capable_writer')+': '
        self.mutation_rejected('skill/codex-dynamic-workflow/policy.json',
                               key+json.dumps('cwf_sol_writer'), key+json.dumps('cwf_writer'), 'policy writer profile drift')

    def test_critical_reviewer_route_cannot_be_relabelled_sol(self):
        core = 'skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py'
        model = chr(39)+'gpt-6-astra'+chr(39)
        profile = chr(39)+'cwf_reader'+chr(39)
        source = (ROOT/core).read_text(encoding='utf-8')
        start = source.index('DEFAULT_ROUTES =')
        end = source.index('LEGACY_ROUTES =')
        prefix, suffix = source[:start], source[end:]
        block = source[start:end]
        changed = block.replace(model, chr(39)+'gpt-5.6-sol'+chr(39)).replace(profile, chr(39)+'cwf_sol_writer'+chr(39))
        self.mutation_rejected(core, block, changed, 'fixed route identity drift: strong')

    def test_brief_and_probe_guidance_preserves_actual_acceptance(self):
        path = ROOT/'skill/codex-dynamic-workflow/references/delegation.md'
        text = ' '.join(path.read_text(encoding='utf-8').split())
        for required in ('not a second implementation', 'existing task/scope/sources/check/stop fields',
                         'per meaningful task, not per stage or repair', 'challenge the design assumptions',
                         'Astra review capacity and allowance before Sol', 'no model budget',
                         'not independent design review', 'full actual diff', 'pending acceptance'):
            with self.subTest(required=required):
                self.assertIn(required, text)


class SolInstalledCliTests(unittest.TestCase):
    def test_installed_three_stage_flow_has_no_source_import_dependency(self):
        import subprocess
        from install import manifest
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / 'standalone-home'
            home.mkdir()
            for rel, data in manifest(ROOT, include_legacy=False).items():
                dest = home / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            entry = home / 'skills/codex-dynamic-workflow/scripts/cwf.py'
            db = home / 'synthetic.sqlite'
            source = home / 'source'
            source.mkdir()
            (source / 'a.py').write_text('value = 1\n', encoding='utf-8')
            def cli(*args):
                # Only the self-contained state controller is executed, never a model host.
                command = [sys.executable, '-E', '-S', '-B', str(entry), '--db', str(db), *args]
                with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as out, \
                     tempfile.TemporaryFile(mode='w+', encoding='utf-8') as err:
                    result = subprocess.run(command, cwd=home, stdin=subprocess.DEVNULL,
                                            stdout=out, stderr=err, timeout=15)
                    out.seek(0); err.seek(0)
                    stdout, stderr = out.read(), err.read()
                self.assertEqual(result.returncode, 0, stdout + stderr)
                body = json.loads(stdout)
                self.assertTrue(body['ok'], body)
                return body['result']
            cli('init')
            plan = dict(root=str(source), goal='SYNTHETIC Astra Sol Astra integration',
                        backend='native', implement=True,
                        bounds=dict(approved=3, reserve=0, absolute=3, strong_approved=2),
                        nodes=[node('design', role='designer'),
                               node('write', role='writer', depends=['design'], writes=['a.py']),
                               node('accept', role='verifier', verifies='write', depends=['write'])])
            plan_file = home / 'plan.json'
            plan_file.write_text(dump(plan), encoding='utf-8')
            run = cli('create', '--plan', str(plan_file))['run_id']
            for name, model in (('design', 'gpt-6-astra'), ('write', 'gpt-5.6-sol'), ('accept', 'gpt-6-astra')):
                packet = cli('next', '--run', run, '--backend', 'native')
                self.assertTrue(packet['admitted'], packet)
                self.assertEqual((packet['node_id'], packet['route']['model']), (name, model))
                attempt, identity = packet['attempt'], 'SYNTHETIC-' + name
                cli('bind', '--attempt', attempt, '--external-id', identity, '--backend', 'native')
                result = reply()
                if name == 'write':
                    (source / 'a.py').write_text('value = 2\n', encoding='utf-8')
                    result = reply(changed_files=['a.py'])
                result_file = home / (name + '-result.json')
                result_file.write_text(dump(result), encoding='utf-8')
                cli('complete', '--attempt', attempt, '--external-id', identity,
                    '--backend', 'native', '--result', str(result_file))
                cli('release', '--attempt', attempt, '--external-id', identity,
                    '--confirmed', '--reason', 'SYNTHETIC receipt, NOT a real host release')
                if name == 'write':
                    cli('refresh', '--run', run, '--node', 'accept', '--reason', 'bind changed fixture')
            finished = cli('finish', '--run', run)
            self.assertTrue(finished['mainline_accepted'])
            self.assertEqual((finished['budget']['used'], finished['budget']['strong_used']), (3, 2))
            self.assertEqual(finished['budget']['unknown_usage_attempts'], 3)
            before = db.read_bytes()
            self.assertEqual(cli('status', '--run', run), finished)
            self.assertEqual(db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
