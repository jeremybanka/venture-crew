import tempfile
from pathlib import Path
import unittest
from .controller import Controller
from .hook import handle
from .prepare_hooks import prepare


class ClaudeHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=Controller(Path(self.tmp.name)/'db',clock=lambda:1000)
        self.c.configure('claude','fixture',{'weekly':40})
        self.c.observe('claude',dict(provider='claude',account_id='fixture',observed_at=1000,
          account_bound=True,freshness_proven=True,usage_allowed=True,source='fixture',
          windows={'weekly':dict(remaining_percent=69,resets_at=5000)}))
        self.c.open_factory([40,40],'fixture')
    def event(self,event,**extra):
        return handle(event,dict(hook_event_name=event,session_id='session',prompt_id='prompt',**extra),self.c,'claude','work.strider2',require_factory=True)
    def test_submit_compaction_tool_stop_share_exact_native_prompt(self):
        self.assertIn('hookSpecificOutput',self.event('UserPromptSubmit'))
        self.assertEqual(self.event('PreCompact'),{})
        self.assertEqual(self.event('PreToolUse',tool_name='Read'),{})
        self.assertEqual(self.event('Stop'),{'continue':False})
        self.assertEqual(self.event('PreCompact')['decision'],'block')
        self.assertEqual(self.c.status('claude')['active_permits'],[])
    def test_failure_releases_and_closed_compaction_blocks_correctly(self):
        self.event('UserPromptSubmit')
        self.assertEqual(self.event('StopFailure'),{})
        self.assertEqual(self.c.status('claude')['active_permits'],[])
        self.c.pause('claude')
        self.assertEqual(self.event('UserPromptSubmit')['decision'],'block')
        self.assertEqual(self.event('PreCompact')['decision'],'block')
    def test_subagent_and_missing_prompt_never_admitted(self):
        self.assertEqual(self.event('UserPromptSubmit',agent_id='child')['decision'],'block')
        payload=dict(hook_event_name='UserPromptSubmit',session_id='session',turn_id='wrong-native-field')
        self.assertEqual(handle('UserPromptSubmit',payload,self.c,'claude','work.strider2')['decision'],'block')
    def test_live_fragment_uses_blocking_events_not_sessionstart(self):
        args=('claude','work.strider2','/rig','/python','/db')
        self.assertEqual(prepare(*args)['activation'],'blocked-claude-contract-incomplete')
        hooks=prepare(*args,enable_claude=True)['fragment']['hooks']
        self.assertEqual(set(hooks),{'UserPromptSubmit','PreToolUse','Stop','StopFailure','PreCompact'})
        for event in ('UserPromptSubmit','PreToolUse','PreCompact'):
            self.assertEqual(hooks[event][0]['hooks'][0]['onFailure'],'block')
        self.assertIn('"decision":"block"',hooks['PreCompact'][0]['hooks'][0]['command'])
