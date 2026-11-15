import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from .stacks import StackPublisher


class StackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.calls = []; self.stack = None; self.mode = 'success'; self.conflict = False
        self.expected = [dict(number=1, head='first', head_sha='a'*40, base='main', base_sha='b'*40),
                         dict(number=2, head='second', head_sha='c'*40, base='first', base_sha='a'*40)]
        self.prs = {p['number']: dict(number=p['number'], state='open', draft=False, merged_at=None,
                    html_url=f'https://github.com/owner/repo/pull/{p["number"]}',
                    head=dict(ref=p['head'], sha=p['head_sha'], repo=dict(full_name='owner/repo')),
                    base=dict(ref=p['base'], sha=p['base_sha'], repo=dict(full_name='owner/repo'))) for p in self.expected}
        self.pub = StackPublisher(Path(self.tmp.name).resolve()/'state', gh_executable='/approved/gh', runner=self.run_api)

    def make_stack(self):
        return dict(number=7, open=True, base=dict(ref='main'), url='https://api.github.com/repos/owner/repo/stacks/7',
                    pull_requests=[copy.deepcopy(self.prs[n]) for n in (1, 2)])

    def run_api(self, argv):
        self.calls.append(argv)
        method = argv[argv.index('--method')+1]
        endpoint = next(x for x in argv if x.startswith('repos/'))
        if method == 'POST':
            self.assertEqual(endpoint, 'repos/owner/repo/stacks')
            self.assertEqual([argv[i+1] for i,v in enumerate(argv) if v == '-F'], ['pull_requests[]=1','pull_requests[]=2'])
            if self.mode != 'timeout_before': self.stack = self.make_stack()
            if self.mode == 'changed_head': self.prs[2]['head']['sha'] = 'd'*40
            if self.mode.startswith('timeout'): raise TimeoutError()
            value = self.stack
        elif '/pulls/' in endpoint: value = self.prs[int(endpoint.rsplit('/',1)[1])]
        elif 'stacks?' in endpoint:
            n = int(endpoint.split('pull_request=')[1].split('&')[0])
            value = [dict(number=8)] if self.conflict and n == 2 else ([self.stack] if self.stack else [])
        elif endpoint.endswith('/stacks/7'): value = self.stack
        else: raise AssertionError(endpoint)
        return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')

    def register(self, **kwargs):
        args = dict(authorized_repo='owner/repo', pull_requests=self.expected); args.update(kwargs)
        return self.pub.register(**args)

    def writes(self): return [c for c in self.calls if 'POST' in c]

    def test_create_and_idempotent_retry(self):
        self.assertTrue(self.register()['created'])
        self.assertFalse(self.register()['created'])
        self.assertEqual(len(self.writes()), 1)
        self.assertTrue(all('merge' not in c and 'push' not in c for c in self.calls))
        self.assertTrue(all(c[c.index('--hostname')+1]=='github.com' for c in self.calls))
        self.assertTrue(all('X-GitHub-Api-Version: 2026-03-10' in c for c in self.calls))

    def test_timeout_after_creation_reconciles(self):
        self.mode = 'timeout_after'
        self.assertEqual(self.register()['status'], 'verified')
        self.assertEqual(len(self.writes()), 1)

    def test_unknown_never_retried_across_instance_or_new_head(self):
        self.mode = 'timeout_before'
        self.assertEqual(self.register()['status'], 'unknown')
        self.pub = StackPublisher(Path(self.tmp.name).resolve()/'state', gh_executable='/approved/gh', runner=self.run_api)
        self.expected[1]['head_sha'] = 'd'*40; self.prs[2]['head']['sha'] = 'd'*40
        self.assertEqual(self.register()['reason'], 'prior_stack_attempt_requires_reconciliation')
        self.assertEqual(len(self.writes()), 1)

    def test_unknown_later_readback_reconciles(self):
        self.mode = 'timeout_before'; self.register(); self.stack = self.make_stack()
        self.assertFalse(self.register()['created']); self.assertEqual(len(self.writes()), 1)

    def test_conflicting_membership_blocks(self):
        self.stack = self.make_stack(); self.conflict = True
        with self.assertRaises(ValueError): self.register()
        self.assertFalse(self.writes())

    def test_malformed_membership_never_allows_post(self):
        original = self.run_api
        for malformed in ({}, 0, False, None, '', [], {'number': True}, {'number': 0}, {'number': '7'}):
            with self.subTest(malformed=malformed):
                def runner(argv):
                    if any('stacks?' in x for x in argv):
                        self.calls.append(argv)
                        return SimpleNamespace(returncode=0, stdout=json.dumps([malformed]), stderr='')
                    return original(argv)
                self.pub.runner = runner
                with self.assertRaisesRegex(ValueError, 'malformed_stack_membership'):
                    self.register()
                self.assertFalse(self.writes())

    def test_partial_membership_blocks(self):
        self.conflict = True
        with self.assertRaises(ValueError): self.register()
        self.assertFalse(self.writes())

    def test_wrong_order_or_revision_blocks_existing(self):
        self.stack = self.make_stack(); self.stack['pull_requests'].reverse()
        with self.assertRaises(ValueError): self.register()
        self.assertFalse(self.writes())

    def test_pr_eligibility(self):
        original = copy.deepcopy(self.prs)
        for key,value in [('draft',True),('draft',None),('state','closed'),('merged_at','yesterday')]:
            self.prs = copy.deepcopy(original); self.prs[2][key] = value
            with self.assertRaises(ValueError): self.register()
        self.prs = copy.deepcopy(original); self.prs[2]['head']['repo']['full_name']='fork/repo'
        with self.assertRaises(ValueError): self.register()
        self.assertFalse(self.writes())

    def test_exact_base_and_head_required(self):
        original = copy.deepcopy(self.prs)
        for side in ('base','head'):
            self.prs = copy.deepcopy(original); self.prs[2][side]['sha']='d'*40
            with self.assertRaises(ValueError): self.register()
        self.assertFalse(self.writes())

    def test_changed_head_after_create_is_unknown(self):
        self.mode = 'changed_head'
        self.assertEqual(self.register()['status'], 'unknown')
        self.assertEqual(len(self.writes()), 1)

    def test_bad_authorization_and_chain_make_no_calls(self):
        for repo in ('', 'owner/../repo', '-owner/repo'):
            with self.assertRaises(ValueError): self.register(authorized_repo=repo)
        for mutate in (lambda p:p[1].update(base='wrong'), lambda p:p[1].update(number=1),
                       lambda p:p[1].update(number=True), lambda p:p[1].update(head_sha='short')):
            prs=copy.deepcopy(self.expected); mutate(prs)
            with self.assertRaises(ValueError): self.register(pull_requests=prs)
        self.assertFalse(self.calls)

    def test_symlink_journal_blocks(self):
        target=Path(self.tmp.name)/'elsewhere';target.touch()
        (self.pub.root/'stacks.sqlite3').symlink_to(target)
        with self.assertRaises(OSError): self.register()
        self.assertFalse(self.calls)


if __name__ == '__main__': unittest.main()
