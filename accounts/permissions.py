"""Shared by accounts/migrations/0001_create_staff_group.py and
accounts/apps.py's post_migrate handler — both need the exact same "which
permissions does Staff get" logic, and letting the two drift apart would
silently change what a fresh migrate grants vs. what a post-flush resync
grants.

Only the *criteria* is shared here, not model classes: a migration's
historical ``Permission`` model and a signal receiver's live one are
different Python classes, but both are ordinary ``QuerySet``s, and this
function only calls ``.filter()``/``.exclude()`` against stable Django
framework fields (``content_type__app_label``, ``codename``) — not this
project's own model shape. That's what makes importing this into a
migration safe despite the usual "migrations shouldn't depend on
application code that can change shape" caution.
"""

from __future__ import annotations

from typing import Any, TypeVar

from django.db.models import QuerySet

STAFF_GROUP_NAME = "Staff"

_STAFF_PERMISSION_APP_LABELS = ("catalog",)
_EXCLUDED_PERMISSION_PREFIX = "delete_"

_QuerySetT = TypeVar("_QuerySetT", bound=QuerySet[Any])


def staff_permissions(all_permissions: _QuerySetT) -> _QuerySetT:
    """Filter an unfiltered ``Permission`` queryset down to what the Staff
    group should hold: view/add/change (never delete) on the listed apps
    only. Deliberately narrow for Stage 3 — requirements §32's fuller
    orders/inventory/customers scope arrives in roadmap Stage 17, which
    extends ``_STAFF_PERMISSION_APP_LABELS`` rather than creating a new
    group."""
    return all_permissions.filter(content_type__app_label__in=_STAFF_PERMISSION_APP_LABELS).exclude(
        codename__startswith=_EXCLUDED_PERMISSION_PREFIX
    )
