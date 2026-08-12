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
