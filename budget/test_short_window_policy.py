"""Claude five-hour renewal is not a factory stop. Temporary fixture DBs only."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from .controller import Controller


class ShortWindowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1000
        self.c = Controller(Path(self.tmp.name) / "state", clock=lambda: self.now)
        self.samples = {}
        for p in ("codex", "claude"):
            self.c.configure(p, p + ":fixture", {"five_hour": 0, "weekly": 40},
                             reserve_windows=["weekly"], freshness=300)
            self.samples[p] = dict(provider=p, account_id=p + ":fixture",
                account_bound=True, freshness_proven=True, observed_at=self.now,
                usage_allowed=True, source="fixture", windows={
                    "five_hour": dict(remaining_percent=70, resets_at=1100),
                    "weekly": dict(remaining_percent=80, resets_at=10000)})
            self.assertTrue(self.c.observe(p, self.samples[p])["accepted"])
        self.c.open_factory([40, 40], "fixture authorized opening")

    def observe(self, p="claude", **changes):
        self.now += 1
        raw = deepcopy(self.samples[p])
        raw.update(changes, observed_at=self.now)
        return self.c.observe(p, raw)

    def test_rollover_refill_and_inactive_preserve_opening_and_permit(self):
        permit = self.c.admit("claude", "worker", "session", "turn")
        before = self.c.status("claude")
        for window in (dict(remaining_percent=100, resets_at=20000),
                       dict(remaining_percent=100, resets_at=None, inactive=True),
                       dict(remaining_percent=99, resets_at=21000)):
            windows = deepcopy(self.samples["claude"]["windows"])
            windows["five_hour"] = window
            self.assertTrue(self.observe(windows=windows)["accepted"])
            state = self.c.status("claude")
            self.assertTrue(state["admission_open"])
            self.assertEqual(state["opening_id"], before["opening_id"])
            self.assertEqual(state["active_permits"][0]["id"], permit["permit"])
            self.assertFalse(self.c.admit("claude", "other", "other", "other")["allowed"])

    def test_short_expiry_uses_original_freshness_not_reset_deadline(self):
        self.now = 1101
        self.assertTrue(self.c.status("claude")["admission_open"])
        self.assertTrue(self.observe()["accepted"])  # fresh native positive evidence, old reset timestamp
        self.assertTrue(self.c.status("claude")["admission_open"])
        self.now += 301
        self.assertEqual(self.c.status("claude")["gate_reason"], "stale_observation")
        self.assertFalse(self.c.admit("claude", "worker", "session", "turn")["allowed"])

    def test_expiry_cannot_renew_cached_observation(self):
        self.now = 1101
        original = self.c.status("claude")["last"]["observed_at"]
        self.c.refresh_failed("claude", "claude:fixture", "transient")
        self.assertEqual(self.c.status("claude")["last"]["observed_at"], original)
        self.now = 1301
        self.assertEqual(self.c.status("claude")["gate_reason"], "stale_observation")

    def test_exhaustion_latches_and_refill_never_reopens(self):
        permit = self.c.admit('claude', 'worker', 'session', 'turn')
        windows = deepcopy(self.samples["claude"]["windows"])
        windows["five_hour"]["remaining_percent"] = 0
        self.assertTrue(self.observe(windows=windows)["accepted"])
        self.assertFalse(self.c.status("claude")["admission_open"])
        windows["five_hour"] = dict(remaining_percent=100, resets_at=20000)
        self.assertTrue(self.observe(windows=windows)["accepted"])
        self.assertFalse(self.c.status("claude")["admission_open"])

    def test_weekly_reset_and_codex_short_reset_remain_strict(self):
        for p, key in (("claude", "weekly"), ("codex", "five_hour")):
            windows = deepcopy(self.samples[p]["windows"])
            windows[key]["resets_at"] += 2000
            self.assertTrue(self.observe(p, windows=windows)["accepted"])
            self.assertFalse(self.c.status(p)["admission_open"])

    def test_weekly_floor_still_closes(self):
        windows = deepcopy(self.samples["claude"]["windows"])
        windows["weekly"]["remaining_percent"] = 40
        self.observe(windows=windows)
        self.assertFalse(self.c.status("claude")["admission_open"])

    def test_identity_and_provider_denial_hold(self):
        self.assertFalse(self.observe(account_id="other")["accepted"])
        self.assertFalse(self.c.status("claude")["admission_open"])
        self.assertFalse(self.observe(usage_allowed=False)["accepted"])

    def test_malformed_short_reset_is_not_ignored(self):
        windows = deepcopy(self.samples["claude"]["windows"])
        windows["five_hour"]["resets_at"] = None
        self.assertFalse(self.observe(windows=windows)["accepted"])
        self.assertFalse(self.c.status("claude")["admission_open"])

    def test_closed_pause_never_reopens_on_short_rollover(self):
        self.c.pause("claude")
        windows = deepcopy(self.samples["claude"]["windows"])
        windows["five_hour"] = dict(remaining_percent=100, resets_at=22000)
        self.observe(windows=windows)
        self.assertFalse(self.c.status("claude")["admission_open"])

    def test_weekly_deadline_still_closes_with_fresh_sample(self):
        self.now = 9950
        raw = deepcopy(self.samples["claude"])
        raw["observed_at"] = self.now
        # Initialize a fresh independent opening: old long-idle evidence cannot reopen.
        c = Controller(Path(self.tmp.name) / "weekly", clock=lambda: self.now)
        c.configure("claude", "claude:fixture", {"five_hour": 0, "weekly": 40})
        self.assertTrue(c.observe("claude", raw)["accepted"])
        c.arm("claude", "fixture")
        self.now = 10000
        self.assertEqual(c.status("claude")["gate_reason"], "reset_expired")

    def test_rollover_and_exhaustion_never_release_active_permit(self):
        permit = self.c.admit("claude", "worker", "session", "turn")
        windows = deepcopy(self.samples["claude"]["windows"])
        windows["five_hour"] = dict(remaining_percent=0, resets_at=20000)
        self.observe(windows=windows)
        self.assertFalse(self.c.status("claude")["admission_open"])
        self.assertEqual(self.c.status("claude")["active_permits"][0]["id"], permit["permit"])
        self.assertFalse(self.c.admit("codex", "worker", "session2", "turn2")["allowed"])
