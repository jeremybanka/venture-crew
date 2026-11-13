import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from .prepare_hooks import prepare
from .hook import handle
from unittest.mock import Mock

class HookPreparationTests(unittest.TestCase):
    def test_codex_shell_fallback_is_denial(self):
        result=prepare('codex','crew.strider1','/nonexistent rig','/no python','/tmp/no-state.db')
        for event,groups in result['fragment']['hooks'].items():
            command=groups[0]['hooks'][0]['command']
            proc=subprocess.run(['/bin/sh','-c',command],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0)
            body=json.loads(proc.stdout)
            self.assertTrue(body.get('decision')=='block' or body.get('continue') is False or body.get('hookSpecificOutput',{}).get('permissionDecision')=='deny')
    def test_claude_fragment_always_blocked_without_invoking_model(self):
        result=prepare('claude','crew.witch','/any','/any/python','/any/db')
        self.assertEqual(result['activation'],'blocked-claude-contract-incomplete')
        self.assertEqual(set(result['fragment']['hooks']),{'SessionStart','UserPromptSubmit','PreToolUse'})
        for event,groups in result['fragment']['hooks'].items():
            command=groups[0]['hooks'][0]['command']
            self.assertTrue(command.startswith('printf '))
            body=json.loads(subprocess.check_output(['/bin/sh','-c',command],text=True))
            self.assertTrue(body.get('decision')=='block' or body.get('continue') is False or body.get('hookSpecificOutput',{}).get('permissionDecision')=='deny')
    def test_claude_prompt_identity_maps_exactly(self):
        c=Mock(); c.admit.return_value={'allowed':True}
        payload={'hook_event_name':'UserPromptSubmit','session_id':'s','prompt_id':'p','turn_id':'wrong'}
        handle('UserPromptSubmit',payload,c,'claude','seat')
        c.admit.assert_called_once_with('claude','seat','s','p')
        payload['hook_event_name']='Stop'
        handle('Stop',payload,c,'claude','seat')
        c.release.assert_called_once_with('claude','s','p')
    def test_claude_missing_prompt_or_subagent_cannot_release(self):
        for extra in ({'turn_id':'not-a-claude-prompt'}, {'prompt_id':'p','agent_id':'child'}):
            c=Mock()
            handle('Stop',{'hook_event_name':'Stop','session_id':'s',**extra},c,'claude','seat')
            c.release.assert_not_called()
            c.admit.assert_not_called()
    def test_claude_tool_checks_exact_prompt(self):
        c=Mock();c.status.return_value={'admission_open':True,'active_permits':[{'seat':'seat','session':'s','turn':'old'}]}
        result=handle('PreToolUse',{'hook_event_name':'PreToolUse','session_id':'s','prompt_id':'new','tool_name':'Read'},c,'claude','seat')
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
    def test_claude_blockade_fails_closed(self):
        r=prepare('claude','seat','/root','/python','/db')
        for event in ('UserPromptSubmit','PreToolUse'):
            self.assertEqual(r['fragment']['hooks'][event][0]['hooks'][0]['onFailure'],'block')
    def test_relative_runtime_paths_rejected(self):
        with self.assertRaises(ValueError): prepare('codex','seat','relative','python3','state.db')
    def test_cli_release_requires_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,'-m','budget','--db',str(Path(tmp)/'db'),'release','codex','--session','s'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('--turn',result.stderr)

if __name__=='__main__':unittest.main()
