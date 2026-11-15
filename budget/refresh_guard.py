"""Cross-process, restart-safe Claude refresh cache and request pacing.

Independent of the admission DB and CLI mode: print-only and --once share this
guard. Never renew observation timestamps on cache reuse. No credentials stored.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time

MIN_INTERVAL = 300
MAX_BACKOFF = 1800


def default_path():
    # One guard per native config directory, not per caller's budget DB.
    config = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home()/'.claude')).resolve()
    import hashlib
    key = hashlib.sha256(str(config).encode()).hexdigest()[:24]
    return Path.home()/'.local/state/wayforge-rig'/('claude-refresh-'+key+'.json')


class RefreshGuard:
    def __init__(self, path=None, clock=time.time):
        self.path = Path(path) if path is not None else default_path()
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        # All request and state operations remain in the lock, including the
        # network attempt. Process death releases flock but keeps its reservation.
        lock = self.path.with_suffix(self.path.suffix+'.lock')
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                if self.path.is_symlink():
                    raise ValueError('refresh_state_symlink')
                if self.path.exists():
                    state = json.loads(self.path.read_text())
                    for key in ('next_attempt_at', 'last_attempt_at', 'failures'):
                        value = state[key]
                        if isinstance(value, bool) or not isinstance(value, (int, float)):
                            raise ValueError('invalid_refresh_state')
                        import math
                        if not math.isfinite(value) or value < 0:
                            raise ValueError('invalid_refresh_state')
                    if state.get('version') != 1:
                        raise ValueError('invalid_refresh_state')
                else:
                    state = dict(version=1, next_attempt_at=0, last_attempt_at=0,
                                 failures=0, sample=None, identity=None)
                yield state
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def save(self, state):
        fd, name = tempfile.mkstemp(prefix='.'+self.path.name, dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(name): os.unlink(name)

    def wait_seconds(self, state):
        return max(0, state['next_attempt_at'] - self.clock())

    def reserve(self, state, interval):
        if self.wait_seconds(state):
            return False
        now = self.clock()
        state['failures'] += 1
        delay = min(MAX_BACKOFF, max(MIN_INTERVAL, interval) *
                    2**min(state['failures']-1, 3))
        state.update(last_attempt_at=now, next_attempt_at=now+delay)
        self.save(state)  # write-ahead: crash, SIGTERM, timeout cannot erase pacing
        return True

    def complete(self, state, sample, identity, interval):
        now = self.clock()
        state.update(failures=0, sample=sample, identity=identity,
                     next_attempt_at=max(state['next_attempt_at'], now+max(MIN_INTERVAL, interval)))
        self.save(state)

    def failed(self, state, interval):
        delay = min(MAX_BACKOFF, max(MIN_INTERVAL, interval) *
                    2**min(state['failures']-1, 3))
        state['next_attempt_at'] = max(state['next_attempt_at'], self.clock()+delay)
        self.save(state)

    def cached(self, state, identity):
        sample = state.get('sample')
        # Native normalized evidence is 60 seconds conservative. It may be used
        # for at most the same one-hour retention as admission, never re-dated.
        if (not isinstance(sample, dict) or state.get('identity') != identity or
                not 0 <= self.clock()-sample.get('observed_at', 0) <= 3600):
            return None
        return sample
