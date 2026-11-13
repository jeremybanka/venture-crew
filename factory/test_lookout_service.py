import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from .lookout_service import LookoutService


class ServiceTests(unittest.TestCase):
    def service(self, root, status='failed', runner=None, wake=False):
        self.report = dict(repo='owner/repo', pr=1, head_sha='a'*40, status=status,
                           terminal=status=='merged', checked_at=1.0, changed=True)
        return LookoutService(observer=SimpleNamespace(poll=lambda: dict(self.report)),
                              state_dir=str(Path(root).resolve()), rig='/bin/rig',
                              source='lookout-observer@crew', destination='bridge-captain@crew', runner=runner, wake_captain=wake)

    def native(self, wake=False):
        self.rows, self.calls = {}, []
        def run(argv):
            self.calls.append(argv)
            if argv[1:3] == ['queue', 'show']:
                row = self.rows.get(argv[3])
                return SimpleNamespace(returncode=0 if row else 1, stdout=json.dumps(row))
            self.assertEqual(argv[1:3], ['queue', 'create'])
            if wake:
                self.assertNotIn('--no-nudge', argv)
                self.assertEqual(argv[argv.index('--gate')+1], 'ci-triage')
            else:
                self.assertIn('--no-nudge', argv)
            get = lambda flag: argv[argv.index(flag)+1]
            row = dict(qitemId=get('--id'), body=Path(get('--body-file')).read_text(),
                       sourceSession=get('--source'), destinationSession=get('--destination'))
            self.rows[row['qitemId']] = row
            return SimpleNamespace(returncode=0, stdout=json.dumps(row))
        return run

    def test_durable_dedup_no_nudge_and_status(self):
        with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            service = self.service(root, runner=self.native())
            with service.lock():
                result = service.tick()
                self.report.update(changed=False, checked_at=2.0)
                service.tick()
            self.assertEqual(result['deliveries'][0]['state'], 'submitted')
            self.assertEqual(len([a for a in self.calls if a[2]=='create']), 1)
            self.assertTrue((Path(root)/'delivery-status.json').exists())

    def test_opt_in_native_wake_is_deduplicated(self):
        with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            service = self.service(root, runner=self.native(wake=True), wake=True)
            with service.lock():
                service.tick(); service.tick()
            self.assertEqual(len([a for a in self.calls if a[2]=='create']), 1)

    def test_recovery_after_failure_delivered_once(self):
        with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            service = self.service(root, runner=self.native(wake=True), wake=True)
            with service.lock():
                service.tick()
                self.report.update(status='observed_green', checked_at=2.0)
                service.tick(); service.tick()
            self.assertEqual(len([a for a in self.calls if a[2]=='create']), 2)

    def test_unknown_retry_same_identity_and_payload(self):
        with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            native = self.native()
            service = self.service(root, runner=lambda argv: SimpleNamespace(returncode=1, stdout='secret'))
            with service.lock():
                initial = service.tick()
            service = self.service(root, runner=native)
            with service.lock():
                final = service.tick()
            self.assertEqual(initial['deliveries'][0]['id'], final['deliveries'][0]['id'])
            self.assertEqual(final['deliveries'][0]['state'], 'submitted')
            self.assertNotIn('secret', (Path(root)/'delivery-status.json').read_text())

    def test_commit_before_response_reconciles_without_second_create(self):
        with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            native = self.native()
            def run(argv):
                result = native(argv)
                if argv[2] == 'create': return SimpleNamespace(returncode=1, stdout='')
                return result
            service = self.service(root, runner=run)
            with service.lock(): result = service.tick()
            self.assertEqual(result['deliveries'][0]['state'], 'submitted')
            self.assertEqual(len([a for a in self.calls if a[2]=='create']), 1)

    def test_mismatched_native_record_holds_without_recreate(self):
        with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            native = self.native()
            def run(argv):
                if argv[2] == 'show':
                    return SimpleNamespace(returncode=0, stdout=json.dumps(dict(qitemId=argv[3], body='different')))
                return native(argv)
            service = self.service(root, runner=run)
            with service.lock():
                result = service.tick()
                service.tick()
            self.assertEqual(result['deliveries'][0]['state'], 'conflict')
            self.assertFalse(self.calls)

    def test_lifetime_lock_and_managed_identity_rejected(self):
        with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            service = self.service(root, runner=self.native())
            with self.assertRaises(ValueError): service.tick()
            with service.lock():
                another = self.service(root, runner=self.native())
                with self.assertRaises(BlockingIOError):
                    with another.lock(): pass
            with patch.dict(os.environ, {'OPENRIG_SESSION_NAME': 'captain@crew'}):
                with self.assertRaises(ValueError): self.service(root)

    def test_no_handoff_for_green_pending_or_terminal(self):
        for state in ('pending', 'observed_green', 'merged'):
            with TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
                service = self.service(root, status=state, runner=self.native())
                with service.lock(): result = service.tick()
                self.assertFalse(result['deliveries']); self.assertFalse(self.calls)


if __name__ == '__main__': unittest.main()
