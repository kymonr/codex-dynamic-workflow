from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import policy_reference as rules
import install as installer
from validate_package import validate, SKILL


class PackageTests(unittest.TestCase):
    def test_package_is_valid(self):
        self.assertEqual(validate(ROOT), [])

    def test_core_is_compact(self):
        self.assertLessEqual(len((ROOT/SKILL/'SKILL.md').read_text(encoding='utf-8').splitlines()), 250)

    def test_canonical_name_is_the_only_implicit_entry(self):
        main=(ROOT/SKILL/'SKILL.md').read_text(encoding='utf-8')
        meta=(ROOT/SKILL/'agents/openai.yaml').read_text(encoding='utf-8')
        legacy=(ROOT/'skill/dispatching-native-agents/agents/openai.yaml').read_text(encoding='utf-8')
        self.assertIn('name: codex-dynamic-workflow',main)
        self.assertIn('$codex-dynamic-workflow',meta)
        self.assertIn('allow_implicit_invocation: true',meta)
        self.assertIn('allow_implicit_invocation: false',legacy)

    def test_manifest_installs_canonical_and_legacy_alias(self):
        files=installer.manifest(ROOT)
        self.assertIn('skills/codex-dynamic-workflow/SKILL.md',files)
        self.assertIn('skills/dispatching-native-agents/SKILL.md',files)
        self.assertNotEqual(files['skills/codex-dynamic-workflow/SKILL.md'],
                            files['skills/dispatching-native-agents/SKILL.md'])

    def test_native_and_raw_contracts_remain_visible(self):
        text=(ROOT/SKILL/'SKILL.md').read_text(encoding='utf-8')
        for marker in ['native', 'directly opens', 'UNKNOWN', 'Root also counts as a writer',
                       'No overlapping', 'never CLI children', 'No fixed refuter count']:
            with self.subTest(marker=marker): self.assertIn(marker, text)

    def test_contract_priority_and_future_boundary(self):
        p=json.loads((ROOT/SKILL/'policy.json').read_text())
        self.assertEqual(p['priority'][0:2], ['quality','automation'])
        self.assertIn('automatic-resume',p['future_only'])
        self.assertFalse(p['child_spawn'])
        self.assertFalse(p['overlapping_writers'])

    def test_invalid_budget_bool_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('reports','.delivery','__pycache__'))
            p=root/SKILL/'policy.json';data=json.loads(p.read_text());data['budget']['absolute_child_launches']=True
            p.write_text(json.dumps(data));self.assertTrue(any('positive integers' in e for e in validate(root)))


