"""Adversarial instruction integration checks; no live model execution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skill/codex-dynamic-workflow'
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_source_manifest import validate


def normalized(path):
    return ' '.join(path.read_text(encoding='utf-8').split())


class SkillAdversarialTests(unittest.TestCase):
    def test_generic_probe_limits_cannot_override_grok_exception(self):
        contracts = {
            'SKILL.md': ('Give each Luna probe', 'Routine Luna probes'),
            'references/supplemental.md': ('give each Luna probe', 'Routine Luna probes'),
            'references/followup.md': ('Every Luna probe',),
            'references/explicit-workflow.md': ('For Astra/Sol/Luna returns',),
        }
        for relative, clauses in contracts.items():
            text = normalized(SKILL / relative)
            with self.subTest(relative=relative):
                for clause in clauses:
                    self.assertIn(clause, text)
                self.assertIn('Grok', text)
                self.assertIn('no workflow-imposed duration or follow-up ceiling', text)
                for stale in ('Give each probe a finite cutoff',
                              'Every probe has an objective scope and finite cutoff',
                              'Routine probes get at most one follow-up'):
                    self.assertNotIn(stale, text)

    def test_routing_and_write_contracts_use_one_root_directed_writer_by_default(self):
        for relative in ('references/host-routing.md', 'references/writes.md'):
            text = normalized(SKILL / relative)
            with self.subTest(relative=relative):
                self.assertIn('current Root', text)
                self.assertIn('one `cwf_sol_writer` child', text)
                self.assertIn('by default', text)
                self.assertIn('parallel', text)
                self.assertIn('Runtime', text)
                self.assertNotIn('Sol Root writes directly by default', text)
        routing = normalized(SKILL / 'references/host-routing.md')
        self.assertIn('never gains dispatch authority', routing)
        self.assertIn('Main-conversation direct writing remains available', routing)
        self.assertIn('A true controller transfer requires explicit user selection and host proof', routing)
        self.assertNotIn('only for admitted Runtime writing or authorized isolated parallel writes', routing)

    def test_runtime_overview_matches_actual_sol_route(self):
        text = normalized(SKILL / 'references/runtime.md')
        self.assertNotIn('the complete mainline uses Astra', text)
        self.assertIn('required non-writer mainline nodes use Astra', text)
        self.assertIn('Sol writer', text)
        self.assertIn('saved contracts retain', text)

    def test_mixed_case_git_directory_is_rejected_before_file_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / '.GiT' / 'config'
            target.parent.mkdir()
            target.write_bytes(b'synthetic control data')
            path = '.GiT/config'
            (root / 'SOURCE_MANIFEST.json').write_text(json.dumps({
                path: hashlib.sha256(target.read_bytes()).hexdigest()
            }), encoding='utf-8')
            errors = validate(root)
            self.assertIn('unsafe/noncanonical', str(errors))


if __name__ == '__main__':
    unittest.main()
