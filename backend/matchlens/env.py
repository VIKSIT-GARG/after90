"""Explicit, non-interpolating local environment loading; importing does nothing."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from dotenv import dotenv_values
from dotenv.parser import parse_stream


DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_environment(path: str | Path = DEFAULT_ENV_FILE) -> None:
    """Load a dotenv file atomically. Existing process values always win."""

    path = Path(path)

    if not path.exists():
        return

    try:
        # Parse and validate the environment file.
        with path.open(encoding="utf-8") as stream:
            bindings = list(parse_stream(stream))

        # Reject malformed syntax and invalid environment variable names.
        for binding in bindings:
            if binding.error:
                raise ValueError("Invalid environment file syntax")

            if binding.key is not None:
                if not re.fullmatch(
                    r"[A-Za-z_][A-Za-z0-9_]*",
                    binding.key,
                ):
                    raise ValueError("Invalid environment variable name")

        # Read values without interpolating environment variables.
        values = dotenv_values(
            path,
            interpolate=False,
        )

    except (OSError, UnicodeError, ValueError):
        raise ValueError(
            "Could not load environment file; check its syntax and permissions"
        ) from None

    # Existing process environment variables always take precedence.
    for key, value in values.items():
        if value is not None:
            os.environ.setdefault(key, value)


def main() -> int:
    """Load environment variables and execute a command."""

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
    )

    parser.add_argument(
        "--run",
        nargs=argparse.REMAINDER,
        required=True,
        metavar="COMMAND",
    )

    args = parser.parse_args()

    if not args.run:
        parser.error("--run requires a command")

    try:
        load_environment(args.env_file)

    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    try:
        if os.name == "nt":
            # Windows: launch a child process without using a shell.
            result = subprocess.run(
                args.run,
                env=os.environ,
                check=False,
            )

            return result.returncode

        # Linux/macOS: replace the current process.
        os.execvpe(
            args.run[0],
            args.run,
            os.environ,
        )

    except OSError:
        print(
            "Could not start configured command",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())