"""Adversarial controller tests. Every host identity/receipt here is a synthetic fixture."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skill/codex-dynamic-workflow/scripts'))
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime.core import DEFAULT_ROUTES, LEGACY_ROUTES, dump, loads, sha
from cwf_runtime.executor import result_schema
from test_v4_supplemental import node, reply, finding


def run_subprocess_captured(args, *, timeout):
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as stdout, \
            tempfile.TemporaryFile(mode='w+', encoding='utf-8') as stderr:
        result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=timeout)
        stdout.seek(0); stderr.seek(0)
        return subprocess.CompletedProcess(result.args,result.returncode,stdout.read(),stderr.read())


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name).resolve()
        self.root=self.base/'source'; self.root.mkdir(); (self.root/'a.py').write_text('x=1\n')
        (self.root/'b.py').write_text('y=1\n')
        self.rt=Runtime(self.base/'state.db',initialize=True)
        self.run=self.rt.create(root=self.root,goal='fixture review',backend='native')
    def tearDown(self):
        self.rt.close(); self.tmp.cleanup()
    def probe(self,name='probe',sources=None):
        source=sources or ['a.py']; root=self.base/('snap-'+name); root.mkdir(exist_ok=True)
        for p in source: (root/p).write_bytes((self.root/p).read_bytes())
        return node(name,sources=source,supplemental=True,required=False,
                    ordinary_qualified=True,snapshot_root=str(root))
    def add(self,*nodes): self.rt.add(self.run,list(nodes),reason='fixture scope')
    def acquire(self,**kw):
        return self.rt.acquire(self.run,backend='native',**(dict(host_capacity=12,host_active=0)|kw))
    def start(self,packet=None,identity=None):
        p=packet or self.acquire(); self.assertTrue(p['admitted'],p)
        ext=identity or 'fixture-'+p['attempt']; self.rt.bind(p['attempt'],ext,backend='native')
        return p,ext
    def done(self,p=None,ext=None,result=None,release=True):
        if ext is None: p,ext=self.start(p)
        self.rt.complete(p['attempt'],result or reply(),external_id=ext,backend='native')
        if release: self.rt.release(p['attempt'],external_id=ext,confirmed=True,reason='synthetic host closure')
        return p,ext
    def setup_findings(self,count=1,implement=False,sources=None):
        self.run=self.rt.create(root=self.root,goal='fixture',backend='native',implement=implement)
        self.add(node('main',sources=sources or ['a.py']),self.probe(sources=sources))
        self.done(result=reply(sources_opened=sources or ['a.py']))
        p,e=self.done(result=reply(sources_opened=sources or ['a.py'],claims=[finding() for _ in range(count)]))
        return [p['attempt']+'-'+str(i) for i in range(count)]
    def promote(self,cid,name='investigate',sources=None):
        self.add(node(name,sources=sources or ['a.py']))
        self.rt.triage(cid,'promoted',target=name,reason='Root fixture: candidate affects acceptance')
        self.done(result=reply(sources_opened=sources or ['a.py']))
    def late_setup(self):
        self.add(node('main'),self.probe()); self.done(); p,e=self.start()
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
        return p,e
    def old_contract(self):
        c=loads(self.rt.run(self.run)['contract']); c['version']='4.0.0'
        c.pop('supplemental_protocol'); c.pop('acceptance_mode')
        self.rt.conn.execute('UPDATE runs SET contract=?,contract_hash=? WHERE id=?',(dump(c),sha(c),self.run))
        return self.rt.run(self.run)['contract']

    def test_luna_profiles_reject_conflicting_effort_atomically(self):
        count=self.rt.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        for tier in ('ordinary','economy'):
            for effort in {'low','medium','high','xhigh','max'}-{DEFAULT_ROUTES[tier]['effort']}:
                with self.subTest(tier=tier,effort=effort):
                    routes=json.loads(json.dumps(DEFAULT_ROUTES)); routes[tier]['effort']=effort
                    with self.assertRaisesRegex(WorkflowError,'identity mismatch'):
                        self.rt.create(root=self.root,goal='bad override',backend='native',routes=routes)
        self.assertEqual(self.rt.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0],count)
    def test_astra_effort_is_selected_and_preserved_in_new_contracts(self):
        for workflow in ('astra-mainline','legacy'):
            for effort in ('low','medium','high','xhigh','max','ultra'):
                with self.subTest(workflow=workflow,effort=effort):
                    routes=json.loads(json.dumps(LEGACY_ROUTES if workflow=='legacy' else DEFAULT_ROUTES))
                    routes['strong']['effort']=effort
                    if workflow=='legacy': routes['writer']['effort']=effort
                    run=self.rt.create(root=self.root,goal='selected effort',backend='native',workflow=workflow,routes=routes)
                    self.assertEqual(loads(self.rt.run(run)['contract'])['routes'],routes)
                    self.rt.add(run,[node('inspect')],reason='route packet check')
                    packet=self.rt.acquire(run,backend='native')
                    self.assertTrue(packet['admitted']);self.assertEqual(packet['route'],routes['strong'])
                    self.rt.release(packet['attempt'],external_id=None,confirmed=True,reason='synthetic no-launch fixture')
    def test_legacy_cannot_change_model_of_a_shipped_profile(self):
        routes=json.loads(json.dumps(DEFAULT_ROUTES));routes['strong']['model']='gpt-5.6-luna'
        with self.assertRaisesRegex(WorkflowError,'identity mismatch'):
            self.rt.create(root=self.root,goal='bad fixed model',backend='native',workflow='legacy',routes=routes)
    def test_unsupported_astra_effort_is_rejected(self):
        routes=json.loads(json.dumps(DEFAULT_ROUTES));routes['strong']['effort']='unbounded'
        with self.assertRaisesRegex(WorkflowError,'unsupported effort'):
            self.rt.create(root=self.root,goal='bad effort',backend='native',routes=routes)
    def test_acceptance_mode_is_explicit_and_repair_requires_authority(self):
        with self.assertRaisesRegex(WorkflowError,'authority'):
            self.rt.create(root=self.root,goal='bad',backend='native',acceptance_mode='repair')
        rid=self.rt.create(root=self.root,goal='repair',backend='native',implement=True)
        self.assertEqual(loads(self.rt.run(rid)['contract'])['acceptance_mode'],'repair')
    def test_old_v4_contract_hash_routes_and_budgets_are_unchanged(self):
        before=self.old_contract(); self.add(node('main')); self.done(); self.rt.finish(self.run)
        self.assertEqual(self.rt.run(self.run)['contract'],before)
        self.assertEqual(self.rt.run(self.run)['contract_hash'],sha(loads(before)))
    def test_old_v4_promotions_keep_old_completion_rule(self):
        self.old_contract(); self.add(node('main'),self.probe()); self.done()
        p,e=self.done(result=reply(claims=[finding()])); self.promote(p['attempt']+'-0')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_old_v4_late_advisory_still_needs_new_finish(self):
        self.old_contract();p,e=self.late_setup()
        self.rt.complete(p['attempt'],reply(claims=[finding()]),external_id=e,backend='native')
        self.rt.triage(p['attempt']+'-0','advisory',reason='fixture source check')
        self.assertFalse(self.rt.status(self.run)['mainline_accepted'])
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_old_v4_rejects_notes_and_new_operations(self):
        self.old_contract();self.add(node('main'));p,e=self.start()
        with self.assertRaisesRegex(WorkflowError,'fields'):
            self.rt.complete(p['attempt'],reply(notes=[]),external_id=e,backend='native')
        with self.assertRaisesRegex(WorkflowError,'v4.1'): self.rt.screen(self.run,[{}])
    def test_late_informational_notes_do_not_revoke_acceptance(self):
        p,e=self.late_setup()
        self.done(p,e,reply(notes=[{'text':'Consider clearer naming','evidence':['a.py']}]))
        self.assertTrue(self.rt.status(self.run)['mainline_accepted'])
        self.assertEqual(self.rt.conn.execute('SELECT COUNT(*) FROM claims').fetchone()[0],0)
    def test_malformed_notes_are_rejected_without_losing_attempt(self):
        self.add(self.probe());p,e=self.start()
        for notes in (None,[{'text':'tip','evidence':['b.py']}],[{'text':'','evidence':[]}],[{'text':'x','evidence':[],'severity':'safe'}]):
            with self.subTest(notes=notes),self.assertRaises(WorkflowError):
                self.rt.complete(p['attempt'],reply(notes=notes),external_id=e,backend='native')
        self.assertEqual(self.rt.attempt(p['attempt'])['state'],'running')
    def test_unknown_candidate_requires_screen_but_advisory_does_not_repeat_acceptance(self):
        p,e=self.late_setup();self.done(p,e,reply(claims=[finding()]))
        self.assertEqual(self.rt.status(self.run)['acceptance_state'],'pending-screen')
        self.rt.screen(self.run,[dict(claim=p['attempt']+'-0',disposition='advisory',reason='Root checked current source: outside task objective')])
        self.assertTrue(self.rt.status(self.run)['mainline_accepted'])
        self.assertEqual(sum(x['kind']=='mainline.accepted' for x in self.rt.events(self.run)),1)
    def test_duplicate_screening_does_not_create_another_mainline_obligation(self):
        p,e=self.late_setup();self.done(p,e,reply(claims=[finding(),finding()]))
        ids=[p['attempt']+'-'+str(i) for i in range(2)]
        self.rt.screen(self.run,[dict(claim=ids[0],disposition='advisory',reason='Root checked suggestion'),
                                dict(claim=ids[1],disposition='duplicate',duplicate_of=ids[0],reason='same evidence and proposition')])
        self.assertTrue(self.rt.status(self.run)['mainline_accepted'])
    def test_duplicate_of_unresolved_claim_remains_unresolved(self):
        ids=self.setup_findings(2)
        self.rt.triage(ids[1],'duplicate',duplicate_of=ids[0],reason='same issue')
        with self.assertRaisesRegex(WorkflowError,'triage'): self.rt.finish(self.run)
    def test_duplicate_cycles_are_rejected(self):
        ids=self.setup_findings(2);self.rt.triage(ids[0],'duplicate',duplicate_of=ids[1],reason='same')
        with self.assertRaisesRegex(WorkflowError,'cycle'):
            self.rt.triage(ids[1],'duplicate',duplicate_of=ids[0],reason='bad cycle')
    def test_duplicate_cannot_point_to_another_run(self):
        first=self.setup_findings()[0]; second=self.setup_findings()[0]
        with self.assertRaisesRegex(WorkflowError,'same-run'):
            self.rt.triage(second,'duplicate',duplicate_of=first,reason='unrelated run')
    def test_duplicate_cannot_expand_canonical_evidence(self):
        self.add(node('main'),self.probe(sources=['a.py','b.py']));self.done()
        other=finding();other['evidence']=['b.py'];p,e=self.done(result=reply(sources_opened=['a.py','b.py'],claims=[finding(),other]))
        with self.assertRaisesRegex(WorkflowError,'covering'):
            self.rt.triage(p['attempt']+'-1','duplicate',duplicate_of=p['attempt']+'-0',reason='bad coverage')
    def test_screen_batch_is_atomic(self):
        ids=self.setup_findings(2);before=self.rt.events(self.run)
        with self.assertRaises(WorkflowError):
            self.rt.screen(self.run,[dict(claim=ids[0],disposition='advisory',reason='valid'),
                                     dict(claim=ids[1],disposition='advisory',reason='')])
        self.assertEqual(self.rt.events(self.run),before)
    def test_screen_rejects_repeat_claim_in_one_batch(self):
        cid=self.setup_findings()[0];d=dict(claim=cid,disposition='dismissed',reason='fixture disproved')
        with self.assertRaisesRegex(WorkflowError,'unique'):self.rt.screen(self.run,[d,d])
    def test_completed_investigation_is_not_issue_resolution(self):
        cid=self.setup_findings()[0];self.promote(cid)
        with self.assertRaisesRegex(WorkflowError,'triage'):self.rt.finish(self.run)
        self.assertIn('issue-resolution-missing',str(self.rt.status(self.run)['supplemental_claim_gaps']))
    def test_review_can_report_confirmed_issue(self):
        cid=self.setup_findings()[0];self.promote(cid)
        self.rt.resolve(cid,'reported',reason='The requested review explicitly reports this finding')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_repair_cannot_pass_by_reporting_existing_bug(self):
        cid=self.setup_findings(implement=True)[0];self.promote(cid)
        with self.assertRaisesRegex(WorkflowError,'repair'):
            self.rt.resolve(cid,'reported',reason='still broken but investigated')
    def test_promoted_issue_cannot_be_demoted_to_advisory(self):
        cid=self.setup_findings()[0];self.promote(cid)
        with self.assertRaisesRegex(WorkflowError,'demotion'):
            self.rt.triage(cid,'advisory',reason='attempt to skip resolution')
    def test_disproved_resolution_is_bound_to_current_astra_evidence(self):
        cid=self.setup_findings()[0];self.promote(cid,sources=['a.py','b.py'])
        self.rt.resolve(cid,'disproved',reason='Root source recheck and concrete counterevidence')
        (self.root/'b.py').write_text('y=2\n')
        self.assertIn('resolution candidate changed',str(self.rt.status(self.run)['supplemental_claim_gaps']))
    def test_blocking_resolution_cannot_close(self):
        cid=self.setup_findings()[0];self.promote(cid)
        self.rt.resolve(cid,'blocking',reason='confirmed but unresolved')
        with self.assertRaisesRegex(WorkflowError,'triage'):self.rt.finish(self.run)
    def test_fixed_needs_independently_reviewed_actual_write(self):
        cid=self.setup_findings(implement=True)[0];self.promote(cid)
        with self.assertRaisesRegex(WorkflowError,'writer verification'):
            self.rt.resolve(cid,'fixed',reason='investigation is not a repair')
        self.add(node('write',role='writer',writes=['a.py'],depends=['main','investigate']),
                 node('verify',role='reviewer',verifies='write',depends=['write']))
        p,e=self.start();(self.root/'a.py').write_text('x=2\n');self.done(p,e,reply(changed_files=['a.py']))
        self.rt.refresh(self.run,'verify',reason='bind post-write verification');self.done()
        self.rt.resolve(cid,'fixed',node='verify',reason='actual scoped change and independent regression check')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_resolution_cannot_use_unsettled_readonly_work(self):
        cid=self.setup_findings()[0];self.add(node('investigate'))
        self.rt.triage(cid,'promoted',target='investigate',reason='need check');self.done(release=False)
        with self.assertRaisesRegex(WorkflowError,'reconciled'):
            self.rt.resolve(cid,'reported',reason='not yet settled')
    def test_resolution_cannot_borrow_unrelated_preexisting_astra_node(self):
        cid=self.setup_findings()[0]; self.promote(cid)
        with self.assertRaisesRegex(WorkflowError,'follow the promoted'):
            self.rt.resolve(cid,'disproved',node='main',reason='unrelated old work')
        self.assertIn('issue-resolution-missing',str(self.rt.status(self.run)['supplemental_claim_gaps']))
    def old_writer_with_new_resolution_review(self, saved_v41=False):
        self.run=self.rt.create(root=self.root,goal='old writer fixture',backend='native',implement=True)
        if saved_v41:
            contract=loads(self.rt.run(self.run)['contract']);contract['version']='4.1.0'
            self.rt.conn.execute('UPDATE runs SET contract=?,contract_hash=? WHERE id=?',(dump(contract),sha(contract),self.run))
        self.add(node('old_write',role='writer',sources=['a.py','b.py'],writes=['b.py']),
                 node('old_review',role='reviewer',sources=['a.py','b.py'],verifies='old_write',depends=['old_write']))
        p,e=self.start();(self.root/'b.py').write_text('y=2\n')
        self.done(p,e,reply(sources_opened=['a.py','b.py'],changed_files=['b.py']))
        self.rt.refresh(self.run,'old_review',reason='bind old writer');self.done(result=reply(sources_opened=['a.py','b.py']))
        self.add(self.probe());p,e=self.done(result=reply(claims=[finding()]))
        cid=p['attempt']+'-0';self.promote(cid)
        self.add(node('new_review',role='reviewer',sources=['a.py','b.py'],verifies='old_write',depends=['old_write','investigate']))
        self.done(result=reply(sources_opened=['a.py','b.py']))
        return cid
    def test_new_reviewer_cannot_wrap_pre_investigation_writer_as_fixed(self):
        cid=self.old_writer_with_new_resolution_review()
        with self.assertRaisesRegex(WorkflowError,'fixed writer must follow'):
            self.rt.resolve(cid,'fixed',node='new_review',reason='try to reuse unrelated old write')
        self.assertEqual(self.root.joinpath('a.py').read_text(),'x=1\n')
        self.assertIn('issue-resolution-missing',str(self.rt.status(self.run)['supplemental_claim_gaps']))
        with self.assertRaises(WorkflowError):self.rt.finish(self.run)
    def test_saved_v41_contract_keeps_original_resolution_behavior_and_identity(self):
        cid=self.old_writer_with_new_resolution_review(saved_v41=True)
        before=self.rt.run(self.run)['contract'];before_hash=self.rt.run(self.run)['contract_hash']
        self.rt.resolve(cid,'fixed',node='new_review',reason='saved v4.1 compatibility fixture')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
        self.assertEqual(self.rt.run(self.run)['contract'],before)
        self.assertEqual(self.rt.run(self.run)['contract_hash'],before_hash)
    def test_cli_triage_exposes_duplicate_and_retains_link(self):
        from cwf_runtime.cli import main
        first,second=self.setup_findings(2)
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            code=main(['--db',str(self.rt.path),'triage','--claim',second,
                       '--disposition','duplicate','--duplicate-of',first,'--reason','fixture same evidence'])
        self.assertEqual(code,0,out.getvalue())
        self.assertEqual(self.rt.events(self.run)[-1]['data']['duplicate_of'],first)

    def test_incremental_finding_survives_interruption(self):
        self.add(node('main'),self.probe());self.done();p,e=self.start()
        report={'report_id':'early','sources_opened':['a.py'],'claims':[finding()]}
        out=self.rt.report_findings(p['attempt'],report,external_id=e,backend='native')
        self.rt.release(p['attempt'],external_id=e,confirmed=True,reason='fixture interrupted and closed')
        self.assertEqual(self.rt.node(self.run,'probe')['state'],'interrupted')
        with self.assertRaisesRegex(WorkflowError,'triage'):self.rt.finish(self.run)
        self.rt.triage(out['claims'][0],'advisory',reason='Root source check: suggestion only')
        self.assertTrue(self.rt.finish(self.run)['mainline_accepted'])
    def test_incremental_reports_are_idempotent_and_conflict_closed(self):
        self.add(self.probe());p,e=self.start();data=dict(report_id='r',sources_opened=['a.py'],claims=[finding()])
        first=self.rt.report_findings(p['attempt'],data,external_id=e,backend='native');before=self.rt.events(self.run)
        self.assertTrue(self.rt.report_findings(p['attempt'],data,external_id=e,backend='native')['idempotent'])
        self.assertEqual(self.rt.events(self.run),before)
        bad=json.loads(json.dumps(data));bad['claims'][0]['proposition']='different'
        with self.assertRaisesRegex(WorkflowError,'conflicting'):
            self.rt.report_findings(p['attempt'],bad,external_id=e,backend='native')
        self.assertEqual(len(first['claims']),1)
    def test_incremental_identity_scope_and_terminal_boundaries(self):
        self.add(self.probe());p,e=self.start();d=dict(report_id='r',sources_opened=['a.py'],claims=[finding()])
        with self.assertRaisesRegex(WorkflowError,'identity'):
            self.rt.report_findings(p['attempt'],d,external_id='wrong',backend='native')
        with self.assertRaisesRegex(WorkflowError,'scope'):
            self.rt.report_findings(p['attempt'],dict(d,sources_opened=['b.py']),external_id=e,backend='native')
        self.rt.release(p['attempt'],external_id=e,confirmed=True,reason='fixture closed')
        with self.assertRaisesRegex(WorkflowError,'active'):
            self.rt.report_findings(p['attempt'],d,external_id=e,backend='native')
    def test_incremental_claim_count_is_bounded(self):
        self.add(self.probe());p,e=self.start()
        for i in range(2):
            self.rt.report_findings(p['attempt'],dict(report_id=str(i),sources_opened=['a.py'],claims=[finding()]*64),external_id=e,backend='native')
        with self.assertRaisesRegex(WorkflowError,'limit'):
            self.rt.report_findings(p['attempt'],dict(report_id='overflow',sources_opened=['a.py'],claims=[finding()]),external_id=e,backend='native')
    def test_two_upcoming_astra_checks_reserve_two_slots(self):
        self.add(node('main'),node('r1',role='reviewer',depends=['main'],verifies='main'),
                 node('r2',role='reviewer',depends=['main'],verifies='main'),self.probe())
        self.start();denied=self.acquire(host_capacity=3,host_active=1)
        self.assertFalse(denied['admitted']);self.assertIn('mainline-capacity-reserved',str(denied))
        self.assertTrue(self.acquire(host_capacity=4,host_active=1)['admitted'])
        event=[e for e in self.rt.events(self.run) if e['kind']=='attempt.reserved'][-1]
        self.assertEqual(event['data']['mainline_reserve'],2)
    def test_root_can_increase_but_not_remove_capacity_reserve(self):
        self.add(self.probe())
        self.assertFalse(self.acquire(host_capacity=4,host_active=1,mainline_slots_needed=3)['admitted'])
        with self.assertRaises(WorkflowError): self.acquire(mainline_slots_needed=0)
        with self.assertRaises(WorkflowError): self.acquire(mainline_slots_needed=True)
    def test_configured_capacity_is_not_a_live_host_observation(self):
        self.run=self.rt.create(root=self.root,goal='capacity fixture',backend='native',bounds={'capacity':5})
        self.add(self.probe())
        self.assertIn('host-capacity-unknown',str(self.rt.acquire(self.run,backend='native',host_active=0)))
        self.assertIn('host-active-unknown',str(self.rt.acquire(self.run,backend='native',host_capacity=5)))
    def test_closeout_does_not_stop_promising_probe_or_release_resources(self):
        p,e=self.late_setup();s=self.rt.status(self.run);self.assertEqual(s['closeout'][0]['state'],'needs-host-closeout')
        until=time.time()+60
        self.rt.closeout(self.run,[dict(attempt=p['attempt'],action='continue',reason='fixture useful progress',
                       observed_via='fixture native receiver receipt',receiver='fixture-root-owner',until=until)])
        s=self.rt.status(self.run);self.assertTrue(s['mainline_accepted']);self.assertFalse(s['host_resources_released'])
        self.assertEqual(self.rt.attempt(p['attempt'])['state'],'running')
        with patch('cwf_runtime.core.time.time',return_value=until+1):
            self.assertEqual(self.rt.status(self.run)['closeout'][0]['state'],'continuation-expired')
    def test_closeout_stop_request_is_not_termination(self):
        p,e=self.late_setup()
        self.rt.closeout(self.run,[dict(attempt=p['attempt'],action='stop-requested',reason='fixture host request',observed_via='fixture interrupt response')])
        self.assertFalse(self.rt.attempt(p['attempt'])['released']);self.assertTrue(self.rt.status(self.run)['mainline_accepted'])
    def test_closeout_requires_receiver_and_bounded_cutoff(self):
        p,e=self.late_setup();entry=dict(attempt=p['attempt'],action='continue',reason='fixture',observed_via='fixture')
        for extra in ({},{'receiver':'fixture'},{'receiver':'fixture','until':time.time()+1000},{'receiver':'fixture','until':True}):
            with self.subTest(extra=extra),self.assertRaises(WorkflowError):self.rt.closeout(self.run,[entry|extra])
    def test_closeout_batch_rejects_mainline_and_rolls_back(self):
        p,e=self.late_setup();main=self.rt.node(self.run,'main')['current_token'];before=self.rt.events(self.run)
        def entry(token):return dict(attempt=token,action='unknown',reason='fixture',observed_via='fixture')
        with self.assertRaises(WorkflowError):self.rt.closeout(self.run,[entry(p['attempt']),entry(main)])
        self.assertEqual(self.rt.events(self.run),before)
    def test_cancellation_never_becomes_acceptance(self):
        p,e=self.late_setup();self.rt.cancel(self.run,reason='fixture user cancellation')
        self.assertFalse(self.rt.status(self.run)['mainline_accepted'])
        with self.assertRaises(WorkflowError):self.rt.closeout(self.run,[dict(attempt=p['attempt'],action='unknown',reason='fixture',observed_via='fixture')])
    def test_new_candidate_reopens_probes_without_resetting_budget(self):
        self.run=self.rt.create(root=self.root,goal='repair',backend='native',implement=True)
        p,e=self.late_setup();self.add(node('write',role='writer',writes=['a.py'],depends=['main']),
                                     node('verify',role='reviewer',verifies='write',depends=['write']))
        w,we=self.start();(self.root/'a.py').write_text('x=2\n');self.done(w,we,reply(changed_files=['a.py']))
        self.rt.refresh(self.run,'verify',reason='new candidate');self.done();self.add(self.probe('new_probe'))
        self.assertFalse(self.acquire()['admitted']);before=self.rt.status(self.run)['budget']
        self.rt.reopen_supplemental(self.run,['a.py'],reason='actual repaired candidate has a distinct test gap')
        self.assertEqual(self.rt.status(self.run)['budget'],before)
        self.assertEqual(self.acquire()['node_id'],'new_probe')
        with self.assertRaises(WorkflowError):self.rt.reopen_supplemental(self.run,['a.py'],reason='cannot reopen open epoch again')
    def test_unchanged_or_unbound_candidate_cannot_reopen(self):
        self.late_setup()
        for paths in (['a.py'],['b.py']):
            with self.assertRaisesRegex(WorkflowError,'changed bound'):
                self.rt.reopen_supplemental(self.run,paths,reason='no changed candidate')
    def test_deadline_does_not_reset_for_candidate_reopen(self):
        self.late_setup();(self.root/'a.py').write_text('x=2\n')
        with patch('cwf_runtime.core.time.time',return_value=self.rt.run(self.run)['deadline']+1):
            with self.assertRaisesRegex(WorkflowError,'deadline'):
                self.rt.reopen_supplemental(self.run,['a.py'],reason='expired')
    def test_cli_screen_resolution_report_and_closeout_are_wired(self):
        from cwf_runtime.cli import main
        def cli(*args):
            out=io.StringIO()
            with contextlib.redirect_stdout(out):code=main(['--db',str(self.rt.path),*args])
            self.assertEqual(code,0,out.getvalue());return json.loads(out.getvalue())['result']
        p,e=self.late_setup();path=self.base/'report.json';path.write_text(json.dumps(dict(report_id='early',sources_opened=['a.py'],claims=[finding()])))
        cid=cli('report','--attempt',p['attempt'],'--external-id',e,'--backend','native','--report',str(path))['claims'][0]
        path.write_text(json.dumps([dict(claim=cid,disposition='advisory',reason='fixture source screening')]))
        cli('screen','--run',self.run,'--decisions',str(path));self.assertTrue(cli('status','--run',self.run)['mainline_accepted'])
        path.write_text(json.dumps([dict(attempt=p['attempt'],action='stop-requested',reason='fixture',observed_via='fixture')]))
        cli('closeout','--run',self.run,'--entries',str(path))
    def test_resolution_cli_survives_real_process_readback(self):
        cid=self.setup_findings()[0]; self.promote(cid)
        entry=Path(__file__).resolve().parents[1]/'skill/codex-dynamic-workflow/scripts/cwf.py'
        def command(*args):
            proc=run_subprocess_captured([sys.executable,'-E','-S','-B',str(entry),'--db',str(self.rt.path),*args],
                                        timeout=15)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            return json.loads(proc.stdout)['result']
        command('resolve','--claim',cid,'--outcome','reported','--reason','fixture review deliverable reports issue')
        self.assertTrue(command('finish','--run',self.run)['mainline_accepted'])
        self.assertTrue(command('status','--run',self.run)['mainline_accepted'])
    def test_reopen_cli_keeps_budget_and_requires_changed_bytes(self):
        from cwf_runtime.cli import main
        self.late_setup();(self.root/'a.py').write_text('x=2\n')
        path=self.base/'paths.json';path.write_text('["a.py"]',encoding='utf-8')
        out=io.StringIO();before=self.rt.status(self.run)['budget']
        with contextlib.redirect_stdout(out):
            code=main(['--db',str(self.rt.path),'reopen-supplemental','--run',self.run,
                       '--changed-paths',str(path),'--reason','fixture changed candidate'])
        self.assertEqual(code,0,out.getvalue());self.assertEqual(self.rt.status(self.run)['budget'],before)
        # Reopening does not make unexplained external drift acceptable.
        self.assertFalse(self.rt.status(self.run)['mainline_accepted'])

    def test_fresh_readonly_connection_keeps_screened_acceptance(self):
        p,e=self.late_setup();self.done(p,e,reply(claims=[finding()]))
        self.rt.triage(p['attempt']+'-0','dismissed',reason='Root fixture disproved')
        with Runtime(self.rt.path,read_only=True) as rt:self.assertTrue(rt.status(self.run)['mainline_accepted'])


class FollowupPackageTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)/'package'
        shutil.copytree(Path(__file__).resolve().parents[1],self.root,ignore=shutil.ignore_patterns('.git','__pycache__','.delivery'))
    def tearDown(self):self.t.cleanup()
    def validate(self):
        from scripts.validate_package import validate
        return validate(self.root)
    def test_profile_model_and_effort_must_match_runtime_for_every_profile(self):
        for profile in ('cwf_reader','cwf_writer','cwf_sol_writer','cwf_general','cwf_mechanical'):
            path=self.root/'profiles'/f'{profile}.toml';original=path.read_text()
            for key in ('model','model_reasoning_effort'):
                import re
                with self.subTest(profile=profile,key=key):
                    changed=re.sub(r'^'+key+r' = ".*"',key+' = "invalid-override"',original,flags=re.M)
                    if changed==original:changed=key+' = "invalid-override"\n'+original
                    path.write_text(changed)
                    self.assertTrue(any('runtime/profile/model/effort drift' in e for e in self.validate()))
                    path.write_text(original)
    def test_runtime_astra_effort_default_can_change_without_pinning_profile(self):
        p=self.root/'skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py';s=p.read_text()
        p.write_text(s.replace("'effort': 'high', 'profile': 'cwf_reader'","'effort': 'max', 'profile': 'cwf_reader'",1))
        self.assertEqual(self.validate(),[])
    def test_v41_schema_and_legacy_schema_remain_separate(self):
        base=self.root/'skill/codex-dynamic-workflow/scripts/cwf_runtime'
        self.assertEqual(json.loads((base/'result.schema.json').read_text()),result_schema())
        self.assertEqual(json.loads((base/'result-v41.schema.json').read_text()),result_schema(2))


if __name__=='__main__':unittest.main()
