"""Order number generation (§22): ``ORD-{seq}-{rand}``.

``seq`` comes from a real Postgres sequence (``order_number_seq``,
created in ``orders/migrations/0002_order_number_sequence.py``), started
at 10000. Sequences are non-transactional by design — ``nextval()`` never
returns the same value twice, even across concurrent, uncommitted
transactions — so uniqueness of the whole ``order_number`` is structural
from the ``seq`` half alone. ``rand`` exists only for the reason §22
states (obscuring the order space so public tracking, §25, isn't a
sequential walk), not for collision avoidance, and needs no retry loop.

Alphabet excludes ``0``/``O`` and ``1``/``I``/``l`` (§22, explicitly) —
31 characters, ``31**3 = 29,791`` combinations, which is the actual
friction §22 describes: not cryptographic security, just enough that the
rate limiter (§25) is the real control.
"""

from __future__ import annotations

import secrets

from django.db import connection

ORDER_NUMBER_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
ORDER_NUMBER_RAND_LENGTH = 3


def _next_seq() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('order_number_seq')")
        row = cursor.fetchone()
        assert row is not None
        return int(row[0])


def generate_order_number() -> str:
    seq = _next_seq()
    rand = "".join(secrets.choice(ORDER_NUMBER_ALPHABET) for _ in range(ORDER_NUMBER_RAND_LENGTH))
    return f"ORD-{seq}-{rand}"
