"""Draft-only GitHub publication with durable uncertain-result reconciliation.

No push/merge API exists here. A caller must authorize the explicit repository
and issue, authenticate review receipts, and choose the slice. Cross-process
locking serializes publication using this state directory. An unknown attempt
never automatically creates again, even if GitHub currently lists no PR.
Remote read-before-write cannot eliminate a concurrent branch-update race:
post-create readback must still match the approved SHA, else outcome is unknown.
"""
import fcntl
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from urllib.parse import quote
from .publication import plan_publication, _SHA
from .checks import discover


def native_runner(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)


class GitHubPublisher:
    def __init__(self, state_dir, *, gh_executable, runner=native_runner, inventory_reader=discover):
        if not isinstance(gh_executable,str) or not Path(gh_executable).is_absolute() or any(ord(c)<32 for c in gh_executable):
            raise ValueError('approved_absolute_gh_executable_required')
        self.gh_executable=gh_executable
        self.root=Path(state_dir)
        if not self.root.is_absolute() or self.root.is_symlink(): raise ValueError('safe_absolute_state_directory_required')
        # Reject symlink ancestors: state and body artifacts must remain local.
        if any(p.is_symlink() for p in (self.root,*self.root.parents)): raise ValueError('state_symlink_not_allowed')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.runner=runner
        self.inventory_reader=inventory_reader

    def _run(self, argv):
        if argv[0]!='gh': raise ValueError('unexpected_command')
        return self.runner([self.gh_executable,*argv[1:]])

    def _json(self, argv):
        result=self._run(argv)
        if result.returncode: raise ValueError('github_read_failed')
        try:return json.loads(result.stdout)
        except (TypeError,ValueError):raise ValueError('github_invalid_json') from None

    def _api(self, endpoint):
        return self._json(['gh','api','--hostname','github.com','--method','GET',endpoint])

    def _head(self, repo, branch):
        value=self._api('repos/'+repo+'/git/ref/heads/'+quote(branch,safe=''))
        if not isinstance(value,dict) or value.get('ref')!='refs/heads/'+branch or not isinstance(value.get('object'),dict) or value['object'].get('type')!='commit':
            raise ValueError('remote_branch_unverified')
        return value['object'].get('sha')

    def _existing(self, plan):
        fields='number,url,state,isDraft,headRefName,headRefOid,baseRefName,isCrossRepository,body'
        rows=self._json(['gh','pr','list','--repo','github.com/'+plan['repo'],'--head',plan['head'],'--state','all','--limit','100','--json',fields])
        if not isinstance(rows,list) or len(rows)>=100:raise ValueError('ambiguous_existing_pr')
        # Same head against a different base is not silently duplicated.
        if not rows:return None
        if len(rows)!=1:raise ValueError('ambiguous_existing_pr')
        row=rows[0]
        expected_url=f'https://github.com/{plan["repo"]}/pull/'
        issue=f'https://github.com/{plan["repo"]}/issues/{plan["issue"]}'
        if not isinstance(row,dict) or row.get('isCrossRepository') is not False or row.get('headRefName')!=plan['head'] or row.get('baseRefName')!=plan['base'] or row.get('headRefOid')!=plan['head_sha'] or row.get('state')!='OPEN' or row.get('isDraft') is not True or not isinstance(row.get('number'),int) or isinstance(row.get('number'),bool) or row['number']<1 or str(row.get('url','')).casefold()!=(expected_url+str(row['number'])).casefold() or issue.casefold() not in str(row.get('body','')).casefold():
            raise ValueError('existing_pr_mismatch')
        return {'number':row['number'],'url':row['url']}

    def publish(self, *, authorized_repo, authorized_issue, target_base, expected_base_sha, slices, slice_id, check_repository):
        if not isinstance(expected_base_sha,str) or not _SHA.fullmatch(expected_base_sha):
            raise ValueError('exact_expected_base_sha_required')
        # Planner validates all externally selected fields before any network IO.
        if isinstance(authorized_repo,str):authorized_repo=authorized_repo.lower()
        plans=plan_publication(authorized_repo=authorized_repo,authorized_issue=authorized_issue,target_base=target_base,slices=slices)
        matching=[p for p in plans if p['slice_id']==slice_id]
        if len(matching)!=1:raise ValueError('unknown_slice')
        plan=matching[0]
        base_sha=(next(p['head_sha'] for p in plans if p['slice_id']==plan['predecessor'])
                  if plan['predecessor'] else expected_base_sha)
        if not plan['ready']:return {'status':'blocked','reason':plan['reason']}
        # Rebuild from Git objects; an implementor cannot omit a workflow from
        # an otherwise internally consistent coverage receipt. No network writes
        # occur until local sources match the reviewed inventory exactly.
        candidate=next(item for item in slices if item['id']==slice_id)
        if self.inventory_reader(check_repository, plan['head_sha']) != candidate['check_coverage']['manifest']:
            return {'status':'blocked','reason':'check_inventory_does_not_match_repository'}
        # Journal lane is repo/head: changed revision/base/issue cannot bypass an unknown create.
        # Full authorization and revision remain in its durable identity record.
        identity={k:plan[k] for k in ('repo','issue','base','head','head_sha')}
        identity['expected_base_sha']=base_sha
        key=hashlib.sha256(json.dumps({'repo':plan['repo'],'head':plan['head']},sort_keys=True).encode()).hexdigest()
        flags=os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW
        lockfd=os.open(self.root/'publication.lock',flags,0o600)
        try:
            fcntl.flock(lockfd,fcntl.LOCK_EX)
            dbpath=self.root/'publication.sqlite3'
            if dbpath.is_symlink():raise ValueError('journal_symlink_not_allowed')
            fd=os.open(dbpath,flags,0o600);os.close(fd)
            with closing(sqlite3.connect(dbpath)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, identity TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT)')
                previous=db.execute('SELECT state FROM attempts WHERE key=?',(key,)).fetchone()
                issue=self._api(f'repos/{authorized_repo}/issues/{authorized_issue}')
                if not isinstance(issue,dict) or issue.get('number')!=authorized_issue or 'pull_request' in issue or str(issue.get('html_url','')).casefold()!=f'https://github.com/{authorized_repo}/issues/{authorized_issue}'.casefold():raise ValueError('authorized_issue_unverified')
                existing=self._existing(plan)
                if existing:
                    if self._head(plan['repo'],plan['base'])!=base_sha:raise ValueError('remote_base_changed')
                    if self._head(plan['repo'],plan['head'])!=plan['head_sha']:raise ValueError('remote_head_changed')
                    db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?,?)',(key,json.dumps(identity),'verified',json.dumps(existing)));db.commit()
                    return {'status':'verified','created':False,**existing}
                if previous:return {'status':'unknown','reason':'prior_attempt_requires_reconciliation','attempt_id':key}
                if issue.get('state')!='open':return {'status':'blocked','reason':'issue_not_open'}
                if plan['predecessor']:
                    predecessor=next(p for p in plans if p['slice_id']==plan['predecessor'])
                    if not self._existing(predecessor):return {'status':'blocked','reason':'predecessor_not_published'}
                # Materialize only our generated body in an exclusive artifact.
                artifact=self.root/(key+'.md')
                fd=os.open(artifact,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600) if not artifact.exists() else None
                if fd is not None:
                    with os.fdopen(fd,'w') as f:f.write(plan['body']);f.flush();os.fsync(f.fileno())
                elif artifact.is_symlink() or artifact.read_text()!=plan['body']:raise ValueError('body_artifact_conflict')
                if self._head(plan['repo'],plan['base'])!=base_sha:raise ValueError('remote_base_changed')
                if self._head(plan['repo'],plan['head'])!=plan['head_sha']:raise ValueError('remote_head_changed')
                db.execute('INSERT INTO attempts VALUES (?,?,?,NULL)',(key,json.dumps(identity),'unknown'));db.commit()
                argv=list(plan['argv']);argv[argv.index('--body-file')+1]=str(artifact)
                argv[argv.index('--repo')+1]='github.com/'+plan['repo']
                try:self._run(argv)
                except Exception:pass  # May have succeeded remotely. Never retry blindly.
                try:
                    receipt=self._existing(plan)
                    if receipt and self._head(plan['repo'],plan['head'])==plan['head_sha'] and self._head(plan['repo'],plan['base'])==base_sha:
                        db.execute('UPDATE attempts SET state=?,receipt=? WHERE key=?',('verified',json.dumps(receipt),key));db.commit()
                        return {'status':'verified','created':True,**receipt}
                except Exception:pass
                return {'status':'unknown','reason':'publication_readback_unverified','attempt_id':key}
        finally:
            os.close(lockfd)
