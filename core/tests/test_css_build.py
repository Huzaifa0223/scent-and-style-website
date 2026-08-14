"""The compiled Tailwind bundle is a build artefact, not a checked-in
file (static/css/app.css is gitignored), so nothing else in the suite
would notice if the build broke or if a rule quietly stopped being
emitted. These tests run the real standalone binary against the real
config and assert on its output.

Each assertion below guards something that was actually got wrong once
during the storefront polish pass, not merely something that exists.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# setup_dev.ps1 fetches the .exe, setup_dev.sh and CI fetch the extensionless
# Linux build into the same directory.
BINARY_CANDIDATES = (BASE_DIR / "tools" / "tailwindcss.exe", BASE_DIR / "tools" / "tailwindcss")
TAILWIND = next((path for path in BINARY_CANDIDATES if path.exists()), None)

requires_tailwind = pytest.mark.skipif(
    TAILWIND is None,
    reason=(
        "Tailwind standalone CLI not present in tools/ — run setup_dev.ps1 "
        "(Windows) or setup_dev.sh (Linux/CI) to fetch the pinned 3.4.19 build"
    ),
)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Build once per module: the compile takes a second or two and every
    test here asks a different question about the same output."""
    assert TAILWIND is not None
    output = tmp_path_factory.mktemp("css") / "app.css"
    result = subprocess.run(
        [
            str(TAILWIND),
            "-c",
            "tailwind.config.js",
            "-i",
            "static/css/input.css",
            "-o",
            str(output),
            "--minify",
        ],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"tailwind build failed:\n{result.stderr}"
    return output.read_text(encoding="utf-8")


@requires_tailwind
def test_the_bundle_builds_and_is_not_empty(bundle: str) -> None:
    assert len(bundle) > 10_000, "bundle is implausibly small — did content globs stop matching?"


@requires_tailwind
def test_the_brand_gold_survives_into_the_bundle(bundle: str) -> None:
    """#D8A448 is the real brand gold. The polish brief proposed #C9922F,
    sampled from a lossy screenshot; keeping the wrong one would have
    rebranded every button and hairline by a few percent."""
    assert "#d8a448" in bundle.lower()


@requires_tailwind
def test_form_widget_classes_are_reachable_from_python(bundle: str) -> None:
    """core/forms.py assigns .field/.checkbox to widgets, and tailwind.config.js
    scans ./*/forms.py so those survive purging. Without that glob they
    lived or died on whether some template happened to use the same class."""
    assert ".field{" in bundle
    assert ".checkbox{" in bundle


@requires_tailwind
def test_the_media_box_ratio_is_emitted(bundle: str) -> None:
    """Tile height parity depends on this one declaration."""
    assert "aspect-ratio:3/4" in bundle.replace(" ", "")


@requires_tailwind
def test_a_focus_visible_rule_is_emitted(bundle: str) -> None:
    assert ":focus-visible" in bundle


@requires_tailwind
def test_the_reduced_motion_guard_also_neutralises_animation_delay(bundle: str) -> None:
    """The usual form of this snippet resets animation-duration but not
    animation-delay. .grid-stagger animates with fill-mode `both`, so a
    card holds opacity 0 for the length of its delay: zeroing only the
    duration leaves a reduced-motion visitor looking at an empty grid for
    up to 440ms and then a pop-in — worse than the animation itself.
    """
    blocks = re.findall(
        r"@media \(prefers-reduced-motion:reduce\)\{(.*?)\}\s*(?=@|$)", bundle, re.S
    )
    assert blocks, "no prefers-reduced-motion block in the bundle at all"
    guard = "".join(blocks)
    assert "animation-duration" in guard
    assert "animation-delay" in guard


@requires_tailwind
def test_the_entrance_stagger_counts_by_type_not_child_position(bundle: str) -> None:
    """Regression guard. Each product tile renders as two sibling elements
    — the partial emits a JSON-LD <script> before its <a> — so :nth-child
    counts two per card and lands every delay on the wrong tile. Reverting
    this to :nth-child compiles cleanly and breaks silently.
    """
    assert "nth-of-type" in bundle
    stagger_rules = re.findall(r"\.grid-stagger[^{]*\{", bundle)
    assert stagger_rules, "the grid-stagger rules were purged"
    assert not any("nth-child" in rule for rule in stagger_rules), (
        "grid-stagger is using :nth-child again; the JSON-LD <script> "
        "siblings make that count two elements per card"
    )
