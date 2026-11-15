"""Reset precision regressions use temporary databases, never live quota state."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from .controller import Controller


class ResetJitterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.serial = 0

    def opening(self, weekly_reset=1794895199):
        self.now = 1794645000
        self.serial += 1
        c = Controller(Path(self.tmp.name) / str(self.serial), clock=lambda: self.now)
        self.samples = {}
        for p in ('codex', 'claude'):
            self.samples[p] = dict(
                provider=p, account_id=p + ':fixture', account_bound=True,
                freshness_proven=True, observed_at=self.now, usage_allowed=True,
                source='fixture', windows={
                    'five_hour': dict(remaining_percent=90, resets_at=self.now + 3600),
                    'weekly': dict(remaining_percent=64, resets_at=weekly_reset),
                })
            c.configure(p, p + ':fixture', {'five_hour': 0, 'weekly': 40}, max_active=1)
            self.assertTrue(c.observe(p, self.samples[p])['accepted'])
        c.open_factory([40, 40], 'fixture opening')
        return c

    def observe(self, c, *, p='claude', window='weekly', reset=None,
                remaining=None, **changes):
        self.now += 1
        raw = deepcopy(self.samples[p])
        raw['observed_at'] = self.now
        if reset is not None:
            raw['windows'][window]['resets_at'] = reset
        if remaining is not None:
            raw['windows'][window]['remaining_percent'] = remaining
        raw.update(changes)
        return c.observe(p, raw)

    def test_reported_weekly_oscillation_preserves_opening_and_raw_audit(self):
        for initial in (1794895199, 1794895200):
            with self.subTest(initial=initial):
                c = self.opening(initial)
                alternate = 1794895200 if initial == 1794895199 else 1794895199
                for reset in (alternate, initial, alternate, initial):
                    self.assertTrue(self.observe(c, reset=reset)['accepted'])
                    state = c.status('claude')
                    self.assertTrue(state['admission_open'])
                    self.assertEqual(state['last']['windows']['weekly']['resets_at'], reset)
                with c.tx(readonly=True) as db:
                    audit = json.loads(db.execute(
                        "SELECT detail FROM audit WHERE provider='claude' AND event='observe' "
                        "ORDER BY rowid DESC LIMIT 1").fetchone()[0])
                self.assertFalse(audit['reset_requires_rearm'])
                self.assertEqual(audit['sample']['windows']['weekly']['resets_at'], initial)

    def test_each_claude_window_accepts_jitter_with_decreasing_usage(self):
        for window in ('five_hour', 'weekly'):
            with self.subTest(window=window):
                c = self.opening()
                old = self.samples['claude']['windows'][window]
                self.observe(c, window=window, reset=old['resets_at'] + 1,
                             remaining=old['remaining_percent'] - 1)
                self.assertTrue(c.status('claude')['admission_open'])

    def test_stable_reference_prevents_cumulative_drift_after_restart(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                c = self.opening()
                self.observe(c, reset=1794895199 + direction)
                self.assertTrue(c.status('claude')['admission_open'])
                c = Controller(c.path, clock=lambda: self.now)
                self.observe(c, reset=1794895199 + 2 * direction)
                self.assertFalse(c.status('claude')['admission_open'])
                self.assertTrue(c.status('codex')['admission_open'])

    def test_legacy_state_without_epoch_metadata_migrates_conservatively(self):
        c = self.opening()
        with c.tx() as db:
            state = c.state(db, 'claude')
            state.pop('reset_epochs', None)
            c.save(db, 'claude', state, 'fixture_legacy', {})
        self.observe(c, reset=1794895200)
        self.assertTrue(c.status('claude')['admission_open'])
        self.observe(c, reset=1794895201)
        self.assertFalse(c.status('claude')['admission_open'])

    def test_tolerance_boundary_and_real_reset_still_close(self):
        for delta in (-86400, -1.001, 1.001, 86400):
            with self.subTest(delta=delta):
                c = self.opening()
                self.observe(c, reset=1794895199 + delta)
                self.assertFalse(c.status('claude')['admission_open'])
                self.assertTrue(c.status('codex')['admission_open'])

    def test_codex_keeps_strict_reset_comparison_for_every_window(self):
        for window in ('five_hour', 'weekly'):
            with self.subTest(window=window):
                c = self.opening()
                old = self.samples['codex']['windows'][window]['resets_at']
                self.observe(c, p='codex', window=window, reset=old + 1)
                self.assertFalse(c.status('codex')['admission_open'])
                self.assertTrue(c.status('claude')['admission_open'])

    def test_weekly_allowance_increase_is_never_explained_as_timestamp_jitter(self):
        for window in ('weekly',):
            with self.subTest(window=window):
                c = self.opening()
                old = self.samples['claude']['windows'][window]
                self.observe(c, window=window, reset=old['resets_at'] + 1,
                             remaining=old['remaining_percent'] + .01)
                self.assertFalse(c.status('claude')['admission_open'])

    def test_jitter_never_extends_earliest_reset_deadline(self):
        for first_delta in (-1, 1):
            with self.subTest(first_delta=first_delta):
                original = 1794645004
                c = self.opening(original)
                self.observe(c, reset=original + first_delta)
                self.assertTrue(c.status('claude')['admission_open'])
                self.now = min(original, original + first_delta)
                self.assertEqual(c.status('claude')['gate_reason'], 'reset_expired')
                self.observe(c, reset=original + 1)
                self.assertFalse(c.status('claude')['admission_open'])

    def test_jitter_does_not_reopen_operator_or_reset_latches(self):
        for stop in ('pause', 'reset'):
            with self.subTest(stop=stop):
                c = self.opening()
                anchor = 1794895199
                if stop == 'pause':
                    c.pause('claude')
                else:
                    anchor += 86400
                    self.observe(c, reset=anchor)
                self.observe(c, reset=anchor + 1)
                self.assertFalse(c.status('claude')['admission_open'])
                c.open_factory([40, 40], 'explicit fixture reopening')
                self.assertTrue(c.status('claude')['admission_open'])

    def test_identity_freshness_and_actual_provider_denials_still_close(self):
        cases = ({'account_id': 'other'}, {'account_bound': False},
                 {'freshness_proven': False}, {'usage_allowed': False},
                 {'observed_at': 1794645032},
                 {'windows': {}}, {'windows': {'weekly': None}})
        for changes in cases:
            with self.subTest(changes=changes):
                c = self.opening()
                result = self.observe(c, reset=1794895200, **changes)
                self.assertFalse(result['accepted'])
                self.assertFalse(c.status('claude')['admission_open'])
                self.assertTrue(c.status('codex')['admission_open'])

    def test_newer_but_stale_sample_and_clock_rollback_still_close(self):
        c = self.opening()
        self.now += 400
        result = self.observe(c, reset=1794895200, observed_at=self.now - 301)
        self.assertFalse(result['accepted'])
        self.assertFalse(c.status('claude')['admission_open'])
        c = self.opening()
        self.observe(c, reset=1794895200)
        self.now -= 32
        self.assertEqual(c.status('claude')['gate_reason'], 'clock_rollback')

    def test_floor_and_existing_permit_concurrency_are_preserved(self):
        c = self.opening()
        permit = c.admit('claude', 'reviewer', 'session', 'turn')
        self.assertTrue(permit['allowed'])
        self.observe(c, reset=1794895200)
        self.assertEqual(c.admit('claude', 'other', 'other', 'turn')['reason'],
                         'provider_concurrency')
        self.assertEqual(c.status('claude')['active_permits'][0]['id'], permit['permit'])
        self.observe(c, reset=1794895199, remaining=40)
        self.assertFalse(c.status('claude')['admission_open'])
        self.assertEqual(len(c.status('claude')['active_permits']), 1)

    def test_replayed_jitter_does_not_refresh_observation(self):
        c = self.opening()
        self.observe(c, reset=1794895200)
        observed = self.now
        self.observe(c, reset=1794895199, observed_at=observed)
        self.assertEqual(c.status('claude')['last']['observed_at'], observed)
        self.now = observed + 301
        self.assertEqual(c.status('claude')['gate_reason'], 'stale_observation')


if __name__ == '__main__':
    unittest.main()
