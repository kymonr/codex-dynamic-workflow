"""v4 policy/lifecycle regressions. Host receipts below are deterministic fixtures, not live models."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skill/codex-dynamic-workflow/scripts'))
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime.core import loads, dump, sha, DEFAULT_ROUTES


def node(name, **kw):
    d=dict(id=name, role='explorer', task='inspect', sources=['a.py'], checks=['inspect'], risk='low')
    d.update(kw); return d


def reply(**kw):
    d=dict(outcome='completed',summary='fixture checked',sources_opened=['a.py'],
           checks=[{'name':'inspect','status':'PASS'}],changed_files=[],claims=[])
    d.update(kw); return d


def finding():
    return dict(proposition='candidate omission',evidence=['a.py'],existence='supported',
                applicability='unknown',impact='needs current-source investigation')


class SupplementalV4Tests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.base=Path(self.t.name)
        self.root=self.base/'project'; self.root.mkdir(); (self.root/'a.py').write_text('x=1\n')
        self.rt=Runtime(self.base/'state.db', initialize=True)
        self.run=self.rt.create(root=self.root, goal='v4', backend='native')
    def tearDown(self): self.rt.close(); self.t.cleanup()
    def probe(self,name='probe',**kw):
        sr=self.base/('snapshot-'+name); sr.mkdir(exist_ok=True)
        (sr/'a.py').write_bytes((self.root/'a.py').read_bytes())
        d=node(name,supplemental=True,required=False,ordinary_qualified=True,snapshot_root=str(sr))
        d.update(kw); return d
    def add(self,*xs): return self.rt.add(self.run,list(xs),reason='fixture expansion')
    def acquire(self,**kw): return self.rt.acquire(self.run,backend='native',**kw)
    def done(self,p=None,result=None,release=True):
        p=p or self.acquire(host_capacity=6); ext='child-'+p['attempt']
        self.rt.bind(p['attempt'],ext,backend='native')
        self.rt.complete(p['attempt'],result or reply(),external_id=ext,backend='native')
        if release: self.rt.release(p['attempt'],external_id=ext,confirmed=True,reason='fixture host closure')
        return p,ext
    def test_default_is_astra_mainline(self):
        c=loads(self.rt.run(self.run)['contract'])
        self.assertEqual(c['workflow'],'astra-mainline'); self.assertEqual(c['bounds']['supplemental_approved'],12)
    def test_mainline_cannot_route_luna(self):
        with self.assertRaisesRegex(WorkflowError,'mainline requires'): self.add(node('m',ordinary_qualified=True))
    def test_supplemental_contract_restrictions(self):
        for kw in [dict(required=True),dict(tier='strong'),dict(role='writer',writes=['a.py']),dict(verifies='m'),dict(supplemental=1)]:
            with self.subTest(kw=kw), self.assertRaises(WorkflowError): self.add(self.probe(**kw))
    def test_snapshot_required_isolated_and_matching(self):
        p=self.probe(); p.pop('snapshot_root')
        with self.assertRaisesRegex(WorkflowError,'snapshot_root'): self.add(p)
        p=self.probe(snapshot_root=str(self.root))
        with self.assertRaisesRegex(WorkflowError,'isolated'): self.add(p)
        p=self.probe(); (Path(p['snapshot_root'])/'a.py').write_text('different')
        with self.assertRaisesRegex(WorkflowError,'does not match'): self.add(p)
    def test_mainline_cannot_depend_on_supplemental(self):
        with self.assertRaisesRegex(WorkflowError,'cannot depend'):
            self.add(self.probe(), node('main',depends=['probe']))
        self.assertEqual(self.rt.status(self.run)['nodes'],[])
    def test_pending_supplemental_does_not_block_mainline_finish(self):
        self.add(node('main'),self.probe()); self.done(); status=self.rt.finish(self.run)
        self.assertEqual(status['status'],'completed'); self.assertTrue(status['mainline_accepted'])
        self.assertFalse(status['scope_complete']); self.assertEqual(status['supplemental_coverage']['omitted'],1)
    def test_supplemental_only_never_accepts(self):
        self.add(self.probe())
        with self.assertRaisesRegex(WorkflowError,'supplemental-only'): self.rt.finish(self.run)
    def test_mainline_wins_even_when_added_after_probe(self):
        self.add(self.probe(), node('main',required=False))
        self.assertEqual(self.acquire(host_capacity=6)['node_id'],'main')
    def test_unknown_capacity_does_not_guess_luna_slots(self):
        self.add(self.probe()); p=self.acquire(); self.assertFalse(p['admitted'])
        self.assertIn('host-capacity-unknown',str(p['reasons']))
    def test_last_host_slot_is_reserved_for_astra(self):
        self.add(self.probe()); p=self.acquire(host_capacity=4,host_active=3)
        self.assertFalse(p['admitted']); self.assertIn('mainline-capacity-reserved',str(p))
        self.assertTrue(self.acquire(host_capacity=4,host_active=2)['admitted'])
    def test_full_unused_strong_budget_is_reserved(self):
        self.run=self.rt.create(root=self.root,goal='tight',backend='native',bounds=dict(approved=8,reserve=0,absolute=8,strong_approved=8))
        self.add(self.probe()); p=self.acquire(host_capacity=6)
        self.assertFalse(p['admitted']); self.assertIn('mainline-allowance-reserved',str(p))
    def test_supplemental_quota_counts_failed_attempt_and_retry(self):
        self.run=self.rt.create(root=self.root,goal='retry',backend='native',bounds=dict(supplemental_approved=1))
        self.add(self.probe()); self.done(result=reply(outcome='failed',checks=[]))
        self.rt.retry(self.run,'probe',reason='fixture input repair')
        p=self.acquire(host_capacity=6); self.assertFalse(p['admitted'])
        self.assertIn('supplemental-allowance-exhausted',str(p)); self.assertEqual(self.rt.status(self.run)['budget']['used'],1)
    def test_zero_supplemental_budget_preserves_mainline(self):
        self.run=self.rt.create(root=self.root,goal='no probes',backend='native',bounds=dict(supplemental_approved=0))
        self.add(node('main'),self.probe()); self.done()
        self.assertFalse(self.acquire(host_capacity=6)['admitted']); self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_failed_partial_and_interrupted_probes_stay_truthful(self):
        for outcome in ['failed','partial','interrupted']:
            with self.subTest(outcome=outcome):
                self.run=self.rt.create(root=self.root,goal=outcome,backend='native')
                self.add(node('main'),self.probe()); self.done()
                if outcome=='interrupted':
                    p=self.acquire(host_capacity=6); self.rt.bind(p['attempt'],'stopped',backend='native')
                    self.rt.release(p['attempt'],external_id='stopped',confirmed=True,reason='fixture stopped')
                else: self.done(result=reply(outcome=outcome,checks=[]))
                s=self.rt.finish(self.run); self.assertTrue(s['mainline_accepted'])
                self.assertEqual(s['supplemental_coverage']['states']['probe'],outcome)
    def test_running_probe_does_not_block_mainline_acceptance(self):
        self.add(node('main'),self.probe()); self.done()
        p=self.acquire(host_capacity=6); self.rt.bind(p['attempt'],'slow',backend='native')
        s=self.rt.finish(self.run); self.assertEqual(s['status'],'open'); self.assertTrue(s['mainline_accepted'])
        self.assertEqual(s['supplemental_execution_holds'],1); self.assertFalse(s['host_resources_released'])
        self.rt.release(p['attempt'],external_id='slow',confirmed=True,reason='fixture stopped')
        self.assertEqual(self.rt.finish(self.run)['status'],'completed')
    def test_unreconciled_mainline_still_blocks(self):
        self.add(node('main')); self.done(release=False)
        with self.assertRaisesRegex(WorkflowError,'mainline execution'): self.rt.finish(self.run)
    def test_received_finding_requires_root_triage(self):
        self.add(node('main'),self.probe()); self.done(); p,_=self.done(result=reply(claims=[finding()]))
        with self.assertRaisesRegex(WorkflowError,'triage'): self.rt.finish(self.run)
        with self.assertRaisesRegex(WorkflowError,'Root triage'): self.rt.decide(p['attempt']+'-0','REJECT',reason='not sufficient')
        self.rt.triage(p['attempt']+'-0','dismissed',reason='Root reopened current a.py and disproved this candidate')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_failed_attempt_claim_cannot_disappear_in_retry(self):
        self.add(node('main'),self.probe()); self.done()
        self.done(result=reply(outcome='partial',checks=[],claims=[finding()]))
        self.rt.retry(self.run,'probe',reason='new fixture method'); self.done()
        with self.assertRaisesRegex(WorkflowError,'triage'): self.rt.finish(self.run)
    def test_late_finding_invalidates_prior_acceptance(self):
        self.add(node('main'),self.probe()); self.done()
        p=self.acquire(host_capacity=6); self.rt.bind(p['attempt'],'late',backend='native')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
        self.rt.complete(p['attempt'],reply(claims=[finding()]),external_id='late',backend='native')
        self.assertFalse(self.rt.status(self.run)['mainline_accepted'])
        self.rt.triage(p['attempt']+'-0','advisory',reason='Root checked current source: unrelated improvement outside acceptance')
        self.rt.release(p['attempt'],external_id='late',confirmed=True,reason='fixture closed')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_promotion_is_required_current_astra_work(self):
        self.add(node('main'),self.probe()); self.done(); p,_=self.done(result=reply(claims=[finding()]))
        self.add(node('resolve'))
        self.rt.triage(p['attempt']+'-0','promoted',reason='bounded current-source investigation needed',target='resolve')
        with self.assertRaises(WorkflowError): self.rt.finish(self.run)
        self.done(); self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_completed_or_optional_target_cannot_launder_finding(self):
        self.add(node('main'),self.probe()); self.done(); p,_=self.done(result=reply(claims=[finding()]))
        with self.assertRaisesRegex(WorkflowError,'never-executed'): self.rt.triage(p['attempt']+'-0','promoted',reason='bad target',target='main')
        self.add(node('optional',required=False))
        with self.assertRaisesRegex(WorkflowError,'required Astra'): self.rt.triage(p['attempt']+'-0','promoted',reason='bad target',target='optional')
    def test_snapshot_reader_does_not_lock_current_writer(self):
        self.run=self.rt.create(root=self.root,goal='write',backend='native',implement=True)
        self.add(self.probe()); self.acquire(host_capacity=6)
        self.add(node('w',role='writer',writes=['a.py']),node('review',role='reviewer',verifies='w',depends=['w']))
        self.assertEqual(self.acquire(host_capacity=6)['node_id'],'w')
    def test_packet_reads_frozen_snapshot_not_working_tree(self):
        probe=self.probe(); self.add(probe); p=self.acquire(host_capacity=6)
        self.assertEqual(p['root'],probe['snapshot_root']); self.assertEqual(p['candidate_root'],str(self.root))
        (self.root/'a.py').write_text('x=2\n')
        self.done(p); self.assertEqual(self.rt.status(self.run)['nodes'][0]['state'],'completed')
    def test_omit_is_supplemental_only_and_not_for_active(self):
        self.add(node('m'),self.probe())
        with self.assertRaises(WorkflowError): self.rt.omit(self.run,'m',reason='bad')
        self.done(); self.acquire(host_capacity=6)
        with self.assertRaises(WorkflowError): self.rt.omit(self.run,'probe',reason='still live')
    def test_cutoff_blocks_more_probes_but_not_mainline_repair(self):
        self.add(node('m'),self.probe()); self.done(); self.acquire(host_capacity=6); self.rt.finish(self.run)
        self.add(self.probe('extra'),node('repair'))
        self.assertEqual(self.acquire(host_capacity=6)['node_id'],'repair')
        self.assertIn('supplemental-cutoff',str(self.acquire(host_capacity=6)))
    def test_v3_contract_reopens_without_rewriting_identity(self):
        self.run=self.rt.create(root=self.root,goal='legacy',backend='native',workflow='legacy')
        c=loads(self.rt.run(self.run)['contract']); c['version']='3.0.0'; c.pop('workflow')
        self.rt.conn.execute('UPDATE runs SET contract=?,contract_hash=? WHERE id=?',(dump(c),sha(c),self.run))
        before=self.rt.run(self.run)['contract_hash']; self.add(node('legacy',required=False,ordinary_qualified=True))
        self.done(result=reply(outcome='failed',checks=[]))
        with self.assertRaisesRegex(WorkflowError,'incomplete scope'): self.rt.finish(self.run)
        self.assertEqual(self.rt.run(self.run)['contract_hash'],before)
        with self.assertRaises(WorkflowError): self.add(self.probe())
    def test_bool_budget_and_mixed_routes_rejected(self):
        with self.assertRaises(WorkflowError): self.rt.create(root=self.root,goal='bad',backend='native',bounds=dict(supplemental_approved=True))
        routes=json.loads(json.dumps(DEFAULT_ROUTES)); routes['strong']['model']='gpt-5.6-luna'
        with self.assertRaisesRegex(WorkflowError,'identity mismatch'): self.rt.create(root=self.root,goal='bad',backend='native',routes=routes)
    def test_required_verification_cannot_be_luna(self):
        with self.assertRaisesRegex(WorkflowError,'mainline requires'):
            self.add(node('main'),node('review',role='reviewer',verifies='main',depends=['main'],ordinary_qualified=True))

    def test_nested_snapshot_tree_is_rejected(self):
        nested=self.root/'snap'; nested.mkdir(); (nested/'a.py').write_bytes((self.root/'a.py').read_bytes())
        with self.assertRaisesRegex(WorkflowError,'isolated'): self.add(self.probe(snapshot_root=str(nested)))
    def test_profile_cannot_shadow_requested_astra_model(self):
        routes=json.loads(json.dumps(DEFAULT_ROUTES)); routes['strong']['profile']='cwf_general'
        with self.assertRaisesRegex(WorkflowError,'identity mismatch'):
            self.rt.create(root=self.root,goal='bad profile',backend='native',routes=routes)
    def test_mutated_probe_snapshot_returns_partial(self):
        p=self.probe(); self.add(p); packet=self.acquire(host_capacity=6)
        (Path(p['snapshot_root'])/'a.py').write_text('changed')
        self.done(packet); self.assertEqual(self.rt.status(self.run)['nodes'][0]['state'],'partial')
    def test_stale_advisory_must_be_reconsidered(self):
        self.add(node('main'),self.probe()); self.done(); p,_=self.done(result=reply(claims=[finding()]))
        self.rt.triage(p['attempt']+'-0','advisory',reason='Root checked original candidate')
        (self.root/'a.py').write_text('x=2\n')
        self.assertIn('triage candidate changed',str(self.rt.status(self.run)['supplemental_claim_gaps']))
    def test_concurrent_supplemental_admission_is_atomic(self):
        import concurrent.futures
        self.run=self.rt.create(root=self.root,goal='concurrent',backend='native',bounds=dict(supplemental_approved=1))
        self.add(self.probe('p1'),self.probe('p2'))
        def launch(_):
            with Runtime(self.rt.path) as rt: return rt.acquire(self.run,backend='native',host_capacity=8)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(launch,range(2)))
        self.assertEqual(sum(r['admitted'] for r in results),1)
        self.assertEqual(self.rt.status(self.run)['budget']['used'],1)
    def test_deadline_does_not_fake_mainline_completion(self):
        self.add(node('m'))
        with patch('cwf_runtime.core.time.time',return_value=self.rt.run(self.run)['deadline']+1):
            with self.assertRaises(WorkflowError): self.rt.finish(self.run)
    def test_cleanup_can_finish_after_dispatch_deadline(self):
        self.add(node('m'),self.probe()); self.done(); p=self.acquire(host_capacity=6)
        self.rt.bind(p['attempt'],'slow',backend='native'); self.rt.finish(self.run)
        self.rt.release(p['attempt'],external_id='slow',confirmed=True,reason='fixture stopped')
        with patch('cwf_runtime.core.time.time',return_value=self.rt.run(self.run)['deadline']+1):
            self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_three_distinct_probe_example_runs_through_controller(self):
        import importlib.util
        path=Path(__file__).resolve().parents[1]/'scripts/prepare_v4_example.py'
        spec=importlib.util.spec_from_file_location('prepare_v4_fixture',path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        plan=json.loads(module.prepare(self.base/'example').read_text(encoding='utf-8'))
        nodes=plan.pop('nodes'); run=self.rt.create(**plan); self.rt.add(run,nodes,reason='prepared fixture')
        packets=[self.rt.acquire(run,backend='native',host_capacity=6) for _ in range(4)]
        self.assertEqual(packets[0]['route']['model'],'gpt-6-astra')
        self.assertEqual(len({p['node_id'] for p in packets[1:]}),3)
        self.assertTrue(all(p['route']['model']=='gpt-5.6-luna' for p in packets[1:]))
        def end(p):
            self.rt.bind(p['attempt'],p['node_id'],backend='native')
            self.rt.complete(p['attempt'],reply(sources_opened=['invoice.py']),external_id=p['node_id'],backend='native')
            self.rt.release(p['attempt'],external_id=p['node_id'],confirmed=True,reason='fixture host settled')
        for p in packets: end(p)
        review=self.rt.acquire(run,backend='native',host_capacity=6); self.assertEqual(review['node_id'],'review'); end(review)
        self.assertTrue(self.rt.finish(run)['mainline_accepted'])

    def test_cli_supports_strict_plan_capacity_triage_and_two_phase_finish(self):
        import contextlib
        import io
        from cwf_runtime.cli import main
        def cli(*args):
            out=io.StringIO()
            with contextlib.redirect_stdout(out): code=main(['--db',str(self.rt.path),*args])
            self.assertEqual(code,0,out.getvalue())
            return json.loads(out.getvalue())['result']
        plan=self.base/'cli-plan.json'
        plan.write_text(json.dumps(dict(root=str(self.root),goal='CLI fixture',backend='native',
                                        nodes=[node('m'),self.probe()])),encoding='utf-8')
        rid=cli('create','--plan',str(plan))['run_id']
        first=cli('next','--run',rid,'--backend','native','--host-capacity','6','--host-active','0')
        payload=self.base/'reply.json'; payload.write_text(json.dumps(reply()),encoding='utf-8')
        cli('bind','--attempt',first['attempt'],'--external-id','main-cli','--backend','native')
        cli('complete','--attempt',first['attempt'],'--external-id','main-cli','--backend','native','--result',str(payload))
        cli('release','--attempt',first['attempt'],'--external-id','main-cli','--confirmed','--reason','fixture host closed')
        probe=cli('next','--run',rid,'--backend','native','--host-capacity','6')
        cli('bind','--attempt',probe['attempt'],'--external-id','probe-cli','--backend','native')
        self.assertTrue(cli('finish','--run',rid)['mainline_accepted'])
        payload.write_text(json.dumps(reply(claims=[finding()])),encoding='utf-8')
        cli('complete','--attempt',probe['attempt'],'--external-id','probe-cli','--backend','native','--result',str(payload))
        self.assertFalse(cli('status','--run',rid)['mainline_accepted'])
        cli('triage','--claim',probe['attempt']+'-0','--disposition','dismissed','--reason','Root fixture source recheck')
        cli('release','--attempt',probe['attempt'],'--external-id','probe-cli','--confirmed','--reason','fixture closed')
        self.assertEqual(cli('finish','--run',rid)['status'],'completed')

if __name__=='__main__': unittest.main()
