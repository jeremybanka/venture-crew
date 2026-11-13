import json
import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from .github import GitHubPublisher

SHA='a'*40
GH='/approved/bin/gh'
class FakeGitHub:
    def __init__(self):
        self.calls=[];self.rows=[];self.issue_state='open';self.sha=SHA;self.base_sha=SHA;self.create_mode='success'
    def pr(self):
        return dict(number=7,url='https://github.com/owner/repo/pull/7',state='OPEN',isDraft=True,headRefName='factory/one',headRefOid=SHA,baseRefName='main',isCrossRepository=False,body='Related issue: https://github.com/owner/repo/issues/17')
    def __call__(self,argv):
        self.calls.append(argv)
        if argv[:3]==[GH,'pr','create']:
            body=Path(argv[argv.index('--body-file')+1]).read_text()
            assert 'Related issue:' in body
            if self.create_mode in ('success','timeout_after_create'):self.rows=[self.pr()]
            if self.create_mode.startswith('timeout'):raise TimeoutError()
            return SimpleNamespace(returncode=0 if self.create_mode=='success' else 1,stdout='',stderr='')
        if argv[:3]==[GH,'pr','list']:value=self.rows
        elif argv[-1].endswith('/issues/17'):value={'number':17,'state':self.issue_state,'html_url':'https://github.com/owner/repo/issues/17'}
        elif '/git/ref/heads/' in argv[-1]:
            from urllib.parse import unquote
            branch=unquote(argv[-1].split('/git/ref/heads/')[1]);value={'ref':'refs/heads/'+branch,'object':{'type':'commit','sha':self.base_sha if branch=='main' else self.sha}}
        else:raise AssertionError(argv)
        return SimpleNamespace(returncode=0,stdout=json.dumps(value),stderr='')
    def creates(self):return sum(x[:3]==[GH,'pr','create'] for x in self.calls)

