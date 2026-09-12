"""Regression from real exec output-format failure; acceptance stays strict."""
import sys, unittest
import test_runtime as initial
from test_runtime import spec, reply
from cwf_runtime import WorkflowError
from cwf_runtime.executor import execute_one, build_prompt, ProcessResult

class LiveContractTests(unittest.TestCase):
    setUp=initial.RuntimeTests.setUp
    tearDown=initial.RuntimeTests.tearDown
    stream=initial.ExecutorTests.stream

    def test_prompt_explicitly_requires_assigned_relative_path_ids(self):
        self.rt.add(self.run,[spec()],reason='test')
        packet=self.rt.acquire(self.run,backend='native')
        prompt=build_prompt(packet)
        self.assertIn('PATH CONTRACT',prompt)
        self.assertIn('["a.py"]',prompt)
        self.assertIn('not an absolute path, line-number suffix',prompt)
        self.assertIn('Check names must exactly match packet.task.checks',prompt)

    def test_invalid_paths_still_fail_but_observed_usage_is_retained(self):
        for path in [str(self.root/'a.py'),'a.py:1-3','file:///a.py']:
            with self.subTest(path=path):
                run=self.rt.create(workflow='legacy', root=self.root,goal='invalid path data',backend='exec')
                self.rt.add(run,[spec()],reason='test')
                def transport(*args,**kw):
                    kw['on_started']('ended-process')
                    return ProcessResult('ended-process',0,self.stream(reply(sources_opened=[path]), usage={'input_tokens':10,'output_tokens':1}),'')
                with self.assertRaises(WorkflowError):
                    execute_one(self.rt,run,executable=sys.executable,transport=transport)
                status=self.rt.status(run)
                self.assertEqual(status['nodes'][0]['state'],'failed')
                self.assertEqual(status['budget']['active_holds'],0)
                self.assertEqual(status['budget']['used'],1)
                self.assertEqual(status['budget']['unknown_usage_attempts'],0)
                self.assertEqual(status['attempts'][0]['usage']['input_tokens'],10)
                self.assertEqual(status['attempts'][0]['usage']['output_tokens'],1)

if __name__=='__main__': unittest.main()
