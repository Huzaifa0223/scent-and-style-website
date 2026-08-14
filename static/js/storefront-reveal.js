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

  function scan(root) {
    var elements = root.querySelectorAll("[data-reveal]:not(.is-in)");
    elements.forEach(function (el, index) {
      el.style.transitionDelay = index * 80 + "ms";
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
