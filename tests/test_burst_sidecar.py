"""Burst deterministic tests: synthetic host observations, no live model calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
import io
import json
import pathlib
import shutil
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skill/codex-dynamic-workflow'
sys.path.insert(0, str(SKILL / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts'))
import burst_sidecar as burst
import install as installer
from validate_package import validate

NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


def observation():
    return dict(
        observed_at=NOW.isoformat(), mode='explicit-skill-only',
        purpose='preacceptance-review', candidate_id='SYNTHETIC-snapshot',
        source_approved=True, snapshot_isolated=True, backpressure=False,
        provider_quota_available=True,
        host=dict(
            native_available=True, route_available=True,
            profile_name='cwf_burst_grok', profile_model='xai/grok-4.6',
            profile_effort='high', profile_readonly=True,
            capacity=10, active=5, unbound_reserved=0,
            mainline_slots_needed=2, reuse_idle_burst_child=False,
        ),
    )


class BurstTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads((SKILL / 'burst.json').read_text(encoding='utf-8'))
        self.o = observation()

    def decide(self, now=NOW):
        obs = deepcopy(self.o)
        obs['observed_at'] = now.isoformat()
        return burst.decide(self.p, obs, now=now)

    def denied(self, reason):
        result = self.decide()
        self.assertFalse(result['allowed'], result)
        self.assertIn(reason, result['reason'])
        self.assertFalse(result['mainline_blocked'])
        self.assertNotIn('route', result)

    def test_native_optional_route_and_readonly_advice(self):
        before = deepcopy((self.p, self.o))
        result = self.decide()
        self.assertTrue(result['allowed'])
        self.assertEqual(result['route']['model'], 'xai/grok-4.6')
        for key in ('required', 'may_write', 'may_accept', 'mainline_blocked'):
            self.assertFalse(result[key])
        self.assertEqual((self.p, self.o), before)
        self.assertNotIn('stop_at', result)
        self.assertIn('no Burst timer or attempt ceiling', result['enforcement'])

    def test_manual_disable_is_the_only_burst_policy_stop(self):
        self.p['enabled'] = False
        result = burst.decide(self.p, {}, now=NOW)
        self.assertEqual(result['reason'], 'burst-disabled')
        self.p['enabled'] = True
        self.assertTrue(self.decide()['allowed'])

    def test_policy_has_no_expiry_attempt_or_duration_limits(self):
        self.assertEqual(set(self.p), {
            'schema_version', 'enabled', 'activation', 'backend', 'route', 'purposes'})
        self.assertEqual(self.p['schema_version'], 2)
        self.assertEqual(self.p['activation'], 'implicit-and-explicit-skill')
        serialized = json.dumps(self.p)
        for token in ('starts_at', 'expires_at', 'limits', 'max_task_attempts',
                      'max_probe_seconds', 'max_followups'):
            self.assertNotIn(token, serialized)
        for _ in range(250):
            self.assertTrue(self.decide()['allowed'])

    def test_old_time_or_count_fields_are_rejected(self):
        for key, value in (
            ('starts_at', '2026-09-14T00:00:00+08:00'),
            ('expires_at', '2026-09-28T00:00:00+08:00'),
            ('limits', {'max_task_attempts': 4}),
        ):
            policy = deepcopy(self.p); policy[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                burst.validate_policy(policy)

    def test_implicit_is_eligible_but_runtime_cannot_acquire_new_routes(self):
        from cwf_runtime.core import DEFAULT_ROUTES
        old = deepcopy(DEFAULT_ROUTES)
        self.o['mode'] = 'implicit-supplementation'
        self.assertTrue(self.decide()['allowed'])
        for mode in ('implicit', 'runtime', 'unknown'):
            self.o['mode'] = mode
            self.denied('mode-not-eligible')
        self.assertEqual(DEFAULT_ROUTES, old)
        self.assertNotIn('cwf_burst_grok', str(DEFAULT_ROUTES))

    def test_writes_and_final_acceptance_are_not_sidecar_purposes(self):
        for purpose in ('writer', 'final-acceptance', 'release'):
            self.o['purpose'] = purpose
            self.denied('purpose-not-eligible')

    def test_source_backpressure_and_provider_availability(self):
        for key, reason in (
            ('source_approved', 'source-authorization'),
            ('snapshot_isolated', 'snapshot-missing'),
        ):
            self.o = observation(); self.o[key] = False; self.denied(reason)
        self.o = observation(); self.o['backpressure'] = True; self.denied('backpressure')
        self.o = observation(); self.o['provider_quota_available'] = False
        self.denied('provider-quota-unavailable')

    def test_missing_native_and_mismatched_profile_never_fallback(self):
        for key, value, reason in (
            ('native_available', False, 'no CLI/API fallback'),
            ('route_available', False, 'no CLI/API fallback'),
            ('profile_name', 'other-same-model', 'profile-mismatch'),
            ('profile_model', 'grok-4.6', 'profile-mismatch'),
            ('profile_effort', 'max', 'profile-mismatch'),
            ('profile_readonly', False, 'profile-mismatch'),
        ):
            self.o = observation(); self.o['host'][key] = value; self.denied(reason)

    def test_capacity_reserves_mainline_without_a_burst_concurrency_quota(self):
        self.o['host']['capacity'] = None; self.denied('capacity-unknown')
        self.o = observation(); self.o['host'].update(active=8, mainline_slots_needed=2)
        self.denied('mainline-capacity-reserved')
        self.o = observation(); self.o['host']['unbound_reserved'] = 3
        self.denied('mainline-capacity-reserved')
        self.o = observation(); self.o['host'].update(capacity=100, active=80, mainline_slots_needed=5)
        self.assertTrue(self.decide()['allowed'])

    def test_idle_owned_thread_reuse_does_not_require_a_new_slot(self):
        self.o['host'].update(capacity=8, active=7, mainline_slots_needed=1,
                              reuse_idle_burst_child=True)
        result = self.decide()
        self.assertTrue(result['allowed'])
        self.assertTrue(result['reuse_idle_burst_child'])
        self.o['host']['reuse_idle_burst_child'] = False
        self.denied('mainline-capacity-reserved')
        self.o = observation(); self.o['host'].update(active=0, reuse_idle_burst_child=True)
        self.denied('invalid-thread-reuse')

    def test_stale_or_future_observation_cannot_authorize_work(self):
        for delta in (-31, 1):
            self.o['observed_at'] = (NOW + timedelta(seconds=delta)).isoformat()
            result = burst.decide(self.p, self.o, now=NOW)
            self.assertEqual(result['reason'], 'host-observation-stale-or-future')
        self.o['observed_at'] = (NOW - timedelta(seconds=30)).isoformat()
        self.assertTrue(burst.decide(self.p, self.o, now=NOW)['allowed'])

    def test_no_task_or_burst_usage_counters_are_required(self):
        serialized = pathlib.Path(burst.__file__).read_text(encoding='utf-8')
        for token in ('task_used', 'task_pending', 'burst_used', 'burst_pending',
                      'mandatory_reserved', 'followups_used', 'probe_deadline',
                      'task_deadline', 'stop_at'):
            self.assertNotIn(token, serialized)
        self.assertTrue(self.decide()['allowed'])

    def test_readonly_cli_bad_json_no_process_or_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            cfg = root / 'burst.json'; obs = root / 'observations.json'
            policy = deepcopy(self.p); policy['enabled'] = False
            cfg.write_text(json.dumps(policy), encoding='utf-8'); obs.write_text('{}', encoding='utf-8')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            out = io.StringIO()
            with patch('subprocess.Popen') as launch, redirect_stdout(out):
                code = burst.main(['--policy', str(cfg), '--observation', str(obs)])
            self.assertEqual(code, 2); launch.assert_not_called()
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)
            for bad in ('{"a":1,"a":2}', '[]', '{"x":NaN}', 'x' * (burst.MAX_JSON_BYTES + 1)):
                cfg.write_text(bad, encoding='utf-8')
                with self.assertRaises(ValueError):
                    burst.load_object(cfg)

    def test_profiles_and_quality_guidance(self):
        for name, effort in [('cwf_general', 'max'), ('cwf_mechanical', 'medium')]:
            profile = tomllib.loads((ROOT / f'profiles/{name}.toml').read_text(encoding='utf-8'))
            self.assertEqual((profile['model'], profile['model_context_window'], profile['service_tier'],
                              profile['model_reasoning_effort'], profile['sandbox_mode']),
                             ('gpt-5.6-luna--fast', 922000, 'fast', effort, 'read-only'))
        grok = tomllib.loads((ROOT / 'profiles/cwf_burst_grok.toml').read_text(encoding='utf-8'))
        self.assertEqual((grok['model'], grok['model_reasoning_effort'], grok['sandbox_mode']),
                         ('xai/grok-4.6', 'high', 'read-only'))
        doc = (SKILL / 'references/burst.md').read_text(encoding='utf-8')
        for clause in ('no Grok expiry date', 'no per-task attempt ceiling',
                       'no per-probe duration ceiling', 'do NOT consume',
                       'Unlimited turns do not mean unlimited blocking',
                       'automatic implicit Grok probe',
                       'Runtime 4.2.0', 'required independent Astra acceptance'):
            self.assertIn(clause, doc)

    def test_isolated_install_and_negative_package_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory).resolve()
            source = base / 'source'; home = base / 'home'
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(
                '.git', '.delivery', 'reports', '__pycache__'))
            self.assertEqual(validate(source), [])
            home.mkdir(); rel = 'skills/codex-dynamic-workflow/SKILL.md'
            entry = home / rel; entry.parent.mkdir(parents=True)
            entry.write_bytes(b'SYNTHETIC entry')
            state = source / '.delivery/install-state.json'; state.parent.mkdir()
            state.write_text(json.dumps(dict(
                home=str(home), legacy_enabled=False,
                hashes={rel: installer.digest(entry.read_bytes())})), encoding='utf-8')
            (home / 'agents').mkdir()
            protected = {
                home / 'config.toml': b'# SYNTHETIC user config',
                home / 'agents/luna.toml': b'model_context_window = 500000',
            }
            for path, data in protected.items():
                path.write_bytes(data)
            result = installer.install(source, home, apply=True)
            payload = installer.manifest(source, include_legacy=False)
            self.assertEqual(result['verified_files'], len(payload))
            for relpath, data in payload.items():
                self.assertEqual((home / relpath).read_bytes(), data, relpath)
            for path, data in protected.items():
                self.assertEqual(path.read_bytes(), data)
            self.assertEqual(installer.install(source, home)['changes'], [])

            for relpath, old, new in (
                ('profiles/cwf_burst_grok.toml', 'read-only', 'workspace-write'),
                ('profiles/cwf_burst_grok.toml', 'xai/grok-4.6', 'gpt-6-astra'),
                ('profiles/cwf_general.toml', 'model_context_window = 922000',
                 'model_context_window = true'),
                ('profiles/cwf_general.toml', 'gpt-5.6-luna--fast', 'gpt-5.6-luna'),
                ('profiles/cwf_mechanical.toml', 'gpt-5.6-luna--fast', 'gpt-5.6-luna'),
                ('profiles/cwf_general.toml', 'model_context_window = 922000',
                 'model_context_window = 1000000'),
                ('profiles/cwf_mechanical.toml', 'service_tier = "fast"',
                 'service_tier = "default"'),
            ):
                path = source / relpath
                original = path.read_bytes()
                path.write_bytes(original.replace(old.encode(), new.encode()))
                self.assertTrue(validate(source))
                path.write_bytes(original)

            cfg = source / 'skill/codex-dynamic-workflow/burst.json'
            original = cfg.read_bytes()
            bad = json.loads(original)
            bad['expires_at'] = '2030-01-01T00:00:00Z'
            cfg.write_text(json.dumps(bad), encoding='utf-8')
            self.assertTrue(validate(source))
            cfg.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
