"""Regressions for the independent v3 review's five concrete counterexamples."""
import json, signal, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import test_runtime as initial
from test_runtime import spec, reply
from cwf_runtime import WorkflowError
from cwf_runtime.core import dump
from cwf_runtime.executor import ProcessResult, parse_exec, execute_one, run_owned
import cwf_runtime.executor as executor

class IndependentFindingTests(unittest.TestCase):
    setUp=initial.RuntimeTests.setUp
    tearDown=initial.RuntimeTests.tearDown
    add=initial.RuntimeTests.add
    acquire=initial.RuntimeTests.acquire
    done=initial.RuntimeTests.done
    stream=initial.ExecutorTests.stream

    def test_two_reviewed_write_stages_preserve_each_candidate_gate(self):
        self.run=self.rt.create(root=self.root,goal='two scoped writes',backend='native',implement=True)
        self.add(spec('w1',role='writer',writes=['a.py']),spec('v1',role='reviewer',verifies='w1',depends=['w1']),
                 spec('w2',role='writer',writes=['a.py'],depends=['v1']),spec('v2',role='reviewer',verifies='w2',depends=['w2']))
        p=self.acquire(); (self.root/'a.py').write_text('VALUE=5\n'); self.done(p,reply(changed_files=['a.py']))
        self.rt.refresh(self.run,'v1',reason='stage one actual post-write candidate'); self.done()
        self.rt.refresh(self.run,'w2',reason='stage two starts from reviewed stage one')
        p=self.acquire(); (self.root/'a.py').write_text('VALUE=6\n'); self.done(p,reply(changed_files=['a.py']))
        self.rt.refresh(self.run,'v2',reason='stage two actual post-write candidate'); self.done()
        result=self.rt.finish(self.run)
        self.assertEqual(result['status'],'completed'); self.assertTrue(result['current_evidence_valid'])
        self.assertIn('v1',result['historical_evidence'])
        (self.root/'a.py').write_text('OUTSIDE=99')
        self.assertFalse(self.rt.status(self.run)['current_evidence_valid'])

    def test_review_can_depend_on_historical_explorer_and_current_writer(self):
        self.run=self.rt.create(root=self.root,goal='fix',backend='native',implement=True)
        self.add(spec('explore'),spec('write',role='writer',writes=['a.py'],depends=['explore']),
                 spec('review',role='reviewer',verifies='write',depends=['explore','write']))
        self.done(); p=self.acquire(); (self.root/'a.py').write_text('VALUE=5\n')
        self.done(p,reply(changed_files=['a.py']))
        self.rt.refresh(self.run,'review',reason='actual final candidate')
        self.assertEqual(self.done()[0]['node_id'],'review')
        self.assertEqual(self.rt.finish(self.run)['status'],'completed')

    def test_deletion_is_recorded_partial_not_completed_or_replayed(self):
        self.run=self.rt.create(root=self.root,goal='scoped write',backend='native',implement=True)
        self.add(spec('write',role='writer',writes=['a.py']),spec('review',role='reviewer',verifies='write',depends=['write']))
        p=self.acquire(); self.assertFalse(p['permissions']['delete_files'])
        (self.root/'a.py').unlink()
        unused,unused,outcome=self.done(p,reply(changed_files=['a.py']))
        self.assertEqual(outcome['state'],'partial')
        saved=json.loads(self.rt.node(self.run,'write')['result'])
        self.assertEqual(saved['blocked_effects'],['deletion:a.py'])
        self.assertFalse((self.root/'a.py').exists())
        with self.assertRaises(WorkflowError): self.rt.finish(self.run)
        with self.assertRaises(WorkflowError): self.rt.retry(self.run,'write',reason='do not replay')

    def test_truncated_new_turn_and_misordered_final_cannot_borrow_terminal(self):
        message={'type':'item.completed','item':{'type':'agent_message','text':dump(reply())}}
        cases=[self.stream()+'\n'+dump({'type':'turn.started'})+'\n'+dump(message),
               dump({'type':'turn.started'})+'\n'+dump({'type':'turn.completed'})+'\n'+dump(message),
               dump(message)+'\n'+dump({'type':'turn.completed'}),
               dump({'type':'turn.started'})+'\n'+dump(message)]
        for data in cases:
            with self.subTest(data=data),self.assertRaises(WorkflowError): parse_exec(data,0)

    def test_malformed_result_fields_fail_and_release_confirmed_executor(self):
        bad=[reply(outcome=[]),reply(outcome={}),reply(checks=[{'name':'inspect','status':[]}]),
             reply(claims=[{'proposition':'x','evidence':['a.py'],'existence':[], 'applicability':'supported','impact':'low'}])]
        for index,payload in enumerate(bad):
            run=self.rt.create(root=self.root,goal='bad payload '+str(index),backend='exec')
            self.rt.add(run,[spec()],reason='protocol test')
            def transport(*args,**kw):
                kw['on_started']('fake-terminal-process')
                return ProcessResult('fake-terminal-process',0,self.stream(payload),'')
            with self.subTest(index=index),self.assertRaises(WorkflowError):
                execute_one(self.rt,run,executable=sys.executable,transport=transport)
            status=self.rt.status(run)
            self.assertEqual(status['nodes'][0]['state'],'failed')
            self.assertEqual(status['budget']['active_holds'],0)
            self.assertEqual(status['budget']['used'],1)

    def test_posix_normal_exit_always_cleans_descendant_group(self):
        proc=MagicMock(); proc.pid=112233; proc.returncode=0
        proc.communicate.return_value=(b'{}',b''); proc.poll.return_value=0
        calls=[]
        def group(pid,sig):
            calls.append((pid,sig))
            if sig==0: raise ProcessLookupError('exact group gone')
        host=SimpleNamespace(name='posix',killpg=group)
        with patch.object(executor,'os',host),patch.object(executor,'signal',SimpleNamespace(SIGKILL=9)),patch.object(executor.subprocess,'Popen',return_value=proc):
            result=run_owned(['harmless'],self.root,'data',timeout=10,on_started=lambda pid:None,cancelled=lambda:False)
        self.assertEqual(result.returncode,0)
        self.assertEqual(calls,[(112233,9),(112233,0)])

    def test_unconfirmed_cleanup_never_returns_successful_transport(self):
        proc=MagicMock(); proc.pid=112233; proc.returncode=0
        proc.communicate.return_value=(b'{}',b''); proc.poll.return_value=0
        host=SimpleNamespace(name='posix',killpg=lambda *args:None)
        with patch.object(executor,'os',host),patch.object(executor.subprocess,'Popen',return_value=proc),patch.object(executor,'_cleanup_owned',side_effect=OSError('unconfirmed tree')):
            with self.assertRaisesRegex(OSError,'unconfirmed tree'):
                run_owned(['harmless'],self.root,'data',timeout=10,on_started=lambda pid:None,cancelled=lambda:False)

if __name__=='__main__': unittest.main()
