"""Runtime packaging regressions; uses isolated files, never the user's install."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import install as installer
import policy_reference as compatibility
from validate_package import validate, SKILL
from cwf_runtime import policy, VERSION

class RuntimePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'project'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('reports','.delivery','__pycache__','.git'))
    def tearDown(self): self.temp.cleanup()
    def test_one_authoritative_budget_implementation(self):
        self.assertIs(compatibility.budget_admission,policy.budget_admission)
        self.assertIs(compatibility.permission,policy.permission)
    def test_missing_runtime_module_is_rejected(self):
        (self.root/SKILL/'scripts/cwf_runtime/core.py').unlink()
        self.assertTrue(any('runtime' in e for e in validate(self.root)))
    def test_runtime_version_drift_is_rejected(self):
        p=self.root/SKILL/'scripts/cwf_runtime/core.py'
        s=p.read_text(encoding='utf-8'); p.write_text(re.sub(r"^VERSION = '[0-9.]+'", "VERSION = '0.0.1'", s, count=1, flags=re.M),encoding='utf-8')
        self.assertTrue(any('runtime code version drift' in e for e in validate(self.root)))
    def test_exec_write_capability_cannot_be_silently_enabled(self):
        p=self.root/SKILL/'policy.json'; data=json.loads(p.read_text(encoding='utf-8'))
        data['runtime']['exec_writes']=True; p.write_text(json.dumps(data),encoding='utf-8')
        self.assertTrue(any('runtime identity/backend' in e for e in validate(self.root)))
    def test_bytecode_is_not_installed_as_owned_source(self):
        p=self.root/SKILL/'scripts/cwf_runtime/__pycache__/core.cpython-312.pyc'
        p.parent.mkdir(exist_ok=True); p.write_bytes(b'test cache')
        self.assertFalse(any('__pycache__' in rel or rel.endswith('.pyc') for rel in installer.manifest(self.root)))
    def test_self_contained_installed_entry_without_source_path(self):
        home=Path(self.temp.name)/'standalone-home'; home.mkdir()
        for rel,data in installer.manifest(self.root).items():
            p=home/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
        entry=home/'skills/codex-dynamic-workflow/scripts/cwf.py'
        env=os.environ.copy(); env.pop('PYTHONPATH',None); env['PYTHONDONTWRITEBYTECODE']='1'
        p=subprocess.run([sys.executable,'-B',str(entry),'--version'],cwd=home,env=env,capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout.strip(),VERSION)
        db=home/'state.sqlite'
        p=subprocess.run([sys.executable,'-B',str(entry),'--db',str(db),'init'],cwd=home,env=env,capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(p.returncode,0,p.stderr); self.assertTrue(json.loads(p.stdout)['ok']); self.assertTrue(db.is_file())

if __name__=='__main__': unittest.main()
