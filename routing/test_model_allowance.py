import copy
import time
import unittest
from routing.routing import plan


class ModelAllowanceTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.sample = dict(provider='claude', account_id='fixture', observed_at=self.now,
                           account_bound=True, freshness_proven=True, usage_allowed=True,
                           source='claude-native-get-usage', windows={'weekly': {'remaining_percent':69,'resets_at':self.now+8000}},
                           informational_windows={'model:fable': {'remaining_percent':41,'resets_at':self.now+8000}})
        self.status = {p: dict(admission_open=True,active_permits=[]) for p in ('claude','codex')}
        self.status['claude'].update(valid=True, account='fixture', freshness=300,
            last={k:copy.deepcopy(self.sample[k]) for k in ('account_id','observed_at','source','windows')})
        self.catalog = {key:dict(verified=True,model=model,provider=p,runtime=r) for key,model,p,r in
            [('Fable','claude-fable-5-2','claude','claude-code'),('Opus','claude-opus-5-5','claude','claude-code'),('Sol','gpt-6.1-sol','codex','codex')]}

    def choose(self, choices=('Fable','Sol')):
        return plan('seat', {'seat':list(choices)}, self.catalog,self.status,
                    {'codex':True,'claude-code':True}, model_snapshot={"accepted":True,"sample":self.sample},now=self.now)

    def test_fable_above_zero_allowed_below_reserve(self):
        self.sample['informational_windows']['model:fable']['remaining_percent']=1
        self.assertEqual(self.choose()['selected']['preference'],'Fable')

    def test_zero_routes_sol_not_provider_wide_opus_block(self):
        self.sample['informational_windows']['model:fable']['remaining_percent']=0
        self.assertEqual(self.choose()['selected']['preference'],'Sol')
        self.assertEqual(self.choose(('Opus','Sol'))['selected']['preference'],'Opus')

    def test_unknown_stale_mismatched_fail_closed(self):
        original=copy.deepcopy(self.sample)
        for key,value in [('account_id','other'),('observed_at',self.now-1),('source','other'),
                          ('windows',{}),('account_bound',False),('freshness_proven',False),
                          ('usage_allowed',False),('informational_windows',{})]:
            self.sample=copy.deepcopy(original); self.sample[key]=value
            self.assertEqual(self.choose()['selected']['preference'],'Sol',key)
        self.sample=original; self.now+=301
        self.assertEqual(self.choose()['selected']['preference'],'Sol')
        self.sample=None
        self.assertEqual(self.choose()['selected']['preference'],'Sol')

    def test_bad_window_values_fail_closed(self):
        original=copy.deepcopy(self.sample)
        for update in ({'remaining_percent':True},{'remaining_percent':float('nan')},
                       {'resets_at':None},{'resets_at':self.now-1},{'inactive':True},
                       {'inactive':'true'}):
            self.sample=copy.deepcopy(original)
            self.sample['informational_windows']['model:fable'].update(update)
            self.assertEqual(self.choose()['selected']['preference'],'Sol')

    def test_provider_gate_and_same_seat_permit_preserved(self):
        self.status['claude']['admission_open']=False
        self.assertEqual(self.choose()['selected']['preference'],'Sol')
        self.status['claude']['active_permits']=[{'seat':'seat'}]
        self.assertEqual(self.choose()['status'],'wait')

    def test_snapshot_cannot_revalidate_rejected_provider_state(self):
        self.status['claude']['valid']=False
        self.assertEqual(self.choose()['selected']['preference'],'Sol')


class FableFreshnessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ModelAllowanceTests()
        self.fixture.setUp()
        self.fixture.status['claude']['freshness'] = 3600

    def test_supported_claude_policy_selects_fresh_fable(self):
        for seconds in (300, 900, 901, 3600):
            with self.subTest(seconds=seconds):
                self.fixture.status['claude']['freshness'] = seconds
                self.assertEqual(self.fixture.choose()['selected']['preference'], 'Fable')

    def test_one_hour_policy_keeps_original_observation_age(self):
        observed = self.fixture.sample['observed_at']
        for age, expected in ((901, 'Fable'), (3599, 'Fable'),
                              (3600, 'Fable'), (3600.001, 'Sol')):
            with self.subTest(age=age):
                self.fixture.now = observed + age
                result = self.fixture.choose()
                self.assertEqual(result['selected']['preference'], expected)
                if expected == 'Sol':
                    self.assertEqual(result['skipped'][0]['reason'],
                                     'model_allowance_unknown_or_stale')

    def test_invalid_policy_remains_fail_closed(self):
        for seconds in (0, 3600.001, 3601, True, None, '3600',
                        float('nan'), float('inf')):
            with self.subTest(seconds=seconds):
                self.fixture.status['claude']['freshness'] = seconds
                result = self.fixture.choose()
                self.assertEqual(result['selected']['preference'], 'Sol')
                self.assertEqual(result['skipped'][0]['reason'],
                                 'model_allowance_unknown_or_stale')

    def test_future_sample_still_obeys_existing_clock_tolerance(self):
        for ahead, expected in ((30, 'Fable'), (31, 'Sol')):
            with self.subTest(ahead=ahead):
                observed = self.fixture.now + ahead
                self.fixture.sample['observed_at'] = observed
                self.fixture.status['claude']['last']['observed_at'] = observed
                self.assertEqual(self.fixture.choose()['selected']['preference'], expected)

    def test_one_hour_policy_still_requires_matching_identity_and_evidence(self):
        sample = copy.deepcopy(self.fixture.sample)
        for key, value in (('account_id', 'other'), ('observed_at', self.fixture.now - 1),
                           ('source', 'other'), ('windows', {}), ('account_bound', False),
                           ('freshness_proven', False), ('usage_allowed', False)):
            with self.subTest(key=key):
                self.fixture.sample = copy.deepcopy(sample)
                self.fixture.sample[key] = value
                self.assertEqual(self.fixture.choose()['selected']['preference'], 'Sol')

    def test_one_hour_policy_still_requires_accepted_collector_record(self):
        f = self.fixture
        for record in (None, f.sample, {'accepted': False, 'sample': f.sample},
                       {'accepted': 1, 'sample': f.sample}):
            with self.subTest(record=record):
                result = plan('seat', {'seat': ['Fable', 'Sol']}, f.catalog, f.status,
                              {'codex': True, 'claude-code': True},
                              model_snapshot=record, now=f.now)
                self.assertEqual(result['selected']['preference'], 'Sol')

    def test_one_hour_policy_does_not_restore_zero_model_allowance(self):
        self.fixture.sample['informational_windows']['model:fable']['remaining_percent'] = 0
        result = self.fixture.choose()
        self.assertEqual(result['selected']['preference'], 'Sol')
        self.assertEqual(result['skipped'][0]['reason'], 'model_allowance_exhausted')
        self.assertEqual(self.fixture.choose(('Opus', 'Sol'))['selected']['preference'], 'Opus')

    def test_one_hour_policy_preserves_provider_and_same_seat_gates(self):
        self.fixture.status['claude']['admission_open'] = False
        self.assertEqual(self.fixture.choose()['selected']['preference'], 'Sol')
        self.fixture.status['claude']['admission_open'] = True
        self.fixture.status['codex']['active_permits'] = [{'seat': 'seat'}]
        self.assertEqual(self.fixture.choose()['status'], 'wait')


class PersistedModelSnapshotTests(unittest.TestCase):
    def test_actual_collector_record_through_cli(self):
        self.check_collector_record_through_cli(300)

    def test_one_hour_controller_policy_through_cli(self):
        self.check_collector_record_through_cli(3600)

    def check_collector_record_through_cli(self, freshness):
        import json
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        from budget.controller import Controller
        from budget.native_claude import persist_sample
        fixture = ModelAllowanceTests(); fixture.setUp()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root/'budget.sqlite3'
            c = Controller(db)
            c.configure('claude', 'fixture', {'weekly':40}, freshness=freshness)
            self.assertTrue(c.observe('claude', fixture.sample)['accepted'])
            c.open_factory([40,40], 'fixture')
            self.assertEqual(c.status('claude')['account'], 'fixture')
            files = {'preferences':{'preferences':{'seat':['Fable']}},
                     'catalog':{'models':fixture.catalog},
                     'readiness':{'claude-code':True},
                     'session-evidence':{'no_existing_session':True}}
            command = [sys.executable,'-m','routing','--seat','seat','--db',str(db)]
            for key,value in files.items():
                path=root/(key+'.json'); path.write_text(json.dumps(value))
                command += ['--'+key,str(path)]
            snapshot = root/'claude-latest.json'
            command += ['--model-snapshot',str(snapshot)]
            for accepted, expected in ((True,0),(False,2),(1,2)):
                persist_sample(snapshot, {'accepted':accepted,'sample':fixture.sample})
                result=subprocess.run(command,capture_output=True,text=True)
                self.assertEqual(result.returncode,expected,result.stderr+result.stdout)
            persist_sample(snapshot, fixture.sample)
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
