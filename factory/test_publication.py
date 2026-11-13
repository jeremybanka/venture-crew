from .check_fixtures import coverage_fixture
import copy
import unittest
from .publication import plan_publication

class PublicationTests(unittest.TestCase):
    def slice(self,key='one',**kw):
        sha='a'*40
        value=dict(id=key,branch='factory/'+key,head_sha=sha,author='strider-1',title='Slice '+key,body_file='/tmp/'+key+'.md',
                   review=dict(reviewer='warden',head_sha=sha,approved=True,receipt='review:123'),
                   tests=dict(head_sha=sha,passed=True,proof='test:123'),check_coverage=coverage_fixture(sha))
        value.update(kw);return value
    def plan(self,slices,**kw):
        args=dict(authorized_repo='owner/repo',authorized_issue=17,target_base='main',slices=slices);args.update(kw)
        return plan_publication(**args)
    def test_stack_is_explicit_draft_argv(self):
        plans=self.plan([self.slice(),self.slice('two',predecessor='one')])
        self.assertTrue(all(p['ready'] for p in plans))
        self.assertEqual(plans[0]['base'],'main');self.assertEqual(plans[1]['base'],'factory/one')
        self.assertEqual(plans[1]['argv'],['gh','pr','create','--repo','owner/repo','--base','factory/one','--head','factory/two','--draft','--title','Slice two','--body-file','/tmp/two.md'])
        self.assertIn('https://github.com/owner/repo/issues/17',plans[1]['body'])
        self.assertNotIn('merge',plans[1]['argv'])
    def test_missing_review_and_descendant_block(self):
        one=self.slice();del one['review']
        plans=self.plan([one,self.slice('two',predecessor='one')])
        self.assertEqual(plans[0]['reason'],'independent_review_missing');self.assertEqual(plans[1]['reason'],'predecessor_blocked')
        self.assertTrue(all(p['argv'] is None for p in plans))
    def test_exact_revision_and_independence_required(self):
        for field,changes in [('review',{'head_sha':'b'*40}),('tests',{'head_sha':'b'*40}),('review',{'reviewer':'STRIDER-1'}),('review',{'approved':False}),('tests',{'passed':False}),('tests',{'proof':''})]:
            item=self.slice();item[field].update(changes)
            self.assertFalse(self.plan([item])[0]['ready'])
    def test_changed_head_invalidates_both_receipts(self):
        item=self.slice(head_sha='b'*40)
        self.assertEqual(self.plan([item])[0]['reason'],'review_revision_mismatch')
    def test_bad_graphs_rejected(self):
        cases=[[self.slice(),self.slice()],
               [self.slice(),self.slice('two',branch='factory/one')],
               [self.slice(predecessor='missing')],
               [self.slice(predecessor='two'),self.slice('two',predecessor='one')],
               [self.slice('two',predecessor='one'),self.slice()]]
        for case in cases:
            with self.assertRaises(ValueError):self.plan(case)
    def test_authorization_and_base_required(self):
        for kw in ({'authorized_repo':''},{'authorized_repo':'--help/repo'},{'authorized_issue':True},{'authorized_issue':0},{'target_base':''}):
            with self.assertRaises(ValueError):self.plan([self.slice()],**kw)
    def test_invalid_ref_sha_and_artifacts(self):
        for kw in ({'branch':'--help'},{'branch':'feature/../main'},{'branch':'main'},{'head_sha':'abcdef'},{'body_file':'relative.md'},{'body_file':'/tmp/../secret'},{'title':'bad\nvalue'}):
            with self.assertRaises(ValueError):self.plan([self.slice(**kw)])
        with self.assertRaises(ValueError):self.plan([self.slice(),self.slice('two',body_file='/tmp/one.md')])
    def test_no_mutation_or_shell_interpolation(self):
        item=self.slice(title='literal $(touch /tmp/not-executed); text');before=copy.deepcopy(item)
        plan=self.plan([item])[0]
        self.assertEqual(item,before);self.assertIn(item['title'],plan['argv'])
    def test_proof_text_cannot_insert_issue_closure(self):
        item=self.slice();item['tests']['proof']='Closes #17; private test log'
        body=self.plan([item])[0]['body']
        self.assertNotIn('Closes #17',body);self.assertIn('Test proof SHA-256',body)

if __name__=='__main__':unittest.main()
