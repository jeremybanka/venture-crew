"""Zero-model native Claude 2.1.321 usage observation.

Pinned native get_usage accepts an accountUuid-bound snapshot younger than 60s.
Seeded failure fallback removes limits[]; reject it instead of renewing freshness.
"""
import hashlib
import json
import math
import os
import queue
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from .controller import num


def account_id(account):
    if not isinstance(account,dict) or account.get('apiProvider') != 'firstParty':
        raise ValueError('claude_subscription_account_required')
    identity={k:account.get(k) for k in ('email','organization')}
    if not all(isinstance(v,str) and v.strip() for v in identity.values()):
        raise ValueError('claude_account_identity_missing')
    return 'claude:'+hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


def normalize(account, raw, started_at):
    if not isinstance(account, dict) or account.get('apiProvider') != 'firstParty':
        raise ValueError('claude_subscription_account_required')
    identity = {k: account.get(k) for k in ('email', 'organization')}
    if not all(isinstance(v, str) and v.strip() for v in identity.values()):
        raise ValueError('claude_account_identity_missing')
    if not isinstance(raw, dict) or raw.get('rate_limits_available') is not True:
        raise ValueError('claude_quota_unavailable')
    session = raw.get('session', {})
    if session.get('total_cost_usd') != 0 or session.get('total_api_duration_ms') != 0 or session.get('model_usage') != {}:
        raise ValueError('unexpected_model_usage')
    limits = raw.get('rate_limits')
    if not isinstance(limits, dict) or not isinstance(limits.get('limits'), list) or not limits['limits']:
        raise ValueError('claude_seeded_or_incomplete_quota')
    if not isinstance(limits.get('model_scoped'), list):
        raise ValueError('claude_model_scope_missing')
    windows = {}
    def add(key, w):
        if key in windows or not isinstance(w, dict): raise ValueError('malformed_quota_window')
        used = num(w.get('utilization'), 0, 100)
        reset = w.get('resets_at')
        if reset is None:
            if key != 'five_hour' or used != 0: raise ValueError('missing_window_reset')
            windows[key] = dict(remaining_percent=100, resets_at=None, inactive=True)
        else:
            dt = datetime.fromisoformat(reset.replace('Z','+00:00'))
            if dt.tzinfo is None: raise ValueError('reset_timezone_required')
            windows[key] = dict(remaining_percent=100-used,resets_at=num(dt.timestamp(),1))
    for key in ('five_hour','seven_day'):
        add(key, limits.get(key))
    for key, w in limits.items():
        if key in windows or w is None: continue
        if isinstance(w, dict) and 'utilization' in w and 'resets_at' in w:
            add(key, w)
    for w in limits['model_scoped']:
        label=w.get('display_name') if isinstance(w,dict) else None
        if not isinstance(label,str) or not label.strip(): raise ValueError('model_label_missing')
        add('model:'+label.strip().lower().replace(' ','_'), w)
    # Every native structured limit must agree with its projected window.
    seen = set()
    for w in limits['limits']:
        if not isinstance(w,dict): raise ValueError('malformed_structured_limit')
        kind = w.get('kind')
        if kind == 'session': key = 'five_hour'
        elif kind == 'weekly_all': key = 'seven_day'
        elif kind == 'weekly_scoped':
            scope=w.get('scope') or {}; model=scope.get('model') or {}
            label=model.get('display_name')
            key='model:'+label.strip().lower().replace(' ','_') if isinstance(label,str) else ''
        else: raise ValueError('unknown_structured_limit')
        if key in seen: raise ValueError('duplicate_structured_limit')
        seen.add(key)
        if key not in windows: raise ValueError('unrepresented_scoped_limit')
        reset = w.get('resets_at')
        if reset is not None:
            dt = datetime.fromisoformat(reset.replace('Z','+00:00'))
            if dt.tzinfo is None: raise ValueError('reset_timezone_required')
            reset = num(dt.timestamp(),1)
        if windows[key]['remaining_percent'] != 100-num(w.get('percent'),0,100) or windows[key]['resets_at'] != reset:
            raise ValueError('inconsistent_structured_limit')
    if seen != set(windows): raise ValueError('incomplete_structured_limits')
    # Native successful ISO reset values pass through from the endpoint and
    # jitter around whole seconds between reads. Native header parsing itself
    # rounds seconds. Validate exact projections first, then use that precision
    # minus one second: stable identity and expiry NEVER later than raw evidence.
    raw_reset_times = {key:window['resets_at'] for key,window in windows.items()}
    for window in windows.values():
        if window['resets_at'] is not None:
            window['resets_at'] = math.floor(window['resets_at'] + 0.5) - 1
    return dict(provider='claude',account_id=account_id(account),
                observed_at=started_at-60,account_bound=True,freshness_proven=True,
                usage_allowed=all(w['remaining_percent']>0 for w in windows.values()),
                source='claude-native-get-usage',windows=windows,raw_reset_times=raw_reset_times)


def enforce_windows(sample, observe_only=(), configured=None):
    """Keep expressly exempt model quotas informational, never silently drop new ones."""
    excluded = set(observe_only)
    if excluded - {'model:fable'}: raise ValueError('unsupported_observation_only_window')
    windows = sample['windows']
    if excluded - set(windows): raise ValueError('observation_only_window_missing')
    enforced = {k:v for k,v in windows.items() if k not in excluded}
    if configured is not None and set(enforced) != set(configured):
        raise ValueError('configured_window_set_changed')
    return dict(sample, windows=enforced,
                informational_windows={k:windows[k] for k in excluded},
                usage_allowed=all(w['remaining_percent'] > 0 for w in enforced.values()))


