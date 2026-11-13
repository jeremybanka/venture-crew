import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from .controller import Controller
from .adapters import claude_statusline,codex
from .hook import handle

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.db'; self.now=1000
        self.c=Controller(self.path,clock=lambda:self.now)
    def sample(self,p='codex',**kw):
        value=dict(provider=p,account_id=p+':hash',account_bound=True,freshness_proven=True,observed_at=self.now,usage_allowed=True,source='fixture',windows={'five_hour':{'remaining_percent':90,'resets_at':2000},'weekly':{'remaining_percent':80,'resets_at':8000}})
        value.update(kw); return value
    def ready(self,p='codex',max_active=1):
        self.c.configure(p,p+':hash',{'five_hour':10,'weekly':20},max_active=max_active)
        self.assertTrue(self.c.observe(p,self.sample(p))['accepted']); self.c.arm(p,'test policy')
    def test_default_closed(self):
        for p in ('codex','claude'): self.assertFalse(self.c.status(p)['admission_open'])
    def test_providers_independent(self):
        self.ready(); self.assertTrue(self.c.status('codex')['admission_open']); self.assertFalse(self.c.status('claude')['admission_open'])
        self.ready('claude'); self.c.pause('claude'); self.assertTrue(self.c.status('codex')['admission_open'])
    def test_configure_disarms(self):
        self.ready(); self.c.configure('codex','codex:hash',{'five_hour':10}); self.assertFalse(self.c.status('codex')['admission_open'])
    def test_floor(self):
        self.ready(); self.now+=1; v=self.sample(); v['windows']['weekly']['remaining_percent']=20
        self.c.observe('codex',v); self.assertEqual(self.c.status('codex')['gate_reason'],'usage_floor:weekly')
    def test_missing_window(self):
        self.ready(); self.now+=1; v=self.sample(); del v['windows']['weekly']; self.assertFalse(self.c.observe('codex',v)['accepted']); self.assertFalse(self.c.status('codex')['admission_open'])
    def test_stale_future_and_expired(self):
        self.ready(); self.now+=301; self.assertEqual(self.c.status('codex')['gate_reason'],'stale_observation')
        self.assertFalse(self.c.observe('codex',self.sample(observed_at=self.now+31))['accepted'])
        v=self.sample(); v['windows']['weekly']['resets_at']=self.now; self.assertFalse(self.c.observe('codex',v)['accepted'])
    def test_identity_unbound_and_wrong_provider(self):
        for changes in ({'account_id':'other'},{'account_bound':False},{'freshness_proven':False},{'provider':'claude'},{'usage_allowed':False}):
            self.ready(); self.now+=1; self.assertFalse(self.c.observe('codex',self.sample(**changes))['accepted']); self.assertFalse(self.c.status('codex')['admission_open'])
    def test_reset_disarms_only_provider(self):
        self.ready(); self.ready('claude'); self.now+=1; v=self.sample(); v['windows']['weekly']['resets_at']+=10
        self.c.observe('codex',v); self.assertFalse(self.c.status('codex')['admission_open']); self.assertTrue(self.c.status('claude')['admission_open'])
        self.c.arm('codex','reviewed reset'); self.assertTrue(self.c.status('codex')['admission_open'])
    def test_refill_disarms(self):
        self.ready(); self.now+=1; v=self.sample(); v['windows']['weekly']['remaining_percent']=81
        self.c.observe('codex',v); self.assertFalse(self.c.status('codex')['admission_open'])
    def test_replay_does_not_refresh(self):
        self.ready(); self.now+=200; self.assertEqual(self.c.observe('codex',self.sample(observed_at=1000))['reason'],'not_newer'); self.now+=101; self.assertFalse(self.c.status('codex')['admission_open'])
    def test_concurrent_admission(self):
        self.ready()
        def attempt(i): return Controller(self.path,clock=lambda:self.now).admit('codex','s'+str(i),'session'+str(i),'turn')['allowed']
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(attempt,range(8)))
        self.assertEqual(sum(results),1)
    def test_restart_and_interrupted_permit(self):
        self.ready(); self.assertTrue(self.c.admit('codex','worker','s','t')['allowed'])
        restarted=Controller(self.path,clock=lambda:self.now)
        self.assertFalse(restarted.admit('codex','worker2','s2','t2')['allowed'])
        self.assertEqual(restarted.release('codex','s','wrong'),0)
        self.assertEqual(restarted.release('codex','s','t'),1)
        self.assertTrue(restarted.admit('codex','worker2','s2','t2')['allowed'])
    def test_normal_release_requires_exact_turn(self):
        self.ready(); self.c.admit('codex','worker','s','t')
        with self.assertRaises(TypeError): self.c.release('codex','s')
        with self.assertRaises(ValueError): self.c.release('codex','s',None)
        self.assertEqual(len(self.c.status('codex')['active_permits']),1)
    def test_explicit_reconcile_session(self):
        self.ready(); self.c.admit('codex','worker','s','t')
        with self.assertRaises(ValueError): self.c.reconcile_session('codex','s','verified ended')
        with self.assertRaises(ValueError): self.c.reconcile_session('codex','s','',confirmed_stopped=True)
        self.assertEqual(self.c.reconcile_session('claude','s','verified ended',confirmed_stopped=True),0)
        self.assertEqual(len(self.c.status('codex')['active_permits']),1)
        self.assertEqual(self.c.reconcile_session('codex','s','verified ended',confirmed_stopped=True),1)
    def test_idempotence_and_closed_turn(self):
        self.ready(); a=self.c.admit('codex','worker','s','t'); b=self.c.admit('codex','worker','s','t'); self.assertEqual(a['permit'],b['permit'])
        self.c.release('codex','s','t'); self.assertFalse(self.c.admit('codex','worker','s','t')['allowed'])
    def test_cross_provider_seat_cannot_overlap(self):
        self.ready(); self.ready('claude'); self.c.admit('codex','worker','s','t'); self.assertFalse(self.c.admit('claude','worker','s2','t2')['allowed'])
    def test_invalid_numbers(self):
        for value in (True,float('nan'),float('inf'),-1,101):
            self.ready(); self.now+=1; v=self.sample(); v['windows']['weekly']['remaining_percent']=value; self.assertFalse(self.c.observe('codex',v)['accepted'])
    def test_claude_statusline_is_not_admission_evidence(self):
        value=claude_statusline({'rate_limits':{'five_hour':{'used_percentage':12,'resets_at':2000},'seven_day':{'used_percentage':20,'resets_at':8000}}},received_at=self.now)
        self.assertFalse(value['account_bound']); self.assertIsNone(value['observed_at']); self.ready('claude'); self.assertFalse(self.c.observe('claude',value)['accepted'])
    def test_old_success_cannot_overwrite_newer_rejection(self):
        self.ready(); self.now=1100
        self.c.observe('codex',self.sample(usage_allowed=False))
        self.assertEqual(self.c.observe('codex',self.sample(observed_at=1050))['reason'],'not_newer')
        self.assertFalse(self.c.status('codex')['admission_open'])
    def test_native_codex_adapter(self):
        class Client:
            def request(s,method,params):
                if method=='account/read': return {'account':{'type':'chatgpt'}}
                return {'accountId':'private-id','ordinaryUsageAllowed':True,'rateLimits':{'limitId':'codex','primary':{'windowDurationMins':300,'usedPercent':10,'resetsAt':2000},'secondary':{'windowDurationMins':10080,'usedPercent':20,'resetsAt':8000}}}
        v=codex(Client()); self.assertNotIn('private-id',json.dumps(v)); self.assertTrue(v['account_bound']); self.assertEqual(v['windows']['codex:10080']['remaining_percent'],80)
    def codex_fixture(self, response):
        class Client:
            def request(self,method,params):
                if method=='account/read': return {'account':{'type':'chatgpt'}}
                return response
        return codex(Client())
    def test_codex_malformed_extra_bucket_rejected(self):
        good={'primary':{'windowDurationMins':300,'usedPercent':10,'resetsAt':2000}}
        for bad in (None, [], 'unknown', 5, False, {}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.codex_fixture({'accountId':'x','ordinaryUsageAllowed':True,'rateLimitsByLimitId':{'codex':good,'extra':bad}})
    def test_codex_malformed_window_rejected(self):
        good={'windowDurationMins':300,'usedPercent':10,'resetsAt':2000}
        for bad in ([], 'unknown', 5, False, {}):
            for key in ('primary','secondary'):
                bucket={'primary':good,'secondary':dict(good,windowDurationMins=10080)}; bucket[key]=bad
                with self.subTest(bad=bad,key=key), self.assertRaises(ValueError):
                    self.codex_fixture({'accountId':'x','ordinaryUsageAllowed':True,'rateLimitsByLimitId':{'codex':bucket}})
    def test_codex_absent_optional_window_is_not_malformed(self):
        good={'windowDurationMins':300,'usedPercent':10,'resetsAt':2000}
        for bucket in ({'primary':good},{'primary':good,'secondary':None}):
            value=self.codex_fixture({'accountId':'x','ordinaryUsageAllowed':True,'rateLimitsByLimitId':{'codex':bucket}})
            self.assertEqual(set(value['windows']),{'codex:300'})
            # Required weekly configuration would still reject this observation.
    def test_codex_malformed_map_does_not_fallback_to_valid_single(self):
        good={'limitId':'codex','primary':{'windowDurationMins':300,'usedPercent':10,'resetsAt':2000}}
        for bad in ([], 'unknown', 5, False):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.codex_fixture({'accountId':'x','ordinaryUsageAllowed':True,'rateLimitsByLimitId':bad,'rateLimits':good})
    def test_hook_requires_native_turn_and_admission(self):
        self.ready(); v={'hook_event_name':'UserPromptSubmit','session_id':'s'}
        self.assertEqual(handle('UserPromptSubmit',v,self.c,'codex','worker')['decision'],'block')
        v['turn_id']='t'; self.assertIn('hookSpecificOutput',handle('UserPromptSubmit',v,self.c,'codex','worker'))
        self.assertFalse(handle('Stop',dict(v,hook_event_name='Stop'),self.c,'codex','worker')['continue'])
    def test_hook_blocks_children_and_unpermitted_tools(self):
        self.ready(); v={'hook_event_name':'PreToolUse','session_id':'s','tool_name':'Agent'}
        self.assertEqual(handle('PreToolUse',v,self.c,'codex','worker')['hookSpecificOutput']['permissionDecision'],'deny')
        v['tool_name']='Bash'; self.assertEqual(handle('PreToolUse',v,self.c,'codex','worker')['hookSpecificOutput']['permissionDecision'],'deny')

if __name__=='__main__': unittest.main()
