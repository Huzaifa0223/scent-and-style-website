from __future__ import annotations

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base adding creation/modification timestamps.

    Every domain model in this project inherits from this rather than
    declaring its own ``created_at``/``updated_at`` pair, so audit and
    ordering logic can rely on both fields existing everywhere.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class RateLimitScope(models.TextChoices):
    """Which surface a ``RateLimitAttempt`` row belongs to (§41, roadmap
    Stage 13). A flat enum rather than one table per surface — the three
    scopes here share one sliding-window mechanism (``core.ratelimit``)
    and differ only in their thresholds (``core/config.py``)."""

    LOGIN = "login", "Login"
    CHECKOUT = "checkout", "Checkout"
    SEARCH = "search", "Search"


class RateLimitAttempt(TimeStampedModel):
    """Audit row for one rate-limited request, shared by login, checkout,
    and search (§41, roadmap Stage 13) — the same DB-backed
    sliding-window design ``orders.OrderTrackingAttempt`` established in
    Stage 11, generalised across scopes rather than duplicated a third
    and fourth time. Order tracking itself deliberately keeps its own
    dedicated model rather than migrating onto this one: it already
    shipped, is covered by its own tests, and rewriting working Stage 11
    code to share a table one stage later would be churn a hardening
    pass shouldn't introduce (recorded in specs/state.md's Stage 13
    notes).

    Why a DB table and not ``cache.incr()``: this project's cache is the
    database cache backend (no Redis, per CLAUDE.md), whose ``incr()`` is
    a plain get-then-set with no row lock — it races under concurrent
    requests from the same IP. A ``COUNT`` query has the same
    theoretical race in principle, but the window for two requests from
    one IP landing in the same instant is far narrower in practice, and
    the failure mode (a few extra requests let through) is bounded and
    non-catastrophic.
    """

    ip_address = models.GenericIPAddressField()
    scope = models.CharField(max_length=20, choices=RateLimitScope.choices)
    succeeded = models.BooleanField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["scope", "ip_address", "created_at"])]

    def __str__(self) -> str:
        outcome = "succeeded" if self.succeeded else "failed"
        return f"{self.get_scope_display()} {outcome} from {self.ip_address}"
