import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from budget.controller import Controller


class RoutingCliTests(unittest.TestCase):
    def test_explicit_evidence_and_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=root/'db'; Controller(db)
            files={'preferences':{'preferences':{'crew.strider1':['Sol']}},
                   'catalog':{'models':{}},'readiness':{'codex':False,'claude-code':False},
                   'session-evidence':{'no_existing_session':True}}
            command=[sys.executable,'-m','routing','--seat','crew.strider1','--db',str(db)]
            for key,value in files.items():
                path=root/(key+'.json'); path.write_text(json.dumps(value)); command += ['--'+key,str(path)]
            before=db.read_bytes(),db.stat().st_mtime_ns
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertEqual(json.loads(result.stdout)['reason'],'no_eligible_preference')
            evidence=root/'session-evidence.json'
            for bad in ({},{'current':None},{'no_existing_session':True,'current':{}}, {'no_existing_session':1}):
                evidence.write_text(json.dumps(bad))
                result=subprocess.run(command,capture_output=True,text=True)
                self.assertEqual(result.returncode,1)
                self.assertFalse(json.loads(result.stderr)['ready_to_launch'])
            self.assertEqual(before,(db.read_bytes(),db.stat().st_mtime_ns))
            evidence.write_text(json.dumps({'no_existing_session':True}))
            missing=root/'missing'/'db'; command[command.index('--db')+1]=str(missing)
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertFalse(missing.parent.exists())

if __name__=='__main__': unittest.main()
