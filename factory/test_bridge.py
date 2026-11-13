import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from .bridge import cold_enqueue

class BridgeTests(unittest.TestCase):
 def test_cold_idempotent_and_changed_revision_hold(self):
  with tempfile.TemporaryDirectory() as tmp:
   body=Path(tmp)/'body.json';journal=Path(tmp)/'journal.json';calls=[]
   args=['queue','create','--destination','bridge-commander@rig','--body-file',str(body),'--id','stable-id','--summary','Issue','--target-repo','repo','--no-nudge','--json']
   def runner(a): calls.append(a);return SimpleNamespace(returncode=0,stdout='{"qitemId":"stable-id"}')
   kw=dict(executable='/verified/rig',argv=args,body='body',body_file=str(body),journal=journal,runner=runner)
   self.assertEqual(cold_enqueue(**kw)['state'],'submitted');self.assertEqual(cold_enqueue(**kw)['state'],'submitted');self.assertEqual(len(calls),1)
   with self.assertRaises(ValueError):cold_enqueue(**{**kw,'body':'changed'})
   self.assertNotIn('--source',calls[0])
 def test_unknown_retains_retry_id(self):
  with tempfile.TemporaryDirectory() as tmp:
   body=Path(tmp)/'body';journal=Path(tmp)/'journal';calls=[]
   args=['queue','create','--destination','seat@rig','--body-file',str(body),'--id','same','--summary','Issue','--target-repo','repo','--no-nudge','--json']
   def runner(a):calls.append(a);raise TimeoutError()
   kw=dict(executable='/verified/rig',argv=args,body='body',body_file=str(body),journal=journal,runner=runner)
   self.assertEqual(cold_enqueue(**kw)['state'],'unknown');self.assertEqual(cold_enqueue(**kw)['state'],'unknown');self.assertEqual(len(calls),1)
 def test_no_arbitrary_commands(self):
  with self.assertRaises(ValueError):cold_enqueue(executable='/rig',argv=['agent','start'],body='',body_file='/tmp/body',journal='/tmp/not-created')
 def test_collision_rejected_and_predictable_temp_untouched(self):
  with tempfile.TemporaryDirectory() as tmp:
   body=Path(tmp)/'body';journal=Path(tmp)/'journal';victim=Path(tmp)/'victim';victim.write_text('keep')
   journal.with_suffix('.tmp').symlink_to(victim)
   def args(path):return ['queue','create','--destination','seat@rig','--body-file',str(path),'--id','same','--summary','Issue','--target-repo','repo','--no-nudge','--json']
   with self.assertRaises(ValueError):cold_enqueue(executable='/rig',argv=args(journal),body='task',body_file=str(journal),journal=journal)
   cold_enqueue(executable='/rig',argv=args(body),body='task',body_file=str(body),journal=journal,runner=lambda a:SimpleNamespace(returncode=0,stdout='{"qitemId":"same"}'))
   self.assertEqual(victim.read_text(),'keep');self.assertEqual(body.read_text(),'task')
 def test_shared_body_lock_blocks(self):
  with tempfile.TemporaryDirectory() as tmp:
   body=Path(tmp)/'body';lock=Path(tmp)/'body.lock';lock.write_text('foreign')
   args=['queue','create','--destination','seat@rig','--body-file',str(body),'--id','same','--summary','Issue','--target-repo','repo','--no-nudge','--json']
   with self.assertRaises(FileExistsError):cold_enqueue(executable='/rig',argv=args,body='task',body_file=str(body),journal=Path(tmp)/'journal')
   self.assertEqual(lock.read_text(),'foreign')
if __name__=='__main__':unittest.main()
