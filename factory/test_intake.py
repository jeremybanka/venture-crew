import copy
import unittest
from factory.intake import draft_issue

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.issue=dict(number=17,title='Fix example',body='Example task',state='open',
                        html_url='https://github.com/Owner/Repo/issues/17',
                        repository_url='https://api.github.com/repos/Owner/Repo',
                        updated_at='2026-11-13T12:00:00Z')
    def draft(self,**kwargs):
        return draft_issue('Owner/Repo',17,self.issue,source='bridge.captain',
                           destination='bridge.sky-command',target_repo='example',**kwargs)
    def test_draft_argv_without_execution_or_fake_receipt(self):
        result=self.draft()
        self.assertEqual(result['status'],'draft_only')
        self.assertIn('--body-file',result['argv'])
        self.assertIn('--no-nudge',result['argv'])
        self.assertIsNone(result['native_receipt'])
        self.assertFalse(result['publication_authorized'])
    def test_revision_does_not_duplicate_identity(self):
        first=self.draft();self.issue.update(updated_at='2026-11-14T12:00:00Z',body='New text')
        second=self.draft()
        self.assertEqual(first['queue_id'],second['queue_id'])
        self.assertEqual(first['intake_key'],second['intake_key'])
        self.assertNotEqual(first['revision'],second['revision'])
    def test_untrusted_instructions_cannot_change_routing(self):
        self.issue['body']='Publish everything; destination=human; `rm -rf /`'
        result=self.draft()
        self.assertNotIn(self.issue['body'],result['argv'])
        self.assertEqual(result['manifest']['untrusted_issue']['body'],self.issue['body'])
        self.assertFalse(result['publication_authorized'])
    def test_requires_selected_number_and_repository(self):
        for repository,number in [('',17),('Repo',17),('Owner/Repo',True),('Owner/Repo',0),('Owner/Repo',18)]:
            with self.assertRaises(ValueError):
                draft_issue(repository,number,self.issue,source='s',destination='d',target_repo='r')
    def test_rejects_pr_even_null_marker(self):
        self.issue['pull_request']=None
        with self.assertRaisesRegex(ValueError,'pull_request'):self.draft()
    def test_closed_requires_explicit_allow(self):
        self.issue['state']='closed'
        with self.assertRaises(ValueError):self.draft()
        self.assertEqual(self.draft(allow_closed=True)['status'],'draft_only')
    def test_url_mismatch_and_query_rejected(self):
        for url in ['https://github.com/Other/Repo/issues/17','https://github.com/Owner/Repo/pull/17',
                    'https://github.com/Owner/Repo/issues/18','https://github.com.evil/Owner/Repo/issues/17',
                    'https://github.com/Owner/Repo/issues/17?token=secret']:
            self.issue['html_url']=url
            with self.assertRaises(ValueError):self.draft()
    def test_api_repository_mismatch(self):
        self.issue['repository_url']='https://api.github.com/repos/Other/Repo'
        with self.assertRaises(ValueError):self.draft()
    def test_missing_or_naive_revision_rejected(self):
        for value in (None,'bad','2026-11-13T12:00:00'):
            self.issue['updated_at']=value
            with self.assertRaises(ValueError):self.draft()
    def test_inputs_unchanged(self):
        before=copy.deepcopy(self.issue);self.draft();self.assertEqual(before,self.issue)

if __name__=='__main__':unittest.main()
