"""Provider-local factory opening is a budget primitive, never harness readiness."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from .controller import Controller

class OpeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'db'; self.now=1000
        self.c=Controller(self.path,clock=lambda:self.now)
        for p in ('codex','claude'):
            self.c.configure(p,p+':account',{'short':10,'long':20},max_active=2)
            self.c.observe(p,self.sample(p))
    def sample(self,p,remaining=90,reset=3000):
        return dict(provider=p,account_id=p+':account',account_bound=True,freshness_proven=True,observed_at=self.now,usage_allowed=True,source='test',windows={k:dict(remaining_percent=remaining,resets_at=reset) for k in ('short','long')})
    def opening(self):return self.c.open_factory((50,40),'owner opening')
    def assertClosed(self):
        for p in ('codex','claude'): self.assertFalse(self.c.status(p)['admission_open'])
    def test_pair_and_audit_and_configuration_preserved(self):
        result=self.opening()
        for p,floor in [('codex',50),('claude',40)]:
            state=self.c.status(p)
            self.assertTrue(state['admission_open']);self.assertEqual(state['opening_id'],result['opening_id'])
            self.assertEqual(state['floors'],{'short':floor,'long':floor});self.assertEqual(state['max_active'],2)
            self.assertEqual(state['account'],p+':account')
        with sqlite3.connect(self.path) as db:
            details=[json.loads(row[0]) for row in db.execute("SELECT detail FROM audit WHERE event='open_factory'")]
        self.assertEqual(len(details),2);self.assertTrue(all(x['opening_id']==result['opening_id'] for x in details))
    def test_unavailable_provider_does_not_block_other(self):
        self.c.invalidate('claude','unknown')
        result=self.opening()
        self.assertTrue(result['any_armed']);self.assertFalse(result['all_armed'])
        self.assertEqual(result['providers']['claude']['reason'],'unknown')
        self.assertTrue(self.c.status('codex')['admission_open'])
        self.assertFalse(self.c.status('claude')['admission_open'])
    def test_unconfigured_provider_is_not_faked(self):
        other=Controller(Path(self.tmp.name)/'single',clock=lambda:self.now)
        other.configure('codex','codex:account',{'short':10})
        other.observe('codex',self.sample('codex'))
        result=other.open_factory((50,40),'one provider available')
        self.assertTrue(result['providers']['codex']['armed'])
        self.assertFalse(result['providers']['claude']['armed'])
        self.assertEqual(result['providers']['claude']['reason'],'unconfigured')
        self.assertIsNone(other.status('claude')['account']);self.assertEqual(other.status('claude')['floors'],{})
    def test_equal_floor_denies_only_affected_provider(self):
        result=self.c.open_factory((90,40),'test')
        self.assertFalse(result['providers']['codex']['armed']);self.assertTrue(result['providers']['claude']['armed'])
        result=self.c.open_factory((90,90),'test')
        self.assertFalse(result['any_armed']);self.assertClosed()
    def test_bad_input_rejected(self):
        for pair in ((101,40),(True,40),('50',40),(50,),[float('nan'),40]):
            with self.assertRaises(ValueError):self.c.open_factory(pair,'test')
        with self.assertRaises(ValueError):self.c.open_factory((50,40),' ')
        self.assertClosed()
    def test_active_permit_blocks_reopening_without_changes(self):
        self.opening();self.c.admit('codex','seat','session','turn')
        before=self.c.status('codex')
        with self.assertRaises(ValueError):self.c.open_factory((60,50),'another')
        self.assertEqual(before,self.c.status('codex'))
    def test_floor_latches_only_affected_provider(self):
        self.opening();self.now+=1;self.c.observe('codex',self.sample('codex',50))
        self.assertFalse(self.c.status('codex')['admission_open']);self.assertTrue(self.c.status('claude')['admission_open'])
        self.now+=1;self.c.observe('codex',self.sample('codex',90))
        self.assertFalse(self.c.status('codex')['admission_open']);self.assertTrue(self.c.status('claude')['admission_open'])
        with self.assertRaises(ValueError):self.c.arm('codex','individual bypass')
        self.opening();self.assertTrue(self.c.status('codex')['admission_open'])
    def test_reset_invalid_pause_close_only_affected_provider(self):
        for change in ('reset','invalid','pause','invalidate'):
            self.opening();self.now+=1
            if change=='reset':self.c.observe('codex',self.sample('codex',reset=4000))
            elif change=='invalid':self.c.observe('codex',{'bad':'data'})
            elif change=='pause':self.c.pause('codex')
            else:self.c.invalidate('codex','collector_failed')
            self.assertFalse(self.c.status('codex')['admission_open']);self.assertTrue(self.c.status('claude')['admission_open'])
            self.now+=1;self.c.observe('codex',self.sample('codex'))
    def test_switch_waits_for_exact_release(self):
        self.opening();self.assertTrue(self.c.admit('codex','seat','s','t')['allowed'])
        self.c.pause('codex')
        self.assertFalse(self.c.admit('claude','seat','new-session','new-turn')['allowed'])
        self.c.release('codex','s','wrong')
        self.assertFalse(self.c.admit('claude','seat','new-session','new-turn')['allowed'])
        self.c.release('codex','s','t')
        self.assertTrue(self.c.admit('claude','seat','new-session','new-turn')['allowed'])
    def test_one_stale_provider_does_not_close_fresh_peer(self):
        self.opening();self.now+=200;self.c.observe('claude',self.sample('claude'))
        self.now+=101
        self.assertFalse(self.c.admit('codex','seat','s','t')['allowed'])
        self.assertTrue(self.c.status('claude')['admission_open'])
    def test_staleness_latches_before_new_sample_can_revive(self):
        self.opening();self.now+=301;self.assertClosed()
        for p in ('codex','claude'):self.c.observe(p,self.sample(p))
        self.assertClosed();self.opening()
    def test_admission_latches_staleness_persistently(self):
        self.opening();self.now+=301
        self.assertFalse(self.c.admit('claude','seat','session','turn')['allowed'])
        restart=Controller(self.path,clock=lambda:self.now)
        self.assertFalse(restart.status('claude')['armed'])
    def test_status_readonly_does_not_write(self):
        self.opening();self.now+=301
        ro=Controller(self.path,clock=lambda:self.now,readonly=True)
        before=self.path.read_bytes();self.assertFalse(ro.status('claude')['admission_open']);self.assertEqual(before,self.path.read_bytes())
    def test_cli_arm_denied_before_initialization(self):
        missing=Path(self.tmp.name)/'not-created'
        for path in (missing,self.path):
            before=path.read_bytes() if path.exists() else None
            r=subprocess.run([sys.executable,'-m','budget','--db',str(path),'arm','codex','--reason','legacy'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertIn('use_open_factory',r.stderr)
            self.assertEqual(path.read_bytes() if path.exists() else None,before)
    def test_cli_admit_denies_unpaired_legacy_state(self):
        self.c.arm('codex','legacy fixture')
        r=subprocess.run([sys.executable,'-m','budget','--db',str(self.path),'admit','codex','--seat','seat','--session','session','--turn','turn'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('paired_factory_opening_required',r.stderr)
        self.assertEqual(self.c.status('codex')['active_permits'],[])
    def test_production_hook_rejects_unpaired_legacy_state(self):
        from .hook import handle
        self.c.arm('codex','legacy fixture')
        for event in ('UserPromptSubmit','PreToolUse'):
            payload={'hook_event_name':event,'session_id':'session','turn_id':'turn','tool_name':'Read'}
            result=handle(event,payload,self.c,'codex','seat',require_factory=True)
            self.assertIn('paired_factory_opening_required',json.dumps(result))
        self.assertEqual(self.c.status('codex')['active_permits'],[])
    def test_production_hook_accepts_paired_opening(self):
        from .hook import handle
        self.opening()
        payload={'hook_event_name':'UserPromptSubmit','session_id':'session','turn_id':'turn'}
        result=handle('UserPromptSubmit',payload,self.c,'codex','seat',require_factory=True)
        self.assertIn('additionalContext',result['hookSpecificOutput'])
    def test_cli_rejects_malformed_pair(self):
        r=subprocess.run([sys.executable,'-m','budget','--db',str(self.path),'open-factory','--floors','50/40/30','--reason','test'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('floors_require_codex_claude_pair',r.stderr)

if __name__=='__main__': unittest.main()
