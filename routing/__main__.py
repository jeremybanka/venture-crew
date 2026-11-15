"""Read-only routing decision; never launches, activates, or acquires a permit."""
import argparse
import json
from pathlib import Path
import sys
from budget.controller import Controller
from .routing import plan

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    data = Path(path).read_text()
    if len(data) > 1000000:
        raise ValueError('oversized_input')
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError('expected_json_object')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seat', required=True)
    parser.add_argument('--preferences', default=str(ROOT/'model-preferences.json'))
    parser.add_argument('--catalog', default=str(ROOT/'model-catalog.json'))
    parser.add_argument('--db', default=str(Path.home()/'.local/state/wayforge-rig/budget.sqlite3'))
    parser.add_argument('--readiness', required=True, help='JSON runtime -> boolean evidence file')
    parser.add_argument('--session-evidence', required=True, help='JSON explicit new-session assertion or current session + optional handover')
    parser.add_argument('--model-snapshot', default=str(ROOT/'.state/claude-latest.json'))
    args = parser.parse_args()
    try:
        evidence = read(args.session_evidence)
        if evidence.get('no_existing_session') is True:
            if 'current' in evidence or 'handover' in evidence:
                raise ValueError('conflicting_session_evidence')
            current, handover = None, None
        else:
            if 'no_existing_session' in evidence or not isinstance(evidence.get('current'), dict):
                raise ValueError('explicit_session_evidence_required')
            current, handover = evidence['current'], evidence.get('handover')
        controller = Controller(args.db, readonly=True)
        statuses = {p: controller.status(p) for p in ('codex','claude')}
        try:
            model_snapshot = read(args.model_snapshot)
        except (OSError, ValueError):
            model_snapshot = None  # Fable fails closed; other models remain eligible.
        result = plan(args.seat, read(args.preferences).get('preferences'),
                      read(args.catalog).get('models'), statuses, read(args.readiness),
                      current=current, handover=handover, model_snapshot=model_snapshot)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result['status']=='selected' else 2
    except Exception as error:
        print(json.dumps({'status':'blocked','ready_to_launch':False,
                          'reason':str(error),'error':type(error).__name__}), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
