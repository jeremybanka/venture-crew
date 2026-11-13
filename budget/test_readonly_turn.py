"""Read-only inspection and exact-turn tool admission regression tests."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .controller import Controller
from .hook import handle
from .__main__ import main


class ReadonlyTurnTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'budget.sqlite3'

    def cli(self, *args):
        with patch('sys.argv', ['budget', '--db', str(self.path), *args]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main()

    def test_missing_readonly_never_creates_directory_or_database(self):
        self.path = self.path / 'nested' / 'db'
        with self.assertRaisesRegex(ValueError, 'uninitialized_controller'):
            Controller(self.path, readonly=True)
        self.assertEqual(self.cli('status', 'codex'), 1)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_status_does_not_write_and_mutations_rejected(self):
        Controller(self.path)
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        c = Controller(self.path, readonly=True)
        self.assertFalse(c.status('codex')['admission_open'])
        self.assertEqual(self.cli('status', 'codex'), 0)
        for mutate in (lambda: c.pause('codex'), lambda: c.invalidate('codex','bad'),
                       lambda: c.admit('codex','seat','session','turn'),
                       lambda: c.release('codex','session','turn')):
            with self.assertRaisesRegex(ValueError, 'readonly_controller'):
                mutate()
        with c.tx(readonly=True) as db:
            with self.assertRaises(Exception):
                db.execute('DELETE FROM providers')
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])

    def test_print_only_does_not_initialize_controller(self):
        with patch('budget.__main__.Controller', side_effect=AssertionError('must not open state')), patch('budget.native_codex.NativeClient'), patch('budget.adapters.codex', return_value={'safe':True}):
            self.assertEqual(self.cli('observe-codex','--once','--print-only'), 0)
        self.assertFalse(self.path.exists())

    def test_print_only_failure_does_not_initialize_controller(self):
        with patch('budget.__main__.Controller', side_effect=AssertionError('must not open state')), patch('budget.native_codex.NativeClient', side_effect=RuntimeError('offline')):
            self.assertEqual(self.cli('observe-codex','--once','--print-only'), 1)
        self.assertFalse(self.path.exists())

    def test_tool_requires_exact_current_turn(self):
        c=Controller(self.path, clock=lambda:1000)
        c.configure('codex','account',{'primary':10})
        c.observe('codex',dict(provider='codex',account_id='account',observed_at=1000,account_bound=True,freshness_proven=True,usage_allowed=True,source='test',windows={'primary':dict(remaining_percent=90,resets_at=2000)}))
        c.arm('codex','test')
        self.assertTrue(c.admit('codex','seat','session','turn1')['allowed'])
        readonly=Controller(self.path, clock=lambda:1000, readonly=True)
        base=dict(hook_event_name='PreToolUse',tool_name='Read',session_id='session')
        for turn in (None, '', 'turn0', 'turn2'):
            result=handle('PreToolUse',dict(base,turn_id=turn),readonly,'codex','seat')
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertEqual(handle('PreToolUse',dict(base,turn_id='turn1'),readonly,'codex','seat'), {})
        c.release('codex','session','turn1')
        self.assertTrue(c.admit('codex','seat','session','turn2')['allowed'])
        result=handle('PreToolUse',dict(base,turn_id='turn1'),readonly,'codex','seat')
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertEqual(handle('PreToolUse',dict(base,turn_id='turn2'),readonly,'codex','seat'), {})

if __name__ == '__main__':
    unittest.main()
