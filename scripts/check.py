#!/usr/bin/env python3
"""No-network source checks and fixture tests, never real cleanup."""
import json
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
rig=json.loads((root/'rig.yaml').read_text()); agent=json.loads((root/'agents/crew/agent.yaml').read_text())
seats={f"{p['id']}.{m['id']}":m for p in rig['pods'] for m in p['members']}
expected={'commander','captain','sky-command','strider1','strider2','lancer','pyro','witch','inquisitor','hierophant','cleric','chronicler','deckhand','warden','lookout'}
assert {s.split('.')[1] for s in seats}==expected and len(seats)==15
for m in seats.values():
 assert m['profile'] in agent['profiles']
 assert m['runtime'] in ('codex','claude-code')
 assert m.get('effort') == 'high'
 for f in agent['profiles'][m['profile']]['startup']['files']:
  assert (root/'agents/crew'/f['path']).is_file()
for e in rig['edges']: assert e['from'] in seats and e['to'] in seats
for pod in rig['pods']:
 for e in pod['edges']: assert pod['id']+'.'+e['from'] in seats and pod['id']+'.'+e['to'] in seats
for f in rig['startup']['files']: assert (root/f['path']).is_file()
assert (root/rig['culture_file']).is_file()
assert 'Knight' not in [m['label'] for m in seats.values()]
assert 'integration' in (root/'agents/crew/guidance/warden.md').read_text()
for directory in ('budget','hygiene','routing','factory'):
 files=list((root/directory).rglob('test*.py'))
 assert files, f'No tests for {directory}'
 cmd=[sys.executable,'-m','unittest','discover','-s',str(root/directory),'-p','test*.py','-v']
 if directory in ('budget','routing','factory'): cmd += ['-t',str(root)]
 subprocess.run(cmd,cwd=root,check=True)
print('15-seat roster, handoff references, startup files, budget, hygiene, routing and factory tests passed.')
