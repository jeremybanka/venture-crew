"""Issue-driven factory CLI. Planning is read-only; execution verbs require explicit scope and --execute."""
import argparse
import json
from pathlib import Path
from .intake import draft_issue
from .publication import plan_publication
from .dispatch import plan_dispatch

def read(path):
 raw=Path(path).read_text()
 if len(raw)>2000000:raise ValueError('oversized_input')
 return json.loads(raw)

def main():
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='cmd',required=True)
 a=s.add_parser('intake');a.add_argument('--repo',required=True);a.add_argument('--issue',required=True,type=int);a.add_argument('--snapshot',required=True);a.add_argument('--source',required=True);a.add_argument('--destination',required=True);a.add_argument('--target-repo',required=True)
 a=s.add_parser('publication');a.add_argument('--repo',required=True);a.add_argument('--issue',required=True,type=int);a.add_argument('--base',required=True);a.add_argument('--slices',required=True)
 a=s.add_parser('dispatch');a.add_argument('--evidence',required=True)
 a=s.add_parser('enqueue');a.add_argument('--repo',required=True);a.add_argument('--issue',required=True,type=int);a.add_argument('--context',required=True);a.add_argument('--gh',required=True);a.add_argument('--rig',required=True);a.add_argument('--state-dir',required=True);a.add_argument('--execute',action='store_true',required=True)
 a=s.add_parser('publish');a.add_argument('--repo',required=True);a.add_argument('--issue',required=True,type=int);a.add_argument('--base',required=True);a.add_argument('--base-sha',required=True);a.add_argument('--slices',required=True);a.add_argument('--slice-id',required=True);a.add_argument('--state-dir',required=True);a.add_argument('--gh',required=True);a.add_argument('--execute',action='store_true',required=True)
 args=p.parse_args()
 try:
  if args.cmd=='intake':out=draft_issue(args.repo,args.issue,read(args.snapshot),source=args.source,destination=args.destination,target_repo=args.target_repo)
  elif args.cmd=='publication':out=plan_publication(authorized_repo=args.repo,authorized_issue=args.issue,target_base=args.base,slices=read(args.slices))
  elif args.cmd=='dispatch':out=plan_dispatch(**read(args.evidence))
  elif args.cmd=='enqueue':
   from .github_intake import intake_selected
   out=intake_selected(repository=args.repo,number=args.issue,gh=args.gh,rig=args.rig,state_dir=args.state_dir,context=read(args.context))
  else:
   from .github import GitHubPublisher
   out=GitHubPublisher(args.state_dir,gh_executable=args.gh).publish(authorized_repo=args.repo,authorized_issue=args.issue,target_base=args.base,expected_base_sha=args.base_sha,slices=read(args.slices),slice_id=args.slice_id)
  print(json.dumps(out,indent=2,allow_nan=False));return 2 if isinstance(out,dict) and (out.get('status') in ('blocked','unknown','reconciliation_required') or out.get('state')=='unknown') else 0
 except Exception as e:
  print(json.dumps({'status':'blocked','error':type(e).__name__,'reason':str(e)}));return 2
if __name__=='__main__':raise SystemExit(main())
