import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from .claude_plugin import build, write_plugin


class ClaudePluginTests(unittest.TestCase):
    def args(self):
        return dict(root='/rig', python='/usr/bin/python3', db='/state/budget.sqlite3',
                    seat='bridge.captain', session='bridge-captain@crew')

    def test_plugin_is_launch_local_without_permissions(self):
        files = build(**self.args())
        self.assertEqual(set(files), {'.claude-plugin/plugin.json', 'hooks/claude.json'})
        manifest = files['.claude-plugin/plugin.json']
        self.assertEqual(manifest['hooks'], './hooks/claude.json')
        hooks = files['hooks/claude.json']
        self.assertEqual(set(hooks), {'hooks'})
        self.assertEqual(set(hooks['hooks']), {'UserPromptSubmit', 'PreToolUse', 'Stop', 'StopFailure', 'PreCompact'})
        self.assertNotIn('permissions', json.dumps(files))

    def test_unrelated_and_absent_session_are_inert(self):
        hooks = build(**self.args())['hooks/claude.json']['hooks']
        for session in ('', 'bridge-captain@other', 'work-strider1@crew'):
            for groups in hooks.values():
                command = groups[0]['hooks'][0]['command']
                env = dict(os.environ, OPENRIG_SESSION_NAME=session)
                result = subprocess.run(['sh', '-c', command], input='{}', text=True,
                                        capture_output=True, env=env, check=True)
                self.assertEqual(json.loads(result.stdout), {})

    def test_matching_session_fails_closed_when_runtime_missing(self):
        hooks = build(**self.args())['hooks/claude.json']['hooks']
        for event in ('UserPromptSubmit', 'PreToolUse', 'PreCompact'):
            command = hooks[event][0]['hooks'][0]['command']
            result = subprocess.run(['sh', '-c', command], input='{}', text=True,
                                    capture_output=True,
                                    env=dict(os.environ, OPENRIG_SESSION_NAME='bridge-captain@crew'))
            self.assertIn('quota_hook_process_failed', result.stdout)
            self.assertEqual(hooks[event][0]['hooks'][0]['onFailure'], 'block')

    def test_artifact_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = str(Path(tmp).resolve() / 'plugin')
            write_plugin(directory, **self.args())
            with self.assertRaises(FileExistsError):
                write_plugin(directory, **self.args())

    def test_invalid_session_refused(self):
        args = self.args(); args['session'] = 'not a session'
        with self.assertRaises(ValueError): build(**args)
