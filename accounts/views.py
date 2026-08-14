from __future__ import annotations

from typing import Any

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from core import ratelimit
from core.models import RateLimitScope
from core.ratelimit import LOGIN_RATE_LIMIT_POLICY

_FIELD_CSS = "mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"


class PortalAuthenticationForm(AuthenticationForm):
    """Adds Tailwind classes to the default auth form's widgets — the form
    itself (validation, error messages) is stock ``AuthenticationForm``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": _FIELD_CSS, "autofocus": True})
        self.fields["password"].widget.attrs.update({"class": _FIELD_CSS})


class PortalLoginView(LoginView):
    """§41: "rate limiting on login". Checked before ``AuthenticationForm``
    ever validates credentials — same ordering as every other rate limiter
    in this project (``orders.tracking``, ``core.ratelimit``'s other two
    callers): a locked-out or throttled request never reaches password
    verification at all.
    """

    template_name = "accounts/login.html"
    form_class = PortalAuthenticationForm
    redirect_authenticated_user = True

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        ip_address = ratelimit.client_ip(request)
        try:
            ratelimit.check_rate_limit(
                scope=RateLimitScope.LOGIN, ip_address=ip_address, policy=LOGIN_RATE_LIMIT_POLICY
            )
        except ratelimit.LockedOutError:
            return render(
                request,
                self.template_name,
                {"form": self.get_form(), "locked_out": True},
                status=429,
            )
        except ratelimit.RateLimitedError:
            return render(
                request,
                self.template_name,
                {"form": self.get_form(), "rate_limited": True},
                status=429,
            )
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: AuthenticationForm) -> HttpResponse:
        ratelimit.record_attempt(
            scope=RateLimitScope.LOGIN, ip_address=ratelimit.client_ip(self.request), succeeded=True
        )
        return super().form_valid(form)

    def form_invalid(self, form: AuthenticationForm) -> HttpResponse:
        ratelimit.record_attempt(
            scope=RateLimitScope.LOGIN,
            ip_address=ratelimit.client_ip(self.request),
            succeeded=False,
        )
        return super().form_invalid(form)
