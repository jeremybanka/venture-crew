"""Explicit selected-issue fetch and cold native enqueue integration.

No repo or issue defaults, autonomous polling, source identity override, or model
nudge. Caller supplies a verified actual managed context and registered mapping.
"""
import json
import os
from pathlib import Path
import subprocess
from .intake import draft_issue, REPO
from .bridge import cold_enqueue

def run(argv):
 return subprocess.run(argv,text=True,capture_output=True,timeout=30,check=False)

def fetch_issue(repository,number,*,gh,runner=run):
 if not isinstance(repository,str) or not REPO.fullmatch(repository):raise ValueError('explicit_repository_required')
 if type(number) is not int or number<=0:raise ValueError('explicit_positive_issue_required')
 if not Path(gh).is_absolute():raise ValueError('absolute_approved_gh_required')
 result=runner([gh,'api','--hostname','github.com','--method','GET',f'repos/{repository}/issues/{number}'])
 if result.returncode!=0:raise ValueError('github_issue_read_failed')
 if len(result.stdout)>2000000:raise ValueError('oversized_github_response')
 value=json.loads(result.stdout)
 if not isinstance(value,dict):raise ValueError('invalid_github_issue')
 return value

def intake_selected(*,repository,number,gh,rig,state_dir,context,github_runner=run,queue_runner=run):
 """Fetch a selected issue and cold-enqueue through trusted verified mapping.

 context supplies caller,destination,target_repo,repository,registered=True,
 verified=True. This is a trusted native adapter contract, not user/issue data.
 Do not populate it from issue text; verify it against current native topology.
 """
 if not isinstance(context,dict) or context.get('verified') is not True or context.get('registered') is not True:
  raise ValueError('verified_native_context_required')
 if context.get('repository','').casefold()!=repository.casefold():raise ValueError('repository_mapping_mismatch')
 actual=os.environ.get('OPENRIG_SESSION_NAME') or os.environ.get('RIGGED_SESSION_NAME')
 if not actual or context.get('caller')!=actual:raise ValueError('actual_managed_caller_required')
 issue=fetch_issue(repository,number,gh=gh,runner=github_runner)
 draft=draft_issue(repository,number,issue,source=actual,destination=context.get('destination'),target_repo=context.get('target_repo'))
 root=Path(state_dir).resolve();root.mkdir(parents=True,exist_ok=True)
 body=root/(draft['queue_id']+'.body.json');journal=root/(draft['queue_id']+'.receipt.json')
 argv=draft['argv'][1:];i=argv.index('--source');del argv[i:i+2]
 argv[argv.index('--body-file')+1]=str(body)
 return cold_enqueue(executable=rig,argv=argv,body=draft['stdin'],body_file=str(body),journal=journal,runner=queue_runner)
