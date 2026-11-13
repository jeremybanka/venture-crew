"""Operator CLI. All state is runtime data, outside tracked source."""
import argparse
import json
import os
import queue
import time
from pathlib import Path
import signal
import sys
import threading
from .controller import Controller, PROVIDERS


def read_json(path):
    data = sys.stdin.read(1000001) if path == '-' else Path(path).read_text()
    if len(data)>1000000:
        raise ValueError('oversized_input')
    return json.loads(data)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', default=os.environ.get('WAYFORGE_BUDGET_DB',str(Path.home()/'.local/state/wayforge-rig/budget.sqlite3')))
    sub=p.add_subparsers(dest='cmd',required=True)
    for name in ('status','pause'):
        a=sub.add_parser(name); a.add_argument('provider',choices=PROVIDERS)
    a=sub.add_parser('configure'); a.add_argument('provider',choices=PROVIDERS); a.add_argument('--account',required=True); a.add_argument('--floors',required=True,help='JSON object of required window -> remaining percent floor'); a.add_argument('--freshness',type=int,default=300); a.add_argument('--max-active',type=int,default=1); a.add_argument('--reserve-windows',help='JSON list of windows receiving the opening reserve; defaults to all')
    a=sub.add_parser('set-freshness'); a.add_argument('provider',choices=PROVIDERS); a.add_argument('--seconds',type=int,required=True)
    a=sub.add_parser('open-factory'); a.add_argument('--floors',required=True,help='Codex/Claude reserve percentages, e.g. 50/40'); a.add_argument('--reason',required=True)
    a=sub.add_parser('arm'); a.add_argument('provider',choices=PROVIDERS); a.add_argument('--reason',required=True)
    a=sub.add_parser('observe'); a.add_argument('provider',choices=PROVIDERS); a.add_argument('--file',default='-')
    a=sub.add_parser('admit'); a.add_argument('provider',choices=PROVIDERS); a.add_argument('--seat',required=True); a.add_argument('--session',required=True); a.add_argument('--turn',required=True)
    a=sub.add_parser('release'); a.add_argument('provider',choices=PROVIDERS); a.add_argument('--session',required=True); a.add_argument('--turn',required=True); a.add_argument('--reason',default='completed')
    a=sub.add_parser('reconcile-session'); a.add_argument('provider',choices=PROVIDERS); a.add_argument('--session',required=True); a.add_argument('--reason',required=True); a.add_argument('--confirmed-stopped',action='store_true')
    a=sub.add_parser('observe-codex'); a.add_argument('--codex',default='codex'); a.add_argument('--once',action='store_true'); a.add_argument('--interval',type=int,default=60); a.add_argument('--print-only',action='store_true')
    a=sub.add_parser('observe-claude'); a.add_argument('--claude',default='claude'); a.add_argument('--once',action='store_true'); a.add_argument('--interval',type=int,default=300); a.add_argument('--print-only',action='store_true'); a.add_argument('--observe-only-window',action='append',default=[]); a.add_argument('--sample-file')
    a=sub.add_parser('claude-statusline'); a.add_argument('--file',default='-')
    args=p.parse_args()
    try:
        if args.cmd=='arm':
            raise ValueError('use_open_factory')
        if args.cmd=='claude-statusline':
            from .adapters import claude_statusline
            print(json.dumps(claude_statusline(read_json(args.file)),allow_nan=False)); return 0
        c = None if args.cmd in ('observe-codex','observe-claude') and args.print_only else Controller(args.db, readonly=args.cmd=='status')
        if args.cmd=='observe-claude':
            from .native_claude import observe, enforce_windows, safe_error, persist_sample, NativeClaude
            if args.print_only and args.sample_file: raise ValueError('print_only_cannot_write_sample')
            if not 300 <= args.interval <=1800: raise ValueError('interval_must_be_300_to_1800')
            stop=threading.Event()
            signal.signal(signal.SIGTERM,lambda *_:stop.set()); signal.signal(signal.SIGINT,lambda *_:stop.set())
            client=None; failures=0
            try:
                while not stop.is_set():
                    delay=args.interval
                    try:
                        if client is None: client=NativeClaude(args.claude)
                        sample=enforce_windows(observe(client=client),args.observe_only_window,
                            None if args.print_only else c.status('claude')['floors'])
                        result=sample if args.print_only else c.observe('claude',sample)
                        if args.sample_file and result.get('accepted') is True:
                            persist_sample(args.sample_file,{'accepted':True,'sample':sample})
                        # Invalid successful responses cannot erase the historical
                        # successful file, but the controller rejects routing it.
                        print(json.dumps(result,allow_nan=False),flush=True)
                        failures=0
                        if args.once: return 0 if args.print_only or result.get('accepted') else 1
                    except Exception as error:
                        reason=safe_error(error)
                        transient=reason=='claude_seeded_or_incomplete_quota' or isinstance(error,(TimeoutError,queue.Empty))
                        result={'fallback_retained':False,'reason':reason}
                        if transient and not args.print_only:
                            try:
                                result=c.refresh_failed('claude',client.current_account_id(),reason)
                            except Exception as identity_error:
                                transient=False; reason=safe_error(identity_error)
                        if not transient and not args.print_only:
                            c.invalidate('claude',reason)
                        if args.sample_file:
                            # Separate refresh health from last successful quota.
                            persist_sample(args.sample_file+'.refresh.json',dict(result,error=reason))
                        print(json.dumps(dict(result,error=reason)),flush=True)
                        if not transient and client:
                            client.close(); client=None
                        failures+=1
                        delay=min(1800,args.interval * 2**min(failures-1,3))
                        if args.once: return 1
                    deadline=time.monotonic()+delay
                    while not stop.wait(min(15,max(0,deadline-time.monotonic()))):
                        if client is not None and not args.print_only:
                            try:
                                state=c.status('claude')
                                if client.current_account_id()!=state['account']:
                                    raise ValueError('claude_account_metadata_changed')
                                if state['gate_reason'] in ('stale_observation','reset_expired','clock_rollback'):
                                    c.invalidate('claude',state['gate_reason'])
                            except Exception as identity_error:
                                c.invalidate('claude',safe_error(identity_error))
                                client.close();client=None
                        if time.monotonic()>=deadline:break
            finally:
                if client: client.close()
                # Process exit is not quota exhaustion. Durable successful
                # evidence ages naturally; real invalidation remains latched.
            return 0
        if args.cmd=='observe-codex':
            if not 15 <= args.interval <=120:
                raise ValueError('interval_must_be_15_to_120')
            from .native_codex import NativeClient
            from .adapters import codex
            stop=threading.Event()
            signal.signal(signal.SIGTERM,lambda *_:stop.set()); signal.signal(signal.SIGINT,lambda *_:stop.set())
            client=None
            try:
                while not stop.is_set():
                    try:
                        if client is None: client=NativeClient(args.codex,cwd=str(Path.home()))
                        sample=codex(client)
                        result=sample if args.print_only else c.observe('codex',sample)
                        print(json.dumps(result,allow_nan=False),flush=True)
                        if args.once: return 0 if args.print_only or result.get('accepted') else 1
                    except Exception as error:
                        if not args.print_only: c.invalidate('codex','collector_failed')
                        print(json.dumps({'error':type(error).__name__}),flush=True)
                        if client: client.close(); client=None
                        if args.once: return 1
                    stop.wait(args.interval)
            finally:
                if not args.print_only: c.invalidate('codex','observer_stopped')
                if client: client.close()
            return 0
        if args.cmd=='set-freshness':
            c.set_freshness(args.provider,args.seconds); result=c.status(args.provider)
        elif args.cmd=='configure':
            c.configure(args.provider,args.account,json.loads(args.floors),freshness=args.freshness,max_active=args.max_active,reserve_windows=json.loads(args.reserve_windows) if args.reserve_windows is not None else None); result=c.status(args.provider)
        elif args.cmd=='open-factory':
            parts=args.floors.split('/')
            if len(parts)!=2: raise ValueError('floors_require_codex_claude_pair')
            result=c.open_factory([float(x) for x in parts],args.reason)
        elif args.cmd=='pause': c.pause(args.provider); result=c.status(args.provider)
        elif args.cmd=='status': result=c.status(args.provider)
        elif args.cmd=='observe': result=c.observe(args.provider,read_json(args.file))
        elif args.cmd=='admit':
            if not c.status(args.provider).get('opening_id'):
                raise ValueError('paired_factory_opening_required')
            result=c.admit(args.provider,args.seat,args.session,args.turn)
        elif args.cmd=='release': result={'released':c.release(args.provider,args.session,args.turn,args.reason)}
        elif args.cmd=='reconcile-session': result={'reconciled':c.reconcile_session(args.provider,args.session,args.reason,confirmed_stopped=args.confirmed_stopped)}
        print(json.dumps(result,indent=2,allow_nan=False))
        return 2 if result.get('allowed') is False or result.get('accepted') is False or result.get('any_armed') is False else 0
    except Exception as error:
        print(json.dumps({'error':type(error).__name__,'reason':str(error)}),file=sys.stderr)
        return 1

if __name__=='__main__': raise SystemExit(main())
