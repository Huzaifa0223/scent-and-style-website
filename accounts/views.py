from __future__ import annotations

from typing import Any

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView

_FIELD_CSS = "mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"


class PortalAuthenticationForm(AuthenticationForm):
    """Adds Tailwind classes to the default auth form's widgets — the form
    itself (validation, error messages) is stock ``AuthenticationForm``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": _FIELD_CSS, "autofocus": True})
        self.fields["password"].widget.attrs.update({"class": _FIELD_CSS})


class PortalLoginView(LoginView):
    template_name = "accounts/login.html"
    form_class = PortalAuthenticationForm
    redirect_authenticated_user = True
