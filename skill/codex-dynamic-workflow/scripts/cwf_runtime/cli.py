"""CLI for a trusted local controller. Agent results cannot issue these commands."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .core import Runtime, WorkflowError, VERSION, loads, mapping


def read_json(path):
    return loads(Path(path).read_text(encoding='utf-8'))


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version',action='version',version=VERSION)
    p.add_argument('--db',type=Path,required=True)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    c=sub.add_parser('create'); c.add_argument('--plan',required=True)
    c=sub.add_parser('add'); c.add_argument('--run',required=True); c.add_argument('--nodes',required=True); c.add_argument('--reason',required=True)
    for name in ('next','status','events','finish','claims','exec-one','luna-pool'):
        c=sub.add_parser(name); c.add_argument('--run',required=True)
        if name=='next':
            c.add_argument('--backend',required=True,choices=['native','exec'])
            c.add_argument('--host-capacity',type=int); c.add_argument('--host-active',type=int)
            c.add_argument('--mainline-slots-needed',type=int)
        if name=='events': c.add_argument('--after',type=int,default=0)
        if name in {'exec-one','luna-pool'}: c.add_argument('--executable'); c.add_argument('--timeout',type=int,default=600)
        if name=='luna-pool': c.add_argument('--workers',type=int,required=True)
    c=sub.add_parser('bind'); c.add_argument('--attempt',required=True); c.add_argument('--external-id',required=True); c.add_argument('--backend',choices=['native','exec'],required=True)
    c=sub.add_parser('complete'); c.add_argument('--attempt',required=True); c.add_argument('--external-id',required=True); c.add_argument('--backend',choices=['native','exec'],required=True); c.add_argument('--result',required=True); c.add_argument('--usage')
    c=sub.add_parser('release'); c.add_argument('--attempt',required=True); c.add_argument('--external-id'); c.add_argument('--confirmed',action='store_true'); c.add_argument('--reason',required=True)
    c.add_argument('--kind',choices=['host-resource','readonly-turn-completed'],default='host-resource'); c.add_argument('--receipt')
    for name in ('retry','refresh','omit'):
        c=sub.add_parser(name); c.add_argument('--run',required=True); c.add_argument('--node',required=True); c.add_argument('--reason',required=True)
    c=sub.add_parser('resume'); c.add_argument('--run',required=True); c.add_argument('--contract-hash',required=True); c.add_argument('--reason',required=True); c.add_argument('--extend-deadline-seconds',type=int,default=0)
    c=sub.add_parser('cancel'); c.add_argument('--run',required=True); c.add_argument('--reason',required=True)
    c=sub.add_parser('decide'); c.add_argument('--claim',required=True); c.add_argument('--disposition',required=True); c.add_argument('--reason',required=True)
    c=sub.add_parser('triage'); c.add_argument('--claim',required=True); c.add_argument('--disposition',required=True,choices=['dismissed','advisory','promoted','duplicate']); c.add_argument('--reason',required=True); c.add_argument('--target'); c.add_argument('--duplicate-of')
    c=sub.add_parser('screen'); c.add_argument('--run',required=True); c.add_argument('--decisions',required=True)
    c=sub.add_parser('resolve'); c.add_argument('--claim',required=True); c.add_argument('--outcome',required=True,choices=['reported','disproved','fixed','blocking']); c.add_argument('--reason',required=True); c.add_argument('--node')
    c=sub.add_parser('report'); c.add_argument('--attempt',required=True); c.add_argument('--external-id',required=True); c.add_argument('--backend',required=True,choices=['native']); c.add_argument('--report',required=True)
    c=sub.add_parser('reopen-supplemental'); c.add_argument('--run',required=True); c.add_argument('--changed-paths',required=True); c.add_argument('--reason',required=True)
    c=sub.add_parser('closeout'); c.add_argument('--run',required=True); c.add_argument('--entries',required=True)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command in {'exec-one','luna-pool'} or (args.command == 'next' and args.backend != 'native'):
            raise WorkflowError('native-only routing: dispatch Luna and Astra through native host agent tools')
        with Runtime(args.db,initialize=args.command=='init',read_only=args.command in {'status','events','claims'}) as rt:
            op=args.command
            if op=='init': result={'schema':1,'version':VERSION}
            elif op=='create':
                data=read_json(args.plan)
                mapping(data,{'root','goal','backend','bounds','routes','implement','run_id','nodes','capacity_scope','execution_pool','workflow','acceptance_mode'},{'root','goal','backend','nodes'},'plan')
                if data['backend'] != 'native' or data.get('execution_pool') is not None:
                    raise WorkflowError('native-only routing: new controller plans must use backend=native without an exec pool')
                # Invalid initial plans retain a cancelled audit record, never an executable partial run.
                specs=data.pop('nodes'); rid=rt.create(**data)
                try: rt.add(rid,specs,reason='initial explicit plan')
                except Exception:
                    rt.cancel(rid,reason='initial plan rejected; not executable')
                    raise
                result={'run_id':rid}
            elif op=='add': result={'nodes':rt.add(args.run,read_json(args.nodes),reason=args.reason)}
            elif op=='next': result=rt.acquire(args.run,backend=args.backend,host_capacity=args.host_capacity,host_active=args.host_active,mainline_slots_needed=args.mainline_slots_needed)
            elif op=='bind': result=rt.bind(args.attempt,args.external_id,backend=args.backend)
            elif op=='complete': result=rt.complete(args.attempt,read_json(args.result),external_id=args.external_id,backend=args.backend,usage=read_json(args.usage) if args.usage else None)
            elif op=='release': result=rt.release(args.attempt,external_id=args.external_id,confirmed=args.confirmed,reason=args.reason,kind=args.kind,receipt=read_json(args.receipt) if args.receipt else None)
            elif op=='omit': result=rt.omit(args.run,args.node,reason=args.reason)
            elif op=='triage': result=rt.triage(args.claim,args.disposition,reason=args.reason,target=args.target,duplicate_of=args.duplicate_of)
            elif op=='screen': result=rt.screen(args.run,read_json(args.decisions))
            elif op=='resolve': result=rt.resolve(args.claim,args.outcome,reason=args.reason,node=args.node)
            elif op=='report': result=rt.report_findings(args.attempt,read_json(args.report),external_id=args.external_id,backend=args.backend)
            elif op=='reopen-supplemental': result=rt.reopen_supplemental(args.run,read_json(args.changed_paths),reason=args.reason)
            elif op=='closeout': result=rt.closeout(args.run,read_json(args.entries))
            elif op=='retry': result=rt.retry(args.run,args.node,reason=args.reason)
            elif op=='refresh': result=rt.refresh(args.run,args.node,reason=args.reason)
            elif op=='resume': result=rt.resume(args.run,contract_hash=args.contract_hash,reason=args.reason,extend_deadline_seconds=args.extend_deadline_seconds)
            elif op=='cancel': result=rt.cancel(args.run,reason=args.reason)
            elif op=='status': result=rt.status(args.run)
            elif op=='events': result=rt.events(args.run,args.after)
            elif op=='finish': result=rt.finish(args.run)
            elif op=='decide': result=rt.decide(args.claim,args.disposition,reason=args.reason)
            elif op=='claims':
                rt.run(args.run)
                result=[{**dict(c),'data':loads(c['data'])} for c in rt.conn.execute('SELECT * FROM claims WHERE run_id=?',(args.run,))]
            print(json.dumps({'ok':True,'result':result},ensure_ascii=False,indent=2)); return 0
    except (WorkflowError,ValueError,OSError,sqlite3.Error,TypeError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False)); return 1

if __name__=='__main__': raise SystemExit(main())
