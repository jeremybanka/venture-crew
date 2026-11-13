#!/usr/bin/env python3
"""Conservative, task-owned Git worktree retirement. No forced removal."""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def git(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=30, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    if p.returncode:
        raise ValueError(p.stderr.strip() or 'git command failed')
    return p.stdout.strip()


def worktrees(repo):
    raw = subprocess.run(['git', '-C', str(repo), 'worktree', 'list', '--porcelain', '-z'],
                         check=True, stdout=subprocess.PIPE, timeout=30).stdout.decode()
    result = []
    current = {}
    for field in raw.split('\0'):
        if not field:
            if current:
                result.append(current)
                current = {}
            continue
        key, _, value = field.partition(' ')
        current[key] = value
    if current:
        result.append(current)
    return result


def paths(repo, tree):
    repo = Path(repo).absolute()
    tree = Path(tree).absolute()
    # Reject symlink aliases rather than following them across policy boundaries.
    if repo != repo.resolve() or tree != tree.resolve():
        raise ValueError('symlink or noncanonical path')
    if tree.parent != repo / '.worktrees':
        raise ValueError('worktree must be a direct child of repository .worktrees/')
    if not repo.is_dir() or not tree.is_dir():
        raise ValueError('repository/worktree missing')
    entries = worktrees(repo)
    if not entries or Path(entries[0]['worktree']).resolve() != repo:
        raise ValueError('repo must be the primary checkout')
    entry = next((e for e in entries if e.get('worktree') == str(tree)), None)
    if not entry or tree == repo:
        raise ValueError('not a registered secondary worktree')
    if Path(git(tree, 'rev-parse', '--show-toplevel')).resolve() != tree:
        raise ValueError('worktree root mismatch')
    if Path(git(tree, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve() != Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve():
        raise ValueError('repository ownership mismatch')
    return repo, tree, entry


@contextlib.contextmanager
def ledger(state):
    state = Path(state).expanduser()
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        p = state / 'tasks.json'
        data = json.loads(p.read_text()) if p.exists() else {}
        yield data
        fd, tmp = tempfile.mkstemp(dir=state, prefix='.tasks-')
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)


def event(task, name, **details):
    task.setdefault('events', []).append({'at': now(), 'event': name, **details})
    task['updated_at'] = now()


def register(data, task_id, repo, tree, owner, remote='origin'):
    if task_id in data:
        raise ValueError('task already registered')
    repo, tree, _ = paths(repo, tree)
    if any(t['tree'] == str(tree) and t['status'] != 'retired' for t in data.values()):
        raise ValueError('worktree already owned by another task')
    if remote not in git(repo, 'remote').splitlines():
        raise ValueError('named recovery remote is not configured')
    data[task_id] = dict(repo=str(repo), tree=str(tree), owner=owner, remote=remote,
                         base=git(tree, 'rev-parse', 'HEAD'), status='active', events=[])
    event(data[task_id], 'registered')
    return data[task_id]


def transition(task, task_id, status, confirm_inactive=False):
    if task['status'] == 'retired':
        raise ValueError('task is retired')
    repo, tree, entry = paths(task['repo'], task['tree'])
    reason = 'wayforge-task:' + task_id
    if status in ('closed', 'abandoned', 'paused') and not confirm_inactive:
        raise ValueError('confirm all worktree users have stopped with --confirm-inactive')
    if status == 'paused':
        if 'locked' not in entry:
            git(repo, 'worktree', 'lock', '--reason', reason, str(tree))
    elif status == 'active' and entry.get('locked') == reason:
        git(repo, 'worktree', 'unlock', str(tree))
    task['status'] = status
    event(task, status)
    return task


def inspect(task):
    reasons = []
    if task['status'] == 'retired':
        return {'eligible': False, 'reasons': ['already_retired']}
    if task['status'] not in ('closed', 'abandoned'):
        reasons.append('task_not_closed')
    try:
        repo, tree, entry = paths(task['repo'], task['tree'])
        if 'locked' in entry:
            reasons.append('locked')
        if 'prunable' in entry:
            reasons.append('prunable_registration')
        # Include ignored files: caches/build outputs may still carry unique bytes.
        if git(tree, 'status', '--porcelain=v1', '--untracked-files=all', '--ignored'):
            reasons.append('dirty_untracked_or_ignored_files')
        flags = git(tree, 'ls-files', '-v').splitlines()
        if any(line and (line[0].islower() or line[0] == 'S') for line in flags):
            reasons.append('hidden_index_flags_require_manual_review')
        head = git(tree, 'rev-parse', 'HEAD')
        if any((Path(git(tree, 'rev-parse', '--git-path', name))).exists()
               for name in ('index.lock', 'MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD')):
            reasons.append('git_operation_in_progress')
        if git(tree, 'ls-files', '--stage').find('160000 ') >= 0:
            reasons.append('submodules_require_manual_review')
        return {'eligible': not reasons, 'reasons': reasons, 'head': head,
                'repo': str(repo), 'tree': str(tree)}
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        return {'eligible': False, 'reasons': reasons + ['uncertain:' + str(e)]}


def remote_proof(task, head):
    # A live remote ref must name exactly this HEAD; local tracking refs are not proof.
    refs = git(task['repo'], 'ls-remote', '--heads', task['remote'])
    matches = [line.split()[1] for line in refs.splitlines()
               if len(line.split()) == 2 and line.split()[0] == head]
    if not matches:
        raise ValueError('HEAD not found at a live remote branch; preserve unpushed work')
    return {'remote': task['remote'], 'head': head, 'refs': matches, 'verified_at': now()}


def retire(task, confirm_inactive=False):
    if not confirm_inactive:
        raise ValueError('explicit --confirm-inactive required; stop all users of the tree first')
    first = inspect(task)
    if not first['eligible']:
        event(task, 'cleanup_hold', reasons=first['reasons'])
        return first
    try:
        proof = remote_proof(task, first['head'])
        second = inspect(task)
        if not second['eligible'] or second.get('head') != first['head']:
            raise ValueError('worktree changed during retirement checks')
        # No --force. Git is the last safety gate for concurrent tracked/untracked edits.
        git(task['repo'], 'worktree', 'remove', task['tree'])
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        result = {'eligible': False, 'reasons': ['cleanup_hold:' + str(e)]}
        event(task, 'cleanup_hold', reasons=result['reasons'])
        return result
    task['status'] = 'retired'
    event(task, 'retired', proof=proof)
    return {'retired': True, 'proof': proof, 'branch_deleted': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', default=os.environ.get('WAYFORGE_HYGIENE_STATE', '~/.local/state/wayforge-rig/hygiene'))
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('register')
    for arg in ('task', 'repo', 'tree', 'owner'):
        r.add_argument('--' + arg, required=True)
    r.add_argument('--remote', default='origin')
    s = sub.add_parser('set-state')
    s.add_argument('--task', required=True)
    s.add_argument('status', choices=['active', 'paused', 'closed', 'abandoned'])
    s.add_argument('--confirm-inactive', action='store_true')
    sub.add_parser('inventory')
    r = sub.add_parser('retire')
    r.add_argument('--task', required=True)
    r.add_argument('--confirm-inactive', action='store_true')
    args = p.parse_args()
    try:
        with ledger(args.state) as data:
            if args.cmd == 'register':
                result = register(data, args.task, args.repo, args.tree, args.owner, args.remote)
            elif args.cmd == 'set-state':
                result = transition(data[args.task], args.task, args.status, args.confirm_inactive)
            elif args.cmd == 'retire':
                result = retire(data[args.task], args.confirm_inactive)
            else:
                result = {k: {**inspect(v), 'owner': v['owner'], 'status': v['status'],
                              'last_activity': v['updated_at']} for k, v in data.items()}
        print(json.dumps(result, indent=2))
        if args.cmd == 'retire' and not result.get('retired'):
            return 2
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
        print(json.dumps({'error': str(e)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
