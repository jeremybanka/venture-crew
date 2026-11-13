"""Read-only, revision-pinned check discovery and explicit pre-publication coverage.

No YAML guessing: every workflow/local action is a review obligation, including
uses, matrices, defaults and conditions. Package scripts and hook configs are
also inventoried, not silently equated with the full CI contract. A trusted
reviewer maps obligations to successful check receipts or explains irrelevance.
This validates declared evidence; like review receipts, authenticity belongs to
the caller. Never execute commands found in repository content automatically.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
HOOKS = {'hk.pkl', '.pre-commit-config.yaml', 'lefthook.yml', 'lefthook.yaml',
         '.husky/pre-commit', '.husky/pre-push', '.gitmodules'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def discover(repo, head_sha):
    """Read committed sources at the explicit SHA, never the ambient worktree."""
    if not isinstance(head_sha, str) or not SHA.fullmatch(head_sha):
        raise ValueError('exact_head_sha_required')
    def git(*args):
        result = subprocess.run(['git', '-C', str(Path(repo).resolve()), *args],
                                capture_output=True, check=True)
        return result.stdout
    if git('rev-parse', head_sha + '^{commit}').decode().strip() != head_sha:
        raise ValueError('commit_required')
    entries = git('ls-tree', '-r', '-z', head_sha).split(b'\0')
    units = []
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        path = raw_path.decode()
        selected = (path.startswith('.github/workflows/') or path.startswith('.github/actions/')
                    or path in HOOKS or Path(path).name == 'package.json'
                    or path.startswith('.husky/') or Path(path).name in ('Makefile', 'justfile', 'mise.toml', '.mise.toml'))
        if not selected:
            continue
        if kind != 'blob' or mode == '120000':
            raise ValueError('check_source_must_be_regular_file:' + path)
        raw = git('cat-file', 'blob', oid)
        if len(raw) > 2_000_000:
            raise ValueError('check_source_too_large:' + path)
        content = raw.decode()
        if Path(path).name == 'package.json':
            data = json.loads(content)
            for name, command in sorted(data.get('scripts', {}).items()):
                units.append({'id': path + '#scripts/' + name, 'path': path,
                              'content': command, 'source_sha256': hashlib.sha256(raw).hexdigest()})
        else:
            units.append({'id': path, 'path': path, 'content': content,
                          'source_sha256': hashlib.sha256(raw).hexdigest()})
    manifest = {'version': 1, 'head_sha': head_sha, 'units': sorted(units, key=lambda x: x['id'])}
    manifest['digest'] = digest(manifest)
    return manifest


def coverage_error(receipt, head_sha, reviewer):
    if not isinstance(receipt, dict):
        return 'check_coverage_missing'
    manifest = receipt.get('manifest')
    if not isinstance(manifest, dict) or manifest.get('version') != 1 or manifest.get('head_sha') != head_sha:
        return 'check_inventory_revision_mismatch'
    if manifest.get('digest') != digest({k: v for k, v in manifest.items() if k != 'digest'}):
        return 'check_inventory_digest_mismatch'
    if receipt.get('reviewer') != reviewer:
        return 'check_coverage_not_independently_reviewed'
    units = manifest.get('units')
    if not isinstance(units, list) or not units:
        return 'check_inventory_empty'
    ids = [u.get('id') for u in units if isinstance(u, dict)]
    if len(ids) != len(units) or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        return 'check_inventory_invalid'
    decisions = receipt.get('coverage')
    if not isinstance(decisions, dict) or set(decisions) != set(ids):
        return 'check_coverage_incomplete'
    runs = receipt.get('runs')
    if not isinstance(runs, dict):
        return 'check_run_evidence_missing'
    for decision in decisions.values():
        if not isinstance(decision, dict):
            return 'check_coverage_invalid'
        if decision.get('disposition') == 'not_applicable':
            if not isinstance(decision.get('reason'), str) or not decision['reason'].strip():
                return 'check_exclusion_reason_missing'
        elif decision.get('disposition') == 'required':
            names = decision.get('runs')
            if not isinstance(names, list) or not names:
                return 'check_run_evidence_missing'
            for name in names:
                run = runs.get(name) if isinstance(name, str) else None
                if not isinstance(run, dict) or run.get('head_sha') != head_sha or run.get('exit_code') != 0 or isinstance(run.get('exit_code'), bool):
                    return 'check_run_failed_or_stale'
                if not isinstance(run.get('environment'), str) or not run['environment'].strip():
                    return 'check_environment_missing'
                if not isinstance(run.get('command'), str) or not run['command'].strip() or not isinstance(run.get('proof'), str) or not run['proof'].strip():
                    return 'check_run_evidence_missing'
        else:
            return 'check_coverage_unresolved'
    # An entirely waived inventory is not evidence of relevant checks passing.
    if not any(d.get('disposition') == 'required' for d in decisions.values()):
        return 'no_required_checks'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    print(json.dumps(discover(args.repo, args.head), indent=2))


if __name__ == '__main__':
    main()
