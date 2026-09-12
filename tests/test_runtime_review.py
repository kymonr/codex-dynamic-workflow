"""Post-implementation review regressions, separate from the initial suite."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import test_runtime as initial
from test_runtime import spec, reply
from cwf_runtime import WorkflowError
from cwf_runtime.executor import parse_exec, result_schema

class ReviewRegressionTests(unittest.TestCase):
    setUp = initial.RuntimeTests.setUp
    tearDown = initial.RuntimeTests.tearDown
    add = initial.RuntimeTests.add
    acquire = initial.RuntimeTests.acquire
    done = initial.RuntimeTests.done

    def test_hardlinked_source_cannot_alias_unowned_write(self):
        os.link(self.root/'a.py', self.root/'alias.py')
        with self.assertRaisesRegex(WorkflowError, 'hard-linked'):
            self.add(spec())
        self.assertEqual(self.rt.status(self.run)['budget']['used'], 0)

    def test_old_failed_attempt_claim_does_not_inherit_retry_success(self):
        self.add(spec())
        claim = dict(proposition='Old proposal', evidence=['a.py'], existence='supported', applicability='supported', impact='low')
        self.done(result=reply(outcome='failed', checks=[], claims=[claim]))
        old = self.rt.conn.execute('SELECT id FROM claims').fetchone()[0]
        self.rt.retry(self.run, 'n1', reason='explicit readonly retry')
        self.done()
        with self.assertRaisesRegex(WorkflowError, 'historical attempt'):
            self.rt.decide(old, 'ADOPT', reason='must not promote stale attempt')
        self.assertEqual(self.rt.conn.execute('SELECT disposition FROM claims').fetchone()[0], 'UNKNOWN')

    def test_same_native_author_cannot_approve_itself_under_new_node_id(self):
        self.add(spec('target', risk='high'), spec('check', role='verifier', verifies='target', depends=['target']))
        for unused in range(2):
            p = self.acquire()
            self.rt.bind(p['attempt'], 'same-native-agent', backend='native')
            self.rt.complete(p['attempt'], reply(), external_id='same-native-agent', backend='native')
            self.rt.release(p['attempt'], external_id='same-native-agent', confirmed=True, reason='host closed turn')
        with self.assertRaisesRegex(WorkflowError, 'independent'):
            self.rt.finish(self.run)

    def test_postwrite_status_distinguishes_historical_and_invalid_evidence(self):
        run = self.rt.create(workflow='legacy', root=self.root, goal='fix', backend='native', implement=True)
        self.run = run
        self.add(spec('explore'), spec('write', role='writer', writes=['a.py'], depends=['explore']),
                 spec('review', role='reviewer', verifies='write', depends=['write']))
        self.done()
        writer = self.acquire(); (self.root/'a.py').write_text('VALUE = 5\n')
        self.done(writer, reply(changed_files=['a.py']))
        self.rt.refresh(run, 'review', reason='bind decided post-write candidate')
        self.done(); status = self.rt.finish(run)
        self.assertTrue(status['current_evidence_valid'])
        self.assertEqual(status['historical_evidence'], {'explore':['a.py']})
        (self.root/'a.py').write_text('VALUE = 100\n')
        self.assertFalse(self.rt.status(run)['current_evidence_valid'])

    def test_packaged_schema_matches_generated_schema(self):
        import json
        from cwf_runtime import executor
        stored = json.loads(Path(executor.__file__).with_name('result.schema.json').read_text())
        self.assertEqual(stored, result_schema())

    def test_host_reparse_denial_does_not_require_symlink_creation_privilege(self):
        from cwf_runtime.core import regular_path
        from types import SimpleNamespace
        import stat
        with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=1024)):
            with self.assertRaisesRegex(WorkflowError, 'reparse'):
                regular_path(self.root, 'a.py')

if __name__ == '__main__': unittest.main()
