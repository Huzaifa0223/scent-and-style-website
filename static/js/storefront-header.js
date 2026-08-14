// Storefront header scroll state (docs/design.md, "Motion" — M6).
// First-party, no dependency: toggles a data-scrolled attribute so the
// sticky header gains a shadow only once content is actually passing
// underneath it. At scroll position 0 there is nothing to separate the
// header from, so the shadow would be decoration rather than signal.
//
// The attribute is the entire contract — all styling lives in the
// template's data-[scrolled]: variants, so this file never touches
// classes and cannot drift out of sync with the design tokens.
(function () {
  "use strict";

  var header = document.querySelector("[data-sticky-header]");
  if (!header) {
    return;
  }

  // Matches the brief's 24px threshold. Below this a scroll is usually an
  // accidental trackpad nudge, and toggling a shadow on and off across it
  // reads as flicker.
  var SCROLL_THRESHOLD_PX = 24;
  var ticking = false;

  function apply() {
    ticking = false;
    if (window.scrollY > SCROLL_THRESHOLD_PX) {
      header.setAttribute("data-scrolled", "");
    } else {
      header.removeAttribute("data-scrolled");
    }
  }

  function onScroll() {
    // rAF-coalesced: scroll fires far more often than the compositor can
    // paint, and this writes an attribute that invalidates style.
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(apply);
    }
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  // Set the initial state: a reload partway down a page starts scrolled.
  apply();
})();
