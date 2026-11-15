import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from .scoped_hook import applies, main


class ScopedHookTests(unittest.TestCase):
    def test_exact_and_descendant_only(self):
        root = Path('/tmp/task')
        for cwd in ('/tmp/task', '/tmp/task/src'):
            self.assertTrue(applies({'cwd':cwd}, root, 'worker@rig', {}))
        for cwd in ('/tmp/task-other', '/tmp/other', 'task'):
            self.assertFalse(applies({'cwd':cwd}, root, 'worker@rig', {}))
        self.assertFalse(applies({}, root, 'worker@rig', {}))
        self.assertTrue(applies(None, root, 'worker@rig', {'OPENRIG_SESSION_NAME':'worker@rig'}))
        self.assertFalse(applies(None, root, 'worker@rig', {'OPENRIG_SESSION_NAME':'other@rig'}))

    def test_symlink_escape_is_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'task'; root.mkdir()
            (root/'escape').symlink_to(Path(tmp), target_is_directory=True)
            self.assertFalse(applies({'cwd':str(root/'escape')},root,'worker@rig',{}))

    def run_main(self, raw, env):
        argv=['scoped_hook','--scope','/tmp/task','--session-name','worker@rig',
              '--provider','codex','--seat','work.strider1','--event','SessionStart']
        out=io.StringIO()
        with patch('sys.argv',argv),patch('sys.stdin',io.StringIO(raw)),patch.dict('os.environ',env,clear=True),contextlib.redirect_stdout(out),patch('budget.scoped_hook.hook.main',return_value=7) as delegate:
            result=main()
            return result,out.getvalue(),delegate.call_count

    def test_unrelated_session_is_noop_without_controller(self):
        self.assertEqual(self.run_main('{"cwd":"/tmp/other"}',{}),(0,'{}\n',0))
        self.assertEqual(self.run_main('malformed',{}),(0,'{}\n',0))

    def test_task_event_delegates_including_malformed_managed_event(self):
        self.assertEqual(self.run_main('{"cwd":"/tmp/task"}',{}),(7,'',1))
        self.assertEqual(self.run_main('malformed',{'OPENRIG_SESSION_NAME':'worker@rig'}),(7,'',1))
