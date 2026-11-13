import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from .checks import discover, coverage_error
from .check_fixtures import coverage_fixture
from . import test_publication


class CheckDiscoveryTests(unittest.TestCase):
    def test_sources_are_pinned_and_whole_workflows_are_reviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(['git', '-C', tmp, *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init');git('config', 'user.name', 'Fixture');git('config', 'user.email', 'fixture@example.invalid')
            (root/'.github/workflows').mkdir(parents=True)
            workflow = 'jobs:\n  lint:\n    steps:\n      - run: pnpm lint:unused\n      - run: pnpm lint:unused:production\n      - uses: ./local-action\n'
            (root/'.github/workflows/lint.yml').write_text(workflow)
            (root/'package.json').write_text(json.dumps({'scripts': {'lint': 'pnpm lint:unused', 'test': 'node test.js'}}))
            (root/'hk.pkl').write_text('fixture hook')
            git('add', '.');git('commit', '-m', 'fixture');head = git('rev-parse', 'HEAD')
            first = discover(tmp, head)
            (root/'.github/workflows/lint.yml').write_text('changed dirty content')
            self.assertEqual(first, discover(tmp, head))
            self.assertEqual(len(first['units']), 4)
            self.assertEqual(first['units'][0]['content'], workflow)
            with self.assertRaises(ValueError):discover(tmp, 'HEAD')

    def test_missing_failed_stale_and_unreviewed_coverage_blocks(self):
        head = 'a'*40
        good = coverage_fixture(head)
        self.assertIsNone(coverage_error(good, head, 'warden'))
        for change in ('missing', 'stale', 'failed', 'unreviewed', 'waiver', 'tampered', 'unknown'):
            bad = copy.deepcopy(good)
            if change == 'missing':bad['coverage'] = {}
            if change == 'stale':bad['runs']['test']['head_sha'] = 'b'*40
            if change == 'failed':bad['runs']['test']['exit_code'] = 1
            if change == 'unreviewed':bad['reviewer'] = 'strider1'
            if change == 'waiver':bad['coverage']['.github/workflows/test.yml'] = {'disposition': 'not_applicable', 'reason': ''}
            if change == 'tampered':bad['manifest']['units'] = []
            if change == 'unknown':bad['coverage']['.github/workflows/test.yml']['disposition'] = 'pending'
            self.assertIsNotNone(coverage_error(bad, head, 'warden'), change)

    def test_publication_requires_coverage_even_if_generic_tests_passed(self):
        helper = test_publication.PublicationTests()
        item = helper.slice();del item['check_coverage']
        self.assertEqual(helper.plan([item])[0]['reason'], 'check_coverage_missing')
