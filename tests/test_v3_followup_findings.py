"""Compound cleanup errors and cross-worktree default writer regression."""
import sys, unittest
from unittest.mock import patch
import test_runtime as initial
from test_runtime import spec, reply
from cwf_runtime import WorkflowError
from cwf_runtime import core
from cwf_runtime.executor import execute_one, ProcessResult

class FollowupFindingTests(unittest.TestCase):
    setUp=initial.RuntimeTests.setUp
    tearDown=initial.RuntimeTests.tearDown
    stream=initial.ExecutorTests.stream

    def test_malformed_result_and_unreadable_source_still_release_ended_process(self):
        for failure in [WorkflowError('missing source'),WorkflowError('source exceeds bound'),PermissionError('source denied')]:
            with self.subTest(error=str(failure)):
                run=self.rt.create(workflow='legacy', root=self.root,goal='compound failure',backend='exec')
                self.rt.add(run,[spec()],reason='test')
                original=core.fingerprint; calls=[0]
                def fingerprint(*args,**kw):
                    calls[0]+=1
                    if calls[0]>1: raise failure
                    return original(*args,**kw)
                def transport(*args,**kw):
                    kw['on_started']('test-ended-process')
                    return ProcessResult('test-ended-process',0,self.stream(reply(outcome=[])),'')
                with patch.object(core,'fingerprint',side_effect=fingerprint),self.assertRaises((WorkflowError,OSError)):
                    execute_one(self.rt,run,executable=sys.executable,transport=transport)
                status=self.rt.status(run)
                self.assertEqual(status['budget']['active_holds'],0)
                self.assertEqual(status['budget']['used'],1)
                self.assertEqual(status['nodes'][0]['state'],'interrupted')
                self.assertEqual(self.rt.events(run)[-1]['kind'],'attempt.released')

    def test_different_roots_cannot_bypass_default_single_writer(self):
        second=self.base/'other-worktree'; second.mkdir(); (second/'a.py').write_text('VALUE=3')
        a=self.rt.create(workflow='legacy', root=self.root,goal='first checkout',backend='native',implement=True)
        b=self.rt.create(workflow='legacy', root=second,goal='second checkout',backend='native',implement=True)
        for run in (a,b):
            self.rt.add(run,[spec('w',role='writer',writes=['a.py']),spec('v',role='reviewer',verifies='w',depends=['w'])],reason='test')
        p=self.rt.acquire(a,backend='native'); self.assertTrue(p['admitted'])
        denied=self.rt.acquire(b,backend='native')
        self.assertFalse(denied['admitted'])
        self.assertTrue(any(x['reason']=='source-writer-lock' for x in denied['reasons']))
        self.assertEqual(self.rt.status(b)['budget']['used'],0)
        self.rt.release(p['attempt'],external_id=None,confirmed=True,reason='test host never dispatched')
        self.assertTrue(self.rt.acquire(b,backend='native')['admitted'])

if __name__=='__main__': unittest.main()
