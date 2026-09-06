"""CLI for a trusted local controller. Agent results cannot issue these commands."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .core import Runtime, WorkflowError, VERSION, loads, mapping
from .executor import execute_one


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
    for name in ('next','status','events','finish','claims','exec-one'):
        c=sub.add_parser(name); c.add_argument('--run',required=True)
        if name=='next': c.add_argument('--backend',required=True,choices=['native','exec'])
        if name=='events': c.add_argument('--after',type=int,default=0)
        if name=='exec-one': c.add_argument('--executable'); c.add_argument('--timeout',type=int,default=600)
    c=sub.add_parser('bind'); c.add_argument('--attempt',required=True); c.add_argument('--external-id',required=True); c.add_argument('--backend',choices=['native','exec'],required=True)
    c=sub.add_parser('complete'); c.add_argument('--attempt',required=True); c.add_argument('--external-id',required=True); c.add_argument('--backend',choices=['native','exec'],required=True); c.add_argument('--result',required=True); c.add_argument('--usage')
    c=sub.add_parser('release'); c.add_argument('--attempt',required=True); c.add_argument('--external-id'); c.add_argument('--confirmed',action='store_true'); c.add_argument('--reason',required=True)
    for name in ('retry','refresh'):
        c=sub.add_parser(name); c.add_argument('--run',required=True); c.add_argument('--node',required=True); c.add_argument('--reason',required=True)
    c=sub.add_parser('resume'); c.add_argument('--run',required=True); c.add_argument('--contract-hash',required=True); c.add_argument('--reason',required=True); c.add_argument('--extend-deadline-seconds',type=int,default=0)
    c=sub.add_parser('cancel'); c.add_argument('--run',required=True); c.add_argument('--reason',required=True)
    c=sub.add_parser('decide'); c.add_argument('--claim',required=True); c.add_argument('--disposition',required=True); c.add_argument('--reason',required=True)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        with Runtime(args.db,initialize=args.command=='init',read_only=args.command in {'status','events','claims'}) as rt:
            op=args.command
            if op=='init': result={'schema':1,'version':VERSION}
            elif op=='create':
                data=read_json(args.plan)
                mapping(data,{'root','goal','backend','bounds','routes','implement','run_id','nodes'},{'root','goal','backend','nodes'},'plan')
                # Invalid initial plans retain a cancelled audit record, never an executable partial run.
                specs=data.pop('nodes'); rid=rt.create(**data)
                try: rt.add(rid,specs,reason='initial explicit plan')
                except Exception:
                    rt.cancel(rid,reason='initial plan rejected; not executable')
                    raise
                result={'run_id':rid}
            elif op=='add': result={'nodes':rt.add(args.run,read_json(args.nodes),reason=args.reason)}
            elif op=='next': result=rt.acquire(args.run,backend=args.backend)
            elif op=='bind': result=rt.bind(args.attempt,args.external_id,backend=args.backend)
            elif op=='complete': result=rt.complete(args.attempt,read_json(args.result),external_id=args.external_id,backend=args.backend,usage=read_json(args.usage) if args.usage else None)
            elif op=='release': result=rt.release(args.attempt,external_id=args.external_id,confirmed=args.confirmed,reason=args.reason)
            elif op=='retry': result=rt.retry(args.run,args.node,reason=args.reason)
            elif op=='refresh': result=rt.refresh(args.run,args.node,reason=args.reason)
            elif op=='resume': result=rt.resume(args.run,contract_hash=args.contract_hash,reason=args.reason,extend_deadline_seconds=args.extend_deadline_seconds)
            elif op=='cancel': result=rt.cancel(args.run,reason=args.reason)
            elif op=='status': result=rt.status(args.run)
            elif op=='events': result=rt.events(args.run,args.after)
            elif op=='finish': result=rt.finish(args.run)
            elif op=='exec-one': result=execute_one(rt,args.run,executable=args.executable,timeout=args.timeout)
            elif op=='decide': result=rt.decide(args.claim,args.disposition,reason=args.reason)
            elif op=='claims':
                rt.run(args.run)
                result=[{**dict(c),'data':loads(c['data'])} for c in rt.conn.execute('SELECT * FROM claims WHERE run_id=?',(args.run,))]
            success = not (op == 'exec-one' and result.get('admitted') and result.get('state') != 'completed')
            print(json.dumps({'ok':success,'result':result},ensure_ascii=False,indent=2)); return 0 if success else 1
    except (WorkflowError,ValueError,OSError,sqlite3.Error,TypeError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False)); return 1

if __name__=='__main__': raise SystemExit(main())
