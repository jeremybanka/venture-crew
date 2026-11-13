"""Print native hook fragments for review. Never writes, installs or trusts hooks.

Codex uses project .codex/hooks.json. Claude uses .claude/settings.local.json;
its fragment is an explicit admission blockade, not a working Claude adapter.
"""
import argparse
import json
from pathlib import Path
import shlex
from .controller import ident
from .hook import denied

CODEX_EVENTS=('SessionStart','UserPromptSubmit','Stop','Interrupt','PreToolUse','PreCompact','PostCompact')
CLAUDE_EVENTS=('SessionStart','UserPromptSubmit','PreToolUse')


def prepare(provider,seat,root,python,db):
    ident(seat)
    root,db=Path(root),Path(db)
    if not root.is_absolute() or not db.is_absolute() or not Path(python).is_absolute():
        raise ValueError('absolute_runtime_paths_required')
    if provider not in ('claude','codex'): raise ValueError('invalid_provider')
    hooks={}
    for event in CODEX_EVENTS if provider=='codex' else CLAUDE_EVENTS:
        if provider=='codex':
            command='cd '+shlex.quote(str(root))+' && '+shlex.join([python,'-m','budget.hook','--provider',provider,'--seat',seat,'--event',event,'--db',str(db)])
            fallback=json.dumps(denied(event,'quota_hook_process_failed'),separators=(',',':'))
            command='( '+command+' ) || printf \'%s\\n\' '+shlex.quote(fallback)
        else:
            # Native prompt_id is documented; trustworthy quota is not established. A
            # prepared Claude fragment blocks work, instead of pretending that
            # running the generic adapter makes native enforcement verified.
            payload=json.dumps(denied(event,'claude_activation_blocked_identity_freshness_and_turn_lifecycle_unverified'),separators=(',',':'))
            command='printf \'%s\\n\' '+shlex.quote(payload)
        handler={'type':'command','command':command,'timeout':8}
        if provider=='codex': handler['statusMessage']='Wayforge quota admission'
        elif event in ('UserPromptSubmit','PreToolUse'): handler['onFailure']='block'
        group={'hooks':[handler]}
        if event=='PreToolUse': group['matcher']='.*'
        hooks[event]=[group]
    return dict(provider=provider,seat=seat,
                target='.codex/hooks.json' if provider=='codex' else '.claude/settings.local.json',
                activation='unverified-native-hook-trust-and-lifecycle' if provider=='codex' else 'blocked-claude-contract-incomplete',
                fragment={'hooks':hooks})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider',required=True,choices=('codex','claude'));p.add_argument('--seat',required=True)
    p.add_argument('--root',required=True);p.add_argument('--python',required=True);p.add_argument('--db',required=True)
    a=p.parse_args()
    print(json.dumps(prepare(a.provider,a.seat,a.root,a.python,a.db),indent=2))

if __name__=='__main__': main()
