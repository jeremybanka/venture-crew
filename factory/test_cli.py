import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from .__main__ import main
class FactoryCLITests(unittest.TestCase):
 def test_execute_flag_required(self):
  with patch('sys.argv',['factory','publish','--repo','owner/repo','--issue','1','--base','main','--base-sha','a'*40,'--slices','unused','--slice-id','s1','--state-dir','/unused','--gh','/gh']),patch('sys.stderr',io.StringIO()):
   with self.assertRaises(SystemExit):main()
 def test_publish_delegates_explicit_scope(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'slices';path.write_text('[]')
   with patch('sys.argv',['factory','publish','--repo','owner/repo','--issue','1','--base','main','--base-sha','a'*40,'--slices',str(path),'--slice-id','s1','--state-dir',tmp,'--gh','/gh','--execute']),patch('factory.github.GitHubPublisher') as publisher,patch('sys.stdout',io.StringIO()):
    publisher.return_value.publish.return_value={'status':'unknown'}
    self.assertEqual(main(),2);self.assertEqual(publisher.call_args.kwargs,{'gh_executable':'/gh'});self.assertEqual(publisher.return_value.publish.call_args.kwargs['authorized_repo'],'owner/repo')
 def test_enqueue_no_implicit_scope(self):
  with patch('sys.argv',['factory','enqueue','--execute']),patch('sys.stderr',io.StringIO()):
   with self.assertRaises(SystemExit):main()
