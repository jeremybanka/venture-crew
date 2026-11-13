"""Pure budget-aware route planning. Never execute a returned plan directly.

preferences maps seat to ordered catalog keys (no default for missing seats).
Catalog entries: verified=True, model=<exact native ID>, provider, runtime.
Provider/runtime pairs are codex/codex and claude/claude-code. Verification is
caller-supplied evidence, not a claim that this module queried a provider.
statuses must cover both providers with admission_open (bool), active_permits
(list). readiness maps runtime to literal True only after native verification.

current=None asserts no previous session; otherwise current identifies the old
session_id and exact model/provider/runtime. A changed route requires handover
{session_id: old ID, stopped: True, checkpoint: {reference: str, durable: True}}.
The caller must actually verify stopped-session and durable checkpoint evidence.
A plan is a snapshot, NOT a permit: revalidate and acquire admission atomically
at launch. This module never releases permits or starts/stops sessions.
"""
PAIRS = {'codex': 'codex', 'claude': 'claude-code'}


def text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1024


def route(value):
    return (isinstance(value, dict) and text(value.get('model'))
            and text(value.get('provider')) and value['provider'] in PAIRS
            and value.get('runtime') == PAIRS[value['provider']])


def plan(seat, preferences, catalog, statuses, readiness, *, current=None, handover=None):
    """Return selected/blocked/wait/handover_required with diagnostic skips."""
    result = {'status': 'blocked', 'seat': seat, 'selected': None,
              'ready_to_launch': False, 'skipped': []}

    def stop(reason, status='blocked'):
        return dict(result, status=status, reason=reason)

    if not text(seat):
        return stop('invalid_seat')
    if not isinstance(statuses, dict):
        return stop('provider_status_unknown')
    # Must inspect both providers even when a seat prefers only one: a hidden
    # active permit must never enable cross-provider concurrency for that seat.
    for provider in PAIRS:
        state = statuses.get(provider)
        if (not isinstance(state, dict) or type(state.get('admission_open')) is not bool
                or not isinstance(state.get('active_permits'), list)):
            return stop('provider_status_unknown:' + provider)
        for permit in state['active_permits']:
            if not isinstance(permit, dict) or not text(permit.get('seat')):
                return stop('malformed_active_permit:' + provider)
            if permit['seat'] == seat:
                return stop('seat_has_active_permit:' + provider, 'wait')
    if not isinstance(preferences, dict) or seat not in preferences:
        return stop('seat_preference_missing')
    choices = preferences[seat]
    if not isinstance(choices, list) or not choices or not all(text(x) for x in choices):
        return stop('invalid_preferences')
    if not isinstance(catalog, dict) or not isinstance(readiness, dict):
        return stop('invalid_catalog_or_readiness')
    if current is not None and (not route(current) or not text(current.get('session_id'))):
        return stop('current_session_unknown')

    for key in choices:
        entry = catalog.get(key)
        reason = None
        if entry is None:
            reason = 'unknown_preference_id'
        elif not isinstance(entry, dict) or entry.get('verified') is not True:
            reason = 'unverified_catalog_entry'
        elif not route(entry):
            reason = 'invalid_model_provider_runtime'
        elif not statuses[entry['provider']]['admission_open']:
            reason = 'provider_closed'
        elif readiness.get(entry['runtime']) is not True:
            reason = 'harness_not_ready'
        if reason:
            result['skipped'].append({'preference': key, 'reason': reason})
            continue
        selected = {'preference': key, **{k: entry[k] for k in ('model','provider','runtime')}}
        result['selected'] = selected
        changed = current is not None and any(current[k] != selected[k] for k in ('model','provider','runtime'))
        if changed:
            checkpoint = handover.get('checkpoint') if isinstance(handover, dict) else None
            if not (isinstance(handover, dict) and handover.get('stopped') is True
                    and handover.get('session_id') == current['session_id']
                    and isinstance(checkpoint, dict) and checkpoint.get('durable') is True
                    and text(checkpoint.get('reference'))):
                return stop('stopped_session_and_durable_checkpoint_required', 'handover_required')
        return dict(result, status='selected', reason='eligible_snapshot_requires_atomic_admission', ready_to_launch=True)
    return stop('no_eligible_preference')
