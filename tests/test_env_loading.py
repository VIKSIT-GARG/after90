"""Explicit local configuration must never evaluate shell text or leak values."""

import json
import os
import subprocess
import sys

import pytest

from backend.matchlens.env import load_environment


def test_literal_values_and_process_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("AFTER90_ENV_TEST_EXISTING", "process")
    monkeypatch.delenv("AFTER90_ENV_TEST_LITERAL", raising=False)

    path = tmp_path / ".env"
    marker = tmp_path / "must-not-exist"

    # Use forward slashes to avoid Windows backslash escape sequences.
    value = f'$(touch {marker.as_posix()}) $HOME ${{HOME}}'

    path.write_text(
        f'AFTER90_ENV_TEST_EXISTING=file\n'
        f'AFTER90_ENV_TEST_LITERAL="{value}"\n'
    )

    load_environment(path)

    assert os.environ["AFTER90_ENV_TEST_EXISTING"] == "process"
    assert os.environ["AFTER90_ENV_TEST_LITERAL"] == value
    assert not marker.exists()


def test_missing_file_preserves_fallback(tmp_path):
    load_environment(tmp_path / "absent.env")


def test_invalid_file_is_atomic_and_sanitized(tmp_path, monkeypatch):
    monkeypatch.delenv("AFTER90_ENV_TEST_FIRST", raising=False)

    path = tmp_path / ".env"

    path.write_text(
        'AFTER90_ENV_TEST_FIRST=private-fake-secret\n'
        'BROKEN="private-fake-secret\n'
    )

    with pytest.raises(
        ValueError,
        match="Could not load environment file"
    ) as error:
        load_environment(path)

    assert "private-fake-secret" not in str(error.value)
    assert "AFTER90_ENV_TEST_FIRST" not in os.environ


def test_cli_loads_fresh_child_without_shell(tmp_path):
    path = tmp_path / ".env"

    path.write_text(
        "AFTER90_ENV_TEST_SINGLE='literal $HOME'\n"
        'AFTER90_ENV_TEST_DOUBLE="literal ${HOME}"\n'
    )

    code = (
        'import os,json; '
        'print(json.dumps(['
        'os.environ.get("AFTER90_ENV_TEST_SINGLE")=="literal $HOME",'
        'os.environ.get("AFTER90_ENV_TEST_DOUBLE")=="literal ${HOME}"'
        ']))'
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.matchlens.env",
            "--env-file",
            str(path),
            "--run",
            sys.executable,
            "-c",
            code,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(result.stdout) == [True, True]
    assert not result.stderr


def test_cli_failure_does_not_print_values(tmp_path):
    path = tmp_path / ".env"

    path.write_text('BAD="fake-private-value\n')

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.matchlens.env",
            "--env-file",
            str(path),
            "--run",
            sys.executable,
            "-c",
            'raise RuntimeError("must not run")',
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "fake-private-value" not in result.stderr
    assert "must not run" not in result.stderr


def test_import_does_not_load_environment(tmp_path):
    path = tmp_path / ".env"

    path.write_text(
        "AFTER90_ENV_TEST_IMPORT=must-not-load\n"
    )

    code = (
        'import os; '
        'from backend.matchlens import env; '
        'assert "AFTER90_ENV_TEST_IMPORT" not in os.environ'
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0