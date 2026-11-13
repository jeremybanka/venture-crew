"""Synthetic test receipts, not usable as production evidence."""
from .checks import digest


def coverage_fixture(head, reviewer='warden'):
    manifest = {'version': 1, 'head_sha': head, 'units': [
        {'id': '.github/workflows/test.yml', 'path': '.github/workflows/test.yml',
         'content': 'synthetic', 'source_sha256': '0' * 64}]}
    manifest['digest'] = digest(manifest)
    return {'manifest': manifest, 'reviewer': reviewer,
            'coverage': {'.github/workflows/test.yml': {'disposition': 'required', 'runs': ['test']}},
            'runs': {'test': {'head_sha': head, 'exit_code': 0, 'command': 'synthetic-test', 'proof': 'fixture', 'environment': 'isolated test fixture'}}}
