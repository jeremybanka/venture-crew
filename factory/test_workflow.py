import copy
import unittest
from .check_fixtures import coverage_fixture
from .workflow import PublicationWorkflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.slices = [self.slice('one','a'), self.slice('two','b','one'), self.slice('sibling','c')]
        self.args = dict(authorized_repo='Owner/Repo', authorized_issue=17, target_base='main',
                         expected_base_sha='d'*40, slices=self.slices, slice_id='two', check_repository='/fixture')
        self.publication = dict(status='verified', created=True, is_draft=False, number=2,
                                url='https://github.com/owner/repo/pull/2')
        self.existing = {s['id']:dict(number=i+1, url=f'https://github.com/owner/repo/pull/{i+1}', is_draft=False)
                         for i,s in enumerate(self.slices)}
        self.heads = {s['branch']:s['head_sha'] for s in self.slices}; self.heads['main']='d'*40
        self.stack_result = dict(status='verified',number=7)
        owner=self
        class Publisher:
            def publish(self, **args):
                owner.calls.append(('publish',args['slice_id'])); return copy.deepcopy(owner.publication)
            def inventory_reader(self, repo, head):
                owner.calls.append(('inventory',head)); return coverage_fixture(head)['manifest']
            def _existing(self, plan):
                owner.calls.append(('existing',plan['slice_id'])); return owner.existing.get(plan['slice_id'])
            def _head(self, repo, ref): return owner.heads[ref]
        class Stacks:
            def register(self, **args):
                owner.calls.append(('register',args)); return copy.deepcopy(owner.stack_result)
        self.pub=Publisher();self.stacks=Stacks();self.workflow=PublicationWorkflow(self.pub,self.stacks)

    def slice(self, name, digit, predecessor=None):
        sha=digit*40
        result=dict(id=name,branch='factory/'+name,head_sha=sha,author='worker',title=name,body_file='/tmp/'+name+'.md',
                    review=dict(reviewer='warden',head_sha=sha,approved=True,receipt='proof'),
                    tests=dict(head_sha=sha,passed=True,proof='tests'),check_coverage=coverage_fixture(sha))
        if predecessor:result['predecessor']=predecessor
        return result

    def run_workflow(self):return self.workflow.publish(**self.args)
    def registrations(self):return [c[1] for c in self.calls if c[0]=='register']

    def test_only_selected_publication_then_exact_ancestor_stack(self):
        result=self.run_workflow();self.assertEqual(result['status'],'verified')
        self.assertEqual(self.calls[0],('publish','two'))
        self.assertEqual([c for c in self.calls if c[0]=='publish'],[('publish','two')])
        args=self.registrations()[0]
        self.assertEqual(args['authorized_repo'],'owner/repo')
        self.assertEqual([p['number'] for p in args['pull_requests']],[1,2])
        self.assertEqual(args['pull_requests'][1]['base_sha'],'a'*40)
        self.assertNotIn(('existing','sibling'),self.calls)

    def test_default_constructor_uses_canonical_journal_directory(self):
        from pathlib import Path
        from unittest.mock import patch
        self.pub.root = Path('/fixture/publication-state')
        self.pub.gh_executable = '/approved/gh'
        self.pub.runner = object()
        with patch('factory.workflow.StackPublisher', return_value=self.stacks) as constructor:
            result = PublicationWorkflow(self.pub).publish(**self.args)
        self.assertEqual(result['status'], 'verified')
        constructor.assert_called_once_with(self.pub.root / 'native-stacks',
                                            gh_executable=self.pub.gh_executable,
                                            runner=self.pub.runner)

    def test_blocked_or_unknown_publication_never_registers(self):
        for status in ('blocked','unknown'):
            self.publication['status']=status
            self.assertEqual(self.run_workflow()['status'],status)
        self.assertFalse(self.registrations())

    def test_draft_selected_receipt_is_preserved_without_registration(self):
        self.publication['is_draft']=True
        result=self.run_workflow();self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['publication'],self.publication);self.assertFalse(self.registrations())

    def test_single_slice_is_not_applicable(self):
        self.args['slice_id']='one';self.publication.update(number=1,url=self.existing['one']['url'])
        self.assertEqual(self.run_workflow()['stack']['status'],'not_applicable')
        self.assertFalse(self.registrations())

    def test_missing_or_draft_ancestor_blocks_without_creation(self):
        for row in (None,dict(self.existing['one'],is_draft=True)):
            self.existing['one']=row
            self.assertEqual(self.run_workflow()['status'],'blocked')
        self.assertFalse(self.registrations())
        self.assertEqual([c for c in self.calls if c[0]=='publish'],[('publish','two')]*2)

    def test_ancestor_review_or_inventory_failure_blocks(self):
        self.slices[0]['review']['approved']=False
        self.assertEqual(self.run_workflow()['status'],'blocked')
        self.slices[0]['review']['approved']=True
        self.pub.inventory_reader=lambda repo,head: {}
        self.assertEqual(self.run_workflow()['status'],'blocked');self.assertFalse(self.registrations())

    def test_remote_revision_or_receipt_mismatch_blocks(self):
        self.heads['factory/one']='e'*40
        self.assertEqual(self.run_workflow()['status'],'blocked')
        self.heads['factory/one']='a'*40;self.publication['number']=22
        self.assertEqual(self.run_workflow()['status'],'blocked');self.assertFalse(self.registrations())

    def test_stack_unknown_preserves_publication(self):
        self.stack_result=dict(status='unknown',reason='readback_unverified')
        result=self.run_workflow();self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['publication'],self.publication);self.assertEqual(result['stack'],self.stack_result)

    def test_stack_or_verification_exception_preserves_publication(self):
        def fail(**kwargs):raise ValueError('private external detail')
        self.stacks.register=fail
        result=self.run_workflow();self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['publication'],self.publication)
        self.assertNotIn('private',str(result))


if __name__=='__main__':unittest.main()
