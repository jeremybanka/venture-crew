import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from .refresh_guard import RefreshGuard


def concurrent_attempt(path, start, results):
    start.wait()
    with RefreshGuard(path,clock=lambda:1000).locked() as state:
        results.put(RefreshGuard(path,clock=lambda:1000).reserve(state,300))


class RefreshGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'refresh.json'
        self.now=1000
        self.guard=RefreshGuard(self.path,clock=lambda:self.now)

    def test_restart_after_success_reuses_original_evidence(self):
        sample={'observed_at':940,'windows':{}}
        with self.guard.locked() as state:
            self.assertTrue(self.guard.reserve(state,300))
            self.guard.complete(state,sample,'identity',300)
        self.now=1100
        other=RefreshGuard(self.path,clock=lambda:self.now)
        with other.locked() as state:
            self.assertFalse(other.reserve(state,300))
            self.assertEqual(other.cached(state,'identity'),sample)
            self.assertEqual(state['next_attempt_at'],1300)
            self.assertIsNone(other.cached(state,'changed'))
        self.now=4541
        with other.locked() as state:
            self.assertIsNone(other.cached(state,'identity'))

    def test_crash_reservation_and_failure_backoff_survive_restart(self):
        for at,expected in ((1000,1300),(1300,1900),(1900,3100),(3100,4900)):
            self.now=at
            other=RefreshGuard(self.path,clock=lambda:self.now)
            with other.locked() as state:
                self.assertTrue(other.reserve(state,300))
                self.assertEqual(state['next_attempt_at'],expected)
            # Simulate death before any result can be written.
            with other.locked() as state:
                self.assertFalse(other.reserve(state,300))

    def test_failure_does_not_renew_or_delete_cache(self):
        with self.guard.locked() as state:
            self.guard.reserve(state,300)
            self.guard.complete(state,{'observed_at':940},'id',300)
        self.now=1300
        with self.guard.locked() as state:
            self.guard.reserve(state,300)
            self.now=1345
            self.guard.failed(state,300)
            self.assertEqual(state['next_attempt_at'],1645)
            self.assertEqual(state['sample']['observed_at'],940)

    def test_clock_rollback_cannot_make_request_due(self):
        with self.guard.locked() as state:
            self.guard.reserve(state,300)
        self.now=900
        with self.guard.locked() as state:
            self.assertFalse(self.guard.reserve(state,300))
            self.assertEqual(self.guard.wait_seconds(state),400)

    def test_concurrent_processes_admit_only_one_request(self):
        ctx=multiprocessing.get_context('fork')
        start=ctx.Event();results=ctx.Queue()
        workers=[ctx.Process(target=concurrent_attempt,args=(str(self.path),start,results)) for _ in range(8)]
        for worker in workers:worker.start()
        start.set()
        outcomes=[results.get(timeout=10) for _ in workers]
        for worker in workers:
            worker.join(10);self.assertEqual(worker.exitcode,0)
        self.assertEqual(sum(outcomes),1)

    def test_corrupt_state_fails_closed(self):
        self.path.write_text('bad')
        with self.assertRaises(ValueError):
            with self.guard.locked(): pass
        for value in (-1,float('nan'),'tomorrow'):
            self.path.write_text(json.dumps(dict(version=1,next_attempt_at=value,last_attempt_at=1,failures=1)))
            with self.assertRaises(ValueError):
                with self.guard.locked():pass


class ObserverCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'refresh.json'
        self.now=1000
        self.client=Mock()
        self.raw={'observed_at':940,'windows':{},'marker':'original'}
        self.client.observe.return_value=self.raw
        self.controller=Mock()
        self.controller.status.return_value={'floors':{},'last':self.raw}
        self.controller.observe.return_value={'accepted':True}
        self.patches=[
            patch('budget.refresh_guard.RefreshGuard',side_effect=lambda:RefreshGuard(self.path,clock=lambda:self.now)),
            patch('budget.__main__.Controller',return_value=self.controller),
            patch('budget.native_claude.NativeClaude',return_value=self.client),
            patch('budget.native_claude.auth_metadata',return_value=('fixture','identity')),
            patch('budget.native_claude.enforce_windows',side_effect=lambda sample,*_:sample),
            patch('budget.__main__.signal.signal'),
            patch('builtins.print')]
        self.started=[p.start() for p in self.patches]
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def run_once(self,*extra):
        from .__main__ import main
        with patch('sys.argv',['budget','observe-claude','--once',*extra]):
            return main()

    def test_restarts_and_print_only_do_not_issue_new_requests(self):
        self.assertEqual(self.run_once(),0)
        self.now=1100
        for _ in range(4):
            self.assertEqual(self.run_once(),0)
            self.assertEqual(self.run_once('--print-only'),0)
        self.assertEqual(self.client.observe.call_count,1)
        self.assertEqual(self.started[2].call_count,1)
        self.assertEqual(self.controller.observe.call_count,1)
        self.assertEqual(self.raw['observed_at'],940)

    def test_failures_and_once_restarts_preserve_backoff(self):
        self.client.observe.side_effect=ValueError('claude_seeded_or_incomplete_quota')
        self.controller.refresh_failed.return_value={'fallback_retained':False}
        self.assertEqual(self.run_once(),1)
        self.now=1100
        self.assertEqual(self.run_once(),1)
        self.assertEqual(self.client.observe.call_count,1)
        self.now=1300
        self.assertEqual(self.run_once(),1)
        self.now=1500
        self.assertEqual(self.run_once(),1)
        self.assertEqual(self.client.observe.call_count,2)
        with RefreshGuard(self.path,clock=lambda:self.now).locked() as state:
            self.assertEqual(state['next_attempt_at'],1900)

    def test_cache_rejected_on_identity_change_without_resetting_cooldown(self):
        self.run_once()
        self.now=1100
        with patch('budget.native_claude.auth_metadata',return_value=('other','identity')):
            self.assertEqual(self.run_once('--print-only'),1)
        self.assertEqual(self.client.observe.call_count,1)

    def test_cache_identity_change_invalidates_admission_not_deadline(self):
        self.run_once()
        self.now=1100
        with patch('budget.native_claude.auth_metadata',return_value=('changed','identity')):
            self.assertEqual(self.run_once(),1)
        self.controller.invalidate.assert_called_with('claude','claude_account_metadata_changed')
        with RefreshGuard(self.path,clock=lambda:self.now).locked() as state:
            self.assertEqual(state['next_attempt_at'],1300)
            self.assertEqual(state['sample']['observed_at'],940)

    def test_cache_identity_read_failure_invalidates(self):
        self.run_once()
        self.now=1100
        with patch('budget.native_claude.auth_metadata',side_effect=ValueError('claude_account_identity_missing')):
            self.assertEqual(self.run_once(),1)
        self.controller.invalidate.assert_called_with('claude','claude_account_metadata_changed')
        self.assertEqual(self.client.observe.call_count,1)

    def test_restart_wait_checks_identity_without_native_client(self):
        self.run_once()
        self.now=1100
        self.controller.invalidate.reset_mock()
        event=Mock()
        event.is_set.side_effect=[False,False,True]
        event.wait.side_effect=[False,True]
        from .__main__ import main
        with patch('sys.argv',['budget','observe-claude']), patch('budget.__main__.threading.Event',return_value=event), patch('budget.native_claude.auth_metadata',side_effect=[('fixture','identity'),('changed','identity')]):
            self.assertEqual(main(),0)
        self.controller.invalidate.assert_called_with('claude','claude_account_metadata_changed')
        self.assertEqual(self.client.observe.call_count,1)

    def test_first_refresh_wait_uses_new_identity_baseline(self):
        event=Mock()
        event.is_set.side_effect=[False,False,True]
        event.wait.side_effect=[False,True]
        from .__main__ import main
        with patch('sys.argv',['budget','observe-claude']), patch('budget.__main__.threading.Event',return_value=event), patch('budget.native_claude.auth_metadata',side_effect=[('fixture','identity'),('fixture','identity'),('changed','identity')]):
            self.assertEqual(main(),0)
        self.controller.invalidate.assert_called_with('claude','claude_account_metadata_changed')
        self.assertEqual(self.client.observe.call_count,1)

    def test_cache_reader_projection_error_does_not_invalidate_collector(self):
        self.run_once()
        self.now=1100
        self.controller.invalidate.reset_mock()
        with patch('budget.native_claude.enforce_windows',side_effect=ValueError('configured_window_set_changed')):
            self.assertEqual(self.run_once(),1)
        self.controller.invalidate.assert_not_called()
        self.assertEqual(self.client.observe.call_count,1)