class MetadataMutationTests(unittest.TestCase):
    def assert_mutation_rejected(self, relative, old, new):
        target=(ROOT/relative).resolve(); original=Path.read_text
        text=original(target,encoding='utf-8'); self.assertEqual(text.count(old),1)
        mutated=text.replace(old,new)
        def read(path,*args,**kwargs):
            return mutated if path.resolve()==target else original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):
            self.assertTrue(validate(ROOT),f'false PASS for {relative}: {new!r}')

    def test_xname_and_suffix_names_are_rejected(self):
        for name in ('codex-dynamic-workflow','dispatching-native-agents'):
            for bad in (f'xname: {name}',f'name: {name}-fake'):
                with self.subTest(name=name,bad=bad):
                    self.assert_mutation_rejected(f'skill/{name}/SKILL.md',f'name: {name}',bad)

    def test_missing_or_duplicate_names_are_rejected(self):
        for name in ('codex-dynamic-workflow','dispatching-native-agents'):
            for replacement in ('',f'name: {name}\nname: {name}'):
                self.assert_mutation_rejected(f'skill/{name}/SKILL.md',f'name: {name}',replacement)

    def test_missing_duplicate_or_wrong_versions_are_rejected(self):
        policy=json.loads((ROOT/SKILL/'policy.json').read_text(encoding='utf-8'))
        for name,suffix in (('codex-dynamic-workflow',''),('dispatching-native-agents','-compat')):
            line='  version: '+json.dumps(policy['skill_version']+suffix)
            for replacement in ('','  xversion: "fake"','  version: "0.0.0"',line+'\n'+line):
                self.assert_mutation_rejected(f'skill/{name}/SKILL.md',line,replacement)

    def test_quoted_booleans_and_duplicate_flags_are_rejected(self):
        for name,value in (('codex-dynamic-workflow','true'),('dispatching-native-agents','false')):
            line=f'  allow_implicit_invocation: {value}'
            for replacement in (f'  allow_implicit_invocation: "{value}"',line+'\n'+line,
                                f'  xallow_implicit_invocation: {value}'):
                self.assert_mutation_rejected(f'skill/{name}/agents/openai.yaml',line,replacement)

    def test_duplicate_policy_groups_are_rejected(self):
        for name,value in (('codex-dynamic-workflow','true'),('dispatching-native-agents','false')):
            self.assert_mutation_rejected(f'skill/{name}/agents/openai.yaml','policy:',
                f'policy:\n  allow_implicit_invocation: {value}\npolicy:')

    def test_bad_delimiters_and_metadata_indent_are_rejected(self):
        self.assert_mutation_rejected(str(SKILL/'SKILL.md'),'---\nname:','name:')
        self.assert_mutation_rejected(str(SKILL/'SKILL.md'),'metadata:','xmetadata:')

    def test_description_is_a_nonempty_string(self):
        path=ROOT/SKILL/'SKILL.md'
        line=next(l for l in path.read_text(encoding='utf-8').splitlines() if l.startswith('description:'))
        for value in ('""','false','"'+('a'*1025)+'"'):
            self.assert_mutation_rejected(str(SKILL/'SKILL.md'),line,'description: '+value)

    def test_invocation_must_match_exactly(self):
        path=str(SKILL/'agents/openai.yaml')
        self.assert_mutation_rejected(path,'$codex-dynamic-workflow','$codex-dynamic-workflow-fake')

    def test_json_duplicate_keys_and_invalid_types_are_rejected(self):
        self.assert_mutation_rejected(str(SKILL/'policy.json'),'"child_spawn": false',
                                     '"child_spawn": true, "child_spawn": false')
        self.assert_mutation_rejected(str(SKILL/'policy.json'),'"budget": {','"budget": null, "unused": {')
        self.assert_mutation_rejected('skill/dispatching-native-agents/policy.json',
                                     '"implicit_invocation": false','"implicit_invocation": "false"')

    def test_yaml_null_is_rejected_but_quoted_null_remains_a_string(self):
        from validate_package import check_frontmatter, check_interface
        version=json.loads((ROOT/SKILL/'policy.json').read_text(encoding='utf-8'))['skill_version']
        for name,suffix,display,implicit in (('codex-dynamic-workflow','','Codex Dynamic Workflow',True),
                ('dispatching-native-agents','-compat','Native Dispatch (deprecated)',False)):
            main_rel=f'skill/{name}/SKILL.md'; main=(ROOT/main_rel).read_text(encoding='utf-8')
            desc=next(l for l in main.splitlines() if l.startswith('description:'))
            meta_rel=f'skill/{name}/agents/openai.yaml';meta=(ROOT/meta_rel).read_text(encoding='utf-8')
            short=next(l for l in meta.splitlines() if l.startswith('  short_description:'))
            for value in ('null','Null','NULL','~'):
                self.assert_mutation_rejected(main_rel,desc,'description: '+value)
                self.assert_mutation_rejected(meta_rel,short,'  short_description: '+value)
            check_frontmatter(main.replace(desc,'description: "null"'),name,version+suffix)
            check_interface(meta.replace(short,'  short_description: "null"'),display,implicit)

    def test_unsupported_yaml_forms_are_rejected_not_guessed(self):
        from validate_package import parse_package_mapping
        for text in ('name: &alias foo','name: |\n  text','name: [foo]',
                     'metadata:\n    version: "2.0.2"','metadata:\n\tversion: "2.0.2"',
                     'name: "foo"\n  version: "2.0.2"'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_package_mapping(text)


class BudgetTests(unittest.TestCase):
    def decide(self, **kw):
        opts=dict(approved=20,reserve=4,absolute=24,used=4,reserve_used=0,strong_used=2,
                  strong_approved=8,economy=False,economy_qualified=True,active=1,capacity=4)
        opts.update(kw);return rules.budget_admission(**opts)

    def test_approved_strong_call_needs_no_question(self):
        self.assertEqual(self.decide().outcome,'allow')

    def test_economy_reserve_is_allowed_inside_ceiling(self):
        self.assertEqual(self.decide(used=20,economy=True).reason,'cumulative-economy-reserve')

    def test_optional_economy_expansion_can_use_reserve_without_pending_checks(self):
        self.assertEqual(self.decide(used=20,economy=True,optional=True).reason,'cumulative-economy-reserve')

    def test_optional_reserve_does_not_skip_unfunded_mandatory_checks(self):
        self.assertEqual(self.decide(used=20,economy=True,optional=True,mandatory_pending=1).reason,
                         'mandatory-reservations-exceed-approved')

    def test_new_approved_allowance_does_not_recharge_prior_reserve(self):
        self.assertEqual(self.decide(approved=22,absolute=26,used=23,reserve_used=2).reason,'approved-allowance')

    def test_absolute_ceiling_stops_even_economy(self):
        self.assertEqual(self.decide(used=24,reserve_used=4,economy=True).outcome,'stop')

    def test_reserve_cannot_raise_ceiling(self):
        with self.assertRaises(ValueError):self.decide(absolute=23)

    def test_strong_expansion_asks(self):
        self.assertEqual(self.decide(used=20).outcome,'ask')

    def test_strong_allowance_applies_before_total_allowance(self):
        self.assertEqual(self.decide(used=10,strong_used=8).reason,'strong-allowance-extension')

    def test_unknown_economy_qualification_blocks(self):
        self.assertEqual(self.decide(economy=True,economy_qualified=False).outcome,'blocked')

    def test_capacity_queues_not_spawns(self):
        self.assertEqual(self.decide(active=4).outcome,'queue')

    def test_preserve_mandatory_total(self):
        self.assertEqual(self.decide(used=19,optional=True,mandatory_pending=1).outcome,'defer')

    def test_preserve_mandatory_strong(self):
        self.assertEqual(self.decide(used=10,strong_used=7,optional=True,mandatory_pending=1,
                                    mandatory_strong_pending=1).reason,'preserve-mandatory-strong-allowance')

    def test_bool_is_not_a_launch_count(self):
        with self.assertRaises(ValueError): self.decide(used=True)

    def test_inflight_and_failure_counts_are_not_refunded(self):
        self.assertEqual(self.decide(used=20,active=0).outcome,'ask')

    def test_no_unaccounted_reserve(self):
        with self.assertRaises(ValueError): self.decide(used=22,reserve_used=0)

    def test_no_per_node_reserve_reset(self):
        self.assertEqual(self.decide(used=23,reserve_used=3,economy=True).outcome,'allow')
        self.assertEqual(self.decide(used=24,reserve_used=4,economy=True).outcome,'stop')


    def test_impossible_total_reservation_blocks_every_admission(self):
        for optional in (False,True):
            with self.subTest(optional=optional):
                self.assertEqual(self.decide(used=19,mandatory_pending=6,optional=optional).reason,
                                 'mandatory-reservations-exceed-absolute')

    def test_impossible_strong_reservation_asks_before_any_admission(self):
        for economy in (False,True):
            self.assertEqual(self.decide(used=10,strong_used=7,mandatory_pending=3,
                                        mandatory_strong_pending=3,economy=economy).reason,
                             'mandatory-reservations-exceed-strong')

    def test_nonoptional_unreserved_work_cannot_spend_reserved_allowance(self):
        self.assertEqual(self.decide(used=19,mandatory_pending=1).outcome,'defer')

    def test_current_mandatory_is_not_double_counted(self):
        self.assertEqual(self.decide(used=19,strong_used=7,mandatory_pending=1,
                                    mandatory_strong_pending=1,consumes_mandatory=True).reason,
                         'approved-allowance')

    def test_mandatory_flag_requires_matching_reservation(self):
        for params in ({'consumes_mandatory':True},
                       {'consumes_mandatory':True,'mandatory_pending':1,'optional':True},
                       {'consumes_mandatory':True,'mandatory_pending':1},
                       {'consumes_mandatory':True,'mandatory_pending':1,
                        'mandatory_strong_pending':1,'economy':True}):
            with self.subTest(params=params),self.assertRaises(ValueError):self.decide(**params)

    def test_economy_reserve_preserves_approved_mandatory_work(self):
        self.assertEqual(self.decide(used=19,mandatory_pending=1,mandatory_strong_pending=1,
                                    economy=True,optional=True).reason,'cumulative-economy-reserve')
        self.assertEqual(self.decide(used=20,reserve_used=1,mandatory_pending=1,
                                    mandatory_strong_pending=1,consumes_mandatory=True).outcome,'allow')

    def test_mandatory_economy_uses_its_approved_reservation(self):
        self.assertEqual(self.decide(used=19,mandatory_pending=1,economy=True,
                                    consumes_mandatory=True).reason,'approved-allowance')

    def test_allowed_admissions_preserve_all_remaining_reservations(self):
        import itertools
        allowed=0
        for approved,reserve,base_used,reserve_used in itertools.product(range(1,4),range(3),range(4),range(3)):
            if base_used>approved or reserve_used>reserve:continue
            for strong_used,pending in itertools.product(range(base_used+1),range(5)):
                for strong_pending,economy,consume in itertools.product(range(pending+1),(False,True),(False,True)):
                    if consume and (not pending or (economy and pending==strong_pending)
                                    or (not economy and not strong_pending)):continue
                    result=rules.budget_admission(approved=approved,reserve=reserve,absolute=approved+reserve,
                        used=base_used+reserve_used,reserve_used=reserve_used,strong_used=strong_used,
                        strong_approved=approved,economy=economy,economy_qualified=True,active=0,capacity=4,
                        mandatory_pending=pending,mandatory_strong_pending=strong_pending,consumes_mandatory=consume)
                    if result.outcome!='allow':continue
                    allowed+=1; after=pending-int(consume)
                    self.assertLessEqual(base_used+reserve_used+1+after,approved+reserve)
                    self.assertLessEqual(base_used+int(result.reason=='approved-allowance')+after,approved)
                    self.assertLessEqual(strong_used+int(not economy)+strong_pending-int(consume and not economy),approved)
        self.assertGreater(allowed,100)


class SafetyAndEvidenceTests(unittest.TestCase):
    def test_low_risk_objective_explorer_can_be_economy(self):
        self.assertTrue(rules.economy_eligible(risk='low',bounded=True,objective_check=True,
                         capability_proven=True,cost_known=True,role='explorer'))

    def test_high_or_unknown_risk_cannot_be_economy(self):
        for risk in ['high','unknown']:
            self.assertFalse(rules.economy_eligible(risk=risk,bounded=True,objective_check=True,
                             capability_proven=True,cost_known=True,role='explorer'))

    def test_cheap_nonwriter_cannot_write(self):
        self.assertFalse(rules.economy_eligible(risk='low',bounded=True,objective_check=True,
                         capability_proven=True,cost_known=True,role='writer'))

    def test_audit_does_not_authorize_write(self):
        self.assertFalse(rules.permission(action='write',explicit=frozenset()))
        self.assertTrue(rules.permission(action='read_only_check',explicit=frozenset()))

    def test_implement_authorizes_local_work_not_git(self):
        flags=frozenset({'implement'})
        self.assertTrue(rules.permission(action='write',explicit=flags))
        for action in ['commit','push','merge','destructive_test','deploy']:
            self.assertFalse(rules.permission(action=action,explicit=flags))

    def test_commit_not_push_or_merge(self):
        flags=frozenset({'implement','commit'})
        self.assertTrue(rules.permission(action='commit',explicit=flags))
        self.assertFalse(rules.permission(action='push',explicit=flags))
        self.assertFalse(rules.permission(action='merge',explicit=flags))

    def test_child_never_publishes(self):
        self.assertFalse(rules.permission(action='push',explicit=frozenset({'push'}),delegated=True))

    def test_case_and_dot_aliases_overlap(self):
        self.assertTrue(rules.overlapping([r'D:\repo\src\A.py'],[r'd:\REPO\src\.\a.py']))

    def test_sibling_names_do_not_false_overlap(self):
        self.assertFalse(rules.overlapping([r'D:\repo\src-a'],[r'D:\repo\src-ab\a.py']))

    def test_same_logical_file_conflicts_across_worktrees(self):
        self.assertTrue(rules.logical_overlap('repo-one',['src/A.py'],'repo-one',['src\\a.py']))

    def test_separate_logical_files_can_be_disjoint(self):
        self.assertFalse(rules.logical_overlap('repo-one',['src/a.py'],'repo-one',['src/b.py']))

    def test_wildcard_ownership_is_not_closed(self):
        with self.assertRaises(ValueError):rules.overlapping([r'D:\repo\*.py'],[])

    def test_relative_ownership_traversal_is_rejected(self):
        with self.assertRaises(ValueError):rules.logical_overlap('r',['../file'],'r',['file'])

    def test_snapshot_drift_blocks_acceptance(self):
        self.assertEqual(rules.acceptance(mandatory_results=['PASS'],source_matches=False,
                         high_risk=False,independently_verified=True).reason,'candidate-drift')

    def test_unknown_or_unrun_mandatory_check_blocks(self):
        for result in ['UNKNOWN','NOT_RUN','FAIL','blocked']:
            self.assertEqual(rules.acceptance(mandatory_results=['PASS',result],source_matches=True,
                             high_risk=False,independently_verified=True).outcome,'blocked')

    def test_high_risk_requires_non_author_check(self):
        self.assertEqual(rules.acceptance(mandatory_results=['PASS'],source_matches=True,
                         high_risk=True,independently_verified=False).outcome,'blocked')

    def test_no_checks_is_not_pass(self):
        self.assertEqual(rules.acceptance(mandatory_results=[],source_matches=True,
                         high_risk=False,independently_verified=True).outcome,'blocked')

    def test_dry_signal_never_waives_mandatory_work(self):
        self.assertTrue(rules.stop_optional(dry_expansions=2,mandatory=False))
        self.assertFalse(rules.stop_optional(dry_expansions=8,mandatory=True))


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name)
        self.root=base/'project';shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('reports','.delivery','__pycache__'))
        self.home=base/'home'
        self.legacy_skill=self.home/'skills/dispatching-native-agents/SKILL.md'
        self.skill=self.home/'skills/codex-dynamic-workflow/SKILL.md'
        self.legacy_skill.parent.mkdir(parents=True);self.legacy_skill.write_bytes(b'old skill\n')
        (self.home/'config.toml').write_bytes(b'model = "keep-me"\n')

    def tearDown(self):self.temp.cleanup()

    def install(self, **options):
        # The migration fixture grants only the literal legacy preimage, once.
        if not (self.root / '.delivery/install-state.json').exists():
            options.setdefault('adopt', {'skills/dispatching-native-agents/SKILL.md':
                                        installer.digest(b'old skill\n')})
        return installer.install(self.root, self.home, **options)


    def test_dry_run_makes_no_install_changes(self):
        self.assertEqual(self.install()['status'],'DRY_RUN')
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')
        self.assertFalse((self.root/'reports').exists())

    def test_install_and_exact_restore(self):
        result=self.install(apply=True)
        self.assertEqual(result['status'],'INSTALLED')
        for rel,data in installer.manifest(self.root).items():
            self.assertEqual((self.home/rel).read_bytes(),data)
        installer.rollback(self.root,self.home,Path(result['receipt']))
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')
        self.assertFalse((self.home/'agents/cwf_reader.toml').exists())

    def test_config_and_unowned_files_preserved(self):
        p=self.legacy_skill.parent/'user-note.txt';p.write_bytes(b'preserve')
        self.install(apply=True)
        self.assertEqual(p.read_bytes(),b'preserve')
        self.assertEqual((self.home/'config.toml').read_bytes(),b'model = "keep-me"\n')

    def test_profile_collision_rejected_before_writes(self):
        p=self.home/'agents/cwf_reader.toml';p.parent.mkdir();p.write_bytes(b'user profile')
        with self.assertRaisesRegex(ValueError,'collision'):self.install(apply=True)
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')

    def test_expected_preimage_detects_drift(self):
        with self.assertRaisesRegex(ValueError,'changed since baseline'):
            self.install(apply=True,expected_skill_sha='0'*64)

    def test_partial_failure_restores_previous_targets(self):
        original=installer.atomic_write;calls=[0]
        def fail_second(path,data):
            calls[0]+=1
            if calls[0]==2: raise OSError('injected second-write failure')
            original(path,data)
        with patch.object(installer,'atomic_write',side_effect=fail_second):
            with self.assertRaises(OSError):self.install(apply=True)
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')
        self.assertFalse((self.home/'agents/cwf_reader.toml').exists())

    def test_interrupt_after_destination_replace_is_recovered(self):
        original=installer.atomic_write; fired=[False]
        def stop_once(path,data):
            original(path,data)
            if path.is_relative_to(self.home) and not fired[0]:
                fired[0]=True;raise KeyboardInterrupt('after destination replace')
        with patch.object(installer,'atomic_write',side_effect=stop_once):
            with self.assertRaises(KeyboardInterrupt):self.install(apply=True)
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')
        self.assertEqual(set(p.relative_to(self.home).as_posix() for p in self.home.rglob('*') if p.is_file()),
                         {'config.toml','skills/dispatching-native-agents/SKILL.md'})

    def test_pending_intent_recovers_after_abrupt_process_exit(self):
        result=self.install(apply=True)
        rp=Path(result['receipt']);receipt=json.loads(rp.read_text())
        for entry in receipt['entries']:
            entry['pending']=True;entry['applied']=False
        rp.write_text(json.dumps(receipt))
        installer.rollback(self.root,self.home,rp)
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')
        self.assertFalse((self.home/'agents/cwf_reader.toml').exists())

    def test_receipt_failure_after_destination_replace_does_not_skip_recovery(self):
        original=installer.atomic_write; changed=[False];failed=[False]
        def fail_receipt_once(path,data):
            if path.name=='receipt.json' and changed[0] and not failed[0]:
                failed[0]=True;raise OSError('receipt unavailable once')
            original(path,data)
            if path.is_relative_to(self.home):changed[0]=True
        with patch.object(installer,'atomic_write',side_effect=fail_receipt_once):
            with self.assertRaises(OSError):self.install(apply=True)
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')
        self.assertFalse((self.home/'agents/cwf_reader.toml').exists())

    def test_second_rollback_is_idempotent(self):
        result=self.install(apply=True);rp=Path(result['receipt'])
        installer.rollback(self.root,self.home,rp)
        self.assertEqual(installer.rollback(self.root,self.home,rp)['status'],'RESTORED')

    def test_rollback_does_not_overwrite_external_edits(self):
        result=self.install(apply=True)
        self.skill.write_bytes(b'external edit')
        with self.assertRaisesRegex(RuntimeError,'external drift'):
            installer.rollback(self.root,self.home,Path(result['receipt']))
        self.assertEqual(self.skill.read_bytes(),b'external edit')

    def test_no_arbitrary_destination(self):
        for path in ['../config.toml','skills/dispatching-native-agents/../../config.toml',
                     'agents/sol.toml','skills/dispatching-native-agents/a:stream']:
            with self.subTest(path=path), self.assertRaises(ValueError):installer.destination(self.home,path)

    def test_no_unproven_new_home(self):
        other=Path(self.temp.name)/'empty-home';other.mkdir()
        with self.assertRaisesRegex(ValueError,'not confirmed'):installer.install(self.root,other,apply=True)

    def test_upgrade_rollback_restores_profile_ownership_for_next_upgrade(self):
        first=self.install(apply=True)
        state=self.root/'.delivery/install-state.json';state_a=state.read_bytes()
        profile=self.root/'profiles/cwf_reader.toml';original=profile.read_text()
        profile.write_text(original+'\n# upgrade B\n')
        second=self.install(apply=True)
        installer.rollback(self.root,self.home,Path(second['receipt']))
        self.assertEqual(state.read_bytes(),state_a)
        profile.write_text(original+'\n# upgrade C\n')
        self.assertEqual(self.install(apply=True)['status'],'INSTALLED')

    def test_rollback_never_overwrites_newer_installation_state(self):
        first=self.install(apply=True)
        profile=self.root/'profiles/cwf_reader.toml';profile.write_text(profile.read_text()+'\n# newer\n')
        self.install(apply=True)
        current=(self.home/'agents/cwf_reader.toml').read_bytes()
        with self.assertRaisesRegex(RuntimeError,'ownership state preserved'):
            installer.rollback(self.root,self.home,Path(first['receipt']))
        self.assertEqual((self.home/'agents/cwf_reader.toml').read_bytes(),current)

    def test_first_install_rollback_removes_its_state_record(self):
        result=self.install(apply=True)
        installer.rollback(self.root,self.home,Path(result['receipt']))
        self.assertFalse((self.root/'.delivery/install-state.json').exists())

    def test_explicit_inplace_mode_installs_and_restores(self):
        result=self.install(apply=True,inplace_skill=True)
        self.assertEqual(self.skill.read_bytes(),(self.root/SKILL/'SKILL.md').read_bytes())
        installer.rollback(self.root,self.home,Path(result['receipt']))
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')

    def test_inplace_refuses_preimage_drift(self):
        with self.assertRaisesRegex(ValueError,'preimage drift'):
            installer.inplace_write(self.legacy_skill,b'new',b'wrong')
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')

    def test_inplace_does_not_replace_locked_skill(self):
        original=installer.atomic_write
        def forbid_skill_replace(path,data):
            if path==self.legacy_skill:raise PermissionError('replacement unavailable')
            original(path,data)
        with patch.object(installer,'atomic_write',side_effect=forbid_skill_replace):
            result=self.install(apply=True,inplace_skill=True)
            installer.rollback(self.root,self.home,Path(result['receipt']))
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')

    def test_partial_inplace_crash_is_not_falsely_reported_restored(self):
        def abrupt(path,data,expected):
            path.write_bytes(b'partial interrupted data')
            raise SystemExit('simulated abrupt interruption')
        with patch.object(installer,'inplace_write',side_effect=abrupt):
            with self.assertRaisesRegex(RuntimeError,'recovery incomplete'):
                self.install(apply=True,inplace_skill=True)
        self.assertEqual(self.legacy_skill.read_bytes(),b'partial interrupted data')
        receipt=json.loads(next((self.root/'reports').glob('install-backup-*/receipt.json')).read_text())
        self.assertEqual(receipt['status'],'rollback-conflict')

    def test_unowned_canonical_collision_is_rejected(self):
        self.skill.parent.mkdir(parents=True)
        self.skill.write_bytes(b'user-owned canonical')
        with self.assertRaisesRegex(ValueError, 'unowned destination collision'):
            self.install(apply=True)
        self.assertEqual(self.skill.read_bytes(), b'user-owned canonical')
        self.assertFalse((self.root/'reports').exists())

    def test_identical_unowned_content_still_needs_adoption(self):
        self.skill.parent.mkdir(parents=True)
        self.skill.write_bytes((self.root/SKILL/'SKILL.md').read_bytes())
        with self.assertRaisesRegex(ValueError, 'unowned destination collision'):
            self.install(apply=True)

    def test_all_managed_kinds_preserve_external_edits(self):
        self.install(apply=True)
        original_state=(self.root/'.delivery/install-state.json').read_bytes()
        for rel in installer.manifest(self.root):
            p=self.home/rel; original=p.read_bytes(); changed=original+b'\nUSER EDIT\n'
            p.write_bytes(changed)
            with self.subTest(path=rel):
                with self.assertRaisesRegex(ValueError, 'externally changed'):
                    self.install(apply=True)
                self.assertEqual(p.read_bytes(), changed)
                self.assertEqual((self.root/'.delivery/install-state.json').read_bytes(), original_state)
            p.write_bytes(original)

    def test_owned_file_deletion_is_not_silently_recreated(self):
        self.install(apply=True)
        p=self.home/'skills/codex-dynamic-workflow/references/evidence.md'; p.unlink()
        with self.assertRaisesRegex(ValueError, 'missing owned destination'):
            self.install(apply=True)
        self.assertFalse(p.exists())

    def test_expected_sha_is_not_ownership_adoption(self):
        with self.assertRaisesRegex(ValueError, 'unowned destination collision'):
            installer.install(self.root,self.home,apply=True,
                              expected_skill_sha=installer.digest(b'old skill\n'))

    def test_explicit_adoption_is_scoped_and_reversible(self):
        self.skill.parent.mkdir(parents=True); self.skill.write_bytes(b'custom skill')
        adopt={'skills/dispatching-native-agents/SKILL.md':installer.digest(b'old skill\n'),
               'skills/codex-dynamic-workflow/SKILL.md':installer.digest(b'custom skill')}
        result=installer.install(self.root,self.home,apply=True,adopt=adopt)
        receipt=json.loads(Path(result['receipt']).read_text(encoding='utf-8'))
        self.assertEqual(receipt['adoptions'],adopt)
        installer.rollback(self.root,self.home,Path(result['receipt']))
        self.assertEqual(self.skill.read_bytes(),b'custom skill')
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')

    def test_adoption_drift_between_precheck_and_plan_is_rejected(self):
        original=installer.read_if_file; reads=[0]
        def racing_read(path):
            if path==self.legacy_skill:
                reads[0]+=1
                if reads[0]==2:path.write_bytes(b'concurrent user edit')
            return original(path)
        with patch.object(installer,'read_if_file',side_effect=racing_read):
            with patch.object(installer,'atomic_write') as write:
                with self.assertRaisesRegex(ValueError,'adoption preimage mismatch during planning'):
                    self.install(apply=True)
                write.assert_not_called()
        self.assertEqual(self.legacy_skill.read_bytes(),b'concurrent user edit')
        self.assertFalse((self.root/'reports').exists())

    def test_stale_adoption_is_rejected_before_writes(self):
        with self.assertRaisesRegex(ValueError, 'adoption preimage mismatch'):
            self.install(apply=True,adopt={'skills/dispatching-native-agents/SKILL.md':'0'*64})
        self.assertEqual(self.legacy_skill.read_bytes(),b'old skill\n')
        self.assertFalse((self.root/'reports').exists())

    def test_adoption_outside_manifest_is_rejected(self):
        for rel in ('config.toml','agents/sol.toml','skills/codex-dynamic-workflow/user.txt'):
            with self.subTest(path=rel),self.assertRaisesRegex(ValueError, 'exact package manifest'):
                self.install(apply=True,adopt={rel:'0'*64})

    def test_adoption_parser_rejects_duplicates_and_invalid_hash(self):
        for items in (['a='+'0'*64,'a='+'1'*64],['a=bad'],['missing-separator']):
            with self.subTest(items=items),self.assertRaises(ValueError):
                installer.parse_adoptions(items)

    def test_drift_is_rejected_even_when_source_matches_external_edit(self):
        self.install(apply=True)
        p=self.root/SKILL/'README.md'; current=p.read_bytes()+b'\nnew text\n'; p.write_bytes(current)
        (self.home/'skills/codex-dynamic-workflow/README.md').write_bytes(current)
        with self.assertRaisesRegex(ValueError,'externally changed'):
            self.install(apply=True)

    def test_idempotent_same_source(self):
        self.install(apply=True)
        self.assertEqual(self.install(apply=True)['changed_files'],0)


if __name__ == '__main__':unittest.main()
