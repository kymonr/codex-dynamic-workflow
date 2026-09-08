"""Native-only entrypoints preserve old records without creating CLI model work."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_runtime as initial
from test_runtime import spec
from cwf_runtime import cli


class NativeOnlyDispatchTests(unittest.TestCase):
    setUp = initial.RuntimeTests.setUp
    tearDown = initial.RuntimeTests.tearDown

    def command(self, *args, db=None):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(['--db', str(db or self.db), *args])
        return code, json.loads(output.getvalue())

    def test_model_commands_refuse_before_db_or_process_creation(self):
        absent = self.base/'absent.sqlite'
        for args in (('exec-one','--run','legacy'), ('luna-pool','--run','legacy','--workers','3')):
            with self.subTest(args=args), patch('subprocess.Popen') as launch:
                code, result = self.command(*args, db=absent)
                self.assertEqual(code, 1); self.assertIn('native-only', result['error'])
                self.assertFalse(absent.exists()); launch.assert_not_called()

    def test_exec_admission_refuses_without_consuming_or_rewriting_legacy_run(self):
        run = self.rt.create(workflow='legacy', root=self.root, goal='historic exec record', backend='exec')
        self.rt.add(run, [spec()], reason='test historical record')
        before = self.rt.run(run); events = self.rt.events(run)
        code, result = self.command('next','--run',run,'--backend','exec')
        self.assertEqual(code, 1); self.assertIn('native-only', result['error'])
        self.assertEqual(self.rt.run(run), before); self.assertEqual(self.rt.events(run), events)

    def test_new_exec_and_pool_plans_are_rejected_without_new_runs(self):
        before = self.rt.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        for fields in ({'backend':'exec'}, {'backend':'native','execution_pool':'luna'}):
            path = self.base/'plan.json'
            path.write_text(json.dumps(dict(root=str(self.root),goal='test',nodes=[spec()],**fields)),encoding='utf-8')
            code, result = self.command('create','--plan',str(path))
            self.assertEqual(code, 1); self.assertIn('native-only', result['error'])
            self.assertEqual(self.rt.conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0], before)

    def test_explicit_legacy_native_luna_plan_admits_through_native_bridge(self):
        path = self.base/'native.json'
        path.write_text(json.dumps(dict(root=str(self.root),goal='ordinary native investigation',backend='native',workflow='legacy',
                                       bounds={'strong_approved':0},nodes=[spec(ordinary_qualified=True)])),encoding='utf-8')
        code, result = self.command('create','--plan',str(path)); self.assertEqual(code, 0)
        run = result['result']['run_id']
        code, result = self.command('next','--run',run,'--backend','native'); self.assertEqual(code, 0)
        packet = result['result']
        self.assertTrue(packet['admitted']); self.assertEqual(packet['backend'],'native')
        self.assertEqual(packet['route']['model'],'gpt-5.6-luna'); self.assertEqual(packet['route']['effort'],'max')

    def test_historical_exec_status_is_still_readable(self):
        run = self.rt.create(workflow='legacy', root=self.root, goal='historical inspection', backend='exec')
        before = self.rt.run(run)
        code, result = self.command('status','--run',run)
        self.assertEqual(code, 0); self.assertEqual(result['result']['backend'],'exec')
        self.assertEqual(self.rt.run(run), before)

    def test_legacy_model_smokes_refuse_before_output_creation(self):
        project = Path(__file__).resolve().parents[1]
        for name in ('verify_installed_exec_smoke.py','verify_installed_luna_pool.py'):
            with self.subTest(name=name):
                output = self.base/(name+'-output')
                result = subprocess.run([sys.executable,'-B',str(project/'scripts'/name),
                                         '--skill-dir',str(project/'skill/codex-dynamic-workflow'),
                                         '--output-dir',str(output),'--executable',sys.executable],
                                        capture_output=True,text=True,encoding='utf-8',timeout=15)
                self.assertEqual(result.returncode,1); self.assertIn('native-only',result.stderr)
                self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
