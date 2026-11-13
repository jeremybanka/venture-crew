"""Single-instance Lookout observer with durable, cold native-queue handoffs.

CLI: python3 -m factory.lookout_service --repo owner/repo --pr 123 --gh /abs/gh
--state-dir /abs/ignored/lookout --rig /abs/rig --source lookout-observer@crew
--destination bridge-captain@crew [--expected-check Knip] [--once]. Polls every
300 seconds. Queue writes always use --no-nudge; this never starts model work.
The latest local delivery status is available in delivery-status.json; the
SQLite journal retains exact immutable payloads for interrupted write recovery.
"""
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from .lookout import Lookout, native_runner

ALERTS = {'failed', 'missing', 'unknown', 'unavailable', 'stale'}
SUMMARY = 'Lookout: CI evidence requires Captain triage'


class LookoutService:
    def __init__(self, *, observer, state_dir, rig, source, destination, runner=native_runner):
        self.root = Path(state_dir)
        if not self.root.is_absolute() or any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('safe_absolute_state_directory_required')
        if not Path(rig).is_absolute():
            raise ValueError('absolute_rig_required')
        if not re.fullmatch(r'lookout-observer@[A-Za-z0-9_.-]+', source):
            raise ValueError('truthful_observer_source_required')
        if not re.fullmatch(r'bridge-captain@[A-Za-z0-9_.-]+', destination):
            raise ValueError('captain_destination_required')
        if source.split('@')[1] != destination.split('@')[1]:
            raise ValueError('same_rig_required')
        if os.environ.get('OPENRIG_SESSION_NAME') or os.environ.get('RIGGED_SESSION_NAME'):
            raise ValueError('external_observer_must_not_claim_managed_seat')
        self.observer, self.rig, self.source, self.destination, self.runner = observer, rig, source, destination, runner
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.locked = False

    @contextmanager
    def lock(self):
        fd = os.open(self.root/'service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.locked = True
            yield
        finally:
            self.locked = False
            os.close(fd)

    def _db(self):
        path = self.root/'delivery.sqlite3'
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, body TEXT NOT NULL, source TEXT NOT NULL, destination TEXT NOT NULL, state TEXT NOT NULL)')
        return db

    def _json(self, args):
        try:
            result = self.runner([self.rig, *args])
            return json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    @staticmethod
    def _matches(row, identity, body, source, destination):
        return (isinstance(row, dict) and row.get('qitemId') == identity and row.get('body') == body
                and row.get('sourceSession') == source and row.get('destinationSession') == destination)

    def _deliver(self, identity, body, source, destination):
        # Read-before-retry reconciles a write that committed before a crash.
        row = self._json(['queue', 'show', identity, '--full', '--json'])
        if self._matches(row, identity, body, source, destination):
            return 'submitted'
        if isinstance(row, dict) and row.get('qitemId') == identity:
            return 'conflict'
        path = self.root/(identity+'.json')
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if path.is_symlink() or path.read_text() != body:
                return 'conflict'
        else:
            with os.fdopen(fd, 'w') as file:
                file.write(body); file.flush(); os.fsync(file.fileno())
        args = ['queue', 'create', '--source', source, '--destination', destination,
                '--id', identity, '--summary', SUMMARY, '--body-file', str(path), '--no-nudge', '--json']
        row = self._json(args)
        if self._matches(row, identity, body, source, destination):
            return 'submitted'
        row = self._json(['queue', 'show', identity, '--full', '--json'])
        if self._matches(row, identity, body, source, destination):
            return 'submitted'
        return 'conflict' if isinstance(row, dict) and row.get('qitemId') == identity else 'unknown'

    def tick(self):
        if not self.locked:
            raise ValueError('lifetime_lock_required')
        report = self.observer.poll()
        stable = {k: v for k, v in report.items() if k not in ('changed', 'checked_at')}
        identity = 'lookout-' + hashlib.sha256(json.dumps({'report': stable, 'source': self.source,
                    'destination': self.destination}, sort_keys=True).encode()).hexdigest()[:40]
        with closing(self._db()) as db:
            if report['status'] in ALERTS:
                body = json.dumps(stable, sort_keys=True, indent=2) + '\n'
                db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?,?)',
                           (identity, body, self.source, self.destination, 'unknown'))
                db.commit()  # Durable payload/identity before the first native write.
            for key, body, source, destination in db.execute("SELECT id,body,source,destination FROM deliveries WHERE state='unknown'").fetchall():
                state = self._deliver(key, body, source, destination)
                db.execute('UPDATE deliveries SET state=? WHERE id=?', (state, key)); db.commit()
            rows = db.execute('SELECT id,state FROM deliveries ORDER BY id').fetchall()
        status = {'repo': report['repo'], 'pr': report['pr'], 'observed_status': report['status'],
                  'head_sha': report['head_sha'], 'checked_at': report['checked_at'],
                  'terminal': report['terminal'], 'deliveries': [{'id': key, 'state': state} for key, state in rows]}
        tmp = self.root/'delivery-status.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(status, file, sort_keys=True); file.flush(); os.fsync(file.fileno())
        os.replace(tmp, self.root/'delivery-status.json')
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'gh', 'state-dir', 'rig', 'source', 'destination'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--pr', type=int, required=True)
    parser.add_argument('--expected-check', action='append', default=[])
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    observer = Lookout(repo=args.repo, pr=args.pr, gh_executable=args.gh,
                       state_file=str(Path(args.state_dir)/'observations.sqlite3'), expected_checks=args.expected_check)
    service = LookoutService(observer=observer, state_dir=args.state_dir, rig=args.rig,
                             source=args.source, destination=args.destination)
    with service.lock():
        while True:
            status = service.tick()
            print(json.dumps(status, sort_keys=True), flush=True)
            if args.once or status['terminal']:
                break
            time.sleep(300)


if __name__ == '__main__': main()
