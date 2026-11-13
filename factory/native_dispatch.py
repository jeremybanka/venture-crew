"""Bounded OpenRig 0.7.3 fresh-seat execution; no automatic migration.

Trust boundary: preflight is an operator-owned live evidence collector, NOT issue
JSON or worker self-attestation. It must read native ownership/settings/hooks and
budget immediately when called, and serialize launch/configuration for this seat.
The collector must hash the real task body and all launch-relevant artifacts into
launch_evidence.context_sha256 (64 lowercase hex). workspace_revision must be an
exact Git commit SHA (40/64 lowercase hex) only for a verified clean tree; for a
dirty tree use a 64-hex digest covering HEAD, index, worktree and relevant untracked
inputs. Paths or claimed hash strings alone are not verification. Both hashes must
be freshly computed/verified under the same settings/workspace serialization.
No production collector is supplied. The injected runner is used by fixture tests.
Use one protected persistent journal per seat; never delete it to retry an unknown
outcome. Native launch has no idempotency key, so this adapter NEVER retries a
recorded attempt. Operator reconciliation must inspect the actual native session.

No guessed turn permit is acquired. Verified native boundary hooks must atomically
admit the real turn before model spending, including automatic startup prompts.
Success here means native launch receipt only, not model/task success or admission.
"""
import hashlib
import json
import re
import os
from pathlib import Path
import subprocess
import tempfile
from .dispatch import plan_dispatch


def run(argv):
    return subprocess.run(argv,text=True,capture_output=True,timeout=150,check=False)


def _check(evidence):
    if not isinstance(evidence,dict): raise ValueError('live_evidence_required')
    args={k:evidence[k] for k in ('task','native','preferences','catalog','statuses','readiness')}
    args.update(current=evidence.get('current'),handover=evidence.get('handover'),
                no_existing_session=evidence.get('no_existing_session',False))
    decision=plan_dispatch(**args)
    if decision['status']!='cold_handoff_planned':raise ValueError(decision['reason'])
    if args['current'] is not None:raise ValueError('existing_session_requires_verified_native_handover')
    selected=decision['route']['selected']; proof=evidence.get('launch_evidence',{})
    seat=args['task']['destination']
    for key in ('model','provider','runtime'):
        if proof.get(key)!=selected[key]:raise ValueError('materialized_route_mismatch')
    if proof.get('seat')!=seat or proof.get('effort')!='high':raise ValueError('materialized_seat_high_effort_required')
    for key in ('native_exact_turn_hook_verified','automatic_startup_admission_verified',
                'settings_and_launch_serialized','permissions_verified','task_context_verified'):
        if proof.get(key) is not True:raise ValueError(key+'_required')
    if proof.get('queue_id')!=args['task']['queue_id']:raise ValueError('task_context_mismatch')
    for field,pattern in (('context_sha256',r'[0-9a-f]{64}'),
                          ('workspace_revision',r'(?:[0-9a-f]{40}|[0-9a-f]{64})')):
        if not isinstance(proof.get(field),str) or not re.fullmatch(pattern,proof[field]):
            raise ValueError('verified_'+field+'_required')
    # Freeze every task/native ownership mapping and launch proof value, not
    # merely the queue id or artifact path. Never retain mutable caller objects.
    fingerprint=hashlib.sha256(json.dumps(
        {'task':args['task'],'native':args['native'],'launch_evidence':proof},
        sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    # Each provider owns its admission gate. Other provider state remains
    # mandatory for cross-provider same-seat permit checks in routing.plan.
    state=args['statuses'][selected['provider']]
    if state.get('admission_open') is not True or not state.get('opening_id'):
        raise ValueError('selected_provider_opening_required')
    expected=proof.get('expected_session_name')
    if not isinstance(expected,str) or not expected.strip():
        raise ValueError('verified_native_session_binding_required')
    return {'seat':seat,'queue_id':args['task']['queue_id'],
            'selected':selected,'opening_id':state['opening_id'],
            'expected_session_name':expected,'context_fingerprint':fingerprint,
            'context_sha256':proof['context_sha256'],
            'workspace_revision':proof['workspace_revision']}



def launch_fresh(*, executable, journal, reason, preflight, runner=run):
    """Perform one verified fresh launch; fail closed before native mutation.

    preflight() supplies plan_dispatch input plus launch_evidence documented in
    _check. A second live collection after native preview must yield same target.
    Never sets model/runtime/permissions, stops occupants, or activates all seats.
    """
    if not Path(executable).is_absolute():raise ValueError('absolute_reviewed_executable_required')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>500:raise ValueError('reason_required')
    path=Path(journal)
    if not path.is_absolute() or path.is_symlink():raise ValueError('absolute_private_journal_required')
    path.parent.mkdir(parents=True,exist_ok=True)
    lock=path.with_name(path.name+'.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        if path.exists():
            return {'status':'reconciliation_required','prior':json.loads(path.read_text()),'launched':False}
        context=_check(preflight())
        seat=context['seat']
        preview=runner([executable,'seat','launch',seat,'--fresh','--plan','--json'])
        parsed=json.loads(preview.stdout)
        if (preview.returncode!=0 or parsed.get('ok') is not True or parsed.get('complete') is not True
                or parsed.get('launchable') is not True or parsed.get('stopRequired') is not False
                or parsed.get('currentOccupant')!='absent' or parsed.get('blockers')!=[]):
            raise ValueError('native_fresh_preview_blocked')
        if parsed.get('sessionName')!=context['expected_session_name']:
            raise ValueError('native_session_identity_missing')
        if _check(preflight())!=context:raise ValueError('live_evidence_changed')
        record={'status':'unknown','context':context,'sessionName':parsed['sessionName'],'receipt':None}
        def save():
            temp_fd,temp=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
            try:
                with os.fdopen(temp_fd,'w') as out:
                    json.dump(record,out);out.flush();os.fsync(out.fileno())
                os.replace(temp,path)
                directory=os.open(path.parent,os.O_RDONLY)
                try:os.fsync(directory)
                finally:os.close(directory)
            finally:
                if os.path.exists(temp):os.unlink(temp)
        save() # durable before any possible model-starting command
        try:
            result=runner([executable,'seat','launch',seat,'--fresh','--reason',reason,'--json'])
            receipt=json.loads(result.stdout)
            if (result.returncode==0 and isinstance(receipt,dict) and receipt.get('ok') is True
                    and receipt.get('sessionName')==parsed['sessionName']
                    and receipt.get('model')==context['selected']['model']):
                record.update(status='native_launch_reported',receipt=receipt)
            else:record['error']='native_launch_unverified_reconcile'
        except Exception as error:record['error']=type(error).__name__
        save();return record
    finally:
        os.close(fd);lock.unlink()
