"""Помощники тестов этапа 0: sys.path на skill/scripts + запуск CLI (spec-etap0.md)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "skill" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def run_cli():
    """Запуск CLI-скрипта: subprocess с utf-8 и PYTHONUTF8=1.

    Возвращает CompletedProcess (text=True, encoding="utf-8").
    env_extra — дополнения к окружению (пустая строка в значении — валидный кейс).
    """

    def _run(script: str, *args, env_extra: dict | None = None):
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script)] + [str(a) for a in args],
            capture_output=True, text=True, encoding="utf-8", env=env)

    return _run


@pytest.fixture
def journal(run_cli):
    """journal.py с изолированным --root ДО подкоманды (контракт spec-etap0.md)."""

    def _j(*args, root):
        return run_cli("journal.py", "--root", root, *args)

    return _j
