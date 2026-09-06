"""Regression cases from the external review; no live model calls."""
import json
import sys
import unittest
from unittest.mock import patch

import test_runtime as initial
import test_contracts as package
from test_runtime import spec, reply
from cwf_runtime import Runtime, WorkflowError
from cwf_runtime import core
from cwf_runtime.executor import execute_one, ProcessResult, parse_exec


class RuntimeRepairTests(unittest.TestCase):
    setUp = initial.RuntimeTests.setUp
    tearDown = initial.RuntimeTests.tearDown
    stream = initial.ExecutorTests.stream

    def graph(self, reverse=False):
        self.run = self.rt.create(root=self.root, goal='create then review', backend='native', implement=True)
        nodes = [spec('w', role='writer', writes=['new.py']),
                 spec('r', role='reviewer', sources=['a.py','new.py'], depends=['w'], verifies='w')]
        self.rt.add(self.run, list(reversed(nodes)) if reverse else nodes, reason='regression')

    def writer(self, create=True, release=True):
        p = self.rt.acquire(self.run, backend='native')
        self.assertEqual(p['node_id'], 'w')
        self.rt.bind(p['attempt'], 'writer', backend='native')
        if create: (self.root/'new.py').write_text('VALUE=9\n')
        self.rt.complete(p['attempt'], reply(changed_files=['new.py'] if create else []), external_id='writer', backend='native')
        if release: self.rt.release(p['attempt'], external_id='writer', confirmed=True, reason='test host closed')
        return p

    def test_created_file_requires_refresh_then_independent_review_and_reopen(self):
        self.graph(reverse=True)
        self.writer()
        denied = self.rt.acquire(self.run, backend='native')
        self.assertFalse(denied['admitted'])
        self.assertIn('explicit refresh', str(denied))
        self.rt.refresh(self.run, 'r', reason='bind created candidate')
        p = self.rt.acquire(self.run, backend='native')
        self.rt.bind(p['attempt'], 'reviewer', backend='native')
        self.rt.complete(p['attempt'], reply(sources_opened=['a.py','new.py']), external_id='reviewer', backend='native')
        self.rt.release(p['attempt'], external_id='reviewer', confirmed=True, reason='test host closed')
        self.assertEqual(self.rt.finish(self.run)['status'], 'completed')
        with Runtime(self.db, read_only=True) as reopened:
            self.assertTrue(reopened.status(self.run)['current_evidence_valid'])

    def test_refresh_rejects_pending_or_unreleased_writer(self):
        self.graph()
        with self.assertRaisesRegex(WorkflowError, 'completed reconciled writer'):
            self.rt.refresh(self.run, 'r', reason='too soon')
        self.writer(release=False)
        with self.assertRaisesRegex(WorkflowError, 'completed reconciled writer'):
            self.rt.refresh(self.run, 'r', reason='writer still held')

    def test_missing_or_externally_changed_creation_cannot_refresh(self):
        self.graph(); self.writer(create=False)
        with self.assertRaisesRegex(WorkflowError, 'missing source'):
            self.rt.refresh(self.run, 'r', reason='writer did not create')
        (self.root/'new.py').write_text('external creation\n')
        with self.assertRaisesRegex(WorkflowError, 'candidate drift'):
            self.rt.refresh(self.run, 'r', reason='external creation is not writer evidence')

    def test_missing_source_exception_is_confined_to_verified_writer_scope(self):
        self.run = self.rt.create(root=self.root, goal='bound missing paths', backend='native', implement=True)
        w = spec('w', role='writer', writes=['new.py'])
        for bad in [spec('r', sources=['new.py']),
                    spec('r', role='reviewer', sources=['other.py'], depends=['w'], verifies='w')]:
            with self.assertRaisesRegex(WorkflowError, 'missing source'):
                self.rt.add(self.run, [w,bad], reason='invalid missing source')
        self.assertEqual(self.rt.status(self.run)['nodes'], [])

    def test_existing_writer_source_cannot_be_deleted_to_get_deferred_binding(self):
        self.run = self.rt.create(root=self.root, goal='existing source binding', backend='native', implement=True)
        self.rt.add(self.run, [spec('w', role='writer', writes=['b.py'])], reason='writer baseline')
        (self.root/'b.py').unlink()
        with self.assertRaisesRegex(WorkflowError, 'missing source'):
            self.rt.add(self.run, [spec('r',role='reviewer',sources=['a.py','b.py'],depends=['w'],verifies='w')], reason='must not defer existing source')

    def test_terminal_permission_error_releases_and_preserves_parsed_usage(self):
        run = self.rt.create(root=self.root, goal='post-transport read denied', backend='exec')
        self.rt.add(run, [spec()], reason='regression')
        usage = {'input_tokens':12,'output_tokens':3}
        original = core.fingerprint
        ended = [False]
        def fingerprint(*args, **kwargs):
            if ended[0]: raise PermissionError('post-transport source denied')
            return original(*args, **kwargs)
        def transport(*args, **kwargs):
            kwargs['on_started']('ended-process'); ended[0] = True
            return ProcessResult('ended-process',0,self.stream(usage=usage),'')
        with patch.object(core,'fingerprint',side_effect=fingerprint), self.assertRaises(PermissionError):
            execute_one(self.rt,run,executable=sys.executable,transport=transport)
        status = self.rt.status(run)
        self.assertEqual(status['budget']['active_holds'],0)
        self.assertEqual(status['budget']['used'],1)
        self.assertEqual(status['attempts'][0]['state'],'interrupted')
        self.assertEqual(status['attempts'][0]['usage'],usage)
        self.assertEqual(self.rt.events(run)[-1]['data']['usage'],usage)

    def test_ordinary_value_error_and_controller_interrupt_release_after_transport(self):
        for error in (ValueError('large integer conversion'), KeyboardInterrupt('controller stopped')):
            run = self.rt.create(root=self.root, goal='terminal parse failure', backend='exec')
            self.rt.add(run,[spec()],reason='regression')
            def transport(*args, **kwargs):
                kwargs['on_started']('ended-process')
                return ProcessResult('ended-process',0,self.stream(),'')
            with patch('cwf_runtime.executor.parse_exec',side_effect=error), self.assertRaises(type(error)):
                execute_one(self.rt,run,executable=sys.executable,transport=transport)
            self.assertEqual(self.rt.status(run)['budget']['active_holds'],0)
            self.assertEqual(self.rt.status(run)['budget']['used'],1)

    def test_jsonl_unicode_separators_are_string_content(self):
        for char in ('\u0085','\u2028','\u2029'):
            for newline in ('\n','\r\n'):
                with self.subTest(char=ascii(char),newline=ascii(newline)):
                    payload = reply(summary='before'+char+'after')
                    parsed,_ = parse_exec(self.stream(payload).replace('\n',newline),0)
                    self.assertEqual(parsed,payload)


class InstallerRepairTests(unittest.TestCase):
    setUp = package.InstallationTests.setUp
    tearDown = package.InstallationTests.tearDown
    install = package.InstallationTests.install

    def test_removed_manifest_path_blocks_unchanged_changed_and_missing_owned_file(self):
        self.install(apply=True)
        relative = 'skills/codex-dynamic-workflow/retired.py'
        target = self.home/relative
        state_path = self.root/'.delivery/install-state.json'
        state = json.loads(state_path.read_text(encoding='utf-8'))
        state['hashes'][relative] = package.installer.digest(b'old contents')
        state_path.write_text(json.dumps(state),encoding='utf-8')
        before = state_path.read_bytes()
        receipts = set((self.root/'reports').iterdir())
        for contents in (b'old contents',b'edited contents',None):
            if contents is None: target.unlink()
            else: target.write_bytes(contents)
            for apply in (False,True):
                with self.subTest(contents=contents,apply=apply), self.assertRaisesRegex(ValueError,'retired.py'):
                    self.install(apply=apply)
                self.assertEqual(state_path.read_bytes(),before)
                self.assertEqual(set((self.root/'reports').iterdir()),receipts)
                self.assertEqual(target.read_bytes() if target.exists() else None,contents)
