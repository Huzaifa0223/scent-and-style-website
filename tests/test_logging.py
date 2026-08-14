"""§41's "error monitoring hook" (roadmap Stage 13). Regression test for
a real bug this stage fixed: config/settings/base.py's own LOGGING dict
was silently dropping Django's built-in "django" -> mail_admins wiring
by redefining the "django" logger's handler list without re-listing
"mail_admins" — confirmed via `logging.getLogger("django").handlers`
showing only a console StreamHandler before the fix.
"""

from __future__ import annotations

import logging

from django.utils.log import AdminEmailHandler, RequireDebugFalse


def test_the_django_logger_still_has_a_mail_admins_handler() -> None:
    handlers = logging.getLogger("django").handlers

    admin_handlers = [h for h in handlers if isinstance(h, AdminEmailHandler)]
    assert len(admin_handlers) == 1


def test_the_mail_admins_handler_only_fires_when_debug_is_false() -> None:
    (admin_handler,) = [
        h for h in logging.getLogger("django").handlers if isinstance(h, AdminEmailHandler)
    ]

    assert any(isinstance(f, RequireDebugFalse) for f in admin_handler.filters)
