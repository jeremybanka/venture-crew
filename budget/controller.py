"""Fail-closed, transactional admission; not an account-wide spending cap.

Floors are percentages remaining, never summed between providers/windows.
Unknown/missing identity, stale samples or resets cannot reopen admission.
Only sanitized quota metadata is retained. No model calls or credential reads.
"""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

PROVIDERS = ('codex', 'claude')
ID = re.compile(r'^[A-Za-z0-9_.:@/-]{1,256}$')


def ident(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('invalid_identifier')
    return value


def num(value, low=0, high=1e15):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('invalid_number')
    return float(value)


def provider(value):
    if value not in PROVIDERS:
        raise ValueError('invalid_provider')
    return value


class Controller:
    def __init__(self, path, clock=time.time, *, readonly=False):
        self.path, self.clock = Path(path), clock
        self.readonly = readonly
        if self.path.is_symlink():
            raise ValueError('state_symlink_not_allowed')
        if readonly:
            if not self.path.is_file():
                raise ValueError('uninitialized_controller')
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        with self.tx() as db:
            db.execute('CREATE TABLE IF NOT EXISTS providers (provider TEXT PRIMARY KEY, state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS permits (id TEXT PRIMARY KEY, provider TEXT NOT NULL, seat TEXT NOT NULL, session TEXT NOT NULL, turn TEXT NOT NULL, created REAL NOT NULL, ended REAL, reason TEXT, UNIQUE(provider,session,turn))')
            db.execute('CREATE TABLE IF NOT EXISTS audit (at REAL NOT NULL, provider TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL)')
            for p in PROVIDERS:
                db.execute('INSERT OR IGNORE INTO providers VALUES (?,?)', (p, json.dumps(dict(account=None, floors={}, armed=False, valid=False, reason='unconfigured', last=None, latest_observed_at=None, freshness=300, max_active=1))))

    @contextmanager
    def tx(self, *, readonly=False):
        if self.readonly and not readonly:
            raise ValueError('readonly_controller')
        # mode=ro prevents creation and writes even at the SQLite connection
        # level; do not use immutable=1, which can ignore live WAL updates.
        db = (sqlite3.connect(self.path.absolute().as_uri() + '?mode=ro', uri=True,
                              timeout=5, isolation_level=None) if readonly else
              sqlite3.connect(self.path, timeout=5, isolation_level=None))
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON' if readonly else 'PRAGMA query_only=OFF')
            db.execute('BEGIN' if readonly else 'BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def state(self, db, p):
        provider(p)
        return json.loads(db.execute('SELECT state FROM providers WHERE provider=?', (p,)).fetchone()[0])

    def save(self, db, p, s, event, detail):
        db.execute('UPDATE providers SET state=? WHERE provider=?', (json.dumps(s, allow_nan=False), p))
        db.execute('INSERT INTO audit VALUES (?,?,?,?)', (self.clock(), p, event, json.dumps(detail, allow_nan=False)))

    def factory_gate(self, db, s):
        """An opening shares request identity, never provider capacity or gates."""
        return self.gate(s) if s.get('opening_id') else None

    def close_factory(self, db, p, s, reason):
        opening = s.get('opening_id')
        if not opening:
            return
        s.update(armed=False, reason='provider_latched_closed')
        self.save(db, p, s, 'close_provider', {'opening_id':opening,'reason':reason})

    def open_factory(self, floors, reason):
        """Record one request with independently eligible providers; budget only."""
        if not isinstance(floors, (list, tuple)) or len(floors) != 2:
            raise ValueError('floors_require_codex_claude_pair')
        floors = [num(v, 0, 100) for v in floors]
        if not isinstance(reason, str) or not reason.strip() or len(reason)>500:
            raise ValueError('operator_reason_required')
        with self.tx() as db:
            if db.execute('SELECT 1 FROM permits WHERE ended IS NULL').fetchone():
                raise ValueError('active_permits_require_reconciliation')
            opening = str(uuid.uuid4())
            outcomes = {}
            for p, floor in zip(PROVIDERS, floors):
                state = self.state(db, p)
                if not state['account'] or not state['floors']:
                    gate = 'unconfigured'
                else:
                    reserve_windows = state.get('reserve_windows', list(state['floors']))
                    state['floors'] = {key: floor if key in reserve_windows else value
                                       for key, value in state['floors'].items()}
                    gate = self.gate(state, require_armed=False)
                state.update(armed=gate is None, reason=gate, opening_id=opening)
                outcomes[p] = {'armed':gate is None, 'reason':gate, 'reserve_percent':floor}
                self.save(db,p,state,'open_factory',{'opening_id':opening,'floors':state['floors'],
                    'requested_reserve':floor,'operator_reason':reason,'outcome':outcomes[p]})
            return {'opening_id':opening,'providers':outcomes,
                    'any_armed':any(x['armed'] for x in outcomes.values()),
                    'all_armed':all(x['armed'] for x in outcomes.values())}

    def configure(self, p, account, floors, *, freshness=300, max_active=1, reserve_windows=None):
        """Operator configuration, disarmed until a valid reading and explicit arm."""
        account = ident(account)
        if not floors or not isinstance(floors, dict):
            raise ValueError('required_windows_missing')
        floors = {ident(k): num(v, 0, 100) for k, v in floors.items()}
        if reserve_windows is None:
            reserve_windows = list(floors)
        if not isinstance(reserve_windows, list) or not reserve_windows:
            raise ValueError('invalid_reserve_windows')
        reserve_windows = [ident(key) for key in reserve_windows]
        if len(set(reserve_windows)) != len(reserve_windows) or not set(reserve_windows).issubset(floors):
            raise ValueError('invalid_reserve_windows')
        freshness = num(freshness, 1, 3600 if p == 'claude' else 900)
        if isinstance(max_active, bool) or not isinstance(max_active, int) or not 1 <= max_active <= 16:
            raise ValueError('invalid_concurrency')
        with self.tx() as db:
            s = self.state(db, p)
            if db.execute('SELECT 1 FROM permits WHERE provider=? AND ended IS NULL', (p,)).fetchone():
                raise ValueError('active_permits_require_reconciliation')
            if s['account'] and s['account'] != account:
                raise ValueError('account_already_pinned_use_new_state')
            self.close_factory(db, p, s, 'reconfigured')
            s = self.state(db, p)
            s.update(account=account, floors=floors, reserve_windows=reserve_windows, freshness=freshness, max_active=max_active, armed=False, valid=False, reason='awaiting_observation', last=None, latest_observed_at=None)
            self.save(db, p, s, 'configure', {'account': account, 'floors': floors, 'reserve_windows': reserve_windows, 'freshness': freshness, 'max_active': max_active})

    def set_freshness(self, p, seconds):
        """Explicit policy migration preserving evidence, never rearming a lane."""
        seconds = num(seconds, 1, 3600 if p == 'claude' else 900)
        with self.tx() as db:
            s = self.state(db, p)
            if db.execute('SELECT 1 FROM permits WHERE provider=? AND ended IS NULL', (p,)).fetchone():
                raise ValueError('active_permits_require_reconciliation')
            self.close_factory(db, p, s, 'freshness_policy_changed')
            s = self.state(db, p)
            s.update(freshness=seconds, armed=False)
            self.save(db, p, s, 'freshness_policy', {'seconds':seconds})

    def refresh_failed(self, p, account, reason):
        """Retain original successful evidence; never stamp it as newly observed."""
        reason = ident(reason)
        with self.tx() as db:
            s = self.state(db, p)
            if not account or account != s['account']:
                s.update(valid=False, reason='account_mismatch')
                self.save(db,p,s,'reject',{'reason':'account_mismatch'})
                self.close_factory(db,p,s,'account_mismatch')
                return {'fallback_retained':False,'reason':'account_mismatch'}
            # Gates enforce original age, reset deadline, floor, and any latched
            # stop. A transport failure cannot overwrite or rehabilitate them.
            gate = self.factory_gate(db,s) or self.gate(s)
            self.save(db,p,s,'refresh_failed',{'reason':reason,'observed_at':s['last']['observed_at'] if s['last'] else None})
            if gate:
                self.close_factory(db,p,s,gate)
            return {'fallback_retained':gate is None,'reason':gate or 'last_successful_signal',
                    'observed_at':s['last']['observed_at'] if s['last'] else None}

    def invalidate(self, p, reason):
        reason = ident(reason)
        with self.tx() as db:
            s = self.state(db, p)
            s.update(valid=False, reason=reason)
            self.save(db, p, s, 'invalidate', {'reason': reason})
            self.close_factory(db, p, s, reason)

    def observe(self, p, raw):
        with self.tx() as db:
            s, now = self.state(db, p), self.clock()
            prior_gate = self.factory_gate(db, s)
            if prior_gate:
                self.close_factory(db, p, s, prior_gate)
                s = self.state(db, p)
            try:
                if not isinstance(raw, dict) or raw.get('provider') != p:
                    raise ValueError('provider_mismatch')
                observed = num(raw.get('observed_at'), 1)
                if observed > now + 30:
                    raise ValueError('future_observation')
                watermark = s.get('latest_observed_at')
                if watermark is not None and observed <= watermark:
                    return {'accepted': False, 'reason': 'not_newer'}
                s['latest_observed_at'] = observed
                if raw.get('account_bound') is not True or raw.get('freshness_proven') is not True:
                    raise ValueError('unproven_identity_or_freshness')
                if raw.get('account_id') != s['account'] or not s['account']:
                    raise ValueError('account_mismatch')
                if now - observed > s['freshness']:
                    raise ValueError('stale_observation')
                last = s['last']
                if raw.get('usage_allowed') is not True:
                    raise ValueError('provider_denied_or_unknown')
                windows = raw.get('windows')
                if not isinstance(windows, dict) or not s['floors'] or not set(s['floors']).issubset(windows):
                    raise ValueError('required_window_missing')
                clean = {}
                reset = False
                for key in s['floors']:
                    value = windows[key]
                    remaining = num(value['remaining_percent'], 0, 100)
                    inactive = value.get('inactive', False)
                    if not isinstance(inactive, bool):
                        raise ValueError('invalid_inactive_window')
                    if inactive:
                        # A native unused allowance has no running reset clock.
                        # Null alone is not evidence of inactivity.
                        if remaining != 100 or value['resets_at'] is not None:
                            raise ValueError('invalid_inactive_window')
                        resets = None
                    else:
                        resets = num(value['resets_at'], 1)
                        if resets <= now:
                            raise ValueError('reset_expired')
                    clean[key] = dict(remaining_percent=remaining, resets_at=resets)
                    if inactive:
                        clean[key]['inactive'] = True
                    if last:
                        old = last['windows'][key]
                        # Starting an unused window is not a refill. Returning an
                        # active allowance to unused is, and must require rearm.
                        if not old.get('inactive', False):
                            if inactive or resets != old['resets_at'] or remaining > old['remaining_percent']:
                                reset = True
                sample = dict(provider=p, account_id=s['account'], observed_at=observed, source=ident(raw.get('source')), windows=clean)
                s.update(last=sample, valid=True, reason=None)
                if reset:
                    s.update(armed=False, reason='reset_requires_rearm')
                self.save(db, p, s, 'observe', {'sample': sample, 'reset_requires_rearm': reset})
                gate = self.factory_gate(db, s)
                if gate:
                    self.close_factory(db, p, s, gate)
                    s = self.state(db, p)
                return {'accepted': True, 'reason': s['reason']}
            except (ValueError, KeyError, TypeError) as error:
                reason = str(error) if isinstance(error, ValueError) else 'malformed_observation'
                s.update(valid=False, reason=reason)
                self.save(db, p, s, 'reject', {'reason': reason})
                self.close_factory(db, p, s, reason)
                return {'accepted': False, 'reason': reason}

    def gate(self, s, *, require_armed=True):
        now = self.clock()
        if not s['account']:
            return 'unconfigured'
        if not s['valid']:
            return s['reason']
        if require_armed and not s['armed']:
            return s['reason'] or 'disarmed'
        last = s['last']
        if last['observed_at'] > now + 30:
            return 'clock_rollback'
        if now - last['observed_at'] > s['freshness']:
            return 'stale_observation'
        for k, floor in s['floors'].items():
            w = last['windows'][k]
            if not w.get('inactive', False) and w['resets_at'] <= now:
                return 'reset_expired'
            if w['remaining_percent'] <= floor:
                return 'usage_floor:' + k
        return None

    def arm(self, p, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError('operator_reason_required')
        with self.tx() as db:
            s = self.state(db, p)
            if s.get('opening_id'):
                raise ValueError('paired_factory_requires_open_factory')
            gate = self.gate(s, require_armed=False)
            if gate:
                raise ValueError(gate)
            s.update(armed=True, reason=None)
            self.save(db, p, s, 'arm', {'reason': reason})

    def pause(self, p):
        with self.tx() as db:
            s = self.state(db, p)
            s.update(armed=False, reason='operator_paused')
            self.save(db, p, s, 'pause', {})
            self.close_factory(db, p, s, 'operator_paused')

    def status(self, p):
        with self.tx(readonly=True) as db:
            s = self.state(db, p)
            gate = self.factory_gate(db, s) or self.gate(s)
            active = [dict(x) for x in db.execute('SELECT * FROM permits WHERE provider=? AND ended IS NULL', (p,))]
            return dict(provider=p, **s, admission_open=gate is None, gate_reason=gate, active_permits=active)

    def admit(self, p, seat, session, turn):
        seat, session, turn = map(ident, (seat, session, turn))
        with self.tx() as db:
            s = self.state(db, p)
            gate = self.factory_gate(db, s) or self.gate(s)
            if gate:
                self.close_factory(db, p, s, gate)
                return {'allowed': False, 'reason': gate}
            old = db.execute('SELECT * FROM permits WHERE provider=? AND session=? AND turn=?', (p, session, turn)).fetchone()
            if old:
                return {'allowed': old['ended'] is None and old['seat'] == seat, 'permit': old['id'], 'reason': 'existing_permit' if old['ended'] is None else 'turn_already_closed'}
            # One seat cannot acquire overlapping turns even by changing provider.
            if db.execute('SELECT 1 FROM permits WHERE ended IS NULL AND (seat=? OR session=?)', (seat, session)).fetchone():
                return {'allowed': False, 'reason': 'seat_or_session_busy'}
            count = db.execute('SELECT COUNT(*) FROM permits WHERE provider=? AND ended IS NULL', (p,)).fetchone()[0]
            if count >= s['max_active']:
                return {'allowed': False, 'reason': 'provider_concurrency'}
            key = str(uuid.uuid4())
            db.execute('INSERT INTO permits VALUES (?,?,?,?,?,?,NULL,NULL)', (key,p,seat,session,turn,self.clock()))
            self.save(db,p,s,'admit', {'permit':key,'seat':seat,'session':session,'turn':turn})
            return {'allowed':True,'permit':key,'reason':'admitted'}

    def release(self, p, session, turn, reason='completed'):
        """Release one exact native turn. Never reconciles a whole session."""
        session, turn, reason = ident(session), ident(turn), ident(reason)
        with self.tx() as db:
            s = self.state(db,p)
            count = db.execute('UPDATE permits SET ended=?,reason=? WHERE provider=? AND session=? AND turn=? AND ended IS NULL',
                               (self.clock(),reason,p,session,turn)).rowcount
            self.save(db,p,s,'release', {'session':session,'turn':turn,'reason':reason,'count':count})
            return count

    def reconcile_session(self, p, session, reason, *, confirmed_stopped=False):
        """Explicit operator recovery only, after all covered turns have ended."""
        session = ident(session)
        if confirmed_stopped is not True:
            raise ValueError('confirm_all_session_turns_stopped')
        if not isinstance(reason, str) or not reason.strip() or len(reason)>500:
            raise ValueError('operator_reason_required')
        with self.tx() as db:
            s = self.state(db,p)
            count = db.execute('UPDATE permits SET ended=?,reason=? WHERE provider=? AND session=? AND ended IS NULL',
                               (self.clock(),'operator_reconciled',p,session)).rowcount
            self.save(db,p,s,'reconcile_session', {'session':session,'reason':reason,'count':count})
            return count
