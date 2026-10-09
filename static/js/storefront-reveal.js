// Storefront hero/section entrance animation (docs/design.md, "Motion" —
// storefront redesign). First-party, no new dependency: a single
// IntersectionObserver drives every [data-reveal] element, fires once per
// element, then unobserves — never re-triggers on repeat scroll.
//
// HTMX-swapped content (e.g. search suggestions) can carry [data-reveal]
// too; htmx:afterSettle re-scans so newly-inserted nodes still animate.
(function () {
  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  function reveal(el) {
    el.classList.add("is-in");
  }

  if (prefersReducedMotion || !("IntersectionObserver" in window)) {
    // No motion at all, or no observer support: show everything immediately
    // rather than leaving content permanently at opacity 0.
    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll("[data-reveal]").forEach(reveal);
    });
    document.body.addEventListener("htmx:afterSettle", function (event) {
      event.target.querySelectorAll("[data-reveal]").forEach(reveal);
    });
    return;
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        reveal(entry.target);
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.15 }
  );

  // design.md: "80ms stagger per child". The stagger is counted among an
  // element's [data-reveal] siblings, not across the whole page — a
  // document-wide index left the 30th card on the home page waiting 2.4s
  // after scrolling into view, so a fast scroller saw empty sections.
  // Capped so a long grid's last card never lags far behind its row.
  var STAGGER_MS = 80;
  var STAGGER_MAX_STEPS = 4;

  function scan(root) {
    var elements = root.querySelectorAll("[data-reveal]:not(.is-in)");
    elements.forEach(function (el) {
      var parent = el.parentElement;
      var siblings = parent
        ? Array.prototype.filter.call(parent.children, function (child) {
            return child.hasAttribute("data-reveal");
          })
        : [el];
      var step = Math.min(siblings.indexOf(el), STAGGER_MAX_STEPS);
      el.style.transitionDelay = step * STAGGER_MS + "ms";
      observer.observe(el);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    scan(document);
  });
  document.body.addEventListener("htmx:afterSettle", function (event) {
    scan(event.target);
  });
})();
