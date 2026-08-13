"""Roadmap Stage 9 gate 3: "No module outside notifications/ constructs a
WhatsApp string." CLAUDE.md's own trap note says the same thing more
generally: "Nothing outside notifications/ and payments/ knows WhatsApp
exists." Automated the same way Stage 5 automated "no view imports
PostgresSearchBackend directly" and Stage 2 automated its own
no-float-on-money-fields grep — the forbidden domain substring below,
found anywhere outside `notifications/`, means something built a
WhatsApp link (or is about to) without going through
`notifications.whatsapp.channel.WhatsAppLinkChannel`.

Scoped to `.py` and template files only — `specs/`, `docs/`, and this
file's own prose legitimately discuss the concept without constructing
one. The forbidden substring is spelled out only in the constant below,
deliberately not repeated elsewhere in this docstring: an earlier
sibling grep in `tests/` has no such self-discipline (it only excludes
*itself* from its own scan, not other files that merely *name* its
target substring in prose) and this file's own first draft tripped it.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_SUBSTRING = "wa.me"
EXCLUDED_DIR_NAMES = {".venv", ".git", "node_modules", "static", "specs", "docs", "tools"}


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.py", "*.html"):
        for path in PROJECT_ROOT.rglob(pattern):
            if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
                continue
            if "notifications" in path.parts:
                continue
            if path == Path(__file__).resolve():
                continue
            files.append(path)
    return files


def test_no_wa_me_string_outside_notifications() -> None:
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _scanned_files()
        if FORBIDDEN_SUBSTRING in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"WhatsApp string construction found outside notifications/: {offenders}"
    )
