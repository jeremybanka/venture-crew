"""Opening reserves apply only to configured reserve windows."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from .controller import Controller


class MixedFloorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'budget.sqlite3'
        self.now = 1000
        self.c = Controller(self.path, clock=lambda: self.now)

    def sample(self, provider, five=39, weekly=69):
        return dict(provider=provider, account_id=provider + ':fixture', account_bound=True,
                    freshness_proven=True, observed_at=self.now, usage_allowed=True,
                    source='fixture', windows={
                        'five_hour': dict(remaining_percent=five, resets_at=3000),
                        'weekly': dict(remaining_percent=weekly, resets_at=8000)})

    def ready(self):
        self.c.configure('claude', 'claude:fixture', {'five_hour': 0, 'weekly': 40},
                         reserve_windows=['weekly'])
        self.c.configure('codex', 'codex:fixture', {'five_hour': 10, 'weekly': 10})
        self.c.observe('claude', self.sample('claude'))
        self.c.observe('codex', self.sample('codex', five=80))
        self.c.open_factory([40, 40], 'fixture opening')

    def test_opening_keeps_fixed_floors_and_codex_reserves_all_windows(self):
        self.ready()
        self.assertEqual(self.c.status('claude')['floors'], {'five_hour': 0, 'weekly': 40})
        self.assertEqual(self.c.status('codex')['floors'], {'five_hour': 40, 'weekly': 40})
        self.assertTrue(self.c.status('claude')['admission_open'])
        self.c.open_factory([50, 55], 'new reserves')
        self.assertEqual(self.c.status('claude')['floors'], {'five_hour': 0, 'weekly': 55})
        self.assertEqual(self.c.status('codex')['floors'], {'five_hour': 50, 'weekly': 50})

    def test_zero_availability_closes_only_claude(self):
        self.ready()
        self.now += 1
        self.c.observe('claude', self.sample('claude', five=0))
        self.assertFalse(self.c.status('claude')['admission_open'])
        self.assertTrue(self.c.status('codex')['admission_open'])
        self.now += 1
        self.c.observe('claude', self.sample('claude', five=39))
        self.assertFalse(self.c.status('claude')['admission_open'])

    def test_weekly_reserve_still_stops_at_40(self):
        self.ready()
        self.now += 1
        self.c.observe('claude', self.sample('claude', weekly=40))
        self.assertFalse(self.c.status('claude')['admission_open'])
        self.assertTrue(self.c.status('codex')['admission_open'])

    def test_legacy_state_without_reserve_windows_defaults_to_all(self):
        self.ready()
        with self.c.tx() as db:
            state = self.c.state(db, 'codex')
            del state['reserve_windows']
            self.c.save(db, 'codex', state, 'fixture_legacy', {})
        self.c.open_factory([60, 40], 'legacy opening')
        self.assertEqual(self.c.status('codex')['floors'], {'five_hour': 60, 'weekly': 60})

    def test_invalid_subset_rejected_without_mutating_configuration(self):
        self.ready()
        before = self.c.status('claude')
        for subset in ([], 'weekly', {}, True, ['unknown'], ['weekly', 'weekly'],
                       [1], [None], [''], ['bad key'], ['weekly', 'unknown']):
            with self.subTest(subset=subset), self.assertRaises(ValueError):
                self.c.configure('claude', 'claude:fixture', {'five_hour': 0, 'weekly': 40},
                                 reserve_windows=subset)
            self.assertEqual(self.c.status('claude'), before)

    def test_cli_configure_accepts_json_subset(self):
        result = subprocess.run([sys.executable, '-m', 'budget', '--db', str(self.path),
                                 'configure', 'claude', '--account', 'claude:fixture',
                                 '--floors', '{"five_hour":0,"weekly":40}',
                                 '--reserve-windows', '["weekly"]'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)['reserve_windows'], ['weekly'])


if __name__ == '__main__':
    unittest.main()
