import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from .github_intake import fetch_issue,intake_selected
class GitHubIntakeTests(unittest.TestCase):
 def issue(self):return dict(number=1,title='A',body='untrusted',html_url='https://github.com/owner/repo/issues/1',state='open',updated_at='2026-11-13T00:00:00Z')
 def test_explicit_fetch(self):
  seen=[]
  def runner(argv):seen.append(argv);return SimpleNamespace(returncode=0,stdout=json.dumps(self.issue()))
  self.assertEqual(fetch_issue('owner/repo',1,gh='/gh',runner=runner)['number'],1);self.assertEqual(seen,[['/gh','api','--hostname','github.com','--method','GET','repos/owner/repo/issues/1']])
  with self.assertRaises(ValueError):fetch_issue('owner/repo',True,gh='/gh',runner=runner)
 def test_cold_roundtrip_mock(self):
  seen=[]
  def github(argv):return SimpleNamespace(returncode=0,stdout=json.dumps(self.issue()))
  def native(argv):seen.append(argv);return SimpleNamespace(returncode=0,stdout=json.dumps({'qitemId':argv[argv.index('--id')+1]}))
  with tempfile.TemporaryDirectory() as state,patch.dict(os.environ,{'OPENRIG_SESSION_NAME':'commander@rig'}):
   args=dict(repository='owner/repo',number=1,gh='/gh',rig='/rig',state_dir=state,context=dict(caller='commander@rig',destination='planner@rig',target_repo='repo',repository='owner/repo',registered=True,verified=True),github_runner=github,queue_runner=native)
   self.assertEqual(intake_selected(**args)['state'],'submitted');self.assertEqual(intake_selected(**args)['state'],'submitted');self.assertEqual(len(seen),1);self.assertIn('--no-nudge',seen[0]);self.assertNotIn('--source',seen[0])
 def test_identity_not_borrowed(self):
  with patch.dict(os.environ,{'OPENRIG_SESSION_NAME':'actual@rig'}):
   with self.assertRaises(ValueError):intake_selected(repository='owner/repo',number=1,gh='/gh',rig='/rig',state_dir='/unused',context=dict(verified=True,registered=True,caller='other@rig',repository='owner/repo'))
