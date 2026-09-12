"""Routing capability and budget boundaries; no model or live install calls."""
import unittest
import tomllib

import test_runtime as initial
import test_contracts as package
from test_runtime import spec, reply
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime.core import DEFAULT_ROUTES, dump, loads
from cwf_runtime.policy import budget_admission


class LunaRoutingTests(unittest.TestCase):
    setUp = initial.RuntimeTests.setUp
    tearDown = initial.RuntimeTests.tearDown
    add = initial.RuntimeTests.add
    acquire = initial.RuntimeTests.acquire
    done = initial.RuntimeTests.done

    def test_qualified_ordinary_defaults_to_luna_max_and_reopens(self):
        self.run = self.rt.create(workflow='legacy', root=self.root, goal='bounded source inspection', backend='native',
                                  bounds={'strong_approved': 0})
        self.add(spec(risk='medium', ordinary_qualified=True))
        p = self.acquire()
        self.assertEqual(p['task']['tier'], 'ordinary')
        self.assertEqual(p['route'], dict(model='gpt-5.6-luna', effort='max', profile='cwf_general'))
        self.assertEqual(p['permissions']['write_files'], [])
        self.done(p)
        self.rt.finish(self.run)
        with Runtime(self.db, read_only=True) as reopened:
            budget = reopened.status(self.run)['budget']
            self.assertEqual((budget['used'], budget['strong_used'], budget['reserve_used']), (1, 0, 0))

    def test_ordinary_roles_are_not_restricted_to_explorer(self):
        for role in ('explorer', 'reproducer', 'designer', 'reviewer', 'verifier'):
            with self.subTest(role=role):
                self.run = self.rt.create(workflow='legacy', root=self.root, goal='bounded '+role, backend='native')
                self.add(spec(role=role, risk='medium', ordinary_qualified=True))
                self.assertEqual(self.done()[0]['route']['effort'], 'max')
                self.assertEqual(self.rt.finish(self.run)['status'], 'completed')

    def test_mechanical_and_explicit_strong_routes_are_preserved(self):
        self.add(spec('mechanical', tier='economy', risk='low', economy_qualified=True),
                 spec('explicit', tier='strong', ordinary_qualified=True), spec('unqualified'))
        self.assertEqual(self.done()[0]['route'], DEFAULT_ROUTES['economy'])
        self.assertEqual(self.done()[0]['route'], DEFAULT_ROUTES['strong'])
        self.assertEqual(self.done()[0]['route'], DEFAULT_ROUTES['strong'])

    def test_invalid_ordinary_qualification_is_rejected_atomically(self):
        for change in (dict(tier='ordinary'), dict(ordinary_qualified='yes'),
                       dict(ordinary_qualified=True, risk='high'),
                       dict(ordinary_qualified=True, role='writer', writes=['a.py'])):
            with self.subTest(change=change), self.assertRaises(WorkflowError):
                self.add(spec(**change))
        self.assertEqual(self.rt.status(self.run)['nodes'], [])

    def test_ordinary_verification_of_bounded_readonly_target(self):
        for risk in ('low', 'medium'):
            with self.subTest(risk=risk):
                self.run = self.rt.create(workflow='legacy', root=self.root, goal='verify '+risk, backend='native')
                self.add(spec('target', risk=risk, ordinary_qualified=True),
                         spec('check', role='verifier', risk=risk, ordinary_qualified=True,
                              depends=['target'], verifies='target'))
                self.done(); self.done()
                self.assertEqual(self.rt.finish(self.run)['status'], 'completed')

    def test_ordinary_verification_requires_non_author_and_full_candidate(self):
        for same_author in (False, True):
            with self.subTest(same_author=same_author):
                self.run = self.rt.create(workflow='legacy', root=self.root, goal='verification identity', backend='native')
                check_sources = ['a.py'] if same_author else ['b.py']
                self.add(spec('target', ordinary_qualified=True),
                         spec('check', role='verifier', ordinary_qualified=True, sources=check_sources,
                              depends=['target'], verifies='target'))
                for node, sources in (('target', ['a.py']), ('check', check_sources)):
                    p = self.acquire()
                    ext = 'same-child' if same_author else node
                    self.rt.bind(p['attempt'], ext, backend='native')
                    self.rt.complete(p['attempt'], reply(sources_opened=sources), external_id=ext, backend='native')
                    self.rt.release(p['attempt'], external_id=ext, confirmed=True, reason='test closure')
                with self.assertRaisesRegex(WorkflowError, 'independent current-candidate'):
                    self.rt.finish(self.run)

    def test_critical_check_cannot_be_weakened_by_its_own_risk_label(self):
        for target in (spec('target', risk='high'), spec('target', role='writer', writes=['a.py'])):
            for reverse in (False, True):
                with self.subTest(target=target['role'], reverse=reverse):
                    self.run = self.rt.create(workflow='legacy', root=self.root, goal='critical', backend='native', implement=True)
                    nodes = [target, spec('check', role='reviewer', ordinary_qualified=True,
                                         depends=['target'], verifies='target')]
                    with self.assertRaisesRegex(WorkflowError, 'requires a strong route'):
                        self.rt.add(self.run, list(reversed(nodes)) if reverse else nodes, reason='critical check')
                    self.assertEqual(self.rt.status(self.run)['nodes'], [])

    def test_later_ordinary_checker_cannot_target_existing_high_risk_node(self):
        self.add(spec('target', risk='high'))
        with self.assertRaisesRegex(WorkflowError, 'requires a strong route'):
            self.add(spec('check', role='verifier', ordinary_qualified=True,
                          depends=['target'], verifies='target'))
        self.assertFalse(self.acquire()['admitted'])

    def test_ordinary_work_cannot_consume_mechanical_reserve(self):
        self.run = self.rt.create(workflow='legacy', root=self.root, goal='reserve boundary', backend='native',
                                  bounds={'approved': 1, 'reserve': 1, 'absolute': 2, 'strong_approved': 0})
        self.add(spec('first', ordinary_qualified=True))
        self.done()
        self.add(spec('ordinary', ordinary_qualified=True, required=False))
        self.assertFalse(self.acquire()['admitted'])
        self.add(spec('mechanical', tier='economy', economy_qualified=True, required=False))
        p = self.acquire()
        self.assertEqual(p['node_id'], 'mechanical')
        self.done(p)
        budget = self.rt.status(self.run)['budget']
        self.assertEqual((budget['used'], budget['strong_used'], budget['reserve_used']), (2, 0, 1))

    def test_ordinary_preserves_pending_strong_acceptance_allowance(self):
        args = dict(approved=2, reserve=1, absolute=3, used=0, reserve_used=0,
                    strong_used=0, strong_approved=2, economy=True, economy_qualified=True,
                    active=0, capacity=None, mandatory_pending=2, mandatory_strong_pending=2,
                    optional=True)
        self.assertEqual(budget_admission(**args, reserve_eligible=False).outcome, 'defer')
        self.assertEqual(budget_admission(**args, reserve_eligible=True).reason, 'cumulative-economy-reserve')
        with self.assertRaises(ValueError):
            budget_admission(**args, reserve_eligible=1)

    def test_legacy_three_route_contract_and_node_survive_reopen(self):
        routes = {k: v for k, v in DEFAULT_ROUTES.items() if k != 'ordinary'}
        self.run = self.rt.create(workflow='legacy', root=self.root, goal='legacy routing', backend='native', routes=routes)
        self.add(spec('legacy'))
        old_spec = loads(self.rt.node(self.run, 'legacy')['spec'])
        old_spec.pop('ordinary_qualified')
        self.rt.conn.execute('UPDATE nodes SET spec=? WHERE run_id=? AND id=?',
                             (dump(old_spec), self.run, 'legacy'))
        contract_hash = self.rt.run(self.run)['contract_hash']
        self.rt.close(); self.rt = Runtime(self.db)
        self.assertEqual(loads(self.rt.run(self.run)['contract'])['routes'], routes)
        self.assertEqual(self.rt.run(self.run)['contract_hash'], contract_hash)
        self.assertEqual(loads(self.rt.node(self.run, 'legacy')['spec']), old_spec)
        self.assertEqual(self.done()[0]['route'], routes['strong'])
        with self.assertRaisesRegex(WorkflowError, 'ordinary route absent'):
            self.add(spec('new', ordinary_qualified=True))
        self.assertEqual(self.rt.finish(self.run)['status'], 'completed')


