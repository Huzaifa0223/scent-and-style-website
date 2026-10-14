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
   The sizes are also surfaced on the suggestion so the page can warn.

Two hard rules sit outside the score: a gift set is only ever suggested for a
gift set (and a plain bottle never for one), and words are compared with
spaces ignored ("Nightout" = "Night Out", "9pm" = "9 PM").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Final

from .config import SUGGESTION_COUNT, SUGGESTION_MIN_SCORE

BRAND_WEIGHT: Final[float] = 0.35
NAME_WEIGHT: Final[float] = 0.55
SIZE_BONUS: Final[float] = 0.10
SIZE_MISMATCH_FACTOR: Final[float] = 0.40
BRAND_MISMATCH_FACTOR: Final[float] = 0.30
# Two spellings count as the same brand/word at or above this similarity.
SAME_WORD_RATIO: Final[float] = 0.85
# Sizes closer than this are the same size (floats parsed from text).
SIZE_EPSILON: Final[float] = 0.01
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
# "Gift Set", "Gift-Set", "GIFTSET" all squash to this.
_GIFT_SET_SQUASHED: Final[str] = "giftset"
# Bounded memo size for tokenisation / similarity ratios (a catalogue is a few
# hundred strings; this only stops unbounded growth in a long-lived process).
_CACHE_SIZE: Final[int] = 16384


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
    pos_size_ml: float | None = None
    candidate_size_ml: float | None = None

    @property
    def size_mismatch(self) -> bool:
        """Both sizes are known and they differ."""
        return (
            self.pos_size_ml is not None
            and self.candidate_size_ml is not None
            and abs(self.pos_size_ml - self.candidate_size_ml) >= SIZE_EPSILON
        )

    @property
    def size_unknown(self) -> bool:
        """At least one side has no readable size. Not a warning on the
        one-by-one page, but too uncertain to confirm in bulk."""
        return self.pos_size_ml is None or self.candidate_size_ml is None

    @property
    def size_warning(self) -> str:
        """Text for the visible row warning; empty when the sizes agree or
        either is unknown (unknown is neutral, not a warning)."""
        if not self.size_mismatch:
            return ""
        return (
            f"Size differs: POS says {format_ml(self.pos_size_ml)}, "
            f"website says {format_ml(self.candidate_size_ml)}"
        )


@lru_cache(maxsize=_CACHE_SIZE)
def _canonical(text: str) -> tuple[str, ...]:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    folded = folded.lower().replace("&", " and ")
    tokens = [t for t in _NON_ALNUM.split(folded) if t]
    return tuple(re.sub(r"([aeiou])\1+", r"\1", token) for token in tokens)


def canonical_tokens(text: str) -> list[str]:
    """Lower-case, accent-stripped alphanumeric words with doubled vowels
    collapsed (``majeed`` -> ``majed``) so common transliteration variants
    of the same word compare equal.

    Memoised: the bulk review scores every POS row against every variant, so
    the same few hundred strings are tokenised many thousands of times."""
    return list(_canonical(text))


@lru_cache(maxsize=_CACHE_SIZE)
def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def parse_size_ml(*texts: str) -> float | None:
    """First "<n> ml" found across ``texts`` ("105ml", "100 ML", "1.5 ml")."""
    for text in texts:
        match = _SIZE_RE.search(text)
        if match:
            return float(match.group(1))
    return None


def format_ml(size: float | None) -> str:
    """``100.0`` -> ``"100ml"``, ``1.5`` -> ``"1.5ml"``."""
    if size is None:
        return ""
    return f"{size:g}ml"


def _squash(tokens: list[str]) -> str:
    return "".join(tokens)


def is_gift_set(*texts: str) -> bool:
    """Whether any of ``texts`` says "gift set" (spacing/case/punctuation
    ignored). A gift set is a different product from the bottle it contains,
    so the two must never be suggested for each other."""
    return any(_GIFT_SET_SQUASHED in _squash(canonical_tokens(text)) for text in texts)


