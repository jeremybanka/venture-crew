import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import deckhand as d


class HygieneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'repo'
        self.remote = self.root / 'remote.git'
        self.repo.mkdir()
        d.git(self.repo, 'init', '-b', 'main')
        d.git(self.repo, 'config', 'user.name', 'Test')
        d.git(self.repo, 'config', 'user.email', 'test@example.invalid')
        (self.repo / '.gitignore').write_text('.worktrees/\n.cache/\n')
        d.git(self.repo, 'add', '.gitignore')
        d.git(self.repo, 'commit', '-m', 'initial')
        self.remote.mkdir()
        d.git(self.remote, 'init', '--bare')
        d.git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        d.git(self.repo, 'push', 'origin', 'main')
        self.tree = self.repo / '.worktrees' / 'task-1'
        d.git(self.repo, 'worktree', 'add', '-b', 'task-1', str(self.tree))
        self.data = {}
        self.task = d.register(self.data, '1', self.repo, self.tree, 'strider-1')

    def tearDown(self):
        self.tmp.cleanup()

    def close(self):
        d.transition(self.task, '1', 'closed', True)

    def test_active_hold(self):
        self.assertFalse(d.retire(self.task, True)['eligible'])
        self.assertTrue(self.tree.exists())

    def test_explicit_inactivity_required(self):
        with self.assertRaises(ValueError):
            self.close_without_confirmation()
        with self.assertRaises(ValueError):
            d.retire(self.task)

    def close_without_confirmation(self):
        d.transition(self.task, '1', 'closed')

    def test_clean_remote_retire_keeps_branch(self):
        self.close()
        self.assertTrue(d.retire(self.task, True)['retired'])
        self.assertFalse(self.tree.exists())
        self.assertEqual(d.git(self.repo, 'rev-parse', 'task-1'), self.task['base'])

    def test_untracked_hold(self):
        self.close()
        (self.tree / 'valuable').write_text('unique')
        self.assertFalse(d.retire(self.task, True)['eligible'])
        self.assertEqual((self.tree / 'valuable').read_text(), 'unique')

    def test_dirty_hold(self):
        self.close()
        (self.tree / '.gitignore').write_text('unique edit')
        self.assertFalse(d.retire(self.task, True)['eligible'])

    def test_ignored_hold(self):
        self.close()
        (self.tree / '.cache').mkdir()
        (self.tree / '.cache' / 'valuable').write_text('unique')
        self.assertFalse(d.retire(self.task, True)['eligible'])

    def test_unpushed_hold(self):
        self.close()
        (self.tree / 'file').write_text('new')
        d.git(self.tree, 'add', 'file')
        d.git(self.tree, 'commit', '-m', 'unpushed')
        self.assertFalse(d.retire(self.task, True)['eligible'])
        self.assertTrue(self.tree.exists())

    def test_pause_locks_resume_unlocks(self):
        d.transition(self.task, '1', 'paused', True)
        self.assertIn('locked', d.inspect(self.task)['reasons'])
        d.transition(self.task, '1', 'active')
        self.assertNotIn('locked', d.inspect(self.task)['reasons'])

    def test_foreign_lock_preserved(self):
        d.git(self.repo, 'worktree', 'lock', '--reason', 'human hold', str(self.tree))
        d.transition(self.task, '1', 'active')
        self.close()
        self.assertFalse(d.retire(self.task, True)['eligible'])
        self.assertEqual(d.worktrees(self.repo)[1]['locked'], 'human hold')

    def test_deleted_remote_hold(self):
        self.close()
        d.git(self.repo, 'remote', 'remove', 'origin')
        self.assertFalse(d.retire(self.task, True)['eligible'])

    def test_no_stale_tracking_proof(self):
        self.close()
        # Remove the actual remote branch; existing local tracking ref is insufficient.
        d.git(self.remote, 'update-ref', '-d', 'refs/heads/main')
        self.assertFalse(d.retire(self.task, True)['eligible'])

    def test_path_escape(self):
        other = self.root / 'outside'
        d.git(self.repo, 'worktree', 'add', '-b', 'outside', str(other))
        with self.assertRaises(ValueError):
            d.register(self.data, '2', self.repo, other, 'strider')

    def test_symlink_rejected(self):
        link = self.root / 'alias'
        link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(ValueError):
            d.register(self.data, '2', link, link / '.worktrees' / 'task-1', 'strider')

    def test_duplicate_owner(self):
        with self.assertRaises(ValueError):
            d.register(self.data, '2', self.repo, self.tree, 'other')

    def test_change_during_check_hold(self):
        self.close()
        original = d.remote_proof
        def race(task, head):
            proof = original(task, head)
            (self.tree / 'new-work').write_text('do not delete')
            return proof
        with patch.object(d, 'remote_proof', race):
            self.assertFalse(d.retire(self.task, True)['eligible'])
        self.assertTrue((self.tree / 'new-work').exists())

    def test_git_lock_hold(self):
        self.close()
        lock = Path(d.git(self.tree, 'rev-parse', '--git-path', 'index.lock'))
        lock.write_text('')
        self.assertIn('git_operation_in_progress', d.inspect(self.task)['reasons'])

    def test_assume_unchanged_hold(self):
        self.close()
        d.git(self.tree, 'update-index', '--assume-unchanged', '.gitignore')
        (self.tree / '.gitignore').write_text('hidden edit')
        self.assertIn('hidden_index_flags_require_manual_review', d.inspect(self.task)['reasons'])

    def test_skip_worktree_hold(self):
        self.close()
        d.git(self.tree, 'update-index', '--skip-worktree', '.gitignore')
        self.assertIn('hidden_index_flags_require_manual_review', d.inspect(self.task)['reasons'])

    def test_ledger_persistence(self):
        state = self.root / 'state'
        with d.ledger(state) as data:
            data['1'] = self.task
        with d.ledger(state) as data:
            self.assertEqual(data['1']['owner'], 'strider-1')
        self.assertEqual(json.loads((state / 'tasks.json').read_text())['1']['status'], 'active')


if __name__ == '__main__':
    unittest.main()
