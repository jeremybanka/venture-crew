"""Build a launch-local quota plugin; never install settings or launch a model.

Use the resulting directory as an OpenRig member's plugin_dirs entry. Native
loading and closed/admitted behavior still require verification before activation.
"""
import json
from pathlib import Path
import re
import shlex
from .prepare_hooks import prepare


def build(*, root, python, db, seat, session):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+', session):
        raise ValueError('exact_native_session_required')
    fragment = prepare('claude', seat, root, python, db, enable_claude=True)['fragment']
    for groups in fragment['hooks'].values():
        for group in groups:
            for handler in group['hooks']:
                handler['command'] = (
                    'if [ "${OPENRIG_SESSION_NAME-}" = ' + shlex.quote(session)
                    + ' ]; then ' + handler['command']
                    + '; else printf "{}\\n"; fi')
    return {
        '.claude-plugin/plugin.json': {
            'name': 'venture-quota-' + seat.replace('.', '-'),
            'version': '0.1.0',
            'description': 'Launch-local independent provider quota admission',
            'hooks': './hooks/claude.json',
        },
        'hooks/claude.json': fragment,
    }


def write_plugin(directory, **kwargs):
    """Create a NEW private artifact only; existing artifacts require review."""
    target = Path(directory)
    if not target.is_absolute() or any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('safe_absolute_artifact_directory_required')
    content = build(**kwargs)
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, data in content.items():
        file = target / name
        file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        file.write_text(json.dumps(data, indent=2) + '\n')
    return str(target)
