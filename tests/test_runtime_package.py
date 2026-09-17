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
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import install as installer
import policy_reference as compatibility
from validate_package import validate, SKILL
from cwf_runtime import policy, VERSION

def run_subprocess_captured(args, *, env=None, cwd=None, timeout):
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as stdout, \
            tempfile.TemporaryFile(mode='w+', encoding='utf-8') as stderr:
        result=subprocess.run(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=timeout)
        stdout.seek(0); stderr.seek(0)
        return subprocess.CompletedProcess(result.args,result.returncode,stdout.read(),stderr.read())

class RuntimePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'project'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('reports','.delivery','__pycache__','.git'))
    def tearDown(self): self.temp.cleanup()
    def set_skill_version(self, root, version):
        p=root/SKILL/'policy.json'; data=json.loads(p.read_text(encoding='utf-8'))
        data['skill_version']=version; p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        for rel,declared in (('skill/codex-dynamic-workflow/SKILL.md',version),
                             ('skill/dispatching-native-agents/SKILL.md',version+'-compat')):
            p=root/rel; text=p.read_text(encoding='utf-8')
            p.write_text(re.sub(r'(?m)^(  version: ")[^"]+("$)',r'\g<1>'+declared+r'\2',text,count=1),encoding='utf-8')
    def validate_in_memory(self, transform):
        original=Path.read_text
        def read_text(path, *args, **kwargs):
            text=original(path,*args,**kwargs)
            try: relative=path.relative_to(self.root).as_posix()
            except ValueError: return text
            return transform(relative,text)
        with patch.object(Path,'read_text',read_text):
            return validate(self.root)
    def test_one_authoritative_budget_implementation(self):
        self.assertIs(compatibility.budget_admission,policy.budget_admission)
        self.assertIs(compatibility.permission,policy.permission)
    def test_skill_430_with_runtime_420_is_valid(self):
        self.set_skill_version(self.root,'4.3.0')
        self.assertEqual(validate(self.root),[])
    def test_skill_420_with_runtime_420_remains_valid(self):
        self.set_skill_version(self.root,'4.2.0')
        self.assertEqual(validate(self.root),[])
    def test_runtime_version_declaration_is_required_and_well_formed(self):
        for name,value,remove in (('missing',None,True),('null',None,False),
                                  ('integer',420,False),('malformed','4.2',False)):
            root=Path(self.temp.name)/name; shutil.copytree(self.root,root)
            p=root/SKILL/'policy.json'; data=json.loads(p.read_text(encoding='utf-8'))
            if remove: data['runtime'].pop('version')
            else: data['runtime']['version']=value
            data['budget']['approved_child_launches']=27
            p.write_text(json.dumps(data),encoding='utf-8')
            with self.subTest(name=name):
                errors=validate(root)
                self.assertTrue(any('invalid runtime version' in e for e in errors),errors)
                self.assertTrue(any('v4 runtime/policy budget drift' in e for e in errors),errors)
    def test_runtime_declaration_is_required_object(self):
        for name,value,remove in (('missing',None,True),('null',None,False),('list',[],False)):
            root=Path(self.temp.name)/('runtime-'+name); shutil.copytree(self.root,root)
            p=root/SKILL/'policy.json'; data=json.loads(p.read_text(encoding='utf-8'))
            if remove: data.pop('runtime')
            else: data['runtime']=value
            p.write_text(json.dumps(data),encoding='utf-8')
            with self.subTest(name=name):
                self.assertTrue(any('runtime must be an object' in e for e in validate(root)))
    def test_runtime_420_gates_ignore_lower_skill_version(self):
        self.set_skill_version(self.root,'4.0.0')
        variants=(
            ('supported','skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py',
             "'4.1.2', '4.2.0'","'4.1.2'",'supported contract versions drift'),
            ('route','skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py',
             "'writer': {'model': 'gpt-5.6-sol', 'effort': 'high', 'profile': 'cwf_sol_writer'}",
             "'writer': {'model': 'gpt-5.6-sol', 'effort': 'high', 'profile': 'cwf_writer'}",
             'v4.2 fixed route identity drift: writer'),
            ('profile','profiles/cwf_sol_writer.toml','model = "gpt-5.6-sol"',
             'model = "gpt-6-astra"','v4.2 fixed model/profile identity drift'),
            ('budget','skill/codex-dynamic-workflow/policy.json','"approved_child_launches": 28',
             '"approved_child_launches": 27','v4 runtime/policy budget drift: DEFAULTS'),
        )
        for name,rel,old,new,expected in variants:
            root=Path(self.temp.name)/('lower-'+name); shutil.copytree(self.root,root)
            p=root/rel; text=p.read_text(encoding='utf-8'); self.assertIn(old,text)
            p.write_text(text.replace(old,new,1),encoding='utf-8')
            errors=validate(root)
            with self.subTest(name=name):
                self.assertTrue(any(expected in e for e in errors),errors)
                self.assertFalse(any('runtime identity/backend contract drift' in e for e in errors),errors)
    def test_missing_runtime_module_is_rejected(self):
        (self.root/SKILL/'scripts/cwf_runtime/core.py').unlink()
        self.assertTrue(any('runtime' in e for e in validate(self.root)))
    def test_runtime_version_drift_is_rejected(self):
        p=self.root/SKILL/'scripts/cwf_runtime/core.py'
        s=p.read_text(encoding='utf-8'); p.write_text(re.sub(r"^VERSION = '[0-9.]+'", "VERSION = '0.0.1'", s, count=1, flags=re.M),encoding='utf-8')
        self.assertTrue(any('runtime code version drift' in e for e in validate(self.root)))
    def test_current_runtime_version_must_be_supported(self):
        p=self.root/SKILL/'policy.json'; data=json.loads(p.read_text(encoding='utf-8'))
        data['runtime']['supported_contract_versions'].remove('4.2.0')
        p.write_text(json.dumps(data),encoding='utf-8')
        p=self.root/SKILL/'scripts/cwf_runtime/core.py'; text=p.read_text(encoding='utf-8')
        p.write_text(text.replace(", '4.2.0'}","}"),encoding='utf-8')
        self.assertTrue(any('current runtime version missing from supported contracts' in e
                            for e in validate(self.root)))
    def test_runtime_declared_v2_cannot_disable_42_safety_checks(self):
        flexible={'profiles/cwf_reader.toml','profiles/cwf_writer.toml','profiles/cwf_sol_writer.toml'}
        def mutate(relative,text):
            if relative=='skill/codex-dynamic-workflow/policy.json':
                data=json.loads(text);data['runtime']['version']='2.0.0';data['runtime']['exec_writes']=True
                return json.dumps(data)
            if relative in flexible:return text+'\nmodel_reasoning_effort = "high"\n'
            return text
        errors=self.validate_in_memory(mutate)
        self.assertTrue(any('runtime version drift' in e for e in errors),errors)
        self.assertTrue(any('runtime identity/backend contract drift' in e for e in errors),errors)
        self.assertTrue(any('flexible profile pins effort' in e for e in errors),errors)
    def test_runtime_declared_412_cannot_disable_42_route_checks(self):
        def mutate(relative,text):
            if relative=='skill/codex-dynamic-workflow/policy.json':
                data=json.loads(text);data['runtime']['version']='4.1.2';return json.dumps(data)
            if relative=='skill/codex-dynamic-workflow/scripts/cwf_runtime/core.py':
                text=text.replace("VERSION = '4.2.0'","VERSION = '4.1.2'",1)
                return text.replace("'writer': {'model': 'gpt-5.6-sol', 'effort': 'high', 'profile': 'cwf_sol_writer'}",
                                    "'writer': {'model': 'gpt-6-astra', 'effort': 'high', 'profile': 'cwf_writer'}",1)
            return text
        errors=self.validate_in_memory(mutate)
        self.assertTrue(any('runtime version drift' in e for e in errors),errors)
        self.assertTrue(any('runtime code version drift' in e for e in errors),errors)
        self.assertTrue(any('v4.2 fixed route identity drift: writer' in e for e in errors),errors)
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
        p=run_subprocess_captured([sys.executable,'-E','-S','-B',str(entry),'--version'],cwd=home,env=env,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(p.stdout.strip(),VERSION)
        db=home/'state.sqlite'
        p=run_subprocess_captured([sys.executable,'-E','-S','-B',str(entry),'--db',str(db),'init'],cwd=home,env=env,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr); self.assertTrue(json.loads(p.stdout)['ok']); self.assertTrue(db.is_file())

if __name__=='__main__': unittest.main()
