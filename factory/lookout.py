"""Read-only, explicit-PR CI observer. Emits handoffs; never merges or reruns CI.

Run ``python3 -m factory.lookout --repo owner/repo --pr 12 --gh /path/to/gh
--state /absolute/ignored/lookout.sqlite3``. Add --watch to poll until closure,
--interval 300 (minimum 60), and repeat --expected-check for known required names.
Use --latest (no --gh needed) to recover the last persisted report without any
network request or consuming it. Reports are saved before stdout delivery.
Observed green is not independent review or a complete required-check inventory.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import time
from urllib.parse import urlsplit
from .publication import _REPO, _SHA


def native_runner(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)


def evidence_url(value, repo):
    """Keep only same-repository GitHub run/check links; discard query/fragment."""
    if not isinstance(value, str) or not repo or any(ord(c) < 32 for c in value):
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    prefix = '/' + re.escape(repo)
    if url.scheme != 'https' or url.netloc.lower() != 'github.com' or not re.fullmatch(
            prefix + r'/(?:actions/runs/[0-9]+(?:/job/[0-9]+)?|runs/[0-9]+|pull/[0-9]+/checks)',
            url.path, flags=re.IGNORECASE):
        return None
    return 'https://github.com' + url.path


def classify(pr, expected_checks=(), repo=None):
    """Classify current-head rollup, preserving unknown/missing evidence as holds."""
    if not isinstance(pr, dict) or not _SHA.fullmatch(str(pr.get('headRefOid', ''))):
        raise ValueError('invalid_pr_evidence')
    head = pr['headRefOid']
    if pr.get('state') in ('CLOSED', 'MERGED'):
        return {'head_sha': head, 'status': pr['state'].lower(), 'checks': []}
    if pr.get('state') != 'OPEN':
        raise ValueError('invalid_pr_state')
    rows = pr.get('statusCheckRollup')
    if not isinstance(rows, list):
        return {'head_sha': head, 'status': 'unknown', 'checks': []}
    checks = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid_check_evidence')
        kind = row.get('__typename')
        if kind == 'CheckRun':
            name = row.get('name')
            state = row.get('conclusion') if row.get('status') == 'COMPLETED' else 'PENDING'
            status = ('passed' if state == 'SUCCESS' else 'failed' if state in
                      ('FAILURE', 'TIMED_OUT', 'CANCELLED', 'ACTION_REQUIRED', 'STARTUP_FAILURE') else
                      'pending' if state == 'PENDING' else 'unknown')
        elif kind == 'StatusContext':
            name = row.get('context')
            status = {'SUCCESS': 'passed', 'FAILURE': 'failed', 'ERROR': 'failed',
                      'PENDING': 'pending', 'EXPECTED': 'pending'}.get(row.get('state'), 'unknown')
        else:
            name, status = row.get('name', 'unrecognized-check'), 'unknown'
        if not isinstance(name, str) or not name or len(name) > 500 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError('invalid_check_name')
        item = {'name': name, 'status': status}
        link = evidence_url(row.get('detailsUrl') if kind == 'CheckRun' else row.get('targetUrl'), repo)
        if link:
            item['url'] = link
        checks.append(item)
    names = {c['name'] for c in checks}
    missing = sorted(set(expected_checks) - names)
    checks.sort(key=lambda c: (c['name'], c['status']))
    statuses = {c['status'] for c in checks}
    status = ('failed' if 'failed' in statuses else 'missing' if missing or not checks else
              'unknown' if 'unknown' in statuses else 'pending' if 'pending' in statuses else 'observed_green')
    return {'head_sha': head, 'status': status, 'checks': checks, 'missing_checks': missing}


class Lookout:
    def __init__(self, *, repo, pr, gh_executable, state_file, expected_checks=(), runner=native_runner):
        if not isinstance(repo, str) or not _REPO.fullmatch(repo) or any(x.startswith('-') for x in repo.split('/')):
            raise ValueError('explicit_repository_required')
        if type(pr) is not int or pr < 1:
            raise ValueError('explicit_pr_required')
        if gh_executable is not None and (not isinstance(gh_executable, str) or not Path(gh_executable).is_absolute()):
            raise ValueError('absolute_gh_required')
        self.path = Path(state_file)
        if not self.path.is_absolute() or any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('safe_absolute_state_file_required')
        self.repo, self.pr, self.gh = repo, pr, gh_executable
        self.expected = tuple(expected_checks)
        if any(not isinstance(x, str) or not x.strip() or len(x) > 500 for x in self.expected):
            raise ValueError('invalid_expected_check')
        self.runner = runner

    def _read(self):
        if self.gh is None:
            raise ValueError('absolute_gh_required')
        fields = 'number,state,headRefOid,statusCheckRollup'
        result = self.runner([self.gh, 'pr', 'view', str(self.pr), '--repo', 'github.com/'+self.repo,
                              '--json', fields])
        if result.returncode:
            raise ValueError('github_read_failed')
        try:
            value = json.loads(result.stdout)
        except (TypeError, ValueError):
            raise ValueError('github_invalid_json') from None
        if not isinstance(value, dict) or value.get('number') != self.pr:
            raise ValueError('pr_identity_mismatch')
        return value

    def poll(self):
        try:
            first = self._read()
            observation = classify(first, self.expected, self.repo)
            second = self._read()
            # Invalidate evidence if the head changed during collection. A closed
            # PR is terminal only after the second read confirms that same state.
            if second.get('headRefOid') != first.get('headRefOid') or second.get('state') != first.get('state'):
                observation = {'head_sha': None, 'status': 'stale', 'checks': []}
            else:
                observation = classify(second, self.expected, self.repo)
        except (ValueError, OSError, subprocess.SubprocessError):
            # Never persist credentials, CLI stderr, or raw remote error bodies.
            observation = {'head_sha': None, 'status': 'unavailable', 'checks': []}
        observation.update(repo=self.repo, pr=self.pr)
        status = observation['status']
        observation['handoff'] = ('Captain: return CI failure to the assigned implementor; Cleric: assess missing preflight coverage.'
                                  if status == 'failed' else
                                  'Captain: keep delivery held; investigate incomplete or unavailable CI evidence.'
                                  if status in ('missing', 'unknown', 'stale', 'unavailable') else None)
        observation['terminal'] = status in ('closed', 'merged')
        digest = hashlib.sha256(json.dumps(observation, sort_keys=True).encode()).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS observations (key TEXT PRIMARY KEY, digest TEXT NOT NULL, checked_at REAL NOT NULL)')
            if 'payload' not in {row[1] for row in db.execute('PRAGMA table_info(observations)')}:
                db.execute('ALTER TABLE observations ADD COLUMN payload TEXT')
            db.execute('BEGIN IMMEDIATE')
            key = self.repo.lower() + '#' + str(self.pr)
            row = db.execute('SELECT digest FROM observations WHERE key=?', (key,)).fetchone()
            observation['changed'] = row is None or row[0] != digest
            observation['checked_at'] = time.time()
            db.execute('INSERT OR REPLACE INTO observations (key,digest,checked_at,payload) VALUES (?,?,?,?)',
                       (key, digest, observation['checked_at'], json.dumps(observation, sort_keys=True)))
        return observation


    def latest(self):
        """Non-consuming local recovery, including after stdout delivery failure."""
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            if 'payload' not in {row[1] for row in db.execute('PRAGMA table_info(observations)')}:
                return None  # Legacy digest-only state cannot reconstruct evidence.
            row = db.execute('SELECT payload FROM observations WHERE key=?',
                             (self.repo.lower() + '#' + str(self.pr),)).fetchone()
            return json.loads(row[0]) if row and row[0] else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--pr', required=True, type=int)
    parser.add_argument('--gh')
    parser.add_argument('--latest', action='store_true')
    parser.add_argument('--state', required=True)
    parser.add_argument('--expected-check', action='append', default=[])
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval', type=int, default=300)
    args = parser.parse_args()
    if args.interval < 60:
        parser.error('interval must be at least 60 seconds')
    if args.latest and args.watch:
        parser.error('--latest cannot be combined with --watch')
    if not args.latest and args.gh is None:
        parser.error('--gh is required to poll')
    observer = Lookout(repo=args.repo, pr=args.pr, gh_executable=args.gh, state_file=args.state,
                       expected_checks=args.expected_check)
    if args.latest:
        print(json.dumps(observer.latest(), sort_keys=True))
        return
    while True:
        value = observer.poll()
        if value['changed'] or not args.watch:
            print(json.dumps(value, sort_keys=True), flush=True)
        if not args.watch or value['terminal']:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
