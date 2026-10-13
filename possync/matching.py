"""Suggest which website variant a POS product probably is.

Pure functions (no database): callers hand in plain values, which keeps the
scoring easy to test against realistic names. Suggestions only — nothing
here ever confirms a mapping; a human picks.

Signals, in order of weight:

1. **Brand** — compared after canonicalisation, so "Al Majeed Oud" and
   "Al Majed Oud" (or "AlMajed") are the same brand.
2. **Name tokens** — overlap of the distinguishing words once brand, size
   and filler words are removed.
3. **Size in ml** — a matching "105ml" is a small bonus; *both* sizes known
   and different is a strong penalty, because a 50ml and a 100ml bottle are
   different variants and the wrong one would silently get the wrong stock.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Final

from .config import SUGGESTION_COUNT, SUGGESTION_MIN_SCORE

BRAND_WEIGHT: Final[float] = 0.35
NAME_WEIGHT: Final[float] = 0.55
SIZE_BONUS: Final[float] = 0.10
SIZE_MISMATCH_FACTOR: Final[float] = 0.40
BRAND_MISMATCH_FACTOR: Final[float] = 0.30
# Two spellings count as the same brand/word at or above this similarity.
SAME_WORD_RATIO: Final[float] = 0.85
# Brand similarity below this, with both brands known, is "a different brand".
BRAND_MATCH_FLOOR: Final[float] = 0.60
# When the POS row has no brand and the name doesn't contain the candidate's.
UNKNOWN_BRAND_SCORE: Final[float] = 0.40

# Filler that appears on one side only and says nothing about identity.
# Concentration words (edp, edt, parfum, cologne, intense, …) are *kept*:
# they distinguish products.
_NOISE_TOKENS: Final[frozenset[str]] = frozenset(
    {"the", "and", "by", "de", "for", "spray", "perfume", "ml"}
)
_SIZE_RE: Final = re.compile(r"(\d+(?:\.\d+)?)\s*ml\b", re.IGNORECASE)
_NON_ALNUM: Final = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class VariantCandidate:
    """A website variant that could be the match (already unmapped)."""

    variant_id: int
    brand: str
    product_name: str
    label: str  # e.g. "100ml / Eau de Parfum"
    sku: str
    price: Decimal


@dataclass(frozen=True)
class Suggestion:
    candidate: VariantCandidate
    score: float  # 0..1


def canonical_tokens(text: str) -> list[str]:
    """Lower-case, accent-stripped alphanumeric words with doubled vowels
    collapsed (``majeed`` -> ``majed``) so common transliteration variants
    of the same word compare equal."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    folded = folded.lower().replace("&", " and ")
    tokens = [t for t in _NON_ALNUM.split(folded) if t]
    return [re.sub(r"([aeiou])\1+", r"\1", token) for token in tokens]


def parse_size_ml(*texts: str) -> float | None:
    """First "<n> ml" found across ``texts`` ("105ml", "100 ML", "1.5 ml")."""
    for text in texts:
        match = _SIZE_RE.search(text)
        if match:
            return float(match.group(1))
    return None


def _squash(tokens: list[str]) -> str:
    return "".join(tokens)


def _brand_similarity(pos_brand: str, pos_name: str, candidate_brand: str) -> float | None:
    """1.0 same brand, 0..1 similarity otherwise, ``None`` when the
    candidate has no brand at all (nothing to compare)."""
    candidate_tokens = canonical_tokens(candidate_brand)
    if not candidate_tokens:
        return None
    pos_brand_tokens = canonical_tokens(pos_brand)
    if pos_brand_tokens:
        a, b = _squash(pos_brand_tokens), _squash(candidate_tokens)
        return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()
    # POS row has no brand column: look for the candidate's brand in its name.
    name_squashed = _squash(canonical_tokens(pos_name))
    if _squash(candidate_tokens) in name_squashed:
        return 1.0
    return UNKNOWN_BRAND_SCORE


def _distinguishing_tokens(text: str, brand: str) -> list[str]:
    brand_tokens = set(canonical_tokens(brand))
    tokens = canonical_tokens(_SIZE_RE.sub(" ", text))  # "105ml" is size, not name
    return [t for t in tokens if t not in _NOISE_TOKENS and t not in brand_tokens]


def _name_similarity(left: list[str], right: list[str]) -> float:
    """Dice coefficient over tokens, where near-identical spellings match."""
    if not left or not right:
        return 0.0
    remaining = list(right)
    matched = 0
    for token in left:
        best = next(
            (
                other
                for other in remaining
                if other == token or SequenceMatcher(None, token, other).ratio() >= SAME_WORD_RATIO
            ),
            None,
        )
        if best is not None:
            matched += 1
            remaining.remove(best)
    return 2 * matched / (len(left) + len(right))


def score(*, pos_brand: str, pos_name: str, pos_sku: str, candidate: VariantCandidate) -> float:
    """0..1 likelihood that ``candidate`` is the POS product."""
    brand_similarity = _brand_similarity(pos_brand, pos_name, candidate.brand)
    brand_component = 0.5 if brand_similarity is None else brand_similarity

    pos_tokens = _distinguishing_tokens(pos_name, pos_brand)
    candidate_tokens = _distinguishing_tokens(candidate.product_name, candidate.brand)
    # The variant label ("100ml / Eau de Parfum") is secondary: a word from it
    # that the POS name also uses confirms the match, but a POS name that
    # simply doesn't repeat the concentration must not count against it.
    candidate_tokens += [
        token
        for token in _distinguishing_tokens(candidate.label, candidate.brand)
        if token in pos_tokens and token not in candidate_tokens
    ]
    pos_size = parse_size_ml(pos_name, pos_sku)
    candidate_size = parse_size_ml(candidate.label, candidate.product_name, candidate.sku)
    name_component = _name_similarity(pos_tokens, candidate_tokens)

    total = BRAND_WEIGHT * brand_component + NAME_WEIGHT * name_component
    if pos_size is not None and candidate_size is not None:
        if abs(pos_size - candidate_size) < 0.01:
            total += SIZE_BONUS
        else:
            total *= SIZE_MISMATCH_FACTOR
    if brand_similarity is not None and brand_similarity < BRAND_MATCH_FLOOR:
        total *= BRAND_MISMATCH_FACTOR
    return round(min(max(total, 0.0), 1.0), 3)


def suggest(
    *,
    pos_brand: str,
    pos_name: str,
    pos_sku: str,
    candidates: list[VariantCandidate],
    limit: int = SUGGESTION_COUNT,
    min_score: float = SUGGESTION_MIN_SCORE,
) -> list[Suggestion]:
    """The best ``limit`` candidates scoring at least ``min_score``, best
    first; ties break on variant id so the order is stable between page
    loads."""
    scored = [
        Suggestion(
            candidate=candidate,
            score=score(
                pos_brand=pos_brand, pos_name=pos_name, pos_sku=pos_sku, candidate=candidate
            ),
        )
        for candidate in candidates
    ]
    qualified = [s for s in scored if s.score >= min_score]
    qualified.sort(key=lambda s: (-s.score, s.candidate.variant_id))
    return qualified[:limit]
