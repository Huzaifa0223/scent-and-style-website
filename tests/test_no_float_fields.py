"""CLAUDE.md: "No FloatField on any monetary or quantity field anywhere in
the project" — `grep -rn "FloatField" .` must return nothing outside
migrations of third-party apps (roadmap Stage 2 acceptance gate 7). This
makes that check automated and repo-wide instead of a one-off manual grep.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories that are never our own application code.
EXCLUDED_DIR_NAMES = {".venv", ".git", "migrations", "node_modules", "tools", "static"}


def _our_python_files() -> list[Path]:
    files = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if path == Path(__file__).resolve():
            continue  # this file necessarily mentions "FloatField" itself
        files.append(path)
    return files


def test_no_float_field_anywhere_in_application_code() -> None:
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _our_python_files()
        if "FloatField" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"FloatField found outside migrations: {offenders}"
