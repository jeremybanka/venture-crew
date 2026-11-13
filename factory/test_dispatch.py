import unittest
from .dispatch import plan_dispatch
class DispatchTests(unittest.TestCase):
 def args(self):
  return dict(task=dict(queue_id='q1',source='captain@rig',destination='strider@rig',seat='work.strider1',target_repo='repo',body_file='/tmp/body',scope_approved=True,workspace_registered=True),native=dict(queue_id='q1',owner='captain@rig',caller='captain@rig',state='in-progress',seat_bindings={'work.strider1':'strider@rig'}),preferences={'work.strider1':['Sol']},catalog={'Sol':dict(verified=True,model='exact',provider='codex',runtime='codex')},statuses={p:dict(admission_open=p=='codex',active_permits=[]) for p in ('codex','claude')},readiness={'codex':True},no_existing_session=True)
 def test_ready_is_cold(self):
  p=plan_dispatch(**self.args());self.assertEqual(p['status'],'cold_handoff_planned');self.assertIn('--no-nudge',p['argv']);self.assertNotIn('--from',p['argv']);self.assertFalse(p['launch_authorized'])
 def test_no_impersonation(self):
  a=self.args();a['native']['caller']='other@rig';self.assertIsNone(plan_dispatch(**a)['argv'])
 def test_no_scope(self):
  a=self.args();a['task']['scope_approved']=False;self.assertIsNone(plan_dispatch(**a)['argv'])
 def test_active_seat_hold(self):
  a=self.args();a['statuses']['claude']['active_permits']=[{'seat':'work.strider1'}];self.assertIsNone(plan_dispatch(**a)['argv'])
 def test_unready(self):
  a=self.args();a['readiness']={};self.assertIsNone(plan_dispatch(**a)['argv'])

 def test_wrong_destination_binding(self):
  a=self.args();a['task']['destination']='other@rig';self.assertIsNone(plan_dispatch(**a)['argv'])
 def test_no_implicit_new_session(self):
  a=self.args();a.pop('no_existing_session');self.assertIsNone(plan_dispatch(**a)['argv'])
