"""Bounded native GitHub stack registration; no PR mutation or merge.

The caller authenticates authorization and independent review of each exact PR
head. This adapter checks current remote eligibility, not review authenticity.
Unknown writes are journaled per PR and never retried blindly. API contract:
https://docs.github.com/en/rest/pulls/stacks (2026-03-10).
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing
from .github import GitHubPublisher
from .publication import _SHA, _branch


class StackPublisher(GitHubPublisher):
    def _stack_api(self, method, endpoint, payload=None):
        argv = ['gh', 'api', '--hostname', 'github.com', '--method', method,
                '-H', 'Accept: application/vnd.github+json',
                '-H', 'X-GitHub-Api-Version: 2026-03-10', endpoint]
        if payload is not None:
            # Numeric repeated typed fields generate the documented integer array.
            for number in payload:
                argv += ['-F', 'pull_requests[]=' + str(number)]
        return self._json(argv)

    def _verify_prs(self, repo, prs):
        for p in prs:
            row = self._stack_api('GET', f'repos/{repo}/pulls/{p["number"]}')
            if not isinstance(row, dict):
                raise ValueError('stack_pr_mismatch')
            head, base = row.get('head', {}), row.get('base', {})
            if (type(row.get('number')) is not int or row.get('number') != p['number'] or row.get('state') != 'open'
                    or row.get('draft') is not False or row.get('merged_at') is not None
                    or row.get('html_url', '').lower() != f'https://github.com/{repo}/pull/{p["number"]}'
                    or head.get('ref') != p['head'] or head.get('sha') != p['head_sha']
                    or base.get('ref') != p['base'] or base.get('sha') != p['base_sha']
                    or str(head.get('repo', {}).get('full_name', '')).lower() != repo
                    or str(base.get('repo', {}).get('full_name', '')).lower() != repo):
                raise ValueError('stack_pr_mismatch')

    def _existing_stack(self, repo, prs):
        numbers = [p['number'] for p in prs]
        found = []
        for number in numbers:
            rows = self._stack_api('GET', f'repos/{repo}/stacks?pull_request={number}&per_page=100')
            if not isinstance(rows, list) or len(rows) > 1:
                raise ValueError('ambiguous_stack_membership')
            if rows and (not isinstance(rows[0], dict)
                    or type(rows[0].get('number')) is not int or rows[0]['number'] < 1):
                raise ValueError('malformed_stack_membership')
            found.append(rows[0] if rows else None)
        if all(row is None for row in found):
            return None
        # Only an empty API list proves absence. Falsey or malformed members
        # are not evidence that registration is safe.
        if any(row is not None and (not isinstance(row, dict)
                or type(row.get('number')) is not int or row['number'] < 1) for row in found):
            raise ValueError('malformed_stack_membership')
        if not all(isinstance(row, dict) for row in found):
            raise ValueError('conflicting_stack_membership')
        stack_number = found[0].get('number')
        if type(stack_number) is not int or stack_number < 1 or any(row.get('number') != stack_number for row in found):
            raise ValueError('conflicting_stack_membership')
        row = self._stack_api('GET', f'repos/{repo}/stacks/{stack_number}')
        if (not isinstance(row, dict) or row.get('number') != stack_number
                or row.get('open') is not True or row.get('base', {}).get('ref') != prs[0]['base']
                or row.get('url', '').lower() != f'https://api.github.com/repos/{repo}/stacks/{stack_number}'):
            raise ValueError('stack_readback_mismatch')
        members = row.get('pull_requests')
        if not isinstance(members, list) or len(members) != len(prs):
            raise ValueError('stack_readback_mismatch')
        for member, expected in zip(members, prs):
            if (not isinstance(member, dict) or member.get('number') != expected['number']
                    or member.get('state') != 'open' or member.get('draft') is not False
                    or member.get('merged_at') is not None
                    or member.get('head', {}).get('sha') != expected['head_sha']
                    or member.get('head', {}).get('ref') != expected['head']):
                raise ValueError('stack_readback_mismatch')
        self._verify_prs(repo, prs)
        return {'number': stack_number, 'url': row['url'], 'pull_requests': numbers}

    def register(self, *, authorized_repo, pull_requests):
        """Register >=2 reviewed same-repo normal PRs, bottom to top.

        Each expected PR supplies number, head, head_sha, base and base_sha.
        Existing matching stacks reconcile without writes. Existing conflicts,
        invalid evidence or API errors stop; no stack edits/deletion are exposed.
        """
        if (not isinstance(authorized_repo, str)
                or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*', authorized_repo)):
            raise ValueError('explicit_authorized_repo_required')
        repo = authorized_repo.lower()
        if not isinstance(pull_requests, list) or len(pull_requests) < 2:
            raise ValueError('ordered_prs_required')
        prs = []
        for p in pull_requests:
            if not isinstance(p, dict) or type(p.get('number')) is not int or p['number'] < 1:
                raise ValueError('invalid_pr_number')
            item = {k: p.get(k) for k in ('number', 'head', 'head_sha', 'base', 'base_sha')}
            _branch(item['head']); _branch(item['base'])
            if any(not isinstance(item[k], str) or not _SHA.fullmatch(item[k]) for k in ('head_sha', 'base_sha')):
                raise ValueError('exact_pr_shas_required')
            if item['head'] == item['base']:
                raise ValueError('invalid_stack_chain')
            if prs and (item['base'] != prs[-1]['head'] or item['base_sha'] != prs[-1]['head_sha']):
                raise ValueError('invalid_stack_chain')
            prs.append(item)
        if (len({p['number'] for p in prs}) != len(prs) or len({p['head'] for p in prs}) != len(prs)
                or prs[0]['base'] in {p['head'] for p in prs}):
            raise ValueError('duplicate_stack_member')
        identity = hashlib.sha256(json.dumps({'repo': repo, 'prs': prs}, sort_keys=True).encode()).hexdigest()
        flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
        lock = os.open(self.root / 'stacks.lock', flags, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            dbpath = self.root / 'stacks.sqlite3'
            fd = os.open(dbpath, flags, 0o600); os.close(fd)
            with closing(sqlite3.connect(dbpath)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS stack_attempts (repo TEXT, pr INTEGER, identity TEXT, state TEXT, PRIMARY KEY(repo,pr))')
                self._verify_prs(repo, prs)
                existing = self._existing_stack(repo, prs)
                if existing:
                    for p in prs:
                        db.execute('INSERT OR REPLACE INTO stack_attempts VALUES (?,?,?,?)', (repo, p['number'], identity, 'verified'))
                    return {'status': 'verified', 'created': False, **existing}
                prior = any(db.execute('SELECT 1 FROM stack_attempts WHERE repo=? AND pr=?', (repo, p['number'])).fetchone() for p in prs)
                if prior:
                    return {'status': 'unknown', 'reason': 'prior_stack_attempt_requires_reconciliation'}
                self._verify_prs(repo, prs)
                for p in prs:
                    db.execute('INSERT INTO stack_attempts VALUES (?,?,?,?)', (repo, p['number'], identity, 'unknown'))
                db.commit()
                try:
                    self._stack_api('POST', f'repos/{repo}/stacks', [p['number'] for p in prs])
                except Exception:
                    pass
                try:
                    existing = self._existing_stack(repo, prs)
                    if existing:
                        db.execute('UPDATE stack_attempts SET state=? WHERE repo=? AND identity=?', ('verified', repo, identity))
                        return {'status': 'verified', 'created': True, **existing}
                except Exception:
                    pass
                return {'status': 'unknown', 'reason': 'stack_readback_unverified'}
        finally:
            os.close(lock)
