"""Pure reviewed-stack publication planning. Never executes or contacts GitHub.

Caller supplies an authorized repository/issue and ordered slices. Review and
proof receipts must come from a trusted independent review workflow, not from
an implementing agent's self-attestation. This module validates their declared
identity and exact revision, not their authenticity. Caller must verify current
remote head/base SHAs, branch existence, authorization, existing PRs (for retry
idempotency), and materialize the returned body verbatim immediately before use.
A ready plan is not a publication receipt or proof that tests ran.
"""
import re
import hashlib
from pathlib import PurePosixPath

_REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
_ID = re.compile(r'[A-Za-z0-9_.@-]{1,128}\Z')
_SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
_BRANCH = re.compile(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,199}\Z')


def _text(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value)>limit or any(ord(x)<32 or ord(x)==127 for x in value):
        raise ValueError('invalid_'+name)
    return value


def _branch(value):
    if not isinstance(value,str) or not _BRANCH.fullmatch(value) or '..' in value or '//' in value or value.endswith('/'):
        raise ValueError('invalid_branch')
    if any(part.startswith('.') or part.endswith(('.', '.lock')) for part in value.split('/')):
        raise ValueError('invalid_branch')
    return value


def _receipt_block(slice):
    review=slice.get('review')
    if not isinstance(review,dict): return 'independent_review_missing'
    if review.get('head_sha')!=slice['head_sha']: return 'review_revision_mismatch'
    reviewer=review.get('reviewer')
    if not isinstance(reviewer,str) or not _ID.fullmatch(reviewer): return 'reviewer_identity_missing'
    if reviewer.casefold()==slice['author'].casefold(): return 'review_not_independent'
    if review.get('approved') is not True: return 'review_not_approved'
    try: _text(review.get('receipt'),'review_receipt',2000)
    except ValueError: return 'review_receipt_missing'
    tests=slice.get('tests')
    if not isinstance(tests,dict): return 'test_proof_missing'
    if tests.get('head_sha')!=slice['head_sha']: return 'test_revision_mismatch'
    if tests.get('passed') is not True: return 'tests_not_passed'
    try: _text(tests.get('proof'),'test_proof',2000)
    except ValueError: return 'test_proof_missing'
    return None


def plan_publication(*, authorized_repo, authorized_issue, target_base, slices):
    """Return ordered plans; invalid graphs raise, missing/stale evidence queues.

    A slice: id, branch, head_sha, author, title, absolute body_file, optional
    predecessor (slice ID), review {reviewer, head_sha, approved, receipt},
    tests {head_sha, passed, proof}. Only one predecessor is supported; caller
    splits multi-parent dependency graphs before publication. No auto-close
    issue keywords or arbitrary body text are generated.
    """
    if not isinstance(authorized_repo,str) or not _REPO.fullmatch(authorized_repo):
        raise ValueError('explicit_authorized_repo_required')
    if any(p in ('.','..') or p.startswith('-') for p in authorized_repo.split('/')):
        raise ValueError('invalid_authorized_repo')
    if isinstance(authorized_issue,bool) or not isinstance(authorized_issue,int) or authorized_issue<1:
        raise ValueError('explicit_authorized_issue_required')
    _branch(target_base)
    if not isinstance(slices,list) or not slices: raise ValueError('slices_required')
    indexed={}; branches=set(); paths=set()
    for item in slices:
        if not isinstance(item,dict): raise ValueError('invalid_slice')
        key=item.get('id')
        if not isinstance(key,str) or not _ID.fullmatch(key) or key in indexed: raise ValueError('invalid_or_duplicate_slice_id')
        branch=_branch(item.get('branch'))
        if branch==target_base or branch in branches: raise ValueError('duplicate_or_base_branch')
        if not isinstance(item.get('head_sha'),str) or not _SHA.fullmatch(item['head_sha']): raise ValueError('exact_head_sha_required')
        if not isinstance(item.get('author'),str) or not _ID.fullmatch(item['author']): raise ValueError('author_identity_required')
        _text(item.get('title'),'title')
        if item['title'].startswith('-'): raise ValueError('invalid_title')
        path=_text(item.get('body_file'),'body_file',4096)
        if not PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts: raise ValueError('absolute_body_artifact_required')
        normalized=str(PurePosixPath(path))
        if normalized in paths: raise ValueError('duplicate_body_artifact')
        predecessor=item.get('predecessor')
        if predecessor is not None and (not isinstance(predecessor,str) or not _ID.fullmatch(predecessor)): raise ValueError('invalid_predecessor')
        indexed[key]=item;branches.add(branch);paths.add(normalized)
    for key,item in indexed.items():
        seen={key}; prev=item.get('predecessor')
        while prev is not None:
            if prev not in indexed: raise ValueError('unknown_predecessor')
            if prev in seen: raise ValueError('dependency_cycle')
            seen.add(prev);prev=indexed[prev].get('predecessor')
    plans=[];completed={}
    issue=f'https://github.com/{authorized_repo}/issues/{authorized_issue}'
    for item in slices:
        predecessor=item.get('predecessor')
        if predecessor is not None and predecessor not in completed: raise ValueError('predecessor_must_come_first')
        base=indexed[predecessor]['branch'] if predecessor else target_base
        reason=_receipt_block(item)
        if predecessor and not completed[predecessor]['ready']: reason='predecessor_blocked'
        ready=reason is None
        body=(f'Related issue: {issue}\n\nDraft slice `{item["id"]}`. Owner review and merge required.\n'
              f'Planned base: `{base}`. Exact reviewed head: `{item["head_sha"]}`.\n'
              'No claim of issue completion or merge is made by this publication plan.\n')
        if ready:
            review_digest=hashlib.sha256(item['review']['receipt'].encode()).hexdigest()
            test_digest=hashlib.sha256(item['tests']['proof'].encode()).hexdigest()
            body+=f'\nIndependent reviewer: `{item["review"]["reviewer"]}`.\nReview receipt SHA-256: `{review_digest}`.\nTest proof SHA-256: `{test_digest}`.\n'
        argv=['gh','pr','create','--repo',authorized_repo,'--base',base,'--head',item['branch'],'--draft','--title',item['title'],'--body-file',item['body_file']] if ready else None
        plan=dict(slice_id=item['id'],ready=ready,reason=reason,repo=authorized_repo,issue=authorized_issue,
                  base=base,head=item['branch'],head_sha=item['head_sha'],predecessor=predecessor,
                  argv=argv,body_file=item['body_file'],body=body)
        plans.append(plan);completed[item['id']]=plan
    return plans
