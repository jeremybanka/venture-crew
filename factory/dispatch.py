"""Cold native handoff planning, never model launch or queue mutation."""
import re
from routing.routing import plan

TOKEN=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$')

def plan_dispatch(*, task, native, preferences, catalog, statuses, readiness, current=None, handover=None, no_existing_session=False, model_snapshot=None):
    # Native ownership/claimed status must be checked from actual queue immediately
    # before execution; issue content cannot supply this evidence.
    if not isinstance(task,dict) or not isinstance(native,dict): raise ValueError('task_and_native_evidence_required')
    for key in ('queue_id','source','destination','seat','target_repo','body_file'):
        if not isinstance(task.get(key),str) or not task[key]: raise ValueError('missing_'+key)
    for key in ('queue_id','source','destination','target_repo'):
        if not TOKEN.fullmatch(task[key]): raise ValueError('invalid_'+key)
    if not task['body_file'].startswith('/') or '\x00' in task['body_file']: raise ValueError('absolute_body_file_required')
    if (native.get('queue_id')!=task['queue_id'] or native.get('owner')!=task['source']
            or native.get('caller')!=task['source'] or native.get('state')!='in-progress'):
        return {'status':'blocked','reason':'native_claimed_ownership_required','argv':None}
    if native.get('seat_bindings',{}).get(task['seat']) != task['destination']:
        return {'status':'blocked','reason':'verified_seat_destination_binding_required','argv':None}
    if current is None and (no_existing_session is not True or handover is not None):
        return {'status':'blocked','reason':'explicit_session_evidence_required','argv':None}
    if current is not None and no_existing_session is not False:
        return {'status':'blocked','reason':'conflicting_session_evidence','argv':None}
    if task.get('scope_approved') is not True or task.get('workspace_registered') is not True:
        return {'status':'blocked','reason':'scope_and_owned_workspace_required','argv':None}
    decision=plan(task['seat'],preferences,catalog,statuses,readiness,current=current,handover=handover,model_snapshot=model_snapshot)
    if decision['status']!='selected': return {'status':'blocked','reason':decision['reason'],'route':decision,'argv':None}
    return {'status':'cold_handoff_planned','route':decision,'launch_authorized':False,
            'argv':['rig','queue','handoff',task['queue_id'],'--to',task['destination'],
                    '--target-repo',task['target_repo'],'--body-file',task['body_file'],'--no-nudge','--json'],
            'requirements':['Execute only as actual claimed native owner; never set another seat identity',
                            'After handoff, recheck selected native runtime/model/effort and exact turn admission',
                            'Cold handoff is not a launched or completed task']}
