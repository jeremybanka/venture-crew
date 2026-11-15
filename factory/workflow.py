"""Publish one reviewed slice, then register only its ancestor PR chain.

Never publishes ancestors or siblings, promotes drafts, edits stacks or merges.
A verified PR receipt survives a subsequent stack hold or uncertain API result.
"""
from .publication import plan_publication
from .stacks import StackPublisher


class PublicationWorkflow:
    def __init__(self, publisher, stack_publisher=None):
        self.publisher = publisher
        self.stack_publisher = stack_publisher

    def publish(self, **kwargs):
        publication = self.publisher.publish(**kwargs)
        if publication.get('status') != 'verified':
            return {'status': publication.get('status', 'blocked'), 'publication': publication,
                    'stack': {'status': 'not_attempted', 'reason': 'publication_not_verified'}}
        if publication.get('is_draft') is not False:
            return {'status': 'blocked', 'publication': publication,
                    'stack': {'status': 'blocked', 'reason': 'publication_is_draft_or_unverified'}}
        try:
            stack = self._register_ancestors(kwargs, publication)
        except Exception:
            # PR creation already happened. Preserve its receipt and avoid exposing
            # arbitrary external exceptions or implying the whole workflow passed.
            stack = {'status': 'blocked', 'reason': 'stack_verification_failed'}
        status = 'verified' if stack.get('status') in ('verified', 'not_applicable') else 'blocked'
        return {'status': status, 'publication': publication, 'stack': stack}

    def _register_ancestors(self, args, publication):
        repo = args['authorized_repo'].lower()
        plans = plan_publication(authorized_repo=repo, authorized_issue=args['authorized_issue'],
                                 target_base=args['target_base'], slices=args['slices'])
        by_id = {p['slice_id']: p for p in plans}
        candidates = {s['id']: s for s in args['slices']}
        chain = []; current = by_id[args['slice_id']]
        while current:
            chain.append(current)
            current = by_id[current['predecessor']] if current['predecessor'] else None
        chain.reverse()
        if len(chain) == 1:
            return {'status': 'not_applicable', 'reason': 'single_slice'}
        expected = []
        for plan in chain:
            if not plan['ready']:
                return {'status': 'blocked', 'reason': 'ancestor_not_ready', 'slice_id': plan['slice_id']}
            item = candidates[plan['slice_id']]
            if self.publisher.inventory_reader(args['check_repository'], plan['head_sha']) != item['check_coverage']['manifest']:
                return {'status': 'blocked', 'reason': 'ancestor_check_inventory_mismatch', 'slice_id': plan['slice_id']}
            pr = self.publisher._existing(plan)
            if not pr or pr.get('is_draft') is not False:
                return {'status': 'blocked', 'reason': 'ancestor_pr_missing_or_draft', 'slice_id': plan['slice_id']}
            base_sha = by_id[plan['predecessor']]['head_sha'] if plan['predecessor'] else args['expected_base_sha']
            if (self.publisher._head(repo, plan['head']) != plan['head_sha']
                    or self.publisher._head(repo, plan['base']) != base_sha):
                return {'status': 'blocked', 'reason': 'ancestor_remote_revision_changed', 'slice_id': plan['slice_id']}
            if plan['slice_id'] == args['slice_id'] and (pr['number'] != publication.get('number') or pr['url'] != publication.get('url')):
                return {'status': 'blocked', 'reason': 'published_pr_receipt_changed'}
            expected.append(dict(number=pr['number'], head=plan['head'], head_sha=plan['head_sha'],
                                 base=plan['base'], base_sha=base_sha))
        publisher = self.stack_publisher
        if publisher is None:
            publisher = StackPublisher(self.publisher.root / 'native-stacks',
                                       gh_executable=self.publisher.gh_executable,
                                       runner=self.publisher.runner)
        return publisher.register(authorized_repo=repo, pull_requests=expected)


def publish_with_stack(publisher, stack_publisher, **publish_kwargs):
    """Compose scoped publication and stack registration with retained receipts."""
    return PublicationWorkflow(publisher, stack_publisher).publish(**publish_kwargs)
