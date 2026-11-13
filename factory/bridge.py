"""Cold queue bridge. Native queue is authoritative; this is a retry journal.

Never nudges/launches a worker, invents a source seat, or interprets issue text as
permission. Use only a reviewed installed clean OpenRig executable. Unknown
outcomes keep the SAME native create id; never blindly enqueue a second item.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def run(argv):
    return subprocess.run(argv, text=True, capture_output=True, timeout=30, check=False)


def cold_enqueue(*, executable, argv, body, body_file, journal, runner=run):
    """Execute only a fixed cold queue-create shape from the trusted intake planner."""
    if not Path(executable).is_absolute() or not Path(body_file).is_absolute():
        raise ValueError('absolute_runtime_and_body_paths_required')
    expected = ['queue','create']
    if argv[:2] != expected or '--no-nudge' not in argv or '--json' not in argv:
        raise ValueError('cold_create_only')
    allowed = {'--destination','--body-file','--id','--summary','--target-repo'}
    fields = {}; i = 2
    while i < len(argv):
        flag = argv[i]
        if flag in ('--no-nudge','--json'):
            i += 1; continue
        if flag not in allowed or flag in fields or i+1 >= len(argv):
            raise ValueError('unexpected_queue_argument')
        fields[flag] = argv[i+1]; i += 2
    if set(fields) != allowed or fields['--body-file'] != str(body_file):
        raise ValueError('incomplete_cold_create')
    if not all(isinstance(v,str) and v and '\x00' not in v for v in fields.values()):
        raise ValueError('invalid_queue_value')
    # No shell and no --source: native authenticated context owns provenance.
    path=Path(journal); path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or Path(body_file).is_symlink(): raise ValueError('symlink_not_allowed')
    lock=path.with_suffix(path.suffix+'.lock')
    body_path=Path(body_file)
    body_lock=body_path.with_suffix(body_path.suffix+'.lock')
    paths=[p.resolve() for p in (path,lock,body_path,body_lock)]
    if len(set(paths)) != len(paths): raise ValueError('body_and_journal_paths_must_be_distinct')
    body_path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    body_fd=None
    digest=hashlib.sha256(json.dumps({'argv':argv,'body':body},sort_keys=True).encode()).hexdigest()
    try:
        body_fd=os.open(body_lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        prior=json.loads(path.read_text()) if path.exists() else None
        if prior and (prior.get('digest') != digest or prior.get('id') != fields['--id']):
            raise ValueError('intake_changed_reconcile_existing_item')
        if prior:
            if prior.get('state') == 'submitted': return prior
            return dict(prior,state='unknown',error='prior_attempt_requires_native_reconciliation')
        def atomic_write(target,content):
            temp=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,prefix='.'+target.name+'.',delete=False) as f:
                    temp=Path(f.name);f.write(content);f.flush();os.fsync(f.fileno())
                temp.replace(target)
                directory=os.open(target.parent,os.O_RDONLY)
                try: os.fsync(directory)
                finally: os.close(directory)
            finally:
                if temp is not None and temp.exists(): temp.unlink()
        atomic_write(body_path,body)
        def save(value):
            atomic_write(path,json.dumps(value,indent=2)+'\n')
        record={'id':fields['--id'],'digest':digest,'state':'unknown','receipt':None}
        save(record) # Before subprocess: even a crash must retain native retry identity.
        try: result=runner([executable,*argv])
        except Exception as e:
            record['error']=type(e).__name__;save(record);return record
        if result.returncode == 0:
            try: receipt=json.loads(result.stdout)
            except (ValueError,TypeError): receipt=None
            # CLI success is submission evidence, not worker activation/acceptance.
            if isinstance(receipt,dict) and receipt.get('qitemId') == fields['--id']:
                record.update(state='submitted',receipt=receipt)
            else: record['error']='invalid_native_receipt'
        else: record['error']='native_nonzero_outcome_requires_reconciliation'
        save(record);return record
    finally:
        if body_fd is not None: os.close(body_fd);body_lock.unlink()
        os.close(fd);lock.unlink()
