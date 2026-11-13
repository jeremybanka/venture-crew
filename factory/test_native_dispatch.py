import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from .native_dispatch import launch_fresh

class NativeDispatchTests(unittest.TestCase):
 def evidence(self):
  return dict(task=dict(queue_id='q1',source='captain@rig',destination='strider@rig',seat='work.strider1',target_repo='repo',body_file='/tmp/body',scope_approved=True,workspace_registered=True),native=dict(queue_id='q1',owner='captain@rig',caller='captain@rig',state='in-progress',seat_bindings={'work.strider1':'strider@rig'}),preferences={'work.strider1':['Sol']},catalog={'Sol':dict(verified=True,model='exact',provider='codex',runtime='codex')},statuses={p:dict(admission_open=True,active_permits=[],opening_id='opening') for p in ('codex','claude')},readiness={'codex':True},no_existing_session=True,launch_evidence=dict(context_sha256='a'*64,workspace_revision='b'*40,seat='strider@rig',expected_session_name='strider@rig',model='exact',runtime='codex',provider='codex',effort='high',queue_id='q1',native_exact_turn_hook_verified=True,automatic_startup_admission_verified=True,settings_and_launch_serialized=True,permissions_verified=True,task_context_verified=True))
 def invoke(self,evidence,runner,root):
  return launch_fresh(executable='/verified/rig',journal=Path(root)/'seat.json',reason='authorized task',preflight=lambda:copy.deepcopy(evidence),runner=runner)
 def runner(self,calls,fail=False):
  def run(argv):
   calls.append(argv)
   if '--plan' in argv:return SimpleNamespace(returncode=0,stdout=json.dumps(dict(ok=True,complete=True,launchable=True,stopRequired=False,currentOccupant='absent',blockers=[],sessionName='strider@rig')))
   if fail:raise TimeoutError()
   return SimpleNamespace(returncode=0,stdout=json.dumps(dict(ok=True,sessionName='strider@rig',model='exact')))
  return run
 def test_launch_and_never_duplicate(self):
  with tempfile.TemporaryDirectory() as root:
   calls=[];runner=self.runner(calls)
   self.assertEqual(self.invoke(self.evidence(),runner,root)['status'],'native_launch_reported')
   self.assertEqual(self.invoke(self.evidence(),runner,root)['status'],'reconciliation_required')
   self.assertEqual(len(calls),2)
   self.assertNotIn('--stop',calls[-1]);self.assertNotIn('--operator',calls[-1])
 def test_timeout_is_not_retried(self):
  with tempfile.TemporaryDirectory() as root:
   calls=[];runner=self.runner(calls,True)
   self.assertEqual(self.invoke(self.evidence(),runner,root)['status'],'unknown')
   self.assertEqual(self.invoke(self.evidence(),runner,root)['status'],'reconciliation_required')
   self.assertEqual(len(calls),2)
 def test_missing_proof_blocks_before_native(self):
  for field in ('native_exact_turn_hook_verified','automatic_startup_admission_verified','settings_and_launch_serialized','permissions_verified','task_context_verified','effort'):
   with tempfile.TemporaryDirectory() as root:
    evidence=self.evidence();evidence['launch_evidence'].pop(field);calls=[]
    with self.assertRaises(ValueError):self.invoke(evidence,self.runner(calls),root)
    self.assertEqual(calls,[])
 def test_wrong_model_and_closed_peer_block(self):
  for change in ('model','budget','caller'):
   with tempfile.TemporaryDirectory() as root:
    evidence=self.evidence();calls=[]
    if change=='model':evidence['launch_evidence']['model']='other'
    elif change=='budget':evidence['statuses']['codex']['admission_open']=False
    else:evidence['native']['caller']='imposter'
    with self.assertRaises(ValueError):self.invoke(evidence,self.runner(calls),root)
    self.assertEqual(calls,[])
 def test_closed_other_provider_does_not_block_selected_provider(self):
  with tempfile.TemporaryDirectory() as root:
   evidence=self.evidence();calls=[]
   evidence['statuses']['claude'].update(admission_open=False,opening_id=None)
   self.assertEqual(self.invoke(evidence,self.runner(calls),root)['status'],'native_launch_reported')
   self.assertEqual(len(calls),2)
 def test_wrong_preview_session_binding_blocks(self):
  with tempfile.TemporaryDirectory() as root:
   evidence=self.evidence();calls=[]
   evidence['launch_evidence']['expected_session_name']='different@rig'
   with self.assertRaisesRegex(ValueError,'native_session_identity_missing'):
    self.invoke(evidence,self.runner(calls),root)
   self.assertEqual(len(calls),1)
 def test_live_native_occupant_blocks(self):
  with tempfile.TemporaryDirectory() as root:
   calls=[]
   def runner(argv):calls.append(argv);return SimpleNamespace(returncode=0,stdout=json.dumps(dict(ok=True,complete=True,launchable=False,stopRequired=True,currentOccupant='present',blockers=[])))
   with self.assertRaises(ValueError):self.invoke(self.evidence(),runner,root)
   self.assertEqual(len(calls),1)
 def test_task_artifact_or_workspace_change_blocks_same_queue_id(self):
  for change in ('context_sha256','workspace_revision','body_file','native_mapping'):
   with tempfile.TemporaryDirectory() as root:
    evidence=self.evidence();calls=[];count=[0]
    def preflight():
     count[0]+=1
     if count[0]>1:
      if change=='body_file':evidence['task']['body_file']='/tmp/changed'
      elif change=='native_mapping':evidence['native']['seat_bindings']['other']='new@rig'
      else:evidence['launch_evidence'][change]='c'*64
     return evidence
    with self.assertRaisesRegex(ValueError,'live_evidence_changed'):
     launch_fresh(executable='/verified/rig',journal=Path(root)/'seat.json',reason='task',preflight=preflight,runner=self.runner(calls))
    self.assertEqual(len(calls),1)
    self.assertFalse((Path(root)/'seat.json').exists())
 def test_missing_or_invalid_context_revision_blocks(self):
  for field in ('context_sha256','workspace_revision'):
   for value in (None,'','/tmp/file','not-verified','A'*64):
    with tempfile.TemporaryDirectory() as root:
     evidence=self.evidence();evidence['launch_evidence'][field]=value;calls=[]
     with self.assertRaisesRegex(ValueError,'verified_'+field+'_required'):
      self.invoke(evidence,self.runner(calls),root)
     self.assertEqual(calls,[])
 def test_second_preflight_revalidated(self):
  with tempfile.TemporaryDirectory() as root:
   evidence=self.evidence();calls=[];count=[0]
   def preflight():
    count[0]+=1
    if count[0]>1:evidence['statuses']['codex']['admission_open']=False
    return evidence
   with self.assertRaises(ValueError):launch_fresh(executable='/verified/rig',journal=Path(root)/'seat.json',reason='task',preflight=preflight,runner=self.runner(calls))
   self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
