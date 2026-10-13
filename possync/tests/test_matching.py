"""possync.matching — suggestions only; never an automatic decision."""

from __future__ import annotations

from decimal import Decimal

from possync.config import SUGGESTION_COUNT, SUGGESTION_MIN_SCORE
from possync.matching import (
    VariantCandidate,
    canonical_tokens,
    is_gift_set,
    parse_size_ml,
    score,
    strip_leading_brand,
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


# --- gift sets ---------------------------------------------------------------


def test_gift_set_detection_ignores_spacing_case_and_punctuation() -> None:
    assert is_gift_set("Afnan 9pm Gift Set")
    assert is_gift_set("Afnan 9PM GIFTSET 100ml")
    assert is_gift_set("9pm gift-set")
    assert not is_gift_set("Afnan 9pm 100ml")


def test_a_gift_set_pos_row_is_only_matched_to_gift_set_variants() -> None:
    candidates = [
        candidate(1, "Afnan", "9pm", "100ml"),
        candidate(2, "Afnan", "9pm Gift Set", "100ml"),
    ]

    result = suggest(
        pos_brand="Afnan", pos_name="9pm Gift Set 100ml", pos_sku="x", candidates=candidates
    )

    assert [s.candidate.variant_id for s in result] == [2]


def test_a_plain_bottle_is_never_matched_to_a_gift_set_variant() -> None:
    candidates = [candidate(2, "Afnan", "9pm Gift Set", "100ml")]

    result = suggest(pos_brand="Afnan", pos_name="9pm 100ml", pos_sku="x", candidates=candidates)

    assert result == []
    assert score(pos_brand="Afnan", pos_name="9pm 100ml", pos_sku="x", candidate=candidates[0]) == 0


def test_gift_set_in_the_variant_label_counts_too() -> None:
    candidates = [candidate(1, "Afnan", "9pm", "Gift Set")]

    assert suggest(pos_brand="Afnan", pos_name="9pm", pos_sku="x", candidates=candidates) == []
    assert suggest(pos_brand="Afnan", pos_name="9pm Giftset", pos_sku="x", candidates=candidates)


# --- spacing and spelling ----------------------------------------------------


def test_spacing_inside_a_name_does_not_matter() -> None:
    candidates = [candidate(1, "Armaf", "Night Out", "100ml")]

    for pos_name in ("Nightout 100ml", "Night Out 100ml", "NIGHT-OUT 100ml"):
        result = suggest(pos_brand="Armaf", pos_name=pos_name, pos_sku="x", candidates=candidates)
        assert result and result[0].score >= 0.9, pos_name


def test_nine_pm_matches_9_pm_in_either_direction() -> None:
    one_word = candidate(1, "Afnan", "9pm", "100ml")
    two_words = candidate(2, "Afnan", "9 PM", "100ml")

    for pos_name, target in (("9 PM 100ml", one_word), ("9pm 100ml", two_words)):
        assert score(pos_brand="Afnan", pos_name=pos_name, pos_sku="x", candidate=target) >= 0.9


def test_split_word_merging_does_not_make_unrelated_names_match() -> None:
    other = candidate(1, "Armaf", "Night Out", "100ml")

    assert (
        score(pos_brand="Armaf", pos_name="Club De Nuit 100ml", pos_sku="x", candidate=other) < 0.6
    )


def test_al_majeed_and_al_majed_are_the_same_in_the_product_name() -> None:
    candidates = [candidate(1, "Lattafa", "Al Majed Oud", "100ml")]

    result = suggest(
        pos_brand="Lattafa", pos_name="Al Majeed Oud 100ml", pos_sku="x", candidates=candidates
    )

    assert result and result[0].score >= 0.9


# --- doubled brand -----------------------------------------------------------


def test_a_brand_repeated_at_the_start_of_the_name_is_stripped() -> None:
    assert strip_leading_brand("Afnan", "Afnan Afnan Historic Sahara") == "Historic Sahara"
    assert strip_leading_brand("Afnan", "Afnan Historic Sahara") == "Historic Sahara"
    assert strip_leading_brand("Afnan", "Historic Sahara") == "Historic Sahara"


def test_brand_stripping_folds_spacing_and_spelling() -> None:
    assert strip_leading_brand("Al Majeed", "AlMajed Oud Aswad") == "Oud Aswad"
    assert strip_leading_brand("Al Majed Oud", "Al Majeed Oud Oud Aswad") == "Oud Aswad"


def test_brand_stripping_leaves_a_brand_only_or_brandless_name_alone() -> None:
    assert strip_leading_brand("Afnan", "Afnan") == "Afnan"
    assert strip_leading_brand("", "Afnan Historic Sahara") == "Afnan Historic Sahara"
    assert strip_leading_brand("Afnan", "Afnanistan Sahara") == "Afnanistan Sahara"


def test_doubled_brand_row_matches_the_plain_product() -> None:
    candidates = [candidate(1, "Afnan", "Historic Sahara", "100ml")]

    result = suggest(
        pos_brand="Afnan",
        pos_name="Afnan Afnan Historic Sahara 100ml",
        pos_sku="x",
        candidates=candidates,
    )

    assert result and result[0].score >= 0.9


# --- size --------------------------------------------------------------------


def test_each_suggestion_carries_both_sizes() -> None:
    candidates = [candidate(1, "Armaf", "Tres", "50ml")]

    result = suggest(
        pos_brand="Armaf", pos_name="Tres 100ml", pos_sku="x", candidates=candidates, min_score=0
    )

    assert (result[0].pos_size_ml, result[0].candidate_size_ml) == (100, 50)
    assert result[0].size_mismatch
    assert result[0].size_warning == "Size differs: POS says 100ml, website says 50ml"


def test_matching_or_unknown_sizes_give_no_warning() -> None:
    same = suggest(
        pos_brand="Armaf",
        pos_name="Tres 150ml",
        pos_sku="x",
        candidates=[candidate(1, "Armaf", "Tres", "150 ML")],
    )
    unknown = suggest(
        pos_brand="Armaf",
        pos_name="Tres",
        pos_sku="x",
        candidates=[candidate(2, "Armaf", "Tres", "Eau de Parfum")],
    )

    assert same[0].size_warning == "" and unknown[0].size_warning == ""
    assert not same[0].size_mismatch and not unknown[0].size_mismatch
