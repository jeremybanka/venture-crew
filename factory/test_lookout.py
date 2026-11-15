import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from .lookout import Lookout, classify, evidence_url


def pr(checks=None, **kw):
    value = dict(number=12, state='OPEN', headRefOid='a'*40,
                 statusCheckRollup=[] if checks is None else checks)
    value.update(kw)
    return value


def check(name='Knip', conclusion='SUCCESS', status='COMPLETED'):
    return dict(__typename='CheckRun', name=name, conclusion=conclusion, status=status)


class LookoutTests(unittest.TestCase):
    def test_classifications(self):
        for rows, expected in [([], 'missing'), ([check()], 'observed_green'),
                               ([check(conclusion='FAILURE')], 'failed'),
                               ([check(status='IN_PROGRESS')], 'pending'),
                               ([check(conclusion='SKIPPED')], 'unknown'),
                               ([{'__typename': 'StatusContext', 'context': 'external', 'state': 'ERROR'}], 'failed')]:
            self.assertEqual(classify(pr(rows))['status'], expected)
        self.assertEqual(classify(pr([check()]), ['Knip', 'Tests'])['missing_checks'], ['Tests'])
        self.assertEqual(classify(pr(state='MERGED'))['status'], 'merged')

    def observer(self, root, values):
        commands = []
        def run(argv):
            commands.append(argv)
            value = values.pop(0)
            return SimpleNamespace(returncode=0, stdout=json.dumps(value))
        return Lookout(repo='owner/repo', pr=12, gh_executable='/usr/bin/gh',
                       state_file=str(Path(root).resolve()/'lookout.sqlite3'), runner=run), commands

    def test_dedupe_survives_restart_and_head_change(self):
        with TemporaryDirectory() as root:
            one = pr([check(conclusion='FAILURE')])
            observer, commands = self.observer(root, [one, one])
            value = observer.poll()
            self.assertTrue(value['changed']); self.assertIn('implementor', value['handoff'])
            observer, _ = self.observer(root, [one, one])
            self.assertFalse(observer.poll()['changed'])
            two = pr([check()], headRefOid='b'*40)
            observer, _ = self.observer(root, [two, two])
            self.assertTrue(observer.poll()['changed'])
            self.assertTrue(all(cmd[1:3] == ['pr', 'view'] for cmd in commands))

    def test_head_race_fails_closed(self):
        with TemporaryDirectory() as root:
            observer, _ = self.observer(root, [pr([check()]), pr([check()], headRefOid='b'*40)])
            self.assertEqual(observer.poll()['status'], 'stale')

    def test_latest_rollup_used_and_read_failure_sanitized(self):
        with TemporaryDirectory() as root:
            observer, _ = self.observer(root, [pr([check()]), pr([check(conclusion='FAILURE')])])
            self.assertEqual(observer.poll()['status'], 'failed')
            observer.runner = lambda argv: SimpleNamespace(returncode=1, stdout='secret')
            self.assertEqual(observer.poll()['status'], 'unavailable')

    def test_terminal_rechecked(self):
        with TemporaryDirectory() as root:
            observer, _ = self.observer(root, [pr(state='CLOSED'), pr(state='CLOSED')])
            self.assertTrue(observer.poll()['terminal'])

    def test_unavailable_sanitized(self):
        with TemporaryDirectory() as root:
            observer, _ = self.observer(root, [{'secret': 'do not persist'}])
            value = observer.poll()
            self.assertEqual(value['status'], 'unavailable')
            self.assertNotIn('secret', json.dumps(value))
            self.assertNotIn(b'do not persist', (Path(root)/'lookout.sqlite3').read_bytes())

    def test_evidence_urls_are_same_repo_and_sanitized(self):
        good = 'https://github.com/owner/repo/actions/runs/123/job/456'
        self.assertEqual(evidence_url(good+'?secret=x#fragment', 'owner/repo'), good)
        for url in ('http://github.com/owner/repo/runs/123',
                    'https://github.com/other/repo/runs/123',
                    'https://github.com.evil.test/owner/repo/runs/123',
                    'https://secret@github.com/owner/repo/runs/123',
                    'https://github.com/owner/repo/runs/secret',
                    'https://github.com/owner/repo/../other/runs/123'):
            self.assertIsNone(evidence_url(url, 'owner/repo'))
        row = {**check(conclusion='FAILURE'), 'detailsUrl': good+'?secret=x'}
        self.assertEqual(classify(pr([row]), repo='owner/repo')['checks'][0]['url'], good)

    def test_report_recoverable_after_restart_without_network(self):
        with TemporaryDirectory() as root:
            one = pr([check(conclusion='FAILURE')])
            observer, _ = self.observer(root, [one, one])
            observed = observer.poll()  # Simulate failure delivering stdout here.
            recovered, commands = self.observer(root, [])
            self.assertEqual(recovered.latest(), observed)
            self.assertEqual(recovered.latest(), observed)  # Non-consuming.
            self.assertEqual(commands, [])
            self.assertIsInstance(observed['checked_at'], float)

    def test_legacy_digest_state_migrates_and_missing_latest_is_none(self):
        with TemporaryDirectory() as root:
            observer, _ = self.observer(root, [pr(), pr()])
            self.assertIsNone(observer.latest())
            with sqlite3.connect(observer.path) as db:
                db.execute('CREATE TABLE observations (key TEXT PRIMARY KEY, digest TEXT NOT NULL, checked_at REAL NOT NULL)')
                db.execute('INSERT INTO observations VALUES (?,?,?)', ('owner/repo#12', 'old', 0))
            self.assertIsNone(observer.latest())
            value = observer.poll()
            self.assertEqual(observer.latest(), value)

    def test_invalid_scope_and_symlink_rejected(self):
        with TemporaryDirectory() as root:
            root = str(Path(root).resolve())
            args = dict(repo='owner/repo', pr=12, gh_executable='/bin/gh', state_file=root+'/state')
            for change in ({'repo': '-bad/repo'}, {'pr': True}, {'gh_executable': 'gh'}, {'state_file': 'relative'}):
                with self.assertRaises(ValueError): Lookout(**{**args, **change})
            Path(root+'/alias').symlink_to(Path(root)/'state')
            with self.assertRaises(ValueError): Lookout(**{**args, 'state_file': root+'/alias'})


if __name__ == '__main__': unittest.main()