class GeneralProfileInstallationTests(unittest.TestCase):
    setUp = package.InstallationTests.setUp
    tearDown = package.InstallationTests.tearDown
    install = package.InstallationTests.install

    def test_general_profile_installs_without_changing_existing_luna_or_config(self):
        user_luna = self.home/'agents/luna.toml'
        user_luna.parent.mkdir(); user_luna.write_bytes(b'user-owned luna profile\n')
        result = self.install(apply=True)
        actual = tomllib.loads((self.home/'agents/cwf_general.toml').read_text(encoding='utf-8'))
        self.assertEqual((actual['model'], actual['model_reasoning_effort'], actual['sandbox_mode']),
                         ('gpt-5.6-luna', 'max', 'read-only'))
        self.assertEqual(user_luna.read_bytes(), b'user-owned luna profile\n')
        self.assertEqual((self.home/'config.toml').read_bytes(), b'model = "keep-me"\n')
        self.assertEqual(self.install()['changes'], [])
        package.installer.rollback(self.root, self.home, package.Path(result['receipt']))
        self.assertFalse((self.home/'agents/cwf_general.toml').exists())
        self.assertEqual(user_luna.read_bytes(), b'user-owned luna profile\n')

    def test_unowned_general_profile_collision_stops_before_install(self):
        target = self.home/'agents/cwf_general.toml'
        target.parent.mkdir(); target.write_bytes(b'user-owned general profile\n')
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.install(apply=True)
        self.assertEqual(target.read_bytes(), b'user-owned general profile\n')
        self.assertEqual(self.legacy_skill.read_bytes(), b'old skill\n')
        self.assertFalse(self.skill.exists())


if __name__ == '__main__':
    unittest.main()
