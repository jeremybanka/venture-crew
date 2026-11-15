"""Limit a root-checkout native hook to one authorized task worktree.

Codex inherits root-checkout hook definitions in linked worktrees. This scope
filter prevents those shared definitions changing unrelated sessions. It is not
an authentication boundary against hostile local code.
"""
import argparse
import io
import json
import os
from pathlib import Path
import sys
from . import hook


def applies(payload, scope, session_name, environ):
    # A managed task remains gated even if a malformed event omits its cwd.
    if environ.get('OPENRIG_SESSION_NAME') == session_name:
        return True
    if not isinstance(payload, dict) or not isinstance(payload.get('cwd'), str):
        return False
    cwd = Path(payload['cwd'])
    if not cwd.is_absolute():
        return False
    try:
        cwd.resolve().relative_to(scope.resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--session-name', required=True)
    args, rest = parser.parse_known_args()
    scope = Path(args.scope)
    if not scope.is_absolute() or not args.session_name.strip():
        raise ValueError('absolute_scope_and_session_required')
    raw = sys.stdin.read(1000001)
    try:
        payload = json.loads(raw) if len(raw) <= 1000000 else None
    except ValueError:
        payload = None
    if not applies(payload, scope, args.session_name, os.environ):
        print('{}')
        return 0
    sys.stdin = io.StringIO(raw)
    sys.argv = [sys.argv[0], *rest]
    return hook.main()


if __name__ == '__main__':
    raise SystemExit(main())