def strip_leading_brand(brand: str, name: str) -> str:
    """Drop the brand from the front of ``name`` when the POS brand column
    repeats it, as often as it repeats ("Afnan Afnan Historic Sahara" with
    brand "Afnan" -> "Historic Sahara").

    Compared with spacing and spelling variants folded, so brand "Al Majeed"
    also strips a leading "AlMajed". A name that is *only* the brand is
    returned unchanged — an empty name would match nothing.
    """
    brand_squashed = _squash(canonical_tokens(brand))
    words = name.split()
    if not brand_squashed:
        return name
    while (count := _leading_brand_words(brand_squashed, words)) and count < len(words):
        words = words[count:]
    return " ".join(words) if words else name


def _leading_brand_words(brand_squashed: str, words: list[str]) -> int:
    """How many leading words spell the brand (0 when they don't)."""
    head = ""
    for count, word in enumerate(words, start=1):
        head += _squash(canonical_tokens(word))
        if head == brand_squashed:
            return count
        if not brand_squashed.startswith(head):
            return 0
    return 0


def _brand_similarity(pos_brand: str, pos_name: str, candidate_brand: str) -> float | None:
    """1.0 same brand, 0..1 similarity otherwise, ``None`` when the
    candidate has no brand at all (nothing to compare)."""
    candidate_tokens = canonical_tokens(candidate_brand)
    if not candidate_tokens:
        return None
    pos_brand_tokens = canonical_tokens(pos_brand)
    if pos_brand_tokens:
        a, b = _squash(pos_brand_tokens), _squash(candidate_tokens)
        return 1.0 if a == b else _ratio(a, b)
    # POS row has no brand column: look for the candidate's brand in its name.
    name_squashed = _squash(canonical_tokens(pos_name))
    if _squash(candidate_tokens) in name_squashed:
        return 1.0
    return UNKNOWN_BRAND_SCORE


def _distinguishing_tokens(text: str, brand: str) -> list[str]:
    brand_tokens = set(canonical_tokens(brand))
    tokens = canonical_tokens(_SIZE_RE.sub(" ", text))  # "105ml" is size, not name
    return [t for t in tokens if t not in _NOISE_TOKENS and t not in brand_tokens]


def _same_word(left: str, right: str) -> bool:
    if left == right:
        return True
    # Cheap length bound first: the ratio can't exceed 2*min/(len+len), and
    # most token pairs are nowhere near similar.
    if 2 * min(len(left), len(right)) < SAME_WORD_RATIO * (len(left) + len(right)):
        return False
    return _ratio(left, right) >= SAME_WORD_RATIO


def _join_split_words(tokens: list[str], reference: list[str]) -> list[str]:
    """Re-join adjacent words that ``reference`` spells as one word, so
    spacing never decides a match: ``["night", "out"]`` against
    ``["nightout"]`` becomes ``["nightout"]``; ``["9", "pm"]`` against
    ``["9pm"]`` becomes ``["9pm"]``. Exact after canonicalisation — the
    spelling variants that matter already fold together there."""
    known = set(reference)
    joined: list[str] = []
    index = 0
    while index < len(tokens):
        if index + 1 < len(tokens) and tokens[index] + tokens[index + 1] in known:
            joined.append(tokens[index] + tokens[index + 1])
            index += 2
            continue
        joined.append(tokens[index])
        index += 1
    return joined


def _name_similarity(left: list[str], right: list[str]) -> float:
    """Dice coefficient over tokens, where near-identical spellings match
    and spacing is ignored."""
    if not left or not right:
        return 0.0
    left, right = _join_split_words(left, right), _join_split_words(right, left)
    remaining = list(right)
    unmatched: list[str] = []
    matched = 0
    # Exact words first: they are the vast majority and cost nothing; the
    # fuzzy comparison only has to look at what is left over.
    for token in left:
        if token in remaining:
            remaining.remove(token)
            matched += 1
        else:
            unmatched.append(token)
    for token in unmatched:
        best = next((other for other in remaining if _same_word(token, other)), None)
        if best is not None:
            matched += 1
            remaining.remove(best)
    return 2 * matched / (len(left) + len(right))