class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.fake=FakeGitHub();self.pub=GitHubPublisher(Path(self.tmp.name).resolve()/'state',gh_executable=GH,runner=self.fake)
        self.args=dict(authorized_repo='owner/repo',authorized_issue=17,target_base='main',expected_base_sha=SHA,slice_id='one',slices=[dict(id='one',branch='factory/one',head_sha=SHA,author='strider',title='Slice one',body_file='/tmp/planner-only.md',review=dict(reviewer='warden',head_sha=SHA,approved=True,receipt='receipt'),tests=dict(head_sha=SHA,passed=True,proof='proof'))])
    def test_create_verified_then_retry_idempotent(self):
        self.assertEqual(self.pub.publish(**self.args)['status'],'verified')
        self.assertFalse(self.pub.publish(**self.args)['created']);self.assertEqual(self.fake.creates(),1)
        self.assertTrue(all('merge' not in c and 'push' not in c for c in self.fake.calls))
    def test_timeout_reconciles_success(self):
        self.fake.create_mode='timeout_after_create'
        self.assertEqual(self.pub.publish(**self.args)['status'],'verified');self.assertEqual(self.fake.creates(),1)
    def test_unknown_never_blindly_recreated_even_new_instance(self):
        self.fake.create_mode='timeout_before_create'
        self.assertEqual(self.pub.publish(**self.args)['status'],'unknown')
        self.pub=GitHubPublisher(Path(self.tmp.name).resolve()/'state',gh_executable=GH,runner=self.fake)
        self.assertEqual(self.pub.publish(**self.args)['status'],'unknown');self.assertEqual(self.fake.creates(),1)
    def test_changed_revision_cannot_bypass_unknown_attempt(self):
        self.fake.create_mode='timeout_before_create';self.pub.publish(**self.args)
        item=self.args['slices'][0];item['head_sha']='b'*40
        item['review']['head_sha']='b'*40;item['tests']['head_sha']='b'*40
        self.fake.sha='b'*40
        self.assertEqual(self.pub.publish(**self.args)['status'],'unknown');self.assertEqual(self.fake.creates(),1)
    def test_unknown_can_later_reconcile(self):
        self.fake.create_mode='failure';self.pub.publish(**self.args)
        self.fake.rows=[self.fake.pr()]
        self.assertEqual(self.pub.publish(**self.args)['status'],'verified');self.assertEqual(self.fake.creates(),1)
    def test_repo_host_is_explicit_despite_environment(self):
        from unittest.mock import patch
        with patch.dict('os.environ',{'GH_HOST':'other.invalid'}):
            self.pub.publish(**self.args)
        for argv in self.fake.calls:
            if argv[1]=='pr':self.assertEqual(argv[argv.index('--repo')+1],'github.com/owner/repo')
            if argv[1]=='api':self.assertEqual(argv[argv.index('--hostname')+1],'github.com')
    def test_case_variation_cannot_bypass_unknown_lane(self):
        self.fake.create_mode='timeout_before_create';self.pub.publish(**self.args)
        self.args['authorized_repo']='Owner/Repo'
        self.assertEqual(self.pub.publish(**self.args)['status'],'unknown');self.assertEqual(self.fake.creates(),1)
    def test_closed_issue_blocks_new_create(self):
        self.fake.issue_state='closed'
        self.assertEqual(self.pub.publish(**self.args),{'status':'blocked','reason':'issue_not_open'})
        self.assertEqual(self.fake.creates(),0)
    def test_closed_issue_still_reconciles_existing_attempt(self):
        self.pub.publish(**self.args);self.fake.issue_state='closed'
        self.assertEqual(self.pub.publish(**self.args)['status'],'verified');self.assertEqual(self.fake.creates(),1)
    def test_remote_head_changed_blocks_create(self):
        self.fake.sha='b'*40
        with self.assertRaisesRegex(ValueError,'remote_head_changed'):self.pub.publish(**self.args)
        self.assertEqual(self.fake.creates(),0)
    def test_base_mismatch_blocks_create(self):
        self.fake.base_sha='c'*40
        with self.assertRaisesRegex(ValueError,'remote_base_changed'):self.pub.publish(**self.args)
        self.assertEqual(self.fake.creates(),0)
    def test_base_changed_after_create_stays_unknown(self):
        original=self.fake.__call__
        def changed(argv):
            result=original(argv)
            if argv[:3]==[GH,'pr','create']:self.fake.base_sha='c'*40
            return result
        self.pub.runner=changed
        self.assertEqual(self.pub.publish(**self.args)['status'],'unknown')
    def test_absolute_approved_executable_required(self):
        with self.assertRaises(ValueError):GitHubPublisher(Path(self.tmp.name).resolve()/'state',gh_executable='gh',runner=self.fake)
    def test_expected_base_required_before_calls(self):
        self.args['expected_base_sha']='short'
        with self.assertRaises(ValueError):self.pub.publish(**self.args)
        self.assertEqual(self.fake.calls,[])
    def test_dependent_base_uses_predecessor_reviewed_sha(self):
        first=self.args['slices'][0]
        first['head_sha']='b'*40;first['review']['head_sha']='b'*40;first['tests']['head_sha']='b'*40
        second=copy.deepcopy(first);second.update(id='two',branch='factory/two',body_file='/tmp/two.md',predecessor='one',head_sha='c'*40)
        second['review']['head_sha']='c'*40;second['tests']['head_sha']='c'*40
        self.args['slices'].append(second);self.args['slice_id']='two'
        created=[]
        def runner(argv):
            if argv[1:3]==['pr','list']:
                head=argv[argv.index('--head')+1]
                if head=='factory/one':rows=[dict(self.fake.pr(),headRefOid='b'*40)]
                else:rows=created
                value=rows
            elif argv[1:3]==['pr','create']:
                created.append(dict(self.fake.pr(),number=8,url='https://github.com/owner/repo/pull/8',headRefName='factory/two',headRefOid='c'*40,baseRefName='factory/one'))
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            elif '/git/ref/heads/' in argv[-1]:
                from urllib.parse import unquote
                branch=unquote(argv[-1].split('/git/ref/heads/')[1])
                value={'ref':'refs/heads/'+branch,'object':{'type':'commit','sha':'b'*40 if branch=='factory/one' else 'c'*40}}
            else:return self.fake(argv)
            return SimpleNamespace(returncode=0,stdout=json.dumps(value),stderr='')
        self.pub.runner=runner
        self.assertEqual(self.pub.publish(**self.args)['status'],'verified')
    def test_ambiguous_or_mismatched_existing_blocks(self):
        for rows in ([self.fake.pr(),self.fake.pr()],[dict(self.fake.pr(),baseRefName='wrong')],[dict(self.fake.pr(),headRefOid='b'*40)],[dict(self.fake.pr(),isCrossRepository=True)],[dict(self.fake.pr(),state='CLOSED')]):
            self.fake.rows=rows
            with self.assertRaises(ValueError):self.pub.publish(**self.args)
        self.assertEqual(self.fake.creates(),0)
    def test_missing_review_makes_no_external_calls(self):
        del self.args['slices'][0]['review']
        self.assertEqual(self.pub.publish(**self.args)['status'],'blocked');self.assertEqual(self.fake.calls,[])
    def test_invalid_authorization_makes_no_calls(self):
        self.args['authorized_issue']=None
        with self.assertRaises(ValueError):self.pub.publish(**self.args)
        self.assertEqual(self.fake.calls,[])
    def test_symlink_state_rejected(self):
        path=Path(self.tmp.name)/'link';path.symlink_to(Path(self.tmp.name),target_is_directory=True)
        with self.assertRaises(ValueError):GitHubPublisher(path,gh_executable=GH,runner=self.fake)
    def test_created_pr_changed_before_readback_stays_unknown(self):
        original=self.fake.__call__
        def changed(argv):
            result=original(argv)
            if argv[:3]==[GH,'pr','create']:self.fake.sha='b'*40
            return result
        self.pub.runner=changed
        self.assertEqual(self.pub.publish(**self.args)['status'],'unknown');self.assertEqual(self.fake.creates(),1)

if __name__=='__main__':unittest.main()