def auth_metadata():
    """Credential stat plus account identity fingerprint, never volatile cache state.

    No credential contents are read. Profile metadata is read only to hash the
    allowlisted identity fields; counters and profile refresh timestamps do not
    affect identity. Not an adversarial local filesystem integrity guarantee.
    """
    config = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home()/'.claude')))
    credentials = config/'.credentials.json'
    profile = config/'.claude.json' if os.environ.get('CLAUDE_CONFIG_DIR') else Path.home()/'.claude.json'
    try:
        st=credentials.stat()
        credential_stamp=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        account=json.loads(profile.read_text()).get('oauthAccount')
        if not isinstance(account,dict): raise ValueError('claude_account_identity_missing')
        identity={k:account.get(k) for k in ('accountUuid','organizationUuid','emailAddress')}
        if not all(isinstance(v,str) and v.strip() for v in identity.values()):
            raise ValueError('claude_account_identity_missing')
    except (OSError,json.JSONDecodeError,AttributeError):
        raise ValueError('claude_account_identity_missing') from None
    return credential_stamp, hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


# Only our fixed validation enum strings may reach observer logs. Never forward
# native errors, filenames, JSON content, identifiers, or arbitrary exceptions.
SAFE_ERRORS = frozenset({
    'claude_account_identity_missing', 'claude_account_metadata_changed',
    'claude_subscription_account_required', 'claude_quota_unavailable',
    'unexpected_model_usage', 'claude_seeded_or_incomplete_quota',
    'claude_model_scope_missing', 'malformed_quota_window', 'missing_window_reset',
    'reset_timezone_required', 'model_label_missing', 'malformed_structured_limit',
    'unknown_structured_limit', 'duplicate_structured_limit', 'unrepresented_scoped_limit',
    'inconsistent_structured_limit', 'incomplete_structured_limits',
    'unsupported_observation_only_window', 'observation_only_window_missing',
    'configured_window_set_changed', 'unverified_claude_native_version',
    'claude_control_timeout', 'claude_control_closed', 'claude_control_failed',
})


def safe_error(error):
    reason = str(error)
    return reason if reason in SAFE_ERRORS else 'collector_error'


class NativeClaude:
    def __init__(self, executable='claude'):
        version=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=15,check=True).stdout.strip()
        if version != '2.1.321 (Claude Code)': raise ValueError('unverified_claude_native_version')
        self.temp=tempfile.TemporaryDirectory(prefix='venture-claude-quota-')
        self.proc=subprocess.Popen([executable,'--print','--input-format','stream-json','--output-format','stream-json',
            '--verbose','--tools','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
            '--no-session-persistence','--setting-sources','','--permission-mode','manual'],
            cwd=self.temp.name,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,start_new_session=True)
        self.inbox=queue.Queue(maxsize=1024); self.seq=0
        self.account=None; self.identity=None
        threading.Thread(target=self._read,daemon=True).start()
    def _read(self):
        try:
            for line in self.proc.stdout:
                if len(line)>2000000: break
                try:self.inbox.put(json.loads(line),timeout=1)
                except ValueError:continue
        finally:
            try:self.inbox.put(None,timeout=1)
            except queue.Full:pass
    def request(self, body):
        self.seq+=1; rid=str(self.seq)
        self.proc.stdin.write(json.dumps(dict(type='control_request',request_id=rid,request=body))+'\n');self.proc.stdin.flush()
        deadline=time.monotonic()+45
        while True:
            left=deadline-time.monotonic()
            if left<=0:raise TimeoutError('claude_control_timeout')
            msg=self.inbox.get(timeout=left)
            if msg is None:raise RuntimeError('claude_control_closed')
            response=msg.get('response',{})
            if msg.get('type')=='control_response' and response.get('request_id')==rid:
                if response.get('subtype')!='success':raise RuntimeError('claude_control_failed')
                return response.get('response',{})
    def observe(self):
        before=auth_metadata()
        if self.account is None:
            init=self.request({'subtype':'initialize'})
            if before != auth_metadata(): raise ValueError('claude_account_metadata_changed')
            self.account=init.get('account'); self.identity=before
        elif before != self.identity:
            raise ValueError('claude_account_metadata_changed')
        started=time.time()
        raw=self.request({'subtype':'get_usage','skip_behaviors':True})
        if before != auth_metadata(): raise ValueError('claude_account_metadata_changed')
        return normalize(self.account,raw,started)
    def current_account_id(self):
        if self.account is None or self.identity != auth_metadata():
            raise ValueError('claude_account_metadata_changed')
        return account_id(self.account)

    def close(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid,signal.SIGTERM)
            try:self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(self.proc.pid,signal.SIGKILL);self.proc.wait()
        self.proc.stdin.close();self.proc.stdout.close();self.temp.cleanup()


def observe(executable='claude', client=None):
    # Reuse the native process so its bearer-keyed endpoint Retry-After/backoff
    # survives. A fresh process per retry bypassed that native traffic protection.
    if client is None:
        owned=NativeClaude(executable)
        try:return observe(client=owned)
        finally:owned.close()
    # A failed request is not retried immediately. The observer schedules the
    # next attempt with backoff while retaining original successful evidence.
    return client.observe()


def persist_sample(path, record):
    """Atomic private normalized evidence, including model-only availability."""
    target=Path(path)
    if not target.is_absolute() or target.is_symlink():
        raise ValueError('absolute_regular_sample_path_required')
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+target.name+'.',dir=target.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(record,f,allow_nan=False)
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
