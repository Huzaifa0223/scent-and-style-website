"""possync.matching — suggestions only; never an automatic decision."""

from __future__ import annotations

from decimal import Decimal

from possync.config import SUGGESTION_COUNT, SUGGESTION_MIN_SCORE
from possync.matching import (
    VariantCandidate,
    canonical_tokens,
    parse_size_ml,
    score,
    suggest,
)


def candidate(
    variant_id: int, brand: str, name: str, label: str = "", sku: str = ""
) -> VariantCandidate:
    return VariantCandidate(
        variant_id=variant_id,
        brand=brand,
        product_name=name,
        label=label or sku or f"v{variant_id}",
        sku=sku or f"SKU-{variant_id}",
        price=Decimal("1000.00"),
    )


def test_transliteration_variants_canonicalise_to_the_same_tokens() -> None:
    assert canonical_tokens("Al Majeed Oud") == canonical_tokens("AL MAJED  oud")
    assert canonical_tokens("Café & Co.") == ["cafe", "and", "co"]


def test_size_is_read_from_ml_in_any_spelling() -> None:
    assert parse_size_ml("Club de Nuit 105ml") == 105
    assert parse_size_ml("x", "Khamrah 100 ML EDP") == 100
    assert parse_size_ml("1.5ml sample") == 1.5
    assert parse_size_ml("Khamrah", "no size here") is None


def test_best_match_wins_on_brand_name_and_size() -> None:
    candidates = [
        candidate(1, "Armaf", "Club De Nuit Intense Man", "105ml"),
        candidate(2, "Armaf", "Club De Nuit Intense Man", "50ml"),
        candidate(3, "Armaf", "Club De Nuit Sillage", "105ml"),
        candidate(4, "Lattafa", "Khamrah", "100ml"),
    ]

    result = suggest(
        pos_brand="Armaf",
        pos_name="Armaf Club De Nuit Intense Man 105ml",
        pos_sku="Armaf-CDN-Intense",
        candidates=candidates,
    )

    assert result[0].candidate.variant_id == 1
    assert result[0].score > result[1].score
    assert 4 not in [s.candidate.variant_id for s in result]


def test_same_brand_spelled_differently_still_matches() -> None:
    candidates = [candidate(1, "Al Majed Oud", "Oud Aswad", "100ml")]

    result = suggest(
        pos_brand="Al Majeed Oud",
        pos_name="Oud Aswad 100ml",
        pos_sku="AMO-1",
        candidates=candidates,
    )

    assert [s.candidate.variant_id for s in result] == [1]
    assert result[0].score >= 0.9


def test_brand_written_as_one_word_matches() -> None:
    candidates = [candidate(1, "Al Majed Oud", "Oud Aswad", "100ml")]

    result = suggest(
        pos_brand="AlMajed Oud", pos_name="Oud Aswad 100ml", pos_sku="X", candidates=candidates
    )

    assert result and result[0].score >= 0.9


def test_a_different_size_scores_far_below_the_same_size() -> None:
    same = candidate(1, "Armaf", "Club De Nuit Intense Man", "105ml")
    other = candidate(2, "Armaf", "Club De Nuit Intense Man", "50ml")
    kwargs = {"pos_brand": "Armaf", "pos_name": "Club De Nuit Intense Man 105ml", "pos_sku": "x"}

    assert score(candidate=same, **kwargs) > 2 * score(candidate=other, **kwargs)


def test_unknown_size_on_either_side_is_neutral_not_a_penalty() -> None:
    sized = candidate(1, "Armaf", "Club De Nuit Intense Man", "105ml")
    unsized = candidate(2, "Armaf", "Club De Nuit Intense Man", "Eau de Parfum")
    kwargs = {"pos_brand": "Armaf", "pos_name": "Club De Nuit Intense Man", "pos_sku": "x"}

    assert score(candidate=unsized, **kwargs) >= 0.85
    assert score(candidate=sized, **kwargs) >= 0.85


def test_a_different_brand_with_the_same_product_name_is_not_suggested() -> None:
    candidates = [candidate(1, "Lattafa", "Khamrah", "100ml")]

    result = suggest(
        pos_brand="Armaf", pos_name="Khamrah 100ml", pos_sku="x", candidates=candidates
    )

    assert result == []


def test_pos_row_without_a_brand_uses_the_name() -> None:
    candidates = [
        candidate(1, "Armaf", "Club De Nuit Intense Man", "105ml"),
        candidate(2, "Rasasi", "Club De Nuit Intense Man", "105ml"),
    ]

    result = suggest(
        pos_brand="",
        pos_name="Armaf Club De Nuit Intense Man 105ml",
        pos_sku="x",
        candidates=candidates,
    )

    assert result[0].candidate.variant_id == 1


def test_at_most_three_best_first_and_stable_on_ties() -> None:
    candidates = [candidate(i, "Armaf", "Tres", "100ml") for i in (9, 3, 7, 5, 1)]

    result = suggest(
        pos_brand="Armaf", pos_name="Armaf Tres 100ml", pos_sku="x", candidates=candidates
    )

    assert len(result) == SUGGESTION_COUNT
    assert [s.candidate.variant_id for s in result] == [1, 3, 5]  # equal scores: lowest id first


def test_nothing_below_the_minimum_score_is_returned() -> None:
    candidates = [candidate(1, "Zara", "Something Else Entirely", "30ml")]

    result = suggest(
        pos_brand="Armaf", pos_name="Club De Nuit 105ml", pos_sku="x", candidates=candidates
    )

    assert result == []
    assert all(s.score >= SUGGESTION_MIN_SCORE for s in result)


def test_no_candidates_means_no_suggestions() -> None:
    assert suggest(pos_brand="A", pos_name="B", pos_sku="c", candidates=[]) == []
