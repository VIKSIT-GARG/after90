#!/usr/bin/env python3
"""Configure a private local Foundry connection; never echo or upload the key.

Configuration is local only. --verify explicitly makes live model requests via
After90's production evaluator and can incur usage charges.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values, set_key
from dotenv.parser import parse_stream
from backend.matchlens.provider import endpoint_allowed

NAMES = ('FOUNDRY_RESPONSES_URL', 'FOUNDRY_MODEL', 'FOUNDRY_API_KEY')


def responses_endpoint(value: str) -> str:
    """Accept resource/base/Responses URLs; never accept a project or foreign URL."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Use the HTTPS Azure resource endpoint, not the project endpoint.')
    try:
        parsed = urlsplit(value.strip())
        if parsed.path not in ('', '/', '/openai/v1', '/openai/v1/', '/openai/v1/responses'):
            raise ValueError
        endpoint = urlunsplit(parsed._replace(path='/openai/v1/responses'))
        if not endpoint_allowed(endpoint):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Use the HTTPS Azure resource endpoint, not the project endpoint.') from None
    return endpoint


def _values(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError('The environment file must not be a symbolic link.')
    if not path.exists():
        return {}
    try:
        with path.open(encoding='utf-8') as stream:
            if any(binding.error or (binding.key is not None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', binding.key))
                   for binding in parse_stream(stream)):
                raise ValueError
        return dict(dotenv_values(path, interpolate=False))
    except (OSError, UnicodeError, ValueError):
        raise ValueError('The environment file could not be read; check its syntax and permissions.') from None


def configure(endpoint: str, model: str, key: str, path: Path = ROOT / '.env', *, replace: bool = False) -> None:
    endpoint = responses_endpoint(endpoint)
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', model):
        raise ValueError('Use the deployed model name from Foundry, without spaces.')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{8,4096}', key):
        raise ValueError('Enter a resource API key as a single line.')
    path = Path(path)
    existing = _values(path)
    if not replace and any(existing.get(name) for name in NAMES):
        raise ValueError('A connection already exists. Use --replace to update it.')
    temporary = None
    try:
        # A same-directory private temporary file makes the final write atomic.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.after90-env-', delete=False) as stream:
            temporary = Path(stream.name)
            if path.exists():
                stream.write(path.read_text(encoding='utf-8'))
        for name, value in zip(NAMES, (endpoint, model, key)):
            set_key(temporary, name, value, quote_mode='always')
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except (OSError, UnicodeError):
        raise ValueError('The private environment file could not be saved.') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def status(path: Path, environment: dict | None = None) -> dict:
    values = _values(path)
    env = os.environ if environment is None else environment
    config = {name: env.get(name, values.get(name) or '') for name in NAMES}
    present = {name: bool(config[name]) for name in NAMES}
    endpoint_valid = endpoint_allowed(config[NAMES[0]])
    model_valid = bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', config[NAMES[1]]))
    return {'configured': all(present.values()) and endpoint_valid and model_valid,
            'presence': present, 'endpoint_valid': endpoint_valid,
            'live_verified': False, 'next': 'Run explicit live evaluation to verify the real deployment.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--check', action='store_true', help='Check configuration without showing values or making model calls.')
    parser.add_argument('--verify', action='store_true', help='Run all-context live evaluation; incurs model usage.')
    args = parser.parse_args()
    try:
        if not args.check:
            configure(input('Azure resource endpoint: ').strip(), input('Deployed model name: ').strip(),
                      getpass.getpass('Resource API key (hidden): ').strip(), args.env_file, replace=args.replace)
            print('Private Foundry configuration saved. Existing process variables still take precedence.')
        report = status(args.env_file)
        print(json.dumps(report, indent=2))
        if not report['configured']:
            return 2
        if args.verify:
            env = {**{k: v for k, v in _values(args.env_file).items() if v is not None}, **os.environ}
            for script in ('evaluate_live_ai.py', 'evaluate_copilot.py'):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--live', '--require-foundry'],
                                        cwd=ROOT, env=env, check=False)
                if result.returncode:
                    return result.returncode
            return 0
        return 0
    except (ValueError, EOFError, KeyboardInterrupt) as error:
        print(str(error) if isinstance(error, ValueError) else 'Configuration cancelled.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
