"""Project-scoped native command hook. Never install/trust itself.

Requires a stable native turn identity for admission and release. A harness
without one stays paused; do not manufacture identity from repeated prompts.
Native hook discovery and blocking behavior must be verified before activation.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
from .controller import Controller


def denied(event, reason):
    message='Wayforge budget paused: '+reason
    if event=='PreToolUse':
        return {'hookSpecificOutput':{'hookEventName':event,'permissionDecision':'deny','permissionDecisionReason':message}}
    if event in ('SessionStart','Stop','PreCompact','PostCompact'):
        return {'continue':False,'stopReason':message}
    return {'decision':'block','reason':message}


def handle(event, payload, c, p, seat, *, require_factory=False):
    if not isinstance(payload,dict) or payload.get('hook_event_name')!=event:
        return denied(event,'event_mismatch')
    if require_factory and not c.status(p).get('opening_id'):
        return denied(event,'paired_factory_opening_required')
    if p=='claude':
        # Native 2.1.321 common input defines prompt_id, not turn_id.
        # Never let a subagent event release or reuse its parent's permit.
        if payload.get('agent_id'):
            return denied(event,'subagent_event_not_admitted')
        payload={**payload, 'turn_id':payload.get('prompt_id')}
    if event=='PreToolUse':
        name=str(payload.get('tool_name','')).rsplit('__',1)[-1].rsplit('.',1)[-1]
        if name in {'Agent','Task','spawn_agent','resume_agent','followup_task','send_input','fork_thread','create_thread','send_message_to_thread'}:
            return denied(event,'use_declared_seats_no_unmetered_children')
        # Check both active permit and current capacity for tool work. This is
        # not a gate on model tokens already in flight.
        session, turn = payload.get('session_id'), payload.get('turn_id')
        if not session or not turn:
            return denied(event,'native_session_and_turn_identity_required')
        status=c.status(p)
        if not status['admission_open']:
            return denied(event,status['gate_reason'])
        if not any(x['seat']==seat and x['session']==session and x['turn']==turn for x in status['active_permits']):
            return denied(event,'active_permit_required')
        return {}
    if event in ('SessionStart','PreCompact','PostCompact'):
        s=c.status(p)
        return {} if s['admission_open'] else denied(event,s['gate_reason'])
    session,turn=payload.get('session_id'),payload.get('turn_id')
    if not session or not turn:
        return denied(event,'native_session_and_turn_identity_required')
    if event in ('Stop','Interrupt'):
        c.release(p,session,turn)
        return {'continue':False} if event=='Stop' else {}
    if event!='UserPromptSubmit': return denied(event,'unsupported_event')
    result=c.admit(p,seat,session,turn)
    if not result['allowed']: return denied(event,result['reason'])
    return {'hookSpecificOutput':{'hookEventName':event,'additionalContext':'One bounded Wayforge phase admitted. No child agents or mid-turn provider switching. Hand off and stop at its boundary.'}}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--provider',required=True,choices=('codex','claude')); p.add_argument('--seat',required=True); p.add_argument('--event',required=True)
    p.add_argument('--db',default=os.environ.get('WAYFORGE_BUDGET_DB',str(Path.home()/'.local/state/wayforge-rig/budget.sqlite3')))
    a=p.parse_args()
    def timeout(*_): raise TimeoutError()
    signal.signal(signal.SIGALRM,timeout); signal.alarm(3)
    try:
        if not Path(a.db).is_file(): raise ValueError('uninitialized_controller')
        raw=sys.stdin.read(1000001)
        if len(raw)>1000000: raise ValueError('oversized_input')
        result=handle(a.event,json.loads(raw),Controller(a.db, readonly=a.event in ('PreToolUse','SessionStart','PreCompact','PostCompact')),a.provider,a.seat,require_factory=True)
    except BaseException as error:
        result=denied(a.event,'controller_unavailable_'+type(error).__name__)
    finally:
        signal.alarm(0)
    print(json.dumps(result,allow_nan=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
