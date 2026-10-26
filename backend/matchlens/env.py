"""Explicit, non-interpolating local environment loading; importing does nothing."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

from dotenv import dotenv_values
from dotenv.parser import parse_stream

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / '.env'


def load_environment(path: str | Path = DEFAULT_ENV_FILE) -> None:
    """Load a dotenv file atomically. Existing process values always win."""
    path = Path(path)
    if not path.exists():
        return
    try:
        with path.open(encoding='utf-8') as stream:
            bindings = list(parse_stream(stream))
        if any(binding.error or (binding.key is not None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', binding.key)) for binding in bindings):
            raise ValueError('Invalid environment file syntax')
        values = dotenv_values(path, interpolate=False)
    except (OSError, UnicodeError, ValueError):
        raise ValueError('Could not load environment file; check its syntax and permissions') from None
    for key, value in values.items():
        if value is not None:
            os.environ.setdefault(key, value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument('--run', nargs=argparse.REMAINDER, required=True, metavar='COMMAND')
    args = parser.parse_args()
    if not args.run:
        parser.error('--run requires a command')
    try:
        load_environment(args.env_file)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        os.execvpe(args.run[0], args.run, os.environ)
    except OSError:
        print('Could not start configured command', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
