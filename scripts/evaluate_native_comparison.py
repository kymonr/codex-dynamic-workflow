"""Validate paired native-host attestations and summarize measured outcomes.

This passive tool never calls a model. Passing input validation does not authenticate
host attestations or prove causal model-quality improvement. Keep raw captures local.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


class EvidenceError(ValueError):
    pass


def number(value, name, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise EvidenceError(f'invalid measured {name}')
    return value


def digest(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise EvidenceError('expected a lowercase SHA256 fingerprint')
    return value


def capture(root, item):
    if not isinstance(item, dict) or set(item) != {'path','sha256'}:
        raise EvidenceError('capture needs a path and SHA256')
    path=Path(item['path'])
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise EvidenceError('capture must stay in the comparison directory')
    if any(part.lower() in {'.git','.codex'} or part.lower().startswith('.env') for part in path.parts):
        raise EvidenceError('credential/control paths are not captures')
    current=root
    for part in path.parts:
        current=current/part
        if current.is_symlink():
            raise EvidenceError('capture symlinks are not accepted')
    if not current.resolve().is_relative_to(root) or current.name.lower() in {'auth.json','credentials.json'}:
        raise EvidenceError('unsafe capture path')
    if not current.is_file() or not 0 < current.stat().st_size <= 32*1024*1024:
        raise EvidenceError('missing, empty or oversized raw host capture')
    if hashlib.sha256(current.read_bytes()).hexdigest() != digest(item['sha256']):
        raise EvidenceError('raw capture changed')


def ids(value, name):
    if not isinstance(value,list) or any(not isinstance(x,str) or not x.strip() for x in value) or len(value)!=len(set(value)):
        raise EvidenceError(f'{name} requires unique finding IDs')
    return set(value)


def evaluate(data, root):
    if not isinstance(data,dict) or data.get('status') != 'OBSERVED':
        raise EvidenceError('NOT_RUN: actual paired host observations are required')
    pairs=data.get('pairs')
    if not isinstance(pairs,list) or not 1 <= len(pairs) <= 100:
        raise EvidenceError('provide 1..100 paired trials')
    seen=set(); native_ids=set(); rows=[]
    for pair in pairs:
        trial=pair['trial_id']
        if not isinstance(trial,str) or not trial or trial in seen:
            raise EvidenceError('trial IDs must be unique')
        seen.add(trial); metrics={}; identities={}
        for mode in ('astra','astra_luna'):
            arm=pair[mode]
            if arm.get('provenance') != 'native-host' or arm.get('synthetic') is not False:
                raise EvidenceError('synthetic or non-native evidence cannot qualify')
            capture(root,arm['capture'])
            if not isinstance(arm.get('agents'),list) or not arm['agents']:
                raise EvidenceError('actual agent observations are missing')
            supplemental=[]; mainline=[]
            for agent in arm['agents']:
                identity=agent.get('id')
                if not isinstance(identity,str) or not identity or identity in native_ids:
                    raise EvidenceError('native identities must be distinct across trials/arms')
                native_ids.add(identity)
                if agent.get('role') not in {'mainline','supplemental'}:
                    raise EvidenceError('invalid native responsibility')
                if agent.get('status') not in {'completed','interrupted','failed','running'}:
                    raise EvidenceError('unknown observed lifecycle state')
                effective=agent.get('effective')
                requested=agent.get('requested')
                if not isinstance(effective,dict) or not isinstance(requested,dict):
                    raise EvidenceError('effective identity UNKNOWN; not a qualified comparison')
                expected='gpt-6-astra' if agent['role']=='mainline' else 'gpt-5.6-luna'
                if (effective.get('model') != expected or not effective.get('profile')
                        or not effective.get('effort') or any(effective.get(k)!=requested.get(k) for k in ('model','profile','effort'))):
                    raise EvidenceError('model/profile/effort unverified or mismatched')
                if agent['role']=='supplemental':
                    if effective.get('sandbox') != 'read-only':
                        raise EvidenceError('supplemental effective readonly capability is unverified')
                    direction=agent.get('direction')
                    if not isinstance(direction,str) or not direction.strip():
                        raise EvidenceError('supplemental direction is missing')
                    supplemental.append(direction)
                else:
                    mainline.append((effective['model'],effective['effort']))
            if not mainline or (mode=='astra' and supplemental):
                raise EvidenceError('invalid Astra baseline/mainline')
            if mode=='astra_luna' and len(set(supplemental))<3:
                raise EvidenceError('mixed arm needs at least three distinct observed probes')
            identities[mode]=set(mainline)
            start=number(arm['started_at'],'start'); accepted=number(arm['accepted_at'],'acceptance time',nullable=True)
            finished=number(arm['finished_at'],'finish time')
            passed=arm.get('acceptance_passed')
            if type(passed) is not bool or finished < start:
                raise EvidenceError('missing acceptance outcome or invalid finish time')
            if (passed and (accepted is None or not start <= accepted <= finished)) or (not passed and accepted is not None):
                raise EvidenceError('acceptance timestamp does not match the observed outcome')
            tp=ids(arm['verified_findings'],'verified findings'); fp=ids(arm['false_findings'],'false findings')
            missed=ids(arm['missed_findings'],'missed findings')
            if tp & fp or tp & missed or fp & missed:
                raise EvidenceError('finding verdicts conflict')
            metrics[mode]={'acceptance_passed':passed,'elapsed_seconds':(accepted if passed else finished)-start,'true_findings':len(tp),'false_findings':len(fp),
                           'missed_findings':len(missed),'finding_ids':sorted(tp),
                           'triage_seconds':number(arm.get('triage_seconds'),'triage time',nullable=True),
                           'rework_seconds':number(arm.get('rework_seconds'),'rework time',nullable=True),
                           'total_tokens':number(arm.get('total_tokens'),'tokens',nullable=True),
                           'host_resources_released':arm.get('host_resources_released')}
            if arm.get('total_tokens') is not None and type(arm['total_tokens']) is not int:
                raise EvidenceError('observed token count must be an integer or null')
            if type(metrics[mode]['host_resources_released']) not in (bool,type(None)):
                raise EvidenceError('cleanup must be observed true/false or unknown null')
        a=pair['astra'];b=pair['astra_luna']
        if any(digest(a[key]) != digest(b[key]) for key in ('task_sha256','candidate_sha256','acceptance_sha256')):
            raise EvidenceError('paired arms must have identical task, candidate and acceptance')
        if identities['astra'] != identities['astra_luna']:
            raise EvidenceError('mainline model/effort changed across paired arms')
        row={'trial_id':trial,**metrics}
        row['incremental_verified_findings']=sorted(set(b['verified_findings'])-set(a['verified_findings']))
        row['elapsed_delta_seconds']=metrics['astra_luna']['elapsed_seconds']-metrics['astra']['elapsed_seconds']
        rows.append(row)
    return {'status':'ATTESTATIONS_VALIDATED','paired_trials':len(rows),
            'acceptance_pass_delta':sum(int(row['astra_luna']['acceptance_passed'])-int(row['astra']['acceptance_passed']) for row in rows),
            'median_elapsed_delta_seconds':statistics.median(r['elapsed_delta_seconds'] for r in rows),
            'trials':rows,'model_calls_by_evaluator':0,
            'limits':['Raw captures and Root finding verdicts require independent review; hashes are not authentication.',
                      'A validated input is not a live-host test performed by this script.',
                      'Small paired trials do not establish universal quality or cost superiority.']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('observations',type=Path)
    args=parser.parse_args(argv)
    try:
        path=args.observations.resolve();data=json.loads(path.read_text(encoding='utf-8'))
        print(json.dumps(evaluate(data,path.parent),ensure_ascii=False,indent=2));return 0
    except (EvidenceError,OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'NOT_QUALIFIED','reason':str(exc),'model_calls_by_evaluator':0},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