def _best_possible_score(brand_similarity: float | None) -> float:
    """Upper bound of ``assess().score`` given only the brand — lets
    ``suggest`` skip the word-by-word work for candidates that cannot reach
    ``min_score`` whatever their name (a perfect name, matching size)."""
    brand_component = 0.5 if brand_similarity is None else brand_similarity
    bound = BRAND_WEIGHT * brand_component + NAME_WEIGHT + SIZE_BONUS
    if brand_similarity is not None and brand_similarity < BRAND_MATCH_FLOOR:
        bound *= BRAND_MISMATCH_FACTOR
    return bound


def assess(
    *, pos_brand: str, pos_name: str, pos_sku: str, candidate: VariantCandidate
) -> Suggestion:
    """Score ``candidate`` against the POS product, keeping the parsed sizes
    so the page can warn when they differ.

    Gift sets are a hard gate rather than a penalty: a gift set and a plain
    bottle share every distinguishing word, so any score would be a trap.
    """
    pos_size = parse_size_ml(pos_name, pos_sku)
    candidate_size = parse_size_ml(candidate.label, candidate.product_name, candidate.sku)
    if is_gift_set(pos_name) != is_gift_set(candidate.product_name, candidate.label):
        return Suggestion(
            candidate=candidate, score=0.0, pos_size_ml=pos_size, candidate_size_ml=candidate_size
        )

    name = strip_leading_brand(pos_brand, pos_name)
    brand_similarity = _brand_similarity(pos_brand, name, candidate.brand)
    brand_component = 0.5 if brand_similarity is None else brand_similarity

    pos_tokens = _distinguishing_tokens(name, pos_brand)
    candidate_tokens = _distinguishing_tokens(candidate.product_name, candidate.brand)
    # The variant label ("100ml / Eau de Parfum") is secondary: a word from it
    # that the POS name also uses confirms the match, but a POS name that
    # simply doesn't repeat the concentration must not count against it.
    candidate_tokens += [
        token
        for token in _distinguishing_tokens(candidate.label, candidate.brand)
        if token in pos_tokens and token not in candidate_tokens
    ]
    name_component = _name_similarity(pos_tokens, candidate_tokens)

    total = BRAND_WEIGHT * brand_component + NAME_WEIGHT * name_component
    if pos_size is not None and candidate_size is not None:
        if abs(pos_size - candidate_size) < SIZE_EPSILON:
            total += SIZE_BONUS
        else:
            total *= SIZE_MISMATCH_FACTOR
    if brand_similarity is not None and brand_similarity < BRAND_MATCH_FLOOR:
        total *= BRAND_MISMATCH_FACTOR
    return Suggestion(
        candidate=candidate,
        score=round(min(max(total, 0.0), 1.0), 3),
        pos_size_ml=pos_size,
        candidate_size_ml=candidate_size,
    )


def score(*, pos_brand: str, pos_name: str, pos_sku: str, candidate: VariantCandidate) -> float:
    """0..1 likelihood that ``candidate`` is the POS product."""
    return assess(
        pos_brand=pos_brand, pos_name=pos_name, pos_sku=pos_sku, candidate=candidate
    ).score


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
    name = strip_leading_brand(pos_brand, pos_name)
    qualified = [
        suggestion
        for candidate in candidates
        if _best_possible_score(_brand_similarity(pos_brand, name, candidate.brand)) >= min_score
        and (
            suggestion := assess(
                pos_brand=pos_brand, pos_name=pos_name, pos_sku=pos_sku, candidate=candidate
            )
        ).score
        >= min_score
    ]
    qualified.sort(key=lambda s: (-s.score, s.candidate.variant_id))
    return qualified[:limit]
