# TODO

Debt is recorded here, with the stage that incurred it. Never `# TODO` in shipped code — see
CLAUDE.md.

## Debt

- [Stage 2] `ProductImage` derivative generation (thumb/card/full, WebP+JPEG) runs synchronously
  inside `save()`. Deliberate per requirements §2.5 — a merchant uploading a handful of images
  tolerates a ~1-2s save; a broker/worker process to avoid that cost doesn't pay for itself yet.
  Revisit if CSV bulk import (Stage 16) makes many-image imports painfully slow.

## Deferred UI work (storefront polish pass)

Named out of scope by the polish brief itself. Recorded rather than built.

- [Polish pass] **Hero band and collection sections.** The home page has a hero and product rails
  already; the brief's richer editorial treatment of them was excluded to keep the pass to the
  listing page and shared primitives.
- [Polish pass] **Mobile filter drawer.** The filter rail stacks above the grid below `lg` and is
  always expanded. On a long facet list that is a lot of scrolling before the first product. Needs
  a real decision about whether it opens as a drawer or an accordion — the cart drawer's
  `x-teleport` history (see `templates/cart/_widget.html`) is relevant prior art.
- [Polish pass] **Page transitions, parallax.** Explicitly out of scope; the motion inventory is
  deliberately closed (M1–M7) so motion cannot accumulate a little at a time.
- [Polish pass] **Skeleton loaders beyond the product image.** `sf-animate-shimmer` covers the card
  and PDP gallery only. There is no skeleton for the listing grid itself.
- [Polish pass] **Product detail redesign.** The PDP was restyled before this pass and was left
  alone by it.

## Verification owed (could not be executed in this environment)

The automation browser used during the polish pass reports `visibilityState: "hidden"` and
`document.hasFocus() === false`, and its layout viewport is pinned regardless of window size. A
hidden tab fires neither scroll events nor `requestAnimationFrame` callbacks, and `:focus-visible`
never matches. These need a human at a real browser:

- [Polish pass] **Responsive sweep at 375 / 768 / 1280 / 1920.** `.shell`'s gutter ramp
  (24 → 40 → 64px) was verified from the compiled media queries and at one viewport width only.
- [Polish pass] **Keyboard traversal.** Every focusable stop should show the brass ring, and the
  skip link should be the first stop. The rule and its scope were verified in the CSSOM; the
  traversal itself was not.
- [Polish pass] **Header scroll shadow (M6).** Verified in halves — the JS applies the correct
  state for a given `scrollY`, and the CSS resolves correctly with `data-scrolled` present — but
  never as one integrated scroll.
- [Polish pass] **Card hover (M1–M3)** and **reduced-motion emulation.** Hover needs a pointer the
  automation tool cannot synthesise; reduced motion needs the DevTools rendering override.

## Test isolation

- [Polish pass] **`StoreSettings` tests fail on a reused test database.** Four tests in
  `store/tests/` fail under a plain `pytest` run and pass under `pytest --create-db`. `CACHES` uses
  the database backend, so `django_cache_table` survives between runs and a cached singleton from a
  previous run leaks into a fresh transaction where the row does not exist. CI always builds a
  fresh database so it is never red there. The fix is probably an autouse fixture clearing the
  cache, but it touches test infrastructure shared by every app and was out of scope for a UI pass.
