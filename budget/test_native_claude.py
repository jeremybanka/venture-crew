import copy
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from .native_claude import normalize, enforce_windows, auth_metadata, safe_error, observe

class ClaudeNativeTests(unittest.TestCase):
    def setUp(self):
        self.account=dict(email='example@example.test',organization='example-org',apiProvider='firstParty')
        self.raw=dict(rate_limits_available=True,session=dict(total_cost_usd=0,total_api_duration_ms=0,model_usage={}),rate_limits=dict(
            five_hour=dict(utilization=0,resets_at=None),seven_day=dict(utilization=31,resets_at='2030-01-01T00:00:00Z'),
            model_scoped=[dict(display_name='Fable',utilization=59,resets_at='2030-01-01T00:00:00Z')],
            limits=[dict(kind='session',percent=0),dict(kind='weekly_all',percent=31,resets_at='2030-01-01T00:00:00Z'),dict(kind='weekly_scoped',percent=59,resets_at='2030-01-01T00:00:00Z',scope=dict(model=dict(display_name='Fable')))],
            extra_usage=dict(is_enabled=True,utilization=0)))
    def test_bounded_freshness_identity_scoped_and_inactive(self):
        s=normalize(self.account,self.raw,1000)
        self.assertEqual(s['observed_at'],940)
        self.assertEqual(s['windows']['model:fable']['remaining_percent'],41)
        self.assertEqual(s['windows']['seven_day']['remaining_percent'],69)
        self.assertTrue(s['windows']['five_hour']['inactive'])
        self.assertNotIn('extra_usage',s['windows'])
        self.assertNotIn('example',s['account_id'])
    def test_reject_seeded(self):
        del self.raw['rate_limits']['limits']
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_reject_unavailable(self):
        self.raw['rate_limits_available']=False
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_reject_missing_account(self):
        del self.account['organization']
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_reject_model_usage(self):
        self.raw['session']['model_usage']={'x':{}}
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_reject_nonzero_inactive(self):
        self.raw['rate_limits']['five_hour']['utilization']=1
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_reject_unprojected_scoped(self):
        self.raw['rate_limits']['model_scoped']=[]
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_reject_unknown_limit(self):
        self.raw['rate_limits']['limits'].append(dict(kind='new_limit',percent=10))
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_mismatch_and_duplicate_rejected(self):
        for field,value in [('percent',32),('resets_at','2031-01-01T00:00:00Z')]:
            raw=copy.deepcopy(self.raw);raw['rate_limits']['limits'][1][field]=value
            with self.assertRaises(ValueError):normalize(self.account,raw,1000)
        self.raw['rate_limits']['limits'].append(self.raw['rate_limits']['limits'][0])
        with self.assertRaises(ValueError):normalize(self.account,self.raw,1000)
    def test_authorized_fable_exclusion(self):
        sample=normalize(self.account,self.raw,1000)
        sample['windows']['model:fable']['remaining_percent']=0
        result=enforce_windows(sample,['model:fable'],['five_hour','seven_day'])
        self.assertTrue(result['usage_allowed'])
        self.assertEqual(result['informational_windows']['model:fable']['remaining_percent'],0)
        with self.assertRaises(ValueError):enforce_windows(sample,[],['five_hour','seven_day'])
        with self.assertRaises(ValueError):enforce_windows(sample,['seven_day'])
    def test_profile_fingerprint_ignores_cache_not_identity(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ',{'CLAUDE_CONFIG_DIR':directory}):
            root=Path(directory)
            (root/'.credentials.json').write_text('not-read')
            profile=root/'.claude.json'
            identity=dict(accountUuid='account-a',organizationUuid='org-a',emailAddress='test@example.test')
            profile.write_text(json.dumps(dict(oauthAccount=identity,counter=1)))
            before=auth_metadata()
            profile.write_text(json.dumps(dict(oauthAccount=dict(identity,profileFetchedAt=123),counter=2)))
            self.assertEqual(before,auth_metadata())
            identity['accountUuid']='account-b'
            profile.write_text(json.dumps(dict(oauthAccount=identity)))
            self.assertNotEqual(before,auth_metadata())
            profile.write_text('{}')
            with self.assertRaises(ValueError):auth_metadata()
    def test_safe_errors_never_echo_arbitrary_values(self):
        self.assertEqual(safe_error(ValueError('claude_account_metadata_changed')),'claude_account_metadata_changed')
        self.assertEqual(safe_error(ValueError('sensitive arbitrary value')),'collector_error')
    def test_reset_jitter_stable_and_conservative(self):
        boundaries=[]
        for stamp in ['2026-11-17T05:59:59.555658+00:00','2026-11-17T06:00:00.140253+00:00']:
            raw=copy.deepcopy(self.raw)
            raw['rate_limits']['seven_day']['resets_at']=stamp
            raw['rate_limits']['limits'][1]['resets_at']=stamp
            sample=normalize(self.account,raw,1000)
            window=sample['windows']['seven_day']
            boundaries.append(window['resets_at'])
            self.assertLess(window['resets_at'],sample['raw_reset_times']['seven_day'])
            self.assertEqual(set(window),{'remaining_percent','resets_at'})
        self.assertEqual(*boundaries)
        raw['rate_limits']['seven_day']['resets_at']='2026-11-24T06:00:00.1+00:00'
        raw['rate_limits']['limits'][1]['resets_at']='2026-11-24T06:00:00.1+00:00'
        self.assertNotEqual(boundaries[0],normalize(self.account,raw,1000)['windows']['seven_day']['resets_at'])
    def test_seeded_retry_preserves_initial_freshness(self):
        with patch('budget.native_claude._observe_once',side_effect=[ValueError('claude_seeded_or_incomplete_quota'),{'observed_at':999}]) as read, patch('budget.native_claude.time.time',return_value=1000), patch('budget.native_claude.time.sleep') as sleep:
            self.assertEqual(observe()['observed_at'],940)
            self.assertEqual(read.call_count,2)
            sleep.assert_called_once_with(2)
    def test_account_error_not_retried(self):
        with patch('budget.native_claude._observe_once',side_effect=ValueError('claude_account_metadata_changed')) as read:
            with self.assertRaises(ValueError):observe()
            self.assertEqual(read.call_count,1)
    def test_second_seeded_error_remains_failure(self):
        with patch('budget.native_claude._observe_once',side_effect=ValueError('claude_seeded_or_incomplete_quota')) as read, patch('budget.native_claude.time.sleep'):
            with self.assertRaises(ValueError):observe()
            self.assertEqual(read.call_count,2)
    def test_account_change_changes_binding(self):
        a=normalize(self.account,self.raw,1000)['account_id'];self.account['email']='another@example.test'
        self.assertNotEqual(a,normalize(self.account,self.raw,1000)['account_id'])

class EvidenceFileTests(unittest.TestCase):
    def test_private_atomic_normalized_record_and_symlink_refusal(self):
        from .native_claude import persist_sample
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sample.json'
            persist_sample(str(path),{'accepted':True,'sample':{'informational_windows':{'model:fable':{'remaining_percent':41}}}})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertTrue(json.loads(path.read_text())['accepted'])
            persist_sample(str(path),{'accepted':False,'error':'fixture'})
            self.assertFalse(json.loads(path.read_text())['accepted'])
            link=Path(tmp)/'link';link.symlink_to(path)
            with self.assertRaises(ValueError):persist_sample(str(link),{})
            with self.assertRaises(ValueError):persist_sample('relative.json',{})

if __name__=='__main__':unittest.main()
