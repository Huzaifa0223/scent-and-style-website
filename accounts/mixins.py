"""Portal access control — one mixin, used by every portal view.

CLAUDE.md's app boundaries put "auth, roles, permissions" in ``accounts``;
``portal`` imports this rather than each view rolling its own check, which is
what the roadmap Stage 3 trap ("never by hiding a nav link") is guarding
against — a check that only exists in a template can be forgotten on a new
view, a check baked into a shared mixin cannot.
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy


class PortalPermissionRequiredMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Composes Django's own auth mixins — no custom permission framework
    (requirements §32). Every concrete view must set ``permission_required``;
    leaving it unset raises ``ImproperlyConfigured``, which is deliberate —
    it forces every portal view to declare its own requirement rather than
    inheriting a default that might be wrong for it.

    Anonymous visitors redirect to login. An authenticated user lacking the
    permission gets ``PermissionDenied`` (403), not a redirect loop back to
    a login page they're already past — that's ``AccessMixin.
    handle_no_permission``'s own behavior (it raises whenever the user is
    already authenticated, regardless of ``raise_exception``), not something
    this class has to implement itself. Superusers — the Owner, per §32 —
    bypass every permission check via Django's ``ModelBackend``.
    """

    login_url = reverse_lazy("accounts:login")
