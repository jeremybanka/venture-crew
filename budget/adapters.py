"""Normalize quota sources without inventing identity or cache freshness."""
import hashlib
from datetime import datetime
import time
from .controller import num, ident


def codex(client):
    before = client.request('account/read', {'refreshToken': False})
    response = client.request('account/rateLimits/read', None)
    after = client.request('account/read', {'refreshToken': False})
    if before != after:
        raise ValueError('account_changed_during_read')
    if not isinstance(after, dict) or (after.get('account') or {}).get('type') != 'chatgpt':
        raise ValueError('subscription_account_required')
    if not isinstance(response, dict):
        raise ValueError('missing_quota_response')
    account = response.get('accountId')
    if not isinstance(account, str) or not account.strip():
        raise ValueError('quota_account_identity_missing')
    buckets = response.get('rateLimitsByLimitId')
    if buckets is not None and not isinstance(buckets, dict):
        raise ValueError('malformed_quota_buckets')
    if not buckets:
        single = response.get('rateLimits')
        if not isinstance(single, dict) or not single.get('limitId'):
            raise ValueError('allowance_identity_missing')
        buckets = {single['limitId']: single}
    windows = {}
    allowed = response.get('ordinaryUsageAllowed') is True
    for bucket_id, bucket in buckets.items():
        if not isinstance(bucket, dict):
            raise ValueError('malformed_quota_bucket')
        ident(bucket_id)
        bucket_windows = 0
        allowed = allowed and bucket.get('spendControlReached') is not True and not bucket.get('rateLimitReachedType')
        for name in ('primary','secondary'):
            w = bucket.get(name)
            # Native primary/secondary windows may be omitted or null. Any
            # present non-null value must be a valid window, not silently skipped.
            if w is None:
                continue
            if not isinstance(w, dict):
                raise ValueError('malformed_quota_window')
            bucket_windows += 1
            duration = w.get('windowDurationMins')
            if isinstance(duration, bool) or not isinstance(duration,int) or duration <= 0:
                raise ValueError('invalid_window_duration')
            used = num(w.get('usedPercent'),0,100)
            key = ident(str(bucket_id) + ':' + str(duration))
            if key in windows:
                raise ValueError('duplicate_quota_window')
            windows[key] = dict(remaining_percent=100-used,resets_at=num(w.get('resetsAt'),1))
            allowed = allowed and used < 100
        if not bucket_windows:
            raise ValueError('quota_bucket_has_no_windows')
    if not windows:
        raise ValueError('quota_windows_missing')
    return dict(provider='codex', account_id='codex:'+hashlib.sha256(account.encode()).hexdigest(),
                observed_at=time.time(), account_bound=True, freshness_proven=True,
                usage_allowed=bool(allowed), source='codex-app-server', windows=windows)


def claude_statusline(raw, received_at=None):
    """Observation only. Status-line redraw supplies neither account nor fetch time.

    Do NOT turn the receipt timestamp into source freshness or join a separate
    login lookup to this sample. Such a join would be an assumption, not evidence.
    """
    limits = raw.get('rate_limits') if isinstance(raw, dict) else None
    if not isinstance(limits, dict):
        raise ValueError('claude_rate_limits_missing')
    windows = {}
    for key in ('five_hour','seven_day'):
        w = limits.get(key)
        if not isinstance(w, dict):
            continue
        used = num(w.get('used_percentage',w.get('usedPercent')),0,100)
        reset = w.get('resets_at',w.get('resetsAt'))
        if isinstance(reset, str):
            reset = datetime.fromisoformat(reset.replace('Z','+00:00')).timestamp()
        windows[key] = dict(remaining_percent=100-used,resets_at=num(reset,1))
    return dict(provider='claude', account_id=None, observed_at=None,
                received_at=time.time() if received_at is None else received_at,
                account_bound=False, freshness_proven=False, usage_allowed=False,
                source='claude-statusline', windows=windows)
