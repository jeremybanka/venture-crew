"""Native unused allowances have no reset timestamp, not an invented deadline."""
from pathlib import Path
import tempfile
import unittest

from .controller import Controller


class InactiveWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1000
        self.c = Controller(Path(self.tmp.name) / 'budget.sqlite3', clock=lambda: self.now)
        self.c.configure('claude', 'claude:fixture', {'five_hour': 40, 'weekly': 40})

    def sample(self):
        return dict(provider='claude', account_id='claude:fixture', account_bound=True,
                    freshness_proven=True, observed_at=self.now, usage_allowed=True,
                    source='native-fixture', windows={
                        'five_hour': dict(inactive=True, remaining_percent=100, resets_at=None),
                        'weekly': dict(remaining_percent=69, resets_at=8000)})

    def ready(self):
        self.assertTrue(self.c.observe('claude', self.sample())['accepted'])
        self.c.arm('claude', 'fixture opening')
        self.assertTrue(self.c.status('claude')['admission_open'])

    def test_inactive_persists_without_synthetic_reset_and_stays_inactive(self):
        self.ready()
        self.now += 1
        self.assertIsNone(self.c.observe('claude', self.sample())['reason'])
        with self.c.tx(readonly=True) as db:
            self.assertEqual(self.c.state(db, 'claude')['last']['windows']['five_hour'],
                             dict(inactive=True, remaining_percent=100, resets_at=None))
        self.assertTrue(self.c.status('claude')['admission_open'])

    def test_activation_is_not_reset_but_later_return_to_inactive_is(self):
        self.ready()
        self.now += 1
        active = self.sample()
        active['windows']['five_hour'] = dict(remaining_percent=99, resets_at=3000)
        self.assertIsNone(self.c.observe('claude', active)['reason'])
        self.assertTrue(self.c.status('claude')['admission_open'])
        self.now += 1
        self.assertEqual(self.c.observe('claude', self.sample())['reason'], 'reset_requires_rearm')
        self.assertFalse(self.c.status('claude')['admission_open'])
        self.c.arm('claude', 'explicit reset rearm')
        self.assertTrue(self.c.status('claude')['admission_open'])

    def test_invalid_inactive_representations_are_rejected(self):
        base = self.sample()['windows']['five_hour']
        bad = [dict(base, inactive=x) for x in (None, 'true', 1, 0, [], {})]
        bad += [dict(base, remaining_percent=x) for x in (99, True, float('nan'))]
        bad += [dict(base, resets_at=x) for x in (0, 3000, '3000', False)]
        bad += [dict(remaining_percent=100, resets_at=None),
                dict(inactive=False, remaining_percent=100, resets_at=None),
                dict(inactive=True, remaining_percent=100)]
        for window in bad:
            with self.subTest(window=window):
                self.now += 1
                sample = self.sample()
                sample['windows']['five_hour'] = window
                self.assertFalse(self.c.observe('claude', sample)['accepted'])
                self.assertFalse(self.c.status('claude')['admission_open'])

    def test_floors_still_apply_to_every_window(self):
        self.ready()
        self.now += 1
        sample = self.sample()
        sample['windows']['weekly']['remaining_percent'] = 40
        self.c.observe('claude', sample)
        self.assertEqual(self.c.status('claude')['gate_reason'], 'usage_floor:weekly')
        self.c.configure('claude', 'claude:fixture', {'five_hour': 100})
        self.assertTrue(self.c.observe('claude', self.sample())['accepted'])
        with self.assertRaises(ValueError):
            self.c.arm('claude', '100 percent reserve leaves no spend')

    def test_initial_activation_at_floor_stays_closed(self):
        self.ready()
        self.now += 1
        sample = self.sample()
        sample['windows']['five_hour'] = dict(remaining_percent=40, resets_at=3000)
        self.c.observe('claude', sample)
        self.assertEqual(self.c.status('claude')['gate_reason'], 'usage_floor:five_hour')

    def test_inactive_never_bypasses_identity_freshness_or_required_windows(self):
        self.ready()
        for change in ({'account_id': 'claude:other'}, {'account_bound': False},
                       {'freshness_proven': False}, {'usage_allowed': False}):
            self.now += 1
            sample = self.sample()
            sample.update(change)
            self.assertFalse(self.c.observe('claude', sample)['accepted'])
        self.now += 1
        sample = self.sample()
        del sample['windows']['weekly']
        self.assertFalse(self.c.observe('claude', sample)['accepted'])
        self.now += 1
        self.assertTrue(self.c.observe('claude', self.sample())['accepted'])
        self.c.arm('claude', 'fixture reopening')
        self.now += 301
        self.assertEqual(self.c.status('claude')['gate_reason'], 'stale_observation')
        sample = self.sample()
        sample['observed_at'] -= 301
        self.assertFalse(self.c.observe('claude', sample)['accepted'])

    def test_reset_latches_factory_but_first_activation_does_not(self):
        self.ready()
        self.c.open_factory([40, 40], 'fixture factory')
        self.now += 1
        sample = self.sample()
        sample['windows']['five_hour'] = dict(remaining_percent=99, resets_at=3000)
        self.c.observe('claude', sample)
        self.assertTrue(self.c.status('claude')['admission_open'])
        self.now += 1
        self.c.observe('claude', self.sample())
        self.assertFalse(self.c.status('claude')['admission_open'])
        self.now += 1
        self.c.observe('claude', self.sample())
        self.assertFalse(self.c.status('claude')['admission_open'])
        self.c.open_factory([40, 40], 'explicit reopening')
        self.assertTrue(self.c.status('claude')['admission_open'])


if __name__ == '__main__':
    unittest.main()
