"""Read-only Burst admission advice; NOT a dispatcher, ledger, timer or quota cap.

Root supplies truthful live observations immediately before native dispatch. The
helper never calls models, starts processes, modifies host settings, writes accounting
state, imposes a Burst attempt count, or imposes a Burst wall-clock limit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 65536
PURPOSES = frozenset({
    'design-challenge', 'cross-module-analysis', 'preacceptance-review',
    'stalled-diagnosis', 'durable-evidence',
})
POLICY_KEYS = frozenset({
    'schema_version', 'enabled', 'activation', 'backend', 'route', 'purposes',
})


def object_keys(value: Any, keys: set[str] | frozenset[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f'{label}: missing or unexpected fields')
    return value


def integer(value: Any, label: str, minimum: int = 0, maximum: int = 1000000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{label}: expected integer in [{minimum}, {maximum}]')
    return value


def boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f'{label}: expected boolean')
    return value


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or '\x00' in value:
        raise ValueError(f'{label}: expected bounded nonempty text')
    return value


def timestamp(value: Any, label: str) -> datetime:
    text(value, label)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f'{label}: explicit timezone required')
    return parsed.astimezone(timezone.utc)


def unique_pairs(pairs: list[tuple]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def load_object(path: Path) -> dict:
    with path.open('rb') as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError('JSON input too large')
    value = json.loads(
        data.decode('utf-8'), object_pairs_hook=unique_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON number')),
    )
    if not isinstance(value, dict):
        raise ValueError('JSON root must be an object')
    return value


def validate_policy(policy: dict) -> None:
    object_keys(policy, POLICY_KEYS, 'burst policy')
    if type(policy['schema_version']) is not int or policy['schema_version'] != 2:
        raise ValueError('unsupported burst schema')
    boolean(policy['enabled'], 'enabled')
    if policy['activation'] != 'implicit-and-explicit-skill' or policy['backend'] != 'native':
        raise ValueError('burst requires implicit or explicit Skill-only native dispatch')
    route = object_keys(policy['route'], {'model', 'profile', 'effort'}, 'route')
    for key in ('model', 'profile', 'effort'):
        text(route[key], key)
    if route != {'model': 'xai/grok-4.6', 'profile': 'cwf_burst_grok', 'effort': 'high'}:
        raise ValueError('burst route identity drift')
    purposes = policy['purposes']
    if (not isinstance(purposes, list) or not purposes
            or any(not isinstance(p, str) or p not in PURPOSES for p in purposes)
            or len(set(purposes)) != len(purposes)):
        raise ValueError('invalid or duplicate burst purposes')


def decide(policy: dict, observation: dict, *, now: datetime | None = None) -> dict:
    """Evaluate one optional native turn without reserving or charging a quota."""
    validate_policy(policy)
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now requires timezone')
    now = now.astimezone(timezone.utc)
    common = dict(
        mainline_blocked=False, required=False, may_write=False, may_accept=False,
        checked_at=now.isoformat(),
        policy_sha256=hashlib.sha256(json.dumps(
            policy, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
            allow_nan=False).encode('utf-8')).hexdigest(),
        enforcement='advice-only; no Burst timer or attempt ceiling; no reservation',
    )

    def deny(reason: str) -> dict:
        return dict(common, allowed=False, reason=reason)

    if not policy['enabled']:
        return deny('burst-disabled')

    observation = object_keys(observation, {
        'mode', 'purpose', 'candidate_id', 'observed_at', 'source_approved',
        'snapshot_isolated', 'backpressure', 'provider_quota_available', 'host',
    }, 'observation')
    if observation['mode'] not in {'implicit-supplementation', 'explicit-skill-only'}:
        return deny('mode-not-eligible; Runtime route unchanged')
    if observation['purpose'] not in policy['purposes']:
        return deny('purpose-not-eligible')
    text(observation['candidate_id'], 'candidate_id')
    observed_at = timestamp(observation['observed_at'], 'observed_at')
    if not timedelta(0) <= now - observed_at <= timedelta(seconds=30):
        return deny('host-observation-stale-or-future')
    for key in ('source_approved', 'snapshot_isolated', 'backpressure', 'provider_quota_available'):
        boolean(observation[key], key)
    if not observation['source_approved'] or not observation['snapshot_isolated']:
        return deny('source-authorization-or-snapshot-missing')
    if observation['backpressure']:
        return deny('mainline-backpressure')
    if not observation['provider_quota_available']:
        return deny('provider-quota-unavailable')

    host = object_keys(observation['host'], {
        'native_available', 'route_available', 'profile_name', 'profile_model',
        'profile_effort', 'profile_readonly', 'capacity', 'active',
        'unbound_reserved', 'mainline_slots_needed', 'reuse_idle_burst_child',
    }, 'host')
    for key in ('native_available', 'route_available', 'profile_readonly', 'reuse_idle_burst_child'):
        boolean(host[key], key)
    if not host['native_available'] or not host['route_available']:
        return deny('native-route-unavailable; no CLI/API fallback')
    if (host['profile_name'] != policy['route']['profile']
            or host['profile_model'] != policy['route']['model']
            or host['profile_effort'] != policy['route']['effort']
            or not host['profile_readonly']):
        return deny('effective-profile-mismatch')
    for key in ('capacity', 'active', 'unbound_reserved', 'mainline_slots_needed'):
        if host[key] is None:
            return deny('host-capacity-unknown')
        integer(host[key], key)
    if host['active'] > host['capacity']:
        raise ValueError('inconsistent host observations')

    reuse = host['reuse_idle_burst_child']
    if reuse and host['active'] < 1:
        return deny('invalid-thread-reuse')
    new_slots = 0 if reuse else 1
    reserve = max(1, host['mainline_slots_needed'])
    if host['active'] + host['unbound_reserved'] + reserve + new_slots > host['capacity']:
        return deny('mainline-capacity-reserved')

    return dict(
        common, allowed=True, reason='eligible-not-dispatched',
        route=dict(policy['route']), candidate_id=observation['candidate_id'],
        reuse_idle_burst_child=reuse,
        next_action='Root rechecks live state then uses the native OpenCodex subagent tool',
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'burst.json')
    parser.add_argument('--observation', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = decide(load_object(args.policy), load_object(args.observation))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['allowed'] else 2
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        print(json.dumps(dict(
            allowed=False, mainline_blocked=False, error=str(exc),
            enforcement='advice-only; no Burst timer or attempt ceiling',
        ), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
