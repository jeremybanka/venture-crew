import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import json
from factory.native_dispatch import launch_fresh
from budget.native_claude import persist_sample
from factory import test_native_dispatch as native_fixtures
from routing import test_model_allowance as allowance_fixtures


class ModelDispatchTests(unittest.TestCase):
    def test_fable_exhaustion_at_second_preflight_prevents_launch(self):
        fixture = allowance_fixtures.ModelAllowanceTests(); fixture.setUp()
        evidence = native_fixtures.NativeDispatchTests().evidence()
        evidence['preferences'] = {'work.strider1': ['Fable']}
        evidence['catalog'] = fixture.catalog
        evidence['statuses'] = fixture.status
        for state in evidence['statuses'].values():
            state['opening_id'] = 'opening'
        evidence['readiness']['claude-code'] = True
        evidence['model_snapshot'] = {'accepted':True, 'sample':fixture.sample}
        evidence['launch_evidence'].update(model='claude-fable-5-2', provider='claude',runtime='claude-code')
        calls = []
        def preflight():
            result = copy.deepcopy(evidence)
            if calls:
                result['model_snapshot']['sample']['informational_windows']['model:fable']['remaining_percent'] = 0
            persist_sample(snapshot_path, result['model_snapshot'])
            result['model_snapshot'] = json.loads(snapshot_path.read_text())
            return result
        def runner(argv):
            calls.append(argv)
            return SimpleNamespace(returncode=0,stdout=json.dumps(dict(ok=True,complete=True,
                launchable=True,stopRequired=False,currentOccupant='absent',blockers=[],sessionName='strider@rig')))
        with tempfile.TemporaryDirectory() as root:
            snapshot_path = Path(root) / 'claude-latest.json'
            with self.assertRaisesRegex(ValueError, 'no_eligible_preference'):
                launch_fresh(executable='/verified/rig',journal=Path(root)/'seat.json',
                             reason='fixture',preflight=preflight,runner=runner)
            self.assertFalse((Path(root)/'seat.json').exists())
        self.assertEqual(len(calls),1)
        self.assertIn('--plan',calls[0])
