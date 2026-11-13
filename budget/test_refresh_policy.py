import tempfile
import unittest
from pathlib import Path
from .controller import Controller

class RefreshPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=1000
        self.path=Path(self.tmp.name)/'budget.sqlite'
        self.c=Controller(self.path,clock=lambda:self.now)
        self.c.configure('claude','claude:fixture',{'five_hour':0,'seven_day':40},freshness=3600,reserve_windows=['seven_day'])
        self.sample=dict(provider='claude',account_id='claude:fixture',observed_at=self.now,
            account_bound=True,freshness_proven=True,usage_allowed=True,source='fixture',
            windows={'five_hour':dict(remaining_percent=90,resets_at=20000),
                     'seven_day':dict(remaining_percent=69,resets_at=80000)})
        self.c.observe('claude',self.sample);self.c.arm('claude','fixture')
    def test_failure_retains_original_timestamp_until_one_hour(self):
        for age in (300,1800,3600):
            self.now=1000+age
            self.assertTrue(self.c.refresh_failed('claude','claude:fixture','claude_seeded_or_incomplete_quota')['fallback_retained'])
            self.assertEqual(self.c.status('claude')['last']['observed_at'],1000)
        self.now+=1
        self.assertFalse(self.c.refresh_failed('claude','claude:fixture','claude_seeded_or_incomplete_quota')['fallback_retained'])
        self.assertFalse(self.c.status('claude')['admission_open'])
    def test_identity_change_stops(self):
        self.assertFalse(self.c.refresh_failed('claude','other','transient')['fallback_retained'])
        self.assertFalse(self.c.status('claude')['admission_open'])
    def test_floor_is_not_resurrected_by_failure(self):
        self.now+=1;self.sample['observed_at']=self.now
        self.sample['windows']['seven_day']['remaining_percent']=40
        self.c.observe('claude',self.sample)
        self.assertFalse(self.c.refresh_failed('claude','claude:fixture','transient')['fallback_retained'])
    def test_reset_still_stops(self):
        self.now+=1;self.sample['observed_at']=self.now
        self.sample['windows']['seven_day']['resets_at']+=604800
        self.c.observe('claude',self.sample)
        self.assertFalse(self.c.refresh_failed('claude','claude:fixture','transient')['fallback_retained'])
    def test_migration_preserves_success_but_never_arms(self):
        old=self.c.status('claude')['last']
        self.c.set_freshness('claude',3600)
        self.assertEqual(self.c.status('claude')['last'],old)
        self.assertFalse(self.c.status('claude')['admission_open'])
        with self.assertRaises(ValueError):self.c.set_freshness('claude',3601)
    def test_durable_signal_survives_controller_restart(self):
        reopened=Controller(self.path,clock=lambda:self.now)
        self.assertEqual(reopened.status('claude')['last']['observed_at'],1000)

class ObserverFailureTests(unittest.TestCase):
    def test_seeded_failure_preserves_success_file_and_uses_identity(self):
        from unittest.mock import Mock,patch
        from .__main__ import main
        client=Mock();client.observe.side_effect=ValueError('claude_seeded_or_incomplete_quota')
        client.current_account_id.return_value='claude:fixture'
        controller=Mock();controller.refresh_failed.return_value={'fallback_retained':True,'reason':'last_successful_signal'}
        with patch('sys.argv',['budget','observe-claude','--once','--sample-file','/tmp/sample']), patch('budget.__main__.Controller',return_value=controller), patch('budget.native_claude.NativeClaude',return_value=client), patch('budget.native_claude.persist_sample') as persist, patch('budget.__main__.signal.signal'), patch('builtins.print'):
            self.assertEqual(main(),1)
        controller.refresh_failed.assert_called_once_with('claude','claude:fixture','claude_seeded_or_incomplete_quota')
        controller.invalidate.assert_not_called()
        self.assertEqual(persist.call_args.args[0],'/tmp/sample.refresh.json')
        client.close.assert_called_once()
    def test_identity_failure_invalidates_not_fallback(self):
        from unittest.mock import Mock,patch
        from .__main__ import main
        client=Mock();client.observe.side_effect=ValueError('claude_account_metadata_changed')
        controller=Mock()
        with patch('sys.argv',['budget','observe-claude','--once']), patch('budget.__main__.Controller',return_value=controller), patch('budget.native_claude.NativeClaude',return_value=client), patch('budget.__main__.signal.signal'), patch('builtins.print'):
            self.assertEqual(main(),1)
        controller.refresh_failed.assert_not_called()
        controller.invalidate.assert_called_once_with('claude','claude_account_metadata_changed')
